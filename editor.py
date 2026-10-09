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

import textcut as TC
from urllib.parse import urlsplit

from bs4 import BeautifulSoup

EDITOR_VERSION = 3          # 3: компоновка по правилу абзацев (09.10.2026) — вердикты v2 выбирали «суть в 2–4 абзацах»
BATCH = 6                 # карточек в одном запросе
# 5000 → 2800 знаков (25.09.2026): редактор ел 46% расхода ИИ, в основном
# входящими — полным текстом статей. С 09.10.2026 окно режется ЦЕЛЫМИ абзацами
# (не посреди), а редактор компонует текст сам — ему нужно видеть достаточно, чтобы
# отличить суть от «воды». Жизненно важное выходит целиком (_full)
MAX_PARAS = 10
MAX_TEXT = 2800
MAX_PHOTOS = 6

VITAL_KINDS = {"вода-свет-газ", "дороги-транспорт", "стихия-погода", "здоровье",
               "цены-на-необходимое", "документы-выплаты"}

REASONS = {"реклама", "нет события", "анонс без сути", "закрыто", "мусор",
           "не для читателя"}

_CARD = re.compile(r"/images/sharing/|/sharing/|/social[-_/]|og[-_]image|share[-_]card"
                   r"|_og\.(jpe?g|png|webp)|/og/|[?&]og=|imagemeta/", re.I)
_JUNK_IMG = re.compile(r"logo|icon|avatar|banner|pixel|1x1|sprite|placeholder", re.I)
_SENT = re.compile(r"(?<=[.!?…»\"])\s+(?=[A-ZА-ЯЁÀ-Ý«\"\d])")


# ─── Досье ────────────────────────────────────────────────────────────────

def split_paragraphs(text: str):
    """Окно статьи для редактора: НАСТОЯЩИЕ абзацы, целиком, с начала, пока не
    наберётся ~MAX_TEXT знаков (первый берётся всегда). Нумерация совпадает с
    началом полного списка абзацев (textcut.real_paragraphs), поэтому выбор
    редактора можно применить к целой статье. До 09.10.2026 длинный абзац
    делился по два предложения, а текст резался по знакам посреди абзаца —
    номера перестали соответствовать странице."""
    paras = TC.real_paragraphs(text)
    out, total = [], 0
    for p in paras:
        if out and (total + len(p) > MAX_TEXT or len(out) >= MAX_PARAS):
            break
        out.append(p)
        total += len(p)
    return out


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
        from textcut import is_known_stub
        flag = ("карточка с заголовком" if _CARD.search(url)
                else "логотип/иконка" if (_JUNK_IMG.search(url) or is_known_stub(url)) else "")
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
    # рамка компоновки: сколько абзацев в статье и сколько можно оставить
    full = TC.real_paragraphs(item.get("_full") or "")
    total = len(TC.article_region(full)) if full else len(paras)
    if total > TC.SHOW_WHOLE_UP_TO:
        shown = f"; ты видишь первые {len(paras)}" if len(paras) < len(full) else ""
        lines.append(f"Абзацев в статье: {total}{shown}. Оставь не больше {TC.shown_count(total)} "
                     f"(последний абзац не берём никогда).")
    elif total:
        lines.append(f"Абзацев в статье: {total} — короткая, целиком (`paragraphs` можно не заполнять).")
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


# ТЕНЬ «любопытное» (30.09.2026): пул, где редактор дополнительно помечает
# необычные истории. Лента от пометки НЕ меняется — она только попадает в
# отчёт прогона, чтобы через неделю решить, нужна ли такая полоса. Включён
# один ru: владелец читает его и не хочет переключать пул ради проверки
SHADOW_CURIOUS_POOLS = {"ru", "en", "es", "pt", "fr"}   # 09.10.2026: из «тени» в эфир, все пулы

CURIOUS_NOTE = (
    "ДОПОЛНИТЕЛЬНО (такая карточка попадёт в полосу «Интересное»): если история необычная "
    "и от неё читатель скажет «надо же» — редкое, странное, удивительное или "
    "смешное событие, с понятным первоисточником, без жертв, без рекламы и "
    "пресс-релиза, — добавь в её объект `\"curious\": true`. Ставь и тогда, когда "
    "снимаешь её как «нет события». Не ставь на обычные новости, политику, "
    "происшествия, рекорды из пресс-релизов, светскую хронику. Обычно 0–3 "
    "на весь поток. Подходят: научное открытие, странная находка, необычный вопрос о технологиях "
    "или природе (например, может ли ИИ обладать сознанием). Не подходят: политика, оружие, "
    "происшествия, награды, некрологи, законы, реклама.\n\n")


