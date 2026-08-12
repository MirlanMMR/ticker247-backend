import os
import json
import html
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import google.generativeai as genai
import firebase_admin
from firebase_admin import credentials, db

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
FIREBASE_DATABASE_URL = os.environ.get("FIREBASE_DATABASE_URL")
FIREBASE_SERVICE_ACCOUNT = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
# Некоторые сайты (ТАСС и др.) блокируют по простому User-Agent — притворяемся
# обычным браузером, чтобы дозагружать полный текст коротких новостей
BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
}

TELEGRAM_CHANNEL = "@t247feed"
# Языковые каналы: каждый пул постится в свой канал.
# Бот должен быть админом в каждом. Пока канала нет — ставь None, постинг пропустится.
TELEGRAM_CHANNELS = {
    "ru": "@t247feed",
    "en": "@t247feed_en",
    "es": "@t247feed_es",
    "pt": "@t247feed_pt",
}

genai.configure(api_key=GEMINI_API_KEY)
service_account_info = json.loads(FIREBASE_SERVICE_ACCOUNT)
cred = credentials.Certificate(service_account_info)
firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})

# Источники с квотами
RSS_SOURCES = [
    # ════════════════════════════════════════════════════
    # МИРОВЫЕ — глобальные издания
    # ════════════════════════════════════════════════════
    {"url": "https://feeds.bbci.co.uk/russian/rss.xml", "source": "BBC Русская служба", "category": "NEWS", "priority": 2, "quota": 6, "scope": "world", "lang": "ru"},
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
    {"url": "https://www.theguardian.com/uk/rss", "source": "The Guardian", "category": "NEWS", "priority": 2, "quota": 6, "scope": "world", "lang": "en"},
    {"url": "https://feeds.skynews.com/feeds/rss/home.xml", "source": "Sky News", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "en"},
    # Южная Корея — сильная англоязычная пресса специально под международную
    # аудиторию, переводить нечего, забираем как есть (scope=world — не
    # "домашняя" страна пула en, но публикуется на английском)
    {"url": "https://en.yna.co.kr/RSS/news.xml", "source": "Yonhap News", "category": "NEWS", "priority": 2, "quota": 5, "scope": "world", "lang": "en"},
    {"url": "https://feed.koreatimes.co.kr/k/allnews.xml", "source": "Korea Times", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world", "lang": "en"},
    # Технологии EN
    {"url": "https://www.engadget.com/rss.xml", "source": "Engadget", "category": "TECH", "priority": 0, "quota": 4, "scope": "world", "lang": "en"},
    {"url": "https://arstechnica.com/feed/", "source": "Ars Technica", "category": "TECH", "priority": 0, "quota": 4, "scope": "world", "lang": "en"},
    # Спорт EN
    {"url": "https://www.skysports.com/rss/12040", "source": "Sky Sports", "category": "SPORT", "priority": 1, "quota": 5, "scope": "world", "lang": "en"},
    {"url": "https://www.theguardian.com/sport/rss", "source": "Guardian Sport", "category": "SPORT", "priority": 1, "quota": 4, "scope": "world", "lang": "en"},
    # Финансы EN
    {"url": "https://feeds.marketwatch.com/marketwatch/topstories/", "source": "MarketWatch", "category": "MONEY", "priority": 1, "quota": 4, "scope": "local", "lang": "en"},
    # Тренды EN
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=GB", "source": "Trends UK", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "world", "lang": "en"},

    # ════════════════════════════════════════════════════
    # ИСПАНОЯЗЫЧНЫЙ МИР (локальные для ES пула)
    # ════════════════════════════════════════════════════
    {"url": "https://feeds.bbci.co.uk/mundo/rss/noticias/rss.xml", "source": "BBC Mundo", "category": "NEWS", "priority": 2, "quota": 6, "scope": "world", "lang": "es"},
    {"url": "https://www.infobae.com/arc/outboundfeeds/rss/", "source": "Infobae", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "es"},
    {"url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "source": "El País", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "es"},
    # Латинская Америка
    {"url": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/", "source": "La Nación AR", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "es"},
    {"url": "https://www.eluniversal.com.mx/arc/outboundfeeds/rss/", "source": "El Universal MX", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    {"url": "https://www.eltiempo.com/rss/colombia.xml", "source": "El Tiempo CO", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world", "lang": "es"},
    {"url": "https://www.clarin.com/rss/lo-ultimo/", "source": "Clarín AR", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "es"},
    {"url": "https://www.abc.es/rss/feeds/abcPortada.xml", "source": "ABC.es", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "es"},
    {"url": "https://www.excelsior.com.mx/rss/nacional.xml", "source": "Excelsior MX", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "es"},
    # Спорт ES
    {"url": "https://www.marca.com/rss/portada.xml", "source": "Marca", "category": "SPORT", "priority": 1, "quota": 5, "scope": "world", "lang": "es"},
    # Тренды ES
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=MX", "source": "Trends MX", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "world", "lang": "es"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=AR", "source": "Trends AR", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "world", "lang": "es"},

    # ПОРТУГАЛОЯЗЫЧНЫЙ МИР (локальные для PT пула)
    {"url": "https://feeds.bbci.co.uk/portuguese/rss.xml", "source": "BBC Brasil", "category": "NEWS", "priority": 2, "quota": 6, "scope": "world", "lang": "pt"},
    {"url": "https://g1.globo.com/rss/g1/", "source": "G1 Globo", "category": "NEWS", "priority": 2, "quota": 8, "scope": "local", "lang": "pt"},
    {"url": "https://www.publico.pt/rss", "source": "Público PT", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world", "lang": "pt"},
    {"url": "https://feeds.folha.uol.com.br/emcimadahora/rss091.xml", "source": "Folha de S.Paulo", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "pt"},
    {"url": "https://noticias.uol.com.br/ultnot/index.xml", "source": "UOL Notícias", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "pt"},
    {"url": "https://www.cnnbrasil.com.br/feed/", "source": "CNN Brasil", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "pt"},
    {"url": "https://www.terra.com.br/rss/", "source": "Terra BR", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "pt"},
    # Спорт PT
    {"url": "https://www.record.pt/rss", "source": "Record PT", "category": "SPORT", "priority": 1, "quota": 4, "scope": "world", "lang": "pt"},
    # Тренды PT
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=BR", "source": "Trends BR", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "world", "lang": "pt"},

    # ════════════════════════════════════════════════════
    # ВЬЕТНАМ — пул отключён 12.08.2026: аудитории нет, а ИИ отбраковывал
    # весь пул целиком (0 статей из 105). Следующими идут французский и
    # арабский. Источники живые, вернуть можно в любой момент:
    # vnexpress.net/rss/tin-moi-nhat.rss, thanhnien.vn/rss/home.rss,
    # tuoitre.vn/rss/thoi-su.rss

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
    {"url": "https://tengrinews.kz/rss/", "source": "Tengrinews", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world"},
    {"url": "https://www.zakon.kz/rss.xml", "source": "Zakon.kz", "category": "NEWS", "priority": 0, "quota": 3, "scope": "world"},

    # Узбекистан
    {"url": "https://kun.uz/rss/", "source": "Kun.uz", "category": "NEWS", "priority": 0, "quota": 3, "scope": "world"},

    # РОССИЯ — scope=world: местные новости РФ не должны попадать в блок
    # «Местные» пользователей других стран русского пула (КГ, УЗ, KZ и т.д.)
    {"url": "https://ria.ru/export/rss2/archive/index.xml", "source": "РИА Новости", "category": "NEWS", "priority": 1, "quota": 2, "scope": "world"},
    # ТАСС отключён: в RSS отдаёт только подзаголовок в одну строку, а страница
    # статьи закрыта JS-защитой (servicepipe) — не 403, а заглушка с челленджем,
    # которую не обойти без headless-браузера. Итог: в читалке каждая новость
    # ТАСС открывается почти пустой. РИА рядом проверен и работает нормально
    # (страница отдаёт полный текст), поэтому он остаётся
    {"url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss", "source": "РБК", "category": "NEWS", "priority": 0, "quota": 2, "scope": "world"},

    # РУССКОЯЗЫЧНЫЕ ТЕМАТИЧЕСКИЕ
    {"url": "https://rsport.ria.ru/export/rss2/archive/index.xml", "source": "РИА Спорт", "category": "SPORT", "priority": 1, "quota": 4, "scope": "world"},
    {"url": "https://www.sports.ru/rss/main.xml", "source": "Sports.ru", "category": "SPORT", "priority": 0, "quota": 3, "scope": "world"},
    {"url": "https://habr.com/ru/rss/flows/develop/all/", "source": "Хабр", "category": "TECH", "priority": 0, "quota": 4, "scope": "world"},
    {"url": "https://www.ixbt.com/export/news.rss", "source": "iXBT", "category": "TECH", "priority": 0, "quota": 3, "scope": "world"},
    {"url": "https://www.drive.ru/rss.xml", "source": "Drive.ru", "category": "AUTO", "priority": 0, "quota": 4, "scope": "world"},
    {"url": "https://www.cosmo.ru/rss/all.xml", "source": "Cosmopolitan RU", "category": "FASHION", "priority": 0, "quota": 3, "scope": "world"},
    {"url": "https://www.elle.ru/rss/", "source": "Elle Russia", "category": "FASHION", "priority": 0, "quota": 3, "scope": "world"},
    {"url": "https://www.kino-teatr.ru/rss/news.rss", "source": "Кино-Театр", "category": "CULTURE", "priority": 0, "quota": 4, "scope": "world"},
    {"url": "https://www.tourprom.ru/rss/", "source": "Tourprom", "category": "TOURS", "priority": 0, "quota": 4, "scope": "world"},

    # ТРЕНДЫ
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=KG", "source": "Тренды KG", "category": "TRENDS", "priority": 1, "quota": 5, "scope": "world"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US", "source": "Тренды US", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "world"},
    {"url": "https://trends.google.com/trends/trendingsearches/daily/rss?geo=RU", "source": "Тренды RU", "category": "TRENDS", "priority": 0, "quota": 3, "scope": "world"},
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


# ─── Правило «под флагом страны — источники этой страны» ─────────────────────
# В ленте блок «Местные» подписан флагом страны читателя. Значит и лежать там
# должны издания ЭТОЙ страны, а не всего языкового пространства.
#
# Раньше признак стоял вручную у каждого источника и разъезжался: в русском
# пуле местной оказывалась новость РИА (Россия), в английском под британским
# флагом — NY Times (США). Теперь признак вычисляется по домену издания, а
# ручную пометку в списке используем только как подсказку.
#
# Домашняя страна пула: ru → Кыргызстан, en → США, es → Мексика, pt → Бразилия.
# Всё остальное — мировое, даже если написано на языке пула.
LOCAL_DOMAINS = {
    "ru": ["kaktus.media", "sputnik.kg", "vb.kg", "knews.kg", "gezitter.org",
           "kabar.kg", "akipress.com", "24.kg", "turmush.kg", "super.kg", "economist.kg"],
    "en": ["nytimes.com", "npr.org", "nbcnews.com", "cnn.com", "washingtonpost.com",
           "politico.com", "marketwatch.com", "apnews.com", "usatoday.com", "axios.com"],
    "es": ["eluniversal.com.mx", "milenio.com", "excelsior.com.mx", "jornada.com.mx",
           "proceso.com.mx", "elfinanciero.com.mx", "reforma.com"],
    "pt": ["globo.com", "uol.com.br", "folha.uol.com.br", "estadao.com.br",
           "band.uol.com.br", "r7.com", "cnnbrasil.com.br"],
}


# Языковые пулы, которые сейчас выходят в приложении. Источник, помеченный
# языком не отсюда, отбрасывается при загрузке конфига — иначе выключенный пул
# продолжает жить в базе, потому что список источников берётся ИЗ FIREBASE, а не
# из этого файла. Добавляя пул (французский, арабский), впиши его сюда.
ACTIVE_POOLS = ["ru", "en", "es", "pt"]

# Пулы, которые были включены и выключены: их ветки в /news надо подчистить
DISABLED_POOLS = ["vi"]


def normalize_source_scopes(sources):
    """Приводит scope источников к правилу выше. Возвращает исправленный список."""
    dropped = [s for s in sources if s.get("lang") and s["lang"] not in ACTIVE_POOLS]
    if dropped:
        sources = [s for s in sources if s not in dropped]
        names = ", ".join(sorted({s.get("source", "?") for s in dropped}))
        print(f"  🚫 Источники отключённых пулов убраны: {len(dropped)} ({names})")

    changed = 0
    for s in sources:
        url = (s.get("url") or "").lower()
        is_local = any(
            dom in url for doms in LOCAL_DOMAINS.values() for dom in doms
        )
        want = "local" if is_local else "world"
        if s.get("scope") != want:
            changed += 1
            s["scope"] = want
    if changed:
        print(f"  ⚖️ Разметка источников исправлена: {changed}")
    return sources


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
            RSS_SOURCES = normalize_source_scopes(config["rss_sources"])
            # Список берётся ИЗ БАЗЫ и полностью перекрывает зашитый в файле.
            # Из-за этого правки в коде однажды не дали никакого эффекта, а
            # причину искали полдня — поэтому пишем об этом прямо в журнал
            print(f"✅ Источники ИЗ FIREBASE (зашитый список не используется): {len(RSS_SOURCES)}")
            # Возвращаем исправленную разметку обратно в базу, чтобы код и
            # база не расходились
            db.reference("/config/rss_sources").set(RSS_SOURCES)

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


# Категории YouTube, которые нам интересны:
# 25=Новости и политика, 17=Спорт, 28=Наука и техника, 19=Путешествия
VIRAL_CATEGORIES = ("25", "17", "28", "19")

# ─── Белый список YouTube-каналов ────────────────────────────────────────────
# Тренды YouTube — это про популярность, а не про новости: из 24 роликов
# русского блока приходил 21 разный канал, и почти все блогерские
# («Wow iPhone !», «Напрыгал на 1,5 млн долларов», шортсы с рекламой в кадре).
# Отсеивать такое после факта бессмысленно, поэтому берём видео ПРЯМО с
# отобранных каналов: кроме них попасть в блок нечему.
#
# Принцип отбора — нейтральные вещатели, не только новостные: то, что
# действительно стоит внимания, выходит и у них.
#
# Каждый канал проверен живьём 11.08.2026: лента отдаёт свежие видео.
# Ленты BBC News Русская служба и DW на русском отдают 404 при живых каналах —
# не использовать, нужен путь через API с ключом.
# Список пересматривать примерно раз в три месяца.
YOUTUBE_CHANNELS = {
    "ru": [
        ("UCBG57608Hukev3d0d-gvLhQ", "Настоящее Время",      "world"),
        ("UCztZRXyQNaQuJZtS0GM95Zw", "Настоящее Время. Сюжеты", "world"),
        ("UCFzJjgVicCtFxJ5B0P_ei8A", "Euronews по-русски",   "world"),
        ("UC5yuKBFjaEgLarSi2auKgag", "Азаттык Азия",         "local"),
        ("UCxfxoGrNe4uXrNeBgeESGFQ", "Kyrgyz Sport TV",      "local"),
    ],
    "en": [
        ("UC16niRr50-MSBwiO3YDb3RA", "BBC News",             "world"),
        ("UChqUTb7kYRX8-EiaN3XFrSQ", "Reuters",              "world"),
        ("UCknLrEdhRCp1aegoMqRaCZg", "DW News",              "world"),
        ("UCoMdktPbSTixAyNGwb-UYkQ", "Sky News",             "local"),
        ("UC52X5wxOL_s5yw0dQk7NtgA", "Associated Press",     "world"),
        ("UCHnyfMqiRRG1u-2MsSQLbXA", "Veritasium",           "world"),
        ("UCupvZG-5ko_eiXAupbDfxWw", "CNN",                  "world"),
        ("UCNye-wNBqNL5ZzHSJj3l8Bg", "Al Jazeera English",   "world"),
    ],
    "es": [
        ("UCT4Jg8h03dD0iN3Pb5L0PMA", "DW Español",           "world"),
        ("UCyoGb3SMlTlB8CLGVH4c8Rw", "euronews en español",  "world"),
        ("UC7QZIf0dta-XPXsp9Hv4dTw", "RTVE Noticias",        "local"),
    ],
    "pt": [
        ("UCaGmdJSSiR7fkh2A-c6emsA", "g1",                   "local"),
        ("UCp6RRaz93Pt2xYZoEye_rLA", "GloboNews",            "world"),
    ],
}


# Служебные ролики одобренных каналов, которые новостями не являются.
# Пополняется одной строкой; сверяется вхождением в название, регистр не важен

# ─── Радиостанции ────────────────────────────────────────────────────────────
# Список живёт здесь, а не в приложении: адреса потоков переезжают, и без
# этого узла умершая станция чинилась бы только обновлением в Play.
# В приложении остаётся такой же зашитый список — как запасной, на случай
# недоступной сети.
#
# Отбор: серьёзные вещатели, деловые и общественные, без музыкальных.
# Все потоки проверены живьём 11.08.2026.
RADIO_STATIONS = [
    # ru: нейтральных новостных радио почти не осталось, поэтому деловые
    {"name": "РБК",              "url": "https://rbcreg.hostingradio.ru/rbc32.aacp",                                  "pool": "ru", "colorFrom": "FF1F3A5F", "colorTo": "FF2E6CA8"},
    {"name": "Коммерсантъ FM",   "url": "https://kommersant77.hostingradio.ru:8085/kommersant128.mp3",                 "pool": "ru", "colorFrom": "FF4A2B1E", "colorTo": "FF8A5A3B"},
    {"name": "Бизнес FM",        "url": "https://bfm.hostingradio.ru:9075/fm",                                        "pool": "ru", "colorFrom": "FF1E3B32", "colorTo": "FF2F7A63"},
    {"name": "Радио МИР",        "url": "https://icecast-mirtv.cdnvideo.ru/radio_mir_256",                             "pool": "ru", "colorFrom": "FF2B2350", "colorTo": "FF5B4BA8"},

    {"name": "BBC World Service","url": "http://stream.live.vc.bbcmedia.co.uk/bbc_world_service",                      "pool": "en", "colorFrom": "FF3B1F24", "colorTo": "FF8C2F39"},
    {"name": "NPR",              "url": "http://npr-ice.streamguys1.com/live.mp3",                                     "pool": "en", "colorFrom": "FF1D3247", "colorTo": "FF2E6B8F"},
    {"name": "Times Radio",      "url": "https://timesradio.wireless.radio/stream",                                    "pool": "en", "colorFrom": "FF22303C", "colorTo": "FF44637D"},

    {"name": "Cadena SER",       "url": "http://playerservices.streamtheworld.com/api/livestream-redirect/CADENASER.mp3","pool": "es", "colorFrom": "FF3A2036", "colorTo": "FF7C3F6E"},
    {"name": "COPE",             "url": "http://flucast13-h-cloud.flumotion.com/cope/net1.mp3",                        "pool": "es", "colorFrom": "FF20303A", "colorTo": "FF3F6C82"},
    {"name": "Catalunya Informació","url": "https://shoutcast.ccma.cat/ccma/catalunyainformacioHD.mp3",                "pool": "es", "colorFrom": "FF33291C", "colorTo": "FF7A6134"},
    {"name": "W Radio",          "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/WRADIOAAC.aac","pool": "es", "colorFrom": "FF2A1F3D", "colorTo": "FF5C3F87"},
    {"name": "El Heraldo Radio", "url": "https://stream.radiojar.com/ce31v3yah8nwv",                                   "pool": "es", "colorFrom": "FF3A1F2A", "colorTo": "FF7E3F5C"},
    {"name": "Radio UNAM",       "url": "https://tv.radiohosting.online:9486/stream",                                  "pool": "es", "colorFrom": "FF1F3A2E", "colorTo": "FF357E62"},
    {"name": "Caracol Radio",    "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/CARACOL_RADIOAAC.aac","pool": "es", "colorFrom": "FF3D2A1F", "colorTo": "FF8A5B33"},

    {"name": "BandNews FM",      "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/BANDNEWSFM_SP_ADP.aac","pool": "pt", "colorFrom": "FF1F3340", "colorTo": "FF2F6C88"},
    {"name": "CBN São Paulo",    "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/CBN_SP_ADP.aac","pool": "pt", "colorFrom": "FF23302A", "colorTo": "FF3D7A5F"},
    {"name": "CBN Rio",          "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/CBN_RJ_ADP.aac","pool": "pt", "colorFrom": "FF2B2438", "colorTo": "FF574A80"},
    {"name": "Rádio Itatiaia",   "url": "https://8903.brasilstream.com.br/stream",                                     "pool": "pt", "colorFrom": "FF3A2622", "colorTo": "FF7E4C3D"},
    {"name": "Renascença",       "url": "http://22653.live.streamtheworld.com/RADIO_RENASCENCA_SC",                    "pool": "pt", "colorFrom": "FF1E2A3A", "colorTo": "FF3C5B85"},
]

# ─── Прямые эфиры ────────────────────────────────────────────────────────────
# Круглосуточные трансляции для плиток «прямой эфир» в ленте.
#
# Ссылка на эфир НЕ постоянная: трансляция — это обычное видео со своим
# номером, и когда канал останавливает вещание и запускает новое, номер
# меняется. Зашить его в приложение нельзя — через сутки будут мёртвые плитки.
# Поэтому номер спрашиваем у YouTube и кладём в базу, а приложение играет то,
# что лежит там.
#
# Запрос «что сейчас в эфире» относится у YouTube к поисковым и стоит 100
# единиц квоты вместо одной, поэтому обновляем НЕ ЧАЩЕ раза в три часа:
# около 2400 единиц в сутки при лимите 10 000. Трансляции живут дольше трёх
# часов, так что на глаз разницы нет.
#
# Просмотры пользователей нашу квоту не тратят вообще — видео идёт от YouTube
# напрямую. Квота уходит только на эти восемь запросов в сутки на канал.
LIVE_CHANNELS = [
    ("UCoMdktPbSTixAyNGwb-UYkQ", "Sky News",           "en"),
    ("UCNye-wNBqNL5ZzHSJj3l8Bg", "Al Jazeera English", "en"),
    ("UCFzJjgVicCtFxJ5B0P_ei8A", "Euronews по-русски", "ru"),
]

LIVE_REFRESH_HOURS = 3


def fetch_live_streams():
    """Ссылки на текущие эфиры для узла /viral/live.

    Ничего не пишет сама, а ВОЗВРАЩАЕТ готовый кусок: запись /viral идёт
    целиком и стёрла бы вложенный узел сразу после его создания. Поэтому
    эфиры кладутся вместе с остальным виральным в один приём.

    Если обновлять рано или не получилось — возвращает прежние данные, чтобы
    они не пропали при перезаписи /viral.
    """
    # Узел внутри /viral, а не отдельный /live: в правах боевой базы открыты
    # на чтение только news и viral, а отдельный узел пришлось бы открывать
    # руками в консоли Firebase. По смыслу данные родственные — и там и там
    # видео с YouTube
    ref = db.reference("/viral/live")
    try:
        existing = ref.get() or {}
    except Exception:
        existing = {}

    now_ms = int(datetime.now().timestamp() * 1000)
    updated_at = existing.get("updatedAt", 0) if isinstance(existing, dict) else 0
    if now_ms - updated_at < LIVE_REFRESH_HOURS * 3600 * 1000:
        age_h = (now_ms - updated_at) / 3600000
        print(f"  ⏭ Эфиры: обновлялись {age_h:.1f} ч назад, пропускаем (раз в {LIVE_REFRESH_HOURS} ч)")
        return existing

    items = []
    for channel_id, name, pool in LIVE_CHANNELS:
        try:
            r = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "channelId": channel_id,
                    "eventType": "live",
                    "type": "video",
                    "maxResults": 1,
                    "key": YOUTUBE_API_KEY,
                },
                timeout=15,
            )
            if r.status_code == 403:
                # Квота исчерпана — прекращаем совсем, чтобы не долбиться
                # впустую. Старые ссылки остаются в базе: трансляция идёт
                # сутками, и, скорее всего, они ещё рабочие
                print("  ✗ Эфиры: квота YouTube исчерпана, оставляем прежние ссылки")
                return existing
            if not r.ok:
                print(f"  ✗ Эфир {name}: HTTP {r.status_code}")
                continue
            found = r.json().get("items", [])
            if not found:
                print(f"  · Эфир {name}: сейчас не вещает")
                continue
            entry = found[0]
            video_id = entry.get("id", {}).get("videoId")
            snippet = entry.get("snippet", {})
            if not video_id:
                continue
            thumbs = snippet.get("thumbnails", {})
            items.append({
                "channelId": channel_id,
                "name": name,
                "pool": pool,
                "videoId": video_id,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "title": (snippet.get("title") or name).strip(),
                "imageUrl": (thumbs.get("high") or thumbs.get("medium") or {}).get("url"),
            })
            print(f"  ✓ Эфир {name}: {video_id}")
        except Exception as e:
            print(f"  ✗ Эфир {name}: {e}")

    if not items:
        print("  · Эфиры: ничего не нашли, прежние ссылки оставляем как есть")
        return existing
    print(f"✅ Эфиры обновлены: {len(items)}")
    return {"items": items, "updatedAt": now_ms}


VIDEO_STOP_WORDS = (
    # Только названия рутинных тиражей. Одиночное «loteria» сюда НЕ ставить:
    # «Loteria Federal suspende concursos após fraude» — это новость о
    # махинациях, и она бы отсеялась вместе со сводкой результатов
    "sorteios das loterias", "sorteio da mega-sena", "sorteio da quina",
    "resultado da mega-sena", "resultado das loterias",
    "horóscopo", "horoscopo", "horoscope",
    "гороскоп", "знаки зодиака",
)


def fetch_channel_videos(channel_id, channel_name, scope, lang, limit=6):
    """Свежие видео канала — через API YouTube.

    БЫЛО: публичная лента канала (feeds/videos.xml) — без ключа и квоты.
    С машины разработчика работает, а С СЕРВЕРА GitHub Actions YouTube
    отдаёт 404 на все такие запросы: ленты закрыты для дата-центров.
    Проверено живым запуском — все 16 каналов вернули 404/500, блоки
    оказались пустыми. Поэтому берём те же видео через API по ключу,
    который у нас и так есть.

    Служебный плейлист загрузок канала получается из его идентификатора
    заменой префикса UC на UU — отдельный запрос за ним не нужен, это
    экономит половину обращений.

    Порога по просмотрам нет сознательно: качество гарантирует сам канал,
    а не популярность. Более того, порог вредил — свежий ролик не успевает
    набрать просмотры, и в блок попадало то, что постарее (а кыргызский
    блок с порогом в 50 000 оставался пустым вовсе).
    """
    uploads_playlist = "UU" + channel_id[2:]
    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/playlistItems",
            params={
                "part": "snippet",
                "playlistId": uploads_playlist,
                "maxResults": limit,
                "key": YOUTUBE_API_KEY,
            },
            timeout=15,
        )
        if not r.ok:
            print(f"  ✗ Канал {channel_name}: HTTP {r.status_code}")
            return []
        data = r.json()
    except Exception as e:
        print(f"  ✗ Канал {channel_name}: {e}")
        return []

    items = []
    for entry in data.get("items", []):
        snippet = entry.get("snippet", {})
        video_id = snippet.get("resourceId", {}).get("videoId")
        title_text = (snippet.get("title") or "").strip()
        if not video_id or not title_text:
            continue
        # Приватные и удалённые ролики остаются в плейлисте заглушками
        if title_text in ("Private video", "Deleted video"):
            continue
        # Шортсы и блогерские нарезки узнаются по хештегам в заголовке —
        # у выпуска новостей их не бывает
        if "#" in title_text:
            continue
        # Служебная рутина одобренных каналов: гороскопы и результаты лотерей.
        # Канал мы одобряем целиком, поэтому такие ролики идут вместе с
        # новостями — у бразильского g1 это ежедневные «Sorteios das Loterias».
        # Прогноз погоды сюда НЕ добавляем: по названию обычный прогноз не
        # отличить от штормового предупреждения, а его терять нельзя
        if any(w in title_text.lower() for w in VIDEO_STOP_WORDS):
            continue
        try:
            published_ms = int(datetime.fromisoformat(
                snippet.get("publishedAt", "").replace("Z", "+00:00")).timestamp() * 1000)
        except (ValueError, AttributeError):
            published_ms = int(datetime.now().timestamp() * 1000)
        thumbs = snippet.get("thumbnails", {})
        image = (thumbs.get("high") or thumbs.get("medium") or thumbs.get("default") or {}).get("url")
        items.append({
            "title": title_text,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "summary": channel_name,
            "imageUrl": image,
            "source": f"YouTube {channel_name}",
            "category": "VIRAL",
            "priority": 1,
            "language": lang,
            "audioLang": lang,
            "scope": scope,
            "publishedAt": published_ms,
            "expiresAt": int(datetime.now().timestamp() * 1000) + 24 * 3600 * 1000,
            "viewCount": 0,
            "channelId": channel_id,
            "embeddable": True,
        })
    return items


def collect_pool_videos(lang):
    """Видео пула: местные и мировые, свежие сверху."""
    local, world = [], []
    for cid, name, scope in YOUTUBE_CHANNELS.get(lang, []):
        got = fetch_channel_videos(cid, name, scope, lang)
        (local if scope == "local" else world).extend(got)
    local.sort(key=lambda x: x["publishedAt"], reverse=True)
    world.sort(key=lambda x: x["publishedAt"], reverse=True)
    print(f"  ✓ Каналы {lang}: местных {len(local)}, мировых {len(world)}")
    return local, world


def fetch_youtube_viral(region_code, max_results=10):
    """Тренды региона по КАЖДОЙ релевантной категории отдельно.

    Общий чарт mostPopular почти целиком состоит из музыки, развлечений и
    игр, поэтому прежний фильтр по белому списку категорий выкидывал ~100%
    выдачи и узел /viral оставался пустым. Запрос с videoCategoryId
    возвращает топ уже внутри нужной категории — фильтровать нечего.
    """
    seen, merged = set(), []
    for cat in VIRAL_CATEGORIES:
        for it in fetch_youtube_trending(region_code, max_results, category_id=cat):
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            merged.append(it)
    merged.sort(key=lambda x: x["viewCount"], reverse=True)
    merged = merged[:25]
    print(f"  ✓ YouTube {region_code}: {len(merged)} видео (по {len(VIRAL_CATEGORIES)} категориям)")
    return merged

def fetch_youtube_trending(region_code="KG", max_results=10, category_id=None):
    """Вирусные видео региона; с category_id — тренды внутри категории"""
    try:
        url = "https://www.googleapis.com/youtube/v3/videos"
        params = {
            "part": "snippet,statistics,status",
            "chart": "mostPopular",
            "regionCode": region_code,
            "maxResults": max_results,
            "key": YOUTUBE_API_KEY,
        }
        if category_id:
            params["videoCategoryId"] = category_id
        r = requests.get(url, params=params, timeout=10)
        if not r.ok:
            # 400 — категория не поддерживается в этом регионе, это норма
            if r.status_code != 400:
                print(f"  ✗ YouTube {region_code}/{category_id}: HTTP {r.status_code}")
            return []

        data = r.json()
        items = []

        for video in data.get("items", []):
            snippet = video.get("snippet", {})
            stats = video.get("statistics", {})
            video_id = video.get("id", "")
            views = int(stats.get("viewCount", 0))

            # Порог ниже, чем был у общего чарта: внутри категории цифры
            # естественно скромнее — новости и спорт редко берут миллионы
            min_views = 50_000 if region_code in ("KG", "RU", "KZ") else 200_000
            if views < min_views:
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
                                                 "anime", "episode ", "season ", "серия ", "сезон ",
                                                 # Игровой контент — не новости
                                                 "gameplay", "геймплей", "прохожден", "летсплей", "стрим ",
                                                 "minecraft", "roblox", "backrooms", "симулятор", "speedrun",
                                                 "спидран", "фнаф", "fnaf", "gta ", "мод ", "моды ",
                                                 "fortnite", "valorant", "dota", "cs2", "counter-strike",
                                                 "league of legends", "warzone", "call of duty", "pubg",
                                                 "twitch", "highlights", "montage", "funny moments",
                                                 "смешные моменты", "нарезка", "нарезки",
                                                 # Клипы-реакции с чужих трансляций — не журналистика,
                                                 # источник в скобках вида "(@espn)" типичен для таких
                                                 " did this", " got caught", "you won't believe",
                                                 "wait for it", "watch till the end"]):
                continue
            # Заголовки-реакции: обычно куча смайликов/капса — сигнал
            # клипа-нарезки, а не новости, даже если категория формально спорт
            emoji_count = sum(1 for ch in title_text if ord(ch) > 0x1F300)
            if emoji_count >= 2:
                continue
            # Блокируем только жанровый мусор — берём из Firebase config
            if any(kw in title_lower for kw in YOUTUBE_BLOCK_KEYWORDS):
                continue
            # Язык РЕЧИ в ролике, а не язык подписи. Раньше язык определялся
            # только по заголовку — а мировую подборку мы переводим, и
            # англоязычное видео с русским заголовком считалось русским.
            # defaultAudioLanguage отдаёт сам YouTube; если автор его не
            # проставил, откатываемся на определение по заголовку
            audio_lang = (snippet.get("defaultAudioLanguage")
                          or snippet.get("defaultLanguage") or "")[:2].lower()
            lang = audio_lang or (detect_language(title_text) if title_text else "unknown")
            # KG и RU тренды — локальные, US/мировые — world
            scope = "local" if region_code in ("KG", "RU") else "world"
            # Настоящая дата загрузки видео, не момент сбора — иначе видео,
            # остающееся в трендах несколько циклов подряд, каждый час получает
            # новую метку "сейчас" и "воскресает" свежим в ленте у тех, кто его
            # уже видел и пролистал (тот же класс бага, что чинили в fetch_rss)
            published_raw = snippet.get("publishedAt", "")
            try:
                published_ms = int(datetime.fromisoformat(
                    published_raw.replace("Z", "+00:00")).timestamp() * 1000)
            except (ValueError, AttributeError):
                published_ms = int(datetime.now().timestamp() * 1000)
            items.append({
                "title": title_text,
                "url": f"https://www.youtube.com/watch?v={video_id}",
                "summary": f"{views_str} просмотров · {snippet.get('channelTitle', '')}",
                "imageUrl": snippet.get("thumbnails", {}).get("high", {}).get("url"),
                "source": f"YouTube {region_code}",
                "category": "VIRAL",
                "priority": 1,
                "language": lang,
                "audioLang": audio_lang,   # пусто, если автор не указал
                "scope": scope,
                "publishedAt": published_ms,
                # Дата публикации теперь честная и может быть старше суток —
                # видео нередко попадает в тренды через день-два после заливки.
                # Клиентский фильтр ленты (не старше 24ч от publishedAt) выкинул
                # бы такое видео сразу. expiresAt — отдельное "показывать, пока
                # остаётся трендовым": продлевается на 24ч каждый раз, пока
                # видео снова попадает в этот же fetch; если завтра из трендов
                # выпало — новых продлений не будет, и через 24ч само уйдёт
                "expiresAt": int(datetime.now().timestamp() * 1000) + 24 * 3600 * 1000,
                "regionCode": region_code,
                "viewCount": views,
                "channelId": snippet.get("channelId", ""),
                "label": label,
                # Часть трендовых видео запрещает встраивание — если так,
                # приложение не пытается открыть плеер (там гарантированно
                # будет ошибка), а сразу открывает YouTube
                "embeddable": video.get("status", {}).get("embeddable", True)
            })

        # Фильтр по подписчикам: берём только видео крупных каналов —
        # отсекает случайный/непонятный контент из трендов
        if items:
            ch_ids = list({it["channelId"] for it in items if it["channelId"]})
            try:
                r2 = requests.get("https://www.googleapis.com/youtube/v3/channels", params={
                    "part": "statistics", "id": ",".join(ch_ids[:50]), "key": YOUTUBE_API_KEY
                }, timeout=10)
                subs = {c["id"]: int(c.get("statistics", {}).get("subscriberCount", 0))
                        for c in r2.json().get("items", [])}
                # Порог снижен: у региональных новостных/спортивных каналов
                # редко бывает миллион подписчиков, прежний фильтр их срезал
                min_subs = 50_000 if region_code in ("KG", "RU", "KZ") else 300_000
                items = [it for it in items if subs.get(it["channelId"], 0) >= min_subs]
            except Exception as e:
                print(f"  ⚠️ channels.list: {e}")

        # Сортировку и итоговый лог делает fetch_youtube_viral (иначе на
        # каждый регион печаталось бы по строке на категорию)
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

# Служебные фразы источников (копирайты, дисклеймеры) — вырезаются из текста статьи.
# Паттерн применяется если найден в первых 300 символах.
BOILERPLATE_PATTERNS = [
    "Автором материала является K-News. Любое копирование или частичное использование возможно по разрешению редакции K-News.",
    "Любое копирование или частичное использование возможно по разрешению редакции",
    "Использование материалов разрешено только при наличии гиперссылки",
    "При использовании материалов ссылка на источник обязательна",
    "Все права защищены.",
    "© Все права защищены",
    "Читайте нас в Telegram",
    "Подписывайтесь на наш Telegram",
    "Подписывайтесь на нас в",
    "Фото иллюстративное.",
    "Фото из архива.",
]

def strip_boilerplate(text: str) -> str:
    """Убираем служебные фразы источников из начала текста"""
    for pattern in BOILERPLATE_PATTERNS:
        idx = text.find(pattern)
        if 0 <= idx < 300:
            text = (text[:idx] + text[idx + len(pattern):]).strip(" .,—-\n")
    return text

def extract_full_summary(item_el) -> str:
    """Извлекаем полный текст до логической точки — не обрезаем на полуслове"""
    # Пробуем content:encoded — там обычно полная статья
    ns = {"content": "http://purl.org/rss/1.0/modules/content/"}
    full = item_el.findtext("content:encoded", namespaces=ns) or ""
    if not full:
        full = item_el.findtext("description", "") or ""

    text = strip_boilerplate(clean_text(full))

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

# Служебный мусор новостных страниц — строки, которые нельзя тащить в summary
_PAGE_NOISE = ("this video can not be played", "published ", "getty images",
               "image source", "image caption", "advertisement", "sign up",
               "follow us", "related topics", "cookies", "javascript",
               "share this", "copyright", "watch:", "listen:")

def enrich_short_summaries(items, min_len=400, budget=25):
    """Мировые RSS (BBC/Reuters и др.) дают одно предложение-затравку.
    Для таких статей тянем страницу и собираем 2-4 первых абзаца текста —
    ДО перевода, чтобы читатель получил резюме на своём языке.
    budget ограничивает число HTTP-запросов за прогон (job ежечасный)."""
    done = 0
    for item in items:
        if done >= budget:
            break
        s = item.get("summary", "")
        if len(s) >= min_len or not item.get("url", "").startswith("http"):
            continue
        if "t.me" in item["url"] or "telegram." in item["url"]:
            continue
        try:
            r = requests.get(item["url"], timeout=8,
                             headers=BROWSER_HEADERS)
            done += 1
            if not r.ok:
                continue
            soup = BeautifulSoup(r.content, "html.parser")
            root = soup.find("article") or soup
            paras = []
            seen_paras = set()
            for p in root.find_all("p"):
                t = clean_text(p.get_text(" ", strip=True))
                if len(t) < 60:          # подписи, даты, крошки
                    continue
                low = t.lower()
                if any(n in low for n in _PAGE_NOISE):
                    continue
                # Часть сайтов (Al Jazeera, Sky Sports, Marca) отдаёт статью
                # только после выполнения скриптов, и в разметке лежат меню и
                # куски кода. Раньше они шли в описание — читатель видел
                # «play Live Sign up Show navigation menu…» или обрывки вроде
                # «ars». Лучше оставить описание пустым, чем заполнить мусором.
                if any(m in t for m in ("{", "};", "function(", "var ", "://")):
                    continue
                # Навигация: много слов подряд без знаков препинания
                if t.count(" ") >= 6 and not any(c in t for c in ".!?…"):
                    continue
                # Слипшиеся слова меню («upShow», «menuNews») — заглавная
                # буква сразу после строчной внутри слова, и таких много
                import re as _re
                if len(_re.findall(r"[a-zа-я][A-ZА-Я]", t)) >= 3:
                    continue
                # Некоторые сайты дублируют лид-абзац (стандфёрст + начало
                # текста) — сравниваем по первым 50 символам, не по полному
                # тексту, т.к. дубли иногда чуть отличаются пунктуацией
                dedup_key = low[:50]
                if dedup_key in seen_paras:
                    continue
                seen_paras.add(dedup_key)
                paras.append(t)
                if sum(len(x) for x in paras) > 700:
                    break
            body = " ".join(paras).strip()
            # Обрезаем по последнему полному предложению
            if len(body) > 700:
                body = body[:700]
                idx = max(body.rfind(". "), body.rfind("! "), body.rfind("? "))
                if idx > 150:
                    body = body[:idx + 1]
            if len(body) > len(s) + 80:
                item["summary"] = body
        except Exception:
            continue
    if done:
        print(f"  📄 Обогащено полным текстом: {done} запросов")

def enrich_missing_images(items, budget=15):
    """Важные/срочные новости без фото (priority>=2, URGENT, #карусель) всё
    равно попадают в hero-карусель приложения — с генерической заглушкой
    вместо картинки. RSS иногда не даёт enclosure, но сайт почти всегда
    указывает og:image в мета-тегах страницы — вытаскиваем его точечно,
    только для этих важных случаев, чтобы не тратить бюджет запросов
    на рядовые новости, для которых фото не критично."""
    done = 0
    for item in items:
        if done >= budget:
            break
        if item.get("imageUrl"):
            continue
        is_important = item.get("priority", 0) >= 2 or item.get("category") == "URGENT"
        if not is_important:
            continue
        url = item.get("url", "")
        if not url.startswith("http") or "t.me" in url or "telegram." in url:
            continue
        try:
            r = requests.get(url, timeout=8, headers=BROWSER_HEADERS)
            done += 1
            if not r.ok:
                continue
            soup = BeautifulSoup(r.content, "html.parser")
            og = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
            img_url = og.get("content") if og else None
            if img_url and img_url.startswith("http"):
                item["imageUrl"] = img_url
        except Exception:
            continue
    if done:
        print(f"  🖼️ Дозагружено og:image для важных новостей: {done} запросов")

def parse_pub_date(item_el) -> int:
    """Настоящая дата публикации из RSS (<pubDate>, формат RFC 822).
    Без этого статья-расследование недельной давности выглядела как
    "опубликована только что" — получала бонус за свежесть в оценке
    важности и попадала в hero-карусель как будто это горячая новость."""
    raw = item_el.findtext("pubDate", "").strip()
    if raw:
        try:
            dt = parsedate_to_datetime(raw)
            return int(dt.timestamp() * 1000)
        except Exception:
            pass
    return int(datetime.now().timestamp() * 1000)

def fetch_rss(source):
    try:
        r = requests.get(source["url"], timeout=10, headers=BROWSER_HEADERS)
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
                "category": source["category"], "source_category": source["category"],
                "priority": source["priority"],
                # Язык: явный язык источника надёжнее детектора
                # (детектор не отличает испанский/португальский от английского)
                "language": source.get("lang") or lang,
                "scope": source.get("scope", "world"),
                "source_lang": source.get("lang"),
                "publishedAt": parse_pub_date(item_el)
            })
        return items
    except Exception as e:
        print(f"  ✗ {source['source']}: {e}")
        return []

