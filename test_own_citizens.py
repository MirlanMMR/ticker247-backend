# -*- coding: utf-8 -*-
"""Беда своих граждан за границей — событие у граждан, а не в месте (J77, 27.11.2026).

Случай: «Более 250 паломников из Кыргызстана застряли в Саудовской Аравии» (Азаттык, event_where SA,
scale local) лежала в «Мировых» у читателя из Кыргызстана. Тест — на класс: любая страна пула ×
форма «люди страны» (демоним, «граждане X», «паломники из X») и обратное — мировой масштаб, чужие
граждане у читателя дома, нет людей в заголовке."""
import contextlib
import io

from topic_country import own_people_country, final_own_citizens_guard

ok = fail = 0
RU_SPACE = {"KZ", "UZ", "TJ", "RU", "BY", "AM", "AZ", "GE", "MD", "TM", "KG"}


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


def card(title, where, scale="local", scope="world", **kw):
    return {"title": title, "event_where": where, "scale": scale, "scope": scope, "source": "t", **kw}


def run(items, lang="ru", home="KG", space=RU_SPACE):
    with contextlib.redirect_stdout(io.StringIO()):
        final_own_citizens_guard(items, lang, home, space)
    return items


# ── случай владельца ──
case = "Более 250 паломников из Кыргызстана застряли в Саудовской Аравии"
c = run([card(case, "SA")])[0]
check("случай: событие KG, а не SA", c["event_where"] == "KG")

# ── класс: формы «людей страны» × страны пула ──
for t, want in (
    ("Кыргызстанцы застряли в аэропорту Дубая", "KG"),
    ("Граждане Кыргызстана пострадали при пожаре в Стамбуле", "KG"),
    ("Кыргызские паломники не могут вернуться из Мекки", "KG"),
    ("Узбекистанцев задержали в Каире", "UZ"),
    ("Студенты из Таджикистана застряли в Индии", "TJ"),
    ("Казахстанские туристы попали в аварию в Египте", "KZ"),
    ("Мигранты из Узбекистана погибли при пожаре в Дубае", "UZ"),
):
    got = own_people_country(t, sorted(RU_SPACE))
    check(f"{t[:46]} → {want}", got == want)
c = run([card("Студенты из Таджикистана застряли в Индии", "IN")])[0]
check("граждане страны пространства (не дом) → страна граждан", c["event_where"] == "TJ")

# ── обратное: не трогаем ──
check("мировой масштаб не трогаем (чемпион мира из Кыргызстана)",
      run([card("Спортсмен из Кыргызстана стал чемпионом мира в Японии", "JP", scale="world")])[0]["event_where"] == "JP")
check("чужие граждане там, где читатель дома — не трогаем",
      run([card("Узбекистанцы застряли в Бишкеке из-за снегопада", "KG")])[0]["event_where"] == "KG")
check("чужие граждане в стране пространства — не трогаем",
      run([card("Узбекистанцев задержали в Казахстане", "KZ")])[0]["event_where"] == "KZ")
check("людей страны в заголовке нет — не трогаем",
      run([card("Глава МИД Кыргызстана прибыл в Эр-Рияд", "SA")])[0]["event_where"] == "SA")
check("страна граждан вне пространства пула — не трогаем",
      run([card("Американцы застряли в Мекке", "SA")])[0]["event_where"] == "SA")
check("две страны в подлежащем — не гадаем",
      own_people_country("Кыргызстанцы и узбекистанцы застряли в Мекке", sorted(RU_SPACE)) is None)
check("«интересное» и мост не трогаем",
      run([card(case, "SA", interesting=True)])[0]["event_where"] == "SA"
      and run([card(case, "SA", bridge=True)])[0]["event_where"] == "SA")
check("уже верное место не меняется", run([card(case, "KG")])[0]["event_where"] == "KG")

# ── другие языки пулов (J33): люди дома пула ──
check("en: Americans stranded", own_people_country("Americans stranded in Saudi Arabia after Umrah", ["US", "GB"]) == "US")
check("es: mexicanos varados", own_people_country("Mexicanos varados en Arabia Saudita", ["MX", "ES"]) == "MX")
check("pt: brasileiros presos", own_people_country("Brasileiros ficam presos na Arábia Saudita", ["BR"]) == "BR")
check("fr: ressortissants français bloqués", own_people_country("Des ressortissants français bloqués en Arabie saoudite", ["FR"]) == "FR")
c = run([card("Americans stranded in Saudi Arabia after Umrah", "SA")], lang="en", home="US", space={"US", "GB", "CA"})[0]
check("en: событие US", c["event_where"] == "US")

print(f"own_citizens: {ok} ok, {fail} fail")
raise SystemExit(1 if fail else 0)
