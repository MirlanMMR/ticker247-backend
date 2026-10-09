# -*- coding: utf-8 -*-
"""Областное издание чужой страны не остаётся в пуле без неё (журнал J32, 09.10.2026).

Случай: в испанской ленте стояли 60.ru (Псков) и 56.ru (Оренбург), переведённые на
испанский. Тест — на класс: любая область любой страны вне пространства пула.
"""
import sys

from topic_country import foreign_region, final_foreign_region_guard, region_country

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


ES = {"ES", "AR", "CO", "PE", "CL", "MX"}
RU = {"KZ", "UZ", "RU", "KG", "BY"}

check("страна региона", region_country({"region": "RU-PSK"}) == "RU" and region_country({}) == "")
check("Псков в испанском пуле — чужой", foreign_region({"region": "RU-PSK"}, ES, "es"))
check("Оренбург в испанском пуле — чужой", foreign_region({"region": "RU-ORE"}, ES, "es"))
check("Псков в русском пуле — свой", not foreign_region({"region": "RU-PSK"}, RU, "ru"))
check("Халиско в испанском — свой", not foreign_region({"region": "MX-JAL"}, ES, "es"))
check("штат США в испанском — свой (испанский для штатов)", not foreign_region({"region": "US-TX"}, ES, "es"))
check("штат США в русском пуле — чужой", foreign_region({"region": "US-TX"}, RU, "ru"))
check("штат США в португальском — чужой", foreign_region({"region": "US-TX"}, {"PT", "BR"}, "pt"))
check("нет региона — не трогаем", not foreign_region({}, ES, "es") and not foreign_region({"region": ""}, ES, "es"))
check("мост не режется регионом", not foreign_region({"region": "RU-PSK", "bridge": True}, ES, "es"))
# любая страна, любая область — класс, а не случай
for reg in ("DE-BY", "FR-IDF", "JP-13", "IN-MH", "BR-PR"):
    check(f"{reg} в испанском пуле — чужой", foreign_region({"region": reg}, ES, "es"))

items = [{"source": "60.ru", "region": "RU-PSK", "title": "a"}, {"source": "El Informador", "region": "MX-JAL", "title": "b"},
         {"source": "BBC Mundo", "title": "c"}]
import contextlib, io
with contextlib.redirect_stdout(io.StringIO()):
    out = final_foreign_region_guard(items, "es", ES)
check("страж: снят только чужой", [x["source"] for x in out] == ["El Informador", "BBC Mundo"])
check("страж: порядок и состав сохранены", len(out) == 2)

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
