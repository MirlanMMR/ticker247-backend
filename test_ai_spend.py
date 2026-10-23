# -*- coding: utf-8 -*-
"""Месячный счётчик расхода ИИ не теряет накопленное (журнал J64, 23.10.2026).

Случай: в логах прогонов «💳 Расход ИИ за 2026-10» показывал $1,25 в 05:02 и $0,07 в 08:02 — каждые
сутки. Шаг «Полки стран» (country_shelves.py) писал расход через flush_ai_spend(), не прочитав
итог из базы: AI_SPENT_MONTH был 0, и запись «usd = 0 + расход шага» затирала весь месяц. Потолок
AI_MONTHLY_BUDGET при этом смотрел на цифру, которая заведомо меньше настоящей.

Тест — на класс: любая запись расхода ПРИБАВЛЯЕТ к тому, что лежит в базе, а не к тому, что процесс
прочитал при старте (иначе теряется и при невзятом чтении, и при двух одновременных прогонах).
"""
import os
import sys
from unittest.mock import MagicMock

for m in ("google.generativeai", "firebase_admin", "firebase_admin.credentials", "firebase_admin.db"):
    sys.modules[m] = MagicMock()
import google
google.generativeai = sys.modules["google.generativeai"]
os.environ.setdefault("GEMINI_API_KEY", "x")
os.environ["FIREBASE_SERVICE_ACCOUNT"] = "{}"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch_news as F

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


class FakeRef:
    """Узел базы: достаточно get / update / transaction — то, чем пользуется счётчик."""

    def __init__(self, tree, path):
        self.tree, self.path = tree, path

    def _walk(self, create=False):
        node = self.tree
        for part in [p for p in self.path.split("/") if p]:
            if not isinstance(node, dict):
                return None
            if part not in node:
                if not create:
                    return None
                node[part] = {}
            node = node[part]
        return node

    def get(self):
        return self._walk()

    def update(self, data):
        node = self._walk(create=True)
        node.update(data)

    def transaction(self, fn):
        node = self._walk(create=True)
        new = fn(dict(node) if node else None)
        node.clear()
        node.update(new)
        return new


class FakeDb:
    def __init__(self, tree):
        self.tree = tree

    def reference(self, path):
        return FakeRef(self.tree, path)


MONTH = F._spend_month_key()


def process(tree, started_total_loaded=True):
    """Новый «процесс» (прогон или шаг): чистое состояние модуля, общая база."""
    F.db = FakeDb(tree)
    F.AI_SPENT_MONTH = 0.0
    F.AI_STOPPED = False
    F._SPEND_FLUSHED = 0.0
    F.TOKENS.update({"in": 0, "out": 0, "calls": 0, "fallback_in": 0, "fallback_out": 0})
    if started_total_loaded:
        F.load_ai_spend()


def spend(usd):
    """Прогон потратил usd (подменяем подсчёт по токенам) и записал расход."""
    F.current_run_cost = lambda: usd
    F.flush_ai_spend()


def stored(tree):
    return ((tree.get("ai_spend") or {}).get(MONTH) or {}).get("usd")


# ─── Случай 23.10: шаг не читал итог из базы ───
tree = {"ai_spend": {MONTH: {"usd": 1.25, "calls": 900}}}
process(tree, started_total_loaded=False)
spend(0.07)
check("запись без чтения итога прибавляет к базе, а не затирает месяц", abs(stored(tree) - 1.32) < 1e-6)
check("в памяти — то же, что в базе", abs(F.AI_SPENT_MONTH - 1.32) < 1e-6)

# ─── Обычный прогон: прочитал и записал по ходу несколько раз ───
tree = {"ai_spend": {MONTH: {"usd": 2.0, "calls": 10}}}
process(tree)
spend(0.10)
spend(0.25)
check("несколько записей по ходу прогона: +0,25 к 2,0, не +0,35", abs(stored(tree) - 2.25) < 1e-6)

# ─── Два прогона одновременно: каждый прочитал при старте одно и то же ───
tree = {"ai_spend": {MONTH: {"usd": 1.0, "calls": 0}}}
process(tree)
a_loaded = F.AI_SPENT_MONTH
process(tree)                                   # второй процесс стартовал, пока первый работает
spend(0.20)                                     # второй закончил раньше
F.AI_SPENT_MONTH = a_loaded                     # первый всё ещё помнит $1.00
F._SPEND_FLUSHED = 0.0
spend(0.10)
check("два одновременных прогона: обе записи учтены (1,0 + 0,2 + 0,1)", abs(stored(tree) - 1.30) < 1e-6)

# ─── Первая запись месяца ───
tree = {}
process(tree)
spend(0.05)
check("пустая база: первая запись создаёт счёт месяца", abs(stored(tree) - 0.05) < 1e-6)

# ─── Нулевая и отрицательная добавка базу не трогает ───
tree = {"ai_spend": {MONTH: {"usd": 3.0, "calls": 5}}}
process(tree)
spend(0.0)
check("нет расхода — нет записи", abs(stored(tree) - 3.0) < 1e-6)

# ─── Шаг «Полки стран» читает итог, чтобы потолок действовал и на него ───
src = open("country_shelves.py", encoding="utf-8").read()
check("country_shelves: итог месяца читается перед ИИ-работой",
      "fn.load_ai_spend()" in src and src.index("fn.load_ai_spend()") < src.index("fn.flush_ai_spend()"))

print(f"{ok} из {ok + fail} проверок")
sys.exit(1 if fail else 0)
