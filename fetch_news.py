import os
import re
import json
import html
from collections import Counter
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
    # Португалия осталась без изданий: Público и Expresso отдают 403, DN и JN
    # закрыли ленты. Эти два живы и текст дают (13.08.2026)
    {"url": "https://observador.pt/feed/", "source": "Observador PT", "category": "NEWS", "priority": 1, "quota": 5, "scope": "pool", "lang": "pt"},
    {"url": "https://www.noticiasaominuto.com/rss/ultima-hora", "source": "Notícias ao Minuto", "category": "NEWS", "priority": 1, "quota": 5, "scope": "pool", "lang": "pt"},
    {"url": "https://opais.co.mz/feed/", "source": "O País MZ", "category": "NEWS", "priority": 0, "quota": 3, "scope": "pool", "lang": "pt"},
    # Источник годится, если текст приходит ХОТЬ ОТКУДА-ТО: со страницы или
    # из самой ленты. Сперва я судил только по странице и отбросил Axios за
    # отказ 403 — а он отдаёт 3359 знаков прямо в ленте, больше всех прочих.
    # Этим четверым страница не нужна вовсе (13.08.2026)
    {"url": "https://api.axios.com/feed/", "source": "Axios", "category": "NEWS", "priority": 2, "quota": 5, "scope": "world"},
    {"url": "https://www.semafor.com/rss.xml", "source": "Semafor", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world"},
    {"url": "https://www.france24.com/en/rss", "source": "France 24", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world"},
    {"url": "https://thehill.com/news/feed/", "source": "The Hill", "category": "NEWS", "priority": 0, "quota": 3, "scope": "world"},
    # Добор после ухода источников без текста (13.08.2026). Страницы проверены:
    # UPI 4800 знаков, Independent 3200, Straits Times 2400, Newsweek 1900.
    # Отсеяны вручную: The Conversation (разборы «что это значит» — их выбросит
    # правило про инфоповод) и Anadolu (государственное агентство, как ТАСС)
    {"url": "https://rss.upi.com/news/top_news.rss", "source": "UPI", "category": "NEWS", "priority": 2, "quota": 6, "scope": "world"},
    {"url": "https://www.independent.co.uk/news/world/rss", "source": "The Independent", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world"},
    {"url": "https://www.straitstimes.com/news/world/rss.xml", "source": "Straits Times", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world"},
    {"url": "https://www.newsweek.com/rss", "source": "Newsweek", "category": "NEWS", "priority": 0, "quota": 3, "scope": "world"},
    # ── Англоязычный мир, 15.08.2026 ────────────────────────────────────────
    # Блок «Новости из» показывал 17 флагов, а изданий из этих стран не было
    # вовсе — на весь пул выходило три новости уровня языкового пространства.
    # Ленты проверены: текст отдают либо в описании, либо на странице
    {"url": "https://www.rte.ie/feeds/rss/?index=/news/", "source": "RTÉ Ireland", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "en"},
    {"url": "https://www.irishtimes.com/arc/outboundfeeds/feed-irish-news/", "source": "Irish Times", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "en"},
    {"url": "https://globalnews.ca/feed/", "source": "Global News CA", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "en"},
    {"url": "https://www.abc.net.au/news/feed/51120/rss.xml", "source": "ABC Australia", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "en"},
    {"url": "https://www.smh.com.au/rss/feed.xml", "source": "SMH Australia", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "en"},
    {"url": "https://www.thehindu.com/news/national/feeder/default.rss", "source": "The Hindu", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "en"},
    {"url": "https://punchng.com/feed/", "source": "Punch Nigeria", "category": "NEWS", "priority": 0, "quota": 3, "scope": "pool", "lang": "en"},
    {"url": "https://jamaica-gleaner.com/feed/rss.xml", "source": "Jamaica Gleaner", "category": "NEWS", "priority": 0, "quota": 3, "scope": "pool", "lang": "en"},

    # США: были только общенациональные издания, а в стране 50 штатов —
    # местный слой выходил из четырёх новостей
    {"url": "https://www.latimes.com/local/rss2.0.xml", "source": "LA Times", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "en"},
    {"url": "https://www.seattletimes.com/feed/", "source": "Seattle Times", "category": "NEWS", "priority": 0, "quota": 3, "scope": "local", "lang": "en"},
    {"url": "https://nypost.com/feed/", "source": "NY Post", "category": "NEWS", "priority": 0, "quota": 3, "scope": "local", "lang": "en"},

    # Замена ушедшим (13.08.2026): страницы проверены, текст отдают —
    # CBS 2700 знаков, Time 7200, Fortune 9300
    {"url": "https://www.cbsnews.com/latest/rss/main", "source": "CBS News", "category": "NEWS", "priority": 2, "quota": 6, "scope": "world"},
    {"url": "https://time.com/feed/", "source": "Time", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world"},
    {"url": "https://fortune.com/feed/", "source": "Fortune", "category": "MONEY", "priority": 1, "quota": 4, "scope": "world"},
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
    {"url": "http://rss.cnn.com/rss/cnn_topstories.rss", "source": "CNN", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "en"},
    {"url": "https://feeds.washingtonpost.com/rss/national", "source": "Washington Post", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "en"},
    {"url": "https://www.politico.com/rss/politicopicks.xml", "source": "Politico", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "en"},
    # Великобритания
    {"url": "https://www.theguardian.com/uk/rss", "source": "The Guardian", "category": "NEWS", "priority": 2, "quota": 6, "scope": "world", "lang": "en"},
    {"url": "https://feeds.skynews.com/feeds/rss/home.xml", "source": "Sky News", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "en"},
    # Южная Корея — сильная англоязычная пресса специально под международную
    # аудиторию, переводить нечего, забираем как есть (scope=world — не
    # "домашняя" страна пула en, но публикуется на английском)
    # Корейские источники отключены 12.08.2026. Ленты живые, но подача не
    # годится: телеграфные пометки в заголовках («(4-й LD)» — четвёртая правка
    # материала), непереведённые тела статей, и почти всё содержимое — внутренняя
    # повестка Кореи, которая до русского читателя не доходит по смыслу.
    # Были: en.yna.co.kr/RSS/news.xml (Yonhap), feed.koreatimes.co.kr/k/allnews.xml
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
    # ── Португальский пул: было 12 источников против 44 мировых лент ──────
    # Мировая повестка одинаково заливает все пулы, и там, где своих изданий
    # мало, от пула остаётся одна витрина чужих новостей: в португальском было
    # 40 мировых новостей из 52. Бразилия — домашняя страна пула, её издания
    # идут местными; Португалия, Ангола и Мозамбик — страны пула.
    # Все ленты проверены живьём 15.08.2026
    {"url": "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml", "source": "Agência Brasil", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "pt"},
    {"url": "https://www.estadao.com.br/arc/outboundfeeds/feeds/rss/sections/brasil/?outputType=xml", "source": "Estadão", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "pt"},
    {"url": "https://www.metropoles.com/feed", "source": "Metrópoles", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "pt"},
    {"url": "https://www.poder360.com.br/feed/", "source": "Poder360", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "pt"},
    {"url": "https://www.gazetadopovo.com.br/feed/rss/republica.xml", "source": "Gazeta do Povo", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "pt"},
    {"url": "https://rss.uol.com.br/feed/noticias.xml", "source": "UOL Notícias", "category": "NEWS", "priority": 1, "quota": 5, "scope": "local", "lang": "pt"},
    {"url": "https://www.infomoney.com.br/feed/", "source": "InfoMoney", "category": "MONEY", "priority": 1, "quota": 3, "scope": "local", "lang": "pt"},
    {"url": "https://exame.com/feed/", "source": "Exame", "category": "MONEY", "priority": 1, "quota": 3, "scope": "local", "lang": "pt"},
    {"url": "https://feeds.feedburner.com/PublicoRSS", "source": "Público", "category": "NEWS", "priority": 1, "quota": 5, "scope": "pool", "lang": "pt"},
    {"url": "https://www.rtp.pt/noticias/rss", "source": "RTP Notícias", "category": "NEWS", "priority": 1, "quota": 5, "scope": "pool", "lang": "pt"},
    {"url": "https://feeds.feedburner.com/dn-ultimas", "source": "Diário de Notícias", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "pt"},
    {"url": "https://eco.sapo.pt/feed/", "source": "ECO", "category": "MONEY", "priority": 0, "quota": 3, "scope": "pool", "lang": "pt"},
    {"url": "https://www.jornaldenegocios.pt/rss", "source": "Jornal de Negócios", "category": "MONEY", "priority": 0, "quota": 3, "scope": "pool", "lang": "pt"},

    # -- Испанский пул: местных было 7 из 68 --------------------------------
    # Та же болезнь, что и в португальском: своих изданий мало, мировая лента
    # заливает остальное. Мексика - домашняя страна пула, её издания местные.
    # Проверено живьём 15.08.2026
    {"url": "https://www.jornada.com.mx/rss/edicion.xml", "source": "La Jornada", "category": "NEWS", "priority": 2, "quota": 6, "scope": "local", "lang": "es"},
    {"url": "https://www.eleconomista.com.mx/rss/ultimas-noticias", "source": "El Economista MX", "category": "MONEY", "priority": 1, "quota": 4, "scope": "local", "lang": "es"},
    {"url": "https://expansion.mx/rss", "source": "Expansión MX", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "es"},
    {"url": "https://www.reforma.com/rss/portada.xml", "source": "Reforma", "category": "NEWS", "priority": 1, "quota": 3, "scope": "local", "lang": "es"},
    {"url": "https://www.eldiario.es/rss/", "source": "eldiario.es", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "es"},
    {"url": "https://www.lavanguardia.com/rss/home.xml", "source": "La Vanguardia", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "es"},
    {"url": "https://api2.rtve.es/rss/temas_noticias.xml", "source": "RTVE", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "es"},
    {"url": "https://e00-elmundo.uecdn.es/elmundo/rss/portada.xml", "source": "El Mundo", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "es"},
    {"url": "https://www.semana.com/arc/outboundfeeds/rss/", "source": "Semana CO", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "es"},
    {"url": "https://www.diariolibre.com/rss/portada.xml", "source": "Diario Libre DO", "category": "NEWS", "priority": 0, "quota": 3, "scope": "pool", "lang": "es"},

    # Редакции штатов (сеть States Newsroom). Квота маленькая: их задача —
    # ширина охвата, а не объём. Раньше "местными" для США были только
    # национальные издания, и пятьдесят штатов сводились к Вашингтону и
    # Нью-Йорку. Из домашней сети пользователя эти ленты не открываются,
    # с серверов GitHub — все двенадцать, по сотне материалов каждая.
    # Фото в лентах нет, дотягиваем со страницы
    {"url": "https://floridaphoenix.com/feed/", "source": "Florida Phoenix", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local", "lang": "en"},
    {"url": "https://ohiocapitaljournal.com/feed/", "source": "Ohio Capital Journal", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local", "lang": "en"},
    {"url": "https://michiganadvance.com/feed/", "source": "Michigan Advance", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local", "lang": "en"},
    {"url": "https://georgiarecorder.com/feed/", "source": "Georgia Recorder", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local", "lang": "en"},
    {"url": "https://penncapital-star.com/feed/", "source": "Pennsylvania Capital-Star", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local", "lang": "en"},
    {"url": "https://ncnewsline.com/feed/", "source": "NC Newsline", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local", "lang": "en"},
    {"url": "https://azmirror.com/feed/", "source": "Arizona Mirror", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local", "lang": "en"},
    {"url": "https://minnesotareformer.com/feed/", "source": "Minnesota Reformer", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local", "lang": "en"},
    {"url": "https://coloradonewsline.com/feed/", "source": "Colorado Newsline", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local", "lang": "en"},
    {"url": "https://nevadacurrent.com/feed/", "source": "Nevada Current", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local", "lang": "en"},
    {"url": "https://virginiamercury.com/feed/", "source": "Virginia Mercury", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local", "lang": "en"},
    {"url": "https://missouriindependent.com/feed/", "source": "Missouri Independent", "category": "NEWS", "priority": 0, "quota": 2, "scope": "local", "lang": "en"},

    # -- Американские андердоги: некоммерческие редакции ---------------------
    # Мысль пользователя 15.08.2026: крупным изданиям мы не нужны, а этим —
    # наоборот. У них беда не с материалом, а с читателем, и распространение
    # для них уставная цель: материалы выходят под свободной лицензией с
    # прямой просьбой перепечатывать. Ни договариваться, ни опасаться претензий
    # не нужно. Заодно это шаг к четвёртому уровню — новостям штатов
    {"url": "https://www.texastribune.org/feeds/main/", "source": "Texas Tribune", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "en"},
    {"url": "https://mississippitoday.org/feed/", "source": "Mississippi Today", "category": "NEWS", "priority": 1, "quota": 3, "scope": "local", "lang": "en"},
    {"url": "https://www.themarshallproject.org/rss/recent.rss", "source": "Marshall Project", "category": "NEWS", "priority": 1, "quota": 3, "scope": "local", "lang": "en"},
    {"url": "https://www.propublica.org/feeds/propublica/main", "source": "ProPublica", "category": "NEWS", "priority": 1, "quota": 3, "scope": "local", "lang": "en"},

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
    # Испаноязычная Америка — добавлено 12.08.2026. Ленты проверены живыми:
    # отдают настоящие статьи, не заглушки. Emol (Чили) и El Observador (Уругвай)
    # отброшены: первый рвёт соединение, второй отдаёт 403
    {"url": "https://www.latercera.com/arcio/rss/", "source": "La Tercera CL", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "es"},
    {"url": "https://elcomercio.pe/arcio/rss/", "source": "El Comercio PE", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "es"},
    {"url": "https://rpp.pe/feed", "source": "RPP PE", "category": "NEWS", "priority": 1, "quota": 3, "scope": "pool", "lang": "es"},
    {"url": "https://www.eluniverso.com/arcio/rss/", "source": "El Universo EC", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "es"},
    {"url": "https://www.elnacional.com/feed/", "source": "El Nacional VE", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "es"},
    {"url": "https://www.prensalibre.com/rss/", "source": "Prensa Libre GT", "category": "NEWS", "priority": 0, "quota": 3, "scope": "pool", "lang": "es"},
    {"url": "https://www.nacion.com/arcio/rss/", "source": "La Nación CR", "category": "NEWS", "priority": 0, "quota": 3, "scope": "pool", "lang": "es"},
    {"url": "https://www.elsalvador.com/feed/", "source": "El Salvador", "category": "NEWS", "priority": 0, "quota": 3, "scope": "pool", "lang": "es"},
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
    {"url": "https://www.aljazeera.net/rss", "source": "Al Jazeera Arabic", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world", "lang": "ar"},

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
    # Найдено 14.08.2026 по наводке пользователя (подсмотрел в ленте Google).
    # Ленты проверены: текст отдают, страницы открываются
    {"url": "https://vlast.kz/feed/", "source": "Vlast.kz", "category": "NEWS", "priority": 1, "quota": 5, "scope": "pool", "lang": "ru"},
    {"url": "https://eco.akipress.org/rss/", "source": "AKIpress Эко", "category": "NEWS", "priority": 1, "quota": 4, "scope": "local", "lang": "ru"},
    {"url": "https://itc.ua/feed/", "source": "ITC.ua", "category": "TECH", "priority": 0, "quota": 3, "scope": "world", "lang": "ru"},
    {"url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss", "source": "РБК", "category": "NEWS", "priority": 0, "quota": 2, "scope": "world"},

    # РУССКОЯЗЫЧНЫЕ ТЕМАТИЧЕСКИЕ
    {"url": "https://rsport.ria.ru/export/rss2/archive/index.xml", "source": "РИА Спорт", "category": "SPORT", "priority": 1, "quota": 4, "scope": "world"},
    {"url": "https://www.sports.ru/rss/main.xml", "source": "Sports.ru", "category": "SPORT", "priority": 0, "quota": 3, "scope": "world"},
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
           "politico.com", "marketwatch.com", "apnews.com", "usatoday.com", "axios.com",
           "latimes.com", "seattletimes.com", "nypost.com", "cbsnews.com", "upi.com",
           "texastribune.org", "mississippitoday.org", "themarshallproject.org",
           "propublica.org",
           "floridaphoenix.com", "ohiocapitaljournal.com", "michiganadvance.com", "georgiarecorder.com", "penncapital-star.com", "ncnewsline.com", "azmirror.com", "minnesotareformer.com", "coloradonewsline.com", "nevadacurrent.com", "virginiamercury.com", "missouriindependent.com"],
    "es": ["eluniversal.com.mx", "milenio.com", "excelsior.com.mx", "jornada.com.mx",
           "proceso.com.mx", "elfinanciero.com.mx", "reforma.com",
           "eleconomista.com.mx", "expansion.mx"],
    "pt": ["globo.com", "uol.com.br", "folha.uol.com.br", "estadao.com.br",
           "band.uol.com.br", "r7.com", "cnnbrasil.com.br", "agenciabrasil.ebc.com.br",
           "metropoles.com", "poder360.com.br", "gazetadopovo.com.br",
           "infomoney.com.br", "exame.com"],
}


# ─── Средний уровень: издания языкового пространства ────────────────────────
# Между «мировым» и «моей страной» не хватало третьей ступени. Новость про
# саммит Меркосур или Кубок Либертадорес не мировая — русскому читателю она не
# нужна, — но и не местная: она интересна всем испаноязычным сразу.
#
# Такие статьи остаются внутри своего пула и НЕ ПЕРЕВОДЯТСЯ: язык уже общий.
# Это самый дешёвый способ наполнить ленту — ни запросов к переводчику, ни
# потери смысла.
#
# Домашняя страна пула сюда не входит, она в LOCAL_DOMAINS выше.
# 12.08.2026: список наполнен по-настоящему только для испанского — там добавлены
# восемь стран. Русскому, португальскому и английскому пулам изданий соседей
# почти не подключено, и блок у них пустует. Решено не спешить: лента и так
# полная, пустого блока читатель не видит. Добавляем по мере появления
# стабильных и качественных источников, а не ради заполнения.
POOL_DOMAINS = {
    # Русскоязычные издания — здесь, а не в мировых. Иначе их тексты уходят в
    # английскую, испанскую и португальскую ленты и переводятся машиной: читатель
    # в Лондоне получал материал BBC Русской службы, переведённый обратно на
    # английский, при том что рядом есть BBC News на английском изначально
    "ru": ["ria.ru", "rbc.ru", "lenta.ru", "iz.ru", "kommersant.ru", "rg.ru",
           "bbci.co.uk/russian", "habr.com", "ixbt.com", "sports.ru", "itc.ua",
           "tengrinews.kz", "zakon.kz", "vlast.kz", "gazeta.uz", "podrobno.uz", "asiaplustj.info"],
    # BBC, Guardian, Sky, Reuters, Al Jazeera сюда НЕ вносить: формально они
    # британские, но по сути это мировая лента, и она кормит все пулы. Запри их
    # в английском — остальные три пула останутся без мировой повестки
    "en": ["thehindu.com", "smh.com.au", "irishtimes.com", "nzherald.co.nz",
           "rte.ie", "globalnews.ca", "abc.net.au", "punchng.com",
           "jamaica-gleaner.com", "straitstimes.com"],
    "es": ["eldiario.es", "lavanguardia.com", "rtve.es", "elmundo.es",
           "semana.com", "diariolibre.com",
           "elpais.com", "abc.es", "marca.com", "clarin.com", "lanacion.com.ar",
           "infobae.com", "eltiempo.com", "emol.com", "latercera.com",
           "elcomercio.pe", "rpp.pe", "eluniverso.com", "elnacional.com",
           "prensalibre.com", "elsalvador.com", "nacion.com", "elobservador.com.uy",
           "bbci.co.uk/mundo"],
    # Бразильские издания тоже здесь: раньше Terra BR и BBC Brasil числились
    # мировыми, и «Ratinho высказался в эфире SBT» уходило в английскую и
    # русскую ленты. Это новости языкового пространства, не планеты
    "pt": ["publico.pt", "expresso.pt", "dn.pt", "observador.pt", "rtp.pt",
           "eco.sapo.pt", "jornaldenegocios.pt", "noticiasaominuto.com",
           "jornaldeangola.ao", "verangola.net", "opais.co.mz",
           "terra.com.br", "bbci.co.uk/portuguese", "cnnbrasil.com.br",
           "uol.com.br", "globo.com", "estadao.com.br",
           "agenciabrasil.ebc.com.br", "metropoles.com", "poder360.com.br",
           "gazetadopovo.com.br", "infomoney.com.br", "exame.com"],
}


# Языковые пулы, которые сейчас выходят в приложении. Источник, помеченный
# языком не отсюда, отбрасывается при загрузке конфига — иначе выключенный пул
# продолжает жить в базе, потому что список источников берётся ИЗ FIREBASE, а не
# из этого файла. Добавляя пул (французский, арабский), впиши его сюда.
# Издания одной редакции. BBC News, BBC World, BBC Русская служба, BBC Sport,
# BBC Mundo и BBC Brasil — шесть строк в списке источников, но один вещатель:
# в русской ленте на них приходилось 15% новостей, в английской 24%, и одно
# наводнение в Японии выходило дважды с одной и той же фотографией.
#
# Используем в двух местах: при склейке дублей (одна редакция об одном событии
# — точно дубль, порог совпадения слов ниже) и при ограничении доли в ленте.
PUBLISHER_FAMILIES = {
    "bbc": ["BBC News", "BBC World", "BBC Sport", "BBC Русская служба",
            "BBC Mundo", "BBC Brasil"],
    "cbn": ["CBN São Paulo", "CBN Rio"],
    "elpais": ["El País", "El País América"],
}


def publisher_family(source: str) -> str:
    """К какой редакции относится источник. Своё имя, если семьи нет."""
    for fam, members in PUBLISHER_FAMILIES.items():
        if source in members:
            return fam
    return source


ACTIVE_POOLS = ["ru", "en", "es", "pt"]

# Источники, снятые с эфира. Список источников СЛИВАЕТСЯ с базой, и слияние
# умеет только добавлять — без этого списка удалённый из файла источник
# продолжает жить в Firebase и попадать в ленту. Пишем кусок адреса.
RETIRED_SOURCES = [
    "yna.co.kr",        # Yonhap: телеграфные пометки в заголовках, тела статей без перевода
    "koreatimes.co.kr", # то же и внутренняя повестка Кореи
    "habr.com",         # площадка статей разработчиков, а не новостное издание:
                        # «как тестировать распределённые системы» — руководство,
                        # а не событие. Наше правило об инфоповоде выбрасывало
                        # почти всё, что он присылал, а обложки он рисует сам —
                        # узорная заставка с заголовком вместо фотографии
    # Португальский пул, проверено 15.08.2026: ленты не отдают материалов
    "www.publico.pt/rss",           # пустой ответ 202, без единого материала
    "rss.uol.com.br/feed/geral",    # 403 роботам; у UOL рабочий адрес другой
    "trendingsearches/daily/rss?geo=BR",  # Google убрал эту ленту, 404
    # Мертвы окончательно — проверено и с ноутбука, и на серверах GitHub
    # (13.08.2026). Домены не разрешаются, ленты пусты или отдают не XML
    "feeds.reuters.com",    # бесплатной ленты у Reuters больше нет
    "gezitter.org",         # домен не существует
    "elle.ru",              # домен не существует
    "drive.ru",             # лента пустая
    "kino-teatr.ru",        # отдаёт не XML
    "latercera.com",        # лента пустая
    "publico.pt",           # 403 и битый XML
    "kun.uz",               # отдаёт HTML вместо ленты
    "trends.google.com",    # Google закрыл эти ленты, 404 во всех странах
    "aljazeera.net",    # арабская лента: тексты на арабском во всех пулах.
                        # Метки языка мало — слияние не трогает записи, уже
                        # лежащие в базе, а эта попала туда раньше. Вернём,
                        # когда появится арабский пул
    # Ниже — источники, которые НЕ ОТДАЮТ ТЕКСТ. Критерий технический, а не
    # редакторский: в ленте приходит одна строка-затравка, а страница отвечает
    # отказом или молчит, и читалке нечего показать. Человек упирается в две
    # строки и кнопку «читать на сайте» — мы обещали, что так не будет.
    # Проверено 13.08.2026 запросом статьи с телефонным User-Agent
    "tass.ru",              # в RSS только подзаголовок, страница почти пустая
    "washingtonpost.com",   # соединение обрывается по таймауту
    "nytimes.com",          # 403 Forbidden
    "bloomberg.com",        # 403 Forbidden
    "skynews.com",          # 403, страница блокировки Akamai
    "marketwatch.com",      # 401 Forbidden
]

# Пулы, которые были включены и выключены: их ветки в /news надо подчистить
DISABLED_POOLS = ["vi"]


def normalize_source_scopes(sources):
    """Приводит scope источников к правилу выше. Возвращает исправленный список."""
    dropped = [s for s in sources if s.get("lang") and s["lang"] not in ACTIVE_POOLS]
    retired = [s for s in sources
               if any(dom in (s.get("url") or "").lower() for dom in RETIRED_SOURCES)]
    if dropped or retired:
        out = dropped + retired
        sources = [s for s in sources if s not in out]
        names = ", ".join(sorted({s.get("source", "?") for s in out}))
        print(f"  🚫 Источники убраны: {len(out)} ({names})")

    changed = 0
    stats = {"local": 0, "pool": 0, "world": 0}
    for s in sources:
        url = (s.get("url") or "").lower()
        # Порядок проверок важен: домашняя страна пула перекрывает языковое
        # пространство. bbc.com попадает и в POOL_DOMAINS(en), и в mundo(es) —
        # но "bbc.com/mundo" длиннее и проверяется на том же уровне, поэтому
        # язык источника решает, к какому пулу его относить
        if any(dom in url for doms in LOCAL_DOMAINS.values() for dom in doms):
            want = "local"
        elif any(dom in url for doms in POOL_DOMAINS.values() for dom in doms):
            want = "pool"
        else:
            want = "world"
        stats[want] += 1
        if s.get("scope") != want:
            changed += 1
            s["scope"] = want
    if changed:
        print(f"  ⚖️ Разметка источников исправлена: {changed}")
    print(f"  📐 Уровни: местных {stats['local']}, пуловых {stats['pool']}, мировых {stats['world']}")
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
            # Слияние, а не замена. База — главная (там живут ручные правки без
            # деплоя), но источники, добавленные в этот файл, подхватываются
            # автоматически. Раньше правка кода не давала эффекта вообще, и
            # причину искали полдня
            from_db = config["rss_sources"]
            known = {(s.get("url") or "").lower() for s in from_db}
            added = [s for s in RSS_SOURCES if (s.get("url") or "").lower() not in known]
            if added:
                names = ", ".join(s.get("source", "?") for s in added)
                print(f"  ➕ Новые источники из кода: {len(added)} ({names})")
            RSS_SOURCES = normalize_source_scopes(from_db + added)
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
    # Теги вырезаем ДО распаковки сущностей было бы правильнее, но ленты
    # приходят по-разному, поэтому чистим в два прохода и добиваем остатки.
    #
    # Простое правило <[^>]+> ломается на теге, внутри которого есть > в
    # значении атрибута: обрезав не там, оно оставляло хвост в тексте, и
    # читатель видел «data-image-caption="(Foto: Lisi Niesner / Reuters)"
    # data-large-file="https://…jpg?fit=1280"/>» вместо новости (InfoMoney).
    # Поэтому сначала выбрасываем теги вместе со значениями атрибутов в
    # кавычках, и только потом — всё остальное
    text = re.sub(r'<[a-zA-Z/!][^<>]*?(?:"[^"]*"[^<>]*?)*>', ' ', text)
    text = re.sub(r'<[^>]+>', ' ', text)
    # Осиротевшие куски разметки: одиночные атрибуты и закрывающие скобки,
    # уцелевшие от особо кривой вёрстки
    text = re.sub(r'\b(?:data|src|alt|title|class|style|width|height|srcset|sizes)'
                  r'-?[\w-]*\s*=\s*"[^"]*"', ' ', text)
    text = re.sub(r'\s*/?>\s*', ' ', text)
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
        r = requests.get("https://akchabar.com/ru/currency", timeout=15, headers=headers)
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
            "url": "https://akchabar.com/ru/currency",
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
# ТОЛЬКО https: приложение запрещает незашифрованный HTTP, и станция с адресом
# http:// не «плохо грузится», а блокируется системой мгновенно. Так молча не
# играли Cadena SER, COPE, Renascença, BBC и NPR. Список отсюда ПЕРЕКРЫВАЕТ
# зашитый в приложении — правя один, правь и второй
RADIO_STATIONS = [
    # ru: нейтральных новостных радио почти не осталось, поэтому деловые
    # Азаттык (кыргызская служба Радио Свобода) НЕ взят, хотя поток живой и
    # официальный: вещают они не круглосуточно, и между передачами в эфире
    # часами крутится заставка «This is Radio Free Europe, Prague». Станция,
    # повторяющая одну фразу, для слушателя не лучше тишины.
    # Поток, если понадобится вернуться:
    # https://rferl-ingest.akamaized.net/hls/live/2121749/axia01/master.m3u8

    # Кыргыз радиосу убрано: сервер вещания ОТРК отвечает, но эфира на нём нет
    # ни одного — ни kyrgyzradio, ни 1radio. Государственное радио ушло из
    # интернета. Кыргызстанские станции подбираем вручную: в открытой базе их
    # всего восемь и все музыкальные
    {"name": "РБК",              "url": "https://rbcreg.hostingradio.ru/rbc32.aacp",                                  "pool": "ru", "colorFrom": "FF1F3A5F", "colorTo": "FF2E6CA8"},
    {"name": "Коммерсантъ FM",   "url": "https://kommersant77.hostingradio.ru:8085/kommersant128.mp3",                 "pool": "ru", "colorFrom": "FF4A2B1E", "colorTo": "FF8A5A3B"},
    {"name": "Бизнес FM",        "url": "https://bfm.hostingradio.ru:9075/fm",                                        "pool": "ru", "colorFrom": "FF1E3B32", "colorTo": "FF2F7A63"},
    {"name": "Радио МИР",        "url": "https://icecast-mirtv.cdnvideo.ru/radio_mir_256",                             "pool": "ru", "colorFrom": "FF2B2350", "colorTo": "FF5B4BA8"},

    # ── Речевые станции по странам пулов ────────────────────────────────────
    # Радио идёт ОТ СТРАНЫ, а не от языка: португальцу в Лиссабоне бразильское
    # радио чужое, испанцу — мексиканское. Отобраны новостные и разговорные,
    # музыкальные не берём. Проверены живьём 15.08.2026
    {"name": "KQED",             "url": "https://streams.kqed.org/kqedradio",                                          "pool": "en", "colorFrom": "FF1B2A44", "colorTo": "FF35558C", "countries": "US"},
    {"name": "Newstalk",         "url": "https://edge.audioxi.com/NT",                                                 "pool": "en", "colorFrom": "FF14331F", "colorTo": "FF2A6B3F", "countries": "IE"},
    {"name": "ABC News Radio",   "url": "https://abc.streamguys1.com/live/newsradio/icecast.audio",                     "pool": "en", "colorFrom": "FF1E2F45", "colorTo": "FF3B5F8A", "countries": "AU"},
    {"name": "ABC Radio National","url": "https://abc.streamguys1.com/live/rnnsw/icecast.audio",                        "pool": "en", "colorFrom": "FF2B2440", "colorTo": "FF564A80", "countries": "AU"},

    {"name": "RAC1",             "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/RAC_1.mp3", "pool": "es", "colorFrom": "FF3A2216", "colorTo": "FF7A4A2E", "countries": "ES"},
    {"name": "88.9 Noticias",    "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/XHMFMAAC_SC.aac", "pool": "es", "colorFrom": "FF1F3A2E", "colorTo": "FF3E7A5C", "countries": "MX"},
    {"name": "El Destape Radio", "url": "https://ipanel.instream.audio/8004/stream",                                   "pool": "es", "colorFrom": "FF3A1F2C", "colorTo": "FF743E58", "countries": "AR"},
    {"name": "Cadena 3",         "url": "https://liveradio.mediainbox.net/radio3.mp3",                                 "pool": "es", "colorFrom": "FF33301A", "colorTo": "FF6B6234", "countries": "AR"},
    {"name": "RPP Noticias",     "url": "https://mdstrm.com/audio/5fab3416b5f9ef165cfab6e9/icecast.audio",             "pool": "es", "colorFrom": "FF3A1C1C", "colorTo": "FF783A3A", "countries": "PE"},
    {"name": "Bío-Bío",          "url": "https://unlimited3-cl.dps.live/biobiosantiago/aac/icecast.audio",             "pool": "es", "colorFrom": "FF16303A", "colorTo": "FF2C6274", "countries": "CL"},
    {"name": "Cooperativa",      "url": "https://unlimited3-cl.dps.live/cooperativafm/mp3/icecast.audio",              "pool": "es", "colorFrom": "FF1E2D3F", "colorTo": "FF3C5B7E", "countries": "CL"},
    {"name": "ADN Radio",        "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/ADNAAC.aac","pool": "es", "colorFrom": "FF302038", "colorTo": "FF614070", "countries": "CL"},

    {"name": "TSF Rádio Notícias","url": "https://directo.tsf.pt/tsfdirecto.mp3",                                      "pool": "pt", "colorFrom": "FF1F3340", "colorTo": "FF3E6680", "countries": "PT"},

    # Потоки HLS (.m3u8) — так вещает почти всё современное радио. Работают с
    # версии, где в приложение добавлен модуль media3-exoplayer-hls: без него
    # ExoPlayer такой адрес молча не открывает
    {"name": "CBC Radio 1",      "url": "https://cbcradiolive.akamaized.net/hls/live/2041036/ES_R1ETR/master.m3u8",   "pool": "en", "colorFrom": "FF3A1D1D", "colorTo": "FF7A3A3A", "countries": "CA"},
    {"name": "Newstalk ZB",      "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/NZME_01AAC.m3u8", "pool": "en", "colorFrom": "FF14303A", "colorTo": "FF296070", "countries": "NZ"},
    {"name": "Onda Cero",        "url": "https://atres-live.ondacero.es/live/ondacero/bitrate_1.m3u8",                "pool": "es", "colorFrom": "FF3A2A16", "colorTo": "FF7A5A2E", "countries": "ES"},
    {"name": "Radio 10",         "url": "https://radio10.stweb.tv/radio10/live/playlist.m3u8",                        "pool": "es", "colorFrom": "FF2A3A20", "colorTo": "FF547A40", "countries": "AR"},
    {"name": "Radio Nacional",   "url": "https://cdnhd.iblups.com/hls/0773874174fd4eba8bb9eff741d190dc.m3u8",         "pool": "es", "colorFrom": "FF3A1C2A", "colorTo": "FF783A54", "countries": "PE"},
    {"name": "Antena 1",         "url": "https://streaming-live.rtp.pt/liveradio/antena180a/playlist.m3u8",           "pool": "pt", "colorFrom": "FF1C3A32", "colorTo": "FF387A64", "countries": "PT"},
    {"name": "BandNews FM SP",   "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/BANDNEWSFM_SPAAC.m3u8", "pool": "pt", "colorFrom": "FF3A2016", "colorTo": "FF7A422E", "countries": "BR"},
    {"name": "Rádio Gaúcha",     "url": "https://1132747t.ha.azioncdn.net/primary/gaucha_rbs.sdp/playlist.m3u8",      "pool": "pt", "colorFrom": "FF1E2A3A", "colorTo": "FF3C5474", "countries": "BR"},

    {"name": "BBC World Service","url": "https://stream.live.vc.bbcmedia.co.uk/bbc_world_service",                      "pool": "en", "colorFrom": "FF3B1F24", "colorTo": "FF8C2F39"},
    {"name": "NPR",              "url": "https://npr-ice.streamguys1.com/live.mp3",                                     "pool": "en", "colorFrom": "FF1D3247", "colorTo": "FF2E6B8F"},
    {"name": "Times Radio",      "url": "https://timesradio.wireless.radio/stream",                                    "pool": "en", "colorFrom": "FF22303C", "colorTo": "FF44637D"},

    {"name": "Cadena SER",       "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/CADENASER.mp3","pool": "es", "colorFrom": "FF3A2036", "colorTo": "FF7C3F6E"},
    {"name": "COPE",             "url": "https://flucast13-h-cloud.flumotion.com/cope/net1.mp3",                        "pool": "es", "colorFrom": "FF20303A", "colorTo": "FF3F6C82"},
    {"name": "Catalunya Informació","url": "https://shoutcast.ccma.cat/ccma/catalunyainformacioHD.mp3",                "pool": "es", "colorFrom": "FF33291C", "colorTo": "FF7A6134"},
    {"name": "W Radio",          "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/WRADIOAAC.aac","pool": "es", "colorFrom": "FF2A1F3D", "colorTo": "FF5C3F87"},
    {"name": "El Heraldo Radio", "url": "https://stream.radiojar.com/ce31v3yah8nwv",                                   "pool": "es", "colorFrom": "FF3A1F2A", "colorTo": "FF7E3F5C"},
    {"name": "Radio UNAM",       "url": "https://tv.radiohosting.online:9486/stream",                                  "pool": "es", "colorFrom": "FF1F3A2E", "colorTo": "FF357E62"},
    {"name": "Caracol Radio",    "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/CARACOL_RADIOAAC.aac","pool": "es", "colorFrom": "FF3D2A1F", "colorTo": "FF8A5B33"},

    {"name": "BandNews FM",      "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/BANDNEWSFM_SP_ADP.aac","pool": "pt", "colorFrom": "FF1F3340", "colorTo": "FF2F6C88"},
    {"name": "CBN São Paulo",    "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/CBN_SP_ADP.aac","pool": "pt", "colorFrom": "FF23302A", "colorTo": "FF3D7A5F"},
    {"name": "CBN Rio",          "url": "https://playerservices.streamtheworld.com/api/livestream-redirect/CBN_RJ_ADP.aac","pool": "pt", "colorFrom": "FF2B2438", "colorTo": "FF574A80"},
    {"name": "Rádio Itatiaia",   "url": "https://8903.brasilstream.com.br/stream",                                     "pool": "pt", "colorFrom": "FF3A2622", "colorTo": "FF7E4C3D"},
    {"name": "Renascença",       "url": "https://22653.live.streamtheworld.com/RADIO_RENASCENCA_SC",                    "pool": "pt", "colorFrom": "FF1E2A3A", "colorTo": "FF3C5B85"},
]

def check_radio_stations(stations, workers=8, timeout=10):
    """Отсеивает станции, чей эфир молчит.

    Станции умирают тихо: адрес отвечает 404 или не отвечает вовсе, а читатель
    жмёт play и получает тишину — без единого признака, что дело не в его
    интернете. Проверкой поймано пять мёртвых из двадцати, в том числе «Кыргыз
    радиосу» (сервер вещания жив, но эфира на нём нет).

    Берём первые байты потока: этого хватает, чтобы отличить живой эфир от
    заглушки, и не качаем лишнего.

    Если молчит больше половины списка — виноваты почти наверняка мы (сеть
    раннера, а не двадцать станций разом), и тогда список идёт как есть:
    оставить читателя совсем без радио хуже, чем показать пару нерабочих.
    """
    def alive(st):
        try:
            r = requests.get(st["url"], timeout=timeout, stream=True,
                             headers={**BROWSER_HEADERS, "Range": "bytes=0-4000"})
            ok = r.status_code in (200, 206)
            ctype = (r.headers.get("Content-Type") or "").lower()
            # Важен адрес, на котором поток оказался ПОСЛЕ перенаправлений, а
            # не тот, что записан у нас. El Heraldo Radio отдавал https, но
            # уводил на http://n11.radiojar.com — приложение незашифрованный
            # HTTP блокирует молча, и станция считалась живой, оставаясь немой
            if ok and not (r.url or "").lower().startswith("https://"):
                print(f"     ↳ {st['name']}: перенаправление на незашифрованный {r.url[:60]}")
                ok = False
            # Сервер вещания на месте, но вместо звука отдаёт страницу с ошибкой.
            # Плейлисты HLS (.m3u8) сюда не попадают: часть серверов помечает их
            # text/..., а это законный поток, а не ошибка
            if ok and ctype.startswith("text/") and "mpegurl" not in ctype \
                    and ".m3u8" not in st["url"]:
                ok = False
            r.close()
            return ok
        except Exception:
            return False

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        verdicts = list(pool.map(alive, stations))

    dead = [st for st, ok in zip(stations, verdicts) if not ok]
    if dead:
        print("  📻 Молчат: " + ", ".join(d["name"] for d in dead))

    # Молчащую станцию НЕ выбрасываем, а помечаем. Выброшенная исчезает из
    # списка без следа, и человек не понимает, куда делось радио, которое он
    # слушал вчера. С меткой станция остаётся на месте, но кнопка серая и не
    # нажимается — а как только эфир вернётся, снова оживёт сама
    if len(dead) > len(stations) / 2:
        print(f"  📻 Не отвечает {len(dead)} из {len(stations)} — похоже на нашу сеть, "
              f"метки не ставим")
        return [{**st, "live": True} for st in stations]

    print(f"  📻 В эфире {len(stations) - len(dead)} из {len(stations)}")
    return [{**st, "live": bool(ok)} for st, ok in zip(stations, verdicts)]



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

# Хвосты, которые издания приклеивают в КОНЦЕ описания. Проверка качества
# (quality_check.py) показала их первым же запуском: чистили только начало
# текста, и читатель дочитывал новость до «…Выбор рекламы» или «Read more».
TAIL_PATTERNS = [
    r"\(Image credit:[^)]*\)\s*$",
    r"\(Фото:[^)]*\)\s*$",
    r"Read more\s*$",
    r"Читать далее\s*$",
    r"\[…\]\s*$",
    r"\[\.\.\.\]\s*$",
    r"The post .{0,80} appeared first on .{0,60}$",
    r"(?:©|Copyright).{0,120}$",
    r"[^.!?]{0,60}Cond[eé] Nast.{0,80}$",
    r"Все права защищены.{0,80}$",
    r"Материал полностью[^.]{0,60}$",
    r"Подпишитесь[^.]{0,80}$",
    r"Выбор рекламы\s*$",
]


def strip_tail(text: str) -> str:
    """Срезаем служебный хвост и обрываем по последнему целому предложению."""
    for _ in range(3):          # хвосты бывают слоями: «[…] Read more ©»
        before = text
        for pat in TAIL_PATTERNS:
            text = re.sub(pat, "", text, flags=re.I | re.S).rstrip(" .,—-–;:\n")
        if text == before:
            break
    # Оборвано на полуслове — отступаем до конца последнего предложения.
    # Лучше короче, но целиком: обрывок читается как поломка
    if text and text[-1] not in ".!?…»\"'":
        idx = max(text.rfind(". "), text.rfind("! "), text.rfind("? "),
                  text.rfind("…"), text.rfind(".\n"))
        if idx > 80:
            text = text[:idx + 1]
    return text.strip()


def strip_boilerplate(text: str) -> str:
    """Убираем служебные фразы источников из начала текста и хвост из конца"""
    for pattern in BOILERPLATE_PATTERNS:
        idx = text.find(pattern)
        if 0 <= idx < 300:
            text = (text[:idx] + text[idx + len(pattern):]).strip(" .,—-\n")
    return strip_tail(text)

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
               "share this", "copyright", "watch:", "listen:",
               # Подписи под фотографиями: приходят отдельным абзацем и в ленте
               # выглядят как начало статьи — «Photographer: Bonnie Cash/UPI/
               # Bloomberg», «Crédito, YouTube/Miss Universe»
               "photographer:", "photo:", "crédito,", "credito,", "credit:",
               "фото:", "иллюстрация:", "illustration:",
               # Ряд кнопок «поделиться», который часть сайтов отдаёт обычным
               # абзацем: у Axios в ленту уходило «facebook (opens in new
               # window) twitter (opens in new window)…» вместо текста новости
               "(opens in new window)", "add axios as your preferred source",
               "as your preferred source", "see more of our stories on google",
               # Заглушки живых блогов: приходят с кодом 200 и нормальной
               # разметкой, поэтому проверка ответа их не ловит (Sky Sports)
               "blog is currently unavailable", "please try again later",
               "этот блог в настоящее время недоступен",
               # Собственная реклама издания внутри текста (BBC Русская служба)
               "подписывайтесь на наши соцсети", "при первом открытии приложения",
               "получайте уведомления о важных", "недоступно на территории",
               # Зазывалки в соцсети и рассылку в конце статьи. Проверяются по
               # ОРИГИНАЛУ, до перевода: El Tiempo подклеивает «Toda la
               # información de Colombia está disponible en Facebook y Twitter,
               # así como en nuestro boletín semanal» — и это уезжало в ленту
               # как часть новости о жертвах землетрясения
               "en facebook y twitter", "no facebook e twitter",
               "boletín semanal", "boletim semanal", "nuestro boletín",
               "nosso boletim", "síguenos en", "siga-nos", "suscríbase",
               "inscreva-se", "weekly newsletter", "our newsletter",
               "toda la información de", "más noticias en")

def _page_body(url: str) -> str:
    """Текст статьи со страницы: 2-4 первых абзаца, очищенных от разметки."""
    try:
        r = requests.get(url, timeout=8, headers=BROWSER_HEADERS)
        if not r.ok:
            return ""
        soup = BeautifulSoup(r.content, "html.parser")
        root = soup.find("article") or soup
        paras, seen = [], set()
        for p in root.find_all("p"):
            t = clean_text(p.get_text(" ", strip=True))
            if len(t) < 60:                     # подписи, даты, крошки
                continue
            low = t.lower()
            if any(n in low for n in _PAGE_NOISE):
                continue
            # Куски кода и меню: часть сайтов отдаёт статью только после
            # выполнения скриптов, и в разметке лежит что угодно
            if any(m in t for m in ("{", "};", "function(", "var ", "://")):
                continue
            if t.count(" ") >= 6 and not any(c in t for c in ".!?…"):
                continue
            if len(re.findall(r"[a-zа-я][A-ZА-Я]", t)) >= 3:
                continue
            key = low[:50]
            if key in seen:
                continue
            seen.add(key)
            paras.append(t)
            if sum(len(x) for x in paras) > 700:
                break
        body = " ".join(paras).strip()

        # Абзацы не дались — берём краткое описание из мета-тега. Сайты кладут
        # его для соцсетей, и там обычно две-три сотни знаков: не статья, но
        # честное «что, где, когда». Без этого настоящие новости снимались с
        # эфира за короткий текст — «Обмеление Дуная остановило АЭС Румынии»,
        # «Суд Бишкека о подписантах письма 75»
        if len(body) < 200:
            for attrs in ({"property": "og:description"},
                          {"name": "og:description"},
                          {"name": "description"},
                          {"name": "twitter:description"}):
                tag = soup.find("meta", attrs=attrs)
                meta = clean_text(tag.get("content") or "") if tag else ""
                if len(meta) > len(body):
                    body = meta
                if len(body) >= 200:
                    break

        # 1300, а не 700: столько вмещают полторы страницы читалки — ровно тот
        # объём, который человек проглядывает без утомительной прокрутки.
        # Прежние 700 обрывали материал ради экономии, которой никто не просил
        if len(body) > 1300:
            body = body[:1300]
            idx = max(body.rfind(". "), body.rfind("! "), body.rfind("? "))
            if idx > 150:
                body = body[:idx + 1]
        body = strip_tail(body)

        # Последний рубеж: машина сама признаётся, что потеряла смысл
        if _looks_mangled(body):
            fixed = _ai_rescue_body(url, body, soup)
            if fixed:
                return fixed
        return body
    except Exception:
        return ""


def _looks_mangled(body: str) -> bool:
    """Признаки того, что мы потеряли смысл, а не просто дочитали до конца.

    Ни один из них не считает знаки ради экономии — каждый ловит СИМПТОМ:
    текст обещал продолжение и не дал его, оборвался на полуслове или не
    набрался вовсе. Только на таких страницах зовём ИИ, а не на всех подряд —
    это разница между полутора долларами в месяц и тридцатью пятью.
    """
    if not body:
        return False
    tail = body.rstrip()
    # 1. Обещан перечень, а перечня нет: «ограничения будут действовать на
    #    следующих участках:» — и тишина. Так пропал список улиц Бишкека
    if tail.endswith((":", "—", "–", "-")):
        return True
    # 2. Оборвано на полуслове: последнее предложение не закончено
    if tail and tail[-1] not in ".!?…»\"'" and len(tail.split()) > 12:
        return True
    # Пустую страницу ИИ не зовём: если текста нет (видеосюжет, фотогалерея),
    # разбирать нечего и лечить нечем. Такую новость снимает с эфира эталон
    # качества — это бесплатно и надёжнее, чем платить за подтверждение пустоты
    return False


def _ai_rescue_body(url: str, broken: str, soup) -> str:
    """Просит ИИ собрать текст новости со страницы, которую машина не осилила.

    Разбор по правилам дёшев и в девяти случаях из десяти верен, поэтому он
    идёт первым. Сюда попадают оставшиеся: перечни, врезки, страницы, где
    текст размечен не абзацами. ИИ видит ту же страницу и решает по смыслу.
    """
    if not GEMINI_API_KEY:
        return ""
    # Ключ чистим так же, как для вердиктов: в ключах Firebase запрещены
    # . # $ [ ] / — а это ровно то, из чего состоит любой адрес статьи
    key = _cache_key({"url": url})
    cached = PAGE_BODY_CACHE.get(key)
    if isinstance(cached, dict):
        return cached.get("text", "")
    try:
        # Отдаём очищенный от разметки текст страницы, а не HTML: дешевле по
        # токенам и модели не приходится продираться через вёрстку
        raw = clean_text(soup.get_text(" ", strip=True))[:12000]
        prompt = (
            "Ниже — текст веб-страницы с новостью, вперемешку с меню, рекламой "
            "и ссылками на другие материалы. Собери из него САМУ новость.\n\n"
            "Правила:\n"
            "- Верни только текст новости: ни меню, ни подписей к фото, ни "
            "«читайте также», ни имён авторов и редакции.\n"
            "- Ничего не сокращай и не пересказывай своими словами — это "
            "извлечение, а не выжимка. Перечни (улицы, списки, пункты) "
            "переноси ПОЛНОСТЬЮ: ради них новость и открывают.\n"
            "- Если текста новости на странице нет вовсе (это видеосюжет, "
            "фотогалерея или страница-заглушка), верни ровно: НЕТ_ТЕКСТА\n\n"
            f"Страница:\n{raw}"
        )
        out = ask_gemini(prompt).strip()
        if out.startswith("НЕТ_ТЕКСТА") or len(out) < 120:
            out = ""
        PAGE_BODY_CACHE[key] = {"text": out, "ts": int(datetime.now().timestamp() * 1000)}
        return out
    except Exception as e:
        print(f"  ⚠️ ИИ не смог разобрать страницу: {str(e)[:70]}")
        return ""


def enrich_short_summaries(items, min_len=400, budget=150, workers=8):
    """Дотягивает короткие описания текстом со страницы статьи.

    Мировые ленты дают одно предложение-затравку, и на экране это выглядит как
    «две строки и кнопка». Идёт ДО перевода, чтобы читатель получил резюме на
    своём языке.

    Восемь потоков, а не по очереди: раньше бюджет держали крошечным (25),
    потому что каждая страница ждала предыдущую, и короткие новости оставались
    короткими — а эталон качества их потом снимал с эфира. Дотянуть лучше, чем
    выбросить.
    """
    targets, seen_urls = [], set()
    for item in items:
        url = item.get("url", "")
        if len(item.get("summary", "")) >= min_len or not url.startswith("http"):
            continue
        if "t.me" in url or "telegram." in url or url in seen_urls:
            continue
        seen_urls.add(url)
        targets.append(item)
    targets = targets[:budget]
    if not targets:
        return

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        bodies = list(pool.map(lambda it: _page_body(it["url"]), targets))

    done = 0
    by_url = {}
    for item, body in zip(targets, bodies):
        if body and len(body) > len(item.get("summary", "")) + 80:
            item["summary"] = body
            by_url[item["url"]] = body
            done += 1
    # Копии той же статьи в списке получают тот же текст
    for item in items:
        if len(item.get("summary", "")) < min_len:
            b = by_url.get(item.get("url"))
            if b:
                item["summary"] = b
    print(f"  📄 Дотянуто текстом со страницы: {done} из {len(targets)}")


def drop_repeated_images(items):
    """Убирает логотип издания, выданный за фотографию новости.

    Часть сайтов ставит один и тот же og:image всем материалам подряд — свой
    логотип или фирменную заставку (Terra BR, UPI). В ленте это выглядит
    честной картинкой, но не говорит о новости ничего: пять разных событий с
    одинаковым логотипом.

    Признак простой и не требует распознавания картинок: если одно и то же
    изображение стоит у трёх и более новостей источника, это не снимок
    события. Лучше эмодзи-заглушка, честно говорящая «фото нет», чем логотип,
    притворяющийся фотографией.
    """
    from collections import Counter
    seen = Counter((it.get("source", ""), it.get("imageUrl", ""))
                   for it in items if (it.get("imageUrl") or "").startswith("http"))
    logos = {pair for pair, n in seen.items() if n >= 3}
    if not logos:
        return
    for it in items:
        if (it.get("source", ""), it.get("imageUrl", "")) in logos:
            it["imageUrl"] = ""
    names = sorted({src for src, _ in logos})
    print(f"  🏷 Логотип вместо фото убран у: {', '.join(names)}")


def enrich_missing_images(items, budget=450, workers=16):
    """Достаёт фотографию со страницы статьи для новостей, где её нет в ленте.

    RSS часто приходит без картинки, а сайт почти всегда кладёт og:image —
    метку для соцсетей. Без неё в ленте видна эмодзи-заглушка: в английском
    пуле такими были 40 новостей из 55.

    Два прежних изъяна, из-за которых заглушек было столько:

    1. Вызывалось ПОСЛЕ разделения по пулам. Мировая новость лежит в четырёх
       пулах копиями, и одна и та же страница открывалась четырежды — бюджет
       сгорал вчетверо быстрее. Теперь зовём до разделения, по одному разу
       на адрес.
    2. Страницы открывались по очереди, поэтому бюджет держали крошечным (15)
       и тратили только на важные новости. Восемь потоков делают ту же работу
       за секунды, и хватает на всю ленту.

    Денег это не стоит: обычное открытие страницы, не запрос к ИИ.
    """
    targets = []
    seen_urls = set()
    for item in items:
        if item.get("imageUrl"):
            continue
        url = item.get("url", "")
        if not url.startswith("http") or "t.me" in url or "telegram." in url:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        targets.append(item)
    targets = targets[:budget]
    if not targets:
        return

    # Карточка для соцсетей — не фотография. РИА (и не только) кладёт в
    # og:image картинку с ВПЕЧАТАННЫМ заголовком: у ria.ru это
    # /images/sharing/article/…. В ленте читатель видел одну и ту же фразу
    # дважды — крупным текстом сверху и ещё раз на снимке. Настоящее фото при
    # этом лежит на той же странице
    _SHARING_CARD = re.compile(r"/images/sharing/|/sharing/|/social[-_/]|og[-_]image|share[-_]card", re.I)

    def _page_photo(soup):
        """Настоящий снимок со страницы, когда og:image оказался карточкой."""
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src") or ""
            if not src.startswith("http") or _SHARING_CARD.search(src):
                continue
            if not any(e in src.lower() for e in (".jpg", ".jpeg", ".png", ".webp")):
                continue
            # Иконки, аватарки и пиксели-счётчики отсеиваем по заявленному
            # размеру: настоящая иллюстрация к статье не бывает уже 400 точек
            try:
                w = int(img.get("width") or 0)
                if 0 < w < 400:
                    continue
            except ValueError:
                pass
            if any(k in src.lower() for k in ("logo", "icon", "avatar", "banner", "pixel", "1x1")):
                continue
            return src
        return None

    def fetch(item):
        try:
            r = requests.get(item["url"], timeout=8, headers=BROWSER_HEADERS)
            if not r.ok:
                return None
            soup = BeautifulSoup(r.content, "html.parser")
            og = (soup.find("meta", property="og:image")
                  or soup.find("meta", attrs={"name": "og:image"})
                  or soup.find("meta", attrs={"name": "twitter:image"}))
            img = og.get("content") if og else None
            if img and _SHARING_CARD.search(img):
                img = _page_photo(soup)     # заголовок на картинке — ищем живое фото
            return img if img and img.startswith("http") else None
        except Exception:
            return None

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fetch, targets))

    by_url = {}
    for item, img in zip(targets, results):
        if img:
            item["imageUrl"] = img
            by_url[item["url"]] = img

    # Копии той же новости в других пулах ещё не созданы, но в общем списке
    # могут лежать записи с тем же адресом — раздаём найденное всем
    for item in items:
        if not item.get("imageUrl"):
            img = by_url.get(item.get("url"))
            if img:
                item["imageUrl"] = img

    print(f"  🖼️ Фото добыто: {len(by_url)} из {len(targets)} страниц")

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
                # ElementTree НЕ находит <media:content> по имени с приставкой:
                # для него тег зовётся «{http://search.yahoo.com/mrss/}content».
                # Поэтому поиск по "media:content" не срабатывал НИКОГДА, и
                # издания, дающие фото только так, приходили к нам без картинок
                # (Axios — три новости подряд с пустой карточкой). Ищем по
                # окончанию имени: работает при любом объявлении пространства
                for el in item_el.iter():
                    name = el.tag.rsplit("}", 1)[-1].lower()
                    if name not in ("content", "thumbnail"):
                        continue
                    url_img = el.get("url", "")
                    medium = (el.get("medium") or el.get("type") or "").lower()
                    is_img = ("image" in medium
                              or any(ext in url_img.lower()
                                     for ext in (".jpg", ".jpeg", ".png", ".webp")))
                    if url_img.startswith("http") and is_img:
                        image = url_img
                        break

            item_lang = source.get("lang") or lang
            # Исключение из «источник надёжнее детектора»: кириллица против
            # латиницы не путается, в отличие от испанского/португальского/
            # английского между собой. Vlast.kz помечен как «ru», но иногда
            # публикует материалы на английском — статичная метка это скрывала,
            # и needs_translation() считала статью уже переведённой
            if item_lang in ("ru", "ky", "uk", "kk", "be", "bg", "sr", "mk", "uz", "tg"):
                cyr = len(re.findall(r"[а-яё]", title + summary, re.I))
                lat = len(re.findall(r"[a-z]{3,}", title + summary, re.I))
                if cyr < 3 and lat >= 5:
                    item_lang = lang if lang not in ("unknown", "other") else "en"

            items.append({
                "title": title, "url": link, "summary": summary,
                "imageUrl": image, "source": source["source"],
                "category": source["category"], "source_category": source["category"],
                "priority": source["priority"],
                # Язык: явный язык источника надёжнее детектора
                # (детектор не отличает испанский/португальский от английского)
                "language": item_lang,
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
        # home — страна ЧИТАТЕЛЯ (для полки local), region — всё языковое
        # пространство (для полки pool). Раньше было одно поле на двоих, и ИИ
        # клал британские новости на полку «местные» английского пула: в region
        # значилась и Британия тоже
        "home": "Кыргызстан",
        "region": "Кыргызстан, Казахстан, Узбекистан, Таджикистан, Россия, Беларусь (СНГ/ЦА)",
        "language_name": "русском",
        "language_rule": "Контент должен быть на русском или кыргызском языке. Всё остальное — удалять.",
    },
    "en": {
        "home": "США",
        "region": "США, Великобритания, Австралия, Канада",
        "language_name": "английском",
        "language_rule": "Content must be in English. Remove anything in other languages.",
    },
    "es": {
        "home": "Мексика",
        "region": "Испания, Мексика, Аргентина, Колумбия, Чили (Латинская Америка и Испания)",
        "language_name": "испанском",
        "language_rule": "El contenido debe estar en español. Eliminar todo lo que esté en otros idiomas.",
    },
    "pt": {
        "home": "Бразилия",
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


def promote_global_stories(all_news):
    """Поднимает значимую местную новость до мировой — ДО разделения по пулам.

    Смысл в том, что местная газета пишет о своём событии первой и из первых
    рук. Землетрясение в Колумбии выходит у El Tiempo через сорок минут, а до
    мировых лент добирается через сутки, уже пересказом под чужую аудиторию.
    Забирая первоисточник напрямую, мы опережаем их на этот день.

    Поднимать надо ДО разделения: после него колумбийской статьи в русском
    пуле просто нет, поднимать будет нечего.

    Планка намеренно высокая. Если поднимать всё подряд, пулы захлебнутся
    чужой рутиной — это ровно та беда, от которой мы уходим.
    """
    local = [x for x in all_news if x.get("scope") != "world"]
    if not local:
        return

    titles = [
        f"{i+1}. [{x.get('source','?')}] {x.get('title','')}"
        for i, x in enumerate(local)
    ]

    prompt = f"""Ты выпускающий редактор мирового новостного агрегатора.

Ниже — новости из МЕСТНЫХ изданий разных стран. Обычно они остаются в своей
стране. Твоя задача — найти те немногие, что важны читателю в ЛЮБОЙ точке мира
и должны уйти во все языковые ленты.

ПОДНИМАТЬ:
· катастрофы, стихийные бедствия, аварии с большим числом жертв
· война, вторжение, крупный теракт, переворот, массовые беспорядки
· смерть или отставка главы государства, мировой знаменитости
· решения, последствия которых выходят за границы страны: санкции, закрытие
  проливов и границ, эпидемия, обвал валюты или рынка
· научный прорыв, катастрофа в космосе, событие планетарного масштаба

НЕ ПОДНИМАТЬ (это остаётся дома):
· рядовое ДТП, пожар, убийство, суд, приговор
· внутренняя политика, назначения чиновников, местные выборы
· местный спорт, культура, шоу-бизнес, погода, коммунальные отключения
· «человеческие истории» без масштаба

Будь строг: лучше пропустить сомнительное, чем залить мир чужой рутиной.
Обычно подходит от нуля до пяти новостей. Если ни одна не тянет — верни
пустой список.

Верни ТОЛЬКО JSON: {{"global": [номера]}}

НОВОСТИ:
{chr(10).join(titles[:GEMINI_CHUNK * 3])}"""

    try:
        text = ask_gemini(prompt)
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        picked = json.loads(text).get("global", [])
    except Exception as e:
        # Не подняли — не беда: новость останется в своём пуле, а не пропадёт
        print(f"⚠️ Подъём местных новостей не удался: {e}")
        return

    promoted = 0
    for n in picked:
        if 1 <= n <= len(local):
            item = local[n - 1]
            item["scope"] = "world"
            item["promoted"] = True
            promoted += 1
            print(f"  🌍 Поднято до мировой: [{item.get('source','?')}] {item.get('title','')[:90]}")
    if not promoted:
        print("  🌍 Мировых среди местных не нашлось")


# ── Память вердиктов ИИ ──────────────────────────────────────────────────────
# Новость живёт в ленте сутки, а прогон идёт каждый час — значит про одну и ту
# же статью мы спрашивали ИИ до 24 раз и платили за каждый ответ. Теперь
# спрашиваем один раз, ответ помним.
#
# Вердикт хранится в Firebase (/ai_cache/<пул>/<ключ>), чтобы переживать
# перезапуски: прогон живёт минуты, память в оперативке умирает вместе с ним.
#
# Побочная польза важнее экономии: выдача перестаёт прыгать. Раньше одна и та
# же новость то попадала в ленту, то исчезала — ИИ отвечал чуть иначе при
# каждом опросе, и читатель видел, как статья пропадает без причины.
# Модель прикреплена, а не «последняя»: псевдоним gemini-flash-latest Google
# волен вести куда угодно, и он привёл на модель примерно вдесятеро дороже
# ожидаемой — десять долларов сгорели за сутки. Здесь цена известна заранее.
# Если прикреплённой не окажется, падаем на псевдоним и громко сообщаем.
GEMINI_MODEL = "gemini-flash-lite-latest"
GEMINI_MODEL_FALLBACK = "gemini-flash-latest"

# Счётчик расхода: раньше о цене узнавали, когда деньги кончались
TOKENS = {"in": 0, "out": 0, "calls": 0}


def ask_gemini(prompt: str) -> str:
    """Один запрос к ИИ с подсчётом токенов и запасной моделью."""
    global _MODEL_IN_USE
    try:
        model = genai.GenerativeModel(_MODEL_IN_USE)
        resp = model.generate_content(prompt)
    except Exception as e:
        if "not found" in str(e).lower() or "404" in str(e):
            print(f"  ⚠️ Модель {_MODEL_IN_USE} недоступна, беру {GEMINI_MODEL_FALLBACK}")
            _MODEL_IN_USE = GEMINI_MODEL_FALLBACK
            model = genai.GenerativeModel(_MODEL_IN_USE)
            resp = model.generate_content(prompt)
        else:
            raise
    u = getattr(resp, "usage_metadata", None)
    if u:
        TOKENS["in"] += getattr(u, "prompt_token_count", 0) or 0
        TOKENS["out"] += getattr(u, "candidates_token_count", 0) or 0
    TOKENS["calls"] += 1
    return resp.text.strip()


_MODEL_IN_USE = GEMINI_MODEL

# Номер свода правил. Меняем его при КАЖДОЙ правке промпта — иначе память
# вердиктов держит решения, принятые по старым правилам, двое суток, и новое
# правило будто не работает. Так после запрета светской болтовни она осталась
# в португальской ленте: ИИ одобрил её часом раньше, и мы больше не спрашивали.
# 6 — сброс памяти после починки одностороннего кэша: за время, пока
# одобрения не запоминались, а отказы копились, накопилось 9264 записи, почти
# сплошь отказы. Оставить их значит тащить чёрный список ещё двое суток
RULES_VERSION = 7

AI_CACHE = {}
# Разобранные ИИ страницы: адрес → текст новости. Без этой памяти мы платили
# бы за одну и ту же страницу каждый час, пока новость висит в ленте — двадцать
# четыре раза вместо одного
PAGE_BODY_CACHE = {}
PAGE_BODY_TTL_MS = 48 * 3600 * 1000
# Была ли хоть одна порция без отбора: тогда запоминать вердикты нельзя
_LAST_CHUNK_FELL_BACK = False
AI_CACHE_TTL_MS = 48 * 3600 * 1000     # двое суток: сутки живёт новость + запас

# Вердикты, записанные до этого момента, к ИИ отношения не имеют: прогоны
# 13.08.2026 между 12:17 и 12:35 шли при кончившихся деньгах, и в память
# попадала случайная выборка. Отсечка дешевле и честнее, чем чистка руками
AI_CACHE_MIN_TS = 1786625100000  # 13.08.2026 12:45 UTC


def _cache_key(item) -> str:
    """Ключ статьи. В ключах Firebase запрещены . # $ [ ] / — заменяем."""
    raw = item.get("url") or item.get("title", "")
    safe = "".join(c if c not in "./#$[]" else "_" for c in raw)
    return safe[-180:] or "_"


def load_ai_cache():
    global AI_CACHE
    try:
        AI_CACHE = db.reference("/ai_cache").get() or {}
    except Exception as e:
        print(f"  ⚠️ Память вердиктов недоступна: {e}")
        AI_CACHE = {}
    total = sum(len(v) for v in AI_CACHE.values() if isinstance(v, dict))
    print(f"  🧠 Память вердиктов: {total} статей")


def load_page_bodies():
    global PAGE_BODY_CACHE
    try:
        PAGE_BODY_CACHE = db.reference("/page_bodies").get() or {}
    except Exception as e:
        print(f"  ⚠️ Память разобранных страниц недоступна: {e}")
        PAGE_BODY_CACHE = {}
    print(f"  📄 Память разобранных страниц: {len(PAGE_BODY_CACHE)}")


def save_page_bodies():
    now = int(datetime.now().timestamp() * 1000)
    cleaned = {k: v for k, v in PAGE_BODY_CACHE.items()
               if isinstance(v, dict) and now - v.get("ts", 0) < PAGE_BODY_TTL_MS}
    try:
        db.reference("/page_bodies").set(cleaned)
        print(f"  📄 Память страниц сохранена: {len(cleaned)}")
    except Exception as e:
        print(f"  ⚠️ Память страниц не сохранена: {e}")


def save_ai_cache():
    """Сохраняем, попутно выбрасывая протухшее — иначе узел растёт вечно."""
    now = int(datetime.now().timestamp() * 1000)
    cleaned = {}
    for pool, entries in AI_CACHE.items():
        if not isinstance(entries, dict):
            continue
        fresh = {k: v for k, v in entries.items()
                 if isinstance(v, dict) and now - v.get("ts", 0) < AI_CACHE_TTL_MS}
        if fresh:
            cleaned[pool] = fresh
    try:
        db.reference("/ai_cache").set(cleaned)
        print(f"  🧠 Память вердиктов сохранена: {sum(len(v) for v in cleaned.values())}")
    except Exception as e:
        print(f"  ⚠️ Память вердиктов не сохранилась: {e}")


def filter_with_gemini(news_list, lang="ru"):
    """Прогоняет пул через ИИ порциями и склеивает результат.

    Про статьи с известным вердиктом ИИ не спрашиваем вовсе — берём из памяти.
    Порядок исходного списка сохраняется: и те, что вернулись из памяти, и те,
    что судили сейчас, встают на свои места.
    """
    if not news_list:
        return news_list

    global _LAST_CHUNK_FELL_BACK
    _LAST_CHUNK_FELL_BACK = False
    pool_cache = AI_CACHE.setdefault(lang, {})
    if not isinstance(pool_cache, dict):
        pool_cache = AI_CACHE[lang] = {}

    known_keep, to_ask = {}, []
    dropped_by_memory = 0
    for idx, item in enumerate(news_list):
        v = pool_cache.get(_cache_key(item))
        if isinstance(v, dict) and v.get("ts", 0) < AI_CACHE_MIN_TS:
            v = None            # запись из эпохи случайных вердиктов
        if isinstance(v, dict) and v.get("rules") != RULES_VERSION:
            v = None            # решение по прежним правилам — пересудим
        if not isinstance(v, dict):
            to_ask.append((idx, item))
            continue
        if not v.get("keep"):
            dropped_by_memory += 1
            continue
        # Вердикт помним, а свежий текст и фото берём нынешние: статья могла
        # обрасти подробностями с прошлого часа
        fresh = dict(item)
        fresh["priority"] = v.get("priority", item.get("priority", 0))
        if v.get("category"):
            fresh["category"] = v["category"]
        if v.get("scope"):
            fresh["scope"] = v["scope"]
        known_keep[idx] = fresh

    judged = {}
    if to_ask:
        asked_items = [it for _, it in to_ask]
        out = []
        for start in range(0, len(asked_items), GEMINI_CHUNK):
            out.extend(_filter_chunk(asked_items[start:start + GEMINI_CHUNK], lang))
        kept_keys = {_cache_key(x) for x in out}
        now = int(datetime.now().timestamp() * 1000)
        remember = not _LAST_CHUNK_FELL_BACK
        if not remember:
            print(f"  🧠 [{lang}] вердикты НЕ запомнены: ИИ не отвечал, выборка случайная")
        for idx, item in to_ask:
            k = _cache_key(item)
            keep = k in kept_keys
            # Показать и запомнить — разные действия. Новость, отобранную
            # запасным путём, показываем (лента не должна пустеть), но в
            # память не пишем: это была случайность, а не решение ИИ
            if keep:
                verdict = next(x for x in out if _cache_key(x) == k)
                judged[idx] = verdict
                if remember:
                    pool_cache[k] = {
                        # "rules" ОБЯЗАТЕЛЬНО и здесь. Без него одобрение при
                        # следующем чтении отбраковывалось как «решение по
                        # прежним правилам», а отказы — записывались с версией
                        # и помнились честно. Память работала в одну сторону,
                        # чёрным списком: в логе стояло «0 оставлено, 121
                        # отсеяно», ленты худели, а за одобренные новости мы
                        # каждый час платили ИИ заново
                        "keep": True, "ts": now, "rules": RULES_VERSION,
                        "priority": verdict.get("priority", 0),
                        "category": verdict.get("category"),
                        "scope": verdict.get("scope"),
                    }
            elif remember:
                pool_cache[k] = {"keep": False, "ts": now, "rules": RULES_VERSION}

    print(f"  🧠 [{lang}] из памяти: {len(known_keep)} оставлено, "
          f"{dropped_by_memory} отсеяно | спрошено у ИИ: {len(to_ask)}")

    merged = {**known_keep, **judged}
    return [merged[i] for i in sorted(merged)]


def _filter_chunk(news_list, lang="ru"):
    if not news_list:
        return news_list

    for item in news_list:
        item["category"] = auto_categorize(item)

    # Нынешняя полка идёт в список: без неё ИИ не поймёт, что именно исправлять
    # в scope_fix, и станет размечать заново всё подряд
    titles = [
        f"{i+1}. [{item['category']}/{item.get('scope', 'world')}] {item['title']}"
        for i, item in enumerate(news_list)
    ]

    pool = POOL_CONFIG.get(lang, POOL_CONFIG["en"])
    prompt = f"""Ты редактор пула «{lang.upper()}» новостного агрегатора Ticker 24/7.
Аудитория: читатели на {pool['language_name']} языке, регион: {pool['region']}.

═══ ПРАВИЛО №1 — ЯЗЫК ═══
НЕ удаляй новость из-за того, что заголовок на чужом языке. Отбор идёт ДО
перевода: всё отобранное переводится на {pool['language_name']} следующим шагом.
Суди по СОДЕРЖАНИЮ — важно ли событие читателю пула, а не на каком языке
пришло. Раньше это правило требовало обратного, и мировая повестка не доходила
до неанглоязычных пулов: землетрясение с сотнями погибших выбрасывалось лишь
потому, что заголовок был английским.

Язык — повод удалить только в одном случае: новость интересна исключительно
носителям своего языка и региона (местная поп-звезда, локальный чемпионат,
разбор чужого законопроекта), и переводить её читателю пула незачем.

═══ ГЛАВНОЕ ПРАВИЛО — ИНФОПОВОД ═══
Прежде всего ответь по каждой новости на три вопроса: ЧТО произошло, ГДЕ и
КОГДА. Не можешь уложить ответ в одно предложение с глаголом в прошедшем
времени — это не новость, удаляй, каким бы интересным ни казался заголовок.

Отдельно про манеру западных изданий: они щедры на воду — впечатления
очевидцев, настроение улицы, размышления автора о смысле происходящего. Это
не делает материал новостью. Если, убрав ощущения и эпитеты, не остаётся
факта — что, где, когда, — удаляй.

Новость есть:      «запустили ракету», «умер премьер», «суд вынес приговор»,
                   «компания купила завод», «цена выросла на 20%»
Новости нет:       интервью-воспоминание («как мной интересовались в 2019-м»),
                   портретный очерк, колонка мнений, разбор «что это значит»,
                   подборка советов, анонс будущей передачи, пересказ слухов
                   о переходе игрока без самого перехода, «десять способов…»

Это правило важнее рубрики, важнее источника и важнее того, насколько текст
хорошо написан. Читатель открывает ленту узнать, что случилось. Материал без
события крадёт место у настоящей новости.

ЕДИНСТВЕННОЕ ИСКЛЮЧЕНИЕ — практический совет к событию, которое происходит
ПРЯМО СЕЙЧАС или сегодня: «как безопасно смотреть затмение» в день затмения,
«что делать при землетрясении» при землетрясении, «куда идти при эвакуации».
Событие даёт поводу срок годности, и завтра такой совет уже не нужен — но
сегодня он ценнее иной новости.
Совет БЕЗ привязки к сегодняшнему дню («как выбрать офисное кресло», «как
почистить кэш телефона») исключением НЕ является и удаляется.

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
- ЖИВАЯ ТРАНСЛЯЦИЯ: заголовок с пометкой «en vivo», «ao vivo», «EN DIRECTO»,
  «live», «latest», «онлайн», «минута за минутой», «главное к этому часу».
  Английские ленты маскируют их словом latest: «Iran-US war latest»,
  «Ukraine-Russia war latest» — это не новость, а страница, которая
  переписывается каждый час. Содержимое такой страницы меняется
  каждый час, а заголовок остаётся общим — в ленте выходит несвязица:
  «Милей и его меры, в прямом эфире», а в тексте трудовые иски за полгода.
  Оставляй, только если в заголовке названо конкретное событие
- РЕПОРТАЖ ВМЕСТО НОВОСТИ: текст начинается с обстановки и впечатлений
  очевидцев — «соседка заметила свет в окне», «дети бегали по двору», — а
  факт спрятан в середине. Само событие может быть настоящим, но подача
  такая, что читатель не узнает главного из первых строк. Оставляй, только
  если в первом же абзаце сказано, что именно случилось
- ПЕРЕСКАЗ ТЕЛЕПЕРЕДАЧИ ИЛИ СВЕТСКАЯ БОЛТОВНЯ: ведущий в эфире что-то сказал
  о знаменитости, блогер прокомментировал чужой поступок, обсудили слухи об
  отношениях. Событие подменяется разговором о событии. Признаки: в заголовке
  спор или оценка («разнёс», «ответил», «высказался о»), в тексте пересказ
  выпуска программы. Новостью это становится, только если объявлено решение
  или произошёл поступок: развелись, подписали контракт, ушли с поста
- Дубликаты — оставь одну лучшую версию
- ОДНО СОБЫТИЕ — ОДНА НОВОСТЬ. Издания дробят одно интервью, брифинг или
  пресс-конференцию на пять заметок с разными цитатами одного человека —
  и лента превращается в его монолог. Признаки: один источник, близкое время,
  в каждом заголовке говорит одно и то же лицо. Оставь ОДНУ, самую весомую
  (где сказано новое или принято решение), остальные удали. Так же поступай
  с «разбивкой» доклада, отчёта или заседания на отдельные тезисы
- Происшествия областного масштаба: перевернулся бензовоз на трассе в
  Самарской области, столкнулись машины в районном центре, загорелся склад.
  Для читателя другой страны это шум, даже если пишет крупное агентство
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

КАЛИБРОВКА СРОЧНОСТИ. priority=2 и метку URGENT дают МАСШТАБ и ПОСЛЕДСТВИЯ,
а не сам род события:
  · землетрясение — срочно от магнитуды 5,5 или при разрушениях и жертвах.
    Толчок 3,8 ощущается как проезжающий грузовик, это не срочная новость
  · авария — срочно при жертвах или эвакуации, а не при одном пострадавшем
  · пожар — срочно, если горит город или эвакуируют людей, а не сарай
  · заявление политика — срочно, если объявлено решение, а не мнение

СРОЧНО — ДЛЯ КОГО? Прежде чем поставить URGENT мировой новости, спроси не
"громко ли это", а "касается ли это нашего читателя". Событие внутри одной
страны бывает первой полосой у себя дома и пустым звуком за её пределами.
Читателю в Бишкеке присылали "Срочно: Луиджи Манджоне признаёт вину по
федеральному делу" — он не знает этого имени и не обязан знать.
  · URGENT мировой новости — только если последствия выходят за границы
    страны события: война, обвал рынков, крупная катастрофа, пандемия,
    решение, меняющее правила для всех, гибель мирового лидера
  · внутренняя политика, суды, отставки, скандалы и происшествия одной
    страны — категория NEWS, priority=0-1, БЕЗ URGENT, каким бы громким это
    ни было у себя дома
  · для местных новостей и новостей стран пула правило прежнее: там читатель
    свой, и порог срочности ниже

СПОРТ ЧУЖОГО ПРОСТРАНСТВА. Вид спорта, которым в странах пула не занимаются
и не смотрят, удаляй целиком: крикет и регби для испано- и португалоязычных,
бейсбол для европейцев, американский футбол вне США. Исключение — мировые
первенства, где участвует страна пула.

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

═══ ПРАВИЛО №5 — О ЧЁМ НОВОСТЬ, А НЕ КТО НАПИСАЛ ═══
Лента разложена на три полки, и новость должна лечь на ту, что отвечает её
СОДЕРЖАНИЮ. Сейчас полка определяется изданием, и выходит нелепо: заметка РБК
про швейцарскую компанию попадала к «новостям соседних стран», а материал
кыргызского сайта про выборы в США — к «местным».

  local — событие ПРОИЗОШЛО в стране читателя, то есть в {pool['home']}:
          происшествие, суд, местная власть, городская жизнь, поставки и
          стройки в этой стране. Участие иностранной стороны полку НЕ меняет:
          «Россия привезла в Кыргызстан 671 тысячу учебников» — местная
          новость, потому что случилось это в Кыргызстане и касается его школ.
          Событие в другой стране местным не является, даже если написано на
          языке пула
  pool  — событие важно нескольким странам сразу, где говорят на
          {pool['language_name']} языке ({pool['region']}): общий рынок, союзы
          и саммиты, миграция, курс валют соседей, региональный спорт, фигура,
          известная всему языковому пространству. Проверка простая: если
          событие целиком уместилось в одной стране — это НЕ pool, даже когда
          в нём участвовал кто-то извне
  world — всё остальное: мировая политика, война, глобальная экономика,
          технологии, знаменитости и компании мирового масштаба

Указывай полку ТОЛЬКО там, где нынешняя явно неверна — в поле "scope_fix".
Сомневаешься — не указывай, разметка по изданию останется как есть.

Верни ТОЛЬКО JSON без объяснений:
{{"keep": [1,3,5], "urgent": [2], "important": [3,5], "recategorize": {{"4": "SPORT", "7": "TECH"}}, "ad_suspects": [3], "scope_fix": {{"5": "world", "9": "local"}}}}

НОВОСТИ:
{chr(10).join(titles)}"""

    try:
        # Псевдоним, а не конкретная версия: Google отключает старые модели
        # без предупреждения (так умерла gemini-2.0-flash), и тогда фильтр молча
        # уходит в запасной вариант — 60 случайных статей вместо отбора
        text = ask_gemini(prompt)
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        result = json.loads(text)
        keep = [i-1 for i in result.get("keep", [])]
        urgent = set(i-1 for i in result.get("urgent", []))
        important = set(i-1 for i in result.get("important", []))
        recategorize = {int(k)-1: v for k, v in result.get("recategorize", {}).items()}
        ad_suspects = set(i-1 for i in result.get("ad_suspects", []))
        # Полка по СОДЕРЖАНИЮ, а не по изданию. Разметка по домену остаётся
        # основой — ИИ правит только явные промахи вроде заметки РБК про
        # швейцарскую компанию в блоке новостей соседних стран
        scope_fix = {
            int(k) - 1: v for k, v in result.get("scope_fix", {}).items()
            if v in ("local", "pool", "world")
        }

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
                # ПОСЛЕ переназначения рубрики: ИИ и авторазметка оба могут
                # поставить URGENT, а решает важность приоритет. Если новость не
                # признана важной (priority < 2), красный бейдж не заслужен —
                # иначе метка обесценивается, как было с разливом нефти
                if item.get("category") == "URGENT" and item.get("priority", 0) < 2:
                    item["category"] = "NEWS"
                if i in ad_suspects:
                    # "Чёрная метка" — подозрение на скрытую рекламу/PR: живёт
                    # только до следующего часового прогона, а не обычные 24ч
                    item["expiresAt"] = int(datetime.now().timestamp() * 1000) + 75 * 60 * 1000
                if i in scope_fix and scope_fix[i] != item.get("scope"):
                    print(f"  📐 [{lang}] {item.get('scope')}→{scope_fix[i]}: "
                          f"[{item.get('source','?')}] {item.get('title','')[:70]}")
                    item["scope"] = scope_fix[i]
                filtered.append(item)
        if ad_suspects:
            print(f"  🏴 Чёрная метка (подозрение на рекламу): {len(ad_suspects)}")
        print(f"  ✂️ [{lang}] отбраковано ИИ: {len(news_list) - len(filtered)} из {len(news_list)}")
        return filtered
    except Exception as e:
        print(f"⚠️ Gemini error (порция без отбора): {e}")
        # Пометка для памяти вердиктов: это НЕ решение ИИ, а случайная выборка.
        # Запомнить её значило бы закрепить случайность на двое суток вперёд
        global _LAST_CHUNK_FELL_BACK
        _LAST_CHUNK_FELL_BACK = True
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
    "live blog", "live updates", "war latest", "latest:", "q&a", "ask our", "your questions",
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

# ── Память переводов ─────────────────────────────────────────────────────────
# Новость живёт сутки, прогон идёт каждый час — без памяти одну и ту же статью
# перевели бы двадцать четыре раза и заплатили за каждый раз. Храним рядом с
# вердиктами: /translations/<пул>/<ключ>
TRANSLATIONS = {}


def load_translations():
    global TRANSLATIONS
    try:
        TRANSLATIONS = db.reference("/translations").get() or {}
    except Exception as e:
        print(f"  ⚠️ Память переводов недоступна: {e}")
        TRANSLATIONS = {}
    # Выбрасываем половинчатые записи: заголовок переведён, а тело осталось
    # оригиналом. Такие попали в память 14.08.2026 из-за ошибки в этом файле —
    # ИИ иногда возвращает заголовок без текста, и мы это запоминали
    CYR = re.compile(r"[а-яё]", re.I)
    bad = 0
    for pool, entries in list(TRANSLATIONS.items()):
        if not isinstance(entries, dict):
            continue
        for k, v in list(entries.items()):
            if not isinstance(v, dict):
                continue
            body = v.get("summary") or ""
            if not body:
                del entries[k]; bad += 1; continue
            if pool == "ru" and len(body) > 60 and not CYR.search(body):
                del entries[k]; bad += 1
    if bad:
        print(f"  🗂 Выброшено половинчатых переводов: {bad}")
    total = sum(len(v) for v in TRANSLATIONS.values() if isinstance(v, dict))
    print(f"  🗂 Память переводов: {total} статей")


def save_translations():
    now = int(datetime.now().timestamp() * 1000)
    cleaned = {}
    for pool, entries in TRANSLATIONS.items():
        if not isinstance(entries, dict):
            continue
        fresh = {k: v for k, v in entries.items()
                 if isinstance(v, dict) and now - v.get("ts", 0) < AI_CACHE_TTL_MS}
        if fresh:
            cleaned[pool] = fresh
    try:
        db.reference("/translations").set(cleaned)
        print(f"  🗂 Память переводов сохранена: {sum(len(v) for v in cleaned.values())}")
    except Exception as e:
        print(f"  ⚠️ Память переводов не сохранилась: {e}")


def _gemini_translate(items, target_lang):
    """Перевод пачки новостей через ИИ. Возвращает список пар или None.

    Почему ИИ, а не бесплатный переводчик: тот ломается ровно там, где всего
    заметнее. «a contrarreloj» (наперегонки со временем) он превратил в «на
    время», а «HD Hyundai Chairman to meet Bill Gates» — в «Председатель HD
    Hyundai Билл Гейтс», слепив двух разных людей в одного. ИИ понимает, что
    перед ним новость, держит имена, должности и падежи.
    """
    LANG_NAME = {"ru": "русский", "en": "английский", "es": "испанский", "pt": "португальский"}
    numbered = []
    for i, it in enumerate(items, 1):
        numbered.append(f"{i}. ЗАГОЛОВОК: {it.get('title','')}\n   ТЕКСТ: {(it.get('summary') or '')[:900]}")

    prompt = f"""Переведи новости на {LANG_NAME.get(target_lang, target_lang)} язык.

Требования:
· Это новостная лента, а не художественный текст: переводи точно и сухо
· Имена, фамилии, должности и названия компаний — правильно и целиком.
  «HD Hyundai Chairman to meet Bill Gates» — это председатель Hyundai
  ВСТРЕТИТСЯ С Гейтсом, а не «председатель Билл Гейтс»
· Идиомы передавай смыслом, а не по словам
· Не сокращай и не пересказывай, не добавляй ничего от себя
· Служебные пометки телеграфных лент — «(4th LD)», «UPDATE 2» — убирай

Верни ТОЛЬКО JSON без пояснений, ключ — номер новости:
{{"1": {{"title": "...", "summary": "..."}}, "2": {{"title": "...", "summary": "..."}}}}

НОВОСТИ:
{chr(10).join(numbered)}"""

    try:
        text = ask_gemini(prompt)
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        data = json.loads(text)
        out = []
        for i in range(1, len(items) + 1):
            row = data.get(str(i)) or {}
            out.append((row.get("title", "").strip(), row.get("summary", "").strip()))
        return out
    except Exception as e:
        print(f"  ⚠️ Перевод через ИИ не удался: {str(e)[:80]}")
        return None


def _wrong_alphabet(text: str, target_lang: str) -> bool:
    """Похож ли текст на другой язык, чем заказанный.

    Кириллица в испанском/португальском/английском ответе — верный признак,
    что ИИ на этой конкретной статье перепутал целевой язык. Латиница в
    русском ответе — то же самое в обратную сторону.
    """
    cyr = len(re.findall(r"[а-яё]", text, re.I))
    lat = len(re.findall(r"[a-z]{3,}", text, re.I))
    if target_lang == "ru":
        return cyr < 5 and lat >= 5
    return cyr >= 5


def translate_batch(items, target_lang):
    """Переводит title и summary на язык пула.

    Порядок: память → ИИ → бесплатный Google Translate. Бесплатный оставлен
    запасным: если ИИ не ответит, лента не должна остаться без перевода.

    Прозрачность: оригинал сохраняем в origTitle/origSummary, перевод помечаем
    флагом translated — читатель видит пометку и может свериться.
    """
    import time
    pool_mem = TRANSLATIONS.setdefault(target_lang, {})
    if not isinstance(pool_mem, dict):
        pool_mem = TRANSLATIONS[target_lang] = {}

    def apply(item, title, summary, orig_title, orig_summary):
        if not title:
            return False
        item["title"] = title
        item["summary"] = summary or orig_summary
        item["language"] = target_lang
        item["origTitle"] = orig_title
        item["origSummary"] = orig_summary
        item["translated"] = True
        return True

    pending, translated = [], 0
    for item in items:
        key = _cache_key(item)
        saved = pool_mem.get(key)
        if isinstance(saved, dict) and saved.get("title"):
            if apply(item, saved["title"], saved.get("summary", ""),
                     saved.get("origTitle", item.get("title", "")),
                     saved.get("origSummary", item.get("summary", ""))):
                translated += 1
            continue
        pending.append(item)

    from_memory = translated
    if pending:
        originals = [(it.get("title", ""), it.get("summary", "")) for it in pending]
        result = _gemini_translate(pending, target_lang)
        now = int(datetime.now().timestamp() * 1000)

        for idx, item in enumerate(pending):
            ot, os_ = originals[idx]
            t = s_ = ""
            if result:
                t, s_ = result[idx]

            # ИИ иногда сбивается и отвечает не на том языке для одной статьи
            # в порции — редкий, но настоящий сбой: заметка Engadget про
            # шпионское ПО пришла в испанскую ленту переведённой на русский.
            # Проверяем алфавит и, если он не тот, отбрасываем ответ ИИ целиком
            if t and _wrong_alphabet(t, target_lang):
                t = s_ = ""

            if not t:
                # Запасной путь: бесплатный переводчик, как раньше
                t = _gtx_translate(ot[:300], target_lang) or ""
                time.sleep(0.15)
            if not s_ and os_:
                # ИИ вернул заголовок, но не текст — такое случается, и раньше
                # мы молча оставляли английское тело под русским заголовком,
                # да ещё и запоминали эту пару на двое суток
                s_ = _gtx_translate(os_[:800], target_lang) or ""
                time.sleep(0.15)
            if apply(item, t, s_, ot, os_):
                translated += 1
                # В память кладём только честный перевод: если тело осталось
                # оригиналом, пусть следующий прогон попробует ещё раз
                body_ok = bool(s_) or not os_
                if body_ok:
                    pool_mem[_cache_key(item)] = {
                        "title": t, "summary": s_,
                        "origTitle": ot, "origSummary": os_, "ts": now,
                    }

    print(f"  ✓ Переведено {translated}/{len(items)} на {target_lang} "
          f"(из памяти {from_memory}, заново {translated - from_memory})")


# ═══════════════════════════════════════════════════════════════════════════
# СЛУЖБА КОНТРОЛЯ КАЧЕСТВА — последний рубеж перед эфиром
# ═══════════════════════════════════════════════════════════════════════════
# Проверка идёт ПЕРЕД записью в базу, а не после: то, что уже показано
# читателю, чинить поздно. Что можно исправить — исправляем молча, что нельзя
# — не выпускаем совсем.
#
# Список правил растёт из настоящих находок, а не из фантазий: каждая строка
# ниже — ошибка, которую пользователь увидел на своём экране.
# Порядок — от самых частых к редким.

# Строки, которых не должно быть в тексте новости ни при каких условиях.
# Вырезаем строку целиком, а не всю новость: обычно это одна подпись среди
# нормальных абзацев («Photographer: Bonnie Cash/UPI/Bloomberg»)
QC_JUNK_LINES = [
    r"^\s*photographer\s*:.*$",
    r"^\s*photo\s*:.*$",
    r"^\s*cr[ée]dito\s*,.*$",
    r"^\s*credit\s*:.*$",
    r"^\s*image (?:credit|source|caption)\s*:?.*$",
    r"\(image credit:[^)]*\)",
    r"^\s*getty images.*$",
    r"^\s*read more\s*$",
    r"^\s*end of\b.*$",
    r"^\s*подписывайтесь на наши соцсети.*$",
    r"^\s*при первом открытии приложения.*$",
]

# Приметы того, что вместо статьи пришла заглушка. Такую новость не чиним —
# снимаем с эфира: показывать нечего, а заголовок обещает содержание
QC_STUB_MARKERS = [
    "blog is currently unavailable", "please try again later",
    "этот блог в настоящее время недоступен", "access denied",
    "reference #", "errors.edgesuite.net", "javascript is disabled",
    "subscribe to continue", "подпишитесь, чтобы продолжить",
]



# ── ЭТАЛОН НОВОСТИ ───────────────────────────────────────────────────────────
# Чёрный список выше перечисляет известные дефекты — он ловит только то, что мы
# уже видели. Эталон работает наоборот: описывает, какой должна быть годная
# новость, и не выпускает всё, что не дотягивает, включая беды, которых мы
# ещё не встречали.
#
# Два уровня строгости, иначе лента опустеет:
#   СНИМАЕМ С ЭФИРА — читать нечего или это не наша новость
#   ПОМЕЧАЕМ В ЖУРНАЛ — изъян заметный, но материал ценнее изъяна
TITLE_MIN, TITLE_MAX = 25, 200
# 120, а не 200: «Суд принял дело бывшего сотрудника ГКНБ» — это сто знаков, но
# на «что, где, когда» отвечает полностью. Порог в 200 выбрасывал настоящие
# местные новости, а вместе с ними и атаку на поезд в Одесской области
BODY_MIN = 120
FUTURE_TOLERANCE_MS = 3 * 3600 * 1000   # часовые пояса врут в пределах пары часов

# Хвост источника в заголовке: «…, — РИА Новости», «... - BBC News»
# ПРОБЕЛЫ ОБЯЗАТЕЛЬНЫ с обеих сторон тире. Без этого правило рубило составные
# названия: «атака на порт в Усть-Луга» превращалась в «атака на порт в Усть»,
# потому что «-Луга» выглядело как подпись источника
TITLE_TAIL = re.compile(r"\s+[-—–]\s+[A-ZА-Я][^-—–]{2,24}$")


def meets_standard(item, lang):
    """Возвращает (годна, причина_снятия, список_замечаний)."""
    notes = []
    title = (item.get("title") or "").strip()
    body = (item.get("summary") or "").strip()

    if len(title) < TITLE_MIN:
        return False, "заголовок короче эталона", notes
    if len(title) > TITLE_MAX:
        notes.append("заголовок длиннее эталона")

    # Нижнего порога по длине НЕТ. Считать знаки — грубая замена пониманию:
    # «Вертолёт Apache разбился у Форт-Худа, погибли двое солдат» — восемьдесят
    # знаков, и это полноценная новость, а иная простыня на две тысячи знаков
    # события не содержит вовсе. Смысл оценивает ИИ правилом об инфоповоде,
    # эталон следит лишь за тем, чтобы карточка не оказалась пустой
    if not item.get("notifyOnly") and len(body) < 40:
        return False, "текста нет вовсе", notes

    url = item.get("url") or ""
    if not url.startswith("http"):
        return False, "нет рабочей ссылки", notes

    published = item.get("publishedAt", 0)
    now = int(datetime.now().timestamp() * 1000)
    if published > now + FUTURE_TOLERANCE_MS:
        return False, "дата из будущего", notes
    if published and now - published > 36 * 3600 * 1000:
        return False, "старше полутора суток", notes

    if item.get("scope") not in ("local", "pool", "world"):
        notes.append("уровень не проставлен")
        item["scope"] = "world"

    if item.get("translated") and not item.get("origTitle"):
        notes.append("перевод без оригинала")

    if not item.get("imageUrl"):
        notes.append("без фото")

    return True, None, notes


def quality_gate(items, lang):
    """Правит и отсеивает новости перед публикацией. Возвращает годные."""
    kept, dropped = [], []
    fixed, warned = Counter(), Counter()

    for item in items:
        title = (item.get("title") or "").strip()
        body = (item.get("summary") or "").strip()
        low = body.lower()

        # 1. Заглушка вместо статьи — снимаем с эфира
        if any(m in low for m in QC_STUB_MARKERS):
            dropped.append((item, "заглушка вместо текста"))
            continue

        # 2. Служебные строки внутри текста — вырезаем построчно
        before = body
        for pat in QC_JUNK_LINES:
            body = re.sub(pat, "", body, flags=re.I | re.M)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        if body != before:
            fixed["служебные строки"] += 1

        # 3. Хвост и обрыв на полуслове
        cleaned = strip_tail(body)
        if cleaned != body:
            fixed["хвост"] += 1
            body = cleaned

        # 4. Заголовок, продублированный первой строкой текста
        if title and body.lower().startswith(title.lower()[:40]):
            body = body[len(title):].lstrip(" .,—-:\n")
            fixed["дубль заголовка"] += 1

        # 4б. Заголовок, повторённый ВНУТРИ текста — не в начале. 24.kg вставляет
        # между двумя одинаковыми предложениями подпись к фото: «...мигрантами.
        # Фото иллюстративное. В РФ на 40 процентов сократилось...» — читатель
        # видит одну и ту же мысль дважды с посторонней фразой между ними.
        #
        # Работаем на уровне СЛОВ, не символьных индексов: первая версия искала
        # позицию по индексу в очищенной от пунктуации строке и переносила его
        # на исходный текст с окном погрешности — из-за накопленного смещения
        # окно промахивалось, и обрезка утаскивала за собой весь хвост статьи
        # с уникальными подробностями («за шесть месяцев 2026 года»).
        # Здесь ищем точную последовательность слов заголовка внутри текста и
        # вырезаем ровно её — что вокруг, не трогаем.
        if title and len(title.split()) >= 4:
            def _norm_word(w): return re.sub(r"[^\w]", "", w.lower())
            title_tokens = [_norm_word(w) for w in title.split() if _norm_word(w)]
            words = body.split()
            norm_words = [_norm_word(w) for w in words]
            n = len(title_tokens)
            for i in range(len(norm_words) - n + 1):
                if norm_words[i:i + n] == title_tokens:
                    body = re.sub(r"\s{2,}", " ", " ".join(words[:i] + words[i + n:])).strip()
                    fixed["заголовок повторён внутри текста"] += 1
                    break

        # 5. Метка «срочно», не подтверждённая важностью. Красный бейдж и пуш
        #    обесцениваются, если ими метят рядовую новость
        if item.get("category") == "URGENT" and item.get("priority", 0) < 2:
            item["category"] = "NEWS"
            fixed["незаслуженное «срочно»"] += 1

        item["summary"] = body

        # 6. Хвост источника в заголовке — «…, — РИА Новости». Источник и так
        #    подписан под карточкой, в заголовке он крадёт место
        new_title = TITLE_TAIL.sub("", title).strip()
        if new_title != title and len(new_title) >= TITLE_MIN:
            item["title"] = new_title
            fixed["хвост источника в заголовке"] += 1

        # 7. Полку определяет МЕСТО СОБЫТИЯ, а не издание.
        #
        # Здесь стоял жёсткий запрет: местное издание никогда не попадает в блок
        # «Новости из». Он был нужен, пока ИИ путался в новости «Россия привезла
        # в Кыргызстан 671 тысячу учебников» — видел две страны и ставил уровень
        # языкового пространства, хотя событие целиком уместилось в Кыргызстане.
        #
        # Но запрет оказался слишком грубым: Knews.kg написал об отставке
        # советника Мирзиёева — событие целиком узбекское, и место ему как раз
        # в блоке соседних стран. Правило вернуло его под кыргызский флаг.
        #
        # Теперь в промпте прямо сказано, что решает место события, а участие
        # иностранной стороны полку не меняет, — и подпорка здесь только мешает.

        # 8. Соответствие эталону — последнее слово
        ok, why, notes = meets_standard(item, lang)
        for n in notes:
            warned[n] += 1
        if not ok:
            dropped.append((item, why))
            continue

        kept.append(item)

    if fixed:
        parts = ", ".join(f"{k}: {v}" for k, v in fixed.most_common())
        print(f"  🛡 Контроль качества [{lang}]: исправлено — {parts}")
    if warned:
        print(f"  🛡 Замечания [{lang}]: " + ", ".join(f"{k}: {v}" for k, v in warned.most_common()))
    if dropped:
        print(f"  🛡 Снято с эфира [{lang}]: {len(dropped)}")
        for it, why in dropped[:5]:
            print(f"       {why} | [{it.get('source','?')}] {(it.get('title') or '')[:60]}")
    return kept


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
        "radio":    check_radio_stations(RADIO_STATIONS),
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
    STOP_WORDS = {
        "в","на","и","с","по","из","за","от","к","о","об","не","что","как","для","при","до","он","она","они","это",
        "the","a","an","of","in","on","for","to","and","with","after","from","says","said","his","her",
        "que","los","las","del","para","con","como","por","una","uno",
    }

    def _clean(w):
        # Знаки препинания отрываем ДО сравнения. Из-за прилипшей запятой
        # «Rongji,» не считалось словом из букв, и две заметки о смерти
        # китайского премьера прошли как разные новости
        return re.sub(r"[^\w\-]", "", w, flags=re.U)

    def title_words(title):
        return set(_clean(w).lower() for w in title.split()
                   if len(_clean(w)) > 3 and _clean(w).lower() not in STOP_WORDS)

    def proper_nouns(title):
        """Имена собственные — слова с заглавной буквы (работает между языками)"""
        return set(_clean(w) for w in title.split()
                   if len(_clean(w)) > 2 and _clean(w)[:1].isupper() and _clean(w).isalpha())

    # Насколько имя редкое в этой выдаче. «Трамп» и «Колумбия» встречаются в
    # каждой второй новости и ничего не доказывают: по ним склеивались самолёт
    # Трампа с Ормузским проливом. А «Rongji» или «Tielemans» встречаются в
    # единственном сюжете — вот это и есть признак одного события
    name_freq = Counter()
    for _it in all_news:
        name_freq.update(proper_nouns(_it.get("title", "")))

    def are_duplicates(title1, title2):
        w1, w2 = title_words(title1), title_words(title2)
        if not w1 or not w2:
            return False
        overlap = len(w1 & w2) / min(len(w1), len(w2))
        # Почти дословное совпадение — один и тот же текст у перепечаток
        if overlap >= 0.6:
            return True
        # Заголовок в три слова слипается с чем попало — ему верить нельзя
        if min(len(w1), len(w2)) < 4:
            return False
        rare_common = {n for n in proper_nouns(title1) & proper_nouns(title2)
                       if name_freq[n] <= 3}
        return bool(rare_common) and overlap >= 0.3

    # Собираем статьи об одном событии в кучки, а не выбрасываем на ходу:
    # решение, сколько версий оставить, зависит от всей кучки целиком
    def same_event_same_family(a, b) -> bool:
        """Две редакции одного вещателя об одном событии.

        Пишут разными словами и с разными цифрами — «погибли четыре человека»
        против «погибли восемь» просто потому, что вышли с разницей в час, —
        поэтому общий порог в 60% слов их не ловит. Но одна редакция не даёт
        двух РАЗНЫХ новостей с таким пересечением, так что порог можно опустить.
        """
        if publisher_family(a.get("source", "")) != publisher_family(b.get("source", "")):
            return False
        wa, wb = title_words(a.get("title", "")), title_words(b.get("title", ""))
        if len(wa) < 3 or len(wb) < 3:
            return False
        return len(wa & wb) / min(len(wa), len(wb)) >= 0.35

    clusters = []
    for item in all_news:
        for c in clusters:
            if (are_duplicates(item.get("title", ""), c[0].get("title", ""))
                    or same_event_same_family(item, c[0])):
                c.append(item)
                break
        else:
            clusters.append([item])

    # У важного события несколько версий — это не дубли, а РАЗНЫЕ ВЗГЛЯДЫ:
    # местная газета пишет с места, региональная объясняет соседям, мировая
    # даёт контекст. Читателю есть что сравнить, и в этом наше преимущество
    # перед лентой, где событие подано одним голосом.
    #
    # Условия строгие: только важное событие и только по одной версии с уровня.
    # Три пересказа одного агентства — по-прежнему дубль.
    MAX_ANGLES = 3
    deduped, angles = [], 0
    for c in clusters:
        # Порядок выбора: важность → есть фото → длиннее текст. Раньше сортировали
        # только по важности, и из двух заметок о смерти китайского премьера
        # оставалась та, где 164 знака и нет снимка, а не та, где 450 и портрет
        c.sort(key=lambda x: (
            x.get("priority", 0),
            1 if x.get("imageUrl") else 0,
            len(x.get("summary") or ""),
        ), reverse=True)
        if len(c) == 1 or c[0].get("priority", 0) < 2:
            deduped.append(c[0])
            continue
        chosen, used_scopes = [], set()
        for it in c:
            scope = it.get("scope", "world")
            if scope in used_scopes:
                continue
            used_scopes.add(scope)
            chosen.append(it)
            if len(chosen) == MAX_ANGLES:
                break
        if len(chosen) > 1:
            angles += len(chosen) - 1
            for it in chosen:
                # Пометка для приложения: показать такие рядом, а не вразнобой
                it["storyKey"] = chosen[0].get("url", "")
        deduped.extend(chosen)

    print(f"После дедупликации: {len(deduped)} (убрано {len(all_news)-len(deduped)} дублей, "
          f"оставлено вторых мнений: {angles})")
    all_news = deduped

    # Дозаполняем описания ОДИН раз, до разделения по пулам: мировая статья
    # копируется в каждый пул, и раньше её страница тянулась заново для
    # каждого — бюджет запросов выгорал вчетверо быстрее, а до части новостей
    # очередь не доходила вовсе, и они оставались с пустым описанием
    print("📝 Дозаполняем короткие описания...")
    enrich_short_summaries(all_news)
    enrich_missing_images(all_news)
    drop_repeated_images(all_news)

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

    promote_global_stories(all_news)

    load_ai_cache()
    load_page_bodies()
    load_translations()
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

        # Ни одна редакция не занимает больше пятой части ленты.
        #
        # BBC давал 15% русской ленты и 24% английской — шестью «разными»
        # источниками, которые на деле один вещатель. Читатель видит не
        # агрегатор, а пересказ одного издания. Считаем по семьям, отбираем
        # лучшее по важности: список уже отсортирован, берём первые.
        # Считаем от НАСТОЯЩЕГО размера ленты, а не от предела max_items:
        # предел 70, а статей выходит 33 — «пятая часть от 70» позволяла BBC
        # занять 14 новостей, то есть 40% реальной ленты, и правило молчало
        family_cap = max(3, len(filtered) // 5)
        per_family, capped, cut = Counter(), [], Counter()
        for x in filtered:
            fam = publisher_family(x.get("source", ""))
            if per_family[fam] >= family_cap:
                cut[fam] += 1
                continue
            per_family[fam] += 1
            capped.append(x)
        if cut:
            print(f"  ⚖️ Доля издателя ограничена [{lang}]: "
                  + ", ".join(f"{f} −{n}" for f, n in cut.most_common()))
        filtered = capped[:max_items]
        # Автоперевод: статьи не на языке пула переводим через Gemini
        # Батчи по 15 + один повтор для неудавшихся — падение батча не оставляет
        # половину пула на чужом языке (приложение фильтрует их из ленты)
        to_translate = [x for x in filtered if needs_translation(x, lang)]
        if to_translate:
            print(f"  🌍 Переводим {len(to_translate)} статей на {lang}...")
            for j in range(0, len(to_translate), 10):
                translate_batch(to_translate[j:j+10], lang)
            retry = [x for x in to_translate if needs_translation(x, lang)]
            if retry:
                print(f"  🔁 Повтор перевода {len(retry)} статей...")
                for j in range(0, len(retry), 10):
                    translate_batch(retry[j:j+10], lang)
        cats = {}
        for item in filtered:
            cats[item["category"]] = cats.get(item["category"], 0) + 1
        print(f"  После AI: {len(filtered)} | {cats}")
        # Последний рубеж перед эфиром: чиним что можно, снимаем что нельзя
        filtered = quality_gate(filtered, lang)
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

    save_ai_cache()
    save_page_bodies()
    save_translations()

    # Расход этого прогона. Цены Flash-Lite на 13.08.2026 — примерно $0.10 за
    # миллион входящих и $0.40 за миллион исходящих; считаем по ним, чтобы
    # видеть порядок суммы, а не точную копейку
    cost = TOKENS["in"] / 1e6 * 0.10 + TOKENS["out"] / 1e6 * 0.40
    print(f"💰 Расход ИИ: {TOKENS['calls']} запросов, "
          f"{TOKENS['in']:,} входящих + {TOKENS['out']:,} исходящих токенов "
          f"≈ ${cost:.4f} за прогон (≈ ${cost * 24:.2f} в сутки при часовом графике)")

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
