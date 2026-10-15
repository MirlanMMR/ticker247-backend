# -*- coding: utf-8 -*-
"""Рубрика из списка вёрстки и потолок «важного» (журнал J39, J40, 15.10.2026).

Читатель рубрик не видит; рубрика нужна порядку внутри полки. Сервер отдавал WAR, SOCIETY,
«ECONOMY/JOBS», «SPORT/FOOTBALL» — приложение не знало их и клало в хвост полки по алфавиту.
Приоритет 2 стоял у 49 из 190 карточек en (cap_urgent снимал рубрику, но не приоритет).
"""
import contextlib
import io
import sys

from urgent_guard import (P2_CAP_PER_SCOPE, final_category_guard, layout_category, p2_excess)

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


for c, want in [("WAR", "WORLD"), ("SOCIETY", "NEWS"), ("EDUCATION", "NEWS"), ("ECONOMY/JOBS", "MONEY"),
                ("SPORT/FOOTBALL", "SPORT"), ("INCIDENTS/CRIME", "INCIDENTS"), ("SCIENCE/CLIMATE", "TECH"),
                ("HEALTH/MEDICINE", "HEALTH"), ("POLITICS", "POLITICS"), ("URGENT", "URGENT"),
                ("URGENT_LOCAL_ONLY", "URGENT_LOCAL_ONLY"), ("KG", "KG"), ("что-то новое", "NEWS"),
                ("", "NEWS"), (None, "NEWS"), ("sport/football", "SPORT")]:
    check(f"{c!r} → {want}", layout_category(c) == want)

items = [{"category": "SPORT/FOOTBALL", "priority": 0}, {"category": "WAR", "priority": 1},
         {"category": "CURRENCY", "priority": 0}, {"category": "TECH/AI", "priority": 0, "topic": "tech/ai"}]
with contextlib.redirect_stdout(io.StringIO()):
    final_category_guard(items, "fr")
check("подрубрика уходит в topic", items[0]["category"] == "SPORT" and items[0]["topic"] == "sport/football")
check("WAR → WORLD", items[1]["category"] == "WORLD" and "topic" not in items[1])
check("валюта не трогается", items[2]["category"] == "CURRENCY")
check("готовый topic не затирается", items[3]["category"] == "TECH" and items[3]["topic"] == "tech/ai")


def card(i, scope="local", cat="NEWS", prio=2, **kw):
    return {"title": f"t{i}", "scope": scope, "category": cat, "priority": prio, "publishedAt": 1000 + i, **kw}


# потолок: сверх N самых свежих на полку приоритет снижается; срочные, vital и выбор редактора не трогаем
many = [card(i) for i in range(12)]
urgent = card(100, cat="URGENT", publishedAt=1)
urgent["publishedAt"] = 1
vital = card(101, vital=True)
picked = card(102, isEditorCarousel=True)
world = [card(200 + i, scope="world") for i in range(3)]
items = many + [urgent, vital, picked] + world
with contextlib.redirect_stdout(io.StringIO()):
    final_category_guard(items, "en")
kept = [x for x in many if x["priority"] == 2]
check(f"на полке осталось ровно {P2_CAP_PER_SCOPE} двоек", len(kept) == P2_CAP_PER_SCOPE)
check("остаются самые свежие", {x["title"] for x in kept} == {f"t{i}" for i in range(12 - P2_CAP_PER_SCOPE, 12)})
check("сверх потолка — единица, а не ноль", all(x["priority"] == 1 for x in many if x not in kept))
check("срочная не тронута", urgent["priority"] == 2 and urgent["category"] == "URGENT")
check("vital не тронуто", vital["priority"] == 2)
check("выбор редактора не тронут", picked["priority"] == 2)
check("другая полка считается отдельно", all(x["priority"] == 2 for x in world))
check("повторный проход ничего не меняет", not p2_excess(items))

# карусель не пустеет: у es и fr рубрики URGENT нет, а двойки есть
es = [card(i, scope=s) for i, s in enumerate(["local"] * 5 + ["pool"] * 2 + ["world"] * 3)]
with contextlib.redirect_stdout(io.StringIO()):
    final_category_guard(es, "es")
check("малый пул — двойки на месте", sum(x["priority"] == 2 for x in es) == 10)

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
