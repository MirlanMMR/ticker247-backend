# -*- coding: utf-8 -*-
"""«Срочно» вне «Местных» только с масштабом (журнал J38, 15.10.2026).

Случай: сель в Кашкадарье с одной жертвой (Gazeta.uz, scope=pool, URGENT_LOCAL_ONLY,
priority=2) попал в шторку, строку и карусель читателя в Бишкеке. Тест — на класс:
любая беда местного масштаба × любой язык × обе чужие полки; и обратное — настоящая
беда и свой дом остаются срочными.
"""
import contextlib
import io
import sys

from urgent_guard import final_urgent_guard, foreign_small_urgent

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


def card(title, scope="pool", cat="URGENT", prio=2, summary="", **kw):
    return {"title": title, "summary": summary, "scope": scope, "category": cat,
            "priority": prio, "source": "t", **kw}


# тот самый случай
sel = card("Пассажир Damas погиб в Кашкадарье во время схода селя", cat="URGENT_LOCAL_ONLY")
check("сель, URGENT_LOCAL_ONLY на полке соседей — снимается", foreign_small_urgent(sel))
check("то же в «Мировых»", foreign_small_urgent(card(sel["title"], scope="world", cat="URGENT_LOCAL_ONLY")))
check("«только дома» вне дома — всегда, о чём бы ни было", foreign_small_urgent(
    card("Землетрясение в Японии", scope="world", cat="URGENT_LOCAL_ONLY")))

# класс: беда района, один и тот же вывод на всех языках
small = [
    "Один человек погиб при сходе селя в Кашкадарье",
    "Паводок затопил улицу в соседнем городе, погиб мужчина",
    "Пожар в жилом доме, погибла женщина",
    "ДТП на трассе, погиб водитель",
    "One person killed as flood hits village",
    "Wildfire kills one near Portland",
    "Un muerto por inundación en un pueblo",
    "Incendio en un edificio deja un fallecido",
    "Acidente na rodovia deixa um morto",
    "Un mort dans l'incendie d'un immeuble",
]
for t in small:
    for scope in ("pool", "world"):
        check(f"{scope}: {t[:40]}", foreign_small_urgent(card(t, scope=scope)))

# обратное: масштаб остаётся срочным
big = [
    ("Землетрясение магнитудой 7,1 в Турции", "pool"),
    ("Теракт в метро, погибли 12 человек", "world"),
    ("Hurricane makes landfall in Florida", "world"),
    ("Floods kill dozens in Nepal", "world"),
    ("Наводнение унесло жизни 25 человек", "world"),
    ("Сель сошёл в Узбекистане, погибли 6 человек", "pool"),
    ("Terremoto sacude Chile", "pool"),
    ("Plane crash in Kazakhstan, 40 dead", "pool"),
]
for t, scope in big:
    check(f"остаётся срочным: {t[:40]}", not foreign_small_urgent(card(t, scope=scope)))
check("дом: сель на «Местных» остаётся", not foreign_small_urgent(card(small[0], scope="local")))
check("дом: URGENT_LOCAL_ONLY на «Местных» остаётся", not foreign_small_urgent(
    card(sel["title"], scope="local", cat="URGENT_LOCAL_ONLY")))
check("жизненно важное не трогаем", not foreign_small_urgent(card(small[0], scope="pool", vital=True)))
check("несрочное не трогаем", not foreign_small_urgent(card(small[0], cat="NEWS")))
check("число в тексте статьи (не в заголовке) считается",
      not foreign_small_urgent(card("Сель в Кашкадарье", scope="pool", summary="Погибли 7 человек.")))

# страж: снимает метку и приоритет, карточку не убирает
items = [dict(sel), card("Землетрясение в Японии", scope="world"), card(small[0], scope="local")]
with contextlib.redirect_stdout(io.StringIO()):
    out = final_urgent_guard(items, "ru")
check("страж: карточка осталась в ленте", len(out) == 3)
check("страж: категория снята", out[0]["category"] == "NEWS")
check("страж: приоритет не выше 1", out[0]["priority"] <= 1)
check("страж: настоящая беда не тронута", out[1]["category"] == "URGENT" and out[1]["priority"] == 2)
check("страж: дом не тронут", out[2]["category"] == "URGENT" and out[2]["priority"] == 2)

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
