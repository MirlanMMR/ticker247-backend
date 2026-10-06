"""_is_home_source: домашнее издание определяется и по домену, и по SOURCE_COUNTRY.

06.10.2026: «AKIpress Эко» (eco.akipress.org) не было в LOCAL_DOMAINS, и его
кыргызские новости попали в «Мировые».
fetch_news.py не импортируем (нужны сеть и библиотеки): достаём функцию и
таблицы из файла по AST."""
import ast, sys

src = open("fetch_news.py", encoding="utf-8").read()
tree = ast.parse(src)
ns = {"POOL_CONFIG": {"ru": {"home_code": "KG"}, "en": {"home_code": "US"}}}
for node in tree.body:
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in ("LOCAL_DOMAINS", "SOURCE_COUNTRY") for t in node.targets):
        ns[node.targets[0].id] = ast.literal_eval(node.value)
    if isinstance(node, ast.FunctionDef) and node.name == "_is_home_source":
        exec(compile(ast.Module([node], []), "fetch_news.py", "exec"), ns)
f = ns["_is_home_source"]

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else: fail += 1; print(f"  ✗ {name}")

check("Kaktus по домену", f({"url": "https://kaktus.media/doc/1", "source": "Kaktus.media"}, "ru"))
check("AKIpress Эко: домена нет в списке, но источник записан за KG",
      f({"url": "https://eco.akipress.org/news:2545519", "source": "AKIpress Эко"}, "ru"))
check("казахстанский Tengrinews в русском пуле не домашний",
      not f({"url": "https://tengrinews.kz/x", "source": "Tengrinews"}, "ru"))
check("источник KG в американском пуле не домашний",
      not f({"url": "https://eco.akipress.org/n", "source": "AKIpress Эко"}, "en"))
check("неизвестный источник не домашний",
      not f({"url": "https://example.org/x", "source": "Какой-то сайт"}, "ru"))
print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
