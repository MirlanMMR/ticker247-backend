# -*- coding: utf-8 -*-
"""ДОБОРКА ТЕКСТА: карточка с анонсом вместо статьи получает статью, когда страница дописана.

Случай (журнал J60, 17.10.2026): CNN Brasil «Caso Dark Horse: PF pede a Mendonça prorrogação do inquérito
por 90 dias». Издание выпустило материал в 22:29 UTC с пометкой «Em atualização» — две фразы. Конвейер
взял его через полчаса, пока на странице было то же, а пул обновляется только в свои слоты; читатель в
11:54 увидел две фразы и подпись «Это анонс издания», хотя на странице уже лежали 3157 знаков (9
абзацев). Аудит ленты в каждом прогоне пишет «аннотация вместо статьи: 7 (CNN Brasil, Observador PT,
Público, RFI)» — и никто на это не отвечает.

Здесь отвечаем. Шаг идёт в patrol.yml (раз в полчаса, без ИИ, только запросы страниц): берёт живую ленту
каждого пула, находит свежие карточки, где текст не со страницы (`fromPage` нет), перечитывает страницу
нашим же разбором и, если статья заметно длиннее и о том же, подменяет `summary` по правилу абзацев
(`textcut.card_text`). Заголовок, фото, полку и прочее не трогает.

Не трогаем: переведённые (текст страницы на другом языке), закрытые издателем, живые блоги и видео,
карточки старше MAX_AGE_H, финансовые. Подмена только при выигрыше ≥ MIN_GAIN знаков и общем сюжете
(≥ MIN_SHARED общих корней слов): разбор мог выхватить чужой абзац.

Запуск:  python reenrich.py            — боевой (нужны ключи базы)
         python reenrich.py --dry      — только посчитать по открытой ленте (REST), ничего не писать
"""
import os
import re
import sys
import time

import requests

from textcut import card_text

MAX_AGE_H = 30
MIN_GAIN = 80
MIN_SHARED = 2
MAX_PER_POOL = 40
POOLS = ("ru", "en", "es", "pt", "fr")
DB = "https://ticker247-default-rtdb.asia-southeast1.firebasedatabase.app/news/{pool}/items.json"
_VIDEO = re.compile(r"youtube\.com|youtu\.be|/video/|/videos/|/watch|vimeo\.com|/live/", re.I)


def _stems(text):
    return {w[:5] for w in re.split(r"[^\w]+", (text or "").lower()) if len(w) > 4}


def wants_upgrade(item, now_ms):
    """Нужна ли карточке доборка: свежая, не со страницы, не закрытая, не переведённая, не видео."""
    if not item:
        return False
    url = str(item.get("url") or "")
    if not url.startswith("http") or _VIDEO.search(url):
        return False
    if item.get("fromPage") or item.get("pageClosed") or item.get("translated"):
        return False
    if item.get("expiresAt") or item.get("category") in ("CURRENCY", "CRYPTO"):
        return False
    if now_ms - (item.get("publishedAt") or 0) > MAX_AGE_H * 3_600_000:
        return False
    return True


def accept_upgrade(item, new_text):
    """Подменять ли текст карточки текстом страницы: заметно длиннее и о том же сюжете."""
    old = (item.get("summary") or "").strip()
    new = (new_text or "").strip()
    if len(new) < len(old) + MIN_GAIN:
        return False
    return len(_stems(item.get("title")) & _stems(new[:800])) >= MIN_SHARED


def plan(items, now_ms, article_of):
    """→ ([(индекс, новый текст)], счётчики). article_of(url) → полный текст страницы или ''."""
    stats = {"кандидатов": 0, "страница пуста": 0, "не лучше": 0, "подменено": 0}
    todo = []
    for i, it in enumerate(items):
        if not wants_upgrade(it, now_ms):
            continue
        stats["кандидатов"] += 1
        if stats["кандидатов"] > MAX_PER_POOL:
            break
        full = article_of(it["url"])
        if not full:
            stats["страница пуста"] += 1
            continue
        new = card_text(full)
        if accept_upgrade(it, new):
            todo.append((i, new))
            stats["подменено"] += 1
        else:
            stats["не лучше"] += 1
    return todo, stats


def _live_article_of():
    import fetch_news as fn
    from concurrent.futures import ThreadPoolExecutor

    def fetch_all(urls):
        with ThreadPoolExecutor(max_workers=8) as pool:
            return dict(zip(urls, pool.map(fn._fetch_page, urls)))
    return fn, fetch_all


def run_live():
    fn, fetch_all = _live_article_of()
    now = int(time.time() * 1000)
    for pool in POOLS:
        items = fn.db.reference(f"/news/{pool}/items").get() or []
        items = items if isinstance(items, list) else list(items.values())
        cands = [it for it in items if wants_upgrade(it, now)][:MAX_PER_POOL]
        pages = fetch_all([it["url"] for it in cands])
        cache = {}

        def article_of(url):                # разбор строго по очереди: lxml не любит потоки
            if url not in cache:
                body = fn._body_from_html(pages.get(url) or b"", url)
                full = fn.ARTICLE_FULL.get(url) or body
                cache[url] = fn.polish_summary(full) if full else ""
            return cache[url]
        todo, stats = plan(items, now, article_of)
        written = 0
        for i, text in todo:
            ref = fn.db.reference(f"/news/{pool}/items/{i}")
            if ref.child("url").get() != items[i]["url"]:
                continue                      # ленту переписали между чтением и записью — не трогаем
            ref.update({"summary": text, "fromPage": True, "textUpgradedAt": now})
            written += 1
            print(f"  📄 [{pool}] текст добран: «{items[i].get('title', '')[:60]}» "
                  f"({items[i].get('source')}) {len(items[i].get('summary') or '')} → {len(text)} знаков")
        print(f"📄 Доборка [{pool}]: {stats}, записано {written}")


def run_dry():
    from extract import extract_article
    now = int(time.time() * 1000)
    ua = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
    total = 0
    for pool in POOLS:
        d = requests.get(DB.format(pool=pool), timeout=30).json() or []
        items = [x for x in (d if isinstance(d, list) else d.values()) if x]

        def article_of(url):
            try:
                r = requests.get(url, headers=ua, timeout=15)
                return extract_article(r.content, url).text if r.ok else ""
            except Exception:
                return ""
        todo, stats = plan(items, now, article_of)
        total += len(todo)
        print(f"{pool}: {stats}")
        for i, text in todo[:6]:
            print(f"    ↑ {items[i].get('source')} | {items[i]['title'][:62]} | {len(items[i].get('summary') or '')} → {len(text)}")
    print(f"ИТОГО подменили бы: {total}")


if __name__ == "__main__":
    run_dry() if "--dry" in sys.argv else run_live()
