# -*- coding: utf-8 -*-
"""Разбор ОПУБЛИКОВАННОЙ ленты по всем пулам.

Пользователь читает только русский пул — испанский, португальский и
английский не проверял никто. Все девять бед, найденных 18.08, были найдены
глазами и только в русском. Эта проверка ищет то же самое во всех четырёх и
кричит в журнал прогона.

Никакого ИИ: только признаки, которые видно машинным глазом.
"""
import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

from storydedup import same_story

DB = "https://ticker247-default-rtdb.asia-southeast1.firebasedatabase.app"
# ФРАНЦУЗСКИЙ ЗАБЫЛИ ДОБАВИТЬ. Пул живёт с 27.08, а проверка его не смотрела:
# список пулов правится в одном месте, а заводится в другом. Из-за этого 28.08
# четыре из семи находок оказались именно французскими — их просто не искали
POOLS = ("ru", "en", "es", "pt", "fr")

# Домашняя страна пула: по ней судим, своя ли новость на полке «местные»
HOME = {"ru": "KG", "en": "US", "es": "MX", "pt": "BR", "fr": "FR"}

MARKUP = re.compile(r'data-[\w-]+\s*=\s*"|/>|&[a-z]{2,6};|srcset=|<[a-z]+[\s>]', re.I)
SERVICE = re.compile(
    r"(opens in new window|as your preferred source|sign up now|leia mais em|"
    r"read more at|подпишитесь|читайте также|автором материала является)", re.I)
VIDEO_CAPTION = re.compile(
    r"^\s*(highlights of|watch:|лучшие моменты|обзор матча|melhores momentos|"
    r"lo (más )?destacado|resumen del partido)", re.I)
WEATHER = re.compile(
    r"(прогноз погоды|текущая погода|current weather|weather in|аба ырайы|"
    r"ауа райы|pronóstico del tiempo|previsão do tempo)", re.I)
FILLER = re.compile(r"(гороскоп|horóscopo|wordle|strands|spangram|lottery results)", re.I)
# HTML-подстановки, дошедшие до читателя. Найдено 28.08 в пяти новостях из
# семи с замечаниями. Извлекатели разбирают их сами — НО НЕ ВСЕГДА: текст из
# JSON-LD или из атрибута через разметку не проходит вовсе и остаётся сырым
ENTITY = re.compile(r"&(quot|nbsp|amp|apos|lt|gt|#\d{2,4}|[a-z]{2,8});")

# Кириллица там, где её быть не должно. 28.08 «BBC Русская служба» стояло
# именем издания во ВСЕХ четырёх нерусских пулах, по четыре новости в каждом
CYRILLIC = re.compile(r"[А-Яа-яЁё]")

# Служебные слова чужого языка — чтобы отличить перевод от непереведённого
LANGWORDS = {
    "ru": re.compile(r"\b(что|который|также|после|сообщает|заявил)\b", re.I),
    "en": re.compile(r"\b(the|and|that|with|which|according|said)\b", re.I),
    "es": re.compile(r"\b(que|para|según|también|dijo|los|las)\b", re.I),
    "pt": re.compile(r"\b(que|para|segundo|também|disse|dos|das)\b", re.I),
    "fr": re.compile(r"\b(que|pour|selon|également|dit|les|des)\b", re.I),
}

DANGLING = {"и", "а", "но", "или", "с", "в", "на", "по", "для", "and", "or", "the",
            "of", "in", "to", "for", "with", "de", "da", "do", "e", "y", "que"}


def load(pool):
    with urllib.request.urlopen(f"{DB}/news/{pool}/items.json", timeout=90) as r:
        data = json.load(r)
    rows = data.values() if isinstance(data, dict) else (data or [])
    return [i for i in rows if isinstance(i, dict)]


