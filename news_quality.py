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

    # Numbered rankings, values and advice articles.
    # Numbers may appear as digits or words.
    r"\b(?:top|best)\s+"
    r"(?:\d+|one|two|three|four|five|six|"
    r"seven|eight|nine|ten)\b"
    r".{0,140}\b"
    r"(?:rankings?|values?|players?|picks?|"
    r"sleepers?|targets?|options?|projections?|"
    r"waiver|draft)\b",

    # German, French and Spanish equivalents.
    r"\b(?:top|besten?|meilleurs?|mejores?)\s+"
    r"(?:\d+|"
    r"eins|zwei|drei|vier|funf|sechs|"
    r"sieben|acht|neun|zehn|"
    r"un|deux|trois|quatre|cinq|six|"
    r"sept|huit|neuf|dix|"
    r"uno|dos|tres|cuatro|cinco|seis|"
    r"siete|ocho|nueve|diez)\b"
    r".{0,140}\b"
    r"(?:ranking|rangliste|classement|"
    r"valeurs?|valores?|spieler|joueurs?|"
    r"jugadores?|tipps?|conseils?|consejos?|"
    r"prognosen?|pronostics?|pronosticos?)\b",

    # Hindi equivalents.
    r"(?:टॉप|सर्वश्रेष्ठ)\s+"
    r"(?:\d+|एक|दो|तीन|चार|पाँच|पांच|"
    r"छह|सात|आठ|नौ|दस)"
    r".{0,120}"
    r"(?:रैंकिंग|खिलाड़ी|खिलाड़ियों|"
    r"वैल्यू|पिक्स|सूची|लिस्ट)",

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
    r"breaking|just|now|currently)\b",

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
    r"प्रकोप|आज|अभी|ताज़ा|ताजा)",

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
    r"unfall|heute|aktuell)\b",

    # French, folded.
    r"\b(?:annonce|confirme|declare|avertit|"
    r"rapporte|revele|devoile|lance|presente|"
    r"gagne|perd|bat|resultats?|approuve|"
    r"rejette|interdit|arrete|enquete|"
    r"demissionne|nomme|signe|augmente|"
    r"baisse|chute|ferme|ouvre|investit|"
    r"meurt|blesse|diagnostic|verdict|"
    r"election|loi|inflation|greve|attaque|"
    r"accident|aujourd hui|actuellement)\b",

    # Spanish, folded.
    r"\b(?:anuncia|confirma|dice|advierte|"
    r"informa|revela|presenta|lanza|gana|"
    r"pierde|vence|resultados?|aprueba|"
    r"rechaza|prohibe|arresta|investiga|"
    r"dimite|nombra|firma|sube|baja|cae|"
    r"cierra|abre|adquiere|invierte|muere|"
    r"herido|diagnostico|veredicto|eleccion|"
    r"ley|inflacion|huelga|ataque|accidente|"
    r"hoy|actualmente)\b",
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


SPORTS_SCOPE_ALIASES = {
    "sports",
    "sport",

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

    "खेल",
    "फुटबॉल",
    "क्रिकेट",
}


SPORTS_GAMING_PATTERNS = (
    # Fantasy-sports games and fantasy advice.
    r"\b(?:fantasy "
    r"(?:football|cricket|baseball|basketball|"
    r"hockey|sports?)|"
    r"daily fantasy|dfs|dream11)\b",

    r"\b(?:fantasy[- ]?"
    r"(?:fussball|football|sport)|"
    r"football fantasy|futbol fantasy|"
    r"fantasy futbol)\b",

    r"(?:फैंटेसी|फैंटसी|ड्रीम11|dream11)"
    r".{0,100}"
    r"(?:फुटबॉल|क्रिकेट|खेल|टीम|खिलाड़ी|"
    r"रैंकिंग|पिक्स|ड्राफ्ट)",

    # Betting and wagering advice.
    r"\b(?:best bets?|"
    r"betting (?:picks?|tips?|odds?)|"
    r"prop bets?|parlays?|moneyline|"
    r"point spread|spread picks?|"
    r"over[ /-]?under|sportsbook odds?|"
    r"wagering advice|bet builder)\b",

    r"\b(?:wetttipps?|wettquoten|sportwetten|"
    r"paris sportifs?|meilleurs paris|"
    r"apuestas deportivas?|"
    r"mejores apuestas|cuotas)\b",

    r"(?:सट्टा|बेटिंग|ऑड्स|odds)"
    r".{0,100}"
    r"(?:टिप्स|पिक्स|भविष्यवाणी|"
    r"दांव|बाज़ी|बाजी)",

    # Fantasy roster-management articles.
    r"\b(?:waiver wire|start[ /-]?sit|"
    r"mock draft|draft kit|draft guide|"
    r"fantasy rankings?|fantasy values?|"
    r"fantasy projections?|fantasy sleepers?|"
    r"fantasy picks?)\b",
)


