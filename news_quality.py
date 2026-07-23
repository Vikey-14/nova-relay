from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import re
import unicodedata


# Conservative by design:
#
# A clean partial result is better than filling a News answer
# with explainers, guides, promotions or entertainment pieces.
NON_NEWS_PATTERNS = (
    # Question-style, interactive and quiz content.
    r"\?\s*$",
    r"\b(?:quiz|trivia|can you name|who am i|"
    r"guess (?:the|this|which|who)|test your knowledge)\b",

    # English evergreen explanations and background articles.
    r"^\s*(?:what (?:is|are|does)|"
    r"how (?:does|do|is|are|can)|"
    r"who is|should (?:you|i|we)|will your)\b",

    r"^\s*why (?:do|is .{0,100}\bcalled|"
    r"do they call)\b",

    r"\bwhat makes\b",

    r"\b(?:everything you need to know|"
    r"things? to know|"
    r"beginner(?:'s)? guide|"
    r"complete guide|guide to|"
    r"explainer|explained)\b",

    r"^\s*(?:the )?"
    r"(?:history|origin|origins|meaning) of\b",

    r"\b(?:difference between|timeline of|"
    r"key takeaways|what we learned|"
    r"week in review|recap)\b",

    # Opinion, commentary and feature formats.
    r"^\s*(?:opinion|analysis|commentary|comment|"
    r"editorial|review|profile)\s*[:|-]",

    r"\b(?:op[- ]ed|q\s*&\s*a|"
    r"in conversation with|exclusive interview|"
    r"interview with)\b",

    # Rankings, comparisons and listicles.
    r"^\s*(?:top|best)\s+\d+\b",
    r"^\s*\d+\s+(?:best|top|ways|tips|"
    r"things|reasons)\b",

    r"\b(?:ranked|ranking|pros and cons|"
    r"comparison|versus comparison)\b",

    r"\b(?:full|complete) list of\b",

    # Viewing and sports-utility pages.
    r"\b(?:how to watch|where to watch|"
    r"live stream(?:ing)?|streaming info)\b",

    r"^\s*when is .{0,120}\b"
    r"(?:match|game|race|event)\b",

    r"\b(?:full|complete) schedule\b",

    r"\b(?:fixtures?|lineups?|starting lineup|"
    r"probable lineup|prediction|betting tips?|"
    r"betting odds?|fantasy picks?)\b",

    # Galleries, videos, shows and personality content.
    r"\b(?:photo gallery|gallery|watch the video|"
    r"podcast|episode \d+)\b",

    r"\bcollaboration\b"
    r".{0,160}\b"
    r"(?:youtube|season\s+\d+|series|show)\b",

    r"\b(?:youtube|podcast|online series)\b"
    r".{0,100}\b"
    r"(?:returns?|season\s+\d+)\b",

    r"\b(?:influencer|content creator)\b"
    r".{0,160}\b"
    r"(?:pose|challenge|prank|reaction|viral)\b",

    r"\b(?:mocks?|roasts?|jokes? about|"
    r"viral reaction|internet reacts)\b",

    # Advertising, promotions and press releases.
    r"\b(?:sponsored content|partner content|"
    r"advertorial|press release|paid post|"
    r"giveaway)\b",

    r"^\s*(?:holiday|summer|winter) travel with\b",

    r"\blaunch(?:es|ed|ing)? "
    r"(?:a )?(?:global )?competition\b"
    r".{0,160}\b"
    r"(?:fans?|dreams?|prizes?|win)\b",

    r"\b(?:coupon|promo code|discount code|"
    r"sale of up to \d+%|"
    r"discount of up to \d+%)\b",

    # Bare domains and homepage titles.
    r"^\s*(?:www\.)?"
    r"[a-z0-9-]+"
    r"(?:\.[a-z0-9-]+)+\s*$",

    r"(?:^|[|:–—-]\s*)"
    r"(?:the\s+)?official\s+"
    r"(?:site|website|homepage)\s+"
    r"(?:of|for)\b",

    # Hindi and Hinglish article formats.
    r"(?:क्या (?:है|हैं)|"
    r"कैसे (?:काम|करें|देखें|होता|होती)|"
    r"कौन है|क्यों कहा जाता है)",

    r"(?:पूरी जानकारी|जानिए|गाइड|इतिहास|"
    r"मतलब|पूरी सूची|पूरी लिस्ट)",

    r"(?:कहाँ देखें|कब है|लाइव स्ट्रीम|"
    r"लाइनअप|भविष्यवाणी|ऑड्स)",

    r"(?:तस्वीरें|फोटो गैलरी|वीडियो देखें|"
    r"पॉडकास्ट|रिव्यू|विश्लेषण|राय)",

    r"(?:प्रायोजित|स्पॉन्सर्ड|ऑफर|छूट|"
    r"आधिकारिक वेबसाइट|आधिकारिक साइट|"
    r"यूट्यूब पर वापसी)",

    # German. Accents are folded before matching.
    r"^\s*(?:was (?:ist|sind)|"
    r"wie (?:funktioniert|kann|geht)|"
    r"warum (?:nennt|heisst)|wer ist)\b",

    r"\b(?:ratgeber|leitfaden|"
    r"geschichte (?:von|des|der)|"
    r"bedeutung (?:von|des|der))\b",

    r"\b(?:alles was (?:sie|du) wissen "
    r"(?:mussen|musst)|tipps|besten|ranking|"
    r"vergleich|testbericht)\b",

    r"\b(?:meinung|analyse|kommentar|interview|"
    r"podcast|bildergalerie|fotogalerie)\b",

    r"\b(?:wo (?:sehen|schauen)|wann ist|"
    r"spielplan|aufstellung|spielprognose|"
    r"wettprognose|wettquoten)\b",

    r"\b(?:gewinnspiel|rabattcode|werbung|"
    r"offizielle website|offizielle seite|"
    r"offizielle homepage)\b",

    # French. Accents are folded before matching.
    r"^\s*(?:qu(?:'|’)est ce que|"
    r"comment (?:fonctionne|faire|regarder)|"
    r"pourquoi (?:appelle t on|s appelle)|"
    r"qui est)\b",

    r"\b(?:guide (?:de|du|des|pour)|"
    r"histoire (?:de|du|des)|"
    r"signification (?:de|du|des))\b",

    r"\b(?:tout ce qu(?:'|’)il faut savoir|"
    r"conseils|meilleurs|classement|"
    r"comparatif)\b",

    r"\b(?:avis|analyse|commentaire|interview|"
    r"podcast|galerie photos?)\b",

    r"\b(?:ou regarder|quand (?:est|a lieu)|"
    r"programme|composition|pronostic sportif|"
    r"pronostic de match|cotes)\b",

    r"\b(?:concours|promotion|contenu sponsorise|"
    r"site officiel|page d accueil officielle)\b",

    # Spanish. Accents are folded before matching.
    r"^\s*(?:que (?:es|son)|"
    r"como (?:funciona|hacer|ver)|"
    r"por que se llama|quien es)\b",

    r"\b(?:guia (?:de|para|sobre|completa)|"
    r"historia (?:de|del|de la)|"
    r"significado (?:de|del|de la))\b",

    r"\b(?:todo lo que necesitas saber|"
    r"consejos|mejores|ranking|comparativa)\b",

    r"\b(?:opinion|analisis|comentario|"
    r"entrevista|resena|podcast|"
    r"galeria de fotos)\b",

    r"\b(?:donde ver|"
    r"cuando (?:es|se juega|tiene lugar)|"
    r"calendario|alineacion|pronostico deportivo|"
    r"pronostico del partido|cuotas)\b",

    r"\b(?:sorteo|descuento|"
    r"contenido patrocinado|"
    r"sitio oficial|pagina oficial)\b",
)


