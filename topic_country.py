"""Тема не из страны пула → «Мировые» (владелец, 08.10.2026).

«Чтобы новости про Америку от узбекских изданий не попадали в Новости из…»

Страну события ставит ИИ (event_where), но не у всех карточек: покрытие 27–58 %.
Когда её нет, остаётся только текст. Правило по заголовку: карточка полки
«Новости из» (scope=pool), если в ЗАГОЛОВКЕ названа страна/сила ВНЕ стран пула
(США, Китай, ЕС, Иран…), а ни одна страна пула в заголовке и начале текста не
названа, — мировая. «Узбекистан и США подписали…» остаётся: своя страна названа.
Страна вне пула — та, что не входит в POOL_COUNTRIES пула и не его родина.

Заголовок, а не текст: в тексте упомянуть Америку может любая местная новость.
"""
import re

from shelves import foreign_fate

# код → слова (подстроки, нижний регистр) и слова с границами (короткие)
_WORDS = {
    "US": ("сша", "америк", "трамп", "trump", "рубио", "rubio", "госдеп", "state department", "secretary of state", "вашингтон", "белый дом", "pentágono", "estados unidos",
           "états-unis", "etats-unis", "estados-unidos", "eua", "u.s.", "united states"),
    "CN": ("си цзиньпин", "xi jinping", "китай", "пекин", "китае", "china", "chine", "chinese", "chinês", "chino"),
    "EU": ("евросоюз", "брюссел", "еврокомисс", "european union", "union européenne",
           "unión europea", "união europeia", "bruxelles", "bruselas"),
    "VA": ("ватикан", "vatican", "vaticano", "папа римск", "папа лев", "pope", "papa leão", "papa leon", "papa león", "pape léon", "pope leo", "pontífice", "pontifice", "le pape", "el papa", "o papa"),
    "IL": ("израил", "israel", "israël", "сектор газа", "gaza", "hamas", "хамас"),
    "IR": ("иран", "iran", "irán", "tehran", "тегеран"),
    "UA": ("украин", "ukrain", "ucrania", "ucrânia", "kiev", "киев", "zelensk", "зеленск"),
    "TR": ("турци", "turkey", "turquie", "turquía", "turquia", "эрдоган", "erdoğan", "erdogan"),
    "JP": ("япони", "japan", "japon", "japón", "japão", "токио", "tokyo"),
    "KR": ("южной коре", "южная коре", "северной коре", "south korea", "corée du", "corea del"),
    "DE": ("германи", "germany", "allemagne", "alemania", "alemanha", "берлин"),
    "GB": ("британ", "britain", "british", "великобритан", "reino unido", "royaume-uni"),
    "FR": ("франци", "france", "francia", "frança", "париж", "macron", "макрон"),
    "RU": ("росси", "russia", "rusia", "rússie", "russie", "путин", "putin", "лавров", "lavrov", "кремл", "москв", "moscow"),
}
# у каждой страны пула — свои слова (для проверки «своя страна названа»)
_OWN = {
    "KZ": ('казахстан', 'kazakh', 'астан', 'алмат', 'токаев', 'тоқаев', 'tokayev'),
    "UZ": ('узбекистан', 'uzbek', 'ташкент', 'самарканд', 'мирзиёев', 'мирзиеев', 'mirziyoyev'),
    "TJ": ('таджикистан', 'tajik', 'душанбе', 'рахмон', 'rahmon'),
    "KG": ('кыргыз', 'киргиз', 'бишкек', 'kyrgyz', 'ош '),
    "BY": ('беларус', 'белорус', 'минск', 'лукашенко', 'lukashenko'),
    "AM": ('армени', 'ереван', 'пашинян', 'pashinyan'),
    "AZ": ('азербайджан', 'баку', 'алиев', 'aliyev'),
    "GE": ('грузи', 'тбилиси', 'кобахидзе', 'kobakhidze'),
    "MD": ('молдов', 'кишин', 'санду'),
    "TM": ('туркмен', 'ашхабад', 'бердымухамедов'),
    "RU": _WORDS["RU"],
    "GB": _WORDS["GB"] + ('лондон', 'london', 'downing street', 'даунинг'),
    "FR": _WORDS["FR"],
    "DE": _WORDS["DE"],
    "US": _WORDS["US"],
    "CN": _WORDS["CN"],
    "UA": _WORDS["UA"],
    "TR": _WORDS["TR"],
    "IE": ('ирланди', 'ireland', 'irlande', 'irlanda', 'dublin', 'dublín', 'дублин'),
    "CA": ('канад', 'canada', 'canadá', 'ottawa', 'оттава', 'toronto', 'торонто'),
    "AU": ('австрали', 'australia', 'canberra', 'канберра', 'sydney', 'сидней'),
    "NZ": ('новой зеланди', 'new zealand', 'wellington', 'веллингтон', 'auckland'),
    "IN": ('инди', 'india', 'inde', 'delhi', 'дели', 'mumbai', 'мумбаи'),
    "NG": ('нигери', 'nigeria', 'abuja', 'абуджа', 'lagos', 'лагос'),
    "ZA": ('южной африк', 'south africa', 'pretoria', 'претория', 'johannesburg', 'cape town'),
    "SG": ('сингапур', 'singapore'),
    "JM": ('ямайк', 'jamaica'),
    "ES": ('испани', 'spain', 'españa', 'espagne', 'madrid', 'мадрид'),
    "MX": ('мексик', 'mexico', 'méxico', 'mexique', 'ciudad de méxico', 'cdmx', 'мехико'),
    "AR": ('аргентин', 'argentin', 'buenos aires', 'буэнос-айрес'),
    "CO": ('колумби', 'colombia', 'bogotá', 'bogota', 'богота'),
    "PE": ('перу', 'peru', 'perú', 'pérou'),
    "CL": ('чили', 'chile', 'chili', 'santiago de chile', 'сантьяго'),
    "VE": ('венесуэл', 'venezuela', 'caracas', 'каракас'),
    "CU": ('кубинск', 'на кубе', 'кубы', 'cuba', 'la habana', 'havana', 'гавана'),
    "UY": ('уругва', 'uruguay', 'montevideo', 'монтевидео'),
    "BR": ('бразил', 'brazil', 'brasil', 'brésil', 'brasília', 'brasilia', 'бразилиа'),
    "PT": ('португал', 'portugal', 'lisboa', 'lisbon', 'лиссабон'),
    "AO": ('ангол', 'angola', 'luanda', 'луанда'),
    "MZ": ('мозамбик', 'moçambique', 'mozambique', 'maputo', 'мапуту'),
    "BE": ('бельги', 'belgi', 'belgique', 'bélgica'),
    "CH": ('швейцар', 'suisse', 'suiza', 'suíça', 'switzerland', 'genève', 'zurich', 'берн ', 'bern '),
    "TN": ('тунис', 'tunisie', 'túnez', 'tunisia', 'tunis '),
    "DZ": ('алжир', 'algérie', 'argelia', 'algeria', 'alger '),
    "HT": ('гаити', 'haïti', 'haiti', 'port-au-prince', 'порт-о-пренс'),
    "CD": ('конго', 'congo', 'rdc', 'kinshasa', 'киншаса'),
    "BJ": ('бенин', 'bénin', 'benin', 'cotonou', 'porto-novo', 'котону'),
    "SN": ('сенегал', 'sénégal', 'дакар', 'dakar'),
    "CI": ('кот-д', 'côte d', 'costa de marfil', 'абиджан', 'abidjan', 'yamoussoukro'),
    "MA": ('марокк', 'maroc', 'marruecos', 'morocco', 'rabat', 'рабат'),
    "CM": ('yaoundé', 'yaounde', 'яунде', 'douala'),
    "BF": ('ouagadougou', 'уагадугу'),
    "ML": ('bamako', 'бамако'),
    "NE": ('niamey', 'ниамей'),
    "TG": ('lomé', 'lome'),
    "GN": ('conakry', 'конакри'),
    "MG": ('antananarivo', 'madagascar', 'мадагаскар'),
    "GW": ('bissau', 'бисау'),
    "ST": ('são tomé', 'sao tome'),
    "TL": ('díli', 'dili', 'тимор', 'timor'),
    "LU": ('luxembourg', 'люксембург', 'luxemburgo'),
    "PY": ('asunción', 'asuncion', 'асунсьон'),
    "EC": ('quito', 'кито'),
    "GT": ('guatemala', 'гватемала'),
    "HN": ('tegucigalpa', 'гондурас'),
    "NI": ('managua', 'манагуа', 'никарагуа'),
    "PA": ('panamá', 'panama', 'панам'),
    "SV": ('san salvador', 'сальвадор'),
    "DO": ('santo domingo', 'доминикан'),
    "BO": ('боливи', 'bolivia', 'bolívia'),
    "CR": ('коста-рик', 'costa rica'),
}
_SHORT = {"US": re.compile(r"\bсша\b|\bus\b|\busa\b|\beua\b", re.I), "EU": re.compile(r"\bес\b|\beu\b|\bue\b", re.I)}