SPORTS_UTILITY_PATTERNS = (
    # English: match-reference and statistics pages.
    r"\b(?:pitch|venue|ground|court|track|course)\s+report\b",

    r"\bweather\s+(?:report|forecast)\b"
    r".{0,120}\b"
    r"(?:match|game|race|tournament)\b",

    r"\b(?:head[ -]?to[ -]?head|h2h)\b",

    r"\b(?:average scores?|venue records?|"
    r"ground records?|stadium records?|"
    r"course records?)\b",

    r"\b(?:records?|statistics?|stats?)\b"
    r".{0,120}\b"
    r"(?:venue|ground|stadium|court|track|"
    r"course|match|game|race|ahead of)\b",

    r"\b(?:points table|league table|standings|"
    r"form guide|power rankings?)\b",

    r"\b(?:match|game|race|tournament)\s+preview\b",

    r"\b(?:predicted|probable|possible)\s+"
    r"(?:xi|11|lineup|team|squad)\b",

    r"\b(?:playing xi|starting xi|"
    r"predicted lineup|probable lineup)\b",

    r"\b(?:scorecard|live scores?|live updates?|"
    r"ball[ -]?by[ -]?ball|"
    r"play[ -]?by[ -]?play)\b",

    r"\b(?:key numbers?|numbers to know|"
    r"stat pack|fact file)\b",

    # Match, game and race timing-reference pages.
    # These tell readers when an event begins rather
    # than reporting something that happened.
    r"^\s*(?:what time|when is|when and where)\b"
    r".{0,180}\b"
    r"(?:match|game|race|series|tournament|"
    r"fixture|final)\b",

    r"\b(?:start time|start times|"
    r"match timing|match timings|"
    r"game time|game times|"
    r"race time|race times|"
    r"kick[ -]?off time|kick[ -]?off times|"
    r"tip[ -]?off time|tip[ -]?off times)\b"
    r".{0,180}\b"
    r"(?:including|for|in)\s+"
    r"(?:ist|gmt|utc|bst|cet|cest|"
    r"est|edt|cst|cdt|mst|mdt|"
    r"pst|pdt|aest|aedt)\b",

    r"\b(?:full|complete|all)\s+"
    r"(?:match|game|race|series|tournament|"
    r"fixture)?\s*"
    r"(?:timing|timings|schedule|"
    r"fixtures|calendar)\b",

    r"\b(?:match|game|race|series|tournament)\s+"
    r"(?:timing|timings)\b",

    r"\b(?:date|dates)\s*(?:,|and|&)\s*"
    r"(?:time|times|timing|timings)\b",

    r"\b(?:time ?zone|time ?zones|"
    r"local time|local times)\b",

    r"\b(?:ist|gmt|utc|bst|cet|cest|"
    r"est|edt|cst|cdt|mst|mdt|"
    r"pst|pdt|aest|aedt)\b"
    r".{0,160}\b"
    r"(?:start time|start times|"
    r"timing|timings|time ?zone|time ?zones)\b",

    # Hindi and Hinglish timing-reference pages.
    r"(?:मैच का समय|मैच की टाइमिंग|"
    r"मैच टाइमिंग|पूरी मैच टाइमिंग|"
    r"खेल का समय|रेस का समय|"
    r"शुरुआत का समय|तारीख और समय|"
    r"समय सारिणी|पूरा शेड्यूल|"
    r"टाइम ज़ोन|टाइम जोन|समय क्षेत्र)",

    r"\b(?:match|game|race|series)\s+"
    r"(?:ka|ki)\s+"
    r"(?:time|timing|samay)\b",

    r"\b(?:full|complete)\s+"
    r"(?:match|game|race|series)?\s*"
    r"(?:timing|timings|schedule)\b",

    # German. Text is accent-folded first.
    r"\b(?:startzeit|anstosszeit|"
    r"spielzeiten?|rennzeiten?|uhrzeit|"
    r"zeitzonen?|termine und uhrzeiten|"
    r"vollstandiger spielplan)\b",

    # French.
    r"\b(?:heure de debut|heures de debut|"
    r"horaires? des matchs?|"
    r"fuseaux horaires?|dates et heures|"
    r"calendrier complet)\b",

    # Spanish.
    r"\b(?:hora de inicio|horas de inicio|"
    r"horarios? de los partidos?|"
    r"zonas horarias?|fechas y horas|"
    r"calendario completo)\b",

    # Hindi and Hinglish.
    r"(?:पिच रिपोर्ट|मैदान रिपोर्ट|वेन्यू रिपोर्ट|"
    r"मौसम रिपोर्ट|हेड टू हेड|आमने सामने|"
    r"औसत स्कोर|मैदान के रिकॉर्ड|आंकड़े|"
    r"स्टैट्स|पॉइंट्स टेबल|अंक तालिका|"
    r"फॉर्म गाइड|मैच प्रीव्यू|"
    r"संभावित प्लेइंग इलेवन|संभावित टीम|"
    r"लाइव स्कोर|लाइव अपडेट|स्कोरकार्ड)",

    r"\b(?:pitch report|venue report|h2h|"
    r"head to head|average score|points table|"
    r"match preview|playing xi|live score|"
    r"scorecard)\b",

    # German. The text is accent-folded before matching.
    r"\b(?:platzbericht|stadionbericht|"
    r"wetterbericht|direktvergleich|"
    r"statistiken?|punktetabelle|tabelle|"
    r"formkurve|spielvorschau|"
    r"voraussichtliche aufstellung|"
    r"live ticker|live ergebnisse?)\b",

    # French.
    r"\b(?:rapport du terrain|rapport du stade|"
    r"meteo du match|face a face|statistiques?|"
    r"classement|forme recente|apercu du match|"
    r"composition probable|score en direct|"
    r"feuille de score)\b",

    # Spanish.
    r"\b(?:informe del campo|informe del estadio|"
    r"clima del partido|cara a cara|estadisticas?|"
    r"clasificacion|tabla de puntos|forma reciente|"
    r"previa del partido|alineacion probable|"
    r"marcador en vivo|tarjeta de puntuacion)\b",
)