NON_NEWS_URL_MARKERS = (
    "/opinion/",
    "/commentary/",
    "/editorial/",
    "/analysis/",
    "/explainer/",
    "/explainers/",
    "/feature/",
    "/features/",
    "/profile/",
    "/interview/",
    "/review/",
    "/reviews/",
    "/how-to/",
    "/guide/",
    "/guides/",
    "/quiz/",
    "/trivia/",
    "/gallery/",
    "/galleries/",
    "/photos/",
    "/podcast/",
    "/sponsored/",
    "/advertorial/",
    "/press-release/",
    "/lifestyle/",
)


# The item must report a time-bound event, announcement,
# decision, result, market movement, legal action, conflict,
# disaster, discovery or another genuine development.
CURRENT_EVENT_PATTERNS = (
    # English reporting verbs and developments.
    r"\b(?:announc(?:e|es|ed|ing)|"
    r"confirm(?:s|ed)?|say(?:s|said)?|"
    r"warn(?:s|ed)?|report(?:s|ed)?|"
    r"reveal(?:s|ed)?|unveil(?:s|ed)?|"
    r"launch(?:es|ed)?|introduc(?:e|es|ed)|"
    r"present(?:s|ed)?|hold(?:s|held)|"
    r"enter(?:s|ed)?|plan(?:s|ned)?|"
    r"(?:is|are) (?:likely|set|expected) to)\b",

    r"\b(?:win(?:s|ning)?|won|"
    r"lose(?:s|lost)?|beat(?:s|en)?|"
    r"defeat(?:s|ed)?|qualif(?:y|ies|ied)|"
    r"advance(?:s|d)?|eliminat(?:e|es|ed)|"
    r"score(?:s|d)?|results?)\b",

    r"\b(?:approv(?:e|es|ed)|"
    r"reject(?:s|ed)?|ban(?:s|ned)?|"
    r"arrest(?:s|ed)?|charg(?:e|es|ed)|"
    r"sue(?:s|d)?|investigat(?:e|es|ed)|"
    r"plead(?:s|ed)?|guilty|verdict|"
    r"ruling|court)\b",

    r"\b(?:resign(?:s|ed)?|appoint(?:s|ed)?|"
    r"nam(?:e|es|ed)|sign(?:s|ed)?|"
    r"join(?:s|ed)?|leave(?:s|left)?|"
    r"return(?:s|ed)?|cancel(?:s|led|ed)?|"
    r"delay(?:s|ed)?|suspend(?:s|ed)?)\b",

    r"\b(?:rise(?:s|rose)?|fall(?:s|fell)?|"
    r"drop(?:s|ped)?|surge(?:s|d)?|"
    r"gain(?:s|ed)?|cut(?:s)?|"
    r"rais(?:e|es|ed)|expand(?:s|ed)?|"
    r"clos(?:e|es|ed)|open(?:s|ed)?|"
    r"acquir(?:e|es|ed)|merg(?:e|es|ed)|"
    r"invest(?:s|ed)?|secur(?:e|es|ed)|"
    r"agree(?:s|d)?|deal|talks)\b",

    r"\b(?:begin(?:s|began)?|start(?:s|ed)?|"
    r"end(?:s|ed)?|halt(?:s|ed)?|"
    r"resume(?:s|d)?|postpon(?:e|es|ed)|"
    r"move(?:s|d)?|chang(?:e|es|ed)|"
    r"make(?:s|made)|go(?:es|went)|"
    r"becom(?:e|es|became))\b",

    r"\b(?:die(?:s|d)?|death|"
    r"injur(?:y|ies|ed)|hospitali[sz]ed|"
    r"diagnos(?:is|ed)|outbreak|recall|"
    r"layoffs?|strike|protest|attack|"
    r"crash|fire|flood|earthquake|storm|"
    r"war|ceasefire|sanctions?)\b",

    r"\b(?:election|primary|vote|voting|polls?|"
    r"policy|law|bill|regulation|budget|"
    r"inflation|market|shares?|stocks?|"
    r"economy|economic|sponsorship|"
    r"partnership|contract)\b",

    r"\b(?:today|tonight|this week|latest|"
    r"breaking|just|now|currently|202[0-9])\b",

    # Hindi.
    r"(?:घोषणा|ऐलान|पुष्टि|कहा|चेतावनी|"
    r"रिपोर्ट|खुलासा|लॉन्च|पेश|शुरू|"
    r"जीता|हारा|हराया|नतीजे|परिणाम)",

    r"(?:मंजूर|खारिज|प्रतिबंध|गिरफ्तार|"
    r"आरोप|जांच|इस्तीफा|नियुक्त|"
    r"हस्ताक्षर|समझौता|बातचीत)",

    r"(?:बढ़ा|गिरा|घटा|उछला|बंद|खुला|"
    r"निवेश|अधिग्रहण|विलय|वापसी|"
    r"रद्द|स्थगित)",

    r"(?:मौत|घायल|निदान|फैसला|अदालत|"
    r"चुनाव|मतदान|नीति|कानून|बजट|"
    r"महंगाई|बाजार|हड़ताल|विरोध|हमला|"
    r"दुर्घटना|आग|बाढ़|भूकंप|तूफान|"
    r"प्रकोप|आज|अभी|ताज़ा|ताजा|202[0-9])",

    # German, folded.
    r"\b(?:kundigt an|bestatigt|sagt|warnt|"
    r"berichtet|enthullt|veroffentlicht|"
    r"startet|stellt vor|prasentiert|"
    r"gewinnt|verliert|schlagt|ergebnisse?|"
    r"genehmigt|lehnt ab|verbietet|"
    r"verhaftet|untersucht|tritt zuruck|"
    r"ernennt|unterzeichnet|einigt sich|"
    r"steigt|fallt|sinkt|wachst|schliesst|"
    r"eroffnet|ubernimmt|investiert|"
    r"stirbt|verletzt|diagnose|urteil|wahl|"
    r"gesetz|inflation|streik|angriff|"
    r"unfall|heute|aktuell|202[0-9])\b",

    # French, folded.
    r"\b(?:annonce|confirme|declare|avertit|"
    r"rapporte|revele|devoile|lance|presente|"
    r"gagne|perd|bat|resultats?|approuve|"
    r"rejette|interdit|arrete|enquete|"
    r"demissionne|nomme|signe|augmente|"
    r"baisse|chute|ferme|ouvre|investit|"
    r"meurt|blesse|diagnostic|verdict|"
    r"election|loi|inflation|greve|attaque|"
    r"accident|aujourd hui|actuellement|"
    r"202[0-9])\b",

    # Spanish, folded.
    r"\b(?:anuncia|confirma|dice|advierte|"
    r"informa|revela|presenta|lanza|gana|"
    r"pierde|vence|resultados?|aprueba|"
    r"rechaza|prohibe|arresta|investiga|"
    r"dimite|nombra|firma|sube|baja|cae|"
    r"cierra|abre|adquiere|invierte|muere|"
    r"herido|diagnostico|veredicto|eleccion|"
    r"ley|inflacion|huelga|ataque|accidente|"
    r"hoy|actualmente|202[0-9])\b",
)


