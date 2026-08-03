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

    # Teaser-led titles such as:
    #
    #   Green with envy? How...
    #   A major mistake? Why...
    #
    # are feature or explanatory articles rather than
    # direct reports of a current development.
    r"\?\s+(?:what|why|how|who|where|when|"
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
    r"^\s*(?:what|why|how|who|where|when)\b",
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
    r"^\s*(?:what|why|how|who|where|when)\b",

    r"\?\s+(?:what|why|how|who|where|when)\b",

    r"(?:^|[|:–—-]\s*)"
    r"(?:here(?:'|’)s why|here is why|"
    r"why it matters|what it means)\b",

    # Hindi and Hinglish.
    r"^\s*(?:क्या|क्यों|कैसे|कौन|कब|कहाँ)",

    r"(?:^|[|:–—-]\s*)"
    r"(?:जानिए क्यों|यह है वजह|इसलिए हुआ)",

    # German. Text is accent-folded before matching.
    r"^\s*(?:was|warum|wie|wer|wann|wo)\b",

    r"(?:^|[|:–—-]\s*)"
    r"(?:darum|deshalb|das ist der grund)\b",

    # French.
    r"^\s*(?:qu(?:'|’)est ce que|quoi|"
    r"pourquoi|comment|qui|quand|ou)\b",

    r"(?:^|[|:–—-]\s*)"
    r"(?:voici pourquoi|ce que cela signifie)\b",

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
    # Evaluative and retrospective sports features.
    r"\b(?:proves?|shows?|demonstrates?)\b"
    r".{0,120}\b"
    r"(?:the real deal|why|what it takes|a point)\b",

    r"\b(?:verdict|takeaways?|lessons?|"
    r"what we learned|winners? and losers?)\b",
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


SPORTS_COMPETITIVE_SUBJECT_PATTERNS = (
    # Generic competitive-sports vocabulary. This branch is
    # intentionally sport-agnostic, so a sport does not need
    # to appear in a hardcoded allow-list.
    r"\b(?:sports?|sporting|athletes?|players?|teams?|clubs?|"
    r"competitors?|coaches?|managers?|captains?|squads?|"
    r"federations?|associations?|stadiums?|tournaments?|"
    r"championships?|leagues?|cups?|matches?|games?|medals?|"
    r"podiums?|finals?|semi[ -]?finals?|seasons?|fixtures?|"
    r"friendly|friendlies|transfers?|signings?|loans?|"
    r"internationals?|champions?|medalists?|rookies?|stars?|"
    r"riders?|drivers?|fighters?|racers?|skaters?|golfers?|"
    r"judokas?|boxers?|wrestlers?|swimmers?|cyclists?|"
    r"runners?|gymnasts?|shooters?|bowlers?|batters?|batsmen|"
    r"strikers?|defenders?|midfielders?|goalkeepers?)\b",

    # Competition structures and scoring terms also provide
    # sport evidence when the title names only an athlete
    # or club.
    r"\b(?:goals?|wickets?|runs?|home runs?|homers?|"
    r"touchdowns?|tries|sets?|rounds?|bouts?|heats?|relays?|"
    r"laps?|pole position|grid|drafts?|trades?|contracts?|"
    r"grand prix|open)\b",

    # Common sport names improve recall, but they supplement
    # the generic branches above and do not form a whitelist.
    r"\b(?:football|soccer|cricket|tennis|badminton|"
    r"basketball|hockey|baseball|rugby|golf|athletics|"
    r"judo|boxing|wrestling|swimming|cycling|gymnastics|"
    r"archery|shooting|weightlifting|rowing|fencing|squash|"
    r"volleyball|handball|kabaddi|bowls|skating|skiing|sumo|"
    r"table tennis|motorsport|formula 1|formula one|f1|"
    r"motogp|horse racing|equestrian|jockey)\b",

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
    # Direct results, personnel decisions, transfers and
    # other time-bound sporting developments.
    r"\b(?:wins?|won|victory|loses?|lost|loss|"
    r"beat(?:s|en)?|defeat(?:s|ed)?|draws?|scores?|"
    r"qualif(?:y|ies|ied)|advances?|eliminat(?:e|es|ed)|"
    r"gold|silver|bronze|medals?|podium|record|title|"
    r"champion|clean sweep|signs?|signed|signing|"
    r"bids?|interest|approach|target|joins?|joined|loan|"
    r"appoint(?:s|ed)?|named|launch(?:es|ed)?|"
    r"begins?|starts?|cancel(?:s|led|ed)?|"
    r"postpon(?:e|es|ed)|injur(?:y|ies|ed)|"
    r"suspend(?:s|ed)?|ban(?:s|ned)?|retir(?:e|es|ed)|"
    r"returns?|set for|secures?|breaks?|dies?|death)\b",

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


def sports_development_relevant(
    article: dict,
) -> bool:
    # Use only the headline and description. Long article
    # bodies often mention unrelated sports or countries.
    title_and_description = " ".join(
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

    return bool(
        matches(
            title_and_description,
            SPORTS_COMPETITIVE_SUBJECT_PATTERNS,
        )
        and matches(
            title_and_description,
            SPORTS_COMPETITIVE_DEVELOPMENT_PATTERNS,
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
    "za": (
        "South Africa",
        "South African",
    ),
}


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


def country_relevant(
    article: dict,
    country_code: str,
    country_name: str,
    *,
    topic: str = "",
    category: str = "",
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
                re.findall(
                    r"(?<!\w)"
                    + re.escape(value)
                    + r"(?!\w)",
                    text,
                    flags=re.I | re.UNICODE,
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

        if (
            (
                other_title_hits
                or other_country_title_hits
            )
            and not requested_title_hits
            and not sports_description_hits
        ):
            return False

        if requested_title_hits:
            return True

        # A domestic competition or governing-body phrase,
        # such as Premier League or Scottish Rugby, is strong
        # country evidence in the description.
        if sports_description_hits:
            return True

        if other_description_hits:
            return False

        # One passing location mention such as
        # "in Glasgow, Scotland" is insufficient.
        #
        # This blocks Australian and Canadian Commonwealth
        # Games stories from becoming Scotland headlines.
        return base_description_hits >= 2


    # Normal countries prefer direct title/description
    # evidence. For a verified sporting development, one
    # country or demonym mention in the body is sufficient:
    # sports headlines often name only the athlete or club in
    # the title and say "Japanese", "Indian", "German", etc.
    # once in the article body.
    body_country_hits = (
        base_content_hits
        + sports_content_hits
    )

    return bool(
        base_title_hits
        or base_description_hits
        or sports_title_hits
        or sports_description_hits
        or (
            sports_request
            and body_country_hits >= 1
            and sports_development_relevant(
                article
            )
        )
        or body_country_hits >= 2
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


def _conflicting_entities(
    first: str,
    second: str,
) -> bool:
    first_entities = _named_entities(
        first
    )

    second_entities = _named_entities(
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
        and len(first_only) <= 2
        and len(second_only) <= 2
    )


def near_duplicate(
    first: str,
    second: str,
) -> bool:
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
        _named_entities(first)
        & _named_entities(second)
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

    if appointment_duplicate:
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
            article
        )
    ):
        return "not_sporting_development"

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
                article
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