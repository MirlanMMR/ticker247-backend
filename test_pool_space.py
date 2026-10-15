"""Состав языковых пространств пулов — POOL_COUNTRIES (решение владельца 06.10.2026)."""
import ast, sys
tree = ast.parse(open("fetch_news.py", encoding="utf-8").read())
space = next(ast.literal_eval(n.value) for n in tree.body
             if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "POOL_COUNTRIES" for t in n.targets))
ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else: fail += 1; print(f"  ✗ {name}")
check("Украины нет в ближнем зарубежье русского пула (война: только мировые новости)", "UA" not in space["ru"])
check("Казахстан и Узбекистан остались", {"KZ", "UZ"} <= space["ru"])
check("Беларусь осталась", "BY" in space["ru"])

# Соседи США по полке «Новости из…» — Канада и Мексика (приложение: NewsPlace.HOME_NEIGHBOURS["US"]).
# 15.10.2026: у читателя из США на полке была одна карточка — мексиканских источников в пуле не было
check("Мексика в английском пространстве (сосед США)", "MX" in space["en"])
src_country = next(ast.literal_eval(n.value) for n in tree.body
                   if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "SOURCE_COUNTRY" for t in n.targets))
text = open("fetch_news.py", encoding="utf-8").read()
def sources_of(code):
    return [s for s, c in src_country.items()
            if c == code and f'"source": "{s}"' in text and '"scope": "pool"' in text.split(f'"source": "{s}"')[1].split("}")[0]
            and '"lang": "en"' in text.split(f'"source": "{s}"')[1].split("}")[0]]
check("для соседей США — не меньше трёх канадских англоязычных источников полки", len(sources_of("CA")) >= 3)
check("для соседей США — есть мексиканский англоязычный источник", len(sources_of("MX")) >= 1)

print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