TOPIC_ALIAS_GROUPS = (
    (
        "artificial intelligence",
        "ai",
        "openai",
        "machine learning",
        "kunstliche intelligenz",
        "intelligence artificielle",
        "inteligencia artificial",
        "कृत्रिम बुद्धिमत्ता",
        "एआई",
    ),
    (
        "electric vehicle",
        "electric vehicles",
        "ev",
        "evs",
        "e mobility",
        "electromobility",
        "elektroauto",
        "vehicule electrique",
        "vehiculo electrico",
        "इलेक्ट्रिक वाहन",
    ),
    (
        "formula 1",
        "formula one",
        "f1",
        "formel 1",
        "formule 1",
        "formula uno",
    ),
    (
        "football",
        "soccer",
        "fussball",
        "futbol",
        "फुटबॉल",
    ),
    (
        "cricket",
        "kricket",
        "criquet",
        "क्रिकेट",
    ),
    (
        "climate change",
        "global warming",
        "klimawandel",
        "changement climatique",
        "cambio climatico",
        "जलवायु परिवर्तन",
    ),
)


STOPWORDS = {
    "a", "an", "and", "about", "around", "at",
    "for", "from", "in", "of", "on", "the",
    "to", "with", "latest", "news", "current",
    "recent", "update", "updates", "development",
    "developments", "today", "right", "now",

    "के", "की", "का", "में", "पर", "से", "और",
    "बारे", "खबर", "खबरें", "ताज़ा", "ताजा", "अभी",

    "der", "die", "das", "den", "dem", "des",
    "ein", "eine", "und", "uber", "zu", "von",
    "mit", "im", "am", "bei", "nachrichten",
    "aktuell",

    "de", "du", "la", "le", "les", "un", "une",
    "et", "sur", "avec", "dans", "actualites",
    "nouvelles",

    "el", "los", "las", "una", "y", "sobre",
    "con", "en", "noticias", "actualizacion",
}


