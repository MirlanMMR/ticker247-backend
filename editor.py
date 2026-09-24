"""Выпускающий редактор — последний шаг перед эфиром (24.09.2026).

Зачем. До него над новостью работало с десяток разрозненных шагов — отбор по
заголовкам, разметка, обрезка по правилу, проверка фото, — и каждый видел свой
кусок. Ошибки проскакивали в зазорах: анонс вместо статьи в 14% карточек,
фото блогера над новостью о кокаине, интервью без события, опечатки
изданий. Владелец: «нам нужен один ИИ — выпускающий редактор, который
понимает смысл, отфильтровывает мусор, говорит, какое фото брать, правит
ошибки».

Редактор видит карточку целиком — заголовок, текст по абзацам, снимки со
страницы с подписями — и отвечает одним решением: выпускать ли, какие абзацы,
исправленный заголовок, какой снимок, жизненно ли важно. Инструкция — в
EDITOR.md.

Две модели, как в редакции: дешёвая (без рассуждений) решает всё; спорное,
что она сама пометила unsure, перепроверяет рассуждающая.

Этот модуль не знает про Firebase и Gemini — всё внешнее ему передают.
Так его можно проверять без сети (test_editor.py).
"""
import json
import re
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

EDITOR_VERSION = 1
BATCH = 6                 # карточек в одном запросе
MAX_PARAS = 14
MAX_TEXT = 5000
MAX_PHOTOS = 6

REASONS = {"реклама", "нет события", "анонс без сути", "закрыто", "мусор",
           "не для читателя"}

_CARD = re.compile(r"/images/sharing/|/sharing/|/social[-_/]|og[-_]image|share[-_]card"
                   r"|_og\.(jpe?g|png|webp)|/og/|[?&]og=|imagemeta/", re.I)
_JUNK_IMG = re.compile(r"logo|icon|avatar|banner|pixel|1x1|sprite|placeholder", re.I)
_SENT = re.compile(r"(?<=[.!?…»\"])\s+(?=[A-ZА-ЯЁÀ-Ý«\"\d])")


# ─── Досье ────────────────────────────────────────────────────────────────

def split_paragraphs(text: str):
    """Абзацы статьи. Один длинный кусок режем по два предложения — иначе
    редактору нечего выбирать, кроме «всё или ничего»."""
    text = (text or "").strip()[:MAX_TEXT]
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    out = []
    for p in paras:
        if len(p) > 700:
            sents = _SENT.split(p)
            for i in range(0, len(sents), 2):
                out.append(" ".join(sents[i:i + 2]).strip())
        else:
            out.append(p)
    return [p for p in out if p][:MAX_PARAS]


def _links_elsewhere(img, page_url: str) -> bool:
    here = urlsplit(page_url).path.rstrip("/")
    for anc in img.parents:
        if anc.name == "aside":
            return True
        if anc.name == "a":
            href = anc.get("href") or ""
            if not href or href.startswith("#"):
                continue
            if re.search(r"\.(jpe?g|png|webp)(\?|$)", href, re.I):
                continue
            if urlsplit(href).path.rstrip("/") != here:
                return True
    return False


def page_photos(html: str, page_url: str, current: str = ""):
    """Снимки статьи с подписями. №1 — тот, что стоит в карточке сейчас."""
    photos, seen = [], set()

    def add(url, alt, where):
        if not url or not url.startswith("http"):
            return
        key = re.sub(r"_\d+x\d+|[?#].*$", "", url)
        if key in seen:
            return
        seen.add(key)
        flag = ("карточка с заголовком" if _CARD.search(url)
                else "логотип/иконка" if _JUNK_IMG.search(url) else "")
        photos.append({"url": url, "alt": (alt or "").strip()[:140],
                       "where": where, "flag": flag})

    if current:
        add(current, "", "сейчас в карточке")
    if not html:
        return photos[:MAX_PHOTOS]
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return photos[:MAX_PHOTOS]
    alt_by_src = {}
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src") or ""
        if src.startswith("http"):
            alt_by_src.setdefault(src, img.get("alt") or img.get("title") or "")
    for link in soup.find_all("link", rel="preload"):
        if link.get("as") == "image":
            u = link.get("href") or ""
            add(u, alt_by_src.get(u, ""), "главное фото страницы")
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        add(og["content"], "", "обложка для соцсетей")
    for img in soup.find_all("img"):
        if len(photos) >= MAX_PHOTOS:
            break
        src = img.get("src") or img.get("data-src") or ""
        if not src.startswith("http"):
            continue
        if not re.search(r"\.(jpe?g|png|webp)", src, re.I):
            continue
        try:
            w = int(img.get("width") or 0)
            if 0 < w < 400:
                continue
        except ValueError:
            pass
        where = "ссылка на другую статью" if _links_elsewhere(img, page_url) else "в статье"
        add(src, img.get("alt") or img.get("title") or "", where)
    # подпись для №1 могла найтись на странице
    if photos and not photos[0]["alt"]:
        photos[0]["alt"] = alt_by_src.get(photos[0]["url"], "")
    return photos[:MAX_PHOTOS]