SPORTS_TIMING_CHANGE_NEWS_PATTERNS = (
    # English: an authority actually changed,
    # delayed, announced or cancelled a time/date.
    r"\b(?:change|changes|changed|"
    r"move|moves|moved|"
    r"delay|delays|delayed|"
    r"postpone|postpones|postponed|"
    r"reschedule|reschedules|rescheduled|"
    r"announce|announces|announced|"
    r"confirm|confirms|confirmed|"
    r"cancel|cancels|cancelled)\b"
    r".{0,140}\b"
    r"(?:start time|kick[ -]?off|"
    r"schedule|fixture|date)\b",

    r"\b(?:start time|kick[ -]?off|"
    r"schedule|fixture|date)\b"
    r".{0,140}\b"
    r"(?:changed|moved|delayed|postponed|"
    r"rescheduled|announced|confirmed|"
    r"cancelled)\b",

    # Hindi.
    r"(?:बदला|बदली|बदले|स्थगित|टला|"
    r"घोषित|पुष्टि|रद्द)"
    r".{0,100}"
    r"(?:समय|टाइमिंग|शेड्यूल|तारीख)",

    # German.
    r"\b(?:andert|geandert|verschoben|"
    r"angekundigt|bestatigt|abgesagt)\b"
    r".{0,120}\b"
    r"(?:startzeit|anstosszeit|"
    r"spielplan|termin)\b",

    # French.
    r"\b(?:change|modifie|reporte|"
    r"annonce|confirme|annule)\b"
    r".{0,120}\b"
    r"(?:heure de debut|horaire|"
    r"calendrier|date)\b",

    # Spanish.
    r"\b(?:cambia|cambio|modifica|aplaza|"
    r"anuncia|confirma|cancela)\b"
    r".{0,120}\b"
    r"(?:hora de inicio|horario|"
    r"calendario|fecha)\b",
)


SPORTS_UTILITY_URL_MARKERS = (
    "/pitch-report/",
    "/venue-report/",
    "/ground-report/",
    "/match-preview/",
    "/game-preview/",
    "/race-preview/",
    "/head-to-head/",
    "/h2h/",
    "/statistics/",
    "/stats/",
    "/points-table/",
    "/standings/",
    "/scorecard/",
    "/live-score/",
    "/live-updates/",
    "/predicted-lineup/",
    "/probable-lineup/",
    "/playing-xi/",

    "/start-time/",
    "/match-time/",
    "/match-timings/",
    "/game-time/",
    "/race-time/",
    "/kickoff-time/",
    "/kick-off-time/",
    "/what-time/",
    "/time-zone/",
    "/time-zones/",
    "/schedule/",
    "/fixtures/",
    "/calendar/",
)


