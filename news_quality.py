from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from urllib.parse import urlsplit

import re
import unicodedata


@lru_cache(
    maxsize=8192
)
def _compiled_regex(
    pattern: str,
):
    return re.compile(
        pattern,
        flags=re.I | re.UNICODE,
    )


# Conservative by design:
#
# A clean partial result is better than filling a News answer
# with explainers, guides, promotions or entertainment pieces.
NON_NEWS_PATTERNS = (
    # Question-style, interactive and quiz content.
    r"\?\s*$",

    # Teaser-led titles such as:
    #
    #   Green with envy? How...
    #   A major mistake? Why...
    #
    # are feature or explanatory articles rather than
    # direct reports of a current development.
    r"\?\s+(?:what|why|how|where|when|"
    r"who\s+(?:is|are|was|were|does|do|did|"
    r"can|could|should|will|would|has|have)|"
    r"क्या|क्यों|कैसे|कौन|कब|कहाँ|"
    r"was|warum|wie|wer|wann|wo|"
    r"quoi|pourquoi|comment|qui|quand|ou|"
    r"que|por que|como|quien|cuando|donde)\b",

    r"\b(?:quiz|trivia|can you name|who am i|"
    r"guess (?:the|this|which|who)|test your knowledge)\b",

    # English evergreen explanations, speculative questions
    # and retrospective analysis.
    #
    # A genuine current report should state the event:
    #
    #   England appoints Stephen Fleming as coach
    #
    # rather than analysing it:
    #
    #   Why England picked Stephen Fleming
    #   How England selected its new coach
    #   What the appointment means for England
    r"^\s*(?:what|why|how|where|when)\b",

    r"^\s*who\s+(?:is|are|was|were|does|do|did|"
    r"can|could|should|will|would|has|have)\b",

    r"^\s*(?:should (?:you|i|we)|will your)\b",

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

    # Hindi explanatory and question-led formats.
    r"^\s*(?:क्या|क्यों|कैसे|कौन|कब|कहाँ)",

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
    r"^\s*(?:was|warum|wie|wer|wann|wo)\b",

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
    r"quoi|pourquoi|comment|qui|quand|ou)\b",

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
    r"^\s*¿?\s*"
    r"(?:que|por que|como|quien|cuando|donde)\b",

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

EXPLANATORY_NEWS_FORMAT_PATTERNS = (
    # These formats are rejected even when the title also
    # contains a genuine cancellation, delay or announcement.

    # English.
    r"^\s*(?:what|why|how|where|when)\b",

    r"^\s*who\s+(?:is|are|was|were|does|do|did|"
    r"can|could|should|will|would|has|have)\b",

    # Auxiliary-led question articles:
    #
    # Can you really swing from spider silk?
    # Is ice cream really unhealthy?
    # Could this discovery change medicine?
    r"^\s*(?:can|could|should|would|"
    r"is|are|was|were|"
    r"do|does|did|will|"
    r"has|have)\b.{0,180}\?",

    r"\?\s+(?:what|why|how|where|when)\b",
    r"\?\s+who\s+(?:is|are|was|were|does|do|did|"
    r"can|could|should|will|would|has|have)\b",

    r"(?:^|[|:–—-]\s*)"
    r"(?:here(?:'|’)s why|here is why|"
    r"why it matters|what it means)\b",

    # Hindi and Hinglish.
    r"^\s*(?:क्या|क्यों|कैसे|कौन|कब|कहाँ)",

    r"(?:^|[|:–—-]\s*)"
    r"(?:जानिए क्यों|यह है वजह|इसलिए हुआ)",

    # German auxiliary-led questions.
    r"^\s*(?:kann|konnen|konnte|"
    r"ist|sind|war|waren|"
    r"soll|sollte|wird|werden|"
    r"hat|haben)\b.{0,180}\?",

    # German. Text is accent-folded before matching.
    r"^\s*(?:was|warum|wie|wer|wann|wo)\b",

    r"(?:^|[|:–—-]\s*)"
    r"(?:darum|deshalb|das ist der grund)\b",

    # French auxiliary-led questions.
    r"^\s*(?:peut|peuvent|pourrait|pourraient|"
    r"doit|devrait|est|sont)\b.{0,180}\?",

    # French.
    r"^\s*(?:qu(?:'|’)est ce que|quoi|"
    r"pourquoi|comment|qui|quand|ou)\b",

    r"(?:^|[|:–—-]\s*)"
    r"(?:voici pourquoi|ce que cela signifie)\b",


    # Spanish auxiliary-led questions.
    r"^\s*(?:puede|pueden|podria|podrian|"
    r"debe|deberia|es|son|esta|estan|"
    r"sera|seran)\b.{0,180}\?",

    # Spanish.
    r"^\s*¿?\s*"
    r"(?:que|por que|como|quien|cuando|donde)\b",

    r"(?:^|[|:–—-]\s*)"
    r"(?:esta es la razon|por esto|que significa)\b",
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

    r"\b(?:discover(?:s|ed|ing)?|"
    r"detect(?:s|ed|ing)?|"
    r"observ(?:e|es|ed|ing)|"
    r"identif(?:y|ies|ied|ying)|"
    r"land(?:s|ed|ing)?|"
    r"orbit(?:s|ed|ing)?|"
    r"test(?:s|ed|ing)?|"
    r"develop(?:s|ed|ing)?|"
    r"release(?:s|d|ing)?|"
    r"find(?:s|ing)?|found)\b",

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


TOPIC_EQUIVALENT_GROUPS = (
    (
        "artificial intelligence",
        "ai",
        "kunstliche intelligenz",
        "künstliche intelligenz",
        "intelligence artificielle",
        "inteligencia artificial",
        "कृत्रिम बुद्धिमत्ता",
        "एआई",
    ),

    (
        "electric vehicles",
        "electric vehicle",
        "ev",
        "evs",
        "e mobility",
        "electromobility",
        "elektrofahrzeug",
        "elektrofahrzeuge",
        "vehicule electrique",
        "vehicules electriques",
        "véhicule électrique",
        "véhicules électriques",
        "vehiculo electrico",
        "vehiculos electricos",
        "vehículo eléctrico",
        "vehículos eléctricos",
        "इलेक्ट्रिक वाहन",
    ),

    (
        "formula 1",
        "formula one",
        "f1",
        "formel 1",
        "formule 1",
        "formula uno",
        "फॉर्मूला 1",
    ),

    (
        "football",
        "soccer",
        "fussball",
        "fußball",
        "futbol",
        "fútbol",
        "फुटबॉल",
        "फुटबाल",
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
        "cambio climático",
        "जलवायु परिवर्तन",
    ),

    (
        "space",
        "outer space",
        "weltraum",
        "espace",
        "espacio",
        "अंतरिक्ष",
        "स्पेस",
    ),

    (
        "robotics",
        "robotik",
        "robotique",
        "robotica",
        "robótica",
        "रोबोटिक्स",
    ),
)


# These are related recall terms used only when the user
# requests the broad canonical subject.
#
# Therefore:
#
#   "space news"
#   may search NASA, rockets and satellites.
#
# But:
#
#   "NASA news"
#   remains specifically about NASA.
TOPIC_QUERY_EXPANSIONS = {
    "artificial intelligence": (
        "openai",
        "machine learning",
        "generative ai",
        "deep learning",
    ),

    "space": (
        "nasa",
        "rocket",
        "rockets",
        "satellite",
        "satellites",
        "spacecraft",
        "astronomy",
        "moon mission",
        "mars mission",
    ),

    "robotics": (
        "robot",
        "robots",
        "humanoid robot",
        "industrial robot",
    ),
}



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


SPORTS_VIDEO_GAME_PRODUCT_PATTERNS = (
    # Video-game releases, features, updates and product
    # coverage are not competitive sporting developments.
    #
    # This is generic and is not tied to any game title,
    # publisher, country or platform.
    r"\b(?:video games?|computer games?|console games?|"
    r"pc games?|mobile games?|roguelites?|roguelikes?|"
    r"gameplay|dlc|expansion packs?|patch notes?|"
    r"early access|remasters?|remastered|"
    r"spinoffs?|spin-offs?|sequels?|"
    r"game modes?|playable characters?|"
    r"game features?)\b",

    r"\b(?:playstation|xbox|nintendo|steam|"
    r"epic games store)\b"
    r".{0,120}\b"
    r"(?:game|release|launch|update|patch|"
    r"expansion|features?)\b",

    # Hindi and Hinglish.
    r"(?:वीडियो गेम|कंप्यूटर गेम|कंसोल गेम|"
    r"गेमप्ले|डीएलसी|गेम अपडेट|गेम विस्तार|"
    r"नया गेम मोड)",

    # German. Text is accent-folded before matching.
    r"\b(?:videospiel|computerspiel|konsolenspiel|"
    r"spielerweiterung|spielupdate|spielmodus|"
    r"neuauflage)\b",

    # French.
    r"\b(?:jeu video|jeu sur console|extension du jeu|"
    r"mise a jour du jeu|mode de jeu|remasterisation)\b",

    # Spanish.
    r"\b(?:videojuego|juego de consola|expansion del juego|"
    r"actualizacion del juego|modo de juego|remasterizacion)\b",
)


ESPORTS_COMPETITION_PATTERNS = (
    # Genuine competitive esports remain eligible.
    r"\b(?:esports?|e-sports?|competitive gaming)\b",
    r"(?:ईस्पोर्ट्स|ई-स्पोर्ट्स)",
    r"\b(?:esport|e-sport)\b",
)


SPORTS_REACTION_OR_PERSONALITY_PATTERNS = (
    # Fan reaction, comparisons and social-media chatter are
    # not the underlying sporting development.
    r"\b(?:fans?|supporters?|social media|internet)\b"
    r".{0,100}\b"
    r"(?:compare|compares|compared|react|reacts|reacted|"
    r"debate|mock|joke|believe|think)\b",

    # Celebrity-owner or personality reaction pieces.
    r"\b(?:reveals?|shares?)\s+how\s+"
    r"(?:he|she|they)\s+feels?\b",

    # Relationship and attendance stories are personality
    # coverage, not developments in the requested sport.
    r"\b(?:girlfriend|boyfriend|wife|husband|partner|"
    r"fiance|fiancee)\b"
    r".{0,120}\b"
    r"(?:joins?|attends?|supports?|cheers?|watches?|"
    r"visits?|celebrates?)\b",

    r"\b(?:heartwarming|adorable|sweet)\b"
    r".{0,60}\b"
    r"(?:show|moment|support|gesture|reaction)\b",

    # Sensationalized pundit takes and quote-led commentary.
    r"\b(?:drops?|delivers?)\s+(?:a\s+)?"
    r"(?:truth bomb|brutal verdict|honest take)\b",

    # Sensationalized or unsupported pundit claims.
    r"\b(?:weird|bizarre|strange|bold|controversial)\s+claim\b",

    r"\bmakes?\s+(?:a\s+)?(?:weird|bizarre|strange|bold|"
    r"controversial)\s+claim\b",

    # Hindi and Hinglish equivalents.
    r"(?:प्रशंसक|फैंस).{0,100}"
    r"(?:तुलना|प्रतिक्रिया|मज़ाक|मजाक|मानते)",

    r"(?:गर्लफ्रेंड|बॉयफ्रेंड|पत्नी|पति|साथी)"
    r".{0,100}"
    r"(?:शामिल|समर्थन|देखने|हौसला|जश्न)",

    # German, French and Spanish equivalents.
    # Text is accent-folded before these expressions run.
    r"\b(?:fans?|anhanger)\b.{0,100}\b"
    r"(?:vergleichen|reagieren|spotten|glauben)\b",

    r"\b(?:fans?|supporters?)\b.{0,100}\b"
    r"(?:comparent|reagissent|se moquent|pensent)\b",

    r"\b(?:aficionados?|hinchas?)\b.{0,100}\b"
    r"(?:comparan|reaccionan|se burlan|creen)\b",
)


SPORTS_PERSONALITY_ATTENDANCE_PATTERNS = (
    # Celebrity, investor, owner and royal attendance stories
    # are not sporting developments.
    r"\b(?:celebrity|actor|singer|influencer|investor|"
    r"owner|co[ -]?owner|royal|king|queen|prince|princess|"
    r"family)\b"
    r".{0,140}\b"
    r"(?:attends?|attended|watches?|watched|visits?|visited|"
    r"cheers?|cheered|supports?|supported|in action)\b",

    # Hindi.
    r"(?:सेलिब्रिटी|निवेशक|मालिक|राजपरिवार|राजकुमार|"
    r"राजकुमारी|परिवार).{0,120}"
    r"(?:पहुंचे|पहुंची|देखा|देखी|शामिल|समर्थन)",

    # German, French and Spanish.
    r"\b(?:promi|investor|eigentumer|konig|konigin|"
    r"prinz|prinzessin|familie)\b.{0,120}\b"
    r"(?:besucht|sieht|schaut|unterstutzt)\b",

    r"\b(?:celebrite|investisseur|proprietaire|roi|reine|"
    r"prince|princesse|famille)\b.{0,120}\b"
    r"(?:assiste|regarde|visite|soutient)\b",

    r"\b(?:celebridad|inversor|propietario|rey|reina|"
    r"principe|princesa|familia)\b.{0,120}\b"
    r"(?:asiste|mira|visita|apoya)\b",
)


SPORTS_ANALYSIS_FEATURE_PATTERNS = (
    # Evaluative sports features rather than one direct event.
    r"\b(?:proves?|shows?|demonstrates?)\b"
    r".{0,120}\b"
    r"(?:the real deal|why|what it takes|a point)\b",

    r"\b(?:verdict|takeaways?|lessons?|"
    r"what we learned|winners? and losers?)\b",

    # Forecasts, projected selections and hypothetical outcomes.
    r"\b(?:predicting?|predictions?|projecting?|projections?|"
    r"forecasting?|forecast)\b"
    r".{0,160}\b"
    r"(?:roster|lineup|squad|selection|winner|champion|"
    r"outcome|season|tournament|world cup|qualification)\b",

    # Outlook pieces that discuss whether success may happen
    # someday instead of reporting a new result or decision.
    r"\b(?:distant dream|long shot|far from reality|"
    r"years? away|still a dream|road to qualification)\b",

    # Retrospective memory and regret pieces about old events.
    r"\b(?:recalls?|remembers?|reminisces?|reflects? on|"
    r"looks? back on|revisits?)\b"
    r".{0,180}\b"
    r"(?:regret|memory|final|match|tournament|world cup|"
    r"olympics?|19\d{2}|20\d{2})\b",

    # Rhetorical sports-versus-market commentary. A direct
    # valuation report such as "league value rises" does not
    # match this contrast structure.
    r"\b(?:wins?|won|loses?|lost)\b"
    r".{0,100}\b(?:and|but)\b"
    r".{0,100}\b(?:wins?|won|loses?|lost)\b"
    r".{0,80}\b(?:market|investors?|shares?|stocks?|"
    r"sales|profit|valuation)\b",

    # Speculative career-crisis, rumour and hypothetical pieces.
    r"\b(?:could|may|might)\s+face\s+(?:a\s+)?"
    r"(?:career\s+)?(?:crisis|threat|uncertainty|end)\b",

    r"\b(?:rumou?red|speculated|hypothetical)\b"
    r".{0,140}\b(?:reunion|return|move|transfer|deal)\b",

    # Workload histories and old rule retrospectives.
    r"^\s*managing\b.{0,140}:",

    r"\bevery\b.{0,140}\b"
    r"(?:series|matches?|games?|tournaments?)\s+missed\b",

    r"\b(?:rewrote|changed)\s+(?:the\s+)?rules\b",

    # Hindi and Hinglish equivalents.
    r"(?:भविष्यवाणी|अनुमान|संभावित टीम|दूर का सपना|"
    r"याद किया|याद करते|पछतावा)",

    # German, French and Spanish. Text is accent-folded
    # before matching.
    r"\b(?:prognose|vorhersage|kaderprognose|"
    r"voraussichtlicher kader|ruckblick|erinnert sich|"
    r"ferner traum)\b",

    r"\b(?:prediction|pronostic|projection|"
    r"composition probable|se souvient|revient sur|"
    r"reve lointain)\b",

    r"\b(?:prediccion|pronostico|proyeccion|"
    r"plantilla prevista|recuerda|repasa|sueno lejano)\b",

    r"\b(?:gewinnt|gagne|gana)\b.{0,100}\b"
    r"(?:verliert|perd|pierde)\b.{0,80}\b"
    r"(?:markt|marche|mercado)\b",
)




SPORTS_QUOTE_COMMENTARY_PATTERNS = (
    # Opinion-led player and coach quotes are not the
    # underlying sporting development.
    r"\b(?:warns?|believes?|insists?|urges?|backs?|tips?|"
    r"predicts?|expects?)\b"
    r".{0,140}\b"
    r"(?:must improve|need(?:s)? to improve|should improve|"
    r"can win|will win|to win|title challenge|"
    r"favourites?|favorites?)\b",
)


SPORTS_NONCOMPETITIVE_LEGAL_PATTERNS = (
    # Personal criminal, harassment and misconduct proceedings
    # are legal news about a sports figure, not a sporting result.
    r"\b(?:court|judge|jury|police|prosecutors?|trial|lawsuit|"
    r"charges?|charged|acquits?|acquitted|convicts?|convicted|"
    r"arrests?|arrested)\b.{0,180}\b"
    r"(?:harassment|assault|abuse|fraud|corruption|crime|"
    r"criminal|misconduct)\b",

    r"\b(?:harassment|assault|abuse|fraud|corruption|crime|"
    r"criminal|misconduct)\b.{0,180}\b"
    r"(?:court|judge|jury|police|trial|charges?|charged|"
    r"acquits?|acquitted|convicts?|convicted|arrests?|arrested)\b",
)


SPORTS_COMPETITIVE_SUBJECT_PATTERNS = (
    # Strong competitive-sport anchors. Avoid vague words such
    # as "star", "team", "season", "record" and singular
    # "heat", which also occur in entertainment and disaster
    # reporting.
    r"\b(?:athletes?|players?|coaches?|managers?|captains?|squads?|"
    r"national teams?|sports federations?|tournaments?|championships?|"
    r"leagues?|cups?|matches?|medals?|podiums?|semi[ -]?finals?|"
    r"qualifiers?|friendlies|transfers?|signings?|loans?|"
    r"goalkeepers?|strikers?|defenders?|midfielders?|bowlers?|batters?|"
    r"judokas?|boxers?|wrestlers?|swimmers?|cyclists?|runners?|gymnasts?|"
    r"shooters?|golfers?|skaters?|racers?|drivers?|riders?|climbers?)\b",

    # Scoring and competition structures. "Heat" is accepted
    # only in an unmistakably competitive form, so "heat stroke"
    # cannot become athletics news.
    r"\b(?:goals?|wickets?|home runs?|homers?|touchdowns?|tries|bouts?|"
    r"(?:qualifying|semifinal|final)\s+heats?|heats\b|relays?|laps?|"
    r"pole position|grand prix)\b",

    # Common sport names improve recall, but generic competition
    # anchors above mean this is not a whitelist.
    r"\b(?:football|soccer|cricket|tennis|badminton|basketball|hockey|"
    r"baseball|rugby|golf|athletics|judo|boxing|wrestling|swimming|"
    r"cycling|gymnastics|archery|shooting|weightlifting|rowing|fencing|"
    r"squash|volleyball|handball|kabaddi|bowls|skating|skiing|sumo|"
    r"table tennis|motorsport|formula 1|formula one|f1|motogp|"
    r"horse racing|equestrian|climbing)\b",

    # Hindi.
    r"(?:खेल|खिलाड़ी|टीम|क्लब|कोच|कप्तान|लीग|"
    r"टूर्नामेंट|चैंपियनशिप|कप|मैच|रेस|पदक|"
    r"फाइनल|सेमीफाइनल|ट्रांसफर|गोलकीपर|"
    r"गेंदबाज|बल्लेबाज|मुक्केबाजी|कुश्ती)",

    # German.
    r"\b(?:sport|spieler|mannschaft|verein|trainer|liga|"
    r"turnier|meisterschaft|pokal|spiel|rennen|medaille|"
    r"finale|transfer|torhuter)\b",

    # French.
    r"\b(?:sport|joueur|equipe|club|entraineur|ligue|"
    r"tournoi|championnat|coupe|match|course|medaille|"
    r"finale|transfert|gardien)\b",

    # Spanish.
    r"\b(?:deporte|jugador|equipo|club|entrenador|liga|"
    r"torneo|campeonato|copa|partido|carrera|medalla|"
    r"final|fichaje|portero)\b",
)


SPORTS_COMPETITIVE_DEVELOPMENT_PATTERNS = (
    # Generic time-bound sporting developments. These are
    # event/action forms, not a list of sports.
    r"\b(?:wins?|won|victory|loses?|lost|loss|"
    r"beat(?:s|en)?|battle(?:s|d)?|"
    r"defeat(?:s|ed)?|draws?|scores?|"
    r"hits?|homers?|claims?|clinches?|captures?|takes?|"
    r"edges?|upsets?|qualif(?:y|ies|ied)|advances?|"
    r"progresses?|reaches?|eliminat(?:e|es|ed)|"
    r"gold|silver|bronze|medals?|podium|record|title|"
    r"champion|clean sweep|signs?|signed|signing|"
    r"bids?|offers?|interest|approach|target|"
    r"joins?|joined|loan|appoint(?:s|ed)?|selected|"
    r"called up|named|launch(?:es|ed)?|begins?|starts?|"
    r"debuts?|cancel(?:s|led|ed)?|postpon(?:e|es|ed)|"
    r"injur(?:y|ies|ed)|ruled out|withdraws?|"
    r"suspend(?:s|ed)?|ban(?:s|ned)?|"
    r"retir(?:e|es|ed|ement)|returns?|comeback|"
    r"set for|near(?:s|ed)?|"
    r"clos(?:e|es|ed) in on|"
    r"soar(?:s|ed)?|rise(?:s|rose)?|"
    r"increase(?:s|d)?|top(?:s|ped)?|"
    r"surpass(?:es|ed)?|"
    r"secures?|breaks?|retains?|defends?|"
    r"agrees? (?:a )?(?:deal|contract)|"
    r"extends? (?:his |her |their |the )?contract|"
    r"traded|drafted|dies?|death)\b",

    # Hindi.
    r"(?:जीता|जीती|जीते|हारा|हारी|हराया|स्कोर|"
    r"क्वालीफाई|पदक|स्वर्ण|रजत|कांस्य|रिकॉर्ड|"
    r"चैंपियन|हस्ताक्षर|शामिल|नियुक्त|नामित|"
    r"शुरू|लॉन्च|रद्द|स्थगित|घायल|प्रतिबंध|"
    r"संन्यास|वापसी)",

    # German.
    r"\b(?:gewinnt|gewann|verliert|verlor|schlagt|"
    r"qualifiziert|medaille|gold|silber|bronze|rekord|"
    r"meister|verpflichtet|wechselt|ernennt|startet|"
    r"abgesagt|verschoben|verletzt|gesperrt|kehrt zuruck)\b",

    # French.
    r"\b(?:gagne|remporte|perd|bat|qualifie|"
    r"medaille d or|medaille d argent|medaille de bronze|"
    r"record|champion|signe|rejoint|nomme|debute|"
    r"annule|reporte|blesse|suspendu|revient)\b",

    # Spanish.
    r"\b(?:gana|vence|pierde|clasifica|medalla|oro|plata|"
    r"bronce|record|campeon|ficha|firma|se une|nombra|"
    r"comienza|cancela|aplaza|lesionado|suspendido|regresa)\b",
)


SPORTS_ENTERTAINMENT_RELEASE_PATTERNS = (
    # Entertainment personalities are not competitive
    # sporting developments.
    r"\b(?:frontman|singer|rapper|musician|recording artist|"
    r"band|actor|actress|comedian|dj)\b",

    # Music, film and entertainment releases are never a
    # competitive sporting development, even when an athlete
    # or club is mentioned in the title.
    r"\b(?:album|single|song|music video|soundtrack|concert|"
    r"tour dates?|comeback dates?|repackaged album|box office|"
    r"film|movie|episode)\b",

    r"(?:एल्बम|सिंगल|गाना|गीत|म्यूजिक वीडियो|फिल्म|कॉन्सर्ट)",

    r"\b(?:album|single|lied|musikvideo|konzert|film)\b",
    r"\b(?:album|single|chanson|clip|concert|film)\b",
    r"\b(?:album|sencillo|cancion|video musical|concierto|pelicula)\b",
)


SPORTS_EXTERNAL_INCIDENT_PATTERNS = (
    # Disasters and medical incidents are not sport merely
    # because they mention a sports centre or an athletic
    # "heat". They may qualify only when the title directly
    # reports an effect on a competition, match or athlete.
    r"\b(?:earthquake|quake|aftershock|heat stroke|"
    r"taking shelter|wildfire|flood|storm)\b",

    r"(?:भूकंप|झटका|लू लगना|हीट स्ट्रोक|शरण|जंगल की आग|बाढ़|तूफान)",

    r"\b(?:erdbeben|nachbeben|hitzschlag|waldbrand|uberschwemmung|sturm)\b",
    r"\b(?:seisme|tremblement de terre|coup de chaleur|incendie|inondation|tempete)\b",
    r"\b(?:terremoto|sismo|golpe de calor|incendio|inundacion|tormenta)\b",
)


SPORTS_EXTERNAL_IMPACT_PATTERNS = (
    r"\b(?:cancel(?:s|led|ed|lation)?|postpon(?:e|es|ed|ement)|"
    r"delay(?:s|ed)?|suspend(?:s|ed)?|relocat(?:e|es|ed)|"
    r"move(?:s|d)?|reschedul(?:e|es|ed))\b",
)


SPORTS_COMMERCIAL_PRODUCT_PATTERNS = (
    # Consumer-product stories must not enter Sports merely
    # because the product is described as sporty.
    r"\b(?:unveils?|launches?|introduces?|debut(?:s|ed)?)\b"
    r".{0,140}\b"
    r"(?:watch(?:es)?|smartwatch(?:es)?|shoe(?:s)?|sneakers?|"
    r"jerseys?|kits?|apparel|clothing|collection|gadget|device|"
    r"equipment|accessor(?:y|ies)|product|app|platform)\b",

    r"\b(?:watch(?:es)?|smartwatch(?:es)?|shoe(?:s)?|sneakers?|"
    r"jerseys?|kits?|apparel|clothing|gadget|device|product)\b"
    r".{0,140}\b"
    r"(?:bluetooth|battery|solar|straps?|specifications?|specs?|"
    r"features?|price|availability|available|sale)\b",

    # Hindi.
    r"(?:लॉन्च|पेश|अनावरण).{0,120}"
    r"(?:घड़ी|स्मार्टवॉच|जूते|जर्सी|किट|कपड़े|उत्पाद)",

    # German, French and Spanish.
    r"\b(?:stellt vor|bringt auf den markt|lance|devoile|"
    r"lanza|presenta)\b.{0,120}\b"
    r"(?:uhr|smartwatch|schuhe|trikot|montre|chaussures|"
    r"maillot|reloj|zapatillas|camiseta|producto)\b",
)


CATEGORY_RELEVANCE_PATTERNS = {
    "business": (
        r"\b(?:business|economy|economic|finance|financial|"
        r"markets?|trade|company|companies|corporate|investment|"
        r"investors?|stocks?|shares?|earnings|revenue|profit|"
        r"banking?|merger|acquisition|startup|ipo|inflation|gdp|"
        r"tax|sales|retail|layoffs?|employment)\b",

        r"(?:व्यापार|अर्थव्यवस्था|वित्त|बाज़ार|बाजार|कंपनी|"
        r"निवेश|शेयर|बैंक|मुनाफा|राजस्व|महंगाई)",

        r"\b(?:wirtschaft|unternehmen|finanzen|markt|handel|"
        r"investition|aktien|bank|gewinn|umsatz|inflation)\b",

        r"\b(?:economie|entreprise|finance|marche|commerce|"
        r"investissement|actions|banque|benefice|revenus|inflation)\b",

        r"\b(?:economia|empresa|finanzas|mercado|comercio|"
        r"inversion|acciones|banco|beneficio|ingresos|inflacion)\b",
    ),

    "technology": (
        r"\b(?:technology|tech|software|cybersecurity|cyberattack|"
        r"semiconductor|computing|computer|smartphone|"
        r"artificial intelligence|ai|chip|digital|internet|cloud|"
        r"data|robotics?|telecom|device|hardware|"
        r"operating system|app|platform)\b",

        r"(?:तकनीक|प्रौद्योगिकी|सॉफ्टवेयर|साइबर|कंप्यूटर|"
        r"स्मार्टफोन|कृत्रिम बुद्धिमत्ता|एआई|चिप|रोबोटिक्स)",

        r"\b(?:technologie|software|cybersicherheit|computer|"
        r"kunstliche intelligenz|chip|digital|robotik|"
        r"telekommunikation)\b",

        r"\b(?:technologie|logiciel|cybersecurite|ordinateur|"
        r"intelligence artificielle|puce|numerique|robotique|"
        r"telecom)\b",

        r"\b(?:tecnologia|software|ciberseguridad|computadora|"
        r"inteligencia artificial|chip|digital|robotica|"
        r"telecomunicaciones)\b",
    ),

    "science": (
        r"\b(?:science|scientists?|research|researchers?|study|"
        r"discovery|space|nasa|physics|biology|astronomy|climate|"
        r"fossil|species|telescope|spacecraft|moon|mars|asteroid|"
        r"experiment|genome|laboratory|lab|quantum)\b",

        r"(?:विज्ञान|वैज्ञानिक|शोध|अध्ययन|खोज|अंतरिक्ष|"
        r"भौतिकी|जीवविज्ञान|खगोल|जलवायु|चंद्रमा|मंगल)",

        r"\b(?:wissenschaft|forscher|forschung|studie|entdeckung|"
        r"weltraum|physik|biologie|astronomie|klima|"
        r"experiment|quantum)\b",

        r"\b(?:science|scientifique|recherche|etude|decouverte|"
        r"espace|physique|biologie|astronomie|climat|"
        r"experience|quantique)\b",

        r"\b(?:ciencia|cientifico|investigacion|estudio|"
        r"descubrimiento|espacio|fisica|biologia|astronomia|"
        r"clima|experimento|cuantico)\b",
    ),

    "health": (
        r"\b(?:health|medical|medicine|hospital|disease|vaccine|"
        r"healthcare|doctor|patient|treatment|drug|virus|cancer|"
        r"infection|outbreak|surgery|mental health|public health|"
        r"diagnos(?:is|ed)|therapy|clinical|"
        r"world health organization|fda)\b",

        r"(?:स्वास्थ्य|चिकित्सा|अस्पताल|बीमारी|टीका|डॉक्टर|"
        r"मरीज|इलाज|दवा|वायरस|कैंसर|संक्रमण|सर्जरी)",

        r"\b(?:gesundheit|medizin|krankenhaus|krankheit|"
        r"impfstoff|arzt|patient|behandlung|medikament|"
        r"virus|krebs|infektion)\b",

        r"\b(?:sante|medical|hopital|maladie|vaccin|medecin|"
        r"patient|traitement|medicament|virus|cancer|infection)\b",

        r"\b(?:salud|medico|hospital|enfermedad|vacuna|doctor|"
        r"paciente|tratamiento|medicamento|virus|cancer|"
        r"infeccion)\b",
    ),

    "entertainment": (
        r"\b(?:entertainment|film|movie|cinema|television|tv|"
        r"music|actor|actress|singer|album|song|series|director|"
        r"box office|streaming|netflix|bollywood|hollywood|"
        r"theatre|theater|concert|festival)\b",

        r"(?:मनोरंजन|फिल्म|सिनेमा|टेलीविजन|संगीत|अभिनेता|"
        r"अभिनेत्री|गायक|एल्बम|गीत|वेब सीरीज|कॉन्सर्ट)",

        r"\b(?:unterhaltung|film|kino|fernsehen|musik|"
        r"schauspieler|sanger|album|serie|regisseur|"
        r"streaming|konzert)\b",

        r"\b(?:divertissement|film|cinema|television|musique|"
        r"acteur|chanteur|album|serie|realisateur|"
        r"streaming|concert)\b",

        r"\b(?:entretenimiento|pelicula|cine|television|musica|"
        r"actor|cantante|album|serie|director|streaming|"
        r"concierto)\b",
    ),
}


HEALTH_SPORTS_AVAILABILITY_PATTERNS = (
    # A player's availability for a match, tour or season is
    # Sports news even when an injury or medical team is
    # mentioned in the description.
    r"\b(?:player|athlete|footballer|cricketer|"
    r"batter|bowler|speedster|striker|defender|"
    r"midfielder|goalkeeper|captain|international)\b"
    r".{0,180}\b"
    r"(?:(?:likely|set|expected)\s+to\s+miss|"
    r"to\s+miss|ruled\s+out|unavailable|sidelined|"
    r"fitness\s+doubt|"
    r"far\s+away\s+from\s+injury\s+return)\b",

    r"\b(?:(?:likely|set|expected)\s+to\s+miss|"
    r"to\s+miss|ruled\s+out|unavailable|sidelined|"
    r"fitness\s+doubt|"
    r"far\s+away\s+from\s+injury\s+return)\b"
    r".{0,180}\b"
    r"(?:match|test|series|tour|game|season|"
    r"tournament|squad|team)\b",

    # Hindi and Hinglish.
    r"(?:खिलाड़ी|क्रिकेटर|गेंदबाज|बल्लेबाज)"
    r".{0,140}"
    r"(?:चोट के कारण बाहर|सीरीज से बाहर|"
    r"मैच नहीं खेल|वापसी से दूर)",

    # German.
    r"\b(?:spieler|athlet|fussballer)\b"
    r".{0,140}\b"
    r"(?:fallt aus|verpasst|nicht verfugbar|"
    r"verletzt|ruckkehr noch weit entfernt)\b",

    # French.
    r"\b(?:joueur|athlete|footballeur)\b"
    r".{0,140}\b"
    r"(?:forfait|manquera|indisponible|blesse|"
    r"loin d un retour)\b",

    # Spanish.
    r"\b(?:jugador|atleta|futbolista)\b"
    r".{0,140}\b"
    r"(?:baja|se perdera|no estara disponible|"
    r"lesionado|lejos de regresar)\b",
)


ENTERTAINMENT_CORPORATE_FINANCE_PATTERNS = (
    # Corporate-finance, securities and regulatory reports
    # belong to Business even when the company operates in
    # film, television or music.
    r"\b(?:shareholders?|capital\s+raise|"
    r"fundrais(?:e|es|ing)|"
    r"securities\s+regulator|regulator|"
    r"stock\s+exchange|"
    r"bars?\s+(?:the\s+)?company\s+from\s+markets?|"
    r"shares?|stocks?|earnings|revenue|profit|losses?|"
    r"debt|bonds?|ipo|merger|acquisition)\b",

    # Hindi.
    r"(?:शेयरधारक|पूंजी जुटाने|बाजार नियामक|"
    r"शेयर बाजार|मुनाफा|राजस्व|विलय|अधिग्रहण)",

    # German.
    r"\b(?:aktionare|kapitalerhohung|borse|aktien|"
    r"regulierungsbehorde|umsatz|gewinn|fusion|ubernahme)\b",

    # French.
    r"\b(?:actionnaires|augmentation de capital|bourse|"
    r"actions|regulateur|chiffre d affaires|benefice|"
    r"fusion|acquisition)\b",

    # Spanish.
    r"\b(?:accionistas|ampliacion de capital|bolsa|"
    r"acciones|regulador|ingresos|beneficio|"
    r"fusion|adquisicion)\b",
)


ENTERTAINMENT_CREATIVE_PERFORMANCE_PATTERNS = (
    # Genuine performance reporting remains Entertainment.
    r"\bbox\s+office\b",

    r"\b(?:film|movie|album|song|series)\b"
    r".{0,100}\b"
    r"(?:gross(?:es|ed)?|earns?|sales|streams?|"
    r"views?|debut(?:s|ed)?)\b",

    r"\b(?:gross(?:es|ed)?|earns?|sales|streams?|"
    r"views?|debut(?:s|ed)?)\b"
    r".{0,100}\b"
    r"(?:film|movie|album|song|series)\b",
)


ENTERTAINMENT_PRIMARY_PATTERNS = (
    # Creative works, performers and production developments.
    # The bare word "entertainment" is intentionally excluded:
    # a company's legal name must not be enough.
    r"\b(?:film|movie|cinema|television|tv|series|show|"
    r"music|actor|actress|singer|album|song|director|cast|"
    r"trailer|premiere|box\s+office|streaming|netflix|"
    r"bollywood|hollywood|theatre|theater|concert|festival|"
    r"franchise|sequel)\b",

    # Studio/production announcement wording.
    r"\b(?:studio|pictures|production)\b"
    r".{0,120}\b"
    r"(?:presents?|announces?|unveils?|releases?|"
    r"casts?|acquires?)\b",

    r"\b(?:presents?|announces?|unveils?|releases?|casts?)\b"
    r".{0,120}\b"
    r"(?:film|movie|series|album|song|trailer|"
    r"production|franchise|sequel)\b",

    # Hindi.
    r"(?:फिल्म|सिनेमा|टेलीविजन|संगीत|अभिनेता|"
    r"अभिनेत्री|गायक|एल्बम|गीत|वेब सीरीज|"
    r"ट्रेलर|निर्देशक|कलाकार|कॉन्सर्ट)",

    # German.
    r"\b(?:film|kino|fernsehen|musik|schauspieler|"
    r"sanger|album|serie|regisseur|besetzung|"
    r"trailer|premiere|streaming|konzert)\b",

    # French.
    r"\b(?:film|cinema|television|musique|acteur|"
    r"chanteur|album|serie|realisateur|distribution|"
    r"bande annonce|premiere|streaming|concert)\b",

    # Spanish.
    r"\b(?:pelicula|cine|television|musica|actor|"
    r"cantante|album|serie|director|reparto|"
    r"trailer|estreno|streaming|concierto)\b",
)


def sports_development_relevant(
    article: dict,
    *,
    provider_category_verified: bool = False,
) -> bool:
    # Use only the headline and description. Long article
    # bodies often contain unrelated country or sport terms.
    title = str(
        article.get("title")
        or ""
    )

    description = str(
        article.get("description")
        or ""
    )

    title_has_subject = matches(
        title,
        SPORTS_COMPETITIVE_SUBJECT_PATTERNS,
    )

    description_has_subject = matches(
        description,
        SPORTS_COMPETITIVE_SUBJECT_PATTERNS,
    )

    title_has_development = matches(
        title,
        SPORTS_COMPETITIVE_DEVELOPMENT_PATTERNS,
    )

    description_has_development = matches(
        description,
        SPORTS_COMPETITIVE_DEVELOPMENT_PATTERNS,
    )

    # Entertainment remains rejected regardless of what
    # category a provider assigned.
    if matches(
        title,
        SPORTS_ENTERTAINMENT_RELEASE_PATTERNS,
    ):
        return False

    # A disaster or medical incident qualifies only when the
    # headline directly reports its effect on a sporting event.
    if matches(
        title,
        SPORTS_EXTERNAL_INCIDENT_PATTERNS,
    ):
        return bool(
            title_has_subject
            and matches(
                title,
                SPORTS_EXTERNAL_IMPACT_PATTERNS,
            )
        )

    # Top Headlines category=sports is provider-verified.
    #
    # Do not require the sport itself to appear in a manually
    # maintained vocabulary. Require only a genuine current
    # development. The existing product, opinion, utility,
    # promotional and country gates still run separately.
    if provider_category_verified:
        return bool(
            title_has_development
            or description_has_development
        )

    # Everything has no native category filter, so fallback
    # candidates must show both a sporting subject and a
    # genuine current development.
    return bool(
        (
            title_has_subject
            or description_has_subject
        )
        and (
            title_has_development
            or description_has_development
        )
    )


SPORTS_ROLLING_HUB_TITLE_PATTERNS = (
    # Rolling event centres, medal tables and bundled utility
    # pages are not individual current sporting developments.
    #
    # Keep this title-only so a genuine report is not rejected
    # merely because its description briefly mentions the
    # tournament's wider medal table or schedule.

    # English.
    r"\b(?:medal\s+(?:table|tally|standings)|"
    r"overall standings)\b",

    r"\b(?:live|rolling)\s+"
    r"(?:blog|coverage|tracker|updates?)\b",

    r"\b(?:final|opening|closing)\s+day\s+live\b",
    r"\bday\s+\d+\s+live\b",

    r"\blive\s*[:|–—-]\s*"
    r"(?:results?|scores?|"
    r"medal\s+(?:table|tally)|"
    r"schedule|fixtures?|highlights?)\b",

    # Titles bundling three or more reference utilities:
    #
    # Results, Medal Table, Schedule & Highlights
    # Scores, Fixtures and Standings
    r"\b(?:results?|scores?|"
    r"medal\s+(?:table|tally)|"
    r"schedule|fixtures?|highlights?)\b"
    r".{0,80}\b"
    r"(?:results?|scores?|"
    r"medal\s+(?:table|tally)|"
    r"schedule|fixtures?|highlights?)\b"
    r".{0,80}\b"
    r"(?:results?|scores?|"
    r"medal\s+(?:table|tally)|"
    r"schedule|fixtures?|highlights?)\b",

    # Rolling pages that mix one completed result with the
    # next fixture rather than reporting one development.
    r"\b(?:up next|next up|coming up)\b",

    # Hindi and Hinglish.
    r"(?:पदक तालिका|पदक सूची|"
    r"मेडल टेबल|मेडल टैली)",

    r"(?:लाइव|सीधा).{0,80}"
    r"(?:परिणाम|नतीजे|पदक तालिका|"
    r"मेडल टेबल|शेड्यूल|कार्यक्रम|"
    r"हाइलाइट्स)",

    # German. Text is accent-folded before matching.
    r"\b(?:medaillenspiegel|"
    r"medaillentabelle|medaillenstand)\b",

    r"\b(?:live|liveticker|live ticker)\b"
    r".{0,80}\b"
    r"(?:ergebnisse?|spielplan|highlights?)\b",

    # French. Text is accent-folded before matching.
    r"\b(?:tableau|classement)\s+"
    r"des\s+medailles\b",

    r"\ben direct\b.{0,80}\b"
    r"(?:resultats?|programme|calendrier|"
    r"temps forts)\b",

    # Spanish. Text is accent-folded before matching.
    r"\b(?:medallero|tabla de medallas)\b",

    r"\ben (?:vivo|directo)\b.{0,80}\b"
    r"(?:resultados?|calendario|horarios?|"
    r"destacados?)\b",
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
    "/medal-table/",
    "/medal-tally/",
    "/scorecard/",
    "/live-score/",
    "/live-updates/",
    "/live-blog/",
    "/live-coverage/",
    "/results-centre/",
    "/results-center/",
    "/highlights/",
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

    # Retail offers and shopping copy.
    r"\b(?:buy one|get one|get a free|"
    r"free gift|shop now|order now|"
    r"add to cart|use code|"
    r"limited[ -]?time offer|special offer|"
    r"free shipping|bundle deal)\b",

    r"\b(?:compre uno|obtenga gratis|"
    r"compre ahora|oferta por tiempo limitado|"
    r"livraison gratuite|achetez maintenant|"
    r"jetzt kaufen|kostenlos dazu)\b",

    r"(?:एक खरीदें|मुफ़्त पाएं|मुफ्त पाएं|"
    r"अभी खरीदें|सीमित समय का ऑफर|"
    r"फ्री शिपिंग)",

    # Luxury-property showcase features.
    r"^\s*this\s+[\$€£₹]?"
    r"[0-9][0-9.,]*\s*"
    r"(?:million|billion|crore|lakh)?\s*"
    r"(?:home|house|mansion|villa|"
    r"apartment|estate)\b",

    r"\b(?:inside|tour)\s+(?:a|the)\s+"
    r"[\$€£₹]?[0-9][0-9.,]*\s*"
    r"(?:million|billion|crore|lakh)?\s*"
    r"(?:home|house|mansion|villa|"
    r"apartment|estate)\b",
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

    # Rolling trackers and all-item performance pages are
    # utilities, not one current headline event.
    r"\b(?:tracking|track)\s+every\b",

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


# Country-scoped News must actually concern the requested
# country. A publisher's market or website location alone
# is not sufficient.
#
# Countries not listed below still use their canonical
# country name. The aliases provide common demonyms and
# alternative names for frequent NewsAPI markets.
COUNTRY_RELEVANCE_ALIASES = {
    "ae": (
        "United Arab Emirates",
        "UAE",
        "Emirati",
    ),
    "ar": (
        "Argentina",
        "Argentine",
        "Argentinian",
    ),
    "at": (
        "Austria",
        "Austrian",
    ),
    "au": (
        "Australia",
        "Australian",
    ),
    "be": (
        "Belgium",
        "Belgian",
    ),
    "bg": (
        "Bulgaria",
        "Bulgarian",
    ),
    "br": (
        "Brazil",
        "Brazilian",
    ),
    "bt": (
        "Bhutan",
        "Bhutanese",
    ),
    "ca": (
        "Canada",
        "Canadian",
    ),
    "ch": (
        "Switzerland",
        "Swiss",
    ),
    "cn": (
        "China",
        "Chinese",
    ),
    "co": (
        "Colombia",
        "Colombian",
    ),
    "cu": (
        "Cuba",
        "Cuban",
    ),
    "cz": (
        "Czechia",
        "Czech Republic",
        "Czech",
    ),
    "de": (
        "Germany",
        "German",
    ),
    "eg": (
        "Egypt",
        "Egyptian",
    ),
    "fr": (
        "France",
        "French",
    ),
    "gb": (
        "United Kingdom",
        "Britain",
        "British",
        "England",
        "English",
        "Scotland",
        "Scottish",
        "Wales",
        "Welsh",
        "Northern Ireland",
    ),
    "gr": (
        "Greece",
        "Greek",
    ),
    "gy": (
        "Guyana",
        "Guyanese",
    ),
    "hk": (
        "Hong Kong",
    ),
    "hu": (
        "Hungary",
        "Hungarian",
    ),
    "id": (
        "Indonesia",
        "Indonesian",
    ),
    "ie": (
        "Ireland",
        "Irish",
    ),
    "il": (
        "Israel",
        "Israeli",
    ),
    "in": (
        "India",
        "Indian",
        "Bharat",
    ),
    "it": (
        "Italy",
        "Italian",
    ),
    "jp": (
        "Japan",
        "Japanese",
    ),
    "lk": (
        "Sri Lanka",
        "Sri Lankan",
        "Lankan",
    ),
    "kr": (
        "South Korea",
        "Korean",
    ),
    "lt": (
        "Lithuania",
        "Lithuanian",
    ),
    "lv": (
        "Latvia",
        "Latvian",
    ),
    "ma": (
        "Morocco",
        "Moroccan",
    ),
    "mx": (
        "Mexico",
        "Mexican",
    ),
    "my": (
        "Malaysia",
        "Malaysian",
    ),
    "ng": (
        "Nigeria",
        "Nigerian",
    ),
    "nl": (
        "Netherlands",
        "Dutch",
    ),
    "no": (
        "Norway",
        "Norwegian",
    ),
    "nz": (
        "New Zealand",
        "New Zealander",
    ),
    "ph": (
        "Philippines",
        "Filipino",
        "Philippine",
    ),
    "pl": (
        "Poland",
        "Polish",
    ),
    "pt": (
        "Portugal",
        "Portuguese",
    ),
    "ro": (
        "Romania",
        "Romanian",
    ),
    "rs": (
        "Serbia",
        "Serbian",
    ),
    "ru": (
        "Russia",
        "Russian",
    ),
    "sa": (
        "Saudi Arabia",
        "Saudi",
    ),
    "se": (
        "Sweden",
        "Swedish",
    ),
    "sg": (
        "Singapore",
        "Singaporean",
    ),
    "si": (
        "Slovenia",
        "Slovenian",
    ),
    "sk": (
        "Slovakia",
        "Slovak",
    ),
    "th": (
        "Thailand",
        "Thai",
    ),
    "tr": (
        "Turkey",
        "Türkiye",
        "Turkish",
    ),
    "tw": (
        "Taiwan",
        "Taiwanese",
    ),
    "ua": (
        "Ukraine",
        "Ukrainian",
    ),
    "us": (
        "United States",
        "United States of America",
        "USA",
        "American",
    ),
    "ve": (
        "Venezuela",
        "Venezuelan",
    ),

    # West Indies is a multinational sporting region/team,
    # represented by Nova's News-only pseudo-code "wi".
    "wi": (
        "West Indies",
        "West Indian",
        "Windies",
        "Cricket West Indies",
        "CWI",
    ),

    "za": (
        "South Africa",
        "South African",
    ),
}

# Additional common country names, demonyms and sporting
# designations. These improve recall but do not control
# which countries Nova supports.
COUNTRY_RELEVANCE_ALIASES[
    "gb"
] += (
    "Great Britain",
    "Team GB",
)

COUNTRY_RELEVANCE_ALIASES[
    "tw"
] += (
    "Chinese Taipei",
)

COUNTRY_RELEVANCE_ALIASES[
    "hk"
] += (
    "Hong Kong, China",
)

COUNTRY_RELEVANCE_ALIASES[
    "ie"
] += (
    "Republic of Ireland",
)

COUNTRY_RELEVANCE_ALIASES.update(
    {
        "ba": (
            "Bosnia and Herzegovina",
            "Bosnian",
        ),

        "bn": (
            "Brunei",
            "Bruneian",
        ),

        "bo": (
            "Bolivia",
            "Bolivian",
        ),

        "cd": (
            "DR Congo",
            "Democratic Republic of the Congo",
            "Congo-Kinshasa",
        ),

        "cg": (
            "Republic of the Congo",
            "Congo-Brazzaville",
        ),

        "ci": (
            "Ivory Coast",
            "Côte d'Ivoire",
            "Ivorian",
        ),

        "cv": (
            "Cabo Verde",
            "Cape Verde",
            "Cape Verdean",
        ),

        "fm": (
            "Micronesia",
            "Micronesian",
        ),

        "ir": (
            "Iran",
            "Iranian",
        ),

        "kp": (
            "North Korea",
            "North Korean",
        ),

        "la": (
            "Laos",
            "Lao",
        ),

        "md": (
            "Moldova",
            "Moldovan",
        ),

        "mk": (
            "North Macedonia",
            "Macedonian",
        ),

        "mm": (
            "Myanmar",
            "Burma",
            "Burmese",
        ),

        "mo": (
            "Macao",
            "Macau",
            "Macanese",
        ),

        "ps": (
            "Palestine",
            "Palestinian",
        ),

        "sy": (
            "Syria",
            "Syrian",
        ),

        "sz": (
            "Eswatini",
            "Swaziland",
            "Swazi",
        ),

        "tl": (
            "Timor-Leste",
            "East Timor",
            "Timorese",
        ),

        "tz": (
            "Tanzania",
            "Tanzanian",
        ),

        "va": (
            "Vatican City",
            "Holy See",
        ),

        "vn": (
            "Vietnam",
            "Viet Nam",
            "Vietnamese",
        ),

        # Nova's News-only Kosovo scope.
        "xk": (
            "Kosovo",
            "Kosovan",
            "Kosovar",
        ),
    }
)

GB_HOME_NATION_ALIASES = {
    "england": (
        "England",
        "English",
    ),

    "scotland": (
        "Scotland",
        "Scottish",
    ),

    "wales": (
        "Wales",
        "Welsh",
    ),

    "northern ireland": (
        "Northern Ireland",
        "Northern Irish",
    ),
}


GB_HOME_NATION_SPORTS_QUERY_ALIASES = {
    # Compact geographical and domestic-sport clues used
    # inside NewsAPI's q expression.
    #
    # This is NOT a whitelist of allowed sports. Reports
    # about any sport can still qualify through the country
    # name or demonym: England/English, Scotland/Scottish,
    # Wales/Welsh or Northern Ireland/Northern Irish.
    "england": (
        "Team England",
        "Premier League",
        "EFL",
        "FA Cup",
        "County Championship",
        "Premiership Rugby",
    ),

    "scotland": (
        "Team Scotland",
        "Scottish Premiership",
        "SPFL",
        "Scottish Cup",
        "Scottish Rugby",
        "Cricket Scotland",
    ),

    "wales": (
        "Team Wales",
        "Cymru Premier",
        "Welsh Cup",
        "Sport Wales",
        "Welsh Rugby",
        "Hockey Wales",
    ),

    "northern ireland": (
        "Team Northern Ireland",
        "Team NI",
        "NIFL Premiership",
        "Sport Northern Ireland",
        "Athletics Northern Ireland",
        "Northern Cricket Union",
    ),
}


GB_HOME_NATION_SPORTS_RELEVANCE_ALIASES = {
    # Broader aliases used only after articles have been
    # downloaded. They improve recognition across many
    # domestic sports without making the provider query huge.
    "england": (
        *GB_HOME_NATION_SPORTS_QUERY_ALIASES["england"],
        "England team",
        "England squad",
        "England national team",
        "England international",
        "English sport",
        "English sports",
        "Sport England",
        "Women's Super League",
        "England Rugby",
        "England Athletics",
        "England Hockey",
        "England Netball",
        "Swim England",
        "England Boxing",
        "Badminton England",
        "Basketball England",
        "England Squash",
        "Table Tennis England",
        "England Golf",
        "English Gymnastics",
    ),

    "scotland": (
        *GB_HOME_NATION_SPORTS_QUERY_ALIASES["scotland"],
        "Scotland team",
        "Scotland squad",
        "Scotland national team",
        "Scotland international",
        "Scottish sport",
        "Scottish sports",
        "sportscotland",
        "SWPL",
        "Scottish Athletics",
        "Scottish Hockey",
        "Scottish Swimming",
        "Boxing Scotland",
        "Badminton Scotland",
        "Basketball Scotland",
        "Scottish Squash",
        "Table Tennis Scotland",
        "Scottish Golf",
        "Scottish Gymnastics",
        "Scottish Cycling",
    ),

    "wales": (
        *GB_HOME_NATION_SPORTS_QUERY_ALIASES["wales"],
        "Wales team",
        "Wales squad",
        "Wales national team",
        "Wales international",
        "Welsh sport",
        "Welsh sports",
        "Wales Netball",
        "Welsh Athletics",
        "Swim Wales",
        "Welsh Boxing",
        "Badminton Wales",
        "Basketball Wales",
        "Squash Wales",
        "Table Tennis Wales",
        "Wales Golf",
        "Welsh Gymnastics",
        "Welsh Cycling",
        "Cricket Wales",
    ),

    "northern ireland": (
        *GB_HOME_NATION_SPORTS_QUERY_ALIASES[
            "northern ireland"
        ],
        "Northern Ireland team",
        "Northern Ireland squad",
        "Northern Ireland national team",
        "Northern Ireland international",
        "Northern Irish sport",
        "Northern Irish sports",
        "Irish Premiership",
        "Ulster Rugby",
        "Swim Ulster",
        "Ulster Hockey",
        "Ulster Boxing",
        "Golf Ireland",
    ),
}



def _exact_gb_country_key(
    country_name: str,
) -> str:
    target = fold(
        country_name
    )

    aliases = {
        "england": {
            "england",
            "english",
            "angleterre",
            "inglaterra",
            "इंग्लैंड",
            "इंगलैंड",
        },

        "scotland": {
            "scotland",
            "scottish",
            "schottland",
            "ecosse",
            "écosse",
            "escocia",
            "स्कॉटलैंड",
        },

        "wales": {
            "wales",
            "welsh",
            "pays de galles",
            "gales",
            "वेल्स",
        },

        "northern ireland": {
            "northern ireland",
            "northern irish",
            "nordirland",
            "irlande du nord",
            "irlanda del norte",
            "उत्तरी आयरलैंड",
        },
    }

    for key, values in aliases.items():
        if target in {
            fold(value)
            for value in values
        }:
            return key

    return ""



def _country_sports_alias_values(
    country_code: str,
    country_name: str,
    *,
    for_query: bool = False,
) -> tuple[str, ...]:
    code = str(
        country_code or ""
    ).strip().casefold()

    if code != "gb":
        return ()

    exact_gb_key = _exact_gb_country_key(
        country_name
    )

    if not exact_gb_key:
        return ()

    source = (
        GB_HOME_NATION_SPORTS_QUERY_ALIASES
        if for_query
        else GB_HOME_NATION_SPORTS_RELEVANCE_ALIASES
    )

    return tuple(
        source.get(
            exact_gb_key,
            (),
        )
    )


def _country_alias_values(
    country_code: str,
    country_name: str,
) -> tuple[str, ...]:
    code = str(
        country_code or ""
    ).strip().casefold()

    name = str(
        country_name or ""
    ).strip()

    if name.casefold() == "world":
        return ()

    exact_gb_key = (
        _exact_gb_country_key(
            name
        )
        if code == "gb"
        else ""
    )

    if exact_gb_key:
        return (
            GB_HOME_NATION_ALIASES[
                exact_gb_key
            ]
        )

    values: list[str] = []

    if name:
        values.append(
            name
        )

    values.extend(
        COUNTRY_RELEVANCE_ALIASES.get(
            code,
            (),
        )
    )

    output: list[str] = []
    seen: set[str] = set()

    for value in values:
        clean = " ".join(
            str(
                value or ""
            ).split()
        ).strip()

        folded = fold(
            clean
        )

        # Never use dangerous short tokens such as:
        # in, us, de or es.
        if (
            not clean
            or len(folded) < 3
            or folded in seen
        ):
            continue

        seen.add(
            folded
        )

        output.append(
            clean
        )

    return tuple(
        output
    )


def country_headline_search_terms(
    country_code: str,
    country_name: str,
    *,
    limit: int = 6,
) -> tuple[str, ...]:
    """
    Return safe geographical terms for provider-side
    Sports discovery.

    These are country and demonym aliases only. No sport,
    league, competition or result term is listed here.
    """

    values = _country_alias_values(
        country_code,
        country_name,
    )

    return tuple(
        values[
            :max(
                1,
                int(limit or 1),
            )
        ]
    )


def country_query_expression(
    country_code: str,
    country_name: str,
    *,
    topic: str = "",
    category: str = "",
) -> str:
    values = list(
        _country_alias_values(
            country_code,
            country_name,
        )
    )

    if sports_scope(
        topic,
        category,
    ):
        values.extend(
            _country_sports_alias_values(
                country_code,
                country_name,
                for_query=True,
            )
        )

    output: list[str] = []
    seen: set[str] = set()

    for value in values:
        clean = " ".join(
            str(
                value or ""
            ).split()
        ).strip()

        key = fold(
            clean
        )

        if (
            not clean
            or not key
            or key in seen
        ):
            continue

        seen.add(
            key
        )

        output.append(
            clean
        )

    if not output:
        return ""

    return (
        "("
        + " OR ".join(
            f'"{alias}"'
            for alias in output
        )
        + ")"
    )

COUNTRY_OWNERSHIP_SUBJECT_PATTERN = (
    r"(?:government|parliament|congress|court|central bank|"
    r"ministry|minister|president|prime minister|regulator|"
    r"authority|military|police|company|firm|startup|bank|"
    r"manufacturer|business|university|researchers?|scientists?|"
    r"laborator(?:y|ies)|space agency|hospital|health authority|"
    r"film|movie|actor|actress|singer|director|national team|team|"
    r"club|players?|athletes?|coaches?|managers?|captains?|squads?|"
    r"internationals?|federation|association|league|championship|"
    r"medallists?|medalists?|defenders?|midfielders?|strikers?|"
    r"goalkeepers?|bowlers?|batters?|pitchers?|golfers?|swimmers?|"
    r"cyclists?|runners?|boxers?|judokas?|drivers?)"
)


COUNTRY_SOURCE_DESCRIPTOR_PATTERN = (
    r"(?:news\s+)?(?:outlet|publication|newspaper|website|site|"
    r"media|broadcaster|magazine|journal|agency|report|source)"
)


def _country_mentions_are_incidental_only(
    text: str,
    aliases: set[str],
) -> bool:
    """
    Return True when every requested-country mention is only
    a venue, source, list item, comparison or future opponent.
    """

    folded_text = fold(
        text
    )

    found = False

    for alias in aliases:
        clean_alias = fold(
            alias
        )

        if not clean_alias:
            continue

        alias_pattern = re.compile(
            r"(?<!\w)"
            + re.escape(
                clean_alias
            )
            + r"(?!\w)",
            flags=re.I | re.UNICODE,
        )

        for occurrence in alias_pattern.finditer(
            folded_text
        ):
            found = True

            prefix = folded_text[
                max(
                    0,
                    occurrence.start() - 160,
                ):
                occurrence.start()
            ]

            suffix = folded_text[
                occurrence.end():
                occurrence.end() + 160
            ]

            source_reference = bool(
                re.search(
                    r"^\s+(?:'s\s+)?"
                    + COUNTRY_SOURCE_DESCRIPTOR_PATTERN
                    + r"\b",
                    suffix,
                    flags=re.I | re.UNICODE,
                )
            )

            venue_reference = bool(
                re.search(
                    r"(?:held\s+in|hosted\s+in|staged\s+in|"
                    r"scheduled\s+in|set\s+in|"
                    r"takes?\s+place\s+in|to\s+be\s+held\s+in|"
                    r"bound\s+for|heads?\s+to|headed\s+to|"
                    r"travels?\s+to|arrives?\s+in|lands?\s+in)\s*$",
                    prefix,
                    flags=re.I | re.UNICODE,
                )
                or re.search(
                    r"\b(?:games?|tournament|championship|cup|"
                    r"match|race|test|series|conference|summit|"
                    r"expo|festival|ceremony|event)\b"
                    r".{0,90}\b(?:in|at)\s*$",
                    prefix,
                    flags=re.I | re.UNICODE,
                )
                or re.search(
                    r"^\s*[- ]?hosted\b",
                    suffix,
                    flags=re.I | re.UNICODE,
                )
            )

            future_opponent_reference = bool(
                re.search(
                    r"(?:will|to|set\s+to|scheduled\s+to|due\s+to)\s+"
                    r"(?:face|play|meet|take\s+on|host)\b.{0,100}$",
                    prefix,
                    flags=re.I | re.UNICODE,
                )
            )

            comparison_reference = bool(
                re.search(
                    r"\b(?:follow|follows|followed|following|"
                    r"mirror|mirrors|mirrored|mirroring|"
                    r"echo|echoes|echoed|echoing|like|"
                    r"in\s+line\s+with|compared\s+with|"
                    r"compared\s+to)\b.{0,80}$",
                    prefix,
                    flags=re.I | re.UNICODE,
                )
            )

            secondary_quote_reference = bool(
                re.search(
                    r"\b(?:after|following|amid)\s*$",
                    prefix,
                    flags=(
                        re.I
                        | re.UNICODE
                    ),
                )
                and re.search(
                    r"^\s+['\"“”‘’]",
                    suffix,
                    flags=(
                        re.I
                        | re.UNICODE
                    ),
                )
            )

            unsuccessful_alternative_reference = bool(
                re.search(
                    r"\b(?:instead\s+of|rather\s+than|"
                    r"snubs?|snubbed|rejects?|rejected|rejecting|"
                    r"turns?\s+down|turned\s+down|"
                    r"opts?\s+against|opted\s+against|"
                    r"linked\s+(?:with|to)|"
                    r"amid\s+interest\s+from|"
                    r"despite\s+interest\s+from|"
                    r"interest\s+from|wanted\s+by|targeted\s+by|"
                    r"alternative\s+to)\b.{0,90}$",
                    prefix,
                    flags=re.I | re.UNICODE,
                )
                or re.search(
                    r"\b(?:choose|chooses|chose|chosen|"
                    r"pick|picks|picked|"
                    r"join|joins|joined|"
                    r"sign|signs|signed|"
                    r"move|moves|moved)\b"
                    r".{0,70}\bover\s*$",
                    prefix,
                    flags=re.I | re.UNICODE,
                )
            )

            preview_or_absence_reference = bool(
                re.search(
                    r"(?:ruled\s+out\s+of|to\s+miss|"
                    r"miss(?:es|ing)?|withdraw(?:s|n)?\s+from|"
                    r"ahead\s+of|before)\b.{0,100}$",
                    prefix,
                    flags=re.I | re.UNICODE,
                )
                and re.search(
                    r"^\s+(?:test\s+)?(?:series|tour|match|game|"
                    r"fixture|tournament|cup|championship)\b",
                    suffix,
                    flags=re.I | re.UNICODE,
                )
            )

            event_scope_reference = bool(
                re.search(
                    r"\b(?:for|ahead\s+of|before)\s*$",
                    prefix,
                    flags=re.I | re.UNICODE,
                )
                and re.search(
                    r"^\s+(?:test\s+)?(?:series|tour|match|game|"
                    r"fixture|tournament|cup|championship)\b",
                    suffix,
                    flags=re.I | re.UNICODE,
                )
            )

            list_reference = bool(
                re.search(
                    r"\b(?:including|among|alongside|"
                    r"contingent\s+of|players?\s+from|"
                    r"athletes?\s+from|teams?\s+from|"
                    r"countries?\s+including|"
                    r"representatives?\s+from)\b.{0,120}$",
                    prefix,
                    flags=re.I | re.UNICODE,
                )
                or (
                    re.search(
                        r"[,;]\s*$",
                        prefix,
                    )
                    and re.search(
                        r"^\s*[,;]",
                        suffix,
                    )
                )
            )

            if any(
                (
                    source_reference,
                    venue_reference,
                    future_opponent_reference,
                    comparison_reference,
                    secondary_quote_reference,
                    unsuccessful_alternative_reference,
                    preview_or_absence_reference,
                    event_scope_reference,
                    list_reference,
                )
            ):
                continue

            return False

    return found


def _country_description_has_primary_ownership(
    description: str,
    aliases: set[str],
) -> bool:
    """
    Require a description-only country match to identify an
    actor, institution or participant belonging to that country.
    A bare venue, source or opponent mention is insufficient.
    """

    text = fold(
        description
    )[:1200]

    if not text:
        return False

    if _country_mentions_are_incidental_only(
        text,
        aliases,
    ):
        return False

    for alias in aliases:
        clean_alias = fold(
            alias
        )

        if not clean_alias:
            continue

        country_pattern = (
            r"(?<!\w)"
            + re.escape(
                clean_alias
            )
            + r"(?!\w)"
        )

        if re.search(
            country_pattern
            + r"(?:['’]s)?(?:\s+[^\W_]+){0,3}\s+"
            + COUNTRY_OWNERSHIP_SUBJECT_PATTERN
            + r"\b",
            text,
            flags=re.I | re.UNICODE,
        ):
            return True

        if re.search(
            r"\b"
            + COUNTRY_OWNERSHIP_SUBJECT_PATTERN
            + r"\b.{0,35}\b(?:for|of|from|representing)\s+"
            + country_pattern,
            text,
            flags=re.I | re.UNICODE,
        ):
            return True

        occurrence = re.search(
            country_pattern,
            text,
            flags=re.I | re.UNICODE,
        )

        if (
            occurrence
            and occurrence.start() <= 90
            and matches(
                text[:320],
                CURRENT_EVENT_PATTERNS,
            )
        ):
            return True

    return False


def _country_reference_is_secondary_only(
    title: str,
    aliases: set[str],
) -> bool:
    return _country_mentions_are_incidental_only(
        title,
        aliases,
    )

    
def country_relevant(
    article: dict,
    country_code: str,
    country_name: str,
    *,
    topic: str = "",
    category: str = "",
    provider_category_verified: bool = False,
) -> bool:
    sports_request = sports_scope(
        topic,
        category,
    )

    base_aliases = {
        fold(alias)
        for alias in _country_alias_values(
            country_code,
            country_name,
        )
        if fold(alias)
    }

    sports_aliases = {
        fold(alias)
        for alias in (
            _country_sports_alias_values(
                country_code,
                country_name,
            )
            if sports_request
            else ()
        )
        if fold(alias)
    }

    if not (
        base_aliases
        or sports_aliases
    ):
        return True

    title = fold(
        article.get("title")
        or ""
    )

    description = fold(
        article.get("description")
        or ""
    )[:1000]

    content = fold(
        article.get("content")
        or ""
    )[:1200]

    exact_gb_key = (
        _exact_gb_country_key(
            country_name
        )
        if str(
            country_code or ""
        ).casefold() == "gb"
        else ""
    )

    # New England is a US region/team name, not England.
    if exact_gb_key == "england":
        def remove_new_england(
            value: str,
        ) -> str:
            return re.sub(
                r"(?<!\w)new\s+england(?!\w)",
                " ",
                value,
                flags=re.I | re.UNICODE,
            )

        title = remove_new_england(
            title
        )

        description = remove_new_england(
            description
        )

        content = remove_new_england(
            content
        )

    def mention_count(
        text: str,
        values: set[str],
    ) -> int:
        return sum(
            len(
                _compiled_regex(
                    r"(?<!\w)"
                    + re.escape(
                        value
                    )
                    + r"(?!\w)"
                ).findall(
                    text
                )
            )
            for value in values
            if value
        )
    
    base_title_hits = mention_count(
        title,
        base_aliases,
    )

    sports_title_hits = mention_count(
        title,
        sports_aliases,
    )

    base_description_hits = mention_count(
        description,
        base_aliases,
    )

    sports_description_hits = mention_count(
        description,
        sports_aliases,
    )

    base_content_hits = mention_count(
        content,
        base_aliases,
    )

    sports_content_hits = mention_count(
        content,
        sports_aliases,
    )

    requested_title_hits = (
        base_title_hits
        + sports_title_hits
    )

    if (
        requested_title_hits
        and _country_reference_is_secondary_only(
            title,
            (
                base_aliases
                | sports_aliases
            ),
        )
    ):
        return False

    requested_aliases = (
        base_aliases
        | sports_aliases
    )

    requested_description_is_primary = (
        _country_description_has_primary_ownership(
            description,
            requested_aliases,
        )
    )

    # For ordinary country requests, a headline explicitly
    # centred on another sovereign country must not qualify
    # merely because the requested country appears as the host
    # or venue in the description or article body.
    if not exact_gb_key:
        requested_code = str(
            country_code or ""
        ).strip().casefold()

        other_country_title_aliases = {
            fold(alias)
            for code, values in (
                COUNTRY_RELEVANCE_ALIASES.items()
            )
            if code != requested_code
            for alias in values
            if fold(alias)
        }

        other_country_title_hits = mention_count(
            title,
            other_country_title_aliases,
        )

        if (
            other_country_title_hits
            and not requested_title_hits
            and not requested_description_is_primary
        ):
            return False

    if exact_gb_key:
        other_base_aliases = {
            fold(alias)
            for key, values in (
                GB_HOME_NATION_ALIASES.items()
            )
            if key != exact_gb_key
            for alias in values
        }

        other_sports_aliases = (
            {
                fold(alias)
                for key, values in (
                    GB_HOME_NATION_SPORTS_RELEVANCE_ALIASES.items()
                )
                if key != exact_gb_key
                for alias in values
            }
            if sports_request
            else set()
        )

        other_title_hits = (
            mention_count(
                title,
                other_base_aliases,
            )
            + mention_count(
                title,
                other_sports_aliases,
            )
        )

        other_description_hits = (
            mention_count(
                description,
                other_base_aliases,
            )
            + mention_count(
                description,
                other_sports_aliases,
            )
        )

        # An article explicitly headed by another sovereign
        # country is not a Scotland, England, Wales or Northern
        # Ireland story merely because the event happens there.
        other_country_title_aliases = {
            fold(alias)
            for code, values in (
                COUNTRY_RELEVANCE_ALIASES.items()
            )
            if code != "gb"
            for alias in values
            if fold(alias)
        }

        other_country_title_hits = mention_count(
            title,
            other_country_title_aliases,
        )

        gb_sports_description_is_primary = bool(
            sports_description_hits
            and not _country_mentions_are_incidental_only(
                description,
                sports_aliases,
            )
        )

        if (
            (
                other_title_hits
                or other_country_title_hits
            )
            and not requested_title_hits
            and not gb_sports_description_is_primary
        ):
            return False

        if requested_title_hits:
            return True

        # A domestic competition or governing-body phrase,
        # such as Premier League or Scottish Rugby, is strong
        # country evidence only when it is not a venue,
        # comparison, source or opponent reference.
        if gb_sports_description_is_primary:
            return True

        if other_description_hits:
            return False

        # One passing location mention such as
        # "in Glasgow, Scotland" is insufficient.
        #
        # This blocks Australian and Canadian Commonwealth
        # Games stories from becoming Scotland headlines.
        return base_description_hits >= 2


    if requested_title_hits:
        return True

    return requested_description_is_primary


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
    text = fold(
        value
    )

    return any(
        _compiled_regex(
            pattern
        ).search(
            text
        )
        for pattern in patterns
    )


def phrase_present(
    phrase: str,
    text: str,
) -> bool:
    pattern = (
        r"(?<!\w)"
        + re.escape(
            phrase
        )
        + r"(?!\w)"
    )

    return bool(
        _compiled_regex(
            pattern
        ).search(
            text
        )
    )


def _query_atom(
    value: str,
) -> str:
    clean = " ".join(
        str(
            value or ""
        ).split()
    ).strip()

    if not clean:
        return ""

    return (
        f'"{clean}"'
        if (
            " " in clean
            or not clean.isascii()
        )
        else clean
    )


def canonical_topic(
    topic: str,
) -> str:
    clean = " ".join(
        str(
            topic or ""
        ).split()
    ).strip()

    if not clean:
        return ""

    target = fold(
        clean
    )

    for group in (
        TOPIC_EQUIVALENT_GROUPS
    ):
        if target in {
            fold(alias)
            for alias in group
        }:
            return str(
                group[0]
            )

    # Unknown topics are deliberately preserved.
    #
    # This is what makes News open-ended rather
    # than a fixed topic whitelist.
    return clean


def _topic_equivalents(
    canonical: str,
) -> tuple[str, ...]:
    target = fold(
        canonical
    )

    for group in (
        TOPIC_EQUIVALENT_GROUPS
    ):
        if fold(
            group[0]
        ) == target:
            return tuple(
                str(item)
                for item in group
            )

    return (
        (canonical,)
        if canonical
        else ()
    )


def topic_query_expression(
    topic: str,
) -> str:
    canonical = canonical_topic(
        topic
    )

    if not canonical:
        return ""

    equivalent_values = list(
        _topic_equivalents(
            canonical
        )
    )

    expansion_values = list(
        TOPIC_QUERY_EXPANSIONS.get(
            fold(
                canonical
            ),
            (),
        )
    )

    values: list[str] = []
    seen: set[str] = set()

    for value in (
        equivalent_values
        + expansion_values
    ):
        clean = " ".join(
            str(
                value or ""
            ).split()
        ).strip()

        key = fold(
            clean
        )

        if (
            not clean
            or key in seen
        ):
            continue

        seen.add(
            key
        )

        atom = _query_atom(
            clean
        )

        if atom:
            values.append(
                atom
            )

    # Known broad topics use equivalents and optional
    # recall expansions.
    #
    # A specific item such as NASA or OpenAI is not
    # broadened unless the user requested the broader
    # subject.
    if len(
        values
    ) > 1:
        return (
            "("
            + " OR ".join(
                values
            )
            + ")"
        )

    clean_atom = _query_atom(
        canonical
    )

    # Any unknown multiword topic remains dynamic.
    #
    # Example:
    #
    #   quantum computing
    #
    # becomes:
    #
    #   ("quantum computing" OR
    #    (quantum AND computing))
    significant_tokens = [
        token
        for token in re.findall(
            r"[^\W_]+",
            canonical,
            flags=re.UNICODE,
        )
        if (
            len(token) >= 2
            and fold(
                token
            ) not in STOPWORDS
        )
    ]

    if (
        len(
            significant_tokens
        ) >= 2
        and len(
            significant_tokens
        ) <= 6
    ):
        token_expression = (
            " AND ".join(
                _query_atom(
                    token
                )
                for token
                in significant_tokens
            )
        )

        return (
            f"({clean_atom} OR "
            f"({token_expression}))"
        )

    return clean_atom


def topic_aliases(
    topic: str,
) -> set[str]:
    canonical = canonical_topic(
        topic
    )

    if not canonical:
        return set()

    aliases = {
        fold(
            item
        )
        for item in (
            _topic_equivalents(
                canonical
            )
        )
        if fold(
            item
        )
    }

    aliases.update(
        fold(
            item
        )
        for item in (
            TOPIC_QUERY_EXPANSIONS.get(
                fold(
                    canonical
                ),
                (),
            )
        )
        if fold(
            item
        )
    )

    return aliases


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


def category_relevant(
    article: dict,
    category: str,
    *,
    provider_category_verified: bool = False,
) -> bool:
    target = fold(
        category
    )

    if (
        not target
        or target in {
            "general",
            "sports",
            "sport",
            "खेल",
        }
    ):
        return True

    title = str(
        article.get("title")
        or ""
    )

    description = str(
        article.get("description")
        or ""
    )

    title_and_description = " ".join(
        (
            title,
            description,
        )
    )

    # Sports availability and selection stories do not become
    # Health news merely because an injury, doctor or medical
    # team is mentioned.
    if (
        target == "health"
        and matches(
            title,
            HEALTH_SPORTS_AVAILABILITY_PATTERNS,
        )
    ):
        return False

    # Entertainment means a creative work, performer,
    # production, release or audience-performance development.
    #
    # Corporate finance and securities stories remain Business.
    if target == "entertainment":
        if (
            matches(
                title,
                ENTERTAINMENT_CORPORATE_FINANCE_PATTERNS,
            )
            and not matches(
                title,
                ENTERTAINMENT_CREATIVE_PERFORMANCE_PATTERNS,
            )
        ):
            return False

        return matches(
            title_and_description,
            ENTERTAINMENT_PRIMARY_PATTERNS,
        )

    # A native Top Headlines category is useful evidence after
    # category-specific hard exclusions have run.
    if provider_category_verified:
        return True

    patterns = (
        CATEGORY_RELEVANCE_PATTERNS.get(
            target
        )
    )

    if not patterns:
        return True

    return matches(
        title_and_description,
        patterns,
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


_DUPLICATE_TOKEN_SYNONYMS = {
    "announces": "announce",
    "announced": "announce",

    "appoints": "appoint",
    "appointed": "appoint",
    "appointment": "appoint",
    "starts": "appoint",
    "started": "appoint",
    "become": "appoint",
    "becomes": "appoint",
    "became": "appoint",
    "becoming": "appoint",
    "name": "appoint",
    "names": "appoint",
    "named": "appoint",
    "naming": "appoint",
    "hire": "appoint",
    "hires": "appoint",
    "hired": "appoint",
    "hiring": "appoint",

    "secures": "secure",
    "secured": "secure",

    "inaugural": "first",
    "initial": "first",
    "maiden": "first",

    "investment": "funding",
    "investments": "funding",
    "financing": "funding",

    "cuts": "cut",
    "cutting": "cut",
    "jobs": "job",

    "promises": "promise",
}


_DUPLICATE_GENERIC_TOKENS = {
    "a",
    "an",
    "the",
    "its",
    "of",
    "to",
    "for",
    "from",
    "in",
    "on",
    "at",
    "with",
    "and",
    "as",
    "after",
    "before",

    "unit",
    "group",
    "division",
    "department",
    "arm",
    "business",
    "operation",
    "operations",

    "job",
    "role",
    "head",
    "new",
    "latest",
    "update",
    "report",
}



_DUPLICATE_APPOINTMENT_ROLE_TOKENS = {
    "coach",
    "manager",
    "director",
    "chief",
    "president",
    "captain",
    "minister",
    "secretary",
    "leader",
}


_DUPLICATE_TRANSACTION_ACTION_TOKENS = {
    "bid",
    "offer",
    "transfer",
    "sign",
    "signing",
    "join",
    "loan",
    "deal",
    "appoint",
    "hire",
    "cancel",
    "postpone",
    "suspend",
    "injury",
}


_DUPLICATE_STATUS_ACTION_RE = re.compile(
    r"\b(?:ruled\s+out|to\s+miss|miss(?:es|ed|ing)?|"
    r"unavailable|withdraw(?:s|n)?|sidelined|"
    r"injur(?:y|ies|ed))\b",
    flags=re.I | re.UNICODE,
)


_DUPLICATE_WITHDRAW_SUPPORT_RE = re.compile(
    r"\b(?:(?:withdraw(?:s|n|ing)?|withdrew|"
    r"pull(?:s|ed|ing)?|drop(?:s|ped|ping)?)\b"
    r".{0,24}\b(?:support|backing|endorsement)\b|"
    r"(?:no\s+longer|will\s+not|won['’]?t|"
    r"refuses?|refused)\b"
    r".{0,18}\b(?:support|back|endorse)\b)",
    flags=re.I | re.UNICODE,
)


_DUPLICATE_DECISION_NOISE_TOKENS = {
    "withdraw",
    "withdraws",
    "withdrew",
    "withdrawn",
    "withdrawing",
    "pull",
    "pulls",
    "pulled",
    "pulling",
    "drop",
    "drops",
    "dropped",
    "dropping",
    "support",
    "back",
    "backing",
    "endorse",
    "endorsement",
    "no",
    "longer",
    "will",
    "not",
    "won",
    "refuse",
    "refuses",
    "refused",
    "fa",
    "federation",
    "association",
    "club",
    "team",
    "government",
    "committee",
    "board",
    "council",
    "union",
    "league",
    "body",
    "organisation",
    "organization",
}


def _semantic_duplicate_tokens(
    value: object,
) -> list[str]:
    output: list[str] = []

    for token in re.findall(
        r"[^\W_]+",
        fold(value),
        flags=re.UNICODE,
    ):
        normalized = (
            _DUPLICATE_TOKEN_SYNONYMS.get(
                token,
                token,
            )
        )

        if (
            len(normalized) < 2
            or normalized
            in _DUPLICATE_GENERIC_TOKENS
        ):
            continue

        output.append(
            normalized
        )

    return output


def _status_subject_phrases(
    value: object,
) -> set[str]:
    text = str(
        value or ""
    )

    output: set[str] = set()

    for action in (
        _DUPLICATE_STATUS_ACTION_RE.finditer(
            text
        )
    ):
        prefix = text[
            max(
                0,
                action.start() - 100,
            ):
            action.start()
        ]

        phrases = re.findall(
            r"(?<!\w)"
            r"([A-Z][\w'’.-]*"
            r"(?:\s+[A-Z][\w'’.-]*){1,3})"
            r"(?!\w)",
            prefix,
            flags=re.UNICODE,
        )

        if not phrases:
            continue

        phrase = fold(
            phrases[-1]
        )

        if phrase:
            output.add(
                phrase
            )

    return output


def _capitalized_phrase_ngrams(
    value: object,
) -> set[str]:
    text = str(
        value or ""
    )

    output: set[str] = set()

    for sequence in re.findall(
        r"(?<!\w)"
        r"([A-Z][\w'’.-]*"
        r"(?:\s+[A-Z][\w'’.-]*)+)",
        text,
        flags=re.UNICODE,
    ):
        words = sequence.split()

        for size in (
            2,
            3,
        ):
            for start in range(
                0,
                len(words) - size + 1,
            ):
                output.add(
                    fold(
                        " ".join(
                            words[
                                start:
                                start + size
                            ]
                        )
                    )
                )

    return output


def _same_person_status_story(
    first: str,
    second: str,
) -> bool:
    shared_subjects = (
        _status_subject_phrases(
            first
        )
        & _status_subject_phrases(
            second
        )
    )

    if not shared_subjects:
        return False

    first_anchors = (
        _capitalized_phrase_ngrams(
            first
        )
        - shared_subjects
    )

    second_anchors = (
        _capitalized_phrase_ngrams(
            second
        )
        - shared_subjects
    )

    # Require another shared named anchor beyond the person:
    # an opponent, country, club or competition.
    #
    # This merges reports about the same absence while
    # preserving absences against different opponents.
    return bool(
        first_anchors
        & second_anchors
    )


def _decision_actor_anchors(
    value: object,
    action_start: int,
) -> set[str]:
    text = str(
        value or ""
    )

    prefix = text[
        max(
            0,
            action_start - 140,
        ):
        action_start
    ]

    # Keep only the final clause before the decision verb:
    #
    #   Infantino bid hit as Wales withdraws support
    #                         ^^^^^ actor
    actor_segment = re.split(
        r"(?:\bas\b|\bafter\b|\bwhile\b|\bbut\b|"
        r"\bwhereas\b|[:;|–—])",
        prefix,
        flags=re.I | re.UNICODE,
    )[-1]

    anchors = set(
        _semantic_duplicate_tokens(
            actor_segment
        )
    )

    anchors.update(
        _entity_aliases(
            actor_segment
        )
    )

    return {
        token
        for token in anchors
        if (
            token
            not in _DUPLICATE_DECISION_NOISE_TOKENS
            and token
            not in {
                "officially",
                "formally",
                "reportedly",
                "set",
                "expected",
                "plans",
                "plan",
            }
        )
    }


def _same_organisation_decision_story(
    first: str,
    second: str,
) -> bool:
    first_action = (
        _DUPLICATE_WITHDRAW_SUPPORT_RE.search(
            first
        )
    )

    second_action = (
        _DUPLICATE_WITHDRAW_SUPPORT_RE.search(
            second
        )
    )

    if not (
        first_action
        and second_action
    ):
        return False

    first_actor = _decision_actor_anchors(
        first,
        first_action.start(),
    )

    second_actor = _decision_actor_anchors(
        second,
        second_action.start(),
    )

    # Different organisations making the same decision about
    # the same target remain separate stories.
    if not (
        first_actor
        & second_actor
    ):
        return False

    first_target = {
        *set(
            _semantic_duplicate_tokens(
                first
            )
        ),
        *_entity_aliases(
            first
        ),
    } - first_actor - _DUPLICATE_DECISION_NOISE_TOKENS

    second_target = {
        *set(
            _semantic_duplicate_tokens(
                second
            )
        ),
        *_entity_aliases(
            second
        ),
    } - second_actor - _DUPLICATE_DECISION_NOISE_TOKENS

    # Two shared target anchors distinguish one repeated
    # decision from separate decisions by the same body.
    return len(
        first_target
        & second_target
    ) >= 2



def _named_entities(
    value: object,
) -> set[str]:
    return {
        token.casefold()
        for token in re.findall(
            r"(?<!\w)"
            r"(?:[A-Z][\w'’-]{2,}|[A-Z]{2,})"
            r"(?!\w)",
            str(value or ""),
            flags=re.UNICODE,
        )
        if token.casefold()
        not in {
            "the",
            "this",
            "that",
            "why",
            "how",
            "what",
        }
    }


def _entity_acronyms(
    value: object,
) -> tuple[
    set[str],
    set[str],
]:
    text = str(
        value or ""
    )

    explicit = {
        token.casefold()
        for token in re.findall(
            r"(?<!\w)[A-Z]{2,6}(?!\w)",
            text,
            flags=re.UNICODE,
        )
    }

    expanded: set[str] = set()

    for phrase in re.findall(
        r"(?<!\w)"
        r"[A-Z][\w'’]*"
        r"(?:[\s-]+[A-Z][\w'’]*){1,5}"
        r"(?!\w)",
        text,
        flags=re.UNICODE,
    ):
        words = re.findall(
            r"[A-Z][\w'’]*",
            phrase,
            flags=re.UNICODE,
        )

        # Do not invent acronyms from ordinary two-word
        # personal names:
        #
        # Victor Osimhen -> must not become VO
        # Zion Suzuki   -> must not become ZS
        #
        # Longer organisation-style names and hyphenated
        # names can still form acronym candidates:
        #
        # Paris Saint-Germain -> PSG
        if (
            len(words) < 3
            and "-" not in phrase
        ):
            continue

        acronym = "".join(
            word[0]
            for word in words
            if word
        ).casefold()

        if 2 <= len(acronym) <= 6:
            expanded.add(
                acronym
            )

    return (
        explicit,
        expanded,
    )


def _entity_aliases(
    value: object,
) -> set[str]:
    explicit, expanded = (
        _entity_acronyms(
            value
        )
    )

    return {
        *_named_entities(
            value
        ),
        *explicit,
        *expanded,
    }


def _conflicting_entities(
    first: str,
    second: str,
) -> bool:
    first_entities = _entity_aliases(
        first
    )

    second_entities = _entity_aliases(
        second
    )

    shared = (
        first_entities
        & second_entities
    )

    first_only = (
        first_entities
        - shared
    )

    second_only = (
        second_entities
        - shared
    )

    return bool(
        shared
        and first_only
        and second_only
        and len(first_only) <= 3
        and len(second_only) <= 3
    )



def near_duplicate(
    first: str,
    second: str,
) -> bool:
    if _same_person_status_story(
        first,
        second,
    ):
        return True

    if _same_organisation_decision_story(
        first,
        second,
    ):
        return True

    first_entities = _entity_aliases(
        first
    )

    second_entities = _entity_aliases(
        second
    )

    first_tokens = set(
        _semantic_duplicate_tokens(
            first
        )
    )

    second_tokens = set(
        _semantic_duplicate_tokens(
            second
        )
    )

    # Add dynamic entity aliases to the semantic token sets so
    # an acronym and its expanded organisation name can match.
    first_tokens.update(
        first_entities
    )

    second_tokens.update(
        second_entities
    )

    if (
        not first_tokens
        or not second_tokens
    ):
        return False

    if first_tokens == second_tokens:
        return True

    shared_tokens = (
        first_tokens
        & second_tokens
    )

    shared = len(
        shared_tokens
    )

    smaller = min(
        len(first_tokens),
        len(second_tokens),
    )

    union = len(
        first_tokens
        | second_tokens
    )

    containment = (
        shared
        / smaller
    )

    similarity = (
        shared
        / union
    )

    shared_entities = len(
        first_entities
        & second_entities
    )

    appointment_duplicate = bool(
        "appoint" in first_tokens
        and "appoint" in second_tokens
        and shared >= 3
        and shared_entities >= 2
        and bool(
            shared_tokens
            & _DUPLICATE_APPOINTMENT_ROLE_TOKENS
        )
    )

    first_explicit, first_expanded = (
        _entity_acronyms(
            first
        )
    )

    second_explicit, second_expanded = (
        _entity_acronyms(
            second
        )
    )

    shared_acronym_link = bool(
        (
            first_explicit
            & (
                second_explicit
                | second_expanded
            )
        )
        or (
            second_explicit
            & first_expanded
        )
    )

    if (
        _DUPLICATE_STATUS_ACTION_RE.search(
            first
        )
        and _DUPLICATE_STATUS_ACTION_RE.search(
            second
        )
        and _conflicting_entities(
            first,
            second,
        )
    ):
        return False

    transaction_duplicate = bool(
        shared_tokens
        & _DUPLICATE_TRANSACTION_ACTION_TOKENS
    ) and bool(
        (
            shared >= 4
            and shared_entities >= 2
            and shared_acronym_link
        )
        or (
            shared >= 5
            and shared_entities >= 3
        )
    )

    if (
        appointment_duplicate
        or transaction_duplicate
    ):
        return True

    if _conflicting_entities(
        first,
        second,
    ):
        return False

    return bool(
        (
            shared >= 4
            and containment >= 0.70
            and shared_entities >= 1
        )
        or (
            shared >= 6
            and similarity >= 0.68
        )
    )


def articles_near_duplicate(
    first: dict,
    second: dict,
) -> bool:
    first_title = str(
        first.get("title")
        or ""
    )

    second_title = str(
        second.get("title")
        or ""
    )

    if near_duplicate(
        first_title,
        second_title,
    ):
        return True

    first_context = " ".join(
        (
            first_title,

            str(
                first.get("description")
                or ""
            )[:320],
        )
    )

    second_context = " ".join(
        (
            second_title,

            str(
                second.get("description")
                or ""
            )[:320],
        )
    )

    return near_duplicate(
        first_context,
        second_context,
    )



def rejection_reason(
    article: dict,
    topic: str,
    category: str = "",
    country_code: str = "",
    country_name: str = "",
    *,
    provider_category_verified: bool = False,
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

    # This check is unconditional. A cancellation or delay
    # does not rescue a "here's why" explainer article.
    if matches(
        title,
        EXPLANATORY_NEWS_FORMAT_PATTERNS,
    ):
        return "explanatory_or_analysis_title"

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

    if (
        sports_scope(
            topic,
            category,
        )
        and matches(
            title,
            SPORTS_VIDEO_GAME_PRODUCT_PATTERNS,
        )
        and not matches(
            title,
            ESPORTS_COMPETITION_PATTERNS,
        )
    ):
        return "sports_video_game_product"


    if (
        sports_scope(
            topic,
            category,
        )
        and matches(
            title,
            SPORTS_NONCOMPETITIVE_LEGAL_PATTERNS,
        )
    ):
        return "sports_noncompetitive_legal"

    if (
        sports_scope(
            topic,
            category,
        )
        and (
            matches(
                title,
                SPORTS_REACTION_OR_PERSONALITY_PATTERNS,
            )
            or matches(
                title,
                SPORTS_PERSONALITY_ATTENDANCE_PATTERNS,
            )
            or matches(
                title,
                SPORTS_ANALYSIS_FEATURE_PATTERNS,
            )
            or matches(
                title,
                SPORTS_QUOTE_COMMENTARY_PATTERNS,
            )
        )
    ):
        return "sports_reaction_or_personality"

    if (
        sports_scope(
            topic,
            category,
        )
        and matches(
            title,
            SPORTS_COMMERCIAL_PRODUCT_PATTERNS,
        )
    ):
        return "sports_product_or_commercial"

    is_sports_utility = bool(
        matches(
            combined_text,
            SPORTS_UTILITY_PATTERNS,
        )
        or matches(
            title,
            SPORTS_ROLLING_HUB_TITLE_PATTERNS,
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

    if (
        sports_scope(
            topic,
            category,
        )
        and not sports_development_relevant(
            article,
            provider_category_verified=(
                provider_category_verified
            ),
        )
    ):
        return "not_sporting_development"

    if not category_relevant(
        article,
        category,
        provider_category_verified=(
            provider_category_verified
        ),
    ):
        return "category_mismatch"

    if (
        str(
            country_name or ""
        ).strip()
        and str(
            country_name
        ).casefold()
        != "world"
        and not country_relevant(
            article,
            country_code,
            country_name,
            topic=topic,
            category=category,
            provider_category_verified=(
                provider_category_verified
            ),
        )
    ):
        return "country_mismatch"

    topic = canonical_topic(
        topic
    )

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
        # Sports requests have already passed the dedicated
        # direct-development gate above. Do not reject a valid
        # transfer bid, call-up, comeback or similar event only
        # because the generic news verb table lacks that exact
        # sporting verb.
        if (
            sports_scope(
                topic,
                category,
            )
            and sports_development_relevant(
                article,
                provider_category_verified=(
                    provider_category_verified
                ),
            )
        ):
            return ""

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
    country_code: str = "",
    country_name: str = "",
    fresh_days: int = 7,
    provider_category_verified: bool = False,
) -> dict:
    result = dict(
        payload
        if isinstance(
            payload,
            dict,
        )
        else {}
    )

    topic = canonical_topic(
        topic
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


    seen_articles: list[dict] = []
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
            country_code,
            country_name,
            provider_category_verified=(
                provider_category_verified
            ),
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
            articles_near_duplicate(
                article,
                existing_article,
            )
            for existing_article
            in seen_articles
        ):
            reject(
                "duplicate_story"
            )
            continue

        seen_articles.append(
            article
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
        "country": str(
            country_name or ""
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