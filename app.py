from fastapi import FastAPI, HTTPException, Header, Query
from typing import Optional
import os, httpx

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

    url = "https://api.exchangerate.host/convert"
    params = {
        "access_key": EXCHANGE_RATE_KEY,
        "from": from_curr,
        "to": to_curr,
        "amount": amount,
    }

    async with httpx.AsyncClient(timeout=12) as c:
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

    return {
        "ok": True,
        "provider": "exchangerate.host",
        "from": from_curr,
        "to": to_curr,
        "amount": amount,
        "rate": float(rate),
        "result": float(result),
    }

    
@app.get("/news")
async def news(topic: str = "", country: str = "in", lang: str = "en",
               count: int = 10, x_nova_key: Optional[str] = Header(default=None)):
    _check(x_nova_key)
    _require_key("NEWS_API_KEY", NEWS)
    async with httpx.AsyncClient(timeout=12) as c:
        if topic:
            url = "https://newsapi.org/v2/everything"
            params = {
                "q": topic,
                "language": lang,
                "apiKey": NEWS,
                "pageSize": min(max(count, 1), 20),
                "sortBy": "publishedAt",
            }
        else:
            url = "https://newsapi.org/v2/top-headlines"
            params = {
                "country": country or "in",
                "apiKey": NEWS,
                "pageSize": min(max(count, 1), 20),
            }
        r = await c.get(url, params=params)
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json()