# ─── Пять пороков, найденных пользователем 30.08.2026 по снимкам ────────────
#
# Он прислал семь снимков и предложил прислать ещё десять. Присылать не нужно:
# ошибки должна искать машина. Но проверить их по ленте задним числом нельзя —
# за час она сменяется, и к моменту проверки виновников уже нет. Поэтому
# проверки живут ЗДЕСЬ: разбор ходит сразу после публикации, и мимо него не
# проскочит ничего.
_CYR = re.compile(r"[а-яёА-ЯЁ]")
_LAT = re.compile(r"[a-zA-Z]")
# Служебные слова редакции, оставшиеся в тексте отдельной строкой
_EDITORIAL = re.compile(r"(?:^|\n)\s*(Смотрим|Читайте|Напомним|Подробности)!?\s*$", re.M)
# Перечень оборван: последняя строка — голый номер или текст кончается
# двоеточием либо точкой с запятой
_CUT_LIST = re.compile(
    r"(?:^|\n)\s*(?:\d{1,2}[.)]\s*$"
    r"|1[-–—](?:чи\s+)?(?:орун\w*|(?:[ео]е?\s+)?место)\b[^\n]*$)",
    re.I,
)


def _latin_share(t: str) -> float:
    c, l = len(_CYR.findall(t)), len(_LAT.findall(t))
    return l / max(1, c + l)


def _head_repeated(body: str) -> bool:
    """Начало текста встречается дальше по нему второй раз.

    Так приходят заметки, где издание кладёт в ленту аннотацию, а потом тот же
    материал целиком: iXBT, Sputnik, РИА. Читатель видит одно и то же дважды.
    """
    b = " ".join(body.split()).lower()
    head = b[:50]
    return len(head) == 50 and b.count(head) > 1