CATEGORY_KEYWORDS = {
    "SPORT": ["футбол", "баскетбол", "UFC", "дзюдо", "бокс", "чемпионат", "турнир по",
              "матч", "спортсмен", "олимпийский", "олимпиада", "спортивный", "тренировка",
              "футбольный клуб", "хоккей", "волейбол", "теннис", "лига чемпионов",
              "забил гол", "победил на чемпионате", "чемпион мира по", "чемпион азии по"],
    "TECH": ["технологии", "смартфон", "iPhone", "Android", "искусственный интеллект", "ИИ",
             "приложение", "интернет", "компьютер", "программа", "Tesla", "Apple", "Google"],
    "AUTO": ["автомобиль", "машина", "ДТП", "авария на дороге", "дорожная авария",
             "электромобиль", "бензин", "топливо", "водитель задержан",
             "угон", "штраф за вождение", "правила дорожного движения",
             "обзор авто", "тест-драйв", "новый автомобиль", "кроссовер", "внедорожник",
             "седан", "хэтчбек", "пикап", "электрокар"],
    "FASHION": ["мода", "стиль", "одежда", "коллекция", "бренд", "дизайнер", "тренд",
                "красота", "макияж", "fashion", "одежда"],
    "CULTURE": ["кино", "фильм", "сериал", "концерт", "музыка", "театр", "выставка",
                "актёр", "режиссёр", "премьера", "шоу", "артист"],
    "TOURS": ["туризм", "тур", "отдых", "курорт", "отель", "путешествие", "виза",
              "Иссык-Куль", "авиа", "рейс", "туристы"],
    "REALTY": ["недвижимость", "квартира", "дом", "аренда", "ипотека", "цена жилья",
               "строительство", "застройщик", "жилой"],
    "URGENT": [
        # Стихийные бедствия, войны, теракты — актуальны глобально
        "землетрясение", "наводнение", "паводок", "сель", "оползень", "лавина",
        "ураган", "тайфун", "торнадо", "цунами", "засуха", "пожар", "лесной пожар",
        "сильный ветер", "шквалистый ветер", "штормовой ветер", "град", "крупный град",
        "похолодание", "резкое похолодание", "аномальный холод", "аномальная жара",
        "гололёд", "гололедица", "снежный занос", "метель",
        "авиакатастрофа", "крушение", "обрушение", "взрыв", "утечка газа",
        "химическая авария", "радиация", "разлив нефти",
        "ЧС", "МЧС", "чрезвычайная ситуация", "режим ЧС", "эвакуация", "спасательная операция",
        "массовое отравление", "вспышка", "эпидемия",
        "карантин", "опасный вирус", "вспышка инфекции",
        "теракт", "стрельба", "захват заложников", "взрывное устройство", "бомба",
        "дефолт", "девальвация", "санкции", "обвал курса", "банкротство банка",
        # Рост цен на жизненно важное — актуально всем, независимо от товара
        "подорожал", "подорожали", "подорожает", "рост цен на", "цены на хлеб",
        "цены на муку", "цены на сахар", "цены на бензин", "цены на газ выросли",
        "дефицит хлеба", "дефицит топлива", "дефицит продуктов", "нехватка продуктов",
        "резкий скачок цен", "цены взлетели",
        "государственный переворот", "импичмент", "отставка президента", "военное положение",
        "война", "вооружённый конфликт", "ракетный удар", "объявил войну",
        # Спорт — победы ЦА
        "вышел в финал", "вышел в полуфинал", "вышел в четвертьфинал",
        "завоевал золото", "завоевал медаль", "нокаут", "победил на чемпионате",
        "чемпион мира", "чемпион азии", "рекорд мира",
        # Английский, испанский, португальский — те же категории событий для
        # мировых/англоязычных/латиноамериканских/бразильских пулов. Gemini и
        # так понимает срочность по смыслу, это лишь подстраховка для
        # предварительной пометки (auto_categorize) до вызова Gemini
        "earthquake", "flood", "flash flood", "landslide", "avalanche",
        "hurricane", "typhoon", "tornado", "tsunami", "drought", "wildfire",
        "severe storm", "gale", "hailstorm", "cold snap", "heatwave", "blizzard",
        "plane crash", "collapse", "explosion", "gas leak", "chemical spill",
        "radiation leak", "oil spill", "state of emergency", "evacuation",
        "rescue operation", "mass poisoning", "outbreak", "epidemic",
        "quarantine", "deadly virus",
        "terror attack", "shooting", "hostage", "explosive device", "bomb",
        "default", "devaluation", "sanctions", "currency collapse", "bank collapse",
        "prices soar", "price surge", "bread shortage", "fuel shortage", "food shortage",
        "coup", "impeachment", "president resigns", "martial law",
        "war", "armed conflict", "missile strike", "declares war",
        "reaches the final", "reaches the semifinal", "wins gold", "wins medal",
        "knockout", "world champion", "world record",
        "terremoto", "inundación", "huracán", "tifón", "tornado", "tsunami",
        "sequía", "incendio forestal", "ola de calor", "ola de frío",
        "estado de emergencia", "evacuación", "tiroteo",
        "atentado", "rehenes", "bomba", "guerra", "golpe de estado",
        "terremoto", "inundação", "furacão", "tufão", "tsunami", "seca",
        "incêndio florestal", "onda de calor", "onda de frio",
        "estado de emergência", "evacuação", "tiroteio",
        "atentado", "reféns", "bomba", "guerra", "golpe de estado",
    ],
    # Коммунальные отключения, перекрытия дорог, местная коррупция — актуальны
    # только если новость про СТРАНУ читателя (scope=local), см. auto_categorize
    "URGENT_LOCAL_ONLY": [
        "отключение воды", "отключение света", "отключение электричества", "без воды", "без света",
        "отключат", "веерные отключения", "аварийное отключение",
        "перекрыт", "перекрыли", "закрыт перевал", "дорога закрыта", "ДТП со смертельным",
        "столкновение", "авария на дороге",
        "многокилометровая пробка", "многочасовая пробка", "огромная пробка", "серьёзные пробки",
        "движение затруднено", "затор на", "коллапс на дороге", "парализовало движение",
        "задержан за коррупцию", "арестован министр", "обыск в министерстве",
        "задержан чиновник", "антикоррупционный рейд",
        # Рядовые смерти/аварии/пострадавшие — не «мировая» срочность: каждый день
        # где-то в мире ДТП или бытовое происшествие, это не должно попадать в
        # карусель у читателя из другой страны. Крупные катастрофы остаются
        # в основном списке URGENT (землетрясения, теракты, авиакатастрофы и т.д.)
        "погиб", "погибли", "жертвы", "пострадавшие", "ранен", "убит", "найден мёртвым",
        "отравление", "отравились",
        # Английский/испанский/португальский эквиваленты — те же события
        # (отключения, транспортный коллапс, коррупционные аресты, рядовые ДТП) для других пулов
        "power outage", "blackout", "power cut", "water shutoff", "water outage",
        "road closed", "road closure", "highway closed", "traffic collapse",
        "gridlock", "massive traffic jam", "hours-long traffic jam",
        "transit strike", "train strike", "subway shutdown", "flight grounded",
        "arrested for corruption", "minister arrested", "official arrested", "corruption raid",
        "killed", "dead", "casualties", "injured", "shot dead", "found dead", "poisoning",
        "apagón", "corte de luz", "corte de agua", "carretera cerrada",
        "atasco", "embotellamiento", "huelga de transporte",
        "detenido por corrupción", "ministro detenido", "funcionario detenido",
        "muertos", "heridos",
        "apagão", "corte de energia", "corte de água", "estrada fechada",
        "engarrafamento", "greve de transporte",
        "preso por corrupção", "ministro preso", "funcionário preso",
        "mortos", "feridos",
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
    # Местные ЧП (отключения, перекрытия) — только для local-новостей:
    # отключение света в Москве не «срочно» для читателя из Кыргызстана
    if item.get("scope") == "local":
        local_kw = CATEGORY_KEYWORDS.get("URGENT_LOCAL_ONLY", [])
        if any(kw.lower() in title_lower for kw in local_kw):
            return "URGENT"
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

# За один запрос отдаём столько заголовков. Раньше лишние просто отрезались
# (`titles[:60]`), и половина собранного за час никогда не доходила до ИИ —
# статья не могла попасть в ленту, даже будучи лучшей в пуле.
GEMINI_CHUNK = 60


def filter_with_gemini(news_list, lang="ru"):
    """Прогоняет пул через ИИ порциями и склеивает результат.

    Порядок статей внутри порции сохраняется, порции идут подряд — общий
    порядок списка не меняется.
    """
    if not news_list:
        return news_list

    if len(news_list) <= GEMINI_CHUNK:
        return _filter_chunk(news_list, lang)

    out = []
    for start in range(0, len(news_list), GEMINI_CHUNK):
        out.extend(_filter_chunk(news_list[start:start + GEMINI_CHUNK], lang))
    return out


def _filter_chunk(news_list, lang="ru"):
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
- Реклама и PR под видом новости — типичные маркеры (не буквальные слова, а
  сам паттерн): банк/МФО объявляет «выгодные/специальные/льготные условия
  кредитования», «0% переплата», «рассрочка без процентов», «успей оформить»,
  «открой счёт и получи бонус» — это промо конкретного финансового продукта,
  даже если оформлено как новость. Та же логика для любых других услуг:
  «акция», «скидка до X%», «только сегодня», призыв обратиться/оформить/купить
- Исторические справки без актуального повода сегодня
- Кликбейт без содержания
- Дубликаты — оставь одну лучшую версию
- Региональные новости БЕЗ общенационального значения из больших стран
  (Россия, Казахстан и т.п.): рядовое ДТП, бытовое происшествие, местный суд,
  локальное коммунальное ЧП в конкретном городе/области — это новость ТОГО
  региона, не интересна читателю из другой страны СНГ/ЦА, даже если источник
  федеральный (РИА, ТАСС и т.п. репортят и локальные истории тоже). Удаляй,
  если событие не имеет общенационального резонанса и не касается напрямую
  граждан других стран пула. Оставляй только: федеральные решения/законы,
  события с общенациональным резонансом, крупные катастрофы/массовые жертвы,
  напрямую касающееся других стран пула (курс валют, миграция, санкции и т.п.)

═══ ПРАВИЛО №3 — ПРИОРИТЕТЫ ═══
priority=2 — события региона {pool['region']}:
  · ЧС, аварии с жертвами, стихийные бедствия
  · Политика: выборы, отставки, скандалы, аресты чиновников
  · Спорт: победы местных спортсменов, крупные местные турниры
  · Экономика: рост цен, курс валют, дефицит, массовые увольнения
  · Общество: эпидемии, отравления, коммунальные отключения
  · Геополитика мирового масштаба (войны, катастрофы) — для всех пулов

  ВАЖНО про большие страны (Россия, Казахстан и т.п.): «регион» — это НЕ вся
  страна целиком. Рядовое ДТП/бытовое происшествие в конкретном городе/области
  (Кемеровская область, Хабаровский край и т.д.) — это местная новость ТОГО
  города, не событие «региона {pool['region']}», даже если формально страна
  входит в список. Приоритет 2 и категория URGENT — только если у события
  общенациональный резонанс (массовые жертвы, теракт, катастрофа федерального
  масштаба, что обсуждает вся страна), а не потому что оно "в Кыргызстане/
  Казахстане/России" случилось. Обычное ДТП с 1-2 погибшими в областном центре
  — категория NEWS, priority=0-1, БЕЗ пометки URGENT.

priority=1 — важная мировая повестка:
  · Крупный спорт в разгаре (финалы, рекорды мирового уровня)
  · Технологии: релизы и анонсы которые обсуждает весь мир
  · Культура: массовые премьеры и события

priority=0 — обычные новости

═══ ПРАВИЛО №4 — ПОДОЗРЕНИЕ НА СКРЫТУЮ РЕКЛАМУ ═══
Если не уверен на 100%, что это реклама/PR (иначе удалил бы по Правилу №2),
но есть подозрение — оставь в ленте, но добавь номер в "ad_suspects".
Такие новости получат короткий срок жизни и сами исчезнут при следующем
обновлении — это подстраховка, а не наказание, ошибиться не страшно.

═══ КАТЕГОРИИ ═══
URGENT=экстренное, SPORT=спорт, TECH=технологии, AUTO=авто,
FASHION=мода, CULTURE=кино/музыка/театр, TOURS=туризм,
MONEY=финансы/экономика, HEALTH=здоровье, GOOD=позитив,
STARS=знаменитости (только певцы/актёры/блогеры/спортсмены шоу-бизнеса — НЕ политики, НЕ чиновники, НЕ общественные деятели),
VIRAL=вирусное видео, NEWS=всё остальное
ВАЖНО: политики, депутаты, министры, активисты, общественные деятели → категория NEWS или KG, никогда не STARS

Верни ТОЛЬКО JSON без объяснений:
{{"keep": [1,3,5], "urgent": [2], "important": [3,5], "recategorize": {{"4": "SPORT", "7": "TECH"}}, "ad_suspects": [3]}}

НОВОСТИ:
{chr(10).join(titles)}"""

    try:
        # Псевдоним, а не конкретная версия: Google отключает старые модели
        # без предупреждения (так умерла gemini-2.0-flash), и тогда фильтр молча
        # уходит в запасной вариант — 60 случайных статей вместо отбора
        model = genai.GenerativeModel("gemini-flash-latest")
        response = model.generate_content(prompt)
        text = response.text.strip()
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        result = json.loads(text)
        keep = [i-1 for i in result.get("keep", [])]
        urgent = set(i-1 for i in result.get("urgent", []))
        important = set(i-1 for i in result.get("important", []))
        recategorize = {int(k)-1: v for k, v in result.get("recategorize", {}).items()}
        ad_suspects = set(i-1 for i in result.get("ad_suspects", []))

        # Белый список: какие категории Gemini может назначать для каждого типа источника
        # Специализированные источники не меняют категорию — только NEWS-источники гибкие
        SOURCE_CATEGORY_LOCK = {
            "SPORT":   {"SPORT", "URGENT"},
            "TECH":    {"TECH", "URGENT"},
            "AUTO":    {"AUTO", "URGENT"},
            "FASHION": {"FASHION", "STARS", "CULTURE"},
            "CULTURE": {"CULTURE", "STARS"},
            "MONEY":   {"MONEY", "URGENT", "TECH"},
            "TOURS":   {"TOURS"},
            "TRENDS":  {"TRENDS", "NEWS", "VIRAL"},
            # NEWS-источники могут быть переназначены в любую категорию
            "NEWS":    None,  # None = без ограничений
        }

        # Тематические категории требуют подтверждения ключевым словом в заголовке.
        # Gemini может назначить AUTO/SPORT/... только если тема реально присутствует.
        KEYWORD_VALIDATED = {"AUTO", "SPORT", "TECH", "FASHION", "CULTURE", "TOURS", "REALTY"}

        def validate_recat(new_cat: str, title: str) -> bool:
            if new_cat not in KEYWORD_VALIDATED:
                return True  # NEWS, URGENT, STARS, MONEY и пр. — на усмотрение Gemini
            keywords = CATEGORY_KEYWORDS.get(new_cat, [])
            title_lower = title.lower()
            return any(kw.lower() in title_lower for kw in keywords)

        filtered = []
        for i in keep:
            if 0 <= i < len(news_list):
                item = news_list[i].copy()
                if i in urgent:   item["priority"] = 2
                elif i in important: item["priority"] = 1
                # Рубрика, а не новость: срочность снимаем, даже если Gemini
                # её присвоил. Пуш «Срочно» ради приглашения задать вопрос
                # журналистам подрывает доверие к самой пометке
                if is_service_format(item) and (item["priority"] >= 2 or item.get("category") == "URGENT"):
                    item["priority"] = 0
                    if item.get("category") == "URGENT":
                        item["category"] = "NEWS"
                if i in recategorize:
                    new_cat = recategorize[i]
                    source_cat = item.get("source_category", item.get("category", "NEWS"))
                    allowed = SOURCE_CATEGORY_LOCK.get(source_cat)
                    if (allowed is None or new_cat in allowed) and validate_recat(new_cat, item.get("title", "")):
                        item["category"] = new_cat
                    # иначе — игнорируем переназначение Gemini
                if i in ad_suspects:
                    # "Чёрная метка" — подозрение на скрытую рекламу/PR: живёт
                    # только до следующего часового прогона, а не обычные 24ч
                    item["expiresAt"] = int(datetime.now().timestamp() * 1000) + 75 * 60 * 1000
                filtered.append(item)
        if ad_suspects:
            print(f"  🏴 Чёрная метка (подозрение на рекламу): {len(ad_suspects)}")
        return filtered
    except Exception as e:
        print(f"⚠️ Gemini error (порция без отбора): {e}")
        # Запасной вариант на одну порцию: половина наугад. Полный отбор ИИ
        # оставляет примерно столько же, так что лента не проседает и не
        # раздувается мусором. Ошибка кричит в логе: полгода она молчала,
        # и мы не знали, что ленту всё это время набирала случайность
        import random
        return random.sample(news_list, max(1, len(news_list) // 2))

# ════════════════════════════════════════════════════════════════════
# Источники ПРИЛОЖЕНИЯ (Telegram/YouTube каналы, парсятся на устройстве).
# Публикуются в /config/app_sources — приложение читает их оттуда,
# при недоступности использует зашитые копии (SourceSelector.kt).
# h=handle, c=category, t=type (TELEGRAM|YOUTUBE_RSS), p=priority
# ════════════════════════════════════════════════════════════════════
APP_SOURCES = {
    "kg_always": [
        {"h": "t247feed",      "c": "KG",      "t": "TELEGRAM", "p": 10},
        {"h": "akipress",      "c": "KG",      "t": "TELEGRAM", "p": 2},
        {"h": "kabar_news_kg", "c": "KG",      "t": "TELEGRAM", "p": 2},
        {"h": "kyrgyzinform",  "c": "KG",      "t": "TELEGRAM", "p": 1},
        {"h": "tazabek",       "c": "KG",      "t": "TELEGRAM", "p": 1},
        {"h": "breakingmash",  "c": "URGENT",  "t": "TELEGRAM", "p": 2},
        {"h": "ticketon_kg",   "c": "CULTURE", "t": "TELEGRAM", "p": 1},
    ],
    "kg_sport": [
        {"h": "akipress",      "c": "SPORT", "t": "TELEGRAM", "p": 2},
        {"h": "kabar_news_kg", "c": "SPORT", "t": "TELEGRAM", "p": 1},
        {"h": "kgboxing",      "c": "SPORT", "t": "TELEGRAM", "p": 2},
        {"h": "mma_kg",        "c": "SPORT", "t": "TELEGRAM", "p": 2},
        {"h": "kyrgyz_sport",  "c": "SPORT", "t": "TELEGRAM", "p": 2},
        {"h": "ufc_ru",        "c": "SPORT", "t": "TELEGRAM", "p": 1},
        {"h": "mmafightclub",  "c": "SPORT", "t": "TELEGRAM", "p": 1},
        {"h": "wrestlingkg",   "c": "SPORT", "t": "TELEGRAM", "p": 2},
        {"h": "sport24kg",     "c": "SPORT", "t": "TELEGRAM", "p": 2},
    ],
    "kg_youtube": [
        {"h": "UCJQOJGxH87GCxUyHGqOG6Ew", "c": "KG", "t": "YOUTUBE_RSS", "p": 2},
        {"h": "UCiivW6grbRvpMtXKBIGfOdg", "c": "KG", "t": "YOUTUBE_RSS", "p": 1},
        {"h": "UCBFxQUBinMPqQHLHmpMZaJw", "c": "KG", "t": "YOUTUBE_RSS", "p": 2},
    ],
    "combat_sports_youtube": [
        {"h": "UCNFDnh7bvAMCgKzDFNO2fhg", "c": "SPORT", "t": "YOUTUBE_RSS", "p": 2},
        {"h": "UCPIAn-SWhJzBilt1MekO4Vg", "c": "SPORT", "t": "YOUTUBE_RSS", "p": 1},
        {"h": "UCwIiHyFLKZBBzzpLEPsGkEA", "c": "SPORT", "t": "YOUTUBE_RSS", "p": 1},
        {"h": "UCou-8TbxWsXQnBd4hkB9EBg", "c": "SPORT", "t": "YOUTUBE_RSS", "p": 1},
        {"h": "UCfX2-S9FBD1MZiDqxMCNmLg", "c": "SPORT", "t": "YOUTUBE_RSS", "p": 2},
    ],
    "world_neutral": [
        {"h": "bbcrussian",    "c": "WORLD", "t": "TELEGRAM", "p": 2},
        {"h": "aljazeeraee",   "c": "WORLD", "t": "TELEGRAM", "p": 2},
        {"h": "deutscheWelle", "c": "WORLD", "t": "TELEGRAM", "p": 1},
        {"h": "inosmi",        "c": "WORLD", "t": "TELEGRAM", "p": 1},
    ],
    "world_cis_extra": [
        {"h": "meduzaio",    "c": "WORLD", "t": "TELEGRAM", "p": 1},
        {"h": "tvrain",      "c": "WORLD", "t": "TELEGRAM", "p": 1},
        {"h": "currenttime", "c": "WORLD", "t": "TELEGRAM", "p": 1},
    ],
    "world_europe_extra": [
        {"h": "euromaidan",    "c": "WORLD", "t": "TELEGRAM", "p": 1},
        {"h": "bbcrussian",    "c": "WORLD", "t": "TELEGRAM", "p": 2},
        {"h": "deutscheWelle", "c": "WORLD", "t": "TELEGRAM", "p": 2},
    ],
    "world_middle_east_extra": [
        {"h": "aljazeeraee", "c": "WORLD", "t": "TELEGRAM", "p": 2},
        {"h": "bbcrussian",  "c": "WORLD", "t": "TELEGRAM", "p": 1},
    ],
    "tech_always": [
        {"h": "androidauthority",  "c": "TECH", "t": "TELEGRAM", "p": 2},
        {"h": "mobilereview",      "c": "TECH", "t": "TELEGRAM", "p": 2},
        {"h": "ru_9to5google",     "c": "TECH", "t": "TELEGRAM", "p": 1},
        {"h": "phonegeeks",        "c": "TECH", "t": "TELEGRAM", "p": 1},
        {"h": "techinsider_ru",    "c": "TECH", "t": "TELEGRAM", "p": 1},
        {"h": "ixbt_live",         "c": "TECH", "t": "TELEGRAM", "p": 2},
        {"h": "gsminfo_ru",        "c": "TECH", "t": "TELEGRAM", "p": 1},
        {"h": "androidinsider_ru", "c": "TECH", "t": "TELEGRAM", "p": 1},
        {"h": "wylsacom",          "c": "TECH", "t": "TELEGRAM", "p": 2},
        {"h": "fandroid_ru",       "c": "TECH", "t": "TELEGRAM", "p": 1},
    ],
    "tours_kg": [
        {"h": "travel_kg",         "c": "TOURS", "t": "TELEGRAM", "p": 2},
        {"h": "kyrgyzstan_travel", "c": "TOURS", "t": "TELEGRAM", "p": 2},
        {"h": "visitkyrgyzstan",   "c": "TOURS", "t": "TELEGRAM", "p": 2},
        {"h": "ilovekgtravel",     "c": "TOURS", "t": "TELEGRAM", "p": 1},
        {"h": "centralasiatravel", "c": "TOURS", "t": "TELEGRAM", "p": 1},
        {"h": "travelplus_ru",     "c": "TOURS", "t": "TELEGRAM", "p": 1},
    ],
    "tours_youtube": [
        {"h": "UCt_NLJ4McJlCnSbLn5LxjJg", "c": "TOURS", "t": "YOUTUBE_RSS", "p": 2},
        {"h": "UCojElg7pBFxqgFRfKLUwMoA", "c": "TOURS", "t": "YOUTUBE_RSS", "p": 2},
        {"h": "UCKSFtEiJHxMGGDxd0OR9Lug", "c": "TOURS", "t": "YOUTUBE_RSS", "p": 1},
        {"h": "UCxDZs_ltFFvn0FDHT6kmoXA", "c": "TOURS", "t": "YOUTUBE_RSS", "p": 2},
        {"h": "UCnT37BcNGEoMkdDflNJPc5A", "c": "TOURS", "t": "YOUTUBE_RSS", "p": 1},
    ],
    "good_news": [
        {"h": "goodnewsru",    "c": "GOOD", "t": "TELEGRAM", "p": 1},
        {"h": "pozitiv_kg",    "c": "GOOD", "t": "TELEGRAM", "p": 2},
        {"h": "dobroe_utro_kg","c": "GOOD", "t": "TELEGRAM", "p": 1},
        {"h": "positivnews",   "c": "GOOD", "t": "TELEGRAM", "p": 1},
        {"h": "worldgoodnews", "c": "GOOD", "t": "TELEGRAM", "p": 1},
    ],
    "stars_always": [
        {"h": "starhit",      "c": "STARS", "t": "TELEGRAM", "p": 1},
        {"h": "showbiz_kg",   "c": "STARS", "t": "TELEGRAM", "p": 2},
        {"h": "musickg",      "c": "STARS", "t": "TELEGRAM", "p": 2},
        {"h": "peopletalkru", "c": "STARS", "t": "TELEGRAM", "p": 1},
        {"h": "tmz_news",     "c": "STARS", "t": "TELEGRAM", "p": 1},
        {"h": "cosmo_ru",     "c": "STARS", "t": "TELEGRAM", "p": 1},
    ],
    "health_always": [
        {"h": "healthkg",      "c": "HEALTH", "t": "TELEGRAM", "p": 2},
        {"h": "doctorpiter",   "c": "HEALTH", "t": "TELEGRAM", "p": 1},
        {"h": "medicalru",     "c": "HEALTH", "t": "TELEGRAM", "p": 1},
        {"h": "zdorovieinfo",  "c": "HEALTH", "t": "TELEGRAM", "p": 1},
        {"h": "lifehacker_ru", "c": "HEALTH", "t": "TELEGRAM", "p": 1},
        {"h": "psychologykg",  "c": "HEALTH", "t": "TELEGRAM", "p": 2},
    ],
    "money_always": [
        {"h": "fingramota_kg",    "c": "MONEY", "t": "TELEGRAM", "p": 2},
        {"h": "rbc_economics",    "c": "MONEY", "t": "TELEGRAM", "p": 1},
        {"h": "tinkoff_journal",  "c": "MONEY", "t": "TELEGRAM", "p": 1},
        {"h": "nbrkg",            "c": "MONEY", "t": "TELEGRAM", "p": 2},
        {"h": "money_kg",         "c": "MONEY", "t": "TELEGRAM", "p": 2},
        {"h": "invest_simple_ru", "c": "MONEY", "t": "TELEGRAM", "p": 1},
    ],
    "life_always": [
        {"h": "lifehacks_kg",    "c": "LIFE", "t": "TELEGRAM", "p": 2},
        {"h": "lifehacker_ru",   "c": "LIFE", "t": "TELEGRAM", "p": 1},
        {"h": "recipekg",        "c": "LIFE", "t": "TELEGRAM", "p": 2},
        {"h": "sovetdoma",       "c": "LIFE", "t": "TELEGRAM", "p": 1},
        {"h": "psychology_life", "c": "LIFE", "t": "TELEGRAM", "p": 1},
        {"h": "mama_kg",         "c": "LIFE", "t": "TELEGRAM", "p": 2},
    ],
    "niche_always": [
        {"h": "avtoradar",     "c": "AUTO",    "t": "TELEGRAM", "p": 0},
        {"h": "driveru",       "c": "AUTO",    "t": "TELEGRAM", "p": 0},
        {"h": "motor_ru",      "c": "AUTO",    "t": "TELEGRAM", "p": 0},
        {"h": "buro247",       "c": "FASHION", "t": "TELEGRAM", "p": 0},
        {"h": "vogue_russia",  "c": "FASHION", "t": "TELEGRAM", "p": 0},
        {"h": "kinopoisk",     "c": "CULTURE", "t": "TELEGRAM", "p": 0},
        {"h": "afishakg",      "c": "CULTURE", "t": "TELEGRAM", "p": 0},
        {"h": "sport24russia", "c": "SPORT",   "t": "TELEGRAM", "p": 0},
        {"h": "matchtv",       "c": "SPORT",   "t": "TELEGRAM", "p": 0},
    ],
    "youtube_world_news": [
        {"h": "UCK9hDpGRfzZuoOkL9Nf-7jA", "c": "WORLD", "t": "YOUTUBE_RSS", "p": 2},
        {"h": "UC0d3LGCJMzB0YQZN5TFe1QA", "c": "WORLD", "t": "YOUTUBE_RSS", "p": 1},
        {"h": "UCknLrEdhRCp1aegoMqRaCZg", "c": "WORLD", "t": "YOUTUBE_RSS", "p": 1},
        {"h": "UChqUTb7kYRX8-EiaN3XFrSQ", "c": "WORLD", "t": "YOUTUBE_RSS", "p": 1},
    ],
}

POOL_LANGUAGE_NAMES = {
    "ru": "русский",
    "en": "английский (English)",
    "es": "испанский (español)",
    "pt": "португальский (português)",
}


# ─── Служебные форматы: не новости, а рубрики ────────────────────────────────
# Прямые трансляции, «вопросы читателей», подборки и обзоры — это формат
# издания, а не событие. Раньше такое могло получить пометку СРОЧНО и уйти
# пушем в шторку: человека будили приглашением задать вопрос журналистам
# Guardian (поймано 12.08.2026). Событие в них если и есть, то придёт
# отдельной новостью.
# ВАЖНО: адреса живых блогов (/live/) сюда НЕ входят. Живой блог ведут и про
# катастрофу: на проверке правило сняло срочность с «Вторая ночь поисков
# выживших в Колумбии» — настоящее землетрясение с погибшими. Формат сам по
# себе ничего не говорит о важности события, поэтому судим по заголовку.
SERVICE_FORMAT_MARKERS = (
    "/podcast", "/newsletter", "/quiz", "/crossword", "/horoscope",
    "/commentisfree", "/opinion/", "/lifeandstyle/",
)
SERVICE_FORMAT_TITLE = (
    "вопросы и ответы", "в прямом эфире", "прямая трансляция", "онлайн-трансляция",
    "спрашивайте", "задайте вопрос", "подборка", "обзор недели", "итоги недели",
    "что посмотреть", "что почитать", "гид по", "рейтинг лучших",
    "live blog", "live updates", "q&a", "ask our", "your questions",
    "readers reply", "week in review", "best of", "what to watch",
    "en directo", "en vivo", "preguntas y respuestas",
    "ao vivo", "perguntas e respostas",
)


def is_service_format(item):
    """Рубрика/формат, а не новость: срочность и пуш таким не положены."""
    url = (item.get("url") or "").lower()
    if any(m in url for m in SERVICE_FORMAT_MARKERS):
        return True
    title = (item.get("title") or "").lower()
    return any(m in title for m in SERVICE_FORMAT_TITLE)


def needs_translation(item, pool):
    """Нужен ли перевод статьи на язык пула.

    БЫЛО: языки перечислялись поимённо — для ru переводили только «en» и «ar»,
    для en только «ru» и «ar». Любой язык вне списка проходил как есть, и в
    русском пуле оказывались испанские и португальские статьи (28 из 80 на
    проверке 11.08.2026). Приложение прячет их языковым фильтром — лента
    выглядела бедной, а иногда они всё же просачивались, и человек видел чужой
    язык.

    СТАЛО: переводим всё, что НЕ на языке пула. Тогда ни один язык не может
    «не попасть в список» — правило одно и работает для будущих пулов тоже.

    Кириллические языки считаем взаимопонятными внутри ru-пула (русский,
    кыргызский, украинский и т.п. — читатель поймёт), остальное переводим.
    """
    lang = (item.get("language") or "unknown").lower()

    # Язык неизвестен — безопаснее перевести: хуже показать чужой язык
    if lang in ("unknown", "other", ""):
        return True

    CYRILLIC = {"ru", "ky", "uk", "be", "bg", "sr", "mk", "kk", "uz", "tg"}
    if pool == "ru":
        return lang not in CYRILLIC
    return lang != pool

def _gtx_translate(text: str, target: str) -> str | None:
    """Бесплатный Google Translate (без ключа и квот). None при ошибке."""
    if not text.strip():
        return ""
    try:
        r = requests.get("https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t", "q": text[:1500]},
            timeout=10)
        if not r.ok:
            return None
        data = r.json()
        return "".join(seg[0] for seg in data[0] if seg and seg[0])
    except Exception:
        return None

def translate_batch(items, target_lang):
    """Переводит title и summary на язык пула через бесплатный Google Translate.
    (Gemini не используется — его квота нужна фильтрации.) Мутирует items;
    при ошибке оставляет оригиналы — лента не ломается.

    Прозрачность вместо точечных фиксов слов: машинный перевод неизбежно даёт
    огрехи на идиомах/титулах («swinging»→«качели», «King»→«Кинг»). Латать
    конкретные слова — бесконечная игра в кротов, поэтому вместо этого честно
    помечаем перевод и сохраняем оригинал — читатель сам видит и может свериться."""
    import time
    translated = 0
    for item in items:
        orig_title = item.get("title", "")
        orig_summary = item.get("summary", "")
        # Заголовок и текст переводим ОТДЕЛЬНЫМИ запросами — общий запрос с
        # разделителем "@@@" на длинных текстах ломался (Google съедал разделитель),
        # из-за чего заголовок переводился, а текст оставался на языке оригинала
        # с ложной пометкой translated=True
        t = _gtx_translate(orig_title[:300], target_lang) if orig_title else ""
        s = _gtx_translate(orig_summary[:800], target_lang) if orig_summary else ""
        if t and t.strip():
            item["title"] = t.strip()
            item["summary"] = s.strip() if s and s.strip() else orig_summary
            item["language"] = target_lang
            item["origTitle"] = orig_title
            item["translated"] = True
            translated += 1
        time.sleep(0.15)  # мягкий темп — не дразним эндпоинт
    print(f"  ✓ Переведено {translated}/{len(items)} на {target_lang}")

def tg_post_keys(item) -> list:
    """Ключи дедупликации TG-поста: по URL и по заголовку.
    Заголовочный ключ ловит ту же новость от другого источника (другой URL).
    Символы . / # $ [ ] недопустимы в ключах Firebase."""
    keys = []
    url = item.get("url", "")
    if url:
        keys.append("u:" + "".join(c if c not in './#$[]' else '_' for c in url)[:96])
    words = sorted(set(
        w.lower()[:6] for w in item.get("title", "").split()
        if len(w) > 3 and w.isalpha()
    ))[:10]
    if words:
        keys.append("t:" + "-".join(words)[:96])
    return keys

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


def post_to_telegram(items: list, channel: str = TELEGRAM_CHANNEL, lang: str = "ru"):
    """Постим топ-новости в языковой канал. Дедупликация через Firebase /tg_posted/{lang}."""
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ TELEGRAM_BOT_TOKEN не задан, пропускаем постинг")
        return

    # Загружаем уже опубликованные URL (отдельный список на каждый язык —
    # одна и та же мировая новость постится в каждый канал на своём языке)
    posted_ref = db.reference(f"/tg_posted/{lang}" if lang != "ru" else "/tg_posted")
    posted_data = posted_ref.get() or {}
    posted_urls = set(posted_data.keys() if isinstance(posted_data, dict) else [])

    # Пост должен быть на языке канала — непереведённые (сбой перевода) пропускаем
    def lang_ok(item):
        il = item.get("language", "unknown")
        if il in ("unknown", "other", ""):
            return True
        if lang == "ru":
            return il in ("ru", "ky", "uk", "be", "bg", "sr", "mk")
        return il == lang

    # Берём только priority >= 1 (срочные/важные), не опубликованные ранее.
    # Дедуп по URL И по заголовку — та же новость от другого источника не постится
    candidates = [
        item for item in items
        if item.get("priority", 0) >= 1
        and not any(k in posted_urls for k in tg_post_keys(item))
        and item.get("category") not in ("CURRENCY", "CRYPTO")
        and lang_ok(item)
    ]

    # Максимум 5 постов за один запуск
    to_post = candidates[:5]
    if not to_post:
        print("📭 Нет новых важных новостей для постинга в TG")
        return

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    new_posted = {}
    new_messages = {}  # message_id -> {"ts", "channel"} — для автоочистки архива

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
        text += f"\n\n{hashtag} | 📲 {channel}"
        if source:
            text += f" | {source}"
        # Контакт для рекламодателей — в каждом посте, на языке канала
        ads_word = {"ru": "Реклама", "en": "Ads", "es": "Publicidad", "pt": "Publicidade"}.get(lang, "Ads")
        text += f"\n📣 {ads_word}: @ticker247ads_bot"

        try:
            resp = requests.post(api_url, json={
                "chat_id": channel,
                "text": text,
                "parse_mode": "HTML",
                "disable_web_page_preview": False,
            }, timeout=10)
            if resp.status_code == 200:
                print(f"✅ TG posted: {title[:60]}")
                ts_now = int(datetime.now().timestamp())
                for k in tg_post_keys(item):
                    new_posted[k] = ts_now
                mid = resp.json().get("result", {}).get("message_id")
                if mid:
                    new_messages[str(mid)] = {"ts": ts_now, "channel": channel}
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

    # Запоминаем message_id новых постов — понадобится для автоочистки
    msg_ref = db.reference(f"/tg_messages/{lang}" if lang != "ru" else "/tg_messages/ru")
    if new_messages:
        msg_ref.update(new_messages)

    # Автоочистка канала: удаляем из САМОГО Telegram-канала посты старше
    # 30 дней (не только запись в базе, а именно сообщение с канала) —
    # иначе архив в канале растёт бесконечно. Требует, чтобы бот был
    # админом канала с правом "Удаление сообщений".
    all_messages = msg_ref.get() or {}
    msg_cutoff = int(datetime.now().timestamp()) - 30 * 86400
    old_messages = {k: v for k, v in all_messages.items()
                     if isinstance(v, dict) and v.get("ts", 0) < msg_cutoff}
    if old_messages:
        delete_api = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/deleteMessage"
        deleted, to_forget = 0, {}
        for mid, info in old_messages.items():
            try:
                r = requests.post(delete_api, json={
                    "chat_id": info.get("channel", channel),
                    "message_id": int(mid)
                }, timeout=10)
                if r.status_code == 200:
                    deleted += 1
                to_forget[mid] = None  # забываем в любом случае — иначе будем пытаться вечно
            except Exception:
                to_forget[mid] = None
        if to_forget:
            msg_ref.update(to_forget)
        if deleted:
            print(f"  🗑️ TG архив [{lang}]: удалено {deleted}/{len(old_messages)} постов старше 30 дней")


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
    print("📡 Прямые эфиры...")
    live_payload = fetch_live_streams()

    print("▶ YouTube — видео с отобранных каналов...")
    # БЫЛО — тренды региона; давало блогерский мусор, см. YOUTUBE_CHANNELS:
    # viral_kg    = fetch_youtube_viral("KG", 15)
    # viral_ru    = fetch_youtube_viral("RU", 15)
    # viral_kz    = fetch_youtube_viral("KZ", 10)
    # viral_world = fetch_youtube_viral("US", 10)
    # viral_br    = fetch_youtube_viral("BR", 15)
    # viral_mx    = fetch_youtube_viral("MX", 15)
    # viral_gb    = fetch_youtube_viral("GB", 10)
    ru_local, ru_world = collect_pool_videos("ru")
    en_local, en_world = collect_pool_videos("en")
    es_local, es_world = collect_pool_videos("es")
    pt_local, pt_world = collect_pool_videos("pt")

    # Узлы оставлены прежними — приложение читает их по этим именам.
    # Местные каналы пула идут в «свой» узел, остальные — в мировой
    viral_kg    = ru_local
    viral_ru    = ru_local
    viral_kz    = ru_local
    viral_world = en_world
    viral_gb    = en_local or en_world
    viral_mx    = es_local or es_world
    viral_br    = pt_local or pt_world

    # ── Мировые подборки пулов ───────────────────────────────────────────────
    # Раньше здесь брали тренды соседних стран и чистили их по языку речи.
    # Теперь источник — сами каналы из белого списка, у которых язык известен
    # заранее, поэтому ни языковой фильтр, ни чистка локальных узлов не нужны.
    viral_world_ru = ru_world
    viral_world_es = es_world
    viral_world_pt = pt_world

    viral_ref = db.reference("/viral")
    viral_ref.set({
        "kg":       viral_kg,
        "ru":       viral_ru,
        "kz":       viral_kz,
        "world":    viral_world,     # английский — для gb/en пула
        "world_ru": viral_world_ru,
        "world_es": viral_world_es,
        "world_pt": viral_world_pt,
        "br":       viral_br,
        "mx":       viral_mx,
        "gb":       viral_gb,
        "live":     live_payload,   # прямые эфиры, см. fetch_live_streams
        # Станции кладём ВНУТРЬ этой записи, а не отдельным вызовом: запись
        # /viral идёт целиком и стёрла бы вложенный узел сразу после создания.
        # Узел внутри /viral, а не в /config, потому что права боевой базы
        # открывают на чтение только news и viral
        "radio":    RADIO_STATIONS,
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

    # Дедупликация по схожести заголовков — убираем дубли об одном событии
    def title_words(title):
        stop = {"в","на","и","с","по","из","за","от","к","о","об","не","что","как","для","при","до","он","она","они","это"}
        return set(w.lower() for w in title.split() if len(w) > 3 and w.lower() not in stop)

    def proper_nouns(title):
        """Имена собственные — слова с заглавной буквы длиннее 3 символов (работает между языками)"""
        return set(w for w in title.split() if len(w) > 3 and w[0].isupper() and w.isalpha())

    def are_duplicates(title1, title2):
        """Проверяем дубль двумя методами: совпадение слов (1 язык) или имён собственных (разные языки)"""
        w1, w2 = title_words(title1), title_words(title2)
        if len(w1) > 0 and len(w2) > 0:
            overlap = len(w1 & w2) / min(len(w1), len(w2))
            if overlap >= 0.6:
                return True
        # Кросс-языковая проверка: 2+ общих имени собственных в схожем контексте
        p1, p2 = proper_nouns(title1), proper_nouns(title2)
        if len(p1) >= 2 and len(p2) >= 2 and len(p1 & p2) >= 2:
            return True
        # 1 уникальное имя собственное + оба заголовка очень коротких
        if len(p1 & p2) >= 1 and len(w1) <= 3 and len(w2) <= 3:
            return True
        return False

    deduped = []
    for item in all_news:
        is_dup = False
        for kept in deduped:
            if are_duplicates(item.get("title", ""), kept.get("title", "")):
                # Оставляем с большим приоритетом
                if item.get("priority", 0) > kept.get("priority", 0):
                    deduped.remove(kept)
                    deduped.append(item)
                is_dup = True
                break
        if not is_dup:
            deduped.append(item)

    print(f"После дедупликации: {len(deduped)} (убрано {len(all_news)-len(deduped)} дублей)")
    all_news = deduped

    # Дозаполняем описания ОДИН раз, до разделения по пулам: мировая статья
    # копируется в каждый пул, и раньше её страница тянулась заново для
    # каждого — бюджет запросов выгорал вчетверо быстрее, а до части новостей
    # очередь не доходила вовсе, и они оставались с пустым описанием
    print("📝 Дозаполняем короткие описания...")
    enrich_short_summaries(all_news, budget=80)

    # Новости, у которых текста нет и взять его негде (Al Jazeera, Sky Sports,
    # Marca, Bloomberg отдают статью только после выполнения скриптов —
    # проверено вручную 11.08.2026). В ленте им делать нечего: заголовок, фото
    # и пустое место выглядят как поломка приложения.
    #
    # Но срочные оставляем: «землетрясение магнитудой 7.4» ценно как СИГНАЛ,
    # даже без подробностей. Такие помечаем notifyOnly — приложение покажет их
    # в бегущей строке и уведомлении, но не в ленте, а в читалке напишет, что
    # материал готовится. Подробности придут ОТДЕЛЬНОЙ новостью, когда источник
    # допишет текст: дописать старую запись мы не можем, обратной связи с
    # лентой источника нет
    NO_TEXT_LIMIT = 40
    kept, dropped, notify_only = [], 0, 0
    for item in all_news:
        if len((item.get("summary") or "").strip()) >= NO_TEXT_LIMIT:
            kept.append(item)
            continue
        urgent = item.get("category") == "URGENT" or item.get("priority", 0) >= 2
        if urgent:
            item["notifyOnly"] = True
            notify_only += 1
            kept.append(item)
        else:
            dropped += 1
    all_news = kept
    print(f"  🗑 Без текста: выброшено {dropped}, оставлено для уведомлений {notify_only}")

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
            # Каждому пулу — своя КОПИЯ: пулы переводят статьи на свой язык,
            # общий объект нельзя мутировать из четырёх мест
            for pool in ALL_POOLS:
                lang_groups[pool].append(dict(item))
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
        # Удаляем новости старше 90 дней (требование Google Play News policy)
        cutoff = (datetime.now().timestamp() - 30 * 24 * 3600) * 1000
        filtered = [x for x in filtered if x.get("publishedAt", 0) >= cutoff]
        filtered.sort(key=lambda x: x.get("priority", 0), reverse=True)
        max_items = 80 if lang == "ru" else 70
        filtered = filtered[:max_items]
        # Важные/срочные новости без фото — подтягиваем og:image со страницы,
        # чтобы они не висели в hero-карусели с генерической заглушкой
        enrich_missing_images(filtered)
        # Автоперевод: статьи не на языке пула переводим через Gemini
        # Батчи по 15 + один повтор для неудавшихся — падение батча не оставляет
        # половину пула на чужом языке (приложение фильтрует их из ленты)
        to_translate = [x for x in filtered if needs_translation(x, lang)]
        if to_translate:
            print(f"  🌍 Переводим {len(to_translate)} статей на {lang}...")
            for j in range(0, len(to_translate), 15):
                translate_batch(to_translate[j:j+15], lang)
            retry = [x for x in to_translate if needs_translation(x, lang)]
            if retry:
                print(f"  🔁 Повтор перевода {len(retry)} статей...")
                for j in range(0, len(retry), 15):
                    translate_batch(retry[j:j+15], lang)
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

        # Постим в языковой Telegram-канал — каждый пул в свой
        channel = TELEGRAM_CHANNELS.get(lang)
        if channel:
            print(f"📤 Постим [{lang}] в {channel}...")
            post_to_telegram(filtered, channel=channel, lang=lang)

    # Пул выключили — убираем его ветку. Иначе у того, кто уже выбрал этот
    # язык, приложение будет вечно показывать последнюю выдачу перед
    # отключением. Список явный: слепо чистить всё, чего нет среди пулов,
    # опасно — в /news могут лежать ветки, о которых этот скрипт не знает
    for stale in DISABLED_POOLS:
        if db.reference(f"/news/{stale}").get(shallow=True):
            db.reference(f"/news/{stale}").delete()
            print(f"  🧹 Убрана ветка отключённого пула: /news/{stale}")

    # Публикуем имена редакторских каналов — приложение читает их отсюда,
    # смена канала не требует обновления приложения
    db.reference("/config/editorial_channels").set({
        **{lang: ch.lstrip("@") for lang, ch in TELEGRAM_CHANNELS.items() if ch},
        "gl": "t247_gl",  # глобальный редакторский — посты для всех регионов
    })

    # Публикуем источники приложения (Telegram/YouTube каналы, которые
    # приложение парсит само) — правка здесь меняет контент у всех без релиза
    db.reference("/config/app_sources").set(APP_SOURCES)

if __name__ == "__main__":
    main()
