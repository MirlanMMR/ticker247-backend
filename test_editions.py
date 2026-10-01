# -*- coding: utf-8 -*-
"""Какие выпуски BBC идут в какой пул.

Случай не выдуман: русский пул 01.10.2026 — 13 материалов BBC из 79 (31%
мировой полки), среди них BBC Mundo, переведённый с испанского, рядом с BBC
Русской службой; в португальском пуле четыре материала Русской службы,
переведённой на португальский.
"""
import ast
import sys

from editions import EDITION_LANG, edition_belongs_in_pool

ok = fail = 0


def check(name, got, want=True):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}: получили {got!r}, ждали {want!r}")


# Семьи берём из настоящего fetch_news.py, а не из копии: проверка должна
# краснеть, если семью поменяли, а выпуску язык не записали. Импортировать сам
# файл нельзя (нужны сеть и библиотеки), поэтому читаем литерал.
def real_families():
    tree = ast.parse(open("fetch_news.py", encoding="utf-8").read())
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "PUBLISHER_FAMILIES"
                for t in node.targets):
            return ast.literal_eval(node.value)
    raise SystemExit("PUBLISHER_FAMILIES не найден в fetch_news.py")


F = real_families()


def pools_for(source):
    return [p for p in ("ru", "en", "es", "pt", "fr")
            if edition_belongs_in_pool(source, p, F)]


# ─── BBC: каждому пулу свой выпуск ──────────────────────────────────────
check("русскому читателю — Русская служба",
      edition_belongs_in_pool("BBC Русская служба", "ru", F))
check("русскому читателю не идёт Mundo",
      edition_belongs_in_pool("BBC Mundo", "ru", F), False)
check("русскому читателю не идёт Brasil",
      edition_belongs_in_pool("BBC Brasil", "ru", F), False)
check("русскому читателю не идёт английский выпуск",
      edition_belongs_in_pool("BBC World", "ru", F), False)

check("испанскому — Mundo", edition_belongs_in_pool("BBC Mundo", "es", F))
check("испанскому не идёт Русская служба",
      edition_belongs_in_pool("BBC Русская служба", "es", F), False)

check("португальскому — Brasil", edition_belongs_in_pool("BBC Brasil", "pt", F))
check("португальскому не идёт Русская служба (было 4 материала)",
      edition_belongs_in_pool("BBC Русская служба", "pt", F), False)
check("португальскому не идёт Mundo",
      edition_belongs_in_pool("BBC Mundo", "pt", F), False)

for s in ("BBC News", "BBC World", "BBC Sport"):
    check(f"английскому — {s}", edition_belongs_in_pool(s, "en", F))
check("английскому не идёт Mundo",
      edition_belongs_in_pool("BBC Mundo", "en", F), False)
check("английскому не идёт Русская служба",
      edition_belongs_in_pool("BBC Русская служба", "en", F), False)

# Французский: выпуска на его языке нет — остаются все, выбирать не из чего
check("французскому остаются все выпуски BBC",
      all(edition_belongs_in_pool(s, "fr", F) for s in EDITION_LANG))

# Каждый выпуск идёт ровно в один из пулов с родным выпуском (и во французский)
check("Русская служба: только ru и fr", pools_for("BBC Русская служба"), ["ru", "fr"])
check("Mundo: только es и fr", pools_for("BBC Mundo"), ["es", "fr"])
check("Brasil: только pt и fr", pools_for("BBC Brasil"), ["pt", "fr"])
check("BBC World: только en и fr", pools_for("BBC World"), ["en", "fr"])

# ─── Остальное не задето ────────────────────────────────────────────────
check("Reuters (не из семьи) идёт во все пулы",
      pools_for("Reuters"), ["ru", "en", "es", "pt", "fr"])
check("неизвестный источник идёт во все пулы",
      pools_for("Какой-то новый источник"), ["ru", "en", "es", "pt", "fr"])
check("семья без выпусков на разных языках не задета (G1 Globo)",
      pools_for("G1 Globo"), ["ru", "en", "es", "pt", "fr"])
check("новый источник «любопытного» не задет (Futura-Sciences)",
      pools_for("Futura-Sciences"), ["ru", "en", "es", "pt", "fr"])

# ─── Страховка от забытого языка ────────────────────────────────────────
missing = [s for s in F["bbc"] if s not in EDITION_LANG]
check("каждому выпуску BBC записан язык", missing, [])

print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