def _hit(code, text):
    if code in _SHORT and _SHORT[code].search(text):
        return True
    return any(w in text for w in _WORDS.get(code, ()))


def outside_in_title(title, space):
    """→ код страны вне пула, названной в заголовке, или None."""
    low = (title or "").lower()
    for code in _WORDS:
        if code in space:
            continue
        if _hit(code, low):
            return code
    return None


def names_own(text, space):
    low = (text or "").lower()
    for code in space:
        if any(w in low for w in _OWN.get(code, ())):
            return True
        if code in _WORDS and _hit(code, low):
            return True
    return False


def foreign_topic(item, space):
    """True: карточка полки «Новости из» говорит о стране вне пула, своей не называя."""
    if item.get("scope") != "pool" or item.get("bridge") or item.get("event_where"):
        return False
    code = outside_in_title(item.get("title"), space)
    if not code:
        return False
    head = f"{item.get('title','')} {str(item.get('summary',''))[:300]}"
    return not names_own(head, space)


def final_foreign_topic_guard(items, lang, space):
    moved, dropped, kept = [], [], []
    for x in items:
        if foreign_topic(x, space):
            if foreign_fate(x) == "world":
                x["scope"] = "world"
                moved.append(x)
            else:
                dropped.append(x)       # масштаб не мировой — чужое дело, в ленте не нужно
                continue
        kept.append(x)
    if moved:
        print(f"  🌎 Чужая тема с «Новости из» в «Мировые» [{lang}]: {len(moved)}")
        for x in moved[:5]:
            print(f"       · {x.get('source','?')}: {(x.get('title') or '')[:64]}")
    if dropped:
        print(f"  🚮 Чужая тема, масштаб не мировой — снята [{lang}]: {len(dropped)}")
        for x in dropped[:5]:
            print(f"       · {x.get('source','?')}: {(x.get('title') or '')[:64]}")
    return kept


