# -*- coding: utf-8 -*-
"""Заявление должностного лица страны X о её гражданах за рубежом — событие в стране X (J50, 15.10.2026).

Случай: «Глава МИД Кыргызстана впервые публично подтвердил принудительную вербовку кыргызстанцев в
России на войну в Украине» лежала на «Местных» у читателя из Москвы. Тест — на класс: любая страна
пула × должность × заявление × граждане, и обратное — визит, место события и чужие заявления остаются."""
import contextlib
import io
import sys

from topic_country import statement_country, final_statement_country_guard

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


def card(title, where, scope="pool", **kw):
    return {"title": title, "event_where": where, "scope": scope, "source": "t", **kw}


def run(items, home="KG"):
    with contextlib.redirect_stdout(io.StringIO()):
        final_statement_country_guard(items, "ru", home)
    return items


# ── случай владельца ──
case = "Глава МИД Кыргызстана впервые публично подтвердил принудительную вербовку кыргызстанцев в России на войну в Украине"
check("случай: страна заявителя — Кыргызстан", statement_country(case) == "KG")
c = run([card(case, "RU")])[0]
check("случай: событие KG, а не RU", c["event_where"] == "KG")
check("случай: для дома пула (KG) — «Местные»", c["scope"] == "local")
c = run([card(case, "RU")], home="RU")[0]
check("дом пула другой — полку не трогаем, страна всё равно KG", c["event_where"] == "KG" and c["scope"] == "pool")

# ── класс: должность × страна × заявление × граждане ──
for t, want in (
    ("МИД Узбекистана заявил, что узбекистанцев в России не принуждают воевать", "UZ"),
    ("Министр иностранных дел Казахстана сообщил о гибели граждан Казахстана в Украине", "KZ"),
    ("Посол Таджикистана в России призвал мигрантов соблюдать закон", "TJ"),
    ("Президент Армении заявил о защите граждан Армении в Москве", "AM"),
    ("Омбудсмен Кыргызстана подтвердил задержание кыргызстанцев в Москве", "KG"),
    ("Kyrgyzstan foreign minister confirms forced recruitment of Kyrgyz citizens in Russia", None),   # без дома: страна из слов «Kyrgyz»
):
    got = statement_country(t)
    check(f"{t[:48]} → {want}", got == want or (want is None and got in (None, "KG")))

# ── обратное: не трогаем ──
for t in (
    "Глава МИД Кыргызстана прибыл в Москву для переговоров о гражданах",     # визит
    "Глава МИД Кыргызстана заявил о санкциях против России",                  # нет граждан
    "Задержаны трое кыргызстанцев в Москве",                                   # нет должности
    "Путин заявил, что мигранты нужны экономике",                              # нет должности из списка
):
    check(f"не правило: {t[:44]}", statement_country(t) is None)

# защиты: место ИИ не из заголовка, срочное и «интересное», событие уже в стране заявителя
c = run([card(case, "BY")])[0]
check("место ИИ не названо в заголовке — не трогаем", c["event_where"] == "BY")
c = run([card(case, "UA")])[0]
check("место ИИ — Украина, названная в заголовке: событие всё равно заявление", c["event_where"] == "KG")
c = run([card(case, "RU", category="URGENT")])[0]
check("срочное не трогаем", c["event_where"] == "RU")
c = run([card(case, "KG")])[0]
check("уже в стране заявителя — без изменений", c["event_where"] == "KG" and c["scope"] == "pool")
c = run([card(case, "RU", event_countries="RU,UA")])[0]
check("event_countries: чужая страна убрана, страна заявителя добавлена", set(c["event_countries"].split(",")) == {"UA", "KG"})

print(f"\n{ok} ✓, {fail} ✗")
sys.exit(1 if fail else 0)
