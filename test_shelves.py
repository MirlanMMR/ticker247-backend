"""Решение о полке по стране события (shelves.py) — на сегодняшних ошибках."""
import sys
from shelves import shelf_expected, verdict, parse_where_scale

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

# ─── Новые поля ИИ: where + scale ───────────────────────────────────────
w = lambda **k: dict(k)
check("мировой масштаб → world, где бы ни случилось",
      shelf_expected(w(scale="world", event_where="KG"), HOME, SPACE) == "world")
check("местный масштаб дома → local", shelf_expected(w(scale="local", event_where="KG"), HOME, SPACE) == "local")
check("Нарын на world при местном масштабе — подозрение (теперь однозначно)",
      verdict(w(scale="local", event_where="KG", scope="world"), HOME, SPACE) == "suspect")
check("региональный масштаб в Казахстане → pool", shelf_expected(w(scale="region", event_where="KZ"), HOME, SPACE) == "pool")
check("рядовое событие в Великобритании — чужое внутреннее дело: в ленте быть не должно",
      verdict(w(scale="local", event_where="GB", scope="world"), HOME, SPACE) == "suspect")
check("страна не названа, масштаб не мировой — проверить нельзя",
      verdict(w(scale="local", event_where=None, scope="world"), HOME, SPACE) == "unknown")

res = {"where": {"1": "kg", "2": "NP", "3": "-", "4": "Казахстан", "9": "US"},
       "world": [2], "region": [4, "x"]}
wh, sc = parse_where_scale(res, 4)
check("страна приводится к верхнему регистру", wh[0] == "KG")
check("«-» и не-ISO — это «страны нет» (None)", wh[2] is None and wh[3] is None)
check("масштаб: world, region, остальные local", sc[1] == "world" and sc[3] == "region" and sc[0] == "local")
check("номер вне списка новостей отбрасывается", 8 not in wh)
check("карточка, о которой ИИ не сказал where, остаётся без масштаба",
      parse_where_scale({"where": {"1": "KG"}}, 3)[1].get(1) is None)
check("мусорный ответ не роняет разбор", parse_where_scale(None) == ({}, {}) and parse_where_scale({"where": "x"}) == ({}, {}))

# «Новости из…» — только внутренние дела стран пула (владелец, 08.10.2026)
from shelves import pool_shelf_fix as PF, final_shelf_guard as FG
SP = {"KZ", "UZ", "TJ", "RU", "BY", "AM", "AZ", "GE", "MD", "TM"}
P = lambda **k: {"scope": "pool", **k}
check("внутреннее дело соседа остаётся", PF(P(country="UZ", event_where="UZ", scale="local"), SP) is None)
check("мировой масштаб → мировые (Уфа)", PF(P(country="RU", event_where="RU", scale="world"), SP) == "world")
check("событие вне пула (РИА о Стамбуле)", PF(P(country="RU", event_where="TR", scale="local"), SP) == "world")
check("Украина — вне пула (РБК о Донецке)", PF(P(country="RU", event_where="UA", scale="local"), SP) == "world")
check("места события нет, издание не из пула (ITC.ua)", PF(P(country="UA"), SP) == "world")
check("места нет и страны нет (iXBT)", PF(P(country=""), SP) == "world")
check("места события нет, издание из пула — остаётся", PF(P(country="KZ"), SP) is None)
check("родина пула в допустимых (Вечерний Бишкек)", PF(P(country="KG", event_where="KG"), SP | {"KG"}) is None)
check("не pool — не трогаем", PF({"scope": "local", "event_where": "TR"}, SP) is None)
check("мост не трогаем", PF(P(country="RU", event_where="TR", bridge=True), SP) is None)
from shelves import foreign_fate as FF
check("масштаб world → мировая", FF(P(scale="world")) == "world")
check("масштаб local → долой (чужое внутреннее дело)", FF(P(scale="local")) == "drop")
check("масштаб region → долой", FF(P(scale="region")) == "drop")
check("масштаба нет, весомая → мировая", FF(P(sourceCount=3)) == "world" and FF(P(priority=2)) == "world")
check("масштаба нет, лёгкая → долой", FF(P()) == "drop")
_it = [P(country="RU", event_where="TR", scale="local", source="s", title="дом в Стамбуле"),
       P(country="RU", event_where="IR", scale="world", source="s", title="удар по Ирану"),
       P(country="UZ", event_where="UZ", scale="local", source="s", title="Ташкент")]
_out = FG(_it, "ru", SP)
check("страж: мелкое чужое снято, мировое переехало, своё осталось",
      [(x["title"], x["scope"]) for x in _out] == [("удар по Ирану", "world"), ("Ташкент", "pool")])
# «своё о своём» не лежит в «Мировых» (AKIpress Эко, охотоведы Оша, 08.10.2026)
from shelves import world_to_home_fix as HF
W = lambda **k: {"scope": "world", **k}
check("AKIpress Эко: дом о доме → local", HF(W(country="KG", event_where="KG", scale="local"), "KG", SP) == "local")
check("сосед о соседе → pool", HF(W(country="UZ", event_where="UZ", scale="region"), "KG", SP) == "pool")
check("мировой масштаб остаётся", HF(W(country="KG", event_where="KG", scale="world"), "KG", SP) is None)
check("издание не о своей стране остаётся", HF(W(country="RU", event_where="TR", scale="local"), "KG", SP) is None)
check("без метки места — не трогаем", HF(W(country="KG", scale="local"), "KG", SP) is None)
check("интересное и мосты не трогаем", HF(W(country="KG", event_where="KG", scale="local", interesting=True), "KG", SP) is None
      and HF(W(country="KG", event_where="KG", scale="local", bridge=True), "KG", SP) is None)
_it2 = [W(country="KG", event_where="KG", scale="local", source="s", title="t")]
FG(_it2, "ru", SP | {"KG"}, home="KG")
check("страж возвращает домой", _it2[0]["scope"] == "local")
print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
