"""Полки стран: ИИ-отбор местных новостей для ВСЕХ стран пулов (06.10.2026).

Раньше для шести «жирных» домов (KG, US, BR, MX, ES, RU) местные новости шли через
бэкенд с ИИ, а для остальных ~60 стран собирались на ТЕЛЕФОНЕ из RSS без отбора:
ни белого списка событий, ни фильтра намерений, ни страны события и масштаба
(Молдова 06.10.2026: в карусели «призыв министра» и «ЛЭП назовут в честь Трампа»).

Здесь бэкенд берёт ленты стран (country_feeds.json, 64 страны, 129 лент), прогоняет
через ИИ по уставу и кладёт готовую полку в /news/country/{пул}/{ISO}.

ТЕНЕВОЙ РЕЖИМ: пишет только в /news/country и /meta/country_cache; приложение эти
узлы не читает — читателям ничего не меняется, пока приложение не переключат
(выпуск 47/48). За несколько прогонов видно стоимость и качество.

Устройство: чистые функции (язык, выбор целей, разбор ответа ИИ, сборка полки) не
импортируют fetch_news — их проверяет test_country_shelves.py без сети и ключей.
run() импортирует fetch_news лениво (ему нужны ключи и Firebase).

Запуск:  python country_shelves.py --dry-run --countries MD,KZ   (без записи)
         python country_shelves.py --no-ai --countries MD         (только сбор лент)
         python country_shelves.py                                (все страны, запись)
"""
import argparse
import json
import math
import os
import re
import sys
import time

import intent
import native_lang
import twins
from shelves import parse_where_scale

PER_COUNTRY = 12                 # решение владельца 06.10.2026
CANDIDATES = 24                  # сколько берём с лент до отбора
FRESH_MS = 48 * 3600 * 1000
CHUNK = 40
FAT_HOMES = {"KG", "US", "BR", "MX", "ES", "RU"}   # их полки уже делает основной конвейер

HERE = os.path.dirname(os.path.abspath(__file__))


