from fastapi import FastAPI, HTTPException, Header, Query
from typing import Optional
import os, httpx, time

app = FastAPI(title="Nova Relay")

# Server-side secrets (set on Render or your host)
OPENWEATHER = os.environ["OPENWEATHER_API_KEY"]
NEWS        = os.environ["NEWS_API_KEY"]

# ✅ Currency exchange provider key.
# Keep this ONLY on Render/local relay env, never inside Nova desktop.
EXCHANGE_RATE_KEY = (
    os.getenv("EXCHANGERATE_HOST_API_KEY", "").strip()
    or os.getenv("EXCHANGERATE_API_KEY", "").strip()
    or os.getenv("EXCHANGE_RATE_API_KEY", "").strip()
)

RELAY_TOKEN = os.getenv("NOVA_RELAY_TOKEN", "")
_CURRENCY_RATE_CACHE = {}
_CURRENCY_RATE_CACHE_TTL_SECONDS = 6 * 60 * 60


def _check(tok: Optional[str]):
    if RELAY_TOKEN and tok != RELAY_TOKEN:
        raise HTTPException(401, "bad token")

def _require_key(service_name: str, key_value: str):
    if not key_value:
        # ✅ Relay stays alive; endpoint returns a clean error
        raise HTTPException(503, f"{service_name} is not configured on the relay server")


@app.get("/health")
def health():
    return {
        "ok": True,
        "openweather_configured": bool(OPENWEATHER),
        "news_configured": bool(NEWS),
        "currency_configured": bool(EXCHANGE_RATE_KEY),
        "auth_enabled": bool(RELAY_TOKEN),
    }


@app.get("/weather")
async def weather(city: str, units: str = "metric",
                  x_nova_key: Optional[str] = Header(default=None)):
    _check(x_nova_key)
    _require_key("OPENWEATHER_API_KEY", OPENWEATHER)
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER, "units": units}
    async with httpx.AsyncClient(timeout=8) as c:
        r = await c.get(url, params=params)
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json()



@app.get("/forecast")
async def forecast(city: str, units: str = "metric",
                   x_nova_key: Optional[str] = Header(default=None)):
    _check(x_nova_key)
    _require_key("OPENWEATHER_API_KEY", OPENWEATHER)
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"q": city, "appid": OPENWEATHER, "units": units}
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.get(url, params=params)
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json()



@app.get("/currency")
async def currency(
    from_code: str = Query(..., alias="from"),
    to: str = Query(...),
    amount: float = 1.0,
    x_nova_key: str | None = Header(default=None),
):
    """
    Currency relay endpoint.

    Nova desktop calls this:
      /currency?from=USD&to=INR&amount=100

    The relay secretly adds your server-side exchange-rate API key.
    Users never need their own currency API key.
    """
    _check(x_nova_key)

    if not EXCHANGE_RATE_KEY:
        raise HTTPException(500, "currency API key missing on relay")

    from_curr = (from_code or "").upper().strip()
    to_curr = (to or "").upper().strip()

    if not from_curr or not to_curr:
        raise HTTPException(400, "missing from/to currency")

    if amount < 0:
        raise HTTPException(400, "amount cannot be negative")

    # Same currency conversion: no API call needed.
    if from_curr == to_curr:
        return {
            "ok": True,
            "provider": "identity",
            "from": from_curr,
            "to": to_curr,
            "amount": amount,
            "rate": 1.0,
            "result": amount,
        }
    

    cache_key = (from_curr, to_curr)
    cached = _CURRENCY_RATE_CACHE.get(cache_key)
    now = time.time()

    if cached and (now - cached.get("ts", 0)) <= _CURRENCY_RATE_CACHE_TTL_SECONDS:
        rate = float(cached["rate"])
        result = float(amount) * rate

        return {
            "ok": True,
            "provider": "exchangerate.host-cache",
            "from": from_curr,
            "to": to_curr,
            "amount": amount,
            "rate": rate,
            "result": result,
        }

    url = "https://api.exchangerate.host/convert"
    params = {
        "access_key": EXCHANGE_RATE_KEY,
        "from": from_curr,
        "to": to_curr,
        "amount": amount,
    }

    timeout = httpx.Timeout(20.0, connect=6.0)

    async with httpx.AsyncClient(timeout=timeout) as c:
        r = await c.get(url, params=params)


    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)

    data = r.json()

    if data.get("success") is False:
        raise HTTPException(502, data)

    info = data.get("info") or {}
    rate = info.get("rate")
    result = data.get("result")

    if rate is None and result is not None and amount != 0:
        rate = float(result) / float(amount)

    if result is None and rate is not None:
        result = float(amount) * float(rate)

    if rate is None or result is None:
        raise HTTPException(502, {"error": "unexpected currency provider response", "data": data})

    # ✅ Store successful rate so future same-pair conversions are fast.
    # Example:
    # First USD -> EUR call fetches from exchangerate.host.
    # Next USD -> EUR call within 6 hours uses relay cache.
    _CURRENCY_RATE_CACHE[cache_key] = {
        "rate": float(rate),
        "ts": time.time(),
    }

    return {
        "ok": True,
        "provider": "exchangerate.host",
        "from": from_curr,
        "to": to_curr,
        "amount": amount,
        "rate": float(rate),
        "result": float(result),
    }

    