SPORT_FAMILY_PATTERNS = (
    (
        "cricket",
        (
            r"\b(?:cricket|icc|ipl|t20i?|odi|"
            r"test cricket|ashes)\b|क्रिकेट"
        ),
    ),
    (
        "football",
        (
            r"\b(?:football|soccer|fifa|uefa|"
            r"premier league|champions league|"
            r"la liga|serie a|bundesliga)\b|फुटबॉल"
        ),
    ),
    (
        "american_football",
        r"\b(?:nfl|super bowl|american football)\b",
    ),
    (
        "tennis",
        (
            r"\b(?:tennis|atp|wta|wimbledon|"
            r"roland garros|us open)\b|टेनिस"
        ),
    ),
    (
        "badminton",
        r"\b(?:badminton|bwf)\b|बैडमिंटन",
    ),
    (
        "basketball",
        r"\b(?:basketball|nba|wnba|euroleague)\b|बास्केटबॉल",
    ),
    (
        "hockey",
        r"\b(?:hockey|nhl|fih)\b|हॉकी",
    ),
    (
        "motorsport",
        (
            r"\b(?:formula 1|formula one|f1|motogp|"
            r"nascar|indycar|rally)\b"
        ),
    ),
    (
        "baseball",
        r"\b(?:baseball|mlb|world series)\b|बेसबॉल",
    ),
    (
        "rugby",
        r"\b(?:rugby|six nations)\b|रग्बी",
    ),
    (
        "golf",
        r"\b(?:golf|pga|lpga|ryder cup)\b|गोल्फ",
    ),
    (
        "combat",
        (
            r"\b(?:boxing|mma|ufc|wrestling)\b|"
            r"(?:मुक्केबाजी|कुश्ती)"
        ),
    ),
    (
        "athletics",
        (
            r"\b(?:athletics|track and field|"
            r"marathon|olympics?)\b|एथलेटिक्स"
        ),
    ),
)

PROMOTIONAL_CONTENT_PATTERNS = (
    # Branded campaigns, fan competitions and
    # commercial experiences.
    r"\b(?:presents?|presenta|presentan|"
    r"presente|prasentiert|launches?|"
    r"unveil(?:s|ed|ing)?|"
    r"debut(?:s|ed|ing)?|"
    r"lanza|lanzan|devoile|stellt vor)\b"
    r".{0,180}\b"
    r"(?:campaign|competition|contest|"
    r"collection|experience|fan event|"
    r"activation|giveaway|sweepstakes|"
    r"campana|concurso|coleccion|experiencia|"
    r"concours|kampagne|gewinnspiel|"
    r"kollektion|erlebnis)\b",

    r"\b(?:ultimate fan experience|"
    r"fans?['’] dreams?|"
    r"win a chance|enter to win)\b",

    r"(?:फैन प्रतियोगिता|प्रचार अभियान|"
    r"ब्रांड अभियान|इनाम जीतें|"
    r"जीतने का मौका)",
)


PRESS_RELEASE_SOURCES = {
    "pr newswire",
    "business wire",
    "globenewswire",
    "accesswire",
    "ein presswire",
    "prweb",
    "newsfile",
    "media outreach",
    "openpr",
}


