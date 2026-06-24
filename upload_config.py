"""
Загружает начальный конфиг в Firebase /config.
Запускать один раз вручную:
  FIREBASE_SERVICE_ACCOUNT=... FIREBASE_DATABASE_URL=... python3 upload_config.py
После этого редактировать конфиг прямо в Firebase Console — без деплоя.
"""
import os
import json
import firebase_admin
from firebase_admin import credentials, db

FIREBASE_DATABASE_URL = os.environ.get("FIREBASE_DATABASE_URL")
FIREBASE_SERVICE_ACCOUNT = os.environ.get("FIREBASE_SERVICE_ACCOUNT")

service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT)
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})

RSS_SOURCES = [
    # ════ МИРОВЫЕ ════
    {"url": "https://feeds.bbci.co.uk/news/rss.xml", "source": "BBC News", "category": "NEWS", "priority": 2, "quota": 6, "scope": "world"},
    {"url": "https://feeds.bbci.co.uk/news/world/rss.xml", "source": "BBC World", "category": "NEWS", "priority": 2, "quota": 5, "scope": "world"},
    {"url": "https://feeds.reuters.com/reuters/topNews", "source": "Reuters", "category": "NEWS", "priority": 2, "quota": 6, "scope": "world"},
    {"url": "https://www.aljazeera.com/xml/rss/all.xml", "source": "Al Jazeera", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world"},
    {"url": "https://rsshub.app/apnews/topics/apf-topnews", "source": "AP News", "category": "NEWS", "priority": 2, "quota": 5, "scope": "world"},
    {"url": "https://rss.dw.com/rdf/rss-en-all", "source": "Deutsche Welle", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world"},
    # Мировой спорт
    {"url": "https://feeds.bbci.co.uk/sport/rss.xml", "source": "BBC Sport", "category": "SPORT", "priority": 1, "quota": 5, "scope": "world"},
    {"url": "https://www.espn.com/espn/rss/news", "source": "ESPN", "category": "SPORT", "priority": 1, "quota": 5, "scope": "world"},
    {"url": "https://www.goal.com/feeds/en/news", "source": "Goal.com", "category": "SPORT", "priority": 1, "quota": 4, "scope": "world"},
    {"url": "https://www.eurosport.com/rss/sport/rss.xml", "source": "Eurosport", "category": "SPORT", "priority": 1, "quota": 4, "scope": "world"},
    # Мировые технологии
    {"url": "https://techcrunch.com/feed/", "source": "TechCrunch", "category": "TECH", "priority": 0, "quota": 4, "scope": "world"},
    {"url": "https://www.theverge.com/rss/index.xml", "source": "The Verge", "category": "TECH", "priority": 0, "quota": 4, "scope": "world"},
    {"url": "https://www.wired.com/feed/rss", "source": "Wired", "category": "TECH", "priority": 0, "quota": 3, "scope": "world"},
    # Мировые финансы
    {"url": "https://feeds.bloomberg.com/politics/news.rss", "source": "Bloomberg", "category": "MONEY", "priority": 1, "quota": 4, "scope": "world"},
    {"url": "https://www.forbes.com/innovation/feed2/", "source": "Forbes", "category": "MONEY", "priority": 0, "quota": 3, "scope": "world"},
    # Мировая культура
    {"url": "https://variety.com/feed/", "source": "Variety", "category": "CULTURE", "priority": 0, "quota": 3, "scope": "world"},
    {"url": "https://www.rollingstone.com/feed/", "source": "Rolling Stone", "category": "CULTURE", "priority": 0, "quota": 3, "scope": "world"},

    # ════ EN (локальные) ════
    {"url": "https://feeds.npr.org/1001/rss.xml", "source": "NPR News", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "en"},
    {"url": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml", "source": "NY Times", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "en"},
    {"url": "https://feeds.nbcnews.com/nbcnews/public/news", "source": "NBC News", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "en"},
    {"url": "https://rss.cnn.com/rss/edition.rss", "source": "CNN", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "en"},
    {"url": "https://feeds.washingtonpost.com/rss/national", "source": "Washington Post", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "en"},
    {"url": "https://www.theguardian.com/uk/rss", "source": "The Guardian", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "en"},
    {"url": "https://feeds.skynews.com/feeds/rss/home.xml", "source": "Sky News", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "en"},
    {"url": "https://www.engadget.com/rss.xml", "source": "Engadget", "category": "TECH", "priority": 0, "quota": 4, "scope": "local", "lang": "en"},
    {"url": "https://arstechnica.com/feed/", "source": "Ars Technica", "category": "TECH", "priority": 0, "quota": 4, "scope": "local", "lang": "en"},
    {"url": "https://www.skysports.com/rss/12040", "source": "Sky Sports", "category": "SPORT", "priority": 1, "quota": 5, "scope": "local", "lang": "en"},
    {"url": "https://feeds.marketwatch.com/marketwatch/topstories/", "source": "MarketWatch", "category": "MONEY", "priority": 1, "quota": 4, "scope": "local", "lang": "en"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=GB", "source": "Trends UK", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "local", "lang": "en"},

    # ════ ES (локальные) ════
    {"url": "https://feeds.bbci.co.uk/mundo/rss/noticias/rss.xml", "source": "BBC Mundo", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "es"},
    {"url": "https://www.infobae.com/feeds/rss/", "source": "Infobae", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    {"url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "source": "El País", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    {"url": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/", "source": "La Nación AR", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    {"url": "https://www.eluniversal.com.mx/rss.xml", "source": "El Universal MX", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    {"url": "https://www.eltiempo.com/rss/colombia.xml", "source": "El Tiempo CO", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "es"},
    {"url": "https://www.latercera.com/feed/", "source": "La Tercera CL", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "es"},
    {"url": "https://www.clarin.com/rss/lo-ultimo/", "source": "Clarín AR", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    {"url": "https://www.marca.com/rss/portada.xml", "source": "Marca", "category": "SPORT", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    {"url": "https://as.com/rss/tags/ultimo_hora.xml", "source": "AS Deporte", "category": "SPORT", "priority": 1, "quota": 4, "scope": "local", "lang": "es"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=MX", "source": "Trends MX", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "local", "lang": "es"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=AR", "source": "Trends AR", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "local", "lang": "es"},

    # ════ PT (локальные) ════
    {"url": "https://feeds.bbci.co.uk/portuguese/rss.xml", "source": "BBC Brasil", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "pt"},
    {"url": "https://g1.globo.com/rss/g1/", "source": "G1 Globo", "category": "NEWS", "priority": 2, "quota": 8, "scope": "local", "lang": "pt"},
    {"url": "https://www.publico.pt/rss", "source": "Público PT", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "pt"},
    {"url": "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml", "source": "Folha de S.Paulo", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "pt"},
    {"url": "https://noticias.uol.com.br/ultnot/index.xml", "source": "UOL Notícias", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "pt"},
    {"url": "https://www.jn.pt/rss/", "source": "Jornal de Notícias PT", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "pt"},
    {"url": "https://www.lance.com.br/rss/lancenet.xml", "source": "Lance! BR", "category": "SPORT", "priority": 1, "quota": 4, "scope": "local", "lang": "pt"},
    {"url": "https://www.record.pt/rss", "source": "Record PT", "category": "SPORT", "priority": 1, "quota": 4, "scope": "local", "lang": "pt"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=BR", "source": "Trends BR", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "local", "lang": "pt"},

    # ════ RU / КГ / ЦА (локальные) ════
    {"url": "https://24.kg/rss/", "source": "24.kg", "category": "NEWS", "priority": 2, "quota": 12, "scope": "local"},
    {"url": "https://kabar.kg/rss/", "source": "Kabar.kg", "category": "NEWS", "priority": 2, "quota": 10, "scope": "local"},
    {"url": "https://akipress.com/rss/news.rss", "source": "AKIpress", "category": "NEWS", "priority": 2, "quota": 12, "scope": "local"},
    {"url": "https://kaktus.media/rss.xml", "source": "Kaktus.media", "category": "NEWS", "priority": 2, "quota": 10, "scope": "local"},
    {"url": "https://sputnik.kg/export/rss2/archive/index.xml", "source": "Sputnik KG", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local"},
    {"url": "https://www.vb.kg/rss.xml", "source": "Вечерний Бишкек", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local"},
    {"url": "https://knews.kg/feed/", "source": "Knews.kg", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local"},
    {"url": "https://www.gezitter.org/rss/", "source": "Gezitter", "category": "NEWS", "priority": 1, "quota": 6, "scope": "local"},
    {"url": "https://tengrinews.kz/rss/", "source": "Tengrinews", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local"},
    {"url": "https://www.zakon.kz/rss.xml", "source": "Zakon.kz", "category": "NEWS", "priority": 0, "quota": 3, "scope": "local"},
    {"url": "https://kun.uz/rss/", "source": "Kun.uz", "category": "NEWS", "priority": 0, "quota": 3, "scope": "local"},
    {"url": "https://ria.ru/export/rss2/archive/index.xml", "source": "РИА Новости", "category": "NEWS", "priority": 1, "quota": 2, "scope": "local"},
    {"url": "https://tass.ru/rss/v2.xml", "source": "ТАСС", "category": "NEWS", "priority": 1, "quota": 2, "scope": "local"},
    {"url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss", "source": "РБК", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local"},
    {"url": "https://rsport.ria.ru/export/rss2/archive/index.xml", "source": "РИА Спорт", "category": "SPORT", "priority": 1, "quota": 4, "scope": "local"},
    {"url": "https://www.sports.ru/rss/main.xml", "source": "Sports.ru", "category": "SPORT", "priority": 0, "quota": 3, "scope": "local"},
    {"url": "https://habr.com/ru/rss/flows/develop/all/", "source": "Хабр", "category": "TECH", "priority": 0, "quota": 4, "scope": "local"},
    {"url": "https://www.ixbt.com/export/news.rss", "source": "iXBT", "category": "TECH", "priority": 0, "quota": 3, "scope": "local"},
    {"url": "https://www.drive.ru/rss.xml", "source": "Drive.ru", "category": "AUTO", "priority": 0, "quota": 4, "scope": "local"},
    {"url": "https://www.cosmo.ru/rss/all.xml", "source": "Cosmopolitan RU", "category": "FASHION", "priority": 0, "quota": 3, "scope": "local"},
    {"url": "https://www.elle.ru/rss/", "source": "Elle Russia", "category": "FASHION", "priority": 0, "quota": 3, "scope": "local"},
    {"url": "https://www.kino-teatr.ru/rss/news.rss", "source": "Кино-Театр", "category": "CULTURE", "priority": 0, "quota": 4, "scope": "local"},
    {"url": "https://www.tourprom.ru/rss/", "source": "Tourprom", "category": "TOURS", "priority": 0, "quota": 4, "scope": "local"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KG", "source": "Тренды KG", "category": "TRENDS", "priority": 1, "quota": 5, "scope": "local"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US", "source": "Тренды US", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "world"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=RU", "source": "Тренды RU", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "local"},
]

BORING_KEYWORDS = [
    "заседание", "совещание", "пресс-конференция", "протокол",
    "постановление", "регламент", "меморандум", "пленарное",
    "ратификация", "брифинг", "распоряжение"
]

YOUTUBE_BLOCK_KEYWORDS = [
    "kpop", "k-pop", "bts", "blackpink", "twice", "stray kids",
    "aespa", "newjeans", "nmixx", "vtuber", "hololive",
    "anime", "аниме", "manga", "манга",
    "official music video", "official video", "official audio",
    "official mv", "lyrics", "lyric video", "music video",
    "official clip", "клип", "премьера клипа"
]

SPAM_PATTERNS = [
    "kpop", "k-pop", "bts", "blackpink", "twice", "stray kids",
    "aespa", "newjeans", "nmixx", "vtuber", "hololive",
    "anime", "аниме", "manga", "манга", "j-pop", "jpop", "дорама", "dorama",
    "official music video", "official video", "official audio", "official mv",
    "lyric video", "music video", "official clip", "премьера клипа",
    "minecraft", "майнкрафт", "roblox", "роблокс", "fortnite",
    "airdrop", "mint now", "buy now", "presale", "whitelist", "nft drop",
    "подпишись и получи", "переходи по ссылке", "реферальн", "промокод"
]

config = {
    "rss_sources": RSS_SOURCES,
    "boring_keywords": BORING_KEYWORDS,
    "youtube_block_keywords": YOUTUBE_BLOCK_KEYWORDS,
    "spam_patterns": SPAM_PATTERNS,
}

db.reference("/config").set(config)
print(f"✅ Конфиг загружен в Firebase /config")
print(f"   RSS источников: {len(RSS_SOURCES)}")
print(f"   Boring keywords: {len(BORING_KEYWORDS)}")
print(f"   YouTube block: {len(YOUTUBE_BLOCK_KEYWORDS)}")
print(f"   Spam patterns: {len(SPAM_PATTERNS)}")