def pool_header(lang: str, home: str, language_name: str) -> str:
    head = (f"Поток: {lang}. Домашняя страна читателя: {home}. "
            f"Язык ленты: {language_name}.\n\n")
    return head + (CURIOUS_NOTE if lang in SHADOW_CURIOUS_POOLS else "")


def curious_list(results):
    """Карточки, которые редактор назвал любопытными (тень, лента не меняется)."""
    out = []
    for it, v, _paras, _photos in results:
        if v and v.get("curious") is True:
            out.append({
                "title": it.get("title", "")[:110], "source": it.get("source", "?"),
                "url": it.get("url", ""), "published": v.get("publish", True) is not False,
                "note": str(v.get("note") or "")[:60],
            })
    return out


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


def _stems5(text: str) -> set:
    return {w[:5] for w in re.findall(r"[a-zà-ÿа-яёөүң]{5,}", (text or "").lower())}


def caption_matches(caption: str, title: str) -> bool:
    """Подпись снимка делит с заголовком ≥2 основы (одной мало: «Российский
    блогер» и «задержание россиянина» делят «росси»)."""
    return len(_stems5(caption) & _stems5(title)) >= 2


_WORD = re.compile(r"[\w\-]+", re.U)


def title_typo_fix(old: str, new: str):
    """Правка заголовка — только опечатка, не переписка.

    Первый прогон 24.09 показал, что сходства строк мало: ИИ «исправлял»
    кавычки и заменил «MS NOW» на «MSNBC» — а MS NOW и есть новое имя канала.
    Поэтому правка принимается, только если:
      · слова те же по счёту и порядку, меняется не больше двух;
      · каждое изменённое слово похоже на старое (одна-две буквы) и
        начинается с той же буквы — окончание, пропущенная буква;
      · слово не написано с заглавной (имена и названия не трогаем).
    Правка одних знаков препинания не нужна — отвергаем.
    """
    import difflib
    new = (new or "").strip()
    if not new or new == old:
        return None
    a, b = _WORD.findall(old), _WORD.findall(new)
    if a == b or len(a) != len(b):
        return None
    changed = [(x, y) for x, y in zip(a, b) if x != y]
    if not changed or len(changed) > 2:
        return None
    for x, y in changed:
        if x[:1] != y[:1] or x[:1].isupper() or abs(len(x) - len(y)) > 2:
            return None
        if difflib.SequenceMatcher(None, x.lower(), y.lower()).ratio() < 0.8:
            return None
    # подставляем изменённые слова в ИСХОДНЫЙ заголовок — его знаки и
    # кавычки остаются как у издания
    out = old
    for x, y in changed:
        out = re.sub(rf"(?<![\w-]){re.escape(x)}(?![\w-])", y, out, count=1)
    return out if out != old else None


# Пометка «жизненно важное» от ИИ ВЫКЛЮЧЕНА (24.09.2026). Два прогона подряд
# модель ошибалась: сперва ДТП с погибшими и курс песо, после закрытого списка
# видов — «бесплатный проезд военным пенсионерам ХОТЯТ дать», «в айыл подвели
# газ», «электронные браслеты». Вид из списка она подбирает к чему угодно, а
# цена ошибки — ложное уведомление в шторке. Жизненно важное ставит точное
# правило по словам (fetch_news.mark_vital_local); вернуть ИИ — только с
# проверкой на наборе настоящих случаев.
VITAL_FROM_AI = False


# Сокращения, после которых точка — не конец предложения. 30.09.2026 Kaktus:
# «Площадь лесов в Кыргызстане составляет 1 млн 273 тыс. гектаров. По данным…»
# — «тыс.» принято за конец обрывка, и целая первая фраза ушла из карточки
_ABBR = {"тыс", "млн", "млрд", "трлн", "руб", "коп", "долл", "евро", "г", "гг", "т", "д", "п",
         "др", "см", "им", "ул", "св", "проф", "акад", "тел", "кв", "км", "м", "кг", "ч",
         "мин", "сек", "обл", "р", "пр", "пл", "стр", "рис", "табл", "mr", "mrs", "dr",
         "vs", "etc", "no", "inc", "ltd", "st", "mln", "bln", "min", "max"}


# То же, что _BAD_START в fetch_news.py: начало, которое предложением быть не может
_BAD_START = re.compile(r"^(?:[…,.;:)\]]|[a-zа-яёөүң](?![A-ZА-ЯЁ]))", re.U)