# Static articles, guides, advice and reference pages that
# should not be presented as current News in any category.
GENERIC_UTILITY_PATTERNS = (
    # Explanatory/reference formats.
    r"\b(?:what|all)\s+you\s+need\s+to\s+know\b",
    r"\b(?:what we know so far|what to know|"
    r"faq|frequently asked questions)\b",

    # Buying advice and product features.
    r"\b(?:buying guide|buyers?'? guide|"
    r"best .{0,80} to buy|should you buy)\b",

    r"\b(?:hands[ -]?on|unboxing|first look)\b",

    r"^[^:|–—]{1,100}\breview\s*[:|–—-]",

    r"(?:^|[|:–—-]\s*)"
    r"(?:opinion|commentary|editorial|analysis)\b",

    r"\b(?:price|specifications?|specs?|features?|"
    r"release date|launch date|availability)\b"
    r".{0,120}\b"
    r"(?:price|specifications?|specs?|features?|"
    r"release date|launch date|availability)\b",

    # Sales and shopping pages.
    r"\b(?:prime day|black friday|cyber monday|"
    r"festival sale)\b"
    r".{0,100}\b"
    r"(?:deals?|discounts?|offers?|sale)\b",

    r"\b(?:best|top)\s+"
    r"(?:deals?|discounts?|offers?)\b",

    # Finance advice and reference tools.
    r"\b(?:stocks?|shares?)\s+to\s+buy\b",
    r"\b(?:buy|sell)\s+or\s+hold\b",

    r"\b(?:ipo\s+gmp|grey market premium|"
    r"dividend calendar|earnings calendar|"
    r"economic calendar|mutual fund calculator|"
    r"sip calculator|emi calculator|"
    r"loan calculator)\b",

    r"\b(?:price target|stock recommendations?|"
    r"trading tips?|investment picks?)\b",

    r"\b(?:gold|silver|petrol|diesel|fuel)\s+"
    r"prices?\s+today\b",

    # Health and lifestyle listicles.
    r"^\s*(?:\d+|one|two|three|four|five|six|"
    r"seven|eight|nine|ten)\s+"
    r"(?:foods?|habits?|exercises?|remedies|"
    r"signs?|symptoms?|ways?|tips?)\b",

    r"\b(?:doctor|expert|nutritionist|trainer)\s+"
    r"(?:reveals?|shares?)\s+"
    r"(?:\d+|one|two|three|four|five|six|"
    r"seven|eight|nine|ten)\s+"
    r"(?:foods?|tips?|habits?|ways?|remedies|"
    r"exercises?)\b",

    r"\b(?:symptoms?|causes?|treatment|prevention)\b"
    r".{0,120}\b"
    r"(?:symptoms?|causes?|treatment|prevention)\b",

    r"\b(?:horoscope|zodiac forecast|"
    r"recipe of the day|daily recipe|"
    r"meal plan|diet plan|workout plan)\b",

    # Entertainment reference pages.
    r"\b(?:ott|streaming)\s+release date\b",

    r"\b(?:release date|cast|plot|runtime)\b"
    r".{0,120}\b"
    r"(?:release date|cast|plot|runtime)\b",

    r"\b(?:trailer breakdown|ending explained|"
    r"episode guide|watch order)\b",

    r"\b(?:top|best)\s+"
    r"(?:\d+|one|two|three|four|five|six|"
    r"seven|eight|nine|ten)\s+"
    r"(?:movies?|films?|shows?|series|books?|"
    r"games?|songs?|albums?|restaurants?|"
    r"destinations?|places?)\b",

    r"\b(?:rumou?rs?|gossip)\s+"
    r"(?:roundup|round-up)\b",

    # Education and application utilities.
    r"\b(?:exam date|admit card|syllabus|"
    r"answer key|cut[ -]?off marks?|"
    r"result link|application form)\b",

    r"\b(?:admission|application|career|study|"
    r"visa)\s+guide\b",

    # Travel and lifestyle.
    r"\b(?:places to visit|travel itinerary|"
    r"visa checklist|packing list|home tour|"
    r"fashion trends?|recipe)\b",

    # Ticketing, static competition data and statistics.
    r"\b(?:how to buy tickets?|ticket prices?|"
    r"ticket guide|prize money|purse breakdown|"
    r"points distribution)\b",

    r"\b(?:tournament|competition|playoff)\s+"
    r"(?:format|rules|bracket|seedings?)\b",

    r"\b(?:groups?|draw|bracket|seedings?)\s+"
    r"(?:details|explained|list)\b",

    r"\b(?:career|player|team)\s+"
    r"(?:stats?|statistics|records?)\b",

    # Match timing and broadcast utilities, even without
    # explicit time-zone wording.
    r"\b(?:start time|match time|game time|race time|"
    r"kick[ -]?off time|tip[ -]?off time|"
    r"tv channel|broadcast details|"
    r"telecast details)\b",

    r"\b(?:match|game|race|series|tournament)\s+"
    r"(?:schedule|fixtures?|calendar|dates?)\b",

    r"\b(?:schedule|fixtures?|calendar)\b"
    r".{0,100}\b"
    r"(?:venues?|times?|dates?)\b",

    # Hindi and Hinglish.
    r"(?:रिव्यू|समीक्षा|खरीदने की गाइड|"
    r"क्या खरीदें|आईपीओ जीएमपी|"
    r"ग्रे मार्केट प्रीमियम|राशिफल|रेसिपी|"
    r"वीजा चेकलिस्ट|यात्रा कार्यक्रम|"
    r"पैकिंग लिस्ट)",

    r"(?:आज|अभी).{0,40}"
    r"(?:खरीदने|खरीदें).{0,50}"
    r"(?:शेयर|स्टॉक)",

    r"(?:शेयर|स्टॉक).{0,50}"
    r"(?:खरीदने|खरीदें)",

    r"(?:कीमत और (?:फीचर्स|स्पेसिफिकेशन)|"
    r"रिलीज डेट और कीमत|परीक्षा तिथि|"
    r"एडमिट कार्ड|सिलेबस|उत्तर कुंजी|"
    r"टिकट कैसे खरीदें|टिकट की कीमत|"
    r"पुरस्कार राशि|टूर्नामेंट प्रारूप|"
    r"मैच का समय|टीवी चैनल)",

    # German. Accents are folded before matching.
    r"\b(?:testbericht|kaufberatung|aktien kaufen|"
    r"dividendenkalender|horoskop|rezept|"
    r"reiseplan|packliste)\b",

    r"\b(?:preis und technische daten|"
    r"erscheinungsdatum und preis|"
    r"prufungstermin|eintrittspreise|preisgeld|"
    r"turnierformat|startzeit|tv sender)\b",

    # French.
    r"\b(?:guide d achat|actions a acheter|"
    r"calendrier des dividendes|horoscope|"
    r"recette|itineraire de voyage|"
    r"liste de voyage)\b",

    r"\b(?:prix et caracteristiques|"
    r"date de sortie et prix|"
    r"date d['’ ]?examen|"
    r"carte d['’ ]?admission|"
    r"prix des billets|dotation|"
    r"format du tournoi|heure de debut|"
    r"chaine tv)\b",

    # Spanish.
    r"\b(?:guia de compra|acciones para comprar|"
    r"calendario de dividendos|horoscopo|"
    r"receta|itinerario de viaje|"
    r"lista de equipaje)\b",

    r"\b(?:precio y especificaciones|"
    r"fecha de lanzamiento y precio|"
    r"fecha del examen|tarjeta de admision|"
    r"precio de las entradas|premio|"
    r"formato del torneo|hora de inicio|"
    r"canal de tv)\b",
)


