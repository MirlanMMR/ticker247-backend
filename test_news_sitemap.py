# -*- coding: utf-8 -*-
"""Новостная карта сайта как источник — Reuters (09.10.2026).

Reuters закрыл RSS (feeds.reuters.com не существует), но публикует новостную карту в
robots.txt: заголовок, ссылка, время, фото. Образец ниже — настоящая запись с их сайта.
"""
import os
import sys
from unittest.mock import MagicMock

for m in ("google.generativeai", "firebase_admin", "firebase_admin.credentials", "firebase_admin.db"):
    sys.modules[m] = MagicMock()
import google
google.generativeai = sys.modules["google.generativeai"]
os.environ.setdefault("GEMINI_API_KEY", "x")
os.environ["FIREBASE_SERVICE_ACCOUNT"] = "{}"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_news as F

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9" xmlns:image="http://www.google.com/schemas/sitemap-image/1.1">
<url><loc>https://www.reuters.com/business/retail-consumer/chinas-domestic-travel-spend-2026-10-09/</loc><lastmod>2026-10-09T09:05:05.946Z</lastmod><news:news><news:publication><news:name>Reuters</news:name><news:language>en</news:language></news:publication><news:publication_date>2026-10-09T07:13:38.278Z</news:publication_date><news:title>China Golden Week spending per trip hits four-year low amid overseas travel jump</news:title></news:news><image:image><image:loc>https://cloudfront-us-east-2.images.arcpublishing.com/reuters/ELYPA2KLJFLCVDWIVHSOK5ZGOQ.jpg?width=1920</image:loc></image:image></url>
<url><loc>https://www.reuters.com/world/example-2/</loc><news:news><news:publication><news:name>Reuters</news:name><news:language>en</news:language></news:publication><news:publication_date>2026-10-09T08:00:00Z</news:publication_date><news:title>Witkoff, Kushner to meet Ukrainians for talks on the war, says US source</news:title></news:news></url>
<url><loc>https://www.reuters.com/world/example-it/</loc><news:news><news:publication><news:name>Reuters</news:name><news:language>it</news:language></news:publication><news:publication_date>2026-10-09T08:01:00Z</news:publication_date><news:title>Saint Laurent, Vaccarello lascia la direzione creativa</news:title></news:news></url>
<url><loc>https://www.reuters.com/world/no-date/</loc><news:news><news:publication><news:name>Reuters</news:name><news:language>en</news:language></news:publication><news:title>Material without a date</news:title></news:news></url>
</urlset>"""


class R:
    ok = True
    content = XML.encode("utf-8")


src = next(s for s in F.RSS_SOURCES if s["source"] == "Reuters")
F.requests.get = lambda *a, **k: R()

items = F.fetch_rss(src)          # диспетчер fetch_rss должен сам выбрать загрузчик карты
check("диспетчер: источник kind=news_sitemap идёт через fetch_news_sitemap", len(items) == 2)
t = {i["title"]: i for i in items}
a = t["China Golden Week spending per trip hits four-year low amid overseas travel jump"]
check("заголовок, ссылка, источник", a["url"].startswith("https://www.reuters.com/business/") and a["source"] == "Reuters")
check("текста нет намеренно (страницы Reuters закрыты 401)", a["summary"] == "")
check("фото из карты", (a["imageUrl"] or "").endswith("width=1920") and "arcpublishing" in a["imageUrl"])
check("время публикации в миллисекундах (07:13:38 UTC)", a["publishedAt"] == 1791530018278)
check("язык en; чужие языки карты (it) отброшены", a["language"] == "en" and not any("Saint Laurent" in i["title"] for i in items))
check("запись без даты отброшена", not any("without a date" in i["title"] for i in items))
check("приоритет 2 → без текста уходит в строку и уведомления (notifyOnly), не в ленту", a["priority"] == 2)
check("полка world", a["scope"] == "world")

# ── источник описан так, что его увидят дозор и конвейер ──
check("в списке источников есть Reuters с kind=news_sitemap", src.get("kind") == "news_sitemap")
check("адрес — новостная карта www.reuters.com, а не мёртвый feeds.reuters.com", "feeds.reuters.com" not in src["url"] and "news-sitemap" in src["url"])
check("приоритет ≥2: дозор берёт Reuters в быстрые ленты", (src.get("priority") or 0) >= 2)
check("слияние конфига сохраняет kind (код главнее базы)", '"region", "kind")' in open("fetch_news.py", encoding="utf-8").read())
check("квота ограничивает число записей", len(F.fetch_rss({**src, "quota": 1})) == 1)

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
