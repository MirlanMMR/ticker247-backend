# -*- coding: utf-8 -*-
"""Правило дотяжки: аннотация RSS — не текст статьи (09.10.2026).

Класс ошибки: порог «≥400 знаков — уже полный текст» при том, что RSS-аннотацию
режут до 600. Всё в зоне 400–600 оставалось без сверки со страницей. Тест — на
правило, а не на одну статью: ни одна новость в эфире, не взятая со страницы, не
освобождается от дотяжки по длине аннотации.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textcut import wants_page_body

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}")


def card(n, **kw):
    return {"url": "https://x.example/a", "summary": "а" * n, **kw}


# прежнее поведение (до отбора): порог по длине сохранён
check("до отбора: 120 знаков — тянем", wants_page_body(card(120)))
check("до отбора: 500 знаков — не тянем (общая очередь не раздувается)", not wants_page_body(card(500)))

# эфир: длина аннотации ничего не решает, решает fromPage
for n in (50, 281, 400, 449, 500, 544, 599, 600, 608, 900, 1400):
    check(f"эфир: аннотация {n} знаков без страницы — тянем",
          wants_page_body(card(n), annotations_too=True))
check("эфир: уже со страницы — не тянем повторно",
      not wants_page_body(card(500, fromPage=True), annotations_too=True))
check("эфир: пустая аннотация — тянем", wants_page_body(card(0), annotations_too=True))

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
