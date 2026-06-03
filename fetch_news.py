import os
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, db

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FIREBASE_DATABASE_URL = os.environ.get("FIREBASE_DATABASE_URL")
FIREBASE_SERVICE_ACCOUNT = os.environ.get("FIREBASE_SERVICE_ACCOUNT")

genai.configure(api_key=GEMINI_API_KEY)
service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT)
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})

# Источники с квотами
RSS_SOURCES = [
    # КГ новости — приоритет
    {"url": "https://24.kg/rss/", "source": "24.kg", "category": "NEWS", "priority": 1, "quota": 8},
    {"url": "https://kabar.kg/rss/", "source": "Kabar.kg", "category": "NEWS", "priority": 1, "quota": 6},
    {"url": "https://akipress.com/rss/news.rss", "source": "AKIpress", "category": "NEWS", "priority": 1, "quota": 5},

    # Мировые новости — ограничены
    {"url": "https://ria.ru/export/rss2/archive/index.xml", "source": "РИА Новости", "category": "NEWS", "priority": 1, "quota": 4},
    {"url": "https://tass.ru/rss/v2.xml", "source": "ТАСС", "category": "NEWS", "priority": 1, "quota": 3},
    {"url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss", "source": "РБК", "category": "NEWS", "priority": 0, "quota": 3},

    # Технологии
    {"url": "https://habr.com/ru/rss/flows/develop/all/", "source": "Хабр", "category": "TECH", "priority": 0, "quota": 5},
    {"url": "https://www.ixbt.com/export/news.rss", "source": "iXBT", "category": "TECH", "priority": 0, "quota": 4},
    {"url": "https://4pda.to/feed/", "source": "4PDA", "category": "TECH", "priority": 0, "quota": 3},

    # Спорт
    {"url": "https://rsport.ria.ru/export/rss2/archive/index.xml", "source": "РИА Спорт", "category": "SPORT", "priority": 1, "quota": 5},
    {"url": "https://www.sports.ru/rss/main.xml", "source": "Sports.ru", "category": "SPORT", "priority": 0, "quota": 4},

    # Авто
    {"url": "https://www.drive.ru/rss.xml", "source": "Drive.ru", "category": "AUTO", "priority": 0, "quota": 5},
    {"url": "https://auto.mail.ru/rss/news/", "source": "Auto.Mail", "category": "AUTO", "priority": 0, "quota": 4},
    {"url": "https://www.drom.ru/rss/news.xml", "source": "Drom.ru", "category": "AUTO", "priority": 0, "quota": 3},

    # Мода
    {"url": "https://www.cosmo.ru/rss/all.xml", "source": "Cosmopolitan", "category": "FASHION", "priority": 0, "quota": 5},
    {"url": "https://www.elle.ru/rss/", "source": "Elle Russia", "category": "FASHION", "priority": 0, "quota": 4},
    {"url": "https://www.goodhouse.ru/rss/", "source": "Good House", "category": "FASHION", "priority": 0, "quota": 3},

    # Кино
    {"url": "https://www.kino-teatr.ru/rss/news.rss", "source": "Кино-Театр", "category": "CULTURE", "priority": 0, "quota": 5},
    {"url": "https://www.kinoafisha.info/rss/news/", "source": "КиноАфиша", "category": "CULTURE", "priority": 0, "quota": 4},

    # Туры
    {"url": "https://www.tourprom.ru/rss/", "source": "Tourprom", "category": "TOURS", "priority": 0, "quota": 5},
    {"url": "https://www.turpravda.ru/rss.xml", "source": "Турправда", "category": "TOURS", "priority": 0, "quota": 4},

    # Недвижимость
    {"url": "https://www.realestate.ru/rss.xml", "source": "RealEstate.ru", "category": "REALTY", "priority": 0, "quota": 4},

    # Тренды
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KG", "source": "Тренды KG", "category": "TRENDS", "priority": 1, "quota": 5},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=RU", "source": "Тренды RU", "category": "TRENDS", "priority": 0, "quota": 5},
]

