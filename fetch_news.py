import os
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, db

# Инициализация
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FIREBASE_DATABASE_URL = os.environ.get("FIREBASE_DATABASE_URL")
FIREBASE_SERVICE_ACCOUNT = os.environ.get("FIREBASE_SERVICE_ACCOUNT")

genai.configure(api_key=GEMINI_API_KEY)

service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT)
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})

# RSS источники
RSS_SOURCES = [
    {"url": "https://ria.ru/export/rss2/archive/index.xml", "source": "РИА Новости", "category": "NEWS", "priority": 1},
    {"url": "https://tass.ru/rss/v2.xml", "source": "ТАСС", "category": "NEWS", "priority": 1},
    {"url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss", "source": "РБК", "category": "NEWS", "priority": 0},
    {"url": "https://lenta.ru/rss/news", "source": "Лента.ру", "category": "NEWS", "priority": 0},
    {"url": "https://24.kg/rss/", "source": "24.kg", "category": "NEWS", "priority": 1},
    {"url": "https://kabar.kg/rss/", "source": "Kabar.kg", "category": "NEWS", "priority": 1},
    {"url": "https://habr.com/ru/rss/flows/develop/all/", "source": "Хабр", "category": "TECH", "priority": 0},
    {"url": "https://www.ixbt.com/export/news.rss", "source": "iXBT", "category": "TECH", "priority": 0},
    {"url": "https://rsport.ria.ru/export/rss2/archive/index.xml", "source": "РИА Спорт", "category": "SPORT", "priority": 1},
    {"url": "https://www.sports.ru/rss/main.xml", "source": "Sports.ru", "category": "SPORT", "priority": 0},
    {"url": "https://www.drive.ru/rss.xml", "source": "Drive.ru", "category": "AUTO", "priority": 0},
    {"url": "https://www.tourprom.ru/rss/", "source": "Tourprom", "category": "TOURS", "priority": 0},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=RU", "source": "Тренды RU", "category": "TRENDS", "priority": 1},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KG", "source": "Тренды KG", "category": "TRENDS", "priority": 1},
]

BORING_KEYWORDS = ["заседание", "совещание", "пресс-конференция", "протокол", "постановление", "регламент"]

def fetch_rss(source):
    try:
        r = requests.get(source["url"], timeout=10, headers={"User-Agent": "Ticker247/1.0"})
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item")[:8]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = item.findtext("description", "").strip()[:200]
            if not title or any(k in title.lower() for k in BORING_KEYWORDS):
                continue
            # Ищем картинку
            image = None
            enclosure = item.find("enclosure")
            if enclosure is not None and "image" in (enclosure.get("type") or ""):
                image = enclosure.get("url")
            items.append({
                "title": title,
                "url": link,
                "summary": desc,
                "imageUrl": image,
                "source": source["source"],
                "category": source["category"],
                "priority": source["priority"],
                "publishedAt": int(datetime.now().timestamp() * 1000)
            })
        return items
    except Exception as e:
        print(f"Error {source['source']}: {e}")
        return []

def filter_with_gemini(news_list):
    if not news_list:
        return news_list

    titles = [f"{i+1}. [{item['category']}] {item['title']}" for i, item in enumerate(news_list)]
    prompt = f"""Ты редактор новостного приложения. Из списка ниже:
1. Убери скучные/неинтересные новости (совещания, протоколы, бюрократия)
2. Убери дубликаты (похожие новости об одном событии — оставь лучшую)
3. Оцени важность: срочные события (МЧС, катастрофы) = 2, важные новости = 1, обычные = 0
4. Верни ТОЛЬКО номера новостей которые нужно оставить в формате JSON:
{{"keep": [1, 3, 5], "urgent": [1], "important": [3]}}

Новости:
{chr(10).join(titles)}

Верни только JSON, без объяснений."""

    try:
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        result = json.loads(text)

        keep_indices = [i-1 for i in result.get("keep", [])]
        urgent_indices = [i-1 for i in result.get("urgent", [])]
        important_indices = [i-1 for i in result.get("important", [])]

        filtered = []
        for i in keep_indices:
            if 0 <= i < len(news_list):
                item = news_list[i].copy()
                if i in urgent_indices:
                    item["priority"] = 2
                elif i in important_indices:
                    item["priority"] = 1
                filtered.append(item)
        return filtered
    except Exception as e:
        print(f"Gemini error: {e}")
        return news_list[:30]

def main():
    print("Fetching RSS feeds...")
    all_news = []
    for source in RSS_SOURCES:
        items = fetch_rss(source)
        all_news.extend(items)
        print(f"  {source['source']}: {len(items)} items")

    print(f"Total: {len(all_news)} articles")
    print("Filtering with Gemini AI...")

    # Обрабатываем батчами по 50
    filtered = []
    for i in range(0, len(all_news), 50):
        batch = all_news[i:i+50]
        filtered_batch = filter_with_gemini(batch)
        filtered.extend(filtered_batch)

    # Сортируем: срочные первыми
    filtered.sort(key=lambda x: x.get("priority", 0), reverse=True)
    filtered = filtered[:60]

    print(f"After AI filter: {len(filtered)} articles")

    # Записываем в Firebase
    ref = db.reference("/news")
    ref.set({
        "items": filtered,
        "updatedAt": int(datetime.now().timestamp() * 1000),
        "count": len(filtered)
    })
    print("Saved to Firebase!")

if __name__ == "__main__":
    main()