def fold(
    value: object,
) -> str:
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


def words(
    value: object,
) -> set[str]:
    return set(
        re.findall(
            r"[^\W_]+",
            fold(value),
            flags=re.UNICODE,
        )
    )


def matches(
    value: object,
    patterns: tuple[str, ...],
) -> bool:
    text = fold(value)

    return any(
        re.search(
            pattern,
            text,
            flags=re.I | re.UNICODE,
        )
        for pattern in patterns
    )


def phrase_present(
    phrase: str,
    text: str,
) -> bool:
    return bool(
        re.search(
            r"(?<!\w)"
            + re.escape(phrase)
            + r"(?!\w)",
            text,
            flags=re.I | re.UNICODE,
        )
    )


def topic_aliases(
    topic: str,
) -> set[str]:
    target = fold(topic)

    aliases = (
        {target}
        if target
        else set()
    )

    for group in TOPIC_ALIAS_GROUPS:
        folded_group = {
            fold(item)
            for item in group
        }

        if any(
            target == alias
            or (
                len(alias) >= 4
                and alias in target
            )
            for alias in folded_group
        ):
            aliases.update(
                folded_group
            )

    return {
        item
        for item in aliases
        if item
    }


def topic_relevant(
    article: dict,
    topic: str,
) -> bool:
    target = fold(topic)

    if not target:
        return True

    combined = fold(
        " ".join(
            (
                str(
                    article.get("title")
                    or ""
                ),
                str(
                    article.get("description")
                    or ""
                ),
                str(
                    article.get("content")
                    or ""
                )[:600],
            )
        )
    )

    if any(
        phrase_present(
            alias,
            combined,
        )
        for alias in topic_aliases(
            topic
        )
    ):
        return True

    topic_words = [
        word
        for word in words(target)
        if (
            word not in STOPWORDS
            and len(word) >= 3
        )
    ]

    if not topic_words:
        return True

    combined_words = words(
        combined
    )

    matched = 0

    for token in topic_words:
        if token in combined_words:
            matched += 1
            continue

        if (
            len(token) >= 6
            and any(
                item.startswith(
                    token[:5]
                )
                for item in combined_words
                if len(item) >= 5
            )
        ):
            matched += 1

    required = (
        1
        if len(topic_words) == 1
        else min(
            2,
            len(topic_words),
        )
    )

    return matched >= required


