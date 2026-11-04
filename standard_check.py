# -*- coding: utf-8 -*-
"""Проверка ленты на соответствие ЭТАЛОНУ (docs/STANDARD.md).

Эталон — один документ: каким должна быть каждая карточка и каждая полка. Здесь — только
сверка, без правки (чинит сторож, см. STANDARD.md, раздел «Кто чинит»). Все детекторы берутся
из border.REGISTRY — тех же, что стоят в конвейере: второго набора проверок нет.

  python standard_check.py --pool ru            # одна лента
  python standard_check.py                      # все пулы
  python standard_check.py --sources            # + проверка, что каждая лента источника отдаёт записи
  python standard_check.py --json

Выход 1, если есть красный флаг. Только чтение.
"""
import argparse
import json
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import border
from shelves import POOL_HOME

DB = "https://ticker247-default-rtdb.asia-southeast1.firebasedatabase.app/news/{pool}/items.json"
POOLS = ("ru", "en", "es", "pt", "fr")
FLOOR = 6                       # карточек на полку за 36 ч (CLAUDE.md, «Свежесть ленты»)
HOURS = 36
INTERESTING_FLOOR = 3           # «Интересное» живёт 48 ч; меньше трёх — полоса пустая
STALE_HOURS = {"ru": 6, "en": 8, "es": 14, "pt": 14, "fr": 10}   # дольше слотов ничего не было — прогон не дошёл

# Классы, у которых любая находка — красный флаг (закрыты, см. border.REGISTRY, closed=True),
# и классы-доли, где допустим порог
SHELVES = ("local", "pool", "world")
# Общие картинки сайта вместо фото новости: логотипы, «по умолчанию», универсальные иллюстрации
STUB_IMG = re.compile(r"(facebook-default|/default/|placeholder|no-?image|generic-|site-?logo|og-?default|"
                      r"default-?(share|image|og)|favicon)", re.I)


def load(pool):
    d = json.load(urllib.request.urlopen(DB.format(pool=pool), timeout=60))
    return list(d.values()) if isinstance(d, dict) else [x for x in d if x]


def neighbours(pool, space):
    home = POOL_HOME[pool]
    return {"CA", "MX"} if home == "US" else (space - {home})


def check_pool(pool, now_ms):
    items = load(pool)
    space = border._space(pool)
    home = POOL_HOME[pool]
    flags = []              # (код правила, описание, подробности)
    fresh = [x for x in items if (now_ms - (x.get("publishedAt") or 0)) <= HOURS * 3600e3]

    # ── Полки: наполнение (S-F1) ────────────────────────────────────────────
    news = [x for x in fresh if x.get("category") not in ("CURRENCY", "CRYPTO") and not x.get("interesting")]
    nb = neighbours(pool, space)
    counts = {
        "Местные": sum(1 for x in news if x.get("scope") == "local"),
        "Новости из…": sum(1 for x in news if x.get("scope") != "world"
                           and (x.get("country") or "").upper() in nb),
        "Мировые": sum(1 for x in news if x.get("scope") == "world"),
    }
    for shelf, n in counts.items():
        if n < FLOOR:
            flags.append(("S-F1", f"полка «{shelf}» ниже пола: {n} из {FLOOR}", {"shelf": shelf, "n": n}))
    cur = sum(1 for x in items if x.get("interesting")
              and (now_ms - (x.get("publishedAt") or 0)) <= 48 * 3600e3)
    if cur < INTERESTING_FLOOR:
        flags.append(("S-F2", f"«Интересное»: {cur} из {INTERESTING_FLOOR}", {"n": cur}))

    # ── Свежесть ленты (S-F3) ──────────────────────────────────────────────
    newest_h = min(((now_ms - (x.get("publishedAt") or 0)) / 3.6e6 for x in items), default=999)
    if newest_h > STALE_HOURS[pool]:
        flags.append(("S-F3", f"самой свежей карточке {newest_h:.1f} ч (допустимо {STALE_HOURS[pool]})",
                      {"hours": round(newest_h, 1)}))

    # ── Карточка: детекторы пункта пропуска (S-C*) ─────────────────────────
    ctx = {"lang": pool, "home": home, "space": space}
    for code, name, det, closed in border.REGISTRY:
        if det is None:
            continue
        hits = [x for x in items if det(x, ctx)]
        if hits:
            flags.append((f"S-{code}", f"{name}: {len(hits)}",
                          {"closed": closed, "cards": [f"[{x.get('source')}] {(x.get('title') or '')[:60]}"
                                                        for x in hits[:4]]}))
    # ── Фото (S-P*): что видно без зрения. Лицо в кадре и «фото о том же» — S-P5/S-P6, замка пока нет ──
    cards = [x for x in items if x.get("category") not in ("CURRENCY", "CRYPTO")]
    nophoto = [x for x in cards if not x.get("imageUrl")]
    if len(nophoto) > 0.10 * max(1, len(cards)):
        flags.append(("S-P1", f"без фото {len(nophoto)} из {len(cards)} (допустимо до 10%)", {"n": len(nophoto)}))
    byimg = {}
    for x in cards:
        if x.get("imageUrl"):
            byimg.setdefault(x["imageUrl"], []).append(x)
    shared = [v for v in byimg.values() if len(v) > 1]
    if shared:
        flags.append(("S-P2", f"одно фото на несколько карточек: {len(shared)}",
                      {"cards": [f"[{v[0].get('source')}] {(v[0].get('title') or '')[:60]}" for v in shared[:4]]}))
    stub = [x for x in cards if x.get("imageUrl") and STUB_IMG.search(x["imageUrl"])]
    if stub:
        flags.append(("S-P3", f"заглушка или общая картинка вместо фото: {len(stub)}",
                      {"cards": [f"[{x.get('source')}] {x['imageUrl'][-55:]}" for x in stub[:4]]}))
    lowres = [x for x in cards if x.get("imageLowRes")]
    if lowres:
        flags.append(("S-P4", f"фото низкого качества (imageLowRes): {len(lowres)}",
                      {"cards": [f"[{x.get('source')}] {(x.get('title') or '')[:60]}" for x in lowres[:4]]}))
    return {"pool": pool, "cards": len(items), "fresh": len(fresh), "counts": counts,
            "interesting": cur, "newest_h": round(newest_h, 1), "flags": flags}


