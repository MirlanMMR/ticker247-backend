"""Журнал срочного (urgent_log.py): пишет только срочное/важное, без дублей, не падает на пустом."""
import json, os, tempfile, sys
import urgent_log as U
ok = fail = 0
def check(n, c):
    global ok, fail
    if c: ok += 1; print(f"  ✓ {n}")
    else: fail += 1; print(f"  ✗ {n}")
p = os.path.join(tempfile.mkdtemp(), "u.jsonl")
items = [{"url": "a", "category": "URGENT", "title": "t", "publishedAt": 1000},
         {"url": "b", "category": "NEWS", "priority": 2, "title": "важное"},
         {"url": "c", "category": "NEWS", "priority": 0}, {"category": "URGENT"}]
check("пишет срочное и важное, пропускает прочее и карточки без адреса", U.record(items, "ru", p, now_ms=61000) == 2)
check("повторный прогон не дублирует", U.record(items, "ru", p, now_ms=61000) == 0)
check("тот же адрес в другом пуле — отдельная запись", U.record(items[:1], "en", p, now_ms=61000) == 1)
rows = [json.loads(l) for l in open(p, encoding="utf-8")]
check("возраст в минутах считается от публикации", rows[0]["age_min"] == 1)
check("пустой список не падает", U.record([], "ru", p) == 0)
print(f"\nпройдено {ok}, провалено {fail}"); sys.exit(1 if fail else 0)