def _orphan_end(body: str):
    """Позиция после конца первой ЦЕЛОЙ фразы в начале текста — или None.
    Конец — «.!?…», за ним пробел и заглавная буква (или цифра/кавычка), а
    перед точкой не сокращение и не одна буква-инициал."""
    for m in re.finditer(r"([^\s.!?…]*)([.!?…])[»\"”)]?(\s+)(?=[A-ZА-ЯЁ0-9«\"“„(])", body[:300]):
        word = m.group(1).lower()
        if m.group(2) == "." and (word in _ABBR or len(word) <= 1 or word.isdigit()):
            continue
        return m.end()
    return None


# Сколько знаков отдаём читателю без перехода на сайт (то же, что PAGE_BODY_LIMIT
# в fetch_news.py: полторы страницы читалки)
KEEP_LIMIT = 1300
_PROSE_MIN = 80
_JUNK_PARA = re.compile(
    r"^\s*(читайте также|читайте ещё|читайте еще|подписывайтесь|подписаться|"
    r"фото\b|источник\b|реклама|по теме|read also|see also|subscribe)", re.I)


def fill_selection(idx, paras, limit: int = KEEP_LIMIT):
    """Редактор выбирает абзацы, но не вправе вырезать СЕРЕДИНУ статьи.

    06.10.2026, Sputnik KG про Непал: из семи абзацев взяты [1, 3, 4] — второй,
    с главными цифрами (12 электростанций, 1 455 погибших), сочтён
    «второстепенным», и читатель получил 597 знаков вместо 1 570 на сайте.
    Владелец: «это брак». Правило: (1) дыры между выбранными абзацами
    заполняются, если в них настоящий текст; (2) после последнего выбранного
    добираются следующие, пока помещаются в [limit] знаков. Мусорные абзацы
    («читайте также», подписи) не берутся ни там, ни там.
    """
    if not idx or not paras:
        return idx
    def prose(i):
        p = paras[i - 1]
        return len(p) >= _PROSE_MIN and not _JUNK_PARA.match(p)
    chosen = set(idx)
    for i in range(min(idx), max(idx) + 1):
        if i not in chosen and prose(i):
            chosen.add(i)
    total = sum(len(paras[i - 1]) for i in chosen)
    for i in range(max(idx) + 1, len(paras) + 1):
        if not prose(i):
            break                      # дальше обычно хвост издания
        if total + len(paras[i - 1]) > limit:
            break
        chosen.add(i)
        total += len(paras[i - 1])
    return sorted(chosen)


