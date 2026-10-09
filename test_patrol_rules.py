# -*- coding: utf-8 -*-
"""Правила дозора (09.10.2026): «пять изданий из разных концов света — это если не срочно, то
точно важно». Тесты на реальных находках дозора за 8 часов и на классы ложных срабатываний."""
import sys

import patrol_rules as P

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


NA, LA, EU, CIS = "north_america", "latin_america", "europe", "cis"
five = {"a", "b", "c", "d", "e"}

# ── реальные находки дозора за 8 часов (журналы 07–09.10.2026) ──
check("Нобелевская премия: 9 редакций из 3 регионов → важно",
      P.event_tier({"El Financiero", "El Universal", "Franceinfo", "NYT", "Radio-Canada", "UPI", "bbc", "france24", "g1"},
                   {NA, EU, LA}, ["Canadian Anne Carson wins Nobel Prize in literature"]) == "important")
check("Трамп: «не нападёт на Иран» — 3 редакции, без беды → не срочно и не важно",
      P.event_tier({"a", "b", "c"}, {NA, EU}, ["Trump says he won't attack Iran until after midterm elections"]) is None)
check("санкции ЕС против Мадуро: 3 редакции → не поднимаем",
      P.event_tier({"a", "b", "c"}, {EU, LA}, ["EU suma nuevos cargos a Nicolás Maduro: represión y tortura"]) is None)
check("возвращение астронавтки: 3 редакции → не поднимаем",
      P.event_tier({"a", "b", "c"}, {EU}, ["Retour sur Terre de Sophie Adenot : l'astronaute française"]) is None)
check("пожар в университете (3 редакции, слово «incêndio») — срочно",
      P.event_tier({"a", "b", "c"}, {LA}, ["Reitor da UFPE estima prejuízo de incêndio em R$ 100 milhões"]) == "urgent")

# ── уровни ──
check("беда: три редакции хватает", P.event_tier({"a", "b", "c"}, {EU}, ["Earthquake of magnitude 6.1 hits Peru"]) == "urgent")
check("беда: две редакции мало", P.event_tier({"a", "b"}, {EU, NA}, ["Earthquake hits Peru"]) is None)
check("важно: пять редакций из трёх регионов", P.event_tier(five, {NA, EU, CIS}, ["Summit of leaders"]) == "important")
check("пять редакций, но только два региона → не важно", P.event_tier(five, {NA, EU}, ["Summit of leaders"]) is None)
check("пять редакций, регионы неизвестны → не важно (вывод не из воздуха)", P.event_tier(five, set(), ["Summit"]) is None)
check("пять редакций, регионы с пустыми значениями считаются без пустых", P.event_tier(five, {NA, EU, None, ""}, ["Summit"]) is None)
check("четыре редакции из четырёх регионов → ещё не важно", P.event_tier({"a", "b", "c", "d"}, {NA, EU, CIS, LA}, ["Summit"]) is None)
check("беда приоритетнее: «срочно», а не «важно»", P.event_tier(five, {NA, EU, LA}, ["Explosion at plant, 12 killed"]) == "urgent")

# ── слова беды на всех языках пулов ──
for lang, t in {"ru": "Землетрясение магнитудой 6 в Перу", "en": "Wildfire forces evacuation of 10,000",
                "es": "Terremoto de 7 grados sacude Chile", "pt": "Explosão em fábrica deixa mortos",
                "fr": "Attentat à Paris : plusieurs victimes"}.items():
    check(f"{lang}: слово беды опознано", P.has_disaster_word([t]))
check("катастрофа самолёта опознана", P.has_disaster_word(["Plane crash near Lima: 40 dead"]) and P.has_disaster_word(["Bus crash kills 12 in Peru"]))
# ── не беда ──
for t in ("Trump says he won't attack Iran", "Canadian Poet wins Nobel Prize", "Tesla stock crashes the party", "Bitcoin crash wipes out gains",
          "Le président reçoit les syndicats", "El presidente anuncia nuevo gabinete", "Prefeito inaugura a obra"):
    check(f"не беда: «{t[:35]}»", not P.has_disaster_word([t]))

# ── регионы мира ──
check("страны → регионы", P.region_of("MX") == NA and P.region_of("br") == LA and P.region_of("FR") == EU and P.region_of("KG") == CIS)
check("международное издание (страна пустая) регион не добавляет", P.region_of("") is None and P.region_of(None) is None)
check("неизвестная страна → None", P.region_of("ZZ") is None)
check("каждая страна в одном регионе", len(P.REGION_OF) == sum(len(v.split()) for v in P._REGIONS.values()))

# ── международные издания без страны в бэкенде получают дом ──
check("Reuters без страны → GB (Европа)", P.region_of(P.outlet_country("Reuters", "")) == EU)
check("Al Jazeera → Ближний Восток", P.region_of(P.outlet_country("Al Jazeera", "")) == "middle_east")
check("Straits Times → Азия", P.region_of(P.outlet_country("Straits Times", "")) == "asia")
check("страна из бэкенда главнее таблицы", P.outlet_country("Reuters", "CA") == "CA")
check("неизвестное издание без страны → пусто", P.outlet_country("Неизвестное", "") == "")

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