# ── Источники отдают записи (S-S1) ─────────────────────────────────────────

UA = {"User-Agent": "Mozilla/5.0 (compatible; Ticker247Check)"}


def source_list():
    """Ленты источников из fetch_news.py без его импорта (тот тянет ключи и ИИ-библиотеки)."""
    import ast
    text = open("fetch_news.py", encoding="utf-8").read()
    retired = []
    for n in ast.parse(text).body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "RETIRED_SOURCES" for t in n.targets):
            try:
                retired = [str(v).lower() for v in ast.literal_eval(n.value)]
            except Exception:
                pass
    pairs = re.findall(r'\{"url": "(https?://[^"]+)", "source": "([^"]+)"', text)
    seen, out = set(), []
    for url, name in pairs:
        if url not in seen and not any(d in url.lower() for d in retired):
            seen.add(url)
            out.append((name, url))
    return out


def probe(src):
    name, url = src
    try:
        import requests
        r = requests.get(url, timeout=15, headers=UA)
        n = len(re.findall(r"<(?:item|entry)[\s>]", r.text))
        return name, url, r.status_code, n
    except Exception as e:
        return name, url, f"ERR {type(e).__name__}", 0


def dead_sources():
    urls = source_list()
    with ThreadPoolExecutor(16) as ex:
        res = list(ex.map(probe, urls))
    return [r for r in res if r[3] == 0], len(urls)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pool")
    ap.add_argument("--sources", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    now_ms = time.time() * 1000
    out = [check_pool(p, now_ms) for p in ([a.pool] if a.pool else POOLS)]
    dead = []
    if a.sources:
        dead, total = dead_sources()
    red = sum(len(r["flags"]) for r in out) + len(dead)
    if a.json:
        print(json.dumps({"pools": out, "dead_sources": dead, "red": red}, ensure_ascii=False))
    else:
        for r in out:
            print(f"[{r['pool']}] карточек {r['cards']} (за 36 ч {r['fresh']}); полки {r['counts']}; "
                  f"интересное {r['interesting']}; свежайшая {r['newest_h']} ч — "
                  + ("✅ соответствует" if not r["flags"] else f"🔴 флагов {len(r['flags'])}"))
            for code, text, det in r["flags"]:
                print(f"   🔴 {code}: {text}")
                for c in det.get("cards", []):
                    print(f"        · {c}")
        if a.sources:
            print(f"\nИсточники: без записей {len(dead)} из {total}")
            for name, url, st, n in dead:
                print(f"   🔴 S-S1 {name} [{st}] {url}")
        print(f"\nИтого красных флагов: {red}")
    sys.exit(1 if red else 0)


if __name__ == "__main__":
    main()
