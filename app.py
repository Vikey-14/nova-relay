from fastapi import FastAPI, HTTPException, Header
import os, httpx

app = FastAPI(title="Nova Relay")

# Server-side secrets (set on Render or your host)
OPENWEATHER = os.environ["OPENWEATHER_API_KEY"]
NEWS        = os.environ["NEWS_API_KEY"]
RELAY_TOKEN = os.getenv("NOVA_RELAY_TOKEN", "")

def _check(tok: str | None):
    if RELAY_TOKEN and tok != RELAY_TOKEN:
        raise HTTPException(401, "bad token")

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/weather")
async def weather(city: str, units: str = "metric",
                  x_nova_key: str | None = Header(default=None)):
    _check(x_nova_key)
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER, "units": units}
    async with httpx.AsyncClient(timeout=8) as c:
        r = await c.get(url, params=params)
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json()

@app.get("/forecast")
async def forecast(city: str, units: str = "metric",
                   x_nova_key: str | None = Header(default=None)):
    _check(x_nova_key)
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"q": city, "appid": OPENWEATHER, "units": units}
    async with httpx.AsyncClient(timeout=12) as c:
        r = await c.get(url, params=params)
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text)
    return r.json()

@app.get("/news")
async def news(topic: str = "", country: str = "in", lang: str = "en",
               count: int = 10, x_nova_key: str | None = Header(default=None)):
    _check(x_nova_key)
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
