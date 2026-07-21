from datetime import (
    datetime,
    timedelta,
    timezone,
)
from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Query,
)
from typing import Optional

import httpx
import os
import time
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


# Nova should not describe old archived articles
# as the latest news.
NEWS_FRESH_DAYS = 7

# Top Headlines may not arrive newest-first.
# Fetch a broad pool, then sort it ourselves.
NEWS_TOP_FETCH_SIZE = 100


def _news_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _news_cutoff() -> datetime:
    return _news_now() - timedelta(
        days=NEWS_FRESH_DAYS
    )


def _news_iso(
    value: datetime,
) -> str:
    return value.astimezone(
        timezone.utc
    ).isoformat(
        timespec="seconds"
    ).replace(
        "+00:00",
        "Z",
    )


def _parse_news_time(
    value: object,
) -> Optional[datetime]:
    raw = str(
        value or ""
    ).strip()

    if not raw:
        return None

    if raw.endswith("Z"):
        raw = (
            raw[:-1]
            + "+00:00"
        )

    try:
        parsed = datetime.fromisoformat(
            raw
        )

    except Exception:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def _prepare_news_payload(
    payload: dict,
    count: int,
) -> dict:
    """
    Keep only verifiably recent articles, sort newest
    first and remove duplicate titles.
    """

    result = dict(
        payload
        if isinstance(
            payload,
            dict,
        )
        else {}
    )

    articles = (
        result.get("articles")
        or []
    )

    cutoff = _news_cutoff()

    prepared: list[
        tuple[
            datetime,
            dict,
        ]
    ] = []

    seen: set[str] = set()

    for article in articles:
        if not isinstance(
            article,
            dict,
        ):
            continue

        title = str(
            article.get("title")
            or ""
        ).strip()

        if (
            not title
            or title.casefold()
            in {
                "[removed]",
                "removed",
                "null",
                "none",
            }
        ):
            continue

        published = _parse_news_time(
            article.get(
                "publishedAt"
            )
        )

        # Do not call an article "latest" when its
        # publication time cannot be verified.
        if (
            published is None
            or published < cutoff
        ):
            continue

        key = " ".join(
            title.casefold().split()
        )

        if key in seen:
            continue

        seen.add(key)

        prepared.append(
            (
                published,
                article,
            )
        )

    prepared.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    selected = [
        article
        for _published, article
        in prepared[:count]
    ]

    result["articles"] = selected
    result["totalResults"] = len(
        selected
    )

    result["nova_freshness"] = {
        "days": NEWS_FRESH_DAYS,
        "returned": len(selected),
        "sorted": (
            "publishedAt_descending"
        ),
    }

    return result

def _build_news_everything_query(
    topic: str,
    country_name: str,
    category: str,
) -> str:
    """
    Build a strict query for NewsAPI Everything.

    Examples:
        football
        -> (football)

        football + Germany
        -> (football) AND "Germany"

        robotics + technology + Japan
        -> (robotics) AND technology AND "Japan"
    """

    parts: list[str] = []

    clean_topic = str(
        topic or ""
    ).strip()

    clean_category = str(
        category or ""
    ).strip()

    clean_country = str(
        country_name or ""
    ).strip()

    if clean_topic:
        parts.append(
            f"({clean_topic})"
        )

    if clean_category:
        parts.append(
            clean_category
        )

    # World is represented by having no country
    # restriction. Do not require the literal word
    # "world" for a topic such as worldwide football.
    if (
        clean_country
        and clean_country.casefold()
        != "world"
    ):
        parts.append(
            f'"{clean_country}"'
        )

    # A completely generic worldwide request still
    # needs a valid Everything search query.
    if not parts:
        if (
            clean_country
            and clean_country.casefold()
            == "world"
        ):
            return (
                "(world OR global "
                "OR international)"
            )

        return "latest news"

    return " AND ".join(
        parts
    ).strip()



@app.get("/news")
async def news(
    topic: str = "",
    country: str = "in",
    country_name: str = "",
    category: str = "",
    lang: str = "en",
    mode: str = "auto",
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

    mode = str(
        mode or "auto"
    ).strip().casefold()

    if mode not in {
        "auto",
        "everything",
    }:
        mode = "auto"

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

    world_scope = bool(
        country_name
        and country_name.casefold()
        == "world"
    )

    no_search_scope = not any(
        (
            topic,
            country,
            category,
        )
    )

    use_everything = bool(
        mode == "everything"

        # Topic requests require both relevance
        # and reliable newest-first ordering.
        or bool(topic)

        or (
            country
            and not country_supported
        )
        or world_scope
        or no_search_scope
    )

    if use_everything:
        url = (
            "https://newsapi.org/v2/everything"
        )

        search_query = (
            _build_news_everything_query(
                topic,
                country_name,
                category,
            )
        )

        now = _news_now()
        cutoff = _news_cutoff()

        params = {
            "q": search_query,

            "language": (
                lang
                if lang in NEWSAPI_LANGUAGES
                else "en"
            ),

            # Explicit freshness window.
            "from": _news_iso(
                cutoff
            ),
            "to": _news_iso(
                now
            ),

            "pageSize": min(
                max(
                    count * 4,
                    20,
                ),
                100,
            ),

            # Latest means newest first.
            "sortBy": "publishedAt",
        }

        # Topic, category and named-country searches
        # should visibly match the article title.
        #
        # A completely generic worldwide request is
        # intentionally broader and may match the title,
        # description or available content.
        if (
            topic
            or category
            or (
                country_name
                and country_name.casefold()
                != "world"
            )
        ):
            params["searchIn"] = "title"

    else:
        url = (
            "https://newsapi.org/v2/top-headlines"
        )

        params = {
            # Top Headlines may not arrive newest-first,
            # so request a broad pool and sort it below.
            "pageSize": (
                NEWS_TOP_FETCH_SIZE
            ),
        }

        if topic:
            params["q"] = topic

        if country_supported:
            params["country"] = country

        if category:
            params["category"] = category

    endpoint_name = (
        "everything"
        if use_everything
        else "top-headlines"
    )

    print(
        "[NEWS_RELAY] REQUEST "
        f"mode={mode!r} "
        f"endpoint={endpoint_name!r} "
        f"topic={topic!r} "
        f"country={country!r} "
        f"country_name={country_name!r} "
        f"category={category!r} "
        f"count={count!r}",
        flush=True,
    )

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

    payload = response.json()

    if not isinstance(
        payload,
        dict,
    ):
        raise HTTPException(
            502,
            "invalid news provider payload",
        )

    payload = _prepare_news_payload(
        payload,
        count,
    )

    payload["nova_endpoint"] = (
        endpoint_name
    )

    print(
        "[NEWS_RELAY] RESULT "
        f"endpoint={endpoint_name!r} "
        f"returned="
        f"{len(payload.get('articles') or [])!r} "
        f"fresh_days={NEWS_FRESH_DAYS!r}",
        flush=True,
    )

    return payload