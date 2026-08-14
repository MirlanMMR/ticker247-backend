"""
Проверка качества лент — вместо скриншотов.

Читает то, что видит человек в приложении (/news/{ru,en,es,pt} в Firebase),
и проверяет каждую новость по правилам, до которых мы дошли за эти дни.
Печатает сводку и худшие случаи с указанием, чем они плохи.

Запуск (ключи не нужны, /news открыт на чтение):
    python3 quality_check.py            — все пулы
    python3 quality_check.py ru         — один пул
    python3 quality_check.py ru --all   — показать все находки, не только 5

Зачем: раньше ошибки находил пользователь, делая скриншоты по одной. Это и
медленно, и обидно — он работал нашими глазами. Теперь список проблемных
статей собирается сам, и чинить можно классами, а не поштучно.
"""
import json
import re
import sys
import urllib.request
from collections import Counter, defaultdict

DB = "https://ticker247-default-rtdb.asia-southeast1.firebasedatabase.app"
POOLS = ["ru", "en", "es", "pt"]

# ── Признаки беды ────────────────────────────────────────────────────────────

# Служебные строки, которые нельзя показывать как текст новости
JUNK_MARKERS = [
    "photographer:", "crédito,", "credit:", "image caption", "image source",
    "getty images", "blog is currently unavailable", "please try again later",
    "этот блог в настоящее время недоступен", "подписывайтесь на наши соцсети",
    "при первом открытии приложения", "недоступно на территории",
    "sign up", "follow us", "subscribe", "read more", "advertisement",
    "this video can not be played", "reference #", "access denied",
]

# Заголовки без события: интервью, колонки, подборки, разборы.
# Это грубая примета, точное решение принимает ИИ на стороне бэкенда —
# здесь нам достаточно поймать явные случаи и показать их в отчёте.
NO_EVENT_PATTERNS = [
    r"^[«\"']",                      # начинается с цитаты — почти всегда интервью
    r"\b(как я|как мы|почему я)\b",
    r"\b(о разбитых|о том, как|рассказал о том)\b",
    r"^\d+\s+(способ|причин|вещей|things|ways|reasons)",
    r"\b(мнение|колонка|обзор|разбор|что это значит)\b",
    r"\b(opinion|analysis|explainer|review|how to|why you)\b",
    r"\b(интервью|interview)\b",
]

# Кириллица в неславянском пуле и наоборот — след непереведённого текста
CYRILLIC = re.compile(r"[а-яё]", re.I)
LATIN_WORDS = re.compile(r"\b[a-z]{4,}\b", re.I)


def fetch(pool):
    with urllib.request.urlopen(f"{DB}/news/{pool}.json", timeout=30) as r:
        return json.load(r).get("items", [])


def problems(item, pool):
    """Что не так с этой новостью. Пустой список — всё в порядке."""
    out = []
    title = (item.get("title") or "").strip()
    body = (item.get("summary") or "").strip()
    low_body = body.lower()

    if not item.get("imageUrl"):
        out.append("нет фото")

    if len(body) < 120:
        out.append(f"текст короткий ({len(body)})")

    for m in JUNK_MARKERS:
        if m in low_body:
            out.append(f"служебная строка в тексте: «{m}»")
            break

    for p in NO_EVENT_PATTERNS:
        if re.search(p, title, re.I):
            out.append("похоже, нет инфоповода")
            break

    # Обрыв именно НА ПОЛУСЛОВЕ, а не просто отсутствие точки: многие ленты
    # дают одно предложение без завершающего знака, и это нормально.
    # Признак настоящего обрыва — хвост на запятой, союзе или предлоге
    if body:
        tail = body.rstrip()
        last = tail.split()[-1].lower() if tail.split() else ""
        HANGING = {"и", "а", "но", "что", "как", "для", "при", "the", "and",
                   "of", "to", "in", "on", "with", "for", "que", "de", "e"}
        if tail.endswith((",", "—", "–", ":", ";")) or last in HANGING:
            out.append("текст обрывается на полуслове")

    # Чужой язык в теле
    if pool == "ru":
        if body and not CYRILLIC.search(body):
            out.append("текст не на русском")
    else:
        cyr = len(CYRILLIC.findall(body))
        if cyr > 10:
            out.append("кириллица в нерусском пуле")

    # Заголовок повторён в начале текста — читатель видит одно и то же дважды
    if title and body.lower().startswith(title.lower()[:40].lower()):
        out.append("текст начинается с заголовка")

    # Срочность там, где её быть не должно
    if item.get("category") == "URGENT" and item.get("priority", 0) < 2:
        out.append("метка «срочно» без приоритета")

    return out


