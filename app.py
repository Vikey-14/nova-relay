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
from urllib.parse import urlsplit
import httpx
import os
import re
import time
import unicodedata
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


# Topic searches should return actual developments rather
# than quizzes, trivia pages or viewing/schedule guides.
#
# These patterns are deliberately narrow. They reject only
# titles that clearly advertise interactive content or a
# utility guide rather than reporting a development.
NEWS_LOW_VALUE_TOPIC_TITLE_PATTERNS = (
    # English and shared terms
    r"\bquiz\b",
    r"\btrivia\b",
    r"\bcan you name\b",
    r"^\s*who am i\b",
    r"\bguess (?:the|this|which|who)\b",
    r"\btest your knowledge\b",

    # Promotional or advertorial pages rather than
    # meaningful current developments.
    r"^\s*(?:holiday|summer|winter)\s+"
    r"travel\s+with\b",

    r"\blaunch(?:es|ed|ing)?\s+"
    r"(?:a\s+)?(?:global\s+)?competition\b"
    r".{0,160}\b"
    r"(?:fans?|dreams?|prizes?|win)\b",

    r"\b(?:fans?|customers?)['’]?\s+"
    r"(?:ultimate\s+)?dreams?\b",

    # Basic equivalents for other supported
    # provider languages.
    r"^\s*(?:urlaubsreise|voyage|viaje)\s+"
    r"(?:mit|avec|con)\b",

    r"\b(?:gewinnspiel|concours|concurso)\b"
    r".{0,120}\b"
    r"(?:fans?|gewinnen|gagner|ganar|"
    r"prix|premio|traum|reve|sueno)\b",

    # Titles that are only domains or official site pages,
    # rather than reports about a current development.
    r"^\s*(?:www\.)?"
    r"[a-z0-9-]+"
    r"(?:\.[a-z0-9-]+)+"
    r"\s*$",

    # English
    r"(?:^|[|:–—-]\s*)"
    r"(?:the\s+)?official\s+"
    r"(?:site|website|homepage)\s+"
    r"(?:of|for)\b",

    # Hindi
    r"(?:^|[|:–—-]\s*)"
    r"आधिकारिक\s+"
    r"(?:वेबसाइट|साइट|मुखपृष्ठ)\b",

    # German
    r"(?:^|[|:–—-]\s*)"
    r"(?:offizielle\s+"
    r"(?:website|seite|homepage)|"
    r"offizieller\s+internetauftritt)\b",

    # French
    r"(?:^|[|:–—-]\s*)"
    r"(?:site\s+officiel|"
    r"page\s+d(?:['’]|\s)+accueil\s+officielle)\b",

    # Spanish
    r"(?:^|[|:–—-]\s*)"
    r"(?:sitio\s+oficial|"
    r"pagina\s+oficial|"
    r"pagina\s+de\s+inicio\s+oficial)\b",

    r"\bhow to watch\b",
    r"\bwhere to watch\b",
    r"\blive stream(?:ing)?\b",
    r"\bchannel(?:,| and)? streaming info\b",

    r"\bschedule for (?:the )?rest of\b",
    r"^\s*when is .{0,100}\bnext "
    r"(?:match|game|race)\b",

    # Roster/listicle pages rather than current developments.
    r"\b(?:full|complete) list of\b"
    r".{0,120}\b"
    r"(?:players?|stars?|teams?|squads?|"
    r"participants?|entries?|fixtures?)\b",

    r"\b(?:players?|stars?|teams?|squads?)\b"
    r".{0,120}\b"
    r"(?:full|complete) list\b",

    # Hindi
    r"(?:खिलाड़ी|खिलाड़ियों|टीम|टीमों|दल)"
    r".{0,80}"
    r"(?:पूरी सूची|पूरी लिस्ट|संपूर्ण सूची)",

    r"(?:पूरी सूची|पूरी लिस्ट|संपूर्ण सूची)"
    r".{0,80}"
    r"(?:खिलाड़ी|खिलाड़ियों|टीम|टीमों|दल)",
    r"क्विज",
    r"क्या आप .{0,80} नाम बता",
    r"पहचानिए",
    r"अपना ज्ञान परख",
    r"कैसे देखें",
    r"कहाँ देखें",
    r"लाइव स्ट्रीम",

    # German
    r"\bwer bin ich\b",
    r"\bkannst du .{0,80}\bnennen\b",
    r"\bteste dein wissen\b",
    r"\bwie .{0,80}\bsehen\b",
    r"\bwo .{0,80}\bsehen\b",
    r"\b(?:vollstandige|komplette) liste\b"
    r".{0,80}\b"
    r"(?:spieler|teams|kader|teilnehmer)\b",

    # French
    r"\bqui suis je\b",
    r"\bpouvez vous .{0,80}\bnommer\b",
    r"\btestez vos connaissances\b",
    r"\bcomment regarder\b",
    r"\bou regarder\b",
    r"\bliste complete\b"
    r".{0,80}\b"
    r"(?:joueurs|equipes|participants)\b",

    # Spanish
    r"\bquien soy\b",
    r"\bpuedes .{0,80}\bnombrar\b",
    r"\bpon a prueba tus conocimientos\b",
    r"\bcomo ver\b",
    r"\bdonde ver\b",
    r"\blista completa\b"
    r".{0,80}\b"
    r"(?:jugadores|equipos|plantillas|participantes)\b",
)


