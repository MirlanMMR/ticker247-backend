# -*- coding: utf-8 -*-
"""Сквозная проверка: начало текста в эфире — начало предложения.

Путь как в прогоне: контроль качества → редактор → последний взгляд.
Каждый шаг по отдельности «правильный», но 30.09.2026 их сумма дала
«гектаров. По данным…»: контроль стоял ДО редактора, редактор резал после.
Здесь нужно одно — что бы ни резали, итог не начинается с обрывка.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import editor as ED
import textcut as TC

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}")


def path(item, paras, verdict):
    """Весь путь одной карточки, как в прогоне: очистка текста → контроль
    качества (начало с целой фразы) → редактор → последний взгляд.
    Возвращает итоговый текст или None (снята)."""
    body = TC.strip_leading_service(item["summary"])
    body = TC.strip_title_echo(item["title"], body)
    body = TC.sentence_start(body)
    x = dict(item, summary=body)
    good, x, _ = ED.apply_verdict(x, verdict, paras, [])
    if not good:
        return None
    x = TC.final_start_guard([x], "ru")[0]
    return x["summary"]


TAIL = " Подробности сообщили в ведомстве, а также рассказали о планах на следующий год и о сроках."
CASES = {
    "тыс.": "Площадь лесов в Кыргызстане составляет 1 млн 273 тыс. гектаров. По данным министерства, она выросла." + TAIL,
    "руб.": "Цена выросла до 5 тыс. руб. за штуку, сообщили в магазинах. Продажи при этом упали." + TAIL,
    "т.д.": "Закупят бумагу, краски и т.д. для школ республики. Деньги выделят из бюджета." + TAIL,
    "г.": "Указ подписан 12 марта 2026 г. в Бишкеке. Он вступает в силу через месяц." + TAIL,
    "инициалы": "Премьер А. Н. Иванов заявил о планах. Подробности пока не раскрываются." + TAIL,
}
BAD = ("Все самое интересное в Telegram", "Подпишитесь на наш канал")

for name, body in CASES.items():
    for junk in BAD:
        item = {"title": "Новость", "summary": junk + "\n\n" + body, "source": "Kaktus", "url": "https://ex.kg/1",
                "category": "NEWS", "scope": "local", "language": "ru"}
        paras = [junk, body]
        out = path(item, paras, {"paragraphs": [2]})
        starts = out is not None and out.lstrip()[:1].isupper()
        check(f"{name} после «{junk[:14]}…»: начало — предложение", starts)
        if out is not None:
            check(f"{name}: текст не потерял первую фразу", out.startswith(body[:25]))

print(f"пройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
