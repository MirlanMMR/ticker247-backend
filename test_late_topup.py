# -*- coding: utf-8 -*-
"""J79 (27.11.2026): добор до полной ленты — ПОСЛЕ последнего снятия.

ru 27.11: после редактора и его добора 103 карточки, в эфире 77; es 76→57, fr 68→45. Редакторский добор стоит
до поздних стражей (сторож читателя, ведомственное, полки), и заменить снятое ими было некем.
Замок: (1) добор не включается при малой нехватке и вне live; (2) считает снятое стражами и редактором, чтобы
не взять их снова; (3) в конвейере вызывается ПОСЛЕ первого прогона стражей и ДО пункта пропуска."""
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


def cards(n, start=0, **kw):
    return [{"url": f"u{start + i}", "title": f"t{start + i}", "scope": "world", **kw} for i in range(n)]


calls = []


def fake_refill_once(out, dropped, filtered, lang, leftover, max_items, apply_all):
    calls.append({"dropped": {x["url"] for x in dropped}, "seen": {x["url"] for x in filtered},
                  "apply_all": apply_all})
    return out + cards(3, start=900), 3


F._editor_refill_once = fake_refill_once
F.EDITOR_MODE, F.EDITOR_MD, F.AI_STOPPED = "live", "устав", False
after = cards(70)
survivors = after[:60]                                   # стражи сняли u60..u69
F.run_editor.last_dropped = cards(5, start=500)          # редактор снял ещё пять

# (1) условия включения
out, n = F.late_topup(survivors, "ru", cards(20, start=100), 80, after)
check("нехватка 20 > 6 — добор вызван", n == 3 and len(calls) == 1)
calls.clear()
out, n = F.late_topup(survivors, "ru", cards(20, start=100), 64, after)
check("нехватка 4 ≤ 6 — добора нет", n == 0 and not calls)
out, n = F.late_topup(survivors, "ru", [], 80, after)
check("запаса нет — добора нет", n == 0 and not calls)
F.EDITOR_MODE = "shadow"
out, n = F.late_topup(survivors, "ru", cards(20, start=100), 80, after)
check("редактор не в эфире — добора нет", n == 0 and not calls)
F.EDITOR_MODE = "live"
F.AI_STOPPED = True
out, n = F.late_topup(survivors, "ru", cards(20, start=100), 80, after)
check("ИИ остановлен — добора нет", n == 0 and not calls)
F.AI_STOPPED = False

# областные не считаются (потолок max_items — на национальных)
regional = survivors + cards(30, start=700, region="RU-X")
out, n = F.late_topup(regional, "ru", cards(20, start=100), 80, after)
check("областные не засчитываются в полноту (90 карточек, национальных 60 из 80)", n == 3 and len(calls) == 1)
calls.clear()

# (2) что считается снятым
out, n = F.late_topup(survivors, "ru", cards(20, start=100), 80, after)
c = calls[0]
check("снятое стражами (u60..u69) передано как снятое", {f"u{i}" for i in range(60, 70)} <= c["dropped"])
check("снятое редактором передано как снятое", {f"u{i}" for i in range(500, 505)} <= c["dropped"])
check("уцелевшие — не «снятые»", not ({f"u{i}" for i in range(60)} & c["dropped"]))
check("общая функция решений редактора, а не копия", c["apply_all"] is F._editor_apply_all)

# (3) порядок в конвейере
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_news.py"), encoding="utf-8").read()
pos = src.index
first_tail = pos("filtered = _tail_guards(filtered)\n        # J79")
check("стражи — одной функцией, до добора", pos("def _tail_guards(filtered):") < first_tail)
check("добор после первого прогона стражей", first_tail < pos("late_topup(filtered, lang, leftover, max_items, _after_editor)"))
check("после добора стражи идут заново", pos("late_topup(filtered, lang, leftover, max_items, _after_editor)")
      < src.index("filtered = _tail_guards(filtered)", pos("late_topup(filtered, lang, leftover, max_items, _after_editor)")))
check("добор до пункта пропуска и записи", pos("late_topup(filtered, lang, leftover, max_items, _after_editor)")
      < pos("border.control(filtered, lang, report=_BORDER_REPORT)"))
check("final_start_guard только внутри _tail_guards",
      src.count("filtered = final_start_guard(filtered, lang)") == 1
      and pos("def _tail_guards(filtered):") < pos("filtered = final_start_guard(filtered, lang)") < first_tail)
check("run_editor берёт решения у общей функции", "apply_all = _editor_apply_all" in src)

print(f"late_topup: {ok} ok, {fail} fail")
raise SystemExit(1 if fail else 0)