# ─── «Местное» с чужим событием ─────────────────────────────────────────────
#
# 09.10.2026: Knews.kg «Сооснователь Anthropic опасается, что создал нечто,
# обреченное на «вечные муки»» лежала на «Местных» (издание домашнее), хотя событие в
# США и про Кыргызстан в ней ни слова. Полку определяет страна события, а не издание.
# «Мост» (наши за границей: «трое кыргызстанцев задержаны в Москве», «Жапаров прилетел в
# Туркменистан») остаётся местным: в нём названа своя страна. Страна события вне
# пула и масштаб не мировой — чужое внутреннее дело (как foreign_fate); мировой масштаб —
# «Мировые»; событие в стране пула — «Новости из».
_HOME_EXTRA = {"KG": ("жапаров", "ташиев", "кабмин кр", "кр "), "US": (), "MX": (), "BR": (), "FR": ()}


def mentions_home(item, home):
    head = f"{item.get('title','')} {str(item.get('summary',''))[:300]}".lower()
    words = tuple(_OWN.get(home, ())) + _HOME_EXTRA.get(home, ())
    return any(w in head for w in words)


def _word_start(low, w):
    """Слово с НАЧАЛА слова: «алиев» не находится в «Талиева» и «Маматалиев» (фамилии
    кыргызстанцев), «иран» — в «Миранда». Основа с окончанием по-прежнему находится."""
    i = low.find(w)
    while i >= 0:
        if i == 0 or not low[i - 1].isalnum():
            return True
        i = low.find(w, i + 1)
    return False


