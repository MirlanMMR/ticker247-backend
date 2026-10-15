# -*- coding: utf-8 -*-
"""«Местное» с чужим событием, когда страну события ИИ не назвал (журнал J42, 15.10.2026).

Случай: «Шавкат Мирзиёев подписал закон о пожизненном наказании для педофилов» лежало на
«Местных» Кыргызстана — издание наше, президент и страна чужие. final_local_foreign_guard
смотрел только event_where (покрытие 27–58 %), у карточки без него не срабатывал.
Тест — на класс: любая страна и глава государства из пространства пула × дом; плюс защиты
от ложных срабатываний (мост, «своя страна названа», выбор ИИ главнее текста).
"""
import contextlib
import io
import sys

from topic_country import final_local_foreign_guard, local_event_country

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


SPACE = {"AM", "AZ", "BY", "GE", "KZ", "MD", "RU", "TJ", "TM", "UZ", "KG"}


def card(title, **kw):
    return {"title": title, "summary": kw.pop("summary", ""), "scope": "local", "country": "KG",
            "source": "Kaktus.media", "category": "NEWS", **kw}


def run(items, home="KG", space=SPACE):
    with contextlib.redirect_stdout(io.StringIO()):
        return final_local_foreign_guard(items, "ru", space, home)


# тот самый случай
x = card("Шавкат Мирзиёев подписал закон о пожизненном наказании для педофилов")
out = run([x])
check("Мирзиёев без event_where → «Новости из»", out and out[0]["scope"] == "pool")
check("страна события проставлена", out[0].get("event_where") == "UZ")
check("карточка не пропала из ленты", len(out) == 1)

# класс: страна/глава государства в заголовке × соседи
for t, code in [("Токаев подписал указ о новых льготах", "KZ"), ("Лукашенко назначил нового министра", "BY"),
                ("Рахмон открыл новую станцию", "TJ"), ("Алиев принял посла", "AZ"),
                ("Пашинян провёл встречу в Ереване", "AM"), ("В Узбекистане запретили курение в кафе", "UZ"),
                ("Власти Казахстана ввели новые правила", "KZ"), ("Правительство Таджикистана утвердило бюджет", "TJ"),
                ("В Грузии начался суд над бывшим министром", "GE")]:
    out = run([card(t)])
    check(f"{code}: «{t[:36]}» → pool", out and out[0]["scope"] == "pool" and out[0].get("event_where") == code)

# своя страна названа — это «мост», остаётся местным
for t in ["Жапаров встретился с Мирзиёевым в Ташкенте", "Кыргызстан и Узбекистан подписали соглашение",
          "Бишкек и Алматы свяжет новая трасса", "Токаев прибыл в Бишкек с визитом"]:
    out = run([card(t)])
    check(f"мост остаётся: «{t[:40]}»", out and out[0]["scope"] == "local")
check("название в тексте, не в заголовке — не считается", run([card("Новый закон о педофилах принят", summary="Подписал Мирзиёев")])[0]["scope"] == "local")

# выбор ИИ главнее слов
check("ИИ назвал страну — берём её", run([card("Подписан закон", event_where="UZ")])[0]["scope"] == "pool")
check("ИИ назвал свою страну — слова не перебивают", run([card("Мирзиёев и Жапаров", event_where="KG")])[0]["scope"] == "local")

# защиты
for k, v in [("bridge", True), ("interesting", True), ("vital", True), ("category", "URGENT")]:
    check(f"{k}: не трогаем", run([card("Мирзиёев подписал закон", **{k: v})])[0]["scope"] == "local")
check("не «Местное» — не трогаем", run([card("Мирзиёев подписал закон", scope="world")])[0]["scope"] == "world")

# слова, выведенные из текста, карточку НЕ снимают (снимает только выбор ИИ)
out = run([card("Трамп подписал закон о тарифах")])
check("чужая держава по словам, масштаб неясен — не снимаем", len(out) == 1)

# local_event_country
check("local_event_country: ИИ главнее", local_event_country({"event_where": "uz", "title": "x"}, SPACE, "KG") == ("UZ", False))
check("local_event_country: из заголовка", local_event_country({"title": "Мирзиёев подписал"}, SPACE, "KG") == ("UZ", True))
check("local_event_country: пусто", local_event_country({"title": "Цены на мясо выросли"}, SPACE, "KG") == ("", False))

# другой дом: Мексика, соседи по «es»
ES = {"AR", "CO", "ES", "PE", "CL", "VE", "CU", "UY", "MX"}
out = run([card("Argentina aprueba nueva ley de alquileres", country="MX")], home="MX", space=ES)
check("es: Аргентина названа, Мексика нет → «Новости из»", out and out[0]["scope"] == "pool" and out[0]["event_where"] == "AR")
out = run([card("México y Argentina firman acuerdo", country="MX")], home="MX", space=ES)
check("es: названа и Мексика — мост, остаётся", out and out[0]["scope"] == "local")

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
