import os
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from bs4 import BeautifulSoup
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, db

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FIREBASE_DATABASE_URL = os.environ.get("FIREBASE_DATABASE_URL")
FIREBASE_SERVICE_ACCOUNT = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)
service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT)
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})

# Источники с квотами
RSS_SOURCES = [
    # КГ новости — приоритет
    {"url": "https://24.kg/rss/", "source": "24.kg", "category": "NEWS", "priority": 1, "quota": 8},
    {"url": "https://kabar.kg/rss/", "source": "Kabar.kg", "category": "NEWS", "priority": 1, "quota": 6},
    {"url": "https://akipress.com/rss/news.rss", "source": "AKIpress", "category": "NEWS", "priority": 1, "quota": 8},
    {"url": "https://kaktus.media/rss.xml", "source": "Kaktus.media", "category": "NEWS", "priority": 1, "quota": 6},

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

# Источники только на русском/кыргызском
RU_KG_ONLY_SOURCES = {"24.kg", "Kabar.kg", "AKIpress", "Zakon.kz"}

import re

def clean_text(text: str) -> str:
    """Убираем все HTML entities и мусорные символы"""
    import html
    text = html.unescape(text)  # убирает ВСЕ HTML entities включая &nbsp;
    text = text.replace('\xa0', ' ')  # non-breaking space
    text = text.replace('​', '')  # zero-width space
    text = re.sub(r'<[^>]+>', '', text)  # HTML теги
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def is_russian_or_kyrgyz(text: str) -> bool:
    """True если текст на русском или кыргызском (кириллица преобладает)"""
    cyrillic = sum(1 for c in text if 'Ѐ' <= c <= 'ӿ')
    latin = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    return cyrillic > latin * 0.5  # строже — кириллицы должно быть больше половины латиницы

def fetch_akchаbar_rates():
    """Парсим курсы валют с Акчабара — покупка и продажа по банкам КР"""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"}
        r = requests.get("https://akchаbar.com/ru/currency", timeout=15, headers=headers)
        if not r.ok:
            print(f"  ✗ Акчабар: HTTP {r.status_code}")
            return None

        soup = BeautifulSoup(r.content, "html.parser")
        rates = {}

        # Ищем таблицу курсов
        table = soup.find("table", class_=lambda x: x and "currency" in x.lower()) or \
                soup.find("table")

        if not table:
            print("  ✗ Акчабар: таблица не найдена")
            return None

        target = ["USD", "EUR", "RUB", "CNY", "KZT"]
        rows = table.find_all("tr")

        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 3:
                currency = cells[0].get_text(strip=True).upper()
                if any(t in currency for t in target):
                    code = next((t for t in target if t in currency), None)
                    if code:
                        try:
                            buy = cells[1].get_text(strip=True).replace(",", ".").replace(" ", "")
                            sell = cells[2].get_text(strip=True).replace(",", ".").replace(" ", "")
                            buy_f = float(buy)
                            sell_f = float(sell)
                            if buy_f > 0 and sell_f > 0:
                                rates[code] = {"buy": buy_f, "sell": sell_f}
                        except:
                            pass

        if not rates:
            print("  ✗ Акчабар: курсы не распознаны")
            return None

        # Формируем строку для отображения
        lines = []
        emoji_map = {"USD": "$", "EUR": "€", "RUB": "₽", "CNY": "¥", "KZT": "₸"}
        for code, vals in rates.items():
            em = emoji_map.get(code, "")
            lines.append(f"{em}{code}  {vals['buy']:.2f} / {vals['sell']:.2f}")

        title = " | ".join(lines)
        summary = "\n".join([
            f"{emoji_map.get(c,'')}{c}: покупка {v['buy']:.2f} · продажа {v['sell']:.2f} сом"
            for c, v in rates.items()
        ])

        print(f"  ✓ Акчабар: {len(rates)} валют")
        return {
            "title": title,
            "summary": summary,
            "url": "https://akchаbar.com/ru/currency",
            "imageUrl": None,
            "source": "Акчабар",
            "category": "CURRENCY",
            "priority": 1,
            "publishedAt": int(datetime.now().timestamp() * 1000),
            "rates": rates
        }
    except Exception as e:
        print(f"  ✗ Акчабар ошибка: {e}")
        return None


def fetch_youtube_trending(region_code="KG", max_results=10):
    """Вирусные видео YouTube по региону"""
    try:
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "part": "snippet,statistics",
            "chart": "mostPopular",
            "regionCode": region_code,
            "maxResults": max_results,
            "key": YOUTUBE_API_KEY,
            "videoCategoryId": "0"  # все категории
        }
        r = requests.get(url, params=params, timeout=10)
        if not r.ok:
            print(f"  ✗ YouTube {region_code}: HTTP {r.status_code}")
            return []

        data = r.json()
        items = []
        for video in data.get("items", []):
            snippet = video.get("snippet", {})
            stats = video.get("statistics", {})
            video_id = video.get("id", "")
            views = int(stats.get("viewCount", 0))
            views_str = f"{views/1_000_000:.1f}M" if views >= 1_000_000 else f"{views//1000}K"

            label = "🔥 ВИРАЛЬНО В КГ" if region_code == "KG" else \
                    "🌍 ВИРАЛЬНО В МИРЕ" if region_code == "US" else \
                    f"🔥 ТРЕНД {region_code}"

            items.append({
                "title": snippet.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "summary": f"{views_str} просмотров · {snippet.get('channelTitle', '')}",
                "imageUrl": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "source": f"YouTube {region_code}",
                "category": "VIRAL",
                "priority": 1,
                "publishedAt": int(datetime.now().timestamp() * 1000),
                "regionCode": region_code,
                "viewCount": views,
                "label": label
            })
        print(f"  ✓ YouTube {region_code}: {len(items)} видео")
        return items
    except Exception as e:
        print(f"  ✗ YouTube {region_code}: {e}")
        return []


