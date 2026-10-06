"""Сверка опубликованной ленты с источником — мера качества Ticker 24/7.

Правило (CLAUDE.md проекта): качество карточки — это сверка со страницей издания,
а не впечатление. Скрипт берёт живую ленту пула, открывает страницу каждой
новости нашим же извлекателем (extract.py) и считает изъяны:

  · neg    — заголовок потерял или добавил отрицание («так и не нашли» → «так и
             нашли»). Сравнивается только если заголовок страницы на том же
             алфавите, что карточка (переведённые заголовки не сверить по словам)
  · short  — текст карточки короче половины того, что мы вправе показать
             (min(страница, KEEP_LIMIT)), хотя на странице материал ≥ 900 знаков
  · credit — вместо текста подпись к фото или служебная строка
  · lang   — родной язык (ky/kk/uz/tg) с чужой пометкой языка (ru)
  · scope  — своя новость пула лежит в «Мировых» (страна карточки = дом пула,
             полка world): AKIpress Эко с eco.akipress.org, 06.10.2026
  · twin   — второй экземпляр одной и той же истории в ленте (twins.py: тот же
             снимок, либо разные выпуски одной редакции)

Запуск:   python quality_audit.py [--pool ru] [--max-bad-percent 5] [--json]
Выход 1, если доля брака выше порога — для сравнения «до» и «после» правки.
Только чтение: ничего не пишет ни в базу, ни в репозиторий.
"""
import argparse
import concurrent.futures as cf
import html
import json
import re
import sys
import urllib.request

import ast

from extract import extract_article
from editions import EDITION_LANG
from native_lang import detect_native
from twins import drop_twins

DB = "https://ticker247-default-rtdb.asia-southeast1.firebasedatabase.app/news/{pool}/items.json"
KEEP_LIMIT = 1300
HOME = {"ru": "KG", "en": "US", "es": "MX", "pt": "BR", "fr": "FR"}
NEG = re.compile(r"\b(не|нет|ни|без|нельзя|not|no|never|sin|nunca|pas|jamais|não|nunca)\b", re.I)
CREDIT = re.compile(r"^\s*(автор фото|подпись к фото|image source|image caption|photo credit)", re.I)


def norm(t):
    return re.sub(r"\s+", " ", html.unescape(t or "")).strip()


def og_title(page):
    m = (re.search(r'property=["\']og:title["\'][^>]*content=["\']([^"\']+)', page)
         or re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:title', page))
    return norm(m.group(1)) if m else None


def script_of(t):
    cyr = len(re.findall(r"[а-яё]", t.lower()))
    lat = len(re.findall(r"[a-z]", t.lower()))
    return "cyr" if cyr > lat else "lat"


def check(x, pool="ru"):
    u = x["url"]
    if "youtube" in u or "news.google" in u:
        return None
    try:
        raw = urllib.request.urlopen(
            urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=15).read()
    except Exception:
        return None                     # недоступную страницу не засчитываем ни за, ни против
    page = raw.decode("utf-8", "ignore")
    flaws = {}
    native = detect_native(x)
    if native and x.get("language") != native:
        flaws["lang"] = True            # родной язык с чужой пометкой (ky/kk/uz/tg)
    if x.get("scope") == "world" and x.get("country") == HOME.get(pool):
        flaws["scope"] = True
    card, theirs = norm(x["title"]), og_title(page)
    if theirs and script_of(card) == script_of(theirs):
        if len(NEG.findall(card)) != len(NEG.findall(theirs)):
            flaws["neg"] = [card, theirs]
    try:
        res = extract_article(raw, u)
        body = res.text if res.ok() else ""
    except Exception:
        body = ""
    have, page_len = len(x.get("summary", "")), len(body)
    if page_len >= 900 and have < 0.5 * min(page_len, KEEP_LIMIT):
        flaws["short"] = [have, page_len]
    if CREDIT.match(x.get("summary", "")):
        flaws["credit"] = True
    return {"source": x["source"], "title": card[:70], "flaws": flaws}


def families():
    """PUBLISHER_FAMILIES из fetch_news.py без его импорта (нужны ключи и сеть)."""
    try:
        tree = ast.parse(open("fetch_news.py", encoding="utf-8").read())
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "PUBLISHER_FAMILIES" for t in node.targets):
                fam = ast.literal_eval(node.value)
                return lambda s: next((k for k, m in fam.items() if s in m), s)
    except Exception:
        pass
    return lambda s: s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool", default="ru")
    ap.add_argument("--max-bad-percent", type=float, default=5.0)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    data = json.load(urllib.request.urlopen(DB.format(pool=a.pool)))
    items = data if isinstance(data, list) else list(data.values())
    with cf.ThreadPoolExecutor(8) as ex:
        rows = [r for r in ex.map(lambda x: check(x, a.pool), items) if r]
    # близнецы: снятые drop_twins карточки считаем изъяном второго экземпляра
    _, twin_pairs = drop_twins(items, families(), frozenset(EDITION_LANG))
    twin_urls = {lose["url"] for _, lose in twin_pairs}
    by_url = {x["url"]: x for x in items}
    for lose in twin_urls:
        x = by_url.get(lose)
        if x is None:
            continue
        row = next((r for r in rows if r["title"] == norm(x["title"])[:70]), None)
        if row is None:
            row = {"source": x["source"], "title": norm(x["title"])[:70], "flaws": {}}
            rows.append(row)
        row["flaws"]["twin"] = True
    bad = [r for r in rows if r["flaws"]]
    pct = 100.0 * len(bad) / max(1, len(rows))
    loc = [x for x in items if x.get("scope") == "local"]
    nat = [x for x in loc if detect_native(x)]
    share = 100.0 * len(nat) / max(1, len(loc))
    kinds = {k: sum(1 for r in bad if k in r["flaws"])
             for k in ("neg", "short", "credit", "twin", "lang", "scope")}
    if a.json:
        print(json.dumps({"pool": a.pool, "checked": len(rows), "bad": len(bad),
                          "percent": round(pct, 1), "kinds": kinds, "rows": bad},
                         ensure_ascii=False, indent=1))
    else:
        print(f"[{a.pool}] проверено {len(rows)} из {len(items)}; брак {len(bad)} ({pct:.1f}%) "
              f"— заголовок {kinds['neg']}, коротко {kinds['short']}, подпись {kinds['credit']}, "
              f"дубль {kinds['twin']}, язык {kinds['lang']}, "
              f"не на своей полке {kinds['scope']}")
        print(f"    родной язык на «Местных»: {len(nat)} из {len(loc)} ({share:.0f}%, потолок 50%)")
        for r in bad:
            print(" ·", r["source"], "|", r["title"], "|", r["flaws"])
    sys.exit(1 if pct > a.max_bad_percent else 0)


if __name__ == "__main__":
    main()