def _hit_start(code, text):
    if code in _SHORT and _SHORT[code].search(text):
        return True
    return any(_word_start(text, w) for w in _WORDS.get(code, ()))


def local_event_country(x, space, home):
    """Страна события «местной» карточки: поле event_where от ИИ, а когда его нет (покрытие
    27–58 %) — страна или глава государства, названные в ЗАГОЛОВКЕ (15.10.2026).

    Случай: «Шавкат Мирзиёев подписал закон о пожизненном наказании для педофилов» лежало на
    «Местных» Кыргызстана: издание наше, а президент и страна чужие. Страж смотрел только
    event_where; у карточки без него ничего не срабатывало. Правило: чужая страна/глава
    названы в заголовке, а своя — нет (ни в заголовке, ни в начале текста) → событие там.
    """
    ev = (x.get("event_where") or "").strip().upper()
    if ev:
        return ev, False
    title = (x.get("title") or "").lower()
    for code in list(space) + [c for c in _WORDS if c not in space]:
        if code == home:
            continue
        if any(_word_start(title, w) for w in _OWN.get(code, ())) or _hit_start(code, title):
            return code, True               # страна выведена из текста, а не названа ИИ
    return "", False


# РЕГИОН — НЕ МОНОЛИТ, И ПРАВИЛО ОДНО ДЛЯ ВСЕХ ПУЛОВ (владелец, 15.10.2026: «если пишешь правило, то
# оно для всех пулов, то есть системное»). Слово региона в заголовке полку не решает: решают СТРАНЫ,
# в которых событие. «Technovation в Ташкенте … росту ЦА» — событие в Ташкенте: для узбеков местная,
# для остальной ЦА «Новости из…». «Рубио едет в ЦА» — по заголовку не ясно, куда; смотрим текст:
# «посетит Бишкек, Ташкент и Алматы» — местная для киргизов, узбеков, казахов и американцев,
# «Новости из…» для таджиков и туркмен, «Мировые» для читателей вне пула. То же для «Латинской
# Америки» (es), «Африки» (fr/pt), «Кавказа», «Ближнего Востока» на любом языке пула.
#   · места события — страны ИЗ РЕГИОНА, названные в заголовке (а если там нет — в начале текста);
#   · актёр — страна вне региона, названная в заголовке или лиде (США у Рубио, Франция у Макрона):
#     новость для её читателей тоже местная.
# Голое «ЦА» в рекламе — «целевая аудитория»; такие заголовки исключены
REGIONS = {
    "CENTRAL_ASIA": (re.compile(r"(?<![\w])ца(?![\w])|центральн\w*\s+ази|central\s+asia|asia\s+central|asie\s+centrale", re.I),
                     {"KZ", "KG", "UZ", "TJ", "TM"}),
    "CAUCASUS": (re.compile(r"кавказ|закавказ|caucas|c[áa]ucaso|caucase", re.I), {"AM", "AZ", "GE"}),
    "LATIN_AMERICA": (re.compile(r"латинск\w*\s+америк|latin\s+america|am[ée]rica\s+latina|latinoam[ée]rica|am[ée]rique\s+latine", re.I),
                      {"AR", "BO", "BR", "CL", "CO", "CR", "CU", "DO", "EC", "GT", "HN", "MX", "NI", "PA", "PE", "PY", "SV", "UY", "VE", "HT"}),
    "AFRICA": (re.compile(r"африк|africa|[áa]frica|afrique", re.I),
               {"DZ", "AO", "BJ", "BF", "CM", "CV", "CD", "CI", "GN", "GW", "MA", "MG", "ML", "MZ", "NE", "NG", "SN", "ST", "TG", "TN", "ZA"}),
    "MIDDLE_EAST": (re.compile(r"ближн\w*\s+восток|middle\s+east|medio\s+oriente|oriente\s+m[ée]dio|moyen-orient", re.I),
                    {"IL", "IR", "TR"}),
}
# «Южная Африка» — страна, а не регион
_SOUTH_AFRICA = re.compile(r"южн\w*\s+африк|south\s+africa|sud[áa]frica|afrique\s+du\s+sud|[áa]frica\s+do\s+sul", re.I)
_NOT_REGION = re.compile(r"аудитор|маркетинг|реклам|бренд|таргет", re.I)