def load_json(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return json.load(f)


# ─── Язык карточки ─────────────────────────────────────────────────────────

_STOP = {
    "en": {"the", "and", "of", "to", "in", "is", "for", "on", "with", "that", "was", "has", "will"},
    "fr": {"le", "la", "les", "des", "et", "est", "une", "pour", "dans", "que", "qui", "du", "au"},
    "es": {"el", "la", "los", "las", "y", "de", "que", "en", "un", "una", "por", "con", "para"},
    "pt": {"o", "os", "as", "de", "que", "em", "um", "uma", "para", "com", "não", "do", "da"},
    "nl": {"de", "het", "een", "en", "van", "dat", "is", "voor", "met", "op", "niet", "zijn"},
    "de": {"der", "die", "das", "und", "ist", "nicht", "mit", "für", "ein", "eine", "auf", "zu"},
    "ro": {"și", "de", "la", "în", "pe", "cu", "pentru", "este", "care", "din", "un", "o", "mai", "că"},
    "it": {"il", "lo", "la", "di", "che", "e", "un", "una", "per", "con", "non", "sono"},
}


def _script_counts(text):
    c = {"cyr": 0, "lat": 0, "arm": 0, "geo": 0, "ara": 0}
    for ch in text:
        o = ord(ch)
        if 0x0400 <= o <= 0x04FF:
            c["cyr"] += 1
        elif ch.isalpha() and o < 0x250:
            c["lat"] += 1
        elif 0x0530 <= o <= 0x058F:
            c["arm"] += 1
        elif 0x10A0 <= o <= 0x10FF:
            c["geo"] += 1
        elif 0x0600 <= o <= 0x06FF:
            c["ara"] += 1
    return c


def guess_latin_lang(text, candidates):
    """Язык латиницы по служебным словам среди [candidates]; None — не уверены."""
    words = re.findall(r"[^\W\d_]+", text.lower())
    best, best_n = None, 1
    for lang in candidates:
        n = sum(1 for w in words if w in _STOP.get(lang, ()))
        if n > best_n:
            best, best_n = lang, n
    return best


def label_language(item, pool, natives):
    """Язык карточки по тексту: код пула, государственный язык страны или None.

    pool — язык пула (ru/en/es/pt/fr), natives — языки страны из country_langs.json.
    """
    text = (item.get("title") or "") + " " + (item.get("summary") or "")[:300]
    sc = _script_counts(text)
    top = max(sc, key=sc.get)
    if sc[top] == 0:
        return None
    if top == "arm":
        return "hy"
    if top == "geo":
        return "ka"
    if top == "ara":
        return "ar"
    if top == "cyr":
        if pool == "ru":
            return native_lang.detect_native(item) or "ru"
        return "ru"                                 # кириллица в чужом пуле — русский
    cands = [pool] + [n for n in natives if n != pool]
    guess = guess_latin_lang(text, cands)
    if guess:
        return guess
    # латиницей пишет и сам русский пул (румынский в Молдове, азербайджанский): тогда
    # язык страны, иначе язык пула
    if pool == "ru":
        return next((n for n in natives if n not in ("ru", "ky", "kk", "tg", "be", "hy", "ka")), None)
    return pool


# ─── Цели ──────────────────────────────────────────────────────────────────

def targets(pool_countries, feeds, only=None):
    """[(пул, ISO)]: страны пространства пула, у которых есть ленты, без жирных домов.

    Канада состоит и в английском, и во французском пуле — для каждого своя полка:
    второй язык у неё разный (французский для английского читателя и наоборот).
    """
    out = []
    for pool, space in pool_countries.items():
        for iso in sorted(space):
            if iso in feeds and iso not in FAT_HOMES and (not only or iso in only):
                out.append((pool, iso))
    return out


# ─── Сбор и отбор ──────────────────────────────────────────────────────────

def fresh_unique(items, now_ms, limit):
    seen, out = set(), []
    for x in sorted(items, key=lambda i: i.get("publishedAt", 0), reverse=True):
        key = x.get("url") or x.get("title")
        if not key or key in seen:
            continue
        if now_ms - x.get("publishedAt", now_ms) > FRESH_MS:
            continue
        seen.add(key)
        out.append(x)
        if len(out) >= limit:
            break
    return out


def build_prompt(country_name, iso, langs, items, topics):
    cards = "\n".join(
        f"{i + 1}. [{x.get('source', '?')}] {x['title']} — {(x.get('summary') or '')[:260]}"
        for i, x in enumerate(items))
    return (
        f"Ниже новости местных изданий страны «{country_name}» ({iso}). Читатель этой страны "
        f"читает на языках: {', '.join(langs)}. Отбери, что показать ЕМУ, по уставу "
        f"(белый список событий, «Интересное» не снимается).\n\n"
        f"Поля ответа (номера — как в списке):\n"
        f"  keep — номера, которые ОСТАВИТЬ. Убирай: не на этих языках; не события по белому "
        f"списку (планы, призывы, выступления без решения, мнения, интервью, подборки); реклама "
        f"и PR; событие не в этой стране и не касающееся её жителей.\n"
        f"  urgent — до двух срочных (будить звуком стоит редко, порог высокий)\n"
        f"  important — важные жителям этой страны\n"
        f"  where — для КАЖДОЙ новости страна события (ISO) или \"-\"\n"
        f"  world / region — номера мирового / регионального масштаба; остальные местные\n"
        f"  topic — тема каждой из списка: {', '.join(sorted(topics))}\n\n"
        f"Верни ТОЛЬКО JSON: {{\"keep\": [1,3], \"urgent\": [], \"important\": [3], "
        f"\"where\": {{\"1\": \"{iso}\", \"2\": \"-\"}}, \"world\": [], \"region\": [], "
        f"\"topic\": {{\"1\": \"politics\"}}}}\n\nНОВОСТИ:\n{cards}")


def parse_verdict(raw, count, topics):
    """Разбор ответа ИИ. Мусор не роняет: нет JSON → None (страну пропускаем)."""
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    def ids(key):
        raw_list = data.get(key)
        out = set()
        for v in raw_list if isinstance(raw_list, list) else []:
            try:
                i = int(v) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= i < count:
                out.add(i)
        return out

    where, scale = parse_where_scale(data, count)
    topic = {}
    raw_topic = data.get("topic")
    for k, v in (raw_topic.items() if isinstance(raw_topic, dict) else ()):
        main = str(v).strip().lower().partition("/")[0]
        try:
            if main in topics and 0 <= int(k) - 1 < count:
                topic[int(k) - 1] = str(v).strip().lower()
        except (TypeError, ValueError):
            continue
    return {"keep": ids("keep"), "urgent": ids("urgent"), "important": ids("important"),
            "where": where, "scale": scale, "topic": topic}


def assemble(items, verdict, iso, pool, natives, limit=PER_COUNTRY):
    """Применяет вердикт и пост-обработку; → список карточек полки (не больше limit)."""
    kept = []
    for i, x in enumerate(items):
        if i not in verdict["keep"]:
            continue
        x = dict(x)
        x["scope"] = "local"
        x["country"] = iso
        x["language"] = label_language(x, pool, natives) or pool
        x["priority"] = 2 if i in verdict["important"] else 1
        if i in verdict["urgent"]:
            x["category"] = "URGENT_LOCAL_ONLY"
        if i in verdict["where"]:
            x["event_where"] = verdict["where"][i]
            x["scale"] = verdict["scale"][i]
        if i in verdict["topic"]:
            x["topic"] = verdict["topic"][i]
        kept.append(x)
    # урезаем срочные до двух, остальные «срочные» остаются обычными
    urgent = [x for x in kept if x.get("category") == "URGENT_LOCAL_ONLY"]
    for x in sorted(urgent, key=lambda i: i.get("publishedAt", 0), reverse=True)[2:]:
        x["category"] = "NEWS"
    kept, _ = twins.drop_twins(kept)
    intent.mark(kept, pool)
    kept.sort(key=lambda x: x.get("publishedAt", 0), reverse=True)
    kept = native_lang.cap_native_share(kept, pool)[0]
    return kept[:limit]


def strip_internal(x):
    return {k: v for k, v in x.items() if not k.startswith("_")}


# ─── Запуск ────────────────────────────────────────────────────────────────

def run(only=None, pools=None, dry_run=True, no_ai=False, write=False):
    import fetch_news as fn                         # ленивый импорт: нужны ключи и Firebase
    from concurrent.futures import ThreadPoolExecutor

    feeds = load_json("country_feeds.json")
    langs = load_json("country_langs.json")
    topics = set(fn.NEWS_TOPICS)
    names = {c: fn_name(c) for c in feeds}
    pc = {p: v for p, v in fn.POOL_COUNTRIES.items() if not pools or p in pools}
    todo = targets(pc, feeds, only)
    print(f"🌍 Полки стран: {len(todo)} целей, режим: "
          f"{'сухой' if dry_run else 'запись'}{', без ИИ' if no_ai else ''}")
    now_ms = int(time.time() * 1000)

    cache = {}
    if write and not no_ai:
        try:
            cache = fn.db.reference("/meta/country_cache").get() or {}
        except Exception as e:                      # нет кэша — ничего страшного
            print(f"  ⚠️ кэш вердиктов не прочитан: {e}")

    def collect(target):
        pool, iso = target
        fl = feeds[iso]
        per_feed = max(8, math.ceil(CANDIDATES / len(fl)))
        raw = []
        for f in fl:
            raw += fn.fetch_rss({"url": f["url"], "source": f["source"], "category": "NEWS",
                                 "priority": 1, "quota": per_feed, "scope": "local"})
        return target, fresh_unique(raw, now_ms, CANDIDATES)

    with ThreadPoolExecutor(8) as ex:
        collected = list(ex.map(collect, todo))

    published, spent_items = 0, 0
    for (pool, iso), items in collected:
        nat = langs.get(iso, [])
        accept = [pool] + [n for n in nat if n != pool]
        label = f"{pool}/{iso}"
        if not items:
            print(f"  · {label}: лент нет или пусто")
            continue
        if no_ai:
            print(f"  · {label}: собрано {len(items)}; язык: "
                  f"{[label_language(x, pool, nat) for x in items][:6]}")
            continue
        cc = cache.get(pool, {}).get(iso, {}) if isinstance(cache.get(pool), dict) else {}
        fresh_items = [x for x in items if fn._cache_key(x) not in cc]
        verdict_items = fresh_items
        verdict = {"keep": set(), "urgent": set(), "important": set(),
                   "where": {}, "scale": {}, "topic": {}}
        keep_old = [x for x in items if fn._cache_key(x) in cc and cc[fn._cache_key(x)].get("keep")]
        for start in range(0, len(verdict_items), CHUNK):
            part = verdict_items[start:start + CHUNK]
            spent_items += len(part)
            raw = fn.ask_gemini(build_prompt(names.get(iso, iso), iso, accept, part, topics))
            v = parse_verdict(raw, len(part), topics)
            if v is None:
                print(f"  ⚠️ {label}: ответ ИИ не разобран — порция пропущена")
                continue
            for k in ("keep", "urgent", "important"):
                verdict[k] |= {start + i for i in v[k]}
            for k in ("where", "scale", "topic"):
                verdict[k].update({start + i: val for i, val in v[k].items()})
        # к новым вердиктам добавляем помнящиеся «оставить»
        merged = verdict_items + keep_old
        offset_keep = set(verdict["keep"]) | {len(verdict_items) + j for j in range(len(keep_old))}
        full = {"keep": offset_keep, "urgent": verdict["urgent"], "important": verdict["important"],
                "where": verdict["where"], "scale": verdict["scale"], "topic": verdict["topic"]}
        shelf = [strip_internal(x) for x in assemble(merged, full, iso, pool, nat)]
        print(f"  ✓ {label}: собрано {len(items)}, новых для ИИ {len(fresh_items)}, "
              f"на полке {len(shelf)}")
        if dry_run:
            for x in shelf[:3]:
                print(f"       · [{x.get('source')}] {x.get('language')} {x['title'][:70]}")
        if write:
            fn.db.reference(f"/news/country/{pool}/{iso}").set(
                {"items": shelf, "updatedAt": now_ms, "v": 1})
            cc = {fn._cache_key(x): {"keep": int(i in verdict["keep"]), "ts": now_ms}
                  for i, x in enumerate(verdict_items)}
            cc.update({k: v for k, v in (cache.get(pool, {}) or {}).get(iso, {}).items()
                       if isinstance(v, dict) and now_ms - v.get("ts", 0) < 3 * FRESH_MS})
            cache.setdefault(pool, {})[iso] = cc
            published += 1
    if write and cache:
        fn.db.reference("/meta/country_cache").set(cache)
    print(f"🌍 Готово: полок {published}, карточек у ИИ {spent_items}")


COUNTRY_NAMES = {
    "AM": "Армения", "AO": "Ангола", "AR": "Аргентина", "AU": "Австралия", "AZ": "Азербайджан",
    "BE": "Бельгия", "BF": "Буркина-Фасо", "BJ": "Бенин", "BO": "Боливия", "BY": "Беларусь",
    "CA": "Канада", "CD": "ДР Конго", "CH": "Швейцария", "CI": "Кот-д'Ивуар", "CL": "Чили",
    "CM": "Камерун", "CO": "Колумбия", "CR": "Коста-Рика", "CU": "Куба", "CV": "Кабо-Верде",
    "DO": "Доминикана", "DZ": "Алжир", "EC": "Эквадор", "FR": "Франция", "GB": "Великобритания",
    "GE": "Грузия", "GN": "Гвинея", "GT": "Гватемала", "GW": "Гвинея-Бисау", "HN": "Гондурас",
    "HT": "Гаити", "IE": "Ирландия", "IN": "Индия", "JM": "Ямайка", "KZ": "Казахстан",
    "LU": "Люксембург", "MA": "Марокко", "MC": "Монако", "MD": "Молдова", "MG": "Мадагаскар",
    "ML": "Мали", "MZ": "Мозамбик", "NE": "Нигер", "NG": "Нигерия", "NI": "Никарагуа",
    "NZ": "Новая Зеландия", "PA": "Панама", "PE": "Перу", "PT": "Португалия", "PY": "Парагвай",
    "SG": "Сингапур", "SN": "Сенегал", "ST": "Сан-Томе и Принсипи", "SV": "Сальвадор",
    "TG": "Того", "TJ": "Таджикистан", "TL": "Восточный Тимор", "TM": "Туркмения",
    "TN": "Тунис", "UA": "Украина", "UY": "Уругвай", "UZ": "Узбекистан", "VE": "Венесуэла",
    "ZA": "ЮАР",
}


def fn_name(iso):
    return COUNTRY_NAMES.get(iso, iso)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", default="")
    ap.add_argument("--pools", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-ai", action="store_true")
    a = ap.parse_args()
    only = {c.strip().upper() for c in a.countries.split(",") if c.strip()} or None
    pools = {p.strip() for p in a.pools.split(",") if p.strip()} or None
    run(only=only, pools=pools, dry_run=a.dry_run, no_ai=a.no_ai, write=not a.dry_run and not a.no_ai)


if __name__ == "__main__":
    main()