def card_block(n: int, item: dict, paras, photos) -> str:
    shelf = {"local": "местная", "pool": "свой язык (соседи)",
             "world": "мир"}.get(item.get("scope"), item.get("scope") or "?")
    lines = [f"### Карточка {n}",
             f"Издание: {item.get('source', '?')} · полка: {shelf}"
             + (" · помечена срочной" if item.get("category") == "URGENT" else "")
             + (" · издатель закрыл статью" if item.get("pageClosed") else ""),
             f"Заголовок: {item.get('title', '')}",
             "Текст:"]
    lines += [f"[{i}] {p}" for i, p in enumerate(paras, 1)] or ["(текста нет)"]
    lines.append("Снимки:")
    if photos:
        for i, ph in enumerate(photos, 1):
            name = urlsplit(ph["url"]).path.rsplit("/", 1)[-1][:60]
            bits = [ph["where"]]
            if ph["flag"]:
                bits.append(ph["flag"])
            bits.append(f"подпись: «{ph['alt']}»" if ph["alt"] else "подписи нет")
            lines.append(f"({i}) {name} — " + "; ".join(bits))
    else:
        lines.append("(снимков нет)")
    return "\n".join(lines)


def pool_header(lang: str, home: str, language_name: str) -> str:
    return (f"Поток: {lang}. Домашняя страна читателя: {home}. "
            f"Язык ленты: {language_name}.\n\n")


# ─── Ответ ────────────────────────────────────────────────────────────────

