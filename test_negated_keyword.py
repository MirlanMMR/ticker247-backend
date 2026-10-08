"""Слово беды в отрицании не делает новость срочной (09.10.2026, саженцы Kaktus)."""
import ast, re, sys

src = open("fetch_news.py", encoding="utf-8").read()
ns = {"re": re}
for n in ast.parse(src).body:
    if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "_NEGATION_BEFORE" for t in n.targets):
        exec(compile(ast.Module([n], []), "x", "exec"), ns)
    if isinstance(n, ast.FunctionDef) and n.name == "_kw_hit":
        exec(compile(ast.Module([n], []), "x", "exec"), ns)
hit = ns["_kw_hit"]

ok = fail = 0
def check(name, got, want):
    global ok, fail
    if got == want: ok += 1
    else: fail += 1; print(f"  ✗ {name}: получили {got}, ждали {want}")

check("саженцы не погибали — не беда", hit("погиб", "чтобы саженцы не погибали. активисты решили озеленить участок"), False)
check("никто не погиб — не беда", hit("погиб", "в результате пожара никто не погиб"), False)
check("погибли — беда", hit("погиб", "при пожаре погибли двое"), True)
check("не менее 5 погибли — всё равно беда", hit("погиб", "не менее 5 человек погибли при обрушении"), True)
check("не только погибли — всё равно беда", hit("погиб", "в авиаударе не только погибли люди, но и разрушены дома"), True)
check("ключ в начале слова по-прежнему", hit("град", "над ленинградом прошёл дождь"), False)
check("en: no one killed — не беда", hit("killed", "no one was killed in the fire"), False)
check("en: killed — беда", hit("killed", "three people killed in the crash"), True)
check("es: nadie murió — не беда", hit("murió", "nadie murió en el incendio"), False)
check("без света — собственный ключ остаётся", hit("без света", "дом остался без света на два дня"), True)

print(f"пройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
