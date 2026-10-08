"""Ведомственная скука на «Местных» (dull.py), 08.10.2026."""
import sys
from dull import is_dull, cap_dull, MIN_LOCAL

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print(f"  ✗ {name}")

c = lambda title, **k: dict(title=title, scope=k.pop("scope", "local"), category=k.pop("category", "NEWS"), **k)

# Сильная рутина — скучна и без названного субъекта
check("ремонтные работы", is_dull(c("На линии 500 кВ проводятся текущие ремонтные работы")))
check("консультации состоялись", is_dull(c("В Бишкеке состоялись кыргызско-британские консультации")))
check("визит главы государства", is_dull(c("Садыр Жапаров прилетел в Туркменистан")))
check("кыргызский: курулат", is_dull(c("Бишкекте 22 кабаттуу бизнес-борбор курулат")))
check("юбилей учреждения", is_dull(c("Больница отмечает 80-летний юбилей")))
# Слабая рутина — только с официальным субъектом
check("служба получила технику", is_dull(c("Лесная служба Минприроды получила планшеты, дроны и автомобили")))
check("министр проверил", is_dull(c("Министр обороны проверил воинские части на юге")))
check("без субъекта слабая рутина — не скука", not is_dull(c("Соседи получили письмо от почтальона")))
# Последствие для людей — не скука
check("арест — не скука", not is_dull(c("Министр проверил СИЗО: задержан охранник")))
check("штраф — не скука", not is_dull(c("Мэрия провела проверку и оштрафовала торговцев")))
check("отключение — не скука", not is_dull(c("Служба водоканала проводит ремонтные работы, воду отключат")))
check("срочное — не скука", not is_dull(c("Министерство провело совещание", category="URGENT")))
check("жизненно важное — не скука", not is_dull(c("Министерство провело совещание по эвакуации", vital=True)))
check("обычная новость", not is_dull(c("Супруга замначальника РОВД обвинила его в избиении")))

# Доля: не больше четверти, пол MIN_LOCAL
dull = [c(f"Служба провела совещание {i}", priority=0, publishedAt=i) for i in range(10)]
live = [c(f"Пожар в доме {i}", publishedAt=100 + i) for i in range(18)]
kept, gone = cap_dull(dull + live, "ru")
check("снято лишнее", len(gone) == 4 and len(kept) == 24)
check("снята самая лёгкая и старая", all(x["publishedAt"] < 4 for x in gone))
check("в других пулах не работает", cap_dull(dull + live, "en") == (dull + live, []))
check("мировые не трогаем", cap_dull([c("Служба провела совещание", scope="world")] * 5, "ru")[1] == [])
few = [c(f"Служба провела совещание {i}") for i in range(5)] + [c(f"Пожар {i}") for i in range(3)]
kept, gone = cap_dull(few, "ru")
check("пол: полка не опустеет", len(kept) >= min(len(few), MIN_LOCAL) or len(gone) == 0)
check("мосты не трогаем", cap_dull([dict(c("Служба провела совещание"), bridge=True)] * 8, "ru")[1] == [])

print(f"пройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