def parse_verdicts(raw: str):
    """{номер карточки: решение}. Испорченный JSON — пустой словарь."""
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    m = re.search(r"\[.*\]", raw, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except Exception:
        return {}
    out = {}
    for v in data if isinstance(data, list) else []:
        if isinstance(v, dict) and isinstance(v.get("id"), int):
            out[v["id"]] = v
    return out


def title_typo_fix(old: str, new: str):
    """Правка заголовка — только опечатка, не переписка."""
    import difflib
    new = (new or "").strip().strip('"«»')
    if not new or new == old:
        return None
    if difflib.SequenceMatcher(None, old, new).ratio() < 0.93:
        return None
    return new


def apply_verdict(item: dict, v: dict, paras, photos, vital_ok=True):
    """Исполняет решение на КОПИИ карточки. → (выпускать?, копия, заметки)."""
    x = dict(item)
    notes = []
    publish = bool(v.get("publish", True))
    reason = str(v.get("reason") or "").strip().lower()
    if not publish:
        if reason not in REASONS:
            publish, reason = True, ""          # снять можно только по причине
            notes.append("снятие без причины отклонено")
        elif reason == "закрыто" and x.get("category") == "URGENT":
            publish = True                      # срочное — и так
            notes.append("закрыто, но срочно — выпущено")
    if not publish:
        return False, x, [f"снято: {reason}"]
    # текст — выбранные абзацы дословно
    idx = [i for i in v.get("paragraphs") or [] if isinstance(i, int) and 1 <= i <= len(paras)]
    idx = sorted(set(idx))
    if idx and paras:
        body = "\n\n".join(paras[i - 1] for i in idx)
        if len(body) >= 40:
            if len(idx) < len(paras):
                notes.append(f"абзацы {len(idx)}/{len(paras)}")
            x["summary"] = body
    # заголовок
    fixed = title_typo_fix(x.get("title", ""), v.get("title", ""))
    if fixed:
        notes.append(f"заголовок: «{x.get('title','')}» → «{fixed}»")
        x["title"] = fixed
    # снимок
    ph = v.get("photo")
    if isinstance(ph, int) and photos:
        if ph == 0:
            if v.get("need_photo"):
                x["_need_photo"] = True
                notes.append("нужно другое фото")
        elif 1 <= ph <= len(photos) and ph != 1:
            cand = photos[ph - 1]
            if not cand["flag"]:
                x["imageUrl"] = cand["url"]
                notes.append(f"фото: №{ph} вместо №1")
    # жизненно важное — только о своей стране
    if vital_ok and v.get("vital") and x.get("scope") == "local":
        x["category"] = "URGENT"
        x["priority"] = max(x.get("priority", 0), 2)
        x["vital"] = True
        notes.append("жизненно важное")
    if v.get("note"):
        notes.append(str(v["note"])[:60])
    return True, x, notes


# ─── Прогон ───────────────────────────────────────────────────────────────

def review(items, lang, *, ask, ask_strong, fetch_html, cache, cache_key,
           header, now_ms):
    """Решения редактора по всем карточкам пула.

    ask(tail) -> str             — дешёвая модель (инструкция в кэше)
    ask_strong(tail) -> str      — рассуждающая, для unsure
    fetch_html(url) -> str|None
    cache                        — dict, память решений (переживает прогоны)
    cache_key(item) -> str

    → список (item, verdict, paras, photos); verdict None — ИИ не ответил.
    """
    from concurrent.futures import ThreadPoolExecutor
    dossiers = []
    todo = []
    for it in items:
        paras = split_paragraphs(it.get("_full") or it.get("summary") or "")
        k = f"{lang}:{cache_key(it)}"
        c = cache.get(k)
        if (isinstance(c, dict) and c.get("v") == EDITOR_VERSION
                and c.get("n") == sum(len(p) for p in paras)):
            dossiers.append([it, c["verdict"], paras, c.get("photos") or []])
        else:
            d = [it, None, paras, None]
            dossiers.append(d)
            todo.append(d)
    # страницы — только тем, кого спрашиваем
    with ThreadPoolExecutor(max_workers=16) as pool:
        htmls = list(pool.map(lambda d: fetch_html(d[0].get("url", "")) if
                              str(d[0].get("url", "")).startswith("http") else None, todo))
    for d, html in zip(todo, htmls):
        d[3] = page_photos(html or "", d[0].get("url", ""), d[0].get("imageUrl", ""))

    def run(batch, asker, second=False):
        tail = header + ("Ты — ВТОРОЙ редактор: эти карточки первый пометил как "
                         "спорные. Реши сам, unsure не ставь.\n\n" if second else "")
        tail += "\n\n".join(card_block(i, d[0], d[2], d[3]) for i, d in enumerate(batch, 1))
        try:
            got = parse_verdicts(asker(tail))
        except Exception as e:
            print(f"  ⚠️ Редактор [{lang}] не ответил: {str(e)[:120]}")
            return
        for i, d in enumerate(batch, 1):
            if i in got:
                d[1] = got[i]

    for j in range(0, len(todo), BATCH):
        run(todo[j:j + BATCH], ask)
    unsure = [d for d in todo if d[1] and d[1].get("unsure")]
    for j in range(0, len(unsure), BATCH):
        run(unsure[j:j + BATCH], ask_strong, second=True)
    for d in todo:
        if d[1]:
            d[1]["_second"] = d in unsure
            cache[f"{lang}:{cache_key(d[0])}"] = compact(d[1], d[2], d[3], now_ms)
    return [tuple(d) for d in dossiers], len(todo), len(unsure)


def compact(v, paras, photos, now_ms):
    """Память решения — компактно: она скачивается каждый прогон, а трафик
    Firebase платный. Из снимков храним только те, что нужны решению."""
    src = v
    v = {}
    for k in ("reason", "paragraphs", "title", "note"):
        if src.get(k):
            v[k] = src[k]
    for k in ("need_photo", "vital", "_second"):
        if src.get(k) is True:
            v[k] = True
    # Флаг «не выпускать» и фото №0 («годного нет») — это False и 0. Общий
    # фильтр «пустых» значений их выбросил бы (в Python 0 == False), и снятая
    # статья вернулась бы из памяти в эфир. Поэтому — явно
    v["publish"] = src.get("publish", True) is not False
    if isinstance(src.get("photo"), int):
        v["photo"] = src["photo"]
    keep = []
    ph = v.get("photo")
    if isinstance(ph, int) and ph >= 2 and ph <= len(photos):
        keep = [photos[0], photos[ph - 1]]
        v["photo"] = 2
    elif photos:
        keep = [photos[0]]
    return {"v": EDITOR_VERSION, "ts": now_ms, "verdict": v,
            "n": sum(len(p) for p in paras), "photos": keep}


def summarize(results, lang):
    """Отчёт для журнала: что редактор сделал бы / сделал."""
    from collections import Counter
    reasons, fixes, examples = Counter(), Counter(), []
    vital = []
    for it, v, paras, photos in results:
        if not v:
            fixes["без ответа"] += 1
            continue
        ok, x, notes = apply_verdict(it, v, paras, photos)
        if not ok:
            r = notes[0].split(": ", 1)[-1]
            reasons[r] += 1
            if len(examples) < 12:
                examples.append(f"✗ {r}: [{it.get('source','?')}] {it.get('title','')[:70]}")
            continue
        for n in notes:
            if n.startswith("заголовок"):
                fixes["опечатка в заголовке"] += 1
                examples.append(f"✏️ {n[:120]}")
            elif n.startswith("фото"):
                fixes["фото заменено"] += 1
                examples.append(f"🖼 [{it.get('source','?')}] {it.get('title','')[:50]} — {n}")
            elif n == "нужно другое фото":
                fixes["нужно другое фото"] += 1
            elif n.startswith("абзацы"):
                fixes["текст сокращён до сути"] += 1
            elif n == "жизненно важное":
                vital.append(it.get("title", "")[:70])
        if v.get("_second"):
            fixes["перепроверено вторым"] += 1
    return reasons, fixes, examples, vital