def region_of(x):
    """→ (название региона, страны региона) или None."""
    t = _SOUTH_AFRICA.sub(" ", x.get("title") or "")
    if _NOT_REGION.search(t):
        return None
    for name, (rx, members) in REGIONS.items():
        if rx.search(t):
            return name, members
    return None


def space_wide(x):
    return region_of(x) is not None


def named_countries(text):
    """Коды стран, названные в тексте (страна, столица, глава государства) — с начала слова."""
    low = (text or "").lower()
    out = set()
    for code, words in _OWN.items():
        if any(_word_start(low, w) for w in words):
            out.add(code)
    for code in _WORDS:
        if _hit_start(code, low):
            out.add(code)
    return out


def region_event_countries(x):
    """Страны, для читателей которых событие региона местное: места (страны региона, названные в
    заголовке, а если их там нет — в начале текста) и актёры (страны вне региона, названные в
    заголовке или лиде: США у Рубио, Франция у Макрона)."""
    name_members = region_of(x)
    members = name_members[1] if name_members else set()
    title = x.get("title") or ""
    # Места ищем в лиде, а не по всему телу: «…больше, чем в метрополиях Латинской Америки» — это
    # сравнение, а не регион события (G1 São Paulo, 15.10.2026)
    body = str(x.get("_full") or x.get("_article") or x.get("summary") or "")[:400]
    places = named_countries(title) & members
    if not places:
        places = named_countries(body) & members
    actors = (named_countries(title) | named_countries(body[:300])) - members
    return places | actors, places


def _local_foreign_candidate(x, space, home):
    """→ (страна события | "", выведена ли из слов) для «местных» карточек с чужим событием."""
    if x.get("scope") != "local" or x.get("bridge") or x.get("interesting") or x.get("vital") \
            or x.get("category") in ("URGENT", "URGENT_LOCAL_ONLY") or mentions_home(x, home):
        return "", False
    ev, derived = local_event_country(x, space, home)
    if not ev or ev == home:
        return "", False
    return ev, derived


