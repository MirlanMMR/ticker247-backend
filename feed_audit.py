# -*- coding: utf-8 -*-
"""Разбор ОПУБЛИКОВАННОЙ ленты по всем пулам.

Пользователь читает только русский пул — испанский, португальский и
английский не проверял никто. Все девять бед, найденных 18.08, были найдены
глазами и только в русском. Эта проверка ищет то же самое во всех четырёх и
кричит в журнал прогона.

Никакого ИИ: только признаки, которые видно машинным глазом.
"""
import json
import re
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
        if len(title) > 25 and body.lower().startswith(title.lower()[:25]):
            bad["заголовок в теле"].append(i)
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


def main():
    total = 0
    print("\n🔍 РАЗБОР ОПУБЛИКОВАННОЙ ЛЕНТЫ")
    for pool in POOLS:
        try:
            items = load(pool)
        except Exception as e:
            print(f"  [{pool}] не прочитан: {e}")
            continue
        found = audit(pool, items)
        n = sum(len(v) for v in found.values())
        total += n
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


if __name__ == "__main__":
    main()
