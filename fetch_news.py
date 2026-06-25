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
    # ════════════════════════════════════════════════════
    # МИРОВЫЕ — глобальные издания
    # ════════════════════════════════════════════════════
    {"url": "https://feeds.bbci.co.uk/news/rss.xml", "source": "BBC News", "category": "NEWS", "priority": 2, "quota": 6, "scope": "world"},
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "source": "BBC World", "category": "NEWS", "priority": 2, "quota": 5, "scope": "world"},
    {"url": "https://feeds.reuters.com/reuters/topNews", "source": "Reuters", "category": "NEWS", "priority": 2, "quota": 6, "scope": "world"},
    {"url": "https://www.aljazeera.com/xml/rss/all.xml", "source": "Al Jazeera", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world"},
    {"url": "https://rsshub.app/apnews/topics/apf-topnews", "source": "AP News", "category": "NEWS", "priority": 2, "quota": 5, "scope": "world"},
    {"url": "https://rss.dw.com/rdf/rss-en-all", "source": "Deutsche Welle", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world"},

    # МИРОВОЙ СПОРТ
    {"url": "https://feeds.bbci.co.uk/sport/rss.xml", "source": "BBC Sport", "category": "SPORT", "priority": 1, "quota": 5, "scope": "world"},
    {"url": "https://www.espn.com/espn/rss/news", "source": "ESPN", "category": "SPORT", "priority": 1, "quota": 5, "scope": "world"},
    {"url": "https://www.goal.com/feeds/en/news", "source": "Goal.com", "category": "SPORT", "priority": 1, "quota": 4, "scope": "world"},
    {"url": "https://www.eurosport.com/rss/sport/rss.xml", "source": "Eurosport", "category": "SPORT", "priority": 1, "quota": 4, "scope": "world"},

    # МИРОВЫЕ ТЕХНОЛОГИИ
    {"url": "https://techcrunch.com/feed/", "source": "TechCrunch", "category": "TECH", "priority": 0, "quota": 4, "scope": "world"},
    {"url": "https://www.theverge.com/rss/index.xml", "source": "The Verge", "category": "TECH", "priority": 0, "quota": 4, "scope": "world"},
    {"url": "https://www.wired.com/feed/rss", "source": "Wired", "category": "TECH", "priority": 0, "quota": 3, "scope": "world"},

    # МИРОВЫЕ ФИНАНСЫ
    {"url": "https://feeds.bloomberg.com/politics/news.rss", "source": "Bloomberg", "category": "MONEY", "priority": 1, "quota": 4, "scope": "world"},
    {"url": "https://www.forbes.com/innovation/feed2/", "source": "Forbes", "category": "MONEY", "priority": 0, "quota": 3, "scope": "world"},

    # МИРОВАЯ КУЛЬТУРА
    {"url": "https://variety.com/feed/", "source": "Variety", "category": "CULTURE", "priority": 0, "quota": 3, "scope": "world"},
    {"url": "https://www.rollingstone.com/feed/", "source": "Rolling Stone", "category": "CULTURE", "priority": 0, "quota": 3, "scope": "world"},

    # ════════════════════════════════════════════════════
    # АНГЛОЯЗЫЧНЫЙ МИР (локальные для EN пула)
    # ════════════════════════════════════════════════════
    # США
    {"url": "https://feeds.npr.org/1001/rss.xml", "source": "NPR News", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "en"},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "source": "NY Times", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "en"},
    {"url": "https://feeds.nbcnews.com/nbcnews/public/news", "source": "NBC News", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "en"},
    {"url": "https://rss.cnn.com/rss/edition.rss", "source": "CNN", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "en"},
    {"url": "https://feeds.washingtonpost.com/rss/national", "source": "Washington Post", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "en"},
    {"url": "https://www.politico.com/rss/politicopicks.xml", "source": "Politico", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "en"},
    # Великобритания
    {"url": "https://www.theguardian.com/uk/rss", "source": "The Guardian", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "en"},
    {"url": "https://feeds.skynews.com/feeds/rss/home.xml", "source": "Sky News", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "en"},
    # Технологии EN
    {"url": "https://www.engadget.com/rss.xml", "source": "Engadget", "category": "TECH", "priority": 0, "quota": 4, "scope": "local", "lang": "en"},
    {"url": "https://arstechnica.com/feed/", "source": "Ars Technica", "category": "TECH", "priority": 0, "quota": 4, "scope": "local", "lang": "en"},
    # Спорт EN
    {"url": "https://www.skysports.com/rss/12040", "source": "Sky Sports", "category": "SPORT", "priority": 1, "quota": 5, "scope": "local", "lang": "en"},
    {"url": "https://www.theguardian.com/sport/rss", "source": "Guardian Sport", "category": "SPORT", "priority": 1, "quota": 4, "scope": "local", "lang": "en"},
    # Финансы EN
    {"url": "https://feeds.marketwatch.com/marketwatch/topstories/", "source": "MarketWatch", "category": "MONEY", "priority": 1, "quota": 4, "scope": "local", "lang": "en"},
    # Тренды EN
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=GB", "source": "Trends UK", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "local", "lang": "en"},

    # ════════════════════════════════════════════════════
    # ИСПАНОЯЗЫЧНЫЙ МИР (локальные для ES пула)
    # ════════════════════════════════════════════════════
    {"url": "https://feeds.bbci.co.uk/mundo/rss/noticias/rss.xml", "source": "BBC Mundo", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "es"},
    {"url": "https://www.infobae.com/feeds/rss/", "source": "Infobae", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    {"url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "source": "El País", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    # Латинская Америка
    {"url": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/", "source": "La Nación AR", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    {"url": "https://www.eluniversal.com.mx/rss.xml", "source": "El Universal MX", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    {"url": "https://www.eltiempo.com/rss/colombia.xml", "source": "El Tiempo CO", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "es"},
    {"url": "https://www.latercera.com/feed/", "source": "La Tercera CL", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "es"},
    {"url": "https://www.clarin.com/rss/lo-ultimo/", "source": "Clarín AR", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    {"url": "https://www.univision.com/rss/noticias", "source": "Univisión", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "es"},
    # Спорт ES
    {"url": "https://www.marca.com/rss/portada.xml", "source": "Marca", "category": "SPORT", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    {"url": "https://as.com/rss/tags/ultimo_hora.xml", "source": "AS Deporte", "category": "SPORT", "priority": 1, "quota": 4, "scope": "local", "lang": "es"},
    # Тренды ES
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=MX", "source": "Trends MX", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "local", "lang": "es"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=AR", "source": "Trends AR", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "local", "lang": "es"},

    # ПОРТУГАЛОЯЗЫЧНЫЙ МИР (локальные для PT пула)
    {"url": "https://feeds.bbci.co.uk/portuguese/rss.xml", "source": "BBC Brasil", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "pt"},
    {"url": "https://g1.globo.com/rss/g1/", "source": "G1 Globo", "category": "NEWS", "priority": 2, "quota": 8, "scope": "local", "lang": "pt"},
    {"url": "https://www.publico.pt/rss", "source": "Público PT", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "pt"},
    {"url": "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml", "source": "Folha de S.Paulo", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "pt"},
    {"url": "https://noticias.uol.com.br/ultnot/index.xml", "source": "UOL Notícias", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "pt"},
    {"url": "https://www.correiobraziliense.com.br/rss/ultimas-noticias", "source": "Correio Braziliense", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "pt"},
    {"url": "https://www.jn.pt/rss/", "source": "Jornal de Notícias PT", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "pt"},
    # Спорт PT
    {"url": "https://www.lance.com.br/rss/lancenet.xml", "source": "Lance! BR", "category": "SPORT", "priority": 1, "quota": 4, "scope": "local", "lang": "pt"},
    {"url": "https://www.record.pt/rss", "source": "Record PT", "category": "SPORT", "priority": 1, "quota": 4, "scope": "local", "lang": "pt"},
    # Тренды PT
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=BR", "source": "Trends BR", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "local", "lang": "pt"},

    # АРАБСКИЙ МИР (локальные для AR пула)
    {"url": "https://www.aljazeera.net/rss", "source": "Al Jazeera Arabic", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world"},

    # ════════════════════════════════════════════════════
    # КГ / ЦА — локальные для RU пула
    # ════════════════════════════════════════════════════
    {"url": "https://24.kg/rss/", "source": "24.kg", "category": "NEWS", "priority": 2, "quota": 12, "scope": "local"},
    {"url": "https://kabar.kg/rss/", "source": "Kabar.kg", "category": "NEWS", "priority": 2, "quota": 10, "scope": "local"},
    {"url": "https://akipress.com/rss/news.rss", "source": "AKIpress", "category": "NEWS", "priority": 2, "quota": 12, "scope": "local"},
    {"url": "https://kaktus.media/rss.xml", "source": "Kaktus.media", "category": "NEWS", "priority": 2, "quota": 10, "scope": "local"},
    {"url": "https://sputnik.kg/export/rss2/archive/index.xml", "source": "Sputnik KG", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local"},
    {"url": "https://www.vb.kg/rss.xml", "source": "Вечерний Бишкек", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local"},
    {"url": "https://knews.kg/feed/", "source": "Knews.kg", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local"},
    {"url": "https://www.gezitter.org/rss/", "source": "Gezitter", "category": "NEWS", "priority": 1, "quota": 6, "scope": "local"},

    # Казахстан
    {"url": "https://tengrinews.kz/rss/", "source": "Tengrinews", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local"},
    {"url": "https://www.zakon.kz/rss.xml", "source": "Zakon.kz", "category": "NEWS", "priority": 0, "quota": 3, "scope": "local"},

    # Узбекистан
    {"url": "https://kun.uz/rss/", "source": "Kun.uz", "category": "NEWS", "priority": 0, "quota": 3, "scope": "local"},

    # РОССИЯ
    {"url": "https://ria.ru/export/rss2/archive/index.xml", "source": "РИА Новости", "category": "NEWS", "priority": 1, "quota": 2, "scope": "local"},
    {"url": "https://tass.ru/rss/v2.xml", "source": "ТАСС", "category": "NEWS", "priority": 1, "quota": 2, "scope": "local"},
    {"url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss", "source": "РБК", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local"},

    # РУССКОЯЗЫЧНЫЕ ТЕМАТИЧЕСКИЕ
    {"url": "https://rsport.ria.ru/export/rss2/archive/index.xml", "source": "РИА Спорт", "category": "SPORT", "priority": 1, "quota": 4, "scope": "local"},
    {"url": "https://www.sports.ru/rss/main.xml", "source": "Sports.ru", "category": "SPORT", "priority": 0, "quota": 3, "scope": "local"},
    {"url": "https://habr.com/ru/rss/flows/develop/all/", "source": "Хабр", "category": "TECH", "priority": 0, "quota": 4, "scope": "local"},
    {"url": "https://www.ixbt.com/export/news.rss", "source": "iXBT", "category": "TECH", "priority": 0, "quota": 3, "scope": "local"},
    {"url": "https://www.drive.ru/rss.xml", "source": "Drive.ru", "category": "AUTO", "priority": 0, "quota": 4, "scope": "local"},
    {"url": "https://www.cosmo.ru/rss/all.xml", "source": "Cosmopolitan RU", "category": "FASHION", "priority": 0, "quota": 3, "scope": "local"},
    {"url": "https://www.elle.ru/rss/", "source": "Elle Russia", "category": "FASHION", "priority": 0, "quota": 3, "scope": "local"},
    {"url": "https://www.kino-teatr.ru/rss/news.rss", "source": "Кино-Театр", "category": "CULTURE", "priority": 0, "quota": 4, "scope": "local"},
    {"url": "https://www.tourprom.ru/rss/", "source": "Tourprom", "category": "TOURS", "priority": 0, "quota": 4, "scope": "local"},

    # ТРЕНДЫ
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KG", "source": "Тренды KG", "category": "TRENDS", "priority": 1, "quota": 5, "scope": "local"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US", "source": "Тренды US", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "world"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=RU", "source": "Тренды RU", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "local"},
]

BORING_KEYWORDS = [
    "заседание", "совещание", "пресс-конференция", "протокол",
    "постановление", "регламент", "меморандум", "пленарное",
    "ратификация", "брифинг", "распоряжение"
]

# Источники только на русском/кыргызском
RU_KG_ONLY_SOURCES = {"24.kg", "Kabar.kg", "AKIpress", "Zakon.kz"}

# Жанровые стоп-слова для YouTube (по умолчанию, перезаписываются из Firebase)
YOUTUBE_BLOCK_KEYWORDS = [
    "kpop", "k-pop", "bts", "blackpink", "twice", "stray kids",
    "aespa", "newjeans", "nmixx", "vtuber", "hololive",
    "anime", "аниме", "manga", "манга",
    "official music video", "official video", "official audio",
    "official mv", "lyrics", "lyric video", "music video",
    "official clip", "клип", "премьера клипа"
]

def load_firebase_config():
    """Загружает конфиг из Firebase /config и обновляет глобальные переменные."""
    global RSS_SOURCES, BORING_KEYWORDS, YOUTUBE_BLOCK_KEYWORDS
    try:
        config = db.reference("/config").get()
        if not config:
            print("⚠️ /config в Firebase пуст — используем дефолтные значения")
            return

        # Источники RSS
        if "rss_sources" in config and isinstance(config["rss_sources"], list):
            RSS_SOURCES = config["rss_sources"]
            print(f"✅ Firebase config: {len(RSS_SOURCES)} RSS источников")

        # Скучные ключевые слова
        if "boring_keywords" in config and isinstance(config["boring_keywords"], list):
            BORING_KEYWORDS = config["boring_keywords"]
            print(f"✅ Firebase config: {len(BORING_KEYWORDS)} boring keywords")

        # YouTube стоп-слова
        if "youtube_block_keywords" in config and isinstance(config["youtube_block_keywords"], list):
            YOUTUBE_BLOCK_KEYWORDS = config["youtube_block_keywords"]
            print(f"✅ Firebase config: {len(YOUTUBE_BLOCK_KEYWORDS)} YouTube block keywords")

    except Exception as e:
        print(f"⚠️ Ошибка загрузки Firebase config: {e} — используем дефолтные значения")

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

        # Белый список: только релевантные категории
        # 17=Спорт, 19=Путешествия, 22=Люди и блоги, 23=Юмор, 25=Новости, 28=Наука и техника
        ALLOWED_CATEGORIES = {"17", "19", "22", "23", "25", "28"}

        for video in data.get("items", []):
            snippet = video.get("snippet", {})
            stats = video.get("statistics", {})
            video_id = video.get("id", "")
            views = int(stats.get("viewCount", 0))
            category_id = snippet.get("categoryId", "0")

            # Минимум 500K просмотров
            if views < 500_000:
                continue

            # Только разрешённые категории
            if category_id not in ALLOWED_CATEGORIES:
                continue

            views_str = f"{views/1_000_000:.1f}M" if views >= 1_000_000 else f"{views//1000}K"
            label = "🔥 ВИРАЛЬНО В КГ" if region_code == "KG" else \
                    "🌍 ВИРАЛЬНО В МИРЕ" if region_code == "US" else \
                    f"🔥 ТРЕНД {region_code}"

            title_text = snippet.get("title", "")
            # Пропускаем музыкальные клипы и лирик-видео
            title_lower = title_text.lower()
            if any(kw in title_lower for kw in ["official music video", "official video", "official audio",
                                                 "official mv", "lyrics", "lyric video", "music video",
                                                 "official clip", "клип", "премьера клипа",
                                                 "soundtrack", "ost", "official soundtrack", "score",
                                                 "chapter ", "deltarune", "undertale",
                                                 "trailer", "teaser", "official trailer", "official teaser",
                                                 "anime", "episode ", "season ", "серия ", "сезон "]):
                continue
            # Блокируем только жанровый мусор — берём из Firebase config
            if any(kw in title_lower for kw in YOUTUBE_BLOCK_KEYWORDS):
                continue
            lang = detect_language(title_text) if title_text else "unknown"
            # KG и RU тренды — локальные, US/мировые — world
            scope = "local" if region_code in ("KG", "RU") else "world"
            items.append({
                "title": title_text,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "summary": f"{views_str} просмотров · {snippet.get('channelTitle', '')}",
                "imageUrl": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "source": f"YouTube {region_code}",
                "category": "VIRAL",
                "priority": 1,
                "language": lang,
                "scope": scope,
                "publishedAt": int(datetime.now().timestamp() * 1000),
                "regionCode": region_code,
                "viewCount": views,
                "label": label
            })

        # Сортируем по просмотрам — самые популярные первыми
        items.sort(key=lambda x: x["viewCount"], reverse=True)
        print(f"  ✓ YouTube {region_code}: {len(items)} видео (отфильтровано по 100K+ просмотров)")
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
                "language": lang, "scope": source.get("scope", "world"),
                "source_lang": source.get("lang"),
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
    "URGENT": [
        # Стихийные бедствия
        "землетрясение", "наводнение", "паводок", "сель", "оползень", "лавина",
        "ураган", "тайфун", "торнадо", "цунами", "засуха", "пожар", "лесной пожар",
        # Техногенные катастрофы
        "авиакатастрофа", "крушение", "обрушение", "взрыв", "утечка газа",
        "химическая авария", "радиация", "разлив нефти",
        # ЧС и экстренные службы
        "ЧС", "МЧС", "чрезвычайная ситуация", "режим ЧС", "эвакуация", "спасательная операция",
        # Жертвы
        "погиб", "погибли", "жертвы", "пострадавшие", "ранен", "убит", "найден мёртвым",
        # Коммунальные отключения
        "отключение воды", "отключение света", "отключение электричества", "без воды", "без света",
        "отключат", "веерные отключения", "аварийное отключение",
        # Дороги и транспорт
        "перекрыт", "перекрыли", "закрыт перевал", "дорога закрыта", "ДТП со смертельным",
        "столкновение", "авария на дороге",
        # Здоровье и эпидемии
        "отравление", "отравились", "массовое отравление", "вспышка", "эпидемия",
        "карантин", "опасный вирус", "вспышка инфекции",
        # Безопасность и правопорядок
        "теракт", "стрельба", "захват заложников", "взрывное устройство", "бомба",
        "задержан за коррупцию", "арестован министр", "обыск в министерстве",
        "задержан чиновник", "антикоррупционный рейд",
        # Экономика
        "дефолт", "девальвация", "санкции", "обвал курса", "банкротство банка",
        # Политика
        "государственный переворот", "импичмент", "отставка президента", "военное положение",
        "война", "вооружённый конфликт", "ракетный удар", "объявил войну",
        # Спорт — победы ЦА
        "вышел в финал", "вышел в полуфинал", "вышел в четвертьфинал",
        "завоевал золото", "завоевал медаль", "нокаут", "победил на чемпионате",
        "чемпион мира", "чемпион азии", "рекорд мира",
    ],
    "KG": ["кыргыз", "бишкек", "ош", "кыргызстан", "кыргызча",
           "иссык-куль", "нарын", "джалал-абад", "баткен", "талас", "чуй"],
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

POOL_CONFIG = {
    "ru": {
        "region": "Кыргызстан, Казахстан, Узбекистан, Таджикистан, Россия, Беларусь (СНГ/ЦА)",
        "language_name": "русском",
        "language_rule": "Контент должен быть на русском или кыргызском языке. Всё остальное — удалять.",
    },
    "en": {
        "region": "США, Великобритания, Австралия, Канада",
        "language_name": "английском",
        "language_rule": "Content must be in English. Remove anything in other languages.",
    },
    "es": {
        "region": "Испания, Мексика, Аргентина, Колумбия, Чили (Латинская Америка и Испания)",
        "language_name": "испанском",
        "language_rule": "El contenido debe estar en español. Eliminar todo lo que esté en otros idiomas.",
    },
    "pt": {
        "region": "Бразилия, Португалия",
        "language_name": "португальском",
        "language_rule": "O conteúdo deve estar em português. Remover tudo em outros idiomas.",
    },
}

# Обратная совместимость
REGIONAL_SPORT_PRIORITY = {k: v["region"] for k, v in POOL_CONFIG.items()}

def filter_with_gemini(news_list, lang="ru"):
    if not news_list:
        return news_list

    for item in news_list:
        item["category"] = auto_categorize(item)

    titles = [
        f"{i+1}. [{item['category']}] {item['title']}"
        for i, item in enumerate(news_list)
    ]

    pool = POOL_CONFIG.get(lang, POOL_CONFIG["en"])
    prompt = f"""Ты редактор пула «{lang.upper()}» новостного агрегатора Ticker 24/7.
Аудитория: читатели на {pool['language_name']} языке, регион: {pool['region']}.

═══ ПРАВИЛО №1 — ЯЗЫК (важнее всего остального) ═══
{pool['language_rule']}
Новость о событии в любой стране допустима, если она написана на языке пула.

═══ ПРАВИЛО №2 — ЧТО УДАЛЯТЬ ═══
- Нишевый развлекательный контент не для массовой аудитории (субкультуры, фандомы)
- Музыкальные клипы, тизеры, трейлеры — это реклама, не новость
- Бюрократия без последствий: протоколы, меморандумы, плановые заседания
- Реклама и PR под видом новости
- Исторические справки без актуального повода сегодня
- Кликбейт без содержания
- Дубликаты — оставь одну лучшую версию

═══ ПРАВИЛО №3 — ПРИОРИТЕТЫ ═══
priority=2 — события региона {pool['region']}:
  · ЧС, аварии с жертвами, стихийные бедствия
  · Политика: выборы, отставки, скандалы, аресты чиновников
  · Спорт: победы местных спортсменов, крупные местные турниры
  · Экономика: рост цен, курс валют, дефицит, массовые увольнения
  · Общество: эпидемии, отравления, коммунальные отключения
  · Геополитика мирового масштаба (войны, катастрофы) — для всех пулов

priority=1 — важная мировая повестка:
  · Крупный спорт в разгаре (финалы, рекорды мирового уровня)
  · Технологии: релизы и анонсы которые обсуждает весь мир
  · Культура: массовые премьеры и события

priority=0 — обычные новости

═══ КАТЕГОРИИ ═══
URGENT=экстренное, SPORT=спорт, TECH=технологии, AUTO=авто,
FASHION=мода, CULTURE=кино/музыка/театр, TOURS=туризм,
MONEY=финансы/экономика, HEALTH=здоровье, GOOD=позитив,
STARS=знаменитости, VIRAL=вирусное видео, NEWS=всё остальное

Верни ТОЛЬКО JSON без объяснений:
{{"keep": [1,3,5], "urgent": [2], "important": [3,5], "recategorize": {{"4": "SPORT", "7": "TECH"}}}}

НОВОСТИ:
{chr(10).join(titles[:60])}"""

    try:
        model = genai.GenerativeModel("gemini-2.0-flash")
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
        # Fallback: берём равномерно из всего списка, не только первые 40
        import random
        random.shuffle(news_list)
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

    # Загружаем конфиг из Firebase (источники, фильтры)
    load_firebase_config()

    # Биржевые индексы — Dow Jones, S&P 500, золото, нефть
    print("📊 Индексы...")
    indices = fetch_indices()
    db.reference("/indices").set({
        "items": indices,
        "updatedAt": int(datetime.now().timestamp() * 1000)
    })

    # YouTube вирусные видео — сохраняем отдельно
    print("▶ YouTube trending...")
    viral_kg    = fetch_youtube_trending("KG", 10)
    viral_ru    = fetch_youtube_trending("RU", 8)
    viral_kz    = fetch_youtube_trending("KZ", 5)
    viral_world = fetch_youtube_trending("US", 5)
    viral_br    = fetch_youtube_trending("BR", 8)   # Бразилия — PT пул
    viral_mx    = fetch_youtube_trending("MX", 8)   # Мексика — ES пул
    viral_gb    = fetch_youtube_trending("GB", 5)   # Великобритания — EN пул

    viral_ref = db.reference("/viral")
    viral_ref.set({
        "kg":    viral_kg,
        "ru":    viral_ru,
        "kz":    viral_kz,
        "world": viral_world,
        "br":    viral_br,
        "mx":    viral_mx,
        "gb":    viral_gb,
        "updatedAt": int(datetime.now().timestamp() * 1000)
    })
    print(f"✅ YouTube: KG={len(viral_kg)}, RU={len(viral_ru)}, BR={len(viral_br)}, MX={len(viral_mx)}, GB={len(viral_gb)}, World={len(viral_world)}")
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

    # Мировые новости (scope=world) идут во ВСЕ пулы.
    # Локальные (scope=local) — только в пул по языку статьи.
    CYRILLIC_LANGS = {"ru", "ky", "uk", "be", "bg", "sr", "mk"}
    lang_groups = {"ru": [], "en": [], "es": [], "pt": []}
    ALL_POOLS = list(lang_groups.keys())

    for item in all_news:
        detected_lang = item.get("language", "unknown")
        source_lang   = item.get("source_lang")   # явный язык источника (en/es/pt/ru)
        scope         = item.get("scope", "world")

        if scope == "world":
            for pool in ALL_POOLS:
                lang_groups[pool].append(item)
        else:
            # Если источник явно помечен языком — доверяем ему
            if source_lang in lang_groups:
                lang_groups[source_lang].append(item)
            elif detected_lang in CYRILLIC_LANGS:
                lang_groups["ru"].append(item)
            elif detected_lang == "es":
                lang_groups["es"].append(item)
            elif detected_lang == "pt":
                lang_groups["pt"].append(item)
            else:
                lang_groups["en"].append(item)

    ts = int(datetime.now().timestamp() * 1000)
    all_filtered = []

    for lang, group in lang_groups.items():
        if not group:
            continue
        print(f"\n🌐 [{lang.upper()}] {len(group)} статей → Gemini...")
        filtered = []
        for i in range(0, len(group), 80):
            batch = group[i:i+80]
            filtered_batch = filter_with_gemini(batch, lang)
            filtered.extend(filtered_batch)
        filtered.sort(key=lambda x: x.get("priority", 0), reverse=True)
        max_items = 80 if lang == "ru" else 60
        filtered = filtered[:max_items]
        cats = {}
        for item in filtered:
            cats[item["category"]] = cats.get(item["category"], 0) + 1
        print(f"  После AI: {len(filtered)} | {cats}")
        db.reference(f"/news/{lang}").set({
            "items": filtered,
            "updatedAt": ts,
            "count": len(filtered)
        })
        print(f"  ✅ /news/{lang} сохранено")
        all_filtered.extend(filtered)

    # Постим важные новости в Telegram-канал (из всех языков)
    print("\n📤 Постим в @t247feed...")
    post_to_telegram(all_filtered)

if __name__ == "__main__":
    main()