def final_local_foreign_guard(items, lang, space, home):
    """Полка «местной» карточки — по стране СОБЫТИЯ (владелец, 15.10.2026), а читателю её
    окончательно считает приложение: оно знает, откуда читают (страна события против страны читателя).
    Сервер отдаёт страну события (`event_where`, для региона — `event_countries`) и ставит полку
    относительно дома пула:
      · событие региона («ЦА»): страны из заголовка и текста → `event_countries`; дом назван → остаётся
        местной, страны пула → «Новости из…», иначе «Мировые»; стран нет → «Новости из…»;
      · страна события в пуле → «Новости из…»; масштаб «мир» → «Мировые»;
      · чужая держава вне пула: слова в заголовке без вердикта ИИ → «Мировые»; вердикт ИИ про
        «чужое мелкое» → снимаем, как раньше (J23)."""
    moved, dropped, kept = [], [], []
    for x in items:
        # Регион обрабатываем, когда в ЗАГОЛОВКЕ назван кто-то (страна, столица, глава государства,
        # папа): иначе слово региона — лишь сравнение («самый… среди метрополий Латинской Америки»)
        if x.get("scope") == "local" and not x.get("interesting") and not x.get("vital") \
                and x.get("category") not in ("URGENT", "URGENT_LOCAL_ONLY") and space_wide(x) \
                and named_countries(x.get("title") or ""):
            cs, places = region_event_countries(x)
            if places:
                x["event_countries"] = ",".join(sorted(cs))
            else:
                x["space_wide"] = True              # стран региона назвать нельзя; актёры — в event_countries
                if cs:
                    x["event_countries"] = ",".join(sorted(cs))
            if home not in cs:
                x["scope"] = "pool" if (not places or cs & set(space)) else "world"
                moved.append(x)
            kept.append(x)
            continue
        ev, derived = _local_foreign_candidate(x, space, home)
        if ev:
            if x.get("scale") == "world":
                x["scope"] = "world"
                moved.append(x)
            elif ev in space:
                x["scope"] = "pool"
                if derived:
                    x["event_where"] = ev
                moved.append(x)
            elif foreign_fate(x) == "world" or derived:
                x["scope"] = "world"
                moved.append(x)
            else:
                dropped.append(x)
                continue
        kept.append(x)
    if moved or dropped:
        print(f"  🏳️ «Местное» с чужим событием [{lang}]: полка исправлена {len(moved)}, снято {len(dropped)}")
        for x in (moved + dropped)[:6]:
            print(f"       · {x.get('source','?')} [{x.get('event_countries') or x.get('event_where') or ('ЦА' if x.get('space_wide') else '')}]: {(x.get('title') or '')[:60]}")
    return kept


# ─── Заявление должностного лица страны X о СВОИХ гражданах за рубежом → событие в стране X ───────
# (журнал J50, 15.10.2026; правило для всех пулов, владелец: «не должна быть новость местной в России»)
# Случай: «Глава МИД Кыргызстана впервые публично подтвердил принудительную вербовку
# кыргызстанцев в России на войну в Украине» (Азаттык) ИИ отнёс к России («вербовка идёт в
# России»), и у читателя из Москвы она лежала на «Местных». Но событие — ЗАЯВЛЕНИЕ киргизского
# министра о киргизских гражданах; Россия — лишь место, где эти граждане находятся. «Мост» из
# «Местного» Кыргызстана остаётся (там названа своя страна), а у москвича это новость о
# Кыргызстане, то есть «Новости из…».
# Правило узкое, чтобы не стать шире причины: ДОЛЖНОСТЬ страны X в начале заголовка + глагол
# заявления + слова о гражданах (граждане, мигранты, соотечественники, «-станцы»), а страну Y
# события ИИ назвал другой, и Y названа в заголовке как место («в России»). Визит и сами события
# («глава МИД прибыл в Москву», «задержаны в Москве») не затрагиваются.
_ROLE = (r"(?:глав\w+\s+(?:мид|правительств\w+|государств\w+)|министр\w*|мид\b|президент\w*|премьер\w*|посол\w*"
         r"|правительств\w+|парламент\w*|омбудсмен\w*|уполномоченн\w+|спикер\w*|"
         r"foreign\s+minister|minister|president|prime\s+minister|ambassador|government|"
         r"ministro|presidente|primer\s+ministro|embajador|gobierno|ministre|président|premier\s+ministre|ambassadeur|gouvernement|"
         r"governo|embaixador)")
_STATEMENT = re.compile(
    r"подтвердил|заявил|признал|сообщил|призвал|потребовал|предупредил|заверил|опроверг|назвал|рассказал|"
    r"отметил|объявил|пояснил|прокомментировал|"
    r"\b(?:says?|said|confirmed?|admitted?|admits|acknowledged?|called|warned|declared?|denied|denies)\b|"
    r"\b(?:dijo|afirm[óo]|confirm[óo]|reconoci[óo]|admiti[óo]|neg[óo])\b|"
    r"\b(?:a\s+confirm[ée]|a\s+d[ée]clar[ée]|a\s+reconnu|a\s+admis|confirmou|disse|admitiu|reconheceu)\b", re.I)