def audit(pool, items):
    """Возвращает словарь: вид беды → список новостей."""
    bad = defaultdict(list)
    for i in items:
        title = i.get("title", "")
        body = (i.get("summary") or "").strip()
        img = i.get("imageUrl") or ""

        if not img.startswith("http") and not i.get("isVideo"):
            bad["без фото"].append(i)
        if MARKUP.search(body):
            bad["разметка в тексте"].append(i)
        if SERVICE.search(body):
            bad["служебный хвост"].append(i)
        if VIDEO_CAPTION.search(body):
            bad["подпись к видеонарезке"].append(i)
        if WEATHER.search(title) or FILLER.search(title):
            bad["погода или гороскоп"].append(i)
        if len(body) < 60 and not i.get("isVideo"):
            bad["пустой текст"].append(i)
        # АННОТАЦИЯ ВМЕСТО СТАТЬИ. Метку fromPage ставит дотяжка, когда тело
        # действительно взято со страницы издания. Её отсутствие при коротком
        # тексте значит, что страницу мы не открывали вовсе, — и читателю
        # ушла строка из RSS под видом новости.
        #
        # Считаем ИМЕННО так, а не по длине: 29.08 рядом стояли аннотация
        # Guardian на 103 знака (со страницы вынимается 26 тысяч) и заметка о
        # золоте Жуманазаровой на 114 — законченная новость. Длина их не
        # различает, происхождение различает.
        # ЗАКРЫТУЮ СТРАНИЦУ НЕ СЧИТАЕМ ЗАМЕЧАНИЕМ. Метку pageClosed ставит
        # дотяжка, увидев 401/403/451: издание не отдаёт нам текст, и никакая
        # правка это не изменит. 31.08.2026 таких было 11 из 22 — половина
        # всех «аннотаций», и они возвращались бы в отчёт каждый прогон
        # вечно. Замечание, которое нельзя устранить, — не замечание, а шум,
        # и он глушит настоящие находки.
        #
        # Считаем их отдельно, не молча: строка «закрыто издателем» в отчёте
        # остаётся, но живёт вне счёта замечаний.
        if len(body) < 300 and not i.get("fromPage") and not i.get("isVideo"):
            if i.get("pageClosed"):
                bad["ⓘ закрыто издателем"].append(i)
            else:
                bad["аннотация вместо статьи"].append(i)
        if len(title) > 25 and body.lower().startswith(title.lower()[:25]):
            bad["заголовок в теле"].append(i)
        # ── пять пороков со снимков 30.08 ──────────────────────────────
        # Заголовок переведён, а текст остался на чужом письме. Пометка
        # «Переведено» при этом врёт, и это хуже отсутствия перевода
        if len(body) > 150:
            if pool == "ru" and _latin_share(body) > 0.6:
                bad["текст не переведён"].append(i)
            elif pool in ("es", "pt", "fr") and len(_CYR.findall(body)) > 30:
                bad["текст не переведён"].append(i)
        if len(body) > 200 and _head_repeated(body):
            bad["текст повторён"].append(i)
        if _CUT_LIST.search(body) or body.rstrip().endswith((":", ";")):
            bad["оборванный перечень"].append(i)
        if re.search(r"[:,]\s*\.", body):
            bad["склейка знаков"].append(i)
        if _EDITORIAL.search(body):
            bad["служебная строка"].append(i)

        if len(body) > 80:
            tail = body.rstrip()
            last = tail.split()[-1].lower().strip(".") if tail.split() else ""
            if tail.endswith((":", "—", ",")) or last in DANGLING:
                bad["текст оборван"].append(i)

    # ── проверки, добавленные 28.08.2026 ────────────────────────────────
    #
    # Все пять — по следам находок, сделанных В ЭТОТ ДЕНЬ РУКАМИ. Пока их
    # искали руками, они прожили в ленте неделю и дольше: пользователь читает
    # только русский пул, а на остальные четыре смотреть было некому.
    for i in items:
        title = i.get("title", "")
        body = (i.get("summary") or "").strip()
        src = i.get("source", "")

        if ENTITY.search(body) or ENTITY.search(title):
            bad["HTML-подстановки в тексте"].append(i)

        # Имя издания кириллицей в нерусском пуле
        if pool != "ru" and CYRILLIC.search(src):
            bad["кириллица в имени издания"].append(i)

        # Текст на чужом для пула языке
        text = f"{title} {body}"
        if len(text) > 60:
            if pool == "ru" and not CYRILLIC.search(text):
                bad["текст не на языке пула"].append(i)
            elif pool != "ru" and CYRILLIC.search(text):
                bad["текст не на языке пула"].append(i)
            elif pool != "ru":
                own = len(LANGWORDS[pool].findall(text))
                alien = max((len(LANGWORDS[p].findall(text))
                             for p in LANGWORDS if p not in (pool, "ru")), default=0)
                if own == 0 and alien >= 3:
                    bad["текст не на языке пула"].append(i)

        # Чужая страна на полке «местные»
        if (i.get("scope") == "local" and i.get("country")
                and i["country"] != HOME.get(pool)):
            bad["чужая страна в «местных»"].append(i)

    # одна картинка у нескольких новостей — логотип издания
    by_img = Counter(i.get("imageUrl") for i in items if (i.get("imageUrl") or "").startswith("http"))
    logos = {u for u, n in by_img.items() if n >= 3}
    bad["логотип вместо фото"] = [i for i in items if i.get("imageUrl") in logos]

    # перекос: одно издание заняло больше пятой части ленты
    by_src = Counter(i.get("source") for i in items)
    hogs = {s for s, n in by_src.items() if n > max(3, len(items) // 5)}
    bad["перекос по издателю"] = [i for i in items if i.get("source") in hogs]

    return {k: v for k, v in bad.items() if v}


def audit_stories(pool):
    """Сюжеты обзора прессы об одном событии.

    28.08 обзор русского пула на ТРИ ЧЕТВЕРТИ состоял из Непала: «Наводнение
    в Непале», «Обрушение ледника в Непале» и «Наводнения в Непале: 469
    погибших» жили порознь. Склейка их не признала двойниками, и заметить это
    можно было только глазами — теперь замечает машина.
    """
    try:
        with urllib.request.urlopen(f"{DB}/news/{pool}/stories.json", timeout=90) as r:
            data = json.load(r)
    except Exception:
        return []
    rows = data.values() if isinstance(data, dict) else (data or [])
    st = [x for x in rows if isinstance(x, dict)]
    pairs = []
    for a in range(len(st)):
        for b in range(a + 1, len(st)):
            if same_story(st[a], st[b]):
                pairs.append((st[a].get("title", ""), st[b].get("title", "")))
    return pairs


# ─── Охват по регионам ──────────────────────────────────────────────────────
#
# Полгода владелец не видел новостей штатов: 03.10.2026 нашлось, что общий
# потолок 120 на 49 регионов оставлял по две карточки на штат. Аудит проверял
# качество текстов, но НЕ ЧИСЛО новостей по регионам, поэтому провал не
# замечался. Эта проверка считает именно его.
MIN_REGION_ITEMS = 3          # меньше — вкладка региона считается пустой

# Сколько регионов предлагает приложение (StatePapers.kt, списки Choice).
# Обновлять вместе с ним: разница с числом лент и есть дыра в источниках.
APP_REGIONS = {"US": 51, "BR": 27, "RU": 85}   # Индия и Мексика убраны 03.10.2026


def configured_regions():
    """Регионы, у которых в бэкенде есть хотя бы одна лента: код → язык пула."""
    here = os.path.dirname(os.path.abspath(__file__))
    out = {}
    try:
        from state_outlets import STATE_RSS
        for r in STATE_RSS:
            if r.get("region"):
                out[r["region"]] = r.get("lang", "en")
    except Exception:
        pass
    try:
        with open(os.path.join(here, "fetch_news.py"), encoding="utf-8") as f:
            for line in f:
                m = re.search(r'"region": "([A-Z]{2}-[A-Z0-9]+)"', line)
                if m:
                    lg = re.search(r'"lang": "(\w+)"', line)
                    out.setdefault(m.group(1), lg.group(1) if lg else "en")
    except Exception:
        pass
    # Регион попадает и из радио/эфиров (MX-NLE и т.п.): там ленты нет и не
    # должно быть — берём только страны, где приложение предлагает регион
    return {c: lg for c, lg in out.items() if c.split("-")[0] in APP_REGIONS}


def region_sources():
    """Ленты по регионам: код региона → [(издание, адрес)]."""
    here = os.path.dirname(os.path.abspath(__file__))
    out = {}
    try:
        from state_outlets import STATE_RSS
        for r in STATE_RSS:
            if r.get("region") and r.get("url"):
                out.setdefault(r["region"], {})[r["source"]] = r["url"]
    except Exception:
        pass
    try:
        with open(os.path.join(here, "fetch_news.py"), encoding="utf-8") as f:
            for line in f:
                m = re.search(r'"url": "([^"]+)", "source": "([^"]+)".*?"region": "([A-Z]{2}-[A-Z0-9]+)"', line)
                if m:
                    out.setdefault(m.group(3), {}).setdefault(m.group(2), m.group(1))
    except Exception:
        pass
    return out


def probe_feed(url):
    """Что отвечает лента: ('ok', записей) или ('err', причина)."""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; Ticker247/1.0)"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read(400000).decode("utf-8", "ignore")
        return "ok", len(re.findall(r"<item[ >]|<entry[ >]", body))
    except urllib.error.HTTPError as e:
        return "err", f"код {e.code}"
    except Exception as e:
        return "err", (type(e).__name__)


def diagnose(thin_codes):
    """Причина слабости каждого региона. Три лекарства, а не одно сообщение:

      • лента не отвечает  → менять адрес или источник;
      • лента пуста        → источник замолчал, ждать или менять;
      • лента жива, а до читателя не дошло → отсеяли наши фильтры (свежесть,
        инфоповод, дубли): смотреть журнал прогона, а не искать источники.
    """
    import concurrent.futures as cf
    srcs = region_sources()
    jobs = [(c, name, url) for c in thin_codes for name, url in srcs.get(c, {}).items()]
    results = {}
    with cf.ThreadPoolExecutor(12) as ex:
        for (c, name, url), res in zip(jobs, ex.map(lambda j: probe_feed(j[2]), jobs)):
            results.setdefault(c, []).append((name, res))
    verdict = {}
    for c in thin_codes:
        rows = results.get(c, [])
        if not rows:
            verdict[c] = ("нет ленты", "")
            continue
        live = [(n, r[1]) for n, r in rows if r[0] == "ok" and r[1] > 0]
        empty = [n for n, r in rows if r[0] == "ok" and r[1] == 0]
        dead = [(n, r[1]) for n, r in rows if r[0] == "err"]
        if live:
            verdict[c] = ("отсеяно фильтрами",
                          ", ".join(f"{n} {k}" for n, k in live[:3]))
        elif empty:
            verdict[c] = ("лента пуста", ", ".join(empty[:3]))
        else:
            verdict[c] = ("не отвечает", ", ".join(f"{n} {why}" for n, why in dead[:3]))
    return verdict


def coverage(pool_items):
    """Новости по регионам. Возвращает (слабых всего, текст для оповещения)."""
    cfg = configured_regions()
    print("\n🗺  ОХВАТ ПО РЕГИОНАМ")
    by_country = Counter(c.split("-")[0] for c in cfg)
    for cc, want in APP_REGIONS.items():
        have = by_country.get(cc, 0)
        mark = "" if have >= want else f"  ⚠ лент нет у {want - have}"
        print(f"  {cc}: регионов в приложении {want}, с лентами {have}{mark}")
    thin_total, thin_all = 0, {}
    for pool, items in pool_items.items():
        counts = Counter(i.get("region") for i in items if i.get("region"))
        mine = sorted(c for c, lg in cfg.items() if lg == pool)
        if not mine:
            continue
        thin = [c for c in mine if counts[c] < MIN_REGION_ITEMS]
        thin_total += len(thin)
        print(f"  [{pool}] регионов с лентами {len(mine)}, "
              f"меньше {MIN_REGION_ITEMS} новостей: {len(thin)}")
        if thin:
            print("      " + ", ".join(f"{c} {counts[c]}" for c in thin))
            for c in thin:
                thin_all[c] = counts[c]
    lines = []
    if thin_all:
        verdict = diagnose(sorted(thin_all))
        groups = {}
        for c, (why, detail) in verdict.items():
            groups.setdefault(why, []).append((c, detail))
        print("  Причины:")
        order = ["не отвечает", "лента пуста", "нет ленты", "отсеяно фильтрами"]
        mark = {"не отвечает": "⛔", "лента пуста": "◻", "нет ленты": "➖",
                "отсеяно фильтрами": "🧹"}
        for why in order:
            rows = groups.get(why)
            if not rows:
                continue
            body = "; ".join(
                f"{c} {thin_all[c]}" + (f" ({d})" if d else "")
                for c, d in rows)
            print(f"      {why}: {len(rows)} — {body}")
            if why == "отсеяно фильтрами":
                # в Telegram — только коды: лента жива, подробности в журнале,
                # а у сообщения лимит 4096 знаков
                short = ", ".join(f"{c} {thin_all[c]}" for c, _ in rows)
                lines.append(f"{mark[why]} {why} ({len(rows)}) — лента жива, новости "
                             f"режутся по пути (свежесть, инфоповод, дубли): {short}")
            else:
                lines.append(f"{mark[why]} {why} ({len(rows)}): {body}")
    try:
        with urllib.request.urlopen(f"{DB}/viral/radio.json", timeout=60) as r:
            radio = json.load(r)
        rows = [x for x in (radio.values() if isinstance(radio, dict) else (radio or []))
                if isinstance(x, dict) and x.get("region")]
        live = {x["region"] for x in rows if x.get("live", True)}
        print(f"  Радио: регионов с живой станцией {len(live)} "
              f"(из {len(cfg)} с лентами; без станции: "
              f"{', '.join(sorted(c.split('-')[1] for c in cfg if c not in live)[:30]) or 'нет'})")
    except Exception as e:
        print(f"  Радио не прочитано: {str(e)[:60]}")
    return thin_total, lines


def main():
    total = 0
    per_pool = {}
    pool_items = {}
    print("\n🔍 РАЗБОР ОПУБЛИКОВАННОЙ ЛЕНТЫ")
    for pool in POOLS:
        try:
            items = load(pool)
        except Exception as e:
            print(f"  [{pool}] не прочитан: {e}")
            continue
        pool_items[pool] = items
        found = audit(pool, items)
        # Виды с «ⓘ» — не замечания, а сведения: то, что мы знаем и приняли.
        # В счёт они не идут, иначе порог оповещения меряет не беду, а фон.
        n = sum(len(v) for k, v in found.items() if not k.startswith("ⓘ"))
        total += n
        per_pool[pool] = n
        scopes = Counter(i.get("scope") for i in items)
        head = (f"  [{pool}] {len(items)} новостей "
                f"(местные {scopes.get('local',0)}, пул {scopes.get('pool',0)}, "
                f"мировые {scopes.get('world',0)}) — замечаний {n}")
        print(head)
        for t1, t2 in audit_stories(pool):
            total += 1
            print(f"      ⚠ обзоры об одном событии: «{t1[:34]}» ⇄ «{t2[:34]}»")
        for kind, group in sorted(found.items(), key=lambda x: -len(x[1])):
            names = ", ".join(sorted({g.get("source", "?") for g in group})[:4])
            print(f"      {kind}: {len(group)} ({names})")
            for g in group[:2]:
                print(f"         · {g.get('title','')[:70]}")
    print(f"  ИТОГО замечаний по всем пулам: {total}")
    notify(total, per_pool)
    # Охват только в журнал, без Telegram: владелец 03.10.2026 — сообщения всё
    # равно пересылаются разработчику, а проверку можно запустить и прочитать
    # самому (python feed_audit.py)
    coverage(pool_items)


# Сколько замечаний считать обычным делом. Порог, а не ноль: часть замечаний
# неустранима нами — «без фото» у La Jornada означает, что издание не даёт
# фотографий, и молчать об этом каждый час незачем.
#
# 28.08.2026 после починки подстановок и имён изданий по всем пяти пулам
# оставалось около десятка. Двадцать — заметный скачок, а не рябь.
ALERT_ABOVE = 20


def notify(total, per_pool):
    """Пишет владельцу в Telegram, если замечаний заметно больше обычного.

    ПОЧЕМУ НЕ КАЖДЫЙ ЧАС. Прогонов двадцать четыре в сутки; сообщение о том,
    что всё как всегда, за неделю станет шумом, и его перестанут читать
    ровно к тому дню, когда оно окажется важным.

    ПИШЕМ В ЛИЧНЫЙ ЧАТ, а не в читательские каналы: это служебное сообщение,
    читателю оно не адресовано. Адрес берётся из TELEGRAM_ADMIN_CHAT. Нет
    адреса — молчим и работаем дальше: оповещение не должно ронять ленту.
    """
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_ADMIN_CHAT")
    if not token or not chat:
        return
    if total <= ALERT_ABOVE:
        print(f"  🔕 Замечаний {total} — в пределах обычного (порог {ALERT_ABOVE})")
        return
    lines = [f"⚠️ Лента: замечаний {total} (обычно до {ALERT_ABOVE})", ""]
    for pool, n in sorted(per_pool.items(), key=lambda x: -x[1]):
        if n:
            lines.append(f"  {pool}: {n}")
    lines += ["", "Подробности — в журнале прогона Actions."]
    try:
        urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=urllib.parse.urlencode({
                "chat_id": chat, "text": "\n".join(lines),
            }).encode(), timeout=20)
        print(f"  📨 Оповещение отправлено: замечаний {total}")
    except Exception as e:
        # Молча продолжаем: не доставленное письмо не повод ронять прогон
        print(f"  · Оповещение не ушло: {str(e)[:60]}")


if __name__ == "__main__":
    main()
