# -*- coding: utf-8 -*-
"""Журнал срочного: каждая карточка с меткой «срочно» / «важно» при публикации (04.11.2026).

Зачем. Доверие к метке «срочно» — главное, что мы зарабатываем (EDITORIAL.md), а замерить его было нечем: лента
хранит 36–48 часов, отчёты прогона срочных карточек не перечисляют. Режим «Пейджер» (решение владельца 04.11)
строится целиком на этой метке, поэтому сперва — история. Через 7 / 14 / 30 дней по этому файлу меряется
точность: доля меток, которые соответствуют EDITORIAL.md (свежесть ≤ 3 ч, масштаб, не подготовленное, не слова).

Формат: `urgent_log.jsonl`, одна карточка на строку, без дублей (пул + адрес). Коммитится шагом «Сохранить отчёты».
Только добавление; ничего не читает из ленты, кроме самих карточек. Выключить: URGENT_LOG=off.
"""
import json
import os
import time

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "urgent_log.jsonl")
MARKED = ("URGENT", "URGENT_LOCAL_ONLY")


def marked(x):
    return x.get("category") in MARKED or (x.get("priority") or 0) >= 2


def record(items, lang, path=PATH, now_ms=None):
    """Дописывает новые срочные/важные карточки. → сколько записано."""
    if os.environ.get("URGENT_LOG") == "off":
        return 0
    now_ms = now_ms or int(time.time() * 1000)
    seen = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                    seen.add((r["pool"], r["url"]))
                except Exception:
                    continue
    rows = []
    for x in items:
        if not marked(x) or not x.get("url") or (lang, x["url"]) in seen:
            continue
        pub = x.get("publishedAt") or 0
        rows.append({
            "ts": now_ms, "pool": lang, "url": x["url"], "source": x.get("source"), "title": (x.get("title") or "")[:160],
            "category": x.get("category"), "priority": x.get("priority"), "scope": x.get("scope"),
            "country": x.get("country"), "event_where": x.get("event_where"), "scale": x.get("scale"),
            "published": pub, "age_min": round((now_ms - pub) / 60000) if pub else None,
            "vital": bool(x.get("vital")),
        })
    if rows:
        with open(path, "a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)