_CITIZENS = re.compile(
    r"граждан|мигрант|соотечественник|\w+станц\w+|кыргыз\w+|"
    r"\b(?:citizens|nationals|migrants|ciudadanos|migrantes|compatriotas|cidad[aã]os|ressortissants|migrants)\b", re.I)
_HEAD_ROLE = re.compile(r"^\W*" + _ROLE + r"\b", re.I)


def statement_country(title):
    """→ код страны X, если заголовок открывает должность страны X, а дальше заявление о гражданах."""
    t = (title or "").strip()
    m = _HEAD_ROLE.match(t)
    if not m:
        return None
    span = t[m.end():m.end() + 45]
    span = re.split(r"[,:;—–]|\s(?:в|во|на|при|по|из|от|для|in|on|at|en|à|no|na)\s", span)[0]
    codes = named_countries(span)
    if len(codes) != 1:
        return None
    rest = t[m.end():]
    if not (_STATEMENT.search(rest) and _CITIZENS.search(rest)):
        return None
    return next(iter(codes))


def final_statement_country_guard(items, lang, home):
    """Событие заявления должностного лица страны X о её гражданах — в стране X, а не там, где граждане."""
    fixed = []
    for x in items:
        if x.get("interesting") or x.get("vital") or x.get("category") in ("URGENT", "URGENT_LOCAL_ONLY"):
            continue
        y = (x.get("event_where") or "").strip().upper()
        code = statement_country(x.get("title"))
        if not code or not y or y == code:
            continue
        if y not in named_countries(x.get("title") or ""):
            continue                    # место ИИ не из заголовка — не трогаем
        x["event_where"] = code
        ec = [c for c in (x.get("event_countries") or "").split(",") if c and c != y]
        if ec:
            x["event_countries"] = ",".join(sorted(set(ec) | {code}))
        if code == home and x.get("scope") == "pool":
            x["scope"] = "local"
        fixed.append(x)
    if fixed:
        print(f"  🗣 Заявление должностного лица о своих гражданах: страна события исправлена [{lang}]: {len(fixed)}")
        for x in fixed[:5]:
            print(f"       · {x.get('source','?')} → {x.get('event_where')}: {(x.get('title') or '')[:64]}")
    return items


# ─── Издание страны X пишет о ней же, а место события ИИ поставил в другую страну (J51, 15.10.2026) ─────
# Владелец: «смотри на издание, оно кыргызское; для москвича пусть местные новости будут от местных
# изданий». «Кыргызстан вошёл в число стран научного сотрудничества с АлтГУ» (Вечерний Бишкек): издание
# кыргызское, своя страна названа в заголовке, а страна «места» (АлтГУ — вуз в России) в заголовке не
# названа. Событие ИИ назвал российским, и у москвича это были «Местные».
# Правило узкое: издание страны X (по списку изданий), в заголовке названа X, а страна Y события в
# заголовке НЕ названа → событие X. Если Y названа («Глава МИД прибыл в Москву», «Кыргызстан и Узбекистан
# подписали…») — решение ИИ не трогаем. Решение «Трамп в Америке для американца местное» не задето:
# там своя страна издания (Великобритания) в заголовке не названа.
def final_own_subject_guard(items, lang, source_country):
    fixed = []
    for x in items:
        if x.get("interesting") or x.get("vital") or x.get("bridge") \
                or x.get("category") in ("URGENT", "URGENT_LOCAL_ONLY"):
            continue
        y = (x.get("event_where") or "").strip().upper()
        if not y:
            continue
        try:
            own = (source_country(x) or "").strip().upper()
        except Exception:
            own = ""
        if not own or own == y:
            continue
        title = x.get("title") or ""
        low = title.lower()
        own_named = any(_word_start(low, w) for w in _OWN.get(own, ()))
        if not own_named:
            continue
        if y in named_countries(title):
            continue
        x["event_where"] = own
        ec = [c for c in (x.get("event_countries") or "").split(",") if c and c != y]
        if ec:
            x["event_countries"] = ",".join(sorted(set(ec) | {own}))
        fixed.append((y, x))
    if fixed:
        print(f"  🗞 Издание страны пишет о своей стране: страна события исправлена [{lang}]: {len(fixed)}")
        for y, x in fixed[:5]:
            print(f"       · {x.get('source','?')} {y}→{x.get('event_where')}: {(x.get('title') or '')[:60]}")
    return items