NEWSAPI_LANGUAGES = {
    "ar",
    "de",
    "en",
    "es",
    "fr",
    "he",
    "it",
    "nl",
    "no",
    "pt",
    "ru",
    "sv",
    "ud",
    "zh",
}

NEWSAPI_CATEGORIES = {
    "general",
    "business",
    "entertainment",
    "health",
    "science",
    "sports",
    "technology",
}

NEWSAPI_TOP_COUNTRIES = {
    "ae", "ar", "at", "au", "be", "bg", "br", "ca", "ch",
    "cn", "co", "cu", "cz", "de", "eg", "fr", "gb", "gr",
    "hk", "hu", "id", "ie", "il", "in", "it", "jp", "kr",
    "lt", "lv", "ma", "mx", "my", "ng", "nl", "no", "nz",
    "ph", "pl", "pt", "ro", "rs", "ru", "sa", "se", "sg",
    "si", "sk", "th", "tr", "tw", "ua", "us", "ve", "za",
}


@app.get("/news")
async def news(
    topic: str = "",
    country: str = "in",
    country_name: str = "",
    category: str = "",
    lang: str = "en",
    count: int = 10,
    x_nova_key: str | None = Header(
        default=None
    ),
):
    _check(x_nova_key)

    topic = str(
        topic or ""
    ).strip()

    country = str(
        country or ""
    ).strip().casefold()

    country_name = str(
        country_name or ""
    ).strip()

    category = str(
        category or ""
    ).strip().casefold()

    lang = str(
        lang or "en"
    ).strip().casefold()

    count = min(
        max(
            int(count or 10),
            1,
        ),
        20,
    )

    if category not in NEWSAPI_CATEGORIES:
        category = ""

    country_supported = bool(
        country
        and country
        in NEWSAPI_TOP_COUNTRIES
    )

    use_everything = bool(
        country
        and not country_supported
    ) or bool(
        topic
        and not country
        and not category
    )

    if use_everything:
        url = (
            "https://newsapi.org/v2/everything"
        )

        query_parts: list[str] = []

        if topic:
            query_parts.append(
                f"({topic})"
            )

        if country and country_name:
            query_parts.append(
                f'"{country_name}"'
            )

        if category:
            query_parts.append(
                category
            )

        search_query = " AND ".join(
            query_parts
        ).strip()

        if not search_query:
            search_query = (
                country_name
                or topic
                or category
                or "world news"
            )

        params = {
            "q": search_query,
            "language": (
                lang
                if lang in NEWSAPI_LANGUAGES
                else "en"
            ),
            "pageSize": count,
            "sortBy": "publishedAt",
        }

    else:
        url = (
            "https://newsapi.org/v2/top-headlines"
        )

        params = {
            "pageSize": count,
        }

        if topic:
            params["q"] = topic

        if country_supported:
            params["country"] = country

        if category:
            params["category"] = category

    async with httpx.AsyncClient(
        timeout=12
    ) as client:
        response = await client.get(
            url,
            params=params,
            headers={
                "X-Api-Key": NEWS,
            },
        )

    if response.status_code != 200:
        raise HTTPException(
            response.status_code,
            response.text,
        )

    return response.json()
