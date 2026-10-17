# -*- coding: utf-8 -*-
"""Повтор прошлых дней — twins.drop_reposts (журнал J55, 17.10.2026).

Случай: Азаттык «СМИ: девять казахстанцев вывезли из зоны боевых действий в Украине» — третий
материал одного развивающегося сюжета (семеро → девять), с тем же снимком; прежние к тому времени
вышли из ленты, и drop_twins (сравнивает карточки одного прогона) их не видел. Тест — на класс:
память × снимок × слова × адрес × срок.
"""
from twins import drop_reposts, remember_shown, REPOST_TTL_MS

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


H = 3_600_000
IMG = "https://gdb.rferl.org/abc-123/w1023_h574_q80.jpg"
IMG_OTHER = "https://gdb.rferl.org/zzz-999/w1023_h574_q80.jpg"


def card(url, title, img=IMG, cat="NEWS"):
    return {"url": url, "title": title, "imageUrl": img, "source": "Азаттык", "category": cat}


first = card("u1", "Семерых казахстанцев вывезли из зоны боевых действий в Украине")
mem = remember_shown({}, [first], 0)

# тот самый случай
third = card("u3", "СМИ: девять казахстанцев вывезли из зоны боевых действий в Украине")
kept, dropped = drop_reposts([third], mem)
check("тот же снимок, тот же сюжет, другой адрес, прежней уже нет в ленте — повтор", not kept and len(dropped) == 1)

# защиты
kept, _ = drop_reposts([card("u9", "Суд в Алматы вынес приговор по делу о пожаре")], mem)
check("тот же снимок, но другая новость (нет общих слов) — не повтор", len(kept) == 1)
kept, _ = drop_reposts([card("u9", "Казахстанцев на войне встретили в Воронеже семьи")], mem)
check("одно общее слово при общей заставке — не повтор (нужно ≥ 2)", len(kept) == 1)
kept, _ = drop_reposts([card("u3", third["title"], IMG_OTHER)], mem)
check("другой снимок — не повтор", len(kept) == 1)
kept, _ = drop_reposts([card("u3", third["title"], None)], mem)
check("снимка нет — не повтор (не по чему сверять)", len(kept) == 1)
kept, _ = drop_reposts([card("u1", first["title"])], mem)
check("та же карточка, дожившая до следующего прогона, — не повтор", len(kept) == 1)
kept, _ = drop_reposts([card("u3", third["title"]), first], mem)
check("прежняя карточка ещё в этой ленте — решает drop_twins, а не память", len(kept) == 2)
kept, _ = drop_reposts([card("u3", third["title"], cat="CURRENCY")], mem)
check("финансовые карточки не трогаем", len(kept) == 1)
kept, dropped = drop_reposts([third], {})
check("память пуста (первый прогон, нет связи) — ничего не снимаем", len(kept) == 1 and not dropped)

# срок памяти
old = remember_shown(mem, [], REPOST_TTL_MS + 1)
check("запись старше срока забывается", not old)
mem2 = remember_shown(mem, [third], H)
check("новые карточки дописываются, прежние остаются", set(mem2) == {"u1", "u3"})
check("повторная запись не меняет время первого показа", remember_shown(mem2, [first], 5 * H)["u1"]["at"] == 0)

# снятая карточка в память не попадает: пишем только то, что вышло
fresh = remember_shown({}, [], 0)
check("пустая запись безопасна", fresh == {})

print(f"пройдено {ok}, провалено {fail}")
raise SystemExit(1 if fail else 0)
