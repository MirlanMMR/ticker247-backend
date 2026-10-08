"""Пункт пропуска (border.py): фотороботы известных ошибок опознаются, чистое проходит."""
import sys, io, contextlib
import border

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print(f"  ✗ {name}")

PAD = "Россия нанесла удар по городам Украины, сообщили местные власти. " * 17
def run(items, lang="ru"):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        found = border.control(items, lang, report=[])
    return found, buf.getvalue()

# Фотороботы — реальные карточки, на которых мы обожглись (журнал, 08.10.2026)
bad = {
    "J1": dict(scope="pool", country="RU", event_where="TR", scale="local", title="На востоке Стамбула обрушился дом", summary="x"),
    "J2": dict(scope="world", country="KG", event_where="KG", scale="local", title="Депутат попросил улучшить условия охотоведов", summary="x"),
    "J3": dict(scope="world", title="Прилуки", summary=PAD + "Зеленский: «Удалось сбить только часть."),
    "J4": dict(scope="world", title="Прилуки", summary=PAD.strip() + "\n\nУдар по пятиэтажке в Прилуках"),
    "J5": dict(scope="world", title="т" * 130, summary="x"),
    "J8": dict(scope="world", title="t", summary="Автор фото, Getty Images. Текст."),
    "J9": dict(scope="world", title="t", summary="гектаров. По данным ведомства, лес горел. " * 5),
}
for code, item in bad.items():
    found, _ = run([item])
    check(f"{code} опознан", len(found.get(code, [])) == 1)

# Чистая карточка проходит
clean = dict(scope="local", country="KG", event_where="KG", scale="local",
             title="В Бишкеке сгорел рынок", summary="Пожар начался ночью. Пострадавших нет.")
found, out = run([clean])
check("чистое проходит", not any(found.values()) and "чисто" in out)

# Возврат закрытого класса — тревога ::error::, закрытого J5 нет
_, out = run([bad["J3"]])
check("закрытый класс вернулся → ::error::", "::error" in out and "J3" in out)
_, out = run([bad["J5"]])
check("открытый класс не поднимает тревогу", "::error" not in out)

# J11 — долей: одна скучная на полке — норма, много — нет
dull = lambda i: dict(scope="local", title=f"Служба провела совещание {i}", summary="x")
norm = lambda i: dict(scope="local", title=f"Пожар в доме {i}", summary="x")
found, _ = run([dull(0)] + [norm(i) for i in range(9)])
check("одна скучная — норма", not found["J11"])
found, _ = run([dull(i) for i in range(5)] + [norm(i) for i in range(5)])
check("половина полки скучная — флаг", len(found["J11"]) == 5)

# Каждый класс журнала имеет код, детектор или явную пометку
codes = [c for c, *_ in border.REGISTRY]
check("коды уникальны", len(codes) == len(set(codes)))

print(f"пройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