def fetch_rss(source):
    try:
        r = requests.get(source["url"], timeout=10,
                        headers={"User-Agent": "Mozilla/5.0 Ticker247/1.0"})
        if not r.ok:
            return []
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item")[:source.get("quota", 5)]:
            title = clean_text(item.findtext("title", "").strip())
            link = item.findtext("link", "").strip()
            desc = clean_text(item.findtext("description", "").strip())[:200]

            if not title:
                continue
            # Фильтр скучных новостей
            if any(k in title.lower() for k in BORING_KEYWORDS):
                continue
            # Для КГ/РУ источников — только кириллица
            if source["source"] in RU_KG_ONLY_SOURCES and not is_russian_or_kyrgyz(title):
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
    prompt = f"""Ты редактор новостного приложения для аудитории Кыргызстана и СНГ.
Из списка новостей:
1. Убери скучные/бюрократические (заседания, протоколы, меморандумы)
2. Убери дубликаты — оставь лучшую версию
3. Расставь приоритеты:
   - priority=2 (urgent): ЧС, катастрофы, МЧС, теракты, экстренные события
   - priority=1 (important): спортивные победы атлетов КГ/ЦА, важные политические события,
     крупные назначения, преступления, происшествия, вирусные темы, технологические прорывы
   - priority=0: обычные новости
4. Верни JSON: {{"keep": [1,3,5], "urgent": [2], "important": [3,5]}}

Примеры important: "дзюдоистка КГ выиграла золото", "президент назначил нового министра",
"крупное ДТП в Бишкеке", "новый iPhone представлен"

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

    # YouTube вирусные видео — сохраняем отдельно
    print("▶ YouTube trending...")
    viral_kg = fetch_youtube_trending("KG", 10)
    viral_world = fetch_youtube_trending("US", 10)
    viral_ru = fetch_youtube_trending("RU", 5)

    viral_ref = db.reference("/viral")
    viral_ref.set({
        "kg": viral_kg,
        "world": viral_world,
        "ru": viral_ru,
        "updatedAt": int(datetime.now().timestamp() * 1000)
    })
    print(f"✅ YouTube: KG={len(viral_kg)}, World={len(viral_world)}, RU={len(viral_ru)}")
    all_news = []
    category_counts = {}

    # Акчабар — курсы с покупкой/продажей
    print("💱 Парсим Акчабар...")
    akchаbar = fetch_akchаbar_rates()
    if akchаbar:
        all_news.insert(0, akchаbar)
        category_counts["CURRENCY"] = 1

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
