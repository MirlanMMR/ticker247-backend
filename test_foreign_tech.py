# -*- coding: utf-8 -*-
"""Заявление зарубежной технологической компании на «Местных» → «Интересное» (журнал J44, 15.10.2026).

Случай: «Anthropic предупреждает: ИИ скоро начнет сам копироваться и выходить за пределы
дата-центров» (Knews.kg) лежало на «Местных» Кыргызстана без инфоповода: заявление компании о
технологии, решения и своей страны нет. Владелец: «может, в Интересное?». Тест — на класс:
компания другой страны × дом × язык; плюс защиты (своя компания, событие, дом назван).
"""
import contextlib
import io
import sys

from curious import is_curious_content, tech_statement_country
from topic_country import final_foreign_tech_guard

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


def card(title, topic="tech/ai", **kw):
    return {"title": title, "summary": kw.pop("summary", ""), "scope": "local", "category": "TECH",
            "topic": topic, "source": "x", **kw}


def run(x, home):
    with contextlib.redirect_stdout(io.StringIO()):
        final_foreign_tech_guard([x], "xx", home)
    return x


# тот самый случай
x = run(card("Anthropic предупреждает: ИИ скоро начнет сам копироваться и выходить за пределы дата-центров"), "KG")
check("Anthropic у Кыргызстана → Интересное", x.get("interesting") is True)
check("слово «предупреждает» не делает её бедой", is_curious_content(x))

# класс: компания другой страны × дом × язык
for title, home, mark in [
    ("OpenAI CEO says AI will replace most jobs within five years", "MX", True),
    ("Google warns that AI agents may act on their own", "BR", True),
    ("Microsoft advierte que la IA superará a los humanos", "FR", True),
    ("Nvidia prevê que a demanda por chips dobrará", "KG", True),
    ("Meta craint que l'IA devienne incontrôlable", "KG", True),
    ("Huawei says its chips will match US rivals", "US", True),
    ("Samsung warns of weaker chip demand", "US", True),
    ("Mistral prévoit un nouveau modèle", "US", True),
]:
    check(f"{home}: {title[:44]}", (run(card(title), home).get("interesting") is True) == mark)

# своя компания — не чужая
for title, home in [("OpenAI CEO says AI will replace most jobs", "US"), ("Google warns of AI risks", "US"),
                    ("Mistral prévoit un nouveau modèle", "FR"), ("Samsung warns of weaker chip demand", "KR")]:
    check(f"своя: {home} {title[:36]}", not run(card(title), home).get("interesting"))

# не заявление — событие, остаётся новостью
check("запуск продукта — событие", not run(card("Google выпустила новую версию Gemini"), "KG").get("interesting"))
check("покупка — событие", not run(card("Microsoft купила стартап за $2 млрд"), "KG").get("interesting"))
# не про технологию по разметке ИИ
check("тема не tech — не трогаем", not run(card("Tesla warns of recall", topic="auto", category="AUTO"), "KG").get("interesting"))
# дом назван — это про нас
check("дом назван — остаётся", not run(card("Anthropic предупреждает: в Бишкеке откроют центр"), "KG").get("interesting"))
# защиты полок
for k, v in [("scope", "world"), ("bridge", True), ("vital", True), ("category", "URGENT")]:
    y = run(card("Anthropic предупреждает: ИИ опасен", **{k: v}), "KG")
    check(f"{k}={v}: не трогаем", not y.get("interesting"))
# проверка содержания: настоящая беда в заголовке остаётся бедой
check("беда в заголовке — не любопытное", not is_curious_content(card("Anthropic предупредила: погибли двое после сбоя")))
check("ведомство: предупреждение МЧС — не любопытное", not is_curious_content(card("МЧС предупреждает о сильном ветре", topic="")))
check("tech_statement_country: страна компании", tech_statement_country(card("Huawei says new chips are ready")) == "CN")
check("tech_statement_country: не заявление", tech_statement_country(card("Huawei launches new chips")) is None)

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
