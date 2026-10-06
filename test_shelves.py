"""Решение о полке по стране события (shelves.py) — на сегодняшних ошибках."""
import sys
from shelves import shelf_expected, verdict

HOME = "KG"
SPACE = {"KZ", "UZ", "TJ", "RU", "BY", "AM", "AZ", "GE", "MD", "TM"}   # без Украины (06.10.2026)
ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else: fail += 1; print(f"  ✗ {name}")

c = lambda **k: dict(k)
check("домашнее событие ждёт local", shelf_expected(c(event_country="KG"), HOME, SPACE) == "local")
check("Нарын (KG) на local — согласуется", verdict(c(event_country="KG", scope="local"), HOME, SPACE) == "ok")
check("Нарын (KG) в world — под подозрением (верно лишь для мирового масштаба)",
      verdict(c(event_country="KG", scope="world"), HOME, SPACE) == "suspect")
check("Казахстан ждёт pool", shelf_expected(c(event_country="KZ"), HOME, SPACE) == "pool")
check("Украина — не ближнее зарубежье: событие там — мировое",
      shelf_expected(c(event_country="UA"), HOME, SPACE) == "world")
check("война в Йемене на world — согласуется", verdict(c(event_country="YE", scope="world"), HOME, SPACE) == "ok")
check("событие во Франции на local — под подозрением",
      verdict(c(event_country="FR", scope="local"), HOME, SPACE) == "suspect")
check("мост — всегда local", shelf_expected(c(bridge=True, event_country="TR"), HOME, SPACE) == "local")
check("без страны события проверить нельзя", verdict(c(scope="world"), HOME, SPACE) == "unknown")
print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
