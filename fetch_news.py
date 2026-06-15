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
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL = "@t247feed"

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

            title_text = snippet.get("title", "")
            lang = detect_language(title_text) if title_text else "unknown"
            items.append({
                "title": title_text,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "summary": f"{views_str} просмотров · {snippet.get('channelTitle', '')}",
                "imageUrl": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "source": f"YouTube {region_code}",
                "category": "VIRAL",
                "priority": 1,
                "language": lang,
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


INDICES = [
    {"symbol": "^DJI",   "name": "Dow Jones", "emoji": "🇺🇸"},
    {"symbol": "^GSPC",  "name": "S&P 500",   "emoji": "📈"},
    {"symbol": "^IXIC",  "name": "NASDAQ",     "emoji": "💻"},
    {"symbol": "GC=F",   "name": "Золото",     "emoji": "🥇"},
    {"symbol": "CL=F",   "name": "Нефть WTI",  "emoji": "🛢️"},
]

def fetch_indices():
    """Биржевые индексы и золото через Yahoo Finance (без ключа)"""
    results = []
    headers = {"User-Agent": "Mozilla/5.0 Ticker247/1.0"}
    for idx in INDICES:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(idx['symbol'])}?interval=1d&range=1d"
            r = requests.get(url, headers=headers, timeout=8)
            if not r.ok:
                continue
            meta = r.json()["chart"]["result"][0]["meta"]
            price = meta["regularMarketPrice"]
            prev  = meta["chartPreviousClose"]
            chg   = (price - prev) / prev * 100 if prev else 0
            arrow = "▲" if chg >= 0 else "▼"
            results.append({
                "symbol": idx["symbol"],
                "name":   idx["name"],
                "emoji":  idx["emoji"],
                "price":  price,
                "change": chg,
                "display": f"{idx['emoji']} {idx['name']} {'${:,.0f}'.format(price) if 'GC' in idx['symbol'] or 'CL' in idx['symbol'] else '{:,.0f}'.format(int(price))} {arrow}{abs(chg):.1f}%"
            })
        except Exception as e:
            print(f"  ✗ {idx['name']}: {e}")
    print(f"  ✓ Indices: {len(results)}")
    return results

def detect_language(text: str) -> str:
    """Определяем язык текста по символам — без внешних библиотек"""
    if not text:
        return "unknown"
    cyrillic = sum(1 for c in text if 'Ѐ' <= c <= 'ӿ')
    latin = sum(1 for c in text if 'a' <= c.lower() <= 'z')
    arabic = sum(1 for c in text if '؀' <= c <= 'ۿ')
    total = max(len(text), 1)
    if cyrillic / total > 0.2:
        return "ru"
    if arabic / total > 0.2:
        return "ar"
    if latin / total > 0.3:
        return "en"
    return "other"

def extract_full_summary(item_el) -> str:
    """Извлекаем полный текст до логической точки — не обрезаем на полуслове"""
    # Пробуем content:encoded — там обычно полная статья
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
    full = item_el.findtext("content:encoded", namespaces=ns) or ""
    if not full:
        full = item_el.findtext("description", "") or ""

    text = clean_text(full)

    # Убираем дубль заголовка в начале текста (частая проблема 24.kg и др.)
    title = clean_text(item_el.findtext("title", ""))
    if title and text.startswith(title):
        text = text[len(title):].lstrip(" .,—-")

    # Берём до 600 символов, но обрезаем по последнему полному предложению
    if len(text) > 600:
        text = text[:600]
        for sep in (". ", "! ", "? ", ".\n"):
            idx = text.rfind(sep)
            if idx > 100:
                text = text[:idx + 1]
                break

    return text.strip()

def fetch_rss(source):
    try:
        r = requests.get(source["url"], timeout=10,
                        headers={"User-Agent": "Mozilla/5.0 Ticker247/1.0"})
        if not r.ok:
            return []
        root = ET.fromstring(r.content)
        items = []
        for item_el in root.findall(".//item")[:source.get("quota", 5)]:
            title = clean_text(item_el.findtext("title", "").strip())
            link = item_el.findtext("link", "").strip()
            summary = extract_full_summary(item_el)
            lang = detect_language(title + " " + summary)

            if not title:
                continue
            if any(k in title.lower() for k in BORING_KEYWORDS):
                continue
            if source["source"] in RU_KG_ONLY_SOURCES and not is_russian_or_kyrgyz(title):
                continue

            image = None
            enc = item_el.find("enclosure")
            if enc is not None and "image" in (enc.get("type") or ""):
                image = enc.get("url")
            if not image:
                for tag in ["media:content", "media:thumbnail"]:
                    el = item_el.find(tag)
                    if el is not None:
                        url_img = el.get("url", "")
                        if any(ext in url_img for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                            image = url_img
                            break

            items.append({
                "title": title, "url": link, "summary": summary,
                "imageUrl": image, "source": source["source"],
                "category": source["category"], "priority": source["priority"],
                "language": lang,
                "publishedAt": int(datetime.now().timestamp() * 1000)
            })
        return items
    except Exception as e:
        print(f"  ✗ {source['source']}: {e}")
        return []

CATEGORY_KEYWORDS = {
    "SPORT": ["футбол", "баскетбол", "UFC", "борьба", "дзюдо", "бокс", "чемпион", "турнир",
              "матч", "спортсмен", "олимпийский", "спорт", "тренер", "команда", "лига"],
    "TECH": ["технологии", "смартфон", "iPhone", "Android", "искусственный интеллект", "ИИ",
             "приложение", "интернет", "компьютер", "программа", "Tesla", "Apple", "Google"],
    "AUTO": ["автомобиль", "машина", "авто", "ДТП", "авария", "дорога", "трафик",
             "электромобиль", "бензин", "топливо", "водитель", "транспорт"],
    "FASHION": ["мода", "стиль", "одежда", "коллекция", "бренд", "дизайнер", "тренд",
                "красота", "макияж", "fashion", "одежда"],
    "CULTURE": ["кино", "фильм", "сериал", "концерт", "музыка", "театр", "выставка",
                "актёр", "режиссёр", "премьера", "шоу", "артист"],
    "TOURS": ["туризм", "тур", "отдых", "курорт", "отель", "путешествие", "виза",
              "Иссык-Куль", "авиа", "рейс", "туристы"],
    "REALTY": ["недвижимость", "квартира", "дом", "аренда", "ипотека", "цена жилья",
               "строительство", "застройщик", "жилой"],
    "URGENT": ["ЧС", "МЧС", "авария", "пожар", "землетрясение", "наводнение", "теракт",
               "взрыв", "обрушение", "эвакуация", "жертвы", "погиб"],
}

def auto_categorize(item: dict) -> str:
    """Определяем категорию по ключевым словам если категория NEWS"""
    if item.get("category") != "NEWS":
        return item.get("category", "NEWS")
    title_lower = item.get("title", "").lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(kw.lower() in title_lower for kw in keywords):
            return category
    return "NEWS"

def filter_with_gemini(news_list):
    if not news_list:
        return news_list

    for item in news_list:
        item["category"] = auto_categorize(item)

    titles = [
        f"{i+1}. [{item['category']}] {item['title']}"
        for i, item in enumerate(news_list)
    ]

    prompt = f"""Ты главный редактор глобального новостного приложения Ticker 24/7.
Приложение работает по всему миру — пользователи видят контент на своём языке.
Твоя задача: отобрать новости которые людям действительно интересно читать прямо сейчас.

ПРИНЦИПЫ ОТБОРА:

1. АКТУАЛЬНОСТЬ ТЕМЫ важнее даты публикации.
   ✓ Новое видео про релиз iPhone 17 — актуально (тема свежая)
   ✗ Статья про историю аналоговой связи — неактуально (тема устарела)
   ✓ Результаты вчерашнего матча ЧМ — актуально
   ✗ Интервью про ВОВ без новостного повода — неактуально

2. КРУПНЫЕ ТЕКУЩИЕ СОБЫТИЯ — обязательно в ленте:
   - Чемпионаты мира и Европы (футбол, хоккей, баскетбол и др.)
   - Титульные бои UFC, бокс (любой вес, любая федерация) — особенно бои с участием атлетов из СНГ
   - Олимпийские игры, Азиатские игры
   - Громкие судебные процессы, политические кризисы
   - Крупные технологические релизы (новый iPhone, Android, AI-модели)
   - Ожидаемые кинопремьеры, музыкальные альбомы, игры
   - Природные катастрофы, теракты, войны

   ВИДЕО > ТЕКСТ: если есть YouTube-видео о событии и текстовая статья о том же —
   видео получает на 1 приоритет выше. Хайлайты боя, обзор матча, распаковка нового гаджета
   всегда интереснее агрегаторной статьи на ту же тему.

3. КЫРГЫЗСТАН И ЦА — особый приоритет:
   - Любой успех кыргызстанского/казахстанского/узбекского спортсмена = priority 2
   - Внутренние события КГ важны для местной аудитории
   - Бойцы: Топурия, Джумагулов, Досмагамбетов, Сидаков и другие ЦА атлеты

4. ЧТО УБИРАТЬ:
   - Бюрократия: заседания, протоколы, меморандумы, брифинги, ратификации
   - Реклама и PR материалы
   - Исторические справки без актуального новостного повода
   - Дубликаты: оставь лучшую версию (предпочти видео, затем — с фото, затем — с длинным текстом)
   - Кликбейт без содержания ("Вы не поверите что случилось...")

5. КАТЕГОРИИ (исправляй если не совпадает с темой):
   URGENT=экстренное, SPORT=спорт, TECH=технологии, AUTO=авто,
   FASHION=мода, CULTURE=кино/музыка/театр, TOURS=туризм,
   MONEY=финансы/экономика, HEALTH=здоровье, GOOD=позитив,
   STARS=знаменитости, VIRAL=вирусное видео, NEWS=всё остальное

6. ПРИОРИТЕТЫ:
   - priority=2: ЧС, теракты, катастрофы, победы ЦА спортсменов, геополитические кризисы
   - priority=1: результаты крупных турниров, громкие преступления, важные технологические новости
   - priority=0: обычные новости

Верни ТОЛЬКО JSON без объяснений:
{{"keep": [1,3,5], "urgent": [2], "important": [3,5], "recategorize": {{"4": "SPORT", "7": "TECH"}}}}

НОВОСТИ:
{chr(10).join(titles[:60])}"""

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
        recategorize = {int(k)-1: v for k, v in result.get("recategorize", {}).items()}
        filtered = []
        for i in keep:
            if 0 <= i < len(news_list):
                item = news_list[i].copy()
                if i in urgent:   item["priority"] = 2
                elif i in important: item["priority"] = 1
                if i in recategorize: item["category"] = recategorize[i]
                filtered.append(item)
        return filtered
    except Exception as e:
        print(f"Gemini error: {e}")
        return news_list[:40]

def shorten_url(url: str) -> str:
    """Сокращаем ссылку через TinyURL (бесплатно, без ключа)."""
    if not url or not url.startswith("http"):
        return url
    try:
        r = requests.get(
            "https://tinyurl.com/api-create.php",
            params={"url": url},
            timeout=5
        )
        if r.status_code == 200 and r.text.startswith("http"):
            return r.text.strip()
    except Exception:
        pass
    return url


CATEGORY_HASHTAGS = {
    "URGENT":  "#Срочно",
    "SPORT":   "#Спорт",
    "TECH":    "#Технологии",
    "AUTO":    "#Авто",
    "FASHION": "#Мода",
    "CULTURE": "#Культура",
    "TOURS":   "#Туризм",
    "MONEY":   "#Деньги",
    "HEALTH":  "#Здоровье",
    "STARS":   "#Звёзды",
    "VIRAL":   "#Вирально",
    "GOOD":    "#Хорошиеновости",
    "NEWS":    "#Новости",
}


def post_to_telegram(items: list):
    """Постим топ-новости в @t247feed. Дедупликация через Firebase /tg_posted."""
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN не задан, пропускаем постинг")
        return

    # Загружаем уже опубликованные URL
    posted_ref = db.reference("/tg_posted")
    posted_data = posted_ref.get() or {}
    posted_urls = set(posted_data.keys() if isinstance(posted_data, dict) else [])

    # Берём только priority >= 2 (срочные/важные), не опубликованные ранее
    candidates = [
        item for item in items
        if item.get("priority", 0) >= 1
        and item.get("url", "") not in posted_urls
        and item.get("category") not in ("CURRENCY", "CRYPTO")
    ]

    # Максимум 5 постов за один запуск
    to_post = candidates[:5]
    if not to_post:
        print("📭 Нет новых важных новостей для постинга в TG")
        return

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    new_posted = {}

    for item in to_post:
        title   = item.get("title", "")
        summary = item.get("summary", "")
        url     = item.get("url", "")
        cat     = item.get("category", "NEWS")
        source  = item.get("source", "")
        hashtag = CATEGORY_HASHTAGS.get(cat, "#Новости")

        short_url = shorten_url(url) if url else ""

        # Формируем текст поста
        text = f"<b>{title}</b>"
        if summary and summary != title:
            # Обрезаем по последнему предложению до 400 символов
            body = summary[:400]
            last_dot = max(body.rfind(". "), body.rfind("! "), body.rfind("? "))
            if last_dot > 100:
                body = body[:last_dot + 1]
            text += f"\n\n{body}"
        if short_url:
            text += f"\n\n🔗 {short_url}"
        text += f"\n\n{hashtag} | 📲 @t247feed"
        if source:
            text += f" | {source}"

        try:
            resp = requests.post(api_url, json={
                "chat_id": TELEGRAM_CHANNEL,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            }, timeout=10)
            if resp.status_code == 200:
                print(f"✅ TG posted: {title[:60]}")
                if url:
                    new_posted[url.replace(".", "_").replace("/", "|")[:100]] = int(datetime.now().timestamp())
            else:
                print(f"❌ TG error {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"❌ TG exception: {e}")

    # Сохраняем опубликованные URL в Firebase
    if new_posted:
        posted_ref.update(new_posted)
        # Чистим старые записи (старше 7 дней) чтобы не накапливались
        cutoff = int(datetime.now().timestamp()) - 7 * 86400
        to_delete = {k: None for k, v in posted_data.items() if isinstance(v, int) and v < cutoff}
        if to_delete:
            posted_ref.update(to_delete)


def main():
    print("🚀 Ticker247 Backend — Fetching news...")

    # Биржевые индексы — Dow Jones, S&P 500, золото, нефть
    print("📊 Индексы...")
    indices = fetch_indices()
    db.reference("/indices").set({
        "items": indices,
        "updatedAt": int(datetime.now().timestamp() * 1000)
    })

    # YouTube вирусные видео — сохраняем отдельно
    print("▶ YouTube trending...")
    viral_kg = fetch_youtube_trending("KG", 10)
    viral_ru = fetch_youtube_trending("RU", 8)
    viral_kz = fetch_youtube_trending("KZ", 5)
    viral_world = fetch_youtube_trending("US", 5)  # мировые — меньше

    viral_ref = db.reference("/viral")
    viral_ref.set({
        "kg": viral_kg,
        "ru": viral_ru,
        "kz": viral_kz,
        "world": viral_world,
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

    # Постим важные новости в Telegram-канал
    print("📤 Постим в @t247feed...")
    post_to_telegram(filtered)

if __name__ == "__main__":
    main()
