# -*- coding: utf-8 -*-
"""Заявление должностного лица страны X о её гражданах за рубежом — событие в стране X (J50, 15.10.2026).

Случай: «Глава МИД Кыргызстана впервые публично подтвердил принудительную вербовку кыргызстанцев в
России на войну в Украине» лежала на «Местных» у читателя из Москвы. Тест — на класс: любая страна
пула × должность × заявление × граждане, и обратное — визит, место события и чужие заявления остаются."""
import contextlib
import io
import sys

from topic_country import statement_country, final_statement_country_guard, final_own_subject_guard

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

# ── J51: издание страны пишет о своей стране, место события не названо в заголовке ──
SRC = {"Вечерний Бишкек": "KG", "Kaktus.media": "KG", "Kun.uz": "UZ", "The Guardian": "GB"}
src = lambda x: SRC.get(x.get("source"), "")


def own(title, where, source="Вечерний Бишкек", **kw):
    c = {"title": title, "event_where": where, "scope": "local", "source": source, **kw}
    with contextlib.redirect_stdout(io.StringIO()):
        final_own_subject_guard([c], "ru", src)
    return c


check("случай АлтГУ: кыргызское издание, Кыргызстан в заголовке, место не названо → KG",
      own("Кыргызстан вошёл в число стран научного сотрудничества с АлтГУ", "RU")["event_where"] == "KG")
check("узбекское издание пишет об Узбекистане → UZ",
      own("Узбекистан вошёл в рейтинг стран по экспорту хлопка", "TJ", source="Kun.uz")["event_where"] == "UZ")
check("место названо в заголовке — решение ИИ не трогаем",
      own("Кыргызстан и Россия подписали соглашение", "RU")["event_where"] == "RU")
check("визит в Москву — не трогаем", own("Президент Кыргызстана прибыл в Москву", "RU")["event_where"] == "RU")
check("свой Ташкент назван → UZ не трогаем", own("Кыргызстан открыл выставку в Ташкенте", "UZ")["event_where"] == "UZ")
check("Трамп в Америке: издание GB, своя страна не названа — не трогаем",
      own("Трамп подписал указ", "US", source="The Guardian")["event_where"] == "US")
check("страна события уже своя — без изменений", own("Кыргызстан вошёл в рейтинг", "KG")["event_where"] == "KG")
check("издание не из списка — не трогаем", own("Кыргызстан вошёл в рейтинг", "RU", source="Неизвестное")["event_where"] == "RU")
check("срочное не трогаем", own("Кыргызстан объявил тревогу", "RU", category="URGENT")["event_where"] == "RU")
check("мост не трогаем", own("Кыргызстан помог гражданам в России", "RU", bridge=True)["event_where"] == "RU")
check("event_countries: чужая убрана, своя добавлена",
      set(own("Кыргызстан вошёл в число стран с АлтГУ", "RU", event_countries="RU,UZ")["event_countries"].split(",")) == {"UZ", "KG"})

print(f"\n{ok} ✓, {fail} ✗")
sys.exit(1 if fail else 0)
