# -*- coding: utf-8 -*-
"""strip_tail не съедает последнее целое предложение (журнал J27, 09.10.2026).

Класс ошибки: шаг снимал завершающую точку, а следующая проверка принимала
текст без точки за оборванный и отрезала ещё и предложение. Тест на правило:
текст, кончающийся целым предложением, остаётся как есть; служебный хвост
снимается; настоящий обрыв по-прежнему отступает к последнему целому.
"""
import os
import re
import sys
import types
from unittest.mock import MagicMock

for m in ("google.generativeai", "firebase_admin", "firebase_admin.credentials", "firebase_admin.db"):
    sys.modules[m] = MagicMock()
import google
google.generativeai = sys.modules["google.generativeai"]
os.environ.setdefault("GEMINI_API_KEY", "x")
os.environ["FIREBASE_SERVICE_ACCOUNT"] = "{}"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_news import strip_tail

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}")


LEAD = "Первое предложение достаточно длинное, чтобы пройти порог в восемьдесят знаков и ещё немного слов. "
for end in (".", "!", "?", "…", "»"):
    t = LEAD + "Второе предложение — последнее и целое" + end
    check(f"целое последнее предложение на «{end}» сохраняется", strip_tail(t) == t)

check("абзацы: концовка с точкой цела",
      strip_tail(LEAD + "\n\nВторой абзац кончается точкой.") == LEAD + "\n\nВторой абзац кончается точкой.")
check("хвост «Read more» снят, предложение целое",
      strip_tail(LEAD + "Второе целое предложение. Read more") == LEAD + "Второе целое предложение.")
check("хвост-подпись снят, предложение целое",
      strip_tail(LEAD + "Второе целое предложение. (Фото: Reuters)") == LEAD + "Второе целое предложение.")
check("слоями: «[…] Read more» снято",
      strip_tail(LEAD + "Второе целое предложение. […] Read more").endswith("Второе целое предложение."))
check("настоящий обрыв на полуслове по-прежнему отступает",
      strip_tail(LEAD + "Второе предложение оборвано на полусл") == LEAD.strip())

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