BORING_KEYWORDS = [
    "заседание", "совещание", "пресс-конференция", "протокол",
    "постановление", "регламент", "меморандум", "пленарное",
    "ратификация", "брифинг", "распоряжение"
]

def fetch_rss(source):
    try:
        r = requests.get(source["url"], timeout=10,
                        headers={"User-Agent": "Mozilla/5.0 Ticker247/1.0"})
        if not r.ok:
            return []
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item")[:source.get("quota", 5)]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()[:200]
            if not title or any(k in title.lower() for k in BORING_KEYWORDS):
                continue
            image = None
            enc = item.find("enclosure")
            if enc is not None and "image" in (enc.get("type") or ""):
                image = enc.get("url")
            if not image:
                for tag in ["media:content", "media:thumbnail"]:
                    el = item.find(tag)
                    if el is not None:
                        url = el.get("url", "")
                        if any(ext in url for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                            image = url
                            break
            items.append({
                "title": title, "url": link, "summary": desc,
                "imageUrl": image, "source": source["source"],
                "category": source["category"], "priority": source["priority"],
                "publishedAt": int(datetime.now().timestamp() * 1000)
            })
        return items
    except Exception as e:
        print(f"  ✗ {source['source']}: {e}")
        return []

def filter_with_gemini(news_list):
    if not news_list:
        return news_list
    titles = [f"{i+1}. [{item['category']}] {item['title']}" for i, item in enumerate(news_list)]
    prompt = f"""Ты редактор новостного приложения для глобальной аудитории.
Из списка ниже:
1. Убери скучные/бюрократические новости
2. Убери дубликаты — оставь лучшую версию
3. Обозначь срочные (катастрофы, ЧП, экстренные события) — priority=2
4. Верни JSON: {{"keep": [1,3,5], "urgent": [2], "important": [4]}}

Новости:
{chr(10).join(titles[:60])}

Только JSON, без объяснений."""

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        result = json.loads(text)
        keep = [i-1 for i in result.get("keep", [])]
        urgent = set(i-1 for i in result.get("urgent", []))
        important = set(i-1 for i in result.get("important", []))
        filtered = []
        for i in keep:
            if 0 <= i < len(news_list):
                item = news_list[i].copy()
                if i in urgent: item["priority"] = 2
                elif i in important: item["priority"] = 1
                filtered.append(item)
        return filtered
    except Exception as e:
        print(f"Gemini error: {e}")
        return news_list[:40]

def main():
    print("🚀 Ticker247 Backend — Fetching news...")
    all_news = []
    category_counts = {}

    for source in RSS_SOURCES:
        items = fetch_rss(source)
        all_news.extend(items)
        cat = source["category"]
        category_counts[cat] = category_counts.get(cat, 0) + len(items)
        if items:
            print(f"  ✓ {source['source']}: {len(items)} items")

    print(f"\nПо категориям: {category_counts}")
    print(f"Всего: {len(all_news)} статей")
    print("🤖 Фильтруем через Gemini AI...")

    filtered = []
    for i in range(0, len(all_news), 60):
        batch = all_news[i:i+60]
        filtered_batch = filter_with_gemini(batch)
        filtered.extend(filtered_batch)

    # Сортируем: срочные первыми, потом по категориям
    filtered.sort(key=lambda x: x.get("priority", 0), reverse=True)
    filtered = filtered[:80]

    # Статистика
    cats = {}
    for item in filtered:
        cats[item["category"]] = cats.get(item["category"], 0) + 1
    print(f"После AI: {len(filtered)} статей")
    print(f"Категории: {cats}")

    ref = db.reference("/news")
    ref.set({
        "items": filtered,
        "updatedAt": int(datetime.now().timestamp() * 1000),
        "count": len(filtered)
    })
    print("✅ Сохранено в Firebase!")

if __name__ == "__main__":
    main()