# ─── Заявление зарубежной технологической компании на «Местных» → «Интересное» ───────────
# (журнал J44, 15.10.2026; правило для всех пулов, список компаний — curious.TECH_COMPANIES)
def final_foreign_tech_guard(items, lang, home):
    """«Anthropic предупреждает: ИИ скоро…» от домашнего издания: решения, события и своей
    страны нет — в полосу «Интересное», с полки «Местных» она уходит (приложение убирает карточки
    полосы из полок). Своя компания (для США — Anthropic, OpenAI…) такой не считается."""
    from curious import tech_statement_country
    marked = []
    for x in items:
        if x.get("scope") != "local" or x.get("interesting") or x.get("bridge") or x.get("vital") \
                or x.get("category") in ("URGENT", "URGENT_LOCAL_ONLY") or mentions_home(x, home):
            continue
        co = tech_statement_country(x)
        if co and co != home:
            x["interesting"] = True
            marked.append(x)
    if marked:
        print(f"  🎲 Заявление зарубежной компании → «Интересное» [{lang}]: {len(marked)}")
        for x in marked[:5]:
            print(f"       · {x.get('source','?')}: {(x.get('title') or '')[:64]}")
    return items


# ─── Областное издание чужой страны (журнал J32, 09.10.2026) ──────────────
# Областные газеты (поле region: RU-PSK, MX-JAL, US-TX…) пишут для читателей своего
# региона. В пуле, где их страны нет, им не место: в испанской ленте стояли Псков и
# Оренбург (60.ru, 56.ru), переведённые на испанский, — «Travis Barker hospitalizado»
# из псковской газеты. Класс общий: любая область любой страны вне пула.
# Исключение — «мост» (граждане страны пула в чужой новости): его решает мост, не регион.
REGION_EXTRA = {"es": {"US"}}      # испанский для штатов США (выпуск 47): US — свои


_REGIONAL_NAME = re.compile(r"^\S+\.ru\s+[—–-]\s+\S")     # «14.ru — Якутск», «e1.ru — Екатеринбург»


def region_country(item):
    """Страна области. Поле region у части карточек теряется по дороге (14.ru — Якутск:
    у одной из трёх есть RU-SA, у двух нет, 09.10.2026), поэтому запасной признак — имя
    издания: «N.ru — Город» — это областная газета России."""
    r = (item.get("region") or "").strip()
    if r:
        return r.split("-")[0].upper()
    return "RU" if _REGIONAL_NAME.match(item.get("source") or "") else ""


def foreign_region(item, space, lang=""):
    """Областное издание страны, которой нет в пространстве пула."""
    c = region_country(item)
    return bool(c) and c not in set(space) | REGION_EXTRA.get(lang, set()) and not item.get("bridge")


def final_foreign_region_guard(items, lang, space):
    kept, dropped = [], []
    for x in items:
        (dropped if foreign_region(x, space, lang) else kept).append(x)
    if dropped:
        print(f"  🗺️ Областные издания чужой страны [{lang}]: снято {len(dropped)}")
        for x in dropped[:6]:
            print(f"       · {x.get('source','?')} [{x.get('region')}]: {(x.get('title') or '')[:60]}")
    return kept