def apply_verdict(item: dict, v: dict, paras, photos, vital_ok=VITAL_FROM_AI):
    """Исполняет решение на КОПИИ карточки. → (выпускать?, копия, заметки)."""
    x = dict(item)
    notes = []
    publish = bool(v.get("publish", True))
    reason = str(v.get("reason") or "").strip().lower()
    # «Интересное» (признак interesting) по причинам «нет события» и «анонс без
    # сути» не снимаем: любопытный факт не событие по белому списку, но ради него
    # источники и заведены (06.10.2026)
    if not publish and item.get("interesting") and reason in ("нет события", "анонс без сути"):
        publish = True
        notes.append("интересное: белый список событий не применяется")
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
    # ПРАВИЛО АБЗАЦЕВ (09.10.2026, textcut.compose_card): редактор КОМПОНУЕТ
    # текст по смыслу (отсекает «воду»), а код держит рамку и замки: до трёх
    # абзацев целиком, последний не берётся, не больше ⌈2n/3⌉ (до 8), заход и
    # абзацы с потерянными цифрами остаются. Окно редактора — начало тех же абзацев, поэтому
    # номера применимы. Нет целой статьи — прежний путь со лимитом по знакам
    full = TC.real_paragraphs(item.get("_full") or "")
    whole = bool(full) and bool(paras) and list(paras) == full[:len(paras)]
    if whole:
        paras = full
        idx = TC.compose_card(paras, idx)
    else:
        idx = fill_selection(sorted(set(idx)), paras)
    if idx and paras:
        body = "\n\n".join(paras[i - 1] for i in idx)
        # Первый выбранный абзац — продолжение оборванной строки: заголовок на
        # странице разбит переносом, редактор выбросил его начало как повтор, а
        # хвост остался — «Премьер-лиге? Спустя два года…» (BBC, 29.09.2026).
        # Обрывок до первой целой фразы снимаем, если после него есть что читать
        prev = paras[idx[0] - 2].rstrip() if idx[0] > 1 else ""
        # Обрывок — это КОРОТКИЙ хвост (несколько слов) за НАСТОЯЩЕЙ оборванной
        # строкой. Короткая надпись без точки («Все самое интересное в
        # Telegram», Kaktus 30.09.2026) оборванной строкой не считается, а
        # целая первая фраза — не хвост: её срезать нельзя
        if prev and len(prev) >= 40 and prev[-1] not in ".!?…:;»\"”)":
            m = _orphan_end(body)
            if m and m <= 40 and len(body) - m >= 80 and not _BAD_START.match(body[m:].lstrip()):
                # и ещё: после среза начало обязано быть началом предложения
                # (строчная буква, запятая, точка — нет). Контроль качества
                # проверяет это ДО редактора, а срез идёт ПОСЛЕ него — без
                # этой проверки итог не смотрел никто (Kaktus, 30.09.2026)
                body = body[m:]
                notes.append("начало с обрывка снято")
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
            # Лучше без фото, чем с чужим лицом: из тела статьи — только
            # снимок, чья подпись говорит о том же, что заголовок
            safe = cand["where"] in ("главное фото страницы", "обложка для соцсетей") or \
                caption_matches(cand.get("alt", ""), x.get("title", ""))
            if not cand["flag"] and cand["where"] != "ссылка на другую статью" and safe:
                x["imageUrl"] = cand["url"]
                notes.append(f"фото: №{ph} вместо №1")
    # Фото проверено: редактор видел снимки страницы с подписями и оставил
    # или выбрал этот. Приложение такое фото своими правилами не заменяет
    # (24.09.2026: оно подменило карточку Kaktus портретом из «По теме»)
    chosen = ph if isinstance(ph, int) else 1
    flagged = bool(photos) and 1 <= chosen <= len(photos) and photos[chosen - 1]["flag"]
    if x.get("imageUrl") and not x.get("_need_photo") and not flagged:
        x["photoChecked"] = True
    # «Срочно» — будит человека уведомлением. Редактор снимает ложное
    if (v.get("urgent") is False and x.get("category") in ("URGENT", "URGENT_LOCAL_ONLY")
            and not x.get("vital")):
        x["category"] = "NEWS"
        x["priority"] = min(int(x.get("priority") or 0), 1)
        notes.append("срочность снята")
    # жизненно важное — только о своей стране
    # Первый прогон в тени (24.09) назвал «жизненно важным» ДТП с погибшими,
    # курс песо, удар по Украине, штраф банку — десяток ложных уведомлений.
    # Пометка принимается только с видом из закрытого списка
    kind = str(v.get("vital_kind") or "").strip().lower()
    if vital_ok and v.get("vital") and x.get("scope") == "local" and kind in VITAL_KINDS:
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
    from collections import Counter
    dossiers = []
    todo = []
    # Почему память не сработала. 05.10.2026: из памяти брались 13–36% карточек,
    # а ПОЧЕМУ — не было видно: новая карточка (нормально) или та же статья с
    # другим текстом (тогда платим за неё дважды)
    misses = Counter()
    for it in items:
        paras = split_paragraphs(it.get("_full") or it.get("summary") or "")
        k = f"{lang}:{cache_key(it)}"
        c = cache.get(k)
        n_now = sum(len(p) for p in paras)
        if (isinstance(c, dict) and c.get("v") == EDITOR_VERSION
                and c.get("n") == n_now):
            dossiers.append([it, c["verdict"], paras, c.get("photos") or []])
        else:
            if not isinstance(c, dict):
                misses["новая"] += 1
            elif c.get("v") != EDITOR_VERSION:
                misses["другая версия правил"] += 1
            elif (c.get("n") or 0) < n_now:
                misses["текст вырос"] += 1
            else:
                misses["текст стал короче"] += 1
            d = [it, None, paras, None]
            dossiers.append(d)
            todo.append(d)
    review.last_misses = dict(misses)
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
    for k in ("reason", "paragraphs", "title", "note", "vital_kind"):
        if src.get(k):
            v[k] = src[k]
    for k in ("need_photo", "vital", "_second", "curious"):
        if src.get(k) is True:
            v[k] = True
    if src.get("urgent") is False:
        v["urgent"] = False
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
            examples.append(f"✗ {r}: [{it.get('source','?')}] {it.get('title','')[:90]}"
                            + (f" — {v.get('note')}" if v.get("note") else ""))
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
                examples.append(f"✂️ [{it.get('source','?')}] {it.get('title','')[:60]} — {n}"
                                + (f"; {v.get('note')}" if v.get("note") else ""))
            elif n == "срочность снята":
                fixes["ложное «срочно» снято"] += 1
                examples.append(f"🔕 [{it.get('source','?')}] {it.get('title','')[:70]}")
            elif n == "жизненно важное":
                vital.append(f"{it.get('title', '')[:70]} ({v.get('vital_kind')})")
        if v.get("_second"):
            examples.append(f"🧑‍⚖️ второй редактор: [{it.get('source','?')}] "
                            f"{it.get('title','')[:60]}")
        if v.get("_second"):
            fixes["перепроверено вторым"] += 1
    return reasons, fixes, examples, vital