def check_pool(pool, show_all=False):
    items = fetch(pool)
    print(f"\n{'=' * 70}\n[{pool.upper()}] новостей: {len(items)}")
    if not items:
        return

    found = defaultdict(list)
    for it in items:
        for p in problems(it, pool):
            key = p.split(":")[0]
            found[key].append((p, it))

    # Дубли: одна тема у разных источников после всех наших склеек
    seen = defaultdict(list)
    for it in items:
        words = {w.lower() for w in (it.get("title") or "").split() if len(w) > 4}
        for other_key, other_words in list(seen.items()):
            if words and other_words and len(words & other_words) / min(len(words), len(other_words)) >= 0.5:
                found["дубль темы"].append((f"дубль с «{other_key[:40]}»", it))
                break
        seen[(it.get("title") or "")[:60]] = words

    # Почти-дубли: пары, которые склейка НЕ признала одним событием, но
    # которые подозрительно близки. Нужны, чтобы настраивать порог по живым
    # данным, а не на глаз: 24.kg и Knews.kg пишут об одном деле ГКНБ разными
    # словами, и мы показываем обе — одну с фото, другую без
    STOP = {"который", "которая", "после", "более", "также", "через", "около"}
    def sig(t):
        return {w.strip(".,:;«»\"'()").lower() for w in t.split()
                if len(w) > 5 and w.lower() not in STOP}
    near = []
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            wa, wb = sig(items[a].get("title") or ""), sig(items[b].get("title") or "")
            if len(wa) < 3 or len(wb) < 3:
                continue
            common = wa & wb
            ratio = len(common) / min(len(wa), len(wb))
            if 0.3 <= ratio < 0.6:
                near.append((ratio, items[a], items[b], common))
    if near:
        near.sort(reverse=True, key=lambda x: x[0])
        print(f"  ── почти-дубли (склейка их пропустила): {len(near)}")
        for ratio, x, y, common in near[:5]:
            fa = "фото" if x.get("imageUrl") else "БЕЗ ФОТО"
            fb = "фото" if y.get("imageUrl") else "БЕЗ ФОТО"
            print(f"     {ratio:.0%} общих слов: {', '.join(sorted(common))}")
            print(f"        [{x.get('source')}, {fa}] {(x.get('title') or '')[:58]}")
            print(f"        [{y.get('source')}, {fb}] {(y.get('title') or '')[:58]}")
        print()

    total_bad = len({id(it) for lst in found.values() for _, it in lst})
    print(f"с замечаниями: {total_bad} ({total_bad * 100 // max(len(items), 1)}%)")
    print()

    for key, lst in sorted(found.items(), key=lambda kv: -len(kv[1])):
        print(f"  {len(lst):3}  {key}")
        for note, it in (lst if show_all else lst[:3]):
            print(f"        [{it.get('source')}] {(it.get('title') or '')[:62]}")
            if key in ("служебная строка в тексте", "текст обрывается на полуслове"):
                print(f"           …{(it.get('summary') or '')[-90:]}")
    return found


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    show_all = "--all" in sys.argv
    for pool in (args or POOLS):
        check_pool(pool, show_all)
    print()