def homepage_url(
    value: object,
) -> bool:
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
        (
            parsed.path
            or "/"
        ).rstrip("/")
        or "/"
    ).casefold()

    return bool(
        path
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


def non_news_url(
    value: object,
) -> bool:
    raw = str(
        value or ""
    ).strip().casefold()

    if not raw:
        return False

    try:
        path = (
            "/"
            + (
                urlsplit(
                    raw
                ).path
                or ""
            ).strip(
                "/"
            ).casefold()
            + "/"
        )

    except Exception:
        path = raw

    return any(
        marker in path
        for marker
        in NON_NEWS_URL_MARKERS
    )


def current_hits(
    article: dict,
) -> tuple[int, int]:
    title = fold(
        article.get("title")
        or ""
    )

    supporting = fold(
        " ".join(
            (
                str(
                    article.get("description")
                    or ""
                ),
                str(
                    article.get("content")
                    or ""
                )[:600],
            )
        )
    )

    title_hits = sum(
        bool(
            re.search(
                pattern,
                title,
                flags=re.I | re.UNICODE,
            )
        )
        for pattern
        in CURRENT_EVENT_PATTERNS
    )

    supporting_hits = sum(
        bool(
            re.search(
                pattern,
                supporting,
                flags=re.I | re.UNICODE,
            )
        )
        for pattern
        in CURRENT_EVENT_PATTERNS
    )

    return (
        title_hits,
        supporting_hits,
    )


def near_duplicate(
    first: str,
    second: str,
) -> bool:
    first_words = words(first)
    second_words = words(second)

    if (
        not first_words
        or not second_words
    ):
        return False

    if fold(first) == fold(second):
        return True

    shared = len(
        first_words
        & second_words
    )

    smaller = min(
        len(first_words),
        len(second_words),
    )

    larger = max(
        len(first_words),
        len(second_words),
    )

    union = len(
        first_words
        | second_words
    )

    expanded_same_story = bool(
        shared >= 5
        and (
            shared
            / smaller
        ) >= 0.78
        and (
            smaller
            / larger
        ) <= 0.78
    )

    almost_identical_story = bool(
        shared >= 6
        and (
            shared
            / union
        ) >= 0.82
    )

    return bool(
        expanded_same_story
        or almost_identical_story
    )


def rejection_reason(
    article: dict,
    topic: str,
) -> str:
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
        return "missing_title"

    if homepage_url(
        article.get("url")
    ):
        return "homepage"

    if non_news_url(
        article.get("url")
    ):
        return "non_news_url"

    if matches(
        title,
        NON_NEWS_PATTERNS,
    ):
        return "non_news_title"

    target = fold(
        topic
    )

    formula_one_topics = {
        "formula 1",
        "formula one",
        "f1",
        "formel 1",
        "formule 1",
        "formula uno",
    }

    # A Formula 1 title must visibly identify Formula 1.
    # This blocks Formula Sun, Formula E and similarly
    # named but unrelated events.
    if (
        target
        in formula_one_topics
        and not any(
            phrase_present(
                alias,
                fold(title),
            )
            for alias
            in formula_one_topics
        )
    ):
        return "topic_mismatch"

    sport_topics = {
        "football",
        "soccer",
        "cricket",
        "formula 1",
        "formula one",
        "f1",
        "fussball",
        "futbol",
        "kricket",
        "criquet",
        "फुटबॉल",
        "क्रिकेट",
    }

    politics_pattern = (
        r"(?:"
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
        r"चुनाव|उम्मीदवार|संसद|"
        r"\bwahl\b|"
        r"\bkandidat(?:in)?\b|"
        r"\bparlement\b|"
        r"\beleccion\b|"
        r"\bcandidato\b|"
        r"\bcongreso\b"
        r")"
    )

    if (
        target in sport_topics
        and re.search(
            politics_pattern,
            fold(title),
            flags=re.I | re.UNICODE,
        )
        and not any(
            phrase_present(
                alias,
                fold(title),
            )
            for alias
            in topic_aliases(
                topic
            )
        )
    ):
        return "cross_domain_politics"

    if (
        topic
        and not topic_relevant(
            article,
            topic,
        )
    ):
        return "topic_mismatch"

    (
        title_hits,
        supporting_hits,
    ) = current_hits(
        article
    )

    if (
        title_hits == 0
        and supporting_hits == 0
    ):
        return "no_current_event_signal"

    return ""


def quality_score(
    article: dict,
    topic: str,
    published: datetime,
    now: datetime,
) -> int:
    (
        title_hits,
        supporting_hits,
    ) = current_hits(
        article
    )

    score = (
        min(
            title_hits,
            3,
        )
        * 4
    )

    score += (
        min(
            supporting_hits,
            3,
        )
        * 2
    )

    if topic:
        title_only = {
            "title": (
                article.get("title")
                or ""
            ),
            "description": "",
            "content": "",
        }

        if topic_relevant(
            title_only,
            topic,
        ):
            score += 4

        else:
            score += 2

    age = (
        now
        - published
    )

    if age <= timedelta(
        days=1
    ):
        score += 3

    elif age <= timedelta(
        days=3
    ):
        score += 2

    else:
        score += 1

    return score


def parse_time(
    value: object,
) -> datetime | None:
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


def prepare_news_payload(
    payload: dict,
    count: int,
    *,
    topic: str = "",
    fresh_days: int = 7,
) -> dict:
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

    now = datetime.now(
        timezone.utc
    )

    cutoff = (
        now
        - timedelta(
            days=max(
                1,
                int(
                    fresh_days
                ),
            )
        )
    )

    accepted: list[
        tuple[
            int,
            datetime,
            dict,
        ]
    ] = []

    seen_titles: list[str] = []
    rejected: dict[str, int] = {}

    def reject(
        reason: str,
    ) -> None:
        rejected[reason] = (
            rejected.get(
                reason,
                0,
            )
            + 1
        )

    for article in articles:
        if not isinstance(
            article,
            dict,
        ):
            reject(
                "invalid_article"
            )
            continue

        reason = rejection_reason(
            article,
            topic,
        )

        if reason:
            reject(
                reason
            )
            continue

        published = parse_time(
            article.get(
                "publishedAt"
            )
        )

        if (
            published is None
            or published < cutoff
        ):
            reject(
                "stale_or_unverifiable"
            )
            continue

        title = str(
            article.get("title")
            or ""
        ).strip()

        if any(
            near_duplicate(
                title,
                existing_title,
            )
            for existing_title
            in seen_titles
        ):
            reject(
                "duplicate_story"
            )
            continue

        seen_titles.append(
            title
        )

        score = quality_score(
            article,
            topic,
            published,
            now,
        )

        accepted.append(
            (
                score,
                published,
                article,
            )
        )

    # Prefer the strongest current reporting first.
    # Publication time breaks ties.
    accepted.sort(
        key=lambda item: (
            item[0],
            item[1],
        ),
        reverse=True,
    )

    selected = [
        article
        for (
            _score,
            _published,
            article,
        )
        in accepted[
            :max(
                1,
                int(
                    count
                ),
            )
        ]
    ]

    result["articles"] = selected

    result["totalResults"] = len(
        selected
    )

    result["nova_freshness"] = {
        "days": fresh_days,
        "returned": len(
            selected
        ),
        "sorted": (
            "quality_then_"
            "publishedAt_descending"
        ),
    }

    # This metadata will make future diagnosis much easier.
    # Render logs or a direct relay response will show why
    # candidates were removed.
    result["nova_quality"] = {
        "topic": str(
            topic or ""
        ).strip(),
        "accepted": len(
            accepted
        ),
        "returned": len(
            selected
        ),
        "rejected": sum(
            rejected.values()
        ),
        "reasons": rejected,
    }

    return result