# A reference subject remains valid News when an authority
# has actually announced, changed, delayed, cancelled,
# approved or revised it.
GENERIC_REFERENCE_CHANGE_NEWS_PATTERNS = (
    # English: action before reference.
    r"\b(?:announce|announces|announced|"
    r"confirm|confirms|confirmed|"
    r"change|changes|changed|"
    r"revise|revises|revised|"
    r"delay|delays|delayed|"
    r"postpone|postpones|postponed|"
    r"cancel|cancels|cancelled|"
    r"increase|increases|increased|"
    r"cut|cuts|reduce|reduces|reduced|"
    r"approve|approves|approved|"
    r"reject|rejects|rejected|"
    r"unveil|unveils|unveiled)\b"
    r".{0,160}\b"
    r"(?:price|release date|launch date|"
    r"availability|exam date|admit card|"
    r"syllabus|answer key|cut[ -]?off|ticket|"
    r"prize money|format|rules|schedule|"
    r"fixture|date|start time|kick[ -]?off|"
    r"broadcast)\b",

    # English: reference before action.
    r"\b(?:price|release date|launch date|"
    r"availability|exam date|admit card|"
    r"syllabus|answer key|cut[ -]?off|ticket|"
    r"prize money|format|rules|schedule|"
    r"fixture|date|start time|kick[ -]?off|"
    r"broadcast)\b"
    r".{0,160}\b"
    r"(?:announced|confirmed|changed|revised|"
    r"delayed|postponed|cancelled|increased|"
    r"cut|reduced|approved|rejected|unveiled)\b",

    # Hindi: both directions.
    r"(?:घोषित|घोषणा|पुष्टि|बदला|बदली|बदले|"
    r"संशोधित|स्थगित|रद्द|बढ़ाया|घटाया|मंजूर)"
    r".{0,120}"
    r"(?:कीमत|रिलीज डेट|परीक्षा तिथि|"
    r"एडमिट कार्ड|सिलेबस|टिकट|पुरस्कार राशि|"
    r"प्रारूप|नियम|शेड्यूल|समय)",

    r"(?:कीमत|रिलीज डेट|परीक्षा तिथि|"
    r"एडमिट कार्ड|सिलेबस|टिकट|पुरस्कार राशि|"
    r"प्रारूप|नियम|शेड्यूल|समय)"
    r".{0,120}"
    r"(?:घोषित|घोषणा|पुष्टि|बदला|बदली|बदले|"
    r"संशोधित|स्थगित|रद्द|बढ़ाया|घटाया|मंजूर)",

    # German: both directions.
    r"\b(?:angekundigt|bestatigt|geandert|"
    r"uberarbeitet|verschoben|abgesagt|"
    r"erhoht|gesenkt|genehmigt)\b"
    r".{0,140}\b"
    r"(?:preis|erscheinungsdatum|prufungstermin|"
    r"ticket|preisgeld|format|regeln|"
    r"spielplan|startzeit)\b",

    r"\b(?:preis|erscheinungsdatum|prufungstermin|"
    r"ticket|preisgeld|format|regeln|"
    r"spielplan|startzeit)\b"
    r".{0,140}\b"
    r"(?:angekundigt|bestatigt|geandert|"
    r"uberarbeitet|verschoben|abgesagt|"
    r"erhoht|gesenkt|genehmigt)\b",

    # French: both directions.
    r"\b(?:annonce|confirme|modifie|reporte|"
    r"annule|augmente|reduit|approuve)\b"
    r".{0,140}\b"
    r"(?:prix|date de sortie|date d['’ ]?examen|"
    r"billet|dotation|format|regles|"
    r"calendrier|heure de debut)\b",

    r"\b(?:prix|date de sortie|date d['’ ]?examen|"
    r"billet|dotation|format|regles|"
    r"calendrier|heure de debut)\b"
    r".{0,140}\b"
    r"(?:annonce|confirme|modifie|reporte|"
    r"annule|augmente|reduit|approuve)\b",

    # Spanish: both directions.
    r"\b(?:anuncia|confirma|cambia|modifica|"
    r"aplaza|cancela|aumenta|reduce|aprueba)\b"
    r".{0,140}\b"
    r"(?:precio|fecha de lanzamiento|"
    r"fecha del examen|entrada|premio|"
    r"formato|reglas|calendario|"
    r"hora de inicio)\b",

    r"\b(?:precio|fecha de lanzamiento|"
    r"fecha del examen|entrada|premio|"
    r"formato|reglas|calendario|"
    r"hora de inicio)\b"
    r".{0,140}\b"
    r"(?:anuncia|confirma|cambia|modifica|"
    r"aplaza|cancela|aumenta|reduce|aprueba)\b",
)