def _news_fold_title(
    value: object,
) -> str:
    """
    Fold accents in Latin text without damaging scripts
    such as Hindi Devanagari.
    """

    output: list[str] = []

    for character in str(
        value or ""
    ).casefold():
        decomposed = unicodedata.normalize(
            "NFKD",
            character,
        )

        first = (
            decomposed[0]
            if decomposed
            else character
        )

        if (
            first.isascii()
            and first.isalnum()
        ):
            output.append(first)

        else:
            output.append(character)

    return " ".join(
        "".join(output).split()
    )


def _is_low_value_topic_title(
    title: str,
    topic: str,
) -> bool:
    # Do not apply this to generic country or general
    # headline requests. It is specifically for a
    # requested topic such as Cricket or Formula 1.
    if not str(
        topic or ""
    ).strip():
        return False

    folded = _news_fold_title(
        title
    )

    topic_folded = _news_fold_title(
        topic
    )

    # "Formula" alone does not mean Formula 1.
    # This prevents Formula Sun, Formula E and other
    # unrelated formula-based competitions from being
    # returned for a Formula 1 request.
    formula_one_topics = {
        "formula 1",
        "formula one",
        "f1",
        "formel 1",
        "formule 1",
        "formula uno",
    }

    if (
        topic_folded
        in formula_one_topics
        and not re.search(
            r"(?<!\w)"
            r"(?:"
            r"(?:formula|formel|formule)\s*"
            r"(?:1|one|uno)"
            r"|f1"
            r")"
            r"(?!\w)",
            folded,
            flags=re.I | re.UNICODE,
        )
    ):
        return True

    # Sports searches may match politicians or election
    # stories merely because the person once played sport.
    # Reject those when the requested sport is not visible
    # anywhere in the title.
    sport_topics = {
        "football",
        "soccer",
        "cricket",
        "formula 1",
        "formula one",
        "f1",

        "fussball",
        "fußball",
        "kricket",

        "futbol",
        "fútbol",
        "criquet",

        "फुटबॉल",
        "क्रिकेट",
    }

    politics_pattern = (
        r"(?:"
        # English
        r"\bgop\b|"
        r"\bdemocrat(?:ic)?\b|"
        r"\brepublican\b|"
        r"\bprimary\b|"
        r"\belection\b|"
        r"\bcandidate\b|"
        r"\bsenate\b|"
        r"\bcongress\b|"
        r"\bparliament\b|"
        r"\bdistrict\b|"
        r"\bballot\b|"

        # Hindi
        r"चुनाव|उम्मीदवार|संसद|निर्वाचन|"

        # German
        r"\bwahl\b|"
        r"\bkandidat(?:in)?\b|"
        r"\bbundestag\b|"
        r"\bparlament\b|"

        # French
        r"\belection\b|"
        r"\bcandidat(?:e)?\b|"
        r"\bparlement\b|"
        r"\bcirconscription\b|"

        # Spanish
        r"\beleccion\b|"
        r"\bcandidato\b|"
        r"\bcongreso\b|"
        r"\bparlamento\b|"
        r"\bdistrito\b"
        r")"
    )

    if (
        topic_folded in sport_topics
        and re.search(
            politics_pattern,
            folded,
            flags=re.I | re.UNICODE,
        )
        and topic_folded
        not in folded
    ):
        return True

    return any(
        re.search(
            pattern,
            folded,
            flags=re.I | re.UNICODE,
        )
        for pattern in (
            NEWS_LOW_VALUE_TOPIC_TITLE_PATTERNS
        )
    )



def _is_news_homepage_url(
    value: object,
) -> bool:
    """
    Return True when the provider supplied a publisher's
    homepage instead of a specific news article URL.
    """

    raw = str(
        value or ""
    ).strip()

    if not raw:
        return False

    try:
        parsed = urlsplit(
            raw
        )

    except Exception:
        return False

    path = (
        parsed.path
        or "/"
    ).strip().casefold()

    normalized_path = (
        path.rstrip("/")
        or "/"
    )

    return bool(
        normalized_path
        in {
            "/",
            "/index",
            "/index.html",
            "/index.php",
            "/default",
            "/default.aspx",
            "/home",
            "/homepage",
        }
        and not parsed.query
    )



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
    topic: str = "",
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

        if _is_low_value_topic_title(
            title,
            topic,
        ):
            continue

        # A publisher homepage is not an individual
        # article, even when NewsAPI labels it as one.
        if _is_news_homepage_url(
            article.get("url")
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

        # Everything is required when Top Headlines
        # cannot represent the requested scope.
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
        topic=topic,
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