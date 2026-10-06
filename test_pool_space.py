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
print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