GENERIC_UTILITY_URL_MARKERS = (
    "/buying-guide/",
    "/buyers-guide/",
    "/deals/",
    "/horoscope/",
    "/recipe/",
    "/recipes/",
    "/admit-card/",
    "/syllabus/",
    "/answer-key/",
    "/ipo-gmp/",
    "/stocks-to-buy/",
    "/stock-recommendations/",
    "/exam-date/",
    "/ott-release/",
    "/ticket-guide/",
    "/prize-money/",
    "/tournament-format/",
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


def sports_scope(
    topic: str,
    category: str,
) -> bool:
    target_topic = fold(
        topic
    )

    target_category = fold(
        category
    )

    if (
        target_category
        in {
            "sports",
            "sport",
            "खेल",
        }
    ):
        return True

    aliases = topic_aliases(
        topic
    )

    return any(
        alias in SPORTS_SCOPE_ALIASES
        for alias in (
            aliases
            | {
                target_topic,
            }
        )
    )


def source_name(
    article: dict,
) -> str:
    source = article.get(
        "source"
    )

    if isinstance(
        source,
        dict,
    ):
        return fold(
            source.get("name")
            or ""
        )

    return fold(
        source
        or ""
    )


def sports_utility_url(
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
        in SPORTS_UTILITY_URL_MARKERS
    )


def sports_family(
    article: dict,
) -> str:
    combined = " ".join(
        (
            str(
                article.get("title")
                or ""
            ),
            str(
                article.get("description")
                or ""
            ),
        )
    )

    for family, pattern in (
        SPORT_FAMILY_PATTERNS
    ):
        if re.search(
            pattern,
            fold(combined),
            flags=re.I | re.UNICODE,
        ):
            return family

    return ""


def generic_utility_url(
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
        in GENERIC_UTILITY_URL_MARKERS
    )


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

    # One phrase can match more than one language
    # pattern. Count title and supporting evidence
    # once each instead of inflating the score.
    title_hits = int(
        any(
            re.search(
                pattern,
                title,
                flags=re.I | re.UNICODE,
            )
            for pattern
            in CURRENT_EVENT_PATTERNS
        )
    )

    supporting_hits = int(
        any(
            re.search(
                pattern,
                supporting,
                flags=re.I | re.UNICODE,
            )
            for pattern
            in CURRENT_EVENT_PATTERNS
        )
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

    # Some publishers change only a generic organization
    # word, such as "unit" versus "group".
    generic_variants = {
        "a",
        "an",
        "the",
        "its",
        "unit",
        "group",
        "division",
        "department",
        "arm",
        "business",
        "operation",
        "operations",
    }

    first_core = [
        token
        for token in re.findall(
            r"[^\W_]+",
            fold(first),
            flags=re.UNICODE,
        )
        if token not in generic_variants
    ]

    second_core = [
        token
        for token in re.findall(
            r"[^\W_]+",
            fold(second),
            flags=re.UNICODE,
        )
        if token not in generic_variants
    ]

    generic_variant_story = bool(
        len(first_core) >= 6
        and first_core == second_core
    )

    return bool(
        expanded_same_story
        or almost_identical_story
        or generic_variant_story
    )


def rejection_reason(
    article: dict,
    topic: str,
    category: str = "",
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

    combined_text = " ".join(
        (
            title,
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

    current_source = source_name(
        article
    )

    if any(
        marker in current_source
        for marker
        in PRESS_RELEASE_SOURCES
    ):
        return "press_release_source"

    if matches(
        combined_text,
        PROMOTIONAL_CONTENT_PATTERNS,
    ):
        return "promotional_content"

    if (
        sports_scope(
            topic,
            category,
        )
        and matches(
            combined_text,
            SPORTS_GAMING_PATTERNS,
        )
    ):
        return "sports_gaming_or_betting"

    is_sports_utility = bool(
        matches(
            combined_text,
            SPORTS_UTILITY_PATTERNS,
        )
        or sports_utility_url(
            article.get("url")
        )
    )

    is_real_timing_change = matches(
        title,
        SPORTS_TIMING_CHANGE_NEWS_PATTERNS,
    )

    is_real_reference_change = bool(
        is_real_timing_change
        or matches(
            title,
            GENERIC_REFERENCE_CHANGE_NEWS_PATTERNS,
        )
    )

    if (
        (
            matches(
                title,
                GENERIC_UTILITY_PATTERNS,
            )
            or generic_utility_url(
                article.get("url")
            )
        )
        and not is_real_reference_change
    ):
        return "generic_utility_or_advice"
    
    if (
        sports_scope(
            topic,
            category,
        )
        and is_sports_utility
        and not is_real_reference_change
    ):
        return "sports_utility_or_statistics"

    if homepage_url(
        article.get("url")
    ):
        return "homepage"

    if non_news_url(
        article.get("url")
    ):
        return "non_news_url"

    if (
        matches(
            title,
            NON_NEWS_PATTERNS,
        )
        and not is_real_reference_change
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
    category: str = "",
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
            category,
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

    limit = max(
        1,
        int(
            count
        ),
    )

    selected_rows: list[
        tuple[
            int,
            datetime,
            dict,
        ]
    ] = []

    # For a generic Sports request, prefer different
    # sports when qualifying reports are available.
    if (
        fold(category)
        in {
            "sports",
            "sport",
            "खेल",
        }
        and not str(
            topic or ""
        ).strip()
    ):
        seen_families: set[str] = set()

        deferred_rows: list[
            tuple[
                int,
                datetime,
                dict,
            ]
        ] = []

        for row in accepted:
            family = sports_family(
                row[2]
            )

            if (
                family
                and family not in seen_families
            ):
                selected_rows.append(
                    row
                )

                seen_families.add(
                    family
                )

            else:
                deferred_rows.append(
                    row
                )

            if len(
                selected_rows
            ) >= limit:
                break

        # Fill remaining positions by quality when there
        # are not enough distinct sports.
        if len(
            selected_rows
        ) < limit:
            for row in deferred_rows:
                selected_rows.append(
                    row
                )

                if len(
                    selected_rows
                ) >= limit:
                    break

    else:
        selected_rows = accepted[
            :limit
        ]

    selected = [
        article
        for (
            _score,
            _published,
            article,
        )
        in selected_rows
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