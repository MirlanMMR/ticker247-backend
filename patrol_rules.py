# -*- coding: utf-8 -*-
"""Правила дозора: что считать событием, о котором читателю надо знать (09.10.2026).

РЕШЕНИЕ ВЛАДЕЛЬЦА: «пять изданий из разных концов света — это если не срочно, то точно важно».

Раньше дозор поднимал любое событие, о котором писали три редакции за полтора часа, и за
8 часов находил пять «событий»: Нобелевскую премию, пожар в университете Бразилии, санкции
ЕС против Мадуро, возвращение астронавтки, заявление Трампа об Иране. Ни одно не срочное в
смысле «землетрясение, взрыв, бои», а по одному порогу «три» читателя будили бы каждые
полтора часа, и метка «срочно» обесценилась бы.

Теперь два уровня:
  · СРОЧНО  — не менее трёх редакций И слово беды в заголовке (землетрясение, взрыв, теракт,
              крушение, погибли…) на любом языке пулов;
  · ВАЖНО   — не менее ПЯТИ редакций из не менее чем ТРЁХ регионов мира (Северная Америка,
              Латинская Америка, Европа, СНГ, Ближний Восток, Африка, Азия, Океания): когда о
              событии пишут в Мексике, Франции и Бразилии, оно касается всех;
  · иначе   — событие только наблюдаем (в журнале, без права будить читателя).

Модуль чистый: без сети и без fetch_news (тест test_patrol_rules.py).
"""
import re

MIN_OUTLETS_URGENT = 3          # редакций, если в заголовке слово беды
MIN_OUTLETS_IMPORTANT = 5       # редакций для «важного»
MIN_REGIONS_IMPORTANT = 3       # регионов мира для «важного»

# Регионы мира по ISO-коду страны издания. Страна не названа (международное издание) —
# редакция считается, но регион не добавляет: вывод «разные концы света» не из воздуха.
_REGIONS = {
    "north_america": "US CA MX",
    "latin_america": "BR AR CO CL PE VE EC UY PY BO GT CR SV DO PA HN NI CU JM",
    "europe": "GB IE FR DE ES PT IT NL BE CH AT SE NO DK FI PL CZ HU GR RO BG RS HR SK SI LT LV EE IS UA",
    "cis": "RU BY KZ KG UZ TJ TM AM AZ GE MD",
    "middle_east": "TR IL SA AE QA KW BH OM JO LB IQ IR EG SY YE",
    "africa": "NG ZA KE GH ET TZ UG SN MA DZ TN AO MZ CV GW ST CG",
    "asia": "IN CN JP KR SG TH VN ID MY PH PK BD LK NP HK TW MN",
    "oceania": "AU NZ FJ PG TL",
}
REGION_OF = {c: reg for reg, codes in _REGIONS.items() for c in codes.split()}


# Международные издания, у которых бэкенд не знает страну (SOURCE_COUNTRY пуст): без этого
# Reuters, Al Jazeera, DW и Guardian вообще не давали региона, и событие, о котором написали
# во всех концах света, выглядело европейским (разбор 09.10.2026). Страна — штаб-квартира.
SOURCE_HOME = {
    "Reuters": "GB", "The Guardian": "GB", "Al Jazeera": "QA", "Deutsche Welle": "DE",
    "France 24": "FR", "Euronews": "FR", "RFI": "FR", "Bloomberg": "US", "AP News": "US",
    "Africanews": "CG", "CNA": "SG", "Straits Times": "SG", "SCMP": "HK", "NHK World": "JP",
    "ABC Australia": "AU", "Times of India": "IN", "NDTV": "IN", "The Hindu": "IN",
    "Anadolu": "TR", "Daily Sabah": "TR", "Jerusalem Post": "IL", "Times of Israel": "IL",
}


def outlet_country(source, country_from_backend):
    """Страна издания: из бэкенда, а если там пусто — из таблицы SOURCE_HOME."""
    return (country_from_backend or "").strip().upper() or SOURCE_HOME.get((source or "").strip(), "")


def region_of(country):
    """Регион мира по коду страны; None — страна неизвестна или не в таблице."""
    return REGION_OF.get((country or "").strip().upper())


# Слова беды: срочным делает событие не число редакций, а то, что случилось. Корни, регистр
# не важен; русский, английский, испанский, португальский, французский — языки наших пулов.
DISASTER = re.compile(
    # русский
    r"землетряс|цунами|взрыв|теракт|обрушен|крушен|катастроф|наводнен|паводк|оползн|пожар|"
    r"погиб|жертв|эвакуац|обстрел|переворот|заложник|стрельб|"
    # английский. Голое «attack» НЕ берём: «Trump says he won't attack Iran» — не беда
    r"earthquake|tsunami|explosion|blast|terror|bombing|massacre|"
    r"(?:plane|air|airliner|helicopter|train|bus|ship|ferry)\s+crash|crash\s+kills?|"
    r"collapse|flood|wildfire|killed|death toll|evacuat|shooting|hostage|coup\b|missile strike|"
    # испанский
    r"terremoto|sismo|explosi[oó]n|atentado|derrumbe|inundaci|incendio|muertos|muertes|murieron|"
    r"mueren|v[ií]ctimas|evacuaci|tiroteo|golpe de estado|"
    # португальский
    r"explos[aã]o|desabamento|enchente|inunda[cç][aã]o|inc[eê]ndio|mortos|morreram|"
    r"evacua[cç][aã]o|tiroteio|"
    # французский
    r"s[eé]isme|attentat|effondrement|inondation|incendie|morts\b|victimes|"
    r"évacuation|fusillade|coup d'[eé]tat",
    re.IGNORECASE,
)


def has_disaster_word(titles):
    return any(DISASTER.search(t or "") for t in titles)


def event_tier(families, regions, titles):
    """'urgent' | 'important' | None по числу редакций, регионов и словам беды.

    families — множество РЕДАКЦИЙ (не заметок); regions — множество регионов мира
    (None/пустые уже отброшены); titles — заголовки заметок события.
    """
    n = len(set(families))
    r = len({x for x in regions if x})
    if n >= MIN_OUTLETS_URGENT and has_disaster_word(titles):
        return "urgent"
    if n >= MIN_OUTLETS_IMPORTANT and r >= MIN_REGIONS_IMPORTANT:
        return "important"
    return None
