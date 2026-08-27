import os
import re
import hashlib
import time
import json
import html
from collections import Counter
import requests
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
from textcut import trim_to_boundary, _looks_blocked, strip_title_echo
from extract import extract_article
try:
    import trafilatura
except ImportError:          # библиотеки нет — работаем на своём разборе
    trafilatura = None
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
    "fr": "@t247feed_fr",
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
    {"url": "https://www.elfinanciero.com.mx/rss/", "source": "El Financiero", "category": "NEWS", "priority": 2, "quota": 10, "scope": "local", "lang": "es"},
    {"url": "https://www.elsoldemexico.com.mx/rss.xml", "source": "El Sol de México", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local", "lang": "es"},
    {"url": "https://www.jornada.com.mx/rss/edicion.xml", "source": "La Jornada", "category": "NEWS", "priority": 2, "quota": 10, "scope": "local", "lang": "es"},
    {"url": "https://www.eleconomista.com.mx/rss/ultimas-noticias", "source": "El Economista MX", "category": "MONEY", "priority": 1, "quota": 4, "scope": "local", "lang": "es"},
    {"url": "https://expansion.mx/rss", "source": "Expansión MX", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local", "lang": "es"},
    {"url": "https://www.excelsior.com.mx/rss/nacional", "source": "Excélsior", "category": "NEWS", "priority": 2, "quota": 10, "scope": "local", "lang": "es"},
    {"url": "https://www.reforma.com/rss/portada.xml", "source": "Reforma", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local", "lang": "es"},
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

    # ── Родные языки соседей ────────────────────────────────────────────────
    # Правило общее: у каждого народа, чьё издание мы подключим, читатель
    # увидит новости на своём языке. Поле "native" помечает язык материала —
    # приложение покажет такую новость только тому, у кого телефон на этом
    # языке. Русскоязычному читателю чужой язык в ленту не попадёт.
    # Добавить новый народ = одна строка здесь.
    {"url": "https://kun.uz/news/rss?lang=uz", "source": "Kun.uz", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "ru", "native": "uz"},
    {"url": "https://www.gazeta.uz/uz/rss/", "source": "Gazeta.uz", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "ru", "native": "uz"},
    {"url": "https://egemen.kz/rss", "source": "Egemen Qazaqstan", "category": "NEWS", "priority": 1, "quota": 4, "scope": "pool", "lang": "ru", "native": "kk"},
    {"url": "https://asiaplustj.info/tj/rss.xml", "source": "Asia-Plus", "category": "NEWS", "priority": 1, "quota": 3, "scope": "pool", "lang": "ru", "native": "tg"},

    {"url": "https://feeds.bbci.co.uk/mundo/rss/noticias/rss.xml", "source": "BBC Mundo", "category": "NEWS", "priority": 2, "quota": 6, "scope": "world", "lang": "es"},
    {"url": "https://www.infobae.com/arc/outboundfeeds/rss/", "source": "Infobae", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "es"},
    {"url": "https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/portada", "source": "El País", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "es"},
    # Латинская Америка
    {"url": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/", "source": "La Nación AR", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "es"},
    # ─── Французский пул (заведён 22.08.2026) ──────────────────────────────
    # Домашняя страна — Франция. Языковое пространство шире европейского:
    # Бельгия, Швейцария, Квебек и франкоязычная Африка, где французский —
    # язык новостей для десятков миллионов человек. Все ленты проверены
    # живьём перед добавлением: отвечают, свежие, с картинками.
    {"url": "https://www.lefigaro.fr/rss/figaro_actualites.xml", "source": "Le Figaro", "category": "NEWS", "priority": 2, "quota": 10, "scope": "local", "lang": "fr"},
    {"url": "https://www.francetvinfo.fr/titres.rss", "source": "Franceinfo", "category": "NEWS", "priority": 2, "quota": 10, "scope": "local", "lang": "fr"},
    {"url": "https://www.20minutes.fr/feeds/rss-une.xml", "source": "20 Minutes", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local", "lang": "fr"},
    {"url": "https://www.lexpress.fr/rss/alaune.xml", "source": "L'Express", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local", "lang": "fr"},
    {"url": "https://rss.rtbf.be/article/rss/highlight_rtbfinfo_info.xml", "source": "RTBF", "category": "NEWS", "priority": 2, "quota": 8, "scope": "pool", "lang": "fr"},
    {"url": "https://ici.radio-canada.ca/rss/4159", "source": "Radio-Canada", "category": "NEWS", "priority": 2, "quota": 8, "scope": "pool", "lang": "fr"},
    {"url": "https://www.ledevoir.com/rss/manchettes.xml", "source": "Le Devoir", "category": "NEWS", "priority": 1, "quota": 6, "scope": "pool", "lang": "fr"},
    {"url": "https://www.letemps.ch/articles.rss", "source": "Le Temps", "category": "NEWS", "priority": 1, "quota": 6, "scope": "pool", "lang": "fr"},
    {"url": "https://www.jeuneafrique.com/feed/", "source": "Jeune Afrique", "category": "NEWS", "priority": 2, "quota": 8, "scope": "pool", "lang": "fr"},
    {"url": "https://www.rfi.fr/fr/rss", "source": "RFI", "category": "NEWS", "priority": 2, "quota": 8, "scope": "pool", "lang": "fr"},
    # Областные и общенациональные издания добавлены 22.08.2026: местных
    # французских новостей выходило семь из семидесяти. Le Monde и Le Figaro
    # много пишут о мире, и мы честно считаем это мировой повесткой — значит
    # домашнюю ленту должны наполнять те, кто пишет о самой Франции.
    {"url": "https://www.ladepeche.fr/rss.xml", "source": "La Dépêche", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local", "lang": "fr"},
    # Замена Le Monde и Le Parisien (23.08.2026). Оба отдавали 403 на каждой
    # статье: Le Monde — «трафик опознан как робот», Le Parisien — «Access
    # Denied». Воевать с антиботом не стали, парсер должен быть надёжным.
    # Кандидаты отбирались замером, а не репутацией: средняя длина текста по
    # шести свежим статьям каждого. Отброшены Le Soir и Les Echos (тоже
    # «Access Denied»), Swissinfo и TV5Monde (адреса лент мертвы, 404 и 410),
    # Journal de Montréal (заслон на всех шести).
    {"url": "https://www.bfmtv.com/rss/news-24-7/", "source": "BFMTV", "category": "NEWS", "priority": 2, "quota": 10, "scope": "local", "lang": "fr"},          # замер: 698
    {"url": "https://www.sudouest.fr/rss.xml", "source": "Sud Ouest", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local", "lang": "fr"},            # замер: 917
    {"url": "https://www.latribune.fr/feed.xml", "source": "La Tribune", "category": "MONEY", "priority": 1, "quota": 6, "scope": "local", "lang": "fr"},        # замер: 1013
    {"url": "https://fr.africanews.com/feed/rss", "source": "Africanews FR", "category": "NEWS", "priority": 1, "quota": 8, "scope": "pool", "lang": "fr"},      # замер: 1033
    {"url": "https://www.courrierinternational.com/feed/all/rss.xml", "source": "Courrier International", "category": "NEWS", "priority": 1, "quota": 6, "scope": "world", "lang": "fr"},  # замер: 1113
    {"url": "https://www.francebleu.fr/rss/a-la-une.xml", "source": "France Bleu", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local", "lang": "fr"},
    {"url": "https://www.nicematin.com/rss", "source": "Nice-Matin", "category": "NEWS", "priority": 1, "quota": 6, "scope": "local", "lang": "fr"},
    {"url": "https://www.nouvelobs.com/rss.xml", "source": "L'Obs", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local", "lang": "fr"},
    {"url": "https://www.france24.com/fr/rss", "source": "France 24 FR", "category": "NEWS", "priority": 2, "quota": 10, "scope": "world", "lang": "fr"},
    {"url": "https://www.eluniversal.com.mx/arc/outboundfeeds/rss/", "source": "El Universal MX", "category": "NEWS", "priority": 2, "quota": 8, "scope": "local", "lang": "es"},
    {"url": "https://www.eltiempo.com/rss/colombia.xml", "source": "El Tiempo CO", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world", "lang": "es"},
    {"url": "https://www.clarin.com/rss/lo-ultimo/", "source": "Clarín AR", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "es"},
    {"url": "https://www.abc.es/rss/feeds/abcPortada.xml", "source": "ABC.es", "category": "NEWS", "priority": 1, "quota": 5, "scope": "world", "lang": "es"},
    {"url": "https://www.excelsior.com.mx/rss/nacional.xml", "source": "Excelsior MX", "category": "NEWS", "priority": 2, "quota": 7, "scope": "local", "lang": "es"},
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
    {"url": "https://kabar.kg/rss.xml", "source": "Kabar.kg", "category": "NEWS", "priority": 2, "quota": 10, "scope": "local"},
    {"url": "https://akipress.com/rss/news.rss", "source": "AKIpress", "category": "NEWS", "priority": 2, "quota": 12, "scope": "local"},
    {"url": "https://kaktus.media/?rss=1", "source": "Kaktus.media", "category": "NEWS", "priority": 2, "quota": 10, "scope": "local"},
    {"url": "https://sputnik.kg/export/rss2/archive/index.xml", "source": "Sputnik KG", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local"},
    {"url": "https://www.vb.kg/rss.xml", "source": "Вечерний Бишкек", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local"},
    {"url": "https://knews.kg/feed/", "source": "Knews.kg", "category": "NEWS", "priority": 1, "quota": 8, "scope": "local"},
    {"url": "https://www.gezitter.org/rss/", "source": "Gezitter", "category": "NEWS", "priority": 1, "quota": 6, "scope": "local"},

    # Казахстан
    {"url": "https://tengrinews.kz/rss/", "source": "Tengrinews", "category": "NEWS", "priority": 1, "quota": 4, "scope": "world"},
    {"url": "https://www.zakon.kz/rss.xml", "source": "Zakon.kz", "category": "NEWS", "priority": 0, "quota": 3, "scope": "world"},

    # Узбекистан
    {"url": "https://kun.uz/news/rss?lang=ru", "source": "Kun.uz", "category": "NEWS", "priority": 0, "quota": 3, "scope": "world"},

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
# Страна издания. Нужна для главного правила, к которому мы идём: МЕСТНАЯ
# новость — та, чья страна совпадает со страной ЧИТАТЕЛЯ, а не со страной,
# назначенной домашней для всего пула. Сейчас португалец видит под заголовком
# «Местные» бразильские новости, а аргентинец мексиканские: у пула одна
# домашняя страна на всех.
#
# Размечаем по НАЗВАНИЮ издания, а не по домену: у Público и Diário de
# Notícias общий адрес feedburner, и домен их не различает.
SOURCE_COUNTRY = {
    # США
    "LA Times": "US", "Seattle Times": "US", "NY Post": "US", "NPR News": "US",
    "NY Times": "US", "NBC News": "US", "CNN": "US", "Washington Post": "US",
    "Politico": "US", "MarketWatch": "US", "Axios": "US", "CBS News": "US",
    "UPI": "US", "Semafor": "US", "USA Today": "US", "AP News": "US",
    "Florida Phoenix": "US", "Ohio Capital Journal": "US",
    "Michigan Advance": "US", "Georgia Recorder": "US",
    "Pennsylvania Capital-Star": "US", "NC Newsline": "US",
    "Arizona Mirror": "US", "Minnesota Reformer": "US",
    "Colorado Newsline": "US", "Nevada Current": "US",
    "Virginia Mercury": "US", "Missouri Independent": "US",
    "Texas Tribune": "US", "Mississippi Today": "US",
    "Marshall Project": "US", "ProPublica": "US",
    # Португалия и Бразилия
    "Notícias ao Minuto": "PT", "Público": "PT", "Diário de Notícias": "PT",
    "Observador": "PT", "RTP Notícias": "PT",
    "Metrópoles": "BR", "Exame": "BR", "G1 Globo": "BR", "Folha de S.Paulo": "BR",
    "Estadão": "BR", "CNN Brasil": "BR", "Agência Brasil": "BR",
    "Poder360": "BR", "Gazeta do Povo": "BR", "InfoMoney": "BR",
    # Испаноязычные
    "Reforma": "MX", "El Universal MX": "MX", "La Jornada": "MX",
    "El Financiero": "MX", "El Economista MX": "MX", "Expansión MX": "MX",
    "Excélsior": "MX", "El Sol de México": "MX",
    "La Vanguardia": "ES", "El País": "ES", "Marca": "ES",
    "Semana CO": "CO", "El Tiempo CO": "CO", "Diario Libre DO": "DO",
    "La Tercera CL": "CL", "El Universo EC": "EC", "El Nacional VE": "VE",
    "Prensa Libre GT": "GT", "La Nación CR": "CR", "El Salvador": "SV",
    "Clarín AR": "AR", "Infobae": "AR", "El Comercio PE": "PE",
    # Англоязычное пространство
    "Irish Times": "IE", "RTÉ Ireland": "IE", "The Hindu": "IN",
    "Punch Nigeria": "NG", "Jamaica Gleaner": "JM", "ABC Australia": "AU",
    "Global News CA": "CA", "Straits Times": "SG", "Sky Sports": "GB",
    "BBC News": "GB", "BBC World": "GB", "BBC Sport": "GB",
    # Франкоязычные
    "Le Figaro": "FR", "Franceinfo": "FR", "20 Minutes": "FR",
    "L'Express": "FR", "France 24 FR": "FR",
    "La Dépêche": "FR", "France Bleu": "FR",
    "Nice-Matin": "FR", "L'Obs": "FR",
    "BFMTV": "FR", "Sud Ouest": "FR", "La Tribune": "FR",
    "RTBF": "BE", "Radio-Canada": "CA", "Le Devoir": "CA", "Le Temps": "CH",
    "Jeune Afrique": "SN", "RFI": "FR", "Africanews FR": "CI",
    # Кыргызстан и соседи
    "AKIpress": "KG", "AKIpress Эко": "KG", "Gezitter": "KG",
    "Kaktus.media": "KG", "Kabar.kg": "KG", "Knews.kg": "KG",
    "24.kg": "KG", "Sputnik KG": "KG", "Turmush": "KG",
    "Asia-Plus": "TJ", "Kun.uz": "UZ", "Gazeta.uz": "UZ",
    "Vlast.kz": "KZ", "Tengrinews": "KZ",
    "РБК": "RU", "РИА Новости": "RU", "Sports.ru": "RU",
}

# Домен верхнего уровня — когда издания нет в списке выше
TLD_COUNTRY = {
    "kg": "KG", "kz": "KZ", "uz": "UZ", "tj": "TJ", "ru": "RU", "ua": "UA",
    "mx": "MX", "br": "BR", "pt": "PT", "es": "ES", "ar": "AR", "cl": "CL",
    "co": "CO", "pe": "PE", "ec": "EC", "ve": "VE", "uk": "GB", "ie": "IE",
    "au": "AU", "ca": "CA", "in": "IN", "ng": "NG", "za": "ZA", "sg": "SG",
    "fr": "FR", "be": "BE", "ch": "CH", "ma": "MA", "sn": "SN", "ci": "CI",
}


def source_country(item) -> str:
    """Страна издания. Пусто — значит международное, ничьё."""
    name = (item.get("source") or "").strip()
    if name in SOURCE_COUNTRY:
        return SOURCE_COUNTRY[name]
    host = re.sub(r"^https?://", "", item.get("url") or "").split("/")[0].lower()
    return TLD_COUNTRY.get(host.rsplit(".", 1)[-1], "")


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
           "eleconomista.com.mx", "expansion.mx", "elsoldemexico.com.mx", "oem.com.mx"],
    # Домашняя страна французского пула — Франция. Но местные новости
    # читателю в Дакаре или Брюсселе подставит само приложение по его стране
    # (CountryNewsFetcher), поэтому список здесь — про Францию
    "fr": ["lefigaro.fr", "20minutes.fr",
           "lexpress.fr", "liberation.fr", "franceinfo.fr",
           "francetvinfo.fr", "ladepeche.fr", "francebleu.fr", "nicematin.com",
           "nouvelobs.com", "bfmtv.com", "sudouest.fr", "latribune.fr"],
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
# Мировые вещатели: у них есть страна, но повестка планетарная. Их нельзя
# запирать в пул родной страны — остальные останутся без мировых новостей.
WORLD_OUTLETS = {
    "BBC News", "BBC World", "BBC Sport", "BBC Русская служба", "BBC Mundo",
    "Reuters", "Al Jazeera", "Deutsche Welle", "France 24 FR", "RFI",
    "AP News", "Bloomberg", "Guardian Sport", "The Guardian", "Fortune",
    "Semafor", "Time", "The Independent",
}

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
    # Французское пространство шире европейского: Магриб и Западная Африка —
    # десятки миллионов читателей, для которых французский и есть язык новостей
    "fr": ["rtbf.be", "lesoir.be", "rts.ch", "letemps.ch", "radio-canada.ca",
           "lapresse.ca", "ledevoir.com", "jeuneafrique.com", "rfi.fr",
           "lematin.ma", "seneweb.com", "aps.sn", "abidjan.net",
           "africanews.com"],
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


ACTIVE_POOLS = ["ru", "en", "es", "pt", "fr"]

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
    # Проверено из GitHub Actions 17.08.2026: ни одна из этих лент не дала за
    # неделю ни одной новости. Кыргызстанские и казахстанские особенно обидны —
    # из-за них местный блок держался на трёх источниках
    # Французские, 23.08.2026: антибот на каждой статье. Решено не воевать —
    # парсер должен быть надёжным, а не зависеть от капризов Cloudflare
    "lemonde.fr",               # 403 на всех статьях: «трафик опознан как робот»
    "leparisien.fr",            # 403 «Access Denied», и RSS без текста вовсе
    "ouest-france.fr",          # 403 на статьях, RSS даёт 157 знаков — пустышка
    "vb.kg/rss",                # 404, ленту с сайта убрали
    "zakon.kz",                 # 404, ленту с сайта убрали
    "tengrinews.kz",            # не отвечает ни из дома, ни из GitHub
    "super.kg",                 # 404
    "rsport.ria.ru",            # 404
    "cosmo.ru",                 # 404
    "tourprom.ru",              # 404
    # Google закрыл ленты трендов — 404 по всем странам разом
    "trendingsearches/daily/rss",
    # Отдают роботам 403/406/202 и ни одной новости за неделю
    "newsweek.com/rss",
    "politico.com/rss",
    "seattletimes.com/feed",
    "noticias.uol.com.br/ultnot",
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
    "excelsior.com.mx/rss/nacional.xml",   # пустая лента; рабочая — без .xml
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
        if s.get("source", "") in WORLD_OUTLETS:
            # Мировые вещатели остаются мировыми, хотя страна у них есть:
            # запри BBC в английском пуле — и остальные останутся без мировой
            # повестки
            want = "world"
        elif any(dom in url for doms in LOCAL_DOMAINS.values() for dom in doms):
            want = "local"
        elif any(dom in url for doms in POOL_DOMAINS.values() for dom in doms):
            want = "pool"
        elif any(SOURCE_COUNTRY.get(s.get("source", "")) in space
                 for space in POOL_COUNTRIES.values()):
            # Издание не в списках, но страна его известна и входит в чьё-то
            # языковое пространство — значит новость региональная, а не
            # мировая. 22.08 русская лента Kun.uz числилась мировой, и авария
            # с узбекистанцами в Казахстане ушла во французский пул,
            # переведённая на французский. «Мир» не должен быть свалкой
            # неопознанных изданий: мировое расходится по ВСЕМ пулам
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
            # Настройки известного источника берём ИЗ КОДА, а не из базы.
            # 19.08 поднял мексиканцам квоты в файле — и ничего не изменилось:
            # база хранит копию с прежними числами и молча выигрывает. Список
            # изданий базой пополнять по-прежнему можно (ручная правка без
            # выкладки), но квота, вес и полка живут в файле, где у них есть
            # история и объяснение.
            by_url = {(s.get("url") or "").lower(): s for s in RSS_SOURCES}
            fixed = []
            for s in from_db:
                code = by_url.get((s.get("url") or "").lower())
                if code:
                    s = {**s, **{k: code[k] for k in
                                 ("quota", "priority", "scope", "lang", "category")
                                 if k in code}}
                    fixed.append(s)
                else:
                    fixed.append(s)
            from_db = fixed
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
    # ─── Французский пул (22.08.2026) ──────────────────────────────────────
    # Здесь правило «новости хотя бы дважды в час» выполняется с запасом:
    # France Info — круглосуточная новостная станция, новости каждые четверть
    # часа. Все потоки проверены живьём. Страны проставлены, чтобы бельгийцу
    # первой предлагалась RTBF, а квебекцу — Radio-Canada.
    {"name": "France Info", "url": "https://icecast.radiofrance.fr/franceinfo-midfi.mp3", "pool": "fr", "colorFrom": "FF1B2A4A", "colorTo": "FF2E5FA3", "countries": ""},
    {"name": "France Inter", "url": "https://icecast.radiofrance.fr/franceinter-midfi.mp3", "pool": "fr", "colorFrom": "FF2A1B4A", "colorTo": "FF5B3EA3", "countries": ""},
    {"name": "France Culture", "url": "https://icecast.radiofrance.fr/franceculture-midfi.mp3", "pool": "fr", "colorFrom": "FF3A2A1B", "colorTo": "FF8A5B2E", "countries": ""},
    {"name": "RFI Monde", "url": "https://rfimonde64k.ice.infomaniak.ch/rfimonde-64.mp3", "pool": "fr", "colorFrom": "FF1B3A2A", "colorTo": "FF2E8A5B", "countries": ""},
    {"name": "RTBF La Première", "url": "https://radios.rtbf.be/laprem1ere-128.mp3", "pool": "fr", "colorFrom": "FF4A1B2A", "colorTo": "FFA33E5B", "countries": "BE"},
    {"name": "RTS La 1ère", "url": "https://stream.srg-ssr.ch/m/la-1ere/mp3_128", "pool": "fr", "colorFrom": "FF1B3A4A", "colorTo": "FF2E7AA3", "countries": "CH"},
    {"name": "Radio-Canada Première", "url": "https://rcavliveaudio.akamaized.net/hls/live/2006635/M-6A_MTL/master.m3u8", "pool": "fr", "colorFrom": "FF4A2A1B", "colorTo": "FFA35B2E", "countries": "CA"},

    # ru: нейтральных новостных радио почти не осталось, поэтому деловые
    # Азаттык (кыргызская служба Радио Свобода) НЕ взят, хотя поток живой и
    # официальный: вещают они не круглосуточно, и между передачами в эфире
    # часами крутится заставка «This is Radio Free Europe, Prague». Станция,
    # повторяющая одну фразу, для слушателя не лучше тишины.
    # Поток, если понадобится вернуться:
    # https://rferl-ingest.akamaized.net/hls/live/2121749/axia01/master.m3u8

    # Кыргыз радиосу — государственное радио, речевое и новостное.
    #
    # 15.08.2026 сервер ОТРК отвечал, но эфира на нём не было ни одного, и
    # станцию пришлось убрать. 17.08 вещание вернулось: 63 слушателя онлайн.
    # Оставляем в списке насовсем — если замолчит снова, часовая проверка
    # погасит кнопку сама, и правка руками больше не понадобится.
    # «Биринчи» по-прежнему не отвечает, «Миң кыял» музыкальное — не берём
    # «Кыргыз радиосу» и «Биринчи» убраны 22.08.2026: домен liveradio.utrk.kg
    # удалён целиком — NXDOMAIN и у Google, и у Cloudflare, а это не сбой
    # эфира, а исчезновение имени. Вещатель переехал на ktrk.kg и потока там
    # не выкладывает. Речевой станции Кыргызстана у нас снова нет; живы только
    # музыкальные: Кыргызстан Обондору, Сүйүнчү FM, Радио Тумар FM.
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
# Каналы прямых эфиров. Первое поле — либо идентификатор канала, либо
# «собачка» (@france24): по ней YouTube отдаёт идентификатор за одну единицу
# квоты, и мы его запоминаем. Собачки надёжнее — они на виду, их можно
# проверить глазами, и они переживают смену внутреннего идентификатора.
#
# Если собачка не нашлась, канал молча пропускается, а в логе появляется
# строка с его именем: список правится по логу, а не гаданием.
LIVE_CHANNELS = [
    # английский
    ("UCoMdktPbSTixAyNGwb-UYkQ", "Sky News",            "en"),
    ("UCNye-wNBqNL5ZzHSJj3l8Bg", "Al Jazeera English",  "en"),
    ("@DWNews",                  "DW News",             "en"),
    ("@euronews",                "Euronews",            "en"),
    ("@ABCNews",                 "ABC News Live",       "en"),
    # русский
    ("UCFzJjgVicCtFxJ5B0P_ei8A", "Euronews по-русски",  "ru"),
    ("@currenttimetv",           "Настоящее Время",     "ru"),
    ("@dw_russian",              "DW на русском",       "ru"),
    # испанский
    ("@dwespanol",               "DW Español",          "es"),
    ("@euronewses",              "Euronews en español", "es"),
    ("@France24_es",             "FRANCE 24 Español",   "es"),
    ("@rtvenoticias",            "RTVE Noticias",       "es"),
    ("@nmas",                    "N+",                  "es"),
    # португальский
    ("@dwbrasil",                "DW Brasil",           "pt"),
    ("@euronewspt",              "Euronews em português", "pt"),
    ("@CNNbrasil",               "CNN Brasil",          "pt"),
    ("@jovempannews",            "Jovem Pan News",      "pt"),
    ("@SICNoticias",             "SIC Notícias",        "pt"),
    # французский
    ("@FRANCE24",                "FRANCE 24",           "fr"),
    ("@franceinfo",              "franceinfo",          "fr"),
    ("@euronewsfr",              "euronews (français)", "fr"),
    ("@BFMTV",                   "BFMTV",               "fr"),
    ("@LCI",                     "LCI",                 "fr"),
]

LIVE_REFRESH_HOURS = 3


def _resolve_handle(handle: str, cache: dict) -> str:
    """Идентификатор канала по «собачке». Одна единица квоты, потом из памяти.

    Собачку (@france24) видно в адресе канала, её можно проверить глазами и
    поправить, не заглядывая в код. Внутренний идентификатор вида
    UCoMdktPbSTixAyNGwb-UYkQ проверить нельзя ничем, кроме запроса, — а
    ошибиться в нём легко и заметить трудно.
    """
    key = f"handle:{handle.lower()}"
    if cache.get(key):
        return cache[key]
    if not YOUTUBE_API_KEY:
        return ""
    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={"part": "id", "forHandle": handle.lstrip("@"),
                    "key": YOUTUBE_API_KEY},
            timeout=15)
        if not r.ok:
            return ""
        items = r.json().get("items", [])
        if not items:
            return ""
        cid = items[0].get("id") or ""
        if cid:
            cache[key] = cid
        return cid
    except Exception:
        return ""


def _live_check_pinned(pins: dict) -> dict:
    """Проверяет разом, идут ли уже известные эфиры. Возвращает {videoId: снимок}.

    Стоит ОДНУ единицу квоты на все каналы сразу — videos.list принимает до
    пятидесяти идентификаторов через запятую. Для сравнения: search.list стоит
    сто единиц ЗА КАЖДЫЙ канал.

    Замер 24.08.2026: три канала опрашивались поиском восемь раз в сутки —
    2400 единиц из 10000, почти четверть квоты на три ссылки. Девять каналов
    стоили бы 7200. По этому пути девять каналов стоят 8 единиц в сутки.

    Мы ведь не ищем эфир, а проверяем известный: у новостных каналов вещание
    круглосуточное и идентификатор видео месяцами не меняется.
    """
    ids = [v for v in pins.values() if v]
    if not ids or not YOUTUBE_API_KEY:
        return {}
    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={"part": "snippet", "id": ",".join(ids[:50]),
                    "key": YOUTUBE_API_KEY},
            timeout=15)
        if not r.ok:
            return {}
        out = {}
        for it in r.json().get("items", []):
            sn = it.get("snippet", {})
            # «live» — идёт прямо сейчас. «upcoming» и «none» не годятся:
            # первое ещё не началось, второе уже закончилось и стало записью
            if sn.get("liveBroadcastContent") == "live":
                out[it.get("id")] = sn
        return out
    except Exception:
        return {}


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
    # Ручной запуск делает работу всегда — тем же правилом, что и проверка
    # свежести ленты. Иначе, добавив канал, приходится ждать три часа, чтобы
    # узнать, нашёлся ли он
    forced = os.environ.get("FORCE_RUN") == "true"
    if not forced and now_ms - updated_at < LIVE_REFRESH_HOURS * 3600 * 1000:
        age_h = (now_ms - updated_at) / 3600000
        print(f"  ⏭ Эфиры: обновлялись {age_h:.1f} ч назад, пропускаем (раз в {LIVE_REFRESH_HOURS} ч)")
        return existing

    # Сначала дешёвая проверка уже известных эфиров: одна единица квоты на
    # все каналы. Дорогой поиск останется только тем, кто пропал из эфира
    pins = (existing.get("pins") or {}) if isinstance(existing, dict) else {}
    alive = _live_check_pinned(pins)
    if alive:
        print(f"  ⚡ Эфиры по известным ссылкам: {len(alive)} за 1 единицу квоты")

    items, new_pins, searched, unresolved = [], dict(pins), 0, []
    for raw_id, name, pool in LIVE_CHANNELS:
        if raw_id.startswith("@"):
            channel_id = _resolve_handle(raw_id, new_pins)
            if not channel_id:
                unresolved.append(f"{name} ({raw_id})")
                continue
        else:
            channel_id = raw_id
        vid = pins.get(channel_id)
        if vid and vid in alive:
            sn = alive[vid]
            th = sn.get("thumbnails", {})
            items.append({
                "channelId": channel_id, "name": name, "pool": pool,
                "videoId": vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "title": (sn.get("title") or name).strip(),
                "imageUrl": (th.get("high") or th.get("medium") or {}).get("url"),
            })
            continue
        try:
            searched += 1
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
            new_pins[channel_id] = video_id
            print(f"  ✓ Эфир {name}: {video_id} (поиском, 100 единиц)")
        except Exception as e:
            print(f"  ✗ Эфир {name}: {e}")

    if unresolved:
        print(f"  ⚠️ Каналы не нашлись по собачке: {', '.join(unresolved)}")
    if not items:
        print("  · Эфиры: ничего не нашли, прежние ссылки оставляем как есть")
        return existing
    print(f"✅ Эфиры обновлены: {len(items)}, поиском искали {searched} "
          f"(≈{searched * 100 + (1 if pins else 0)} единиц квоты)")
    return {"items": items, "updatedAt": now_ms, "pins": new_pins}


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

    # Берём до 600 знаков по границе предложения. Прежде здесь перебирались
    # разделители по очереди: сначала «. », и только если такой точки не
    # нашлось — «! » и «? ». Порядок означал, что текст с восклицанием в конце
    # резался по более ранней точке, а не по ближайшей границе. Правило
    # обрезки теперь одно на весь конвейер.
    return trim_to_boundary(text, 600).strip()

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
               # Подпись авторства, просочившаяся в текст: «Автором материала
               # является K-News . K-News»
               "автором материала является", "автор материала:",
               "материал подготовлен редакцией",
               # Ряд кнопок «поделиться», который часть сайтов отдаёт обычным
               # абзацем: у Axios в ленту уходило «facebook (opens in new
               # window) twitter (opens in new window)…» вместо текста новости
               "(opens in new window)", "add axios as your preferred source",
               "as your preferred source", "see more of our stories on google",
               # Straits Times шлёт вместо новости приглашение подписаться и
               # служебные строки дат: «Sign up now: Get ST's newsletters
               # delivered to your inbox», «Published Aug 15», «Updated Aug 15»
               "sign up now:", "newsletters delivered to your inbox",
               "get st's newsletters", "subscribe to read", "read this subscriber",
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

_CURRENCY_CODES = {"USD", "EUR", "RUB", "KZT", "UZS", "KGS", "GBP", "CNY", "TRY",
                   "JPY", "BRL", "MXN", "ARS", "CLP", "COP", "INR", "AED"}


def _is_sidebar_table(rows: list) -> bool:
    """Таблица со страницы, но не из статьи — виджет сайта.

    Таблицы мы берём ради сути: цены на ГСМ, расписание, результаты. Но на
    странице висят и постоянные виджеты, и один такой пробрался читателю в
    текст: новость 24.kg о квантовой телепортации начиналась строкой
    «USD — 87.45 EUR — 101.76 RUB — 1.19 KZT — 0.18 UZS — 0.01», после
    которой шли «Физики разработали...». Курсы валют у нас есть отдельной
    строкой в приложении, в теле новости им делать нечего.

    Признак виджета — короткие строки вида «код валюты — число». Настоящая
    таблица из статьи так не выглядит: там есть слова.
    """
    money = sum(1 for r in rows
                if re.match(r"^[A-Z]{3}\b", r)
                and r.split(" — ")[0].strip() in _CURRENCY_CODES)
    return money >= 2


PAGE_BODY_LIMIT = 1300   # полторы страницы читалки — столько человек
                         # проглядывает без утомительной прокрутки


def _trafilatura_body(raw_html: bytes) -> str:
    """Основной разбор статьи — библиотекой, а не своими правилами.

    Почему перешли (замер 23.08.2026 на тридцати живых страницах всех пяти
    пулов): библиотека даёт больше текста почти везде и нигде не даёт меньше.
    24.kg 1097 → 2329 знаков, Le Figaro 799 → 1553, Infobae 672 → 4885,
    Agência Brasil 1170 → 5416. Коротких текстов меньше — значит реже зовём
    платную дотяжку enrich_short_summaries и платное спасение _ai_rescue_body.

    Наш собственный обход абзацев остался запасным ходом: в нём накоплено
    то, чего библиотека не знает, — таблицы с ценами на топливо, перечни улиц
    в <li> после двоеточия, контейнер Kaktus со всей статьёй внутри одного
    элемента.

    Передаём именно байты, а не .text: кодировку определит парсер. На .text
    французские страницы приходили в мохибейке («Ã©» вместо «é»).
    """
    if trafilatura is None:
        return ""
    try:
        out = trafilatura.extract(
            raw_html,
            include_tables=True,      # цены, курсы и расписания живут в таблицах
            include_comments=False,   # ветки комментариев — не статья
            include_images=False,
            favor_precision=True,     # лучше недобрать, чем притащить меню
            deduplicate=True,
        ) or ""
    except Exception:
        return ""
    # Библиотека размечает абзацы и пункты списков переводами строк — их
    # сохраняем: на них держатся перечни улиц и таблицы цен. Схлопываем
    # только пустые строки и лишние пробелы внутри строк
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in out.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


def _fetch_page(url: str) -> bytes:
    """Только качает страницу. Ни строчки разбора.

    Эта функция и есть та часть, которую безопасно звать из многих потоков:
    внутри чистый ввод-вывод, никаких нативных парсеров.
    """
    try:
        r = requests.get(url, timeout=8, headers=BROWSER_HEADERS)
        return r.content if r.ok else b""
    except Exception:
        return b""


def _body_from_html(html: bytes, url: str) -> str:
    """Разбирает уже скачанную страницу. ЗВАТЬ ТОЛЬКО ПОСЛЕДОВАТЕЛЬНО.

    27.08.2026 прогон рухнул с «corrupted size vs. prev_size while
    consolidating» и core dump — это повреждение кучи в нативном коде, а не
    исключение Python. Виновник lxml, которым пользуется trafilatura: к
    вызовам из шестнадцати потоков разом он не готов.

    Снижение числа потоков уменьшало вероятность, но не убирало причину.
    Здесь причина убрана: разбор идёт в одном потоке. Платим временем —
    0.04 секунды на страницу, пятьсот страниц за двадцать секунд, — и это
    дёшево против прогона, который не выходит вовсе.
    """
    if not html:
        return ""
    try:
        soup = BeautifulSoup(html, "html.parser")
        if _page_says_ad(soup):
            AD_PAGES.add(url)
            return ""

        res = extract_article(
            html, url,
            extra_extractors=[("прежний разбор",
                               lambda _h, _u: _page_body_legacy(url) or "")])
        if not res.ok():
            if res.notes:
                print(f"  · Разбор не дался [{url[:48]}]: {'; '.join(res.notes[-2:])}")
            return ""

        body = strip_tail(trim_to_boundary(res.text, PAGE_BODY_LIMIT))
        if _looks_mangled(body):
            fixed = _ai_rescue_body(url, body, soup)
            if fixed:
                return fixed
        return body
    except Exception:
        return ""


def _page_body(url: str) -> str:
    """Скачать и разобрать одну страницу — для одиночных вызовов.

    В МНОГОПОТОЧНОМ месте так звать нельзя: разбор внутри не потокобезопасен.
    Там качайте потоками через _fetch_page, а разбирайте по очереди через
    _body_from_html — см. enrich_short_summaries.
    """
    return _body_from_html(_fetch_page(url), url)


def _page_body_legacy(url: str) -> str:
    """ПРЕЖНИЙ разбор. Оставлен нетронутым и работает последней ступенью.

    Здесь накоплено то, чего библиотеки не знают: таблицы с ценами на
    топливо, перечни улиц в <li> после двоеточия, контейнер Kaktus со всей
    статьёй внутри одного элемента, запасной og:description. На замере
    24.08.2026 он выручил одну страницу из сорока — редко, но незаменимо.
    """
    try:
        r = requests.get(url, timeout=8, headers=BROWSER_HEADERS)
        if not r.ok:
            return ""
        soup = BeautifulSoup(r.content, "html.parser")
        # Издание само пометило материал рекламой — дальше разбирать нечего
        if _page_says_ad(soup):
            AD_PAGES.add(url)
            return ""

        body = _trafilatura_body(r.content)
        # Библиотека честно достаёт основной текст страницы, но не знает, что
        # перед ней не статья, а заслон. Проверка обязательна именно здесь
        if _looks_blocked(body):
            return ""
        if len(body) >= 200:
            body = trim_to_boundary(body, PAGE_BODY_LIMIT)
            body = strip_tail(body)
            if _looks_mangled(body):
                fixed = _ai_rescue_body(url, body, soup)
                if fixed:
                    return fixed
            return body

        # Дальше — прежний собственный разбор: библиотека не справилась
        root = soup.find("article") or soup
        paras, seen = [], set()
        # Таблицы забираем ПЕРВЫМИ: в новостях про цены, курсы и расписания
        # вся суть именно в них. Раньше мы брали только абзацы, и читатель
        # получал «цены на ГСМ такие:» — без единой цифры
        for tbl in root.find_all("table")[:2]:
            rows = []
            for tr in tbl.find_all("tr")[:14]:
                cells = [clean_text(td.get_text(" ", strip=True))
                         for td in tr.find_all(["td", "th"])]
                cells = [c for c in cells if c]
                if len(cells) >= 2:
                    rows.append(" — ".join(cells[:4]))
            if len(rows) >= 2 and not _is_sidebar_table(rows):
                paras.append("\n".join(rows))
        # Берём и <li>: перечни улиц, домов и рейсов живут в списках, а не в
        # абзацах. Короткие строки по-прежнему отбрасываем как подписи и
        # крошки — КРОМЕ тех, что идут сразу после двоеточия. 22.08 читатель
        # открыл «движение ограничено на следующих улицах:» и не увидел ни
        # одной улицы: перечень состоял из строк короче шестидесяти знаков.
        expecting_list = False
        listed = 0
        container_text = ""
        # Слова навигации: у части сайтов статья свёрстана списками, и в тот
        # же список попадают «Главная», «Все новости», «Спецпроекты»
        _NAV = {"главная", "все новости", "спецпроекты", "контакты", "реклама",
                "полезное", "call-центр", "подписка", "архив", "поиск"}
        for p in root.find_all(["p", "li"]):
            t = clean_text(p.get_text(" ", strip=True))
            if not t:
                continue
            # <li> в сотни знаков — это контейнер вёрстки, а не пункт списка:
            # у Kaktus в таком лежит вся статья целиком, и она задвоила бы текст
            if p.name == "li" and len(t) > 600:
                # Запоминаем самый большой: у Kaktus в таком контейнере лежит
                # ВСЯ статья, и если обычных абзацев на странице нет, он
                # единственный источник текста. 22.08 из-за этого одиннадцать
                # заметок вышли в сотню знаков
                if len(t) > len(container_text):
                    container_text = t
                continue
            if t.lower().strip(" ·—-") in _NAV:
                continue
            if len(t) < 60:
                if expecting_list and listed < 15 and len(t) > 2:
                    paras.append(t)
                    listed += 1
                    continue
                continue
            expecting_list = t.rstrip().endswith(":")
            listed = 0
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
            expecting_list = t.rstrip().endswith(":")
            # Набираем до 1400, а не до 700. Потолок ленты — 1300 знаков, он
            # стоит ниже, при обрезке. Но сбор абзацев обрывался на 700, и до
            # потолка текст не доходил НИКОГДА: 20.08 читатель открыл заметку
            # о мошеннике в мечети и увидел половину, хотя на сайте она вся
            # короче 1260. Берём с запасом — лишнее срежет общий предел по
            # границе предложения.
            if sum(len(x) for x in paras) > 1400:
                break
        body = " ".join(paras).strip()
        # Абзацев не нашлось — берём отложенный контейнер
        if len(body) < 200 and len(container_text) > len(body):
            body = container_text.strip()

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

        body = trim_to_boundary(body, PAGE_BODY_LIMIT)
        body = strip_tail(body)

        # Последний рубеж: машина сама признаётся, что потеряла смысл
        if _looks_mangled(body):
            fixed = _ai_rescue_body(url, body, soup)
            if fixed:
                return fixed
        return body
    except Exception:
        return ""


# Пометка рекламы на странице издания. В России её требует закон (маркировка
# «erid»), в Кыргызстане издания обычно пишут «на правах рекламы». Если
# издание само признало материал рекламой, спорить не о чем
_AD_MARKERS = re.compile(
    r"на правах рекламы|рекламный материал|реклама\s*[.:•|]|"
    r"партнёрский материал|партнерский материал|спонсорский материал|"
    r"advertorial|sponsored content|paid post|\berid\s*[=:]",
    re.I)


# Адреса страниц, где издание само признало материал рекламой. Заполняется при
# дотяжке текста, читается контролем качества
AD_PAGES = set()


def _page_says_ad(soup) -> bool:
    """True, если издание само помечает материал как рекламу."""
    try:
        head = clean_text(soup.get_text(" ", strip=True))[:4000]
        return bool(_AD_MARKERS.search(head))
    except Exception:
        return False


# Страна издания по адресу. Нужна, чтобы полку считать относительно ЧИТАТЕЛЯ,
# а не домашней страны пула: для казаха новость из Казахстана местная, хотя
# домашняя страна русского пула — Кыргызстан.
_COUNTRY_BY_DOMAIN = {
    ".kg": "KG", ".kz": "KZ", ".uz": "UZ", ".tj": "TJ", ".tm": "TM",
    ".ru": "RU", ".ua": "UA", ".by": "BY",
    ".mx": "MX", ".ar": "AR", ".cl": "CL", ".pe": "PE", ".co": "CO",
    ".ve": "VE", ".ec": "EC", ".gt": "GT", ".cr": "CR", ".do": "DO",
    ".br": "BR", ".pt": "PT", ".ao": "AO", ".mz": "MZ",
    ".es": "ES", ".ie": "IE", ".au": "AU", ".nz": "NZ", ".in": "IN",
    ".ng": "NG", ".za": "ZA", ".jm": "JM", ".ca": "CA", ".sg": "SG",
}
_COUNTRY_BY_SOURCE = {
    "24.kg": "KG", "Kaktus.media": "KG", "Kabar.kg": "KG", "AKIpress": "KG",
    "Knews.kg": "KG", "Sputnik KG": "KG", "Turmush": "KG", "Economist.kg": "KG",
    "Vlast.kz": "KZ", "Egemen Qazaqstan": "KZ",
    "Kun.uz": "UZ", "Gazeta.uz": "UZ", "Podrobno.uz": "UZ",
    "Asia-Plus": "TJ",
}


def country_of(item) -> str:
    """Страна издания: по названию, если знаем, иначе по домену."""
    src = item.get("source", "")
    if src in _COUNTRY_BY_SOURCE:
        return _COUNTRY_BY_SOURCE[src]
    url = (item.get("url") or "").lower()
    host = url.split("/")[2] if "://" in url else url
    for suffix, code in _COUNTRY_BY_DOMAIN.items():
        if host.endswith(suffix) or suffix + "/" in url:
            return code
    return ""


def _is_home_source(item, lang) -> bool:
    """Издание домашней страны пула — только оно может дать МЕСТНУЮ новость.

    Раньше сюда входили и издания языкового пространства, и новость про
    алматинские парковки выходила в русском пуле под киргизским флагом.
    Казахстанская новость важна и интересна, но она не местная: её полка —
    «страны языка».
    """
    url = (item.get("url") or "").lower()
    return any(dom in url for dom in LOCAL_DOMAINS.get(lang, []))


def _demote_foreign_local(item, lang):
    """Ставит новость на правильную полку, если «местная» ей не по праву."""
    if item.get("scope") != "local" or item.get("bridge"):
        return
    if _is_home_source(item, lang):
        return
    url = (item.get("url") or "").lower()
    in_pool = any(dom in url for dom in POOL_DOMAINS.get(lang, []))
    item["scope"] = "pool" if in_pool else "world"


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
        out = ask_gemini(prompt, charter=False).strip()
        if out.startswith("НЕТ_ТЕКСТА") or len(out) < 120:
            out = ""
        PAGE_BODY_CACHE[key] = {"text": out, "ts": int(datetime.now().timestamp() * 1000)}
        return out
    except Exception as e:
        print(f"  ⚠️ ИИ не смог разобрать страницу: {str(e)[:70]}")
        return ""


def _share_budget(targets, budget, what=""):
    """Делит бюджет обхода страниц между пулами поровну, по кругу.

    Списки собираются пул за пулом, поэтому простая отсечка первых `budget`
    штук обделяет тех, кто собран позже, — целиком и молча.
    """
    if len(targets) <= budget:
        return targets
    buckets = {}
    for it in targets:
        buckets.setdefault(it.get("source_lang") or "??", []).append(it)
    order, picked = list(buckets), []
    while len(picked) < budget and any(buckets[k] for k in order):
        for k in order:
            if not buckets[k]:
                continue
            picked.append(buckets[k].pop(0))
            if len(picked) >= budget:
                break
    share = Counter(t.get("source_lang") or "??" for t in picked)
    print(f"  📄 Бюджет {what} {budget} на {len(targets)} штук, "
          f"по пулам: {dict(sorted(share.items()))}")
    return picked


def enrich_short_summaries(items, min_len=400, budget=500, workers=16):
    """Дотягивает короткие описания текстом со страницы статьи.

    Мировые ленты дают одно предложение-затравку, и на экране это выглядит как
    «две строки и кнопка». Идёт ДО перевода, чтобы читатель получил резюме на
    своём языке.

    Бюджет 500, а не 260: коротких в прогоне бывает под пятьсот, и при 260
    половина оставалась без текста. Раздача по кругу сделала недостачу
    справедливой, но не отменила её — английский пул, прежде забиравший
    очередь первым, просел с 745 знаков до 537. Дотяжка денег не стоит: это
    обычные запросы страниц, а минуты Actions у нас бесплатные. Платит она
    только временем прогона.

    Шестнадцать потоков — и это безопасно, потому что они ТОЛЬКО КАЧАЮТ.
    27.08.2026 прогон рухнул с повреждением кучи: тогда в тех же потоках шёл
    и разбор, а lxml внутри trafilatura к параллельным вызовам не готов.
    Сперва снизили до восьми — сбой стал реже, но причина осталась. Теперь
    разбор вынесен в один поток, и причины нет вовсе.

    Потоки, а не по очереди: раньше бюджет держали крошечным (25),
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

    # Бюджет делим между пулами ПО КРУГУ, а не отсекаем первых по списку.
    #
    # Было `targets[:budget]` — простая отсечка в порядке сбора. Кто собран
    # позже, тому не доставалось ничего: 23.08.2026 французские новости вышли
    # в среднем по 192 знака против 558 у переведённых, хотя те же источники
    # на отдельном прогоне давали за 900. Бюджет к тому дню уже поднимали со
    # 150 до 260 ровно по этой причине — и снова не хватило, потому что
    # лечили число, а не порядок.
    #
    # По кругу справедливо при любом числе новостей: недостаёт не пулу
    # целиком, а хвосту каждого пула поровну. И шестой пул ничего молча
    # не сломает.
    targets = _share_budget(targets, budget, "дотяжки")
    if not targets:
        return

    # СЕТЬ ПОТОКАМИ, РАЗБОР ПО ОЧЕРЕДИ.
    #
    # Раньше здесь качалось и разбиралось разом в шестнадцать потоков, и
    # 27.08.2026 прогон рухнул с повреждением кучи: lxml внутри trafilatura
    # к параллельным вызовам не готов. Снижение числа потоков делало сбой
    # реже, но не убирало причину.
    #
    # Теперь потоки заняты только скачиванием — это чистый ввод-вывод, он
    # безопасен, и потоков можно держать даже больше прежнего. Разбор идёт
    # в одном потоке следом. Он быстрый: 0.04 секунды на страницу, пятьсот
    # страниц за двадцать секунд. Медленная часть — сеть, и она осталась
    # параллельной.
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pages = list(pool.map(lambda it: _fetch_page(it["url"]), targets))

    bodies = [_body_from_html(html, it["url"]) for it, html in zip(targets, pages)]

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


def drop_bilingual_twins(items):
    """Одна новость, выпущенная изданием на двух языках.

    Kabar и Sputnik KG публикуют материал по-русски и по-кыргызски. Для нас
    это два разных заголовка, и обычная проверка на дубли их не видит —
    сравнивать нечего, буквы разные. Зато совпадают ЛАТИНСКИЕ слова и числа:
    «The Rolls», «The Beatles», «26», «1». По ним и опознаём.

    Оставляем ту, где ЕСТЬ фотография: у кыргызской версии про музыкантов
    снимка не было, и читатель видел эмодзи вместо The Beatles на переходе.
    При равенстве оставляем на языке потока.
    """
    import collections
    def signature(title):
        lat = set(re.findall(r"[A-Za-z]{3,}", title))
        nums = set(re.findall(r"\d{2,4}", title))
        return lat | nums

    groups = collections.defaultdict(list)
    for it in items:
        sig = signature(it.get("title", ""))
        if len(sig) >= 2:
            groups[(it.get("source", ""), frozenset(sig))].append(it)

    dropped = 0
    for (src, sig), group in groups.items():
        if len(group) < 2:
            continue
        # разные события одного издания могут делить слова — проверяем время
        group.sort(key=lambda x: x.get("publishedAt", 0))
        if group[-1].get("publishedAt", 0) - group[0].get("publishedAt", 0) > 12 * 3600 * 1000:
            continue
        def rank(it):
            has_photo = (it.get("imageUrl") or "").startswith("http")
            cyr = len(re.findall(r"[а-яё]", it.get("title", ""), re.I))
            return (has_photo, cyr)
        best = max(group, key=rank)
        for it in group:
            if it is not best:
                it["_twin_drop"] = True
                dropped += 1
    if dropped:
        print(f"  👯 Двойники на двух языках: снято {dropped}")
    return [it for it in items if not it.get("_twin_drop")]


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


# Признак уменьшенной копии в адресе. Держим снаружи: нужен и при отборе
# кандидатов, и внутри, когда решаем, годится ли найденное на странице
_THUMBNAIL_URL = re.compile(r"og_thumbnail|thumb|/small[-_/]|_150x|_300x|/preview/", re.I)


def upscale_known_cdn(url: str) -> str:
    """Просит у издательского хранилища ту же картинку покрупнее.

    Размер бывает зашит прямо в адрес, и тогда мелкую копию можно поменять на
    большую, ничего не выдумывая. BBC отдаёт в ленте 240×135 — на весь экран
    это мыло; тот же файл по адресу с 1024 приходит 1024×576. Проверено на
    живых снимках: доступны и 1536, но 1024 хватает любому экрану при
    разумном весе.
    """
    if not url:
        return url
    # BBC: /ace/standard/240/… и /news/240/…
    url = re.sub(r"(ichef\.bbci\.co\.uk/(?:ace/standard|ace/ws|news)/)\d{2,4}/",
                 r"\g<1>1024/", url)
    return url


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
        # Берём и тех, у кого картинка ЕСТЬ, но это миниатюра: на весь экран
        # такая разваливается в мыло. El Tiempo и El Economista кладут
        # уменьшенную копию прямо в ленту («og_thumbnail» в адресе), и дотяжка
        # мимо них проходила — она искала только пустые карточки
        img_now = item.get("imageUrl") or ""
        if img_now and not (_THUMBNAIL_URL.search(img_now) or item.get("imageLowRes")):
            continue
        url = item.get("url", "")
        if not url.startswith("http") or "t.me" in url or "telegram." in url:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)
        targets.append(item)
    targets = _share_budget(targets, budget, "картинок")
    if not targets:
        return

    # Карточка для соцсетей — не фотография. РИА (и не только) кладёт в
    # og:image картинку с ВПЕЧАТАННЫМ заголовком: у ria.ru это
    # /images/sharing/article/…. В ленте читатель видел одну и ту же фразу
    # дважды — крупным текстом сверху и ещё раз на снимке. Настоящее фото при
    # этом лежит на той же странице
    # Карточка для соцсетей — картинка с ВПЕЧАТАННЫМ заголовком. У ria.ru это
    # /images/sharing/article/…, у gazeta.uz — имя файла, кончающееся на «_og»:
    # рядом лежит тот же снимок с «_b», уже без текста. Читатель видел русский
    # заголовок над узбекским, напечатанным прямо на фотографии (21.08.2026).
    _SHARING_CARD = re.compile(
        r"/images/sharing/|/sharing/|/social[-_/]|og[-_]image|share[-_]card"
        r"|_og\.(jpe?g|png|webp)|/og/|[?&]og=|imagemeta/", re.I)
    # Миниатюра вместо снимка: часть изданий отдаёт в og:image уменьшенную
    # копию (у El Tiempo прямо «og_thumbnail» в адресе, у CBS «/thumbnail»).
    # На весь экран она разваливается в мыло, поэтому ищем на странице
    # настоящее фото — тем же способом, что и для карточек соцсетей
    _THUMB_IMAGE = re.compile(r"thumb|/small[-_/]|_150x|_300x|/preview/", re.I)

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
            # Своей картинки нет, но в статье есть ролик — берём его обложку.
            # У новости про ДТП на странице стоял ролик с YouTube, а карточка
            # у нас вышла с эмодзи вместо стопкадра
            if not img:
                import re as _re
                vid = None
                for tag in soup.find_all(["iframe", "a", "link"]):
                    href = tag.get("src") or tag.get("href") or ""
                    m = _re.search(r"(?:youtube\.com/(?:embed/|watch\?v=)|youtu\.be/)"
                                   r"([A-Za-z0-9_-]{11})", href)
                    if m:
                        vid = m.group(1)
                        break
                if vid:
                    img = f"https://img.youtube.com/vi/{vid}/maxresdefault.jpg"
            if img and (_SHARING_CARD.search(img) or _THUMB_IMAGE.search(img)):
                # заголовок на картинке или миниатюра — ищем живое фото
                img = _page_photo(soup) or img
            return img if img and img.startswith("http") else None
        except Exception:
            return None

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(fetch, targets))

    by_url = {}
    for item, img in zip(targets, results):
        if img and not (item.get("imageUrl") and _THUMBNAIL_URL.search(img)):
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
            low_res = False
            enc = item_el.find("enclosure")
            if enc is not None and "image" in (enc.get("type") or ""):
                image = upscale_known_cdn(enc.get("url"))
            if not image:
                # ElementTree НЕ находит <media:content> по имени с приставкой:
                # для него тег зовётся «{http://search.yahoo.com/mrss/}content».
                # Поэтому поиск по "media:content" не срабатывал НИКОГДА, и
                # издания, дающие фото только так, приходили к нам без картинок
                # (Axios — три новости подряд с пустой карточкой). Ищем по
                # окончанию имени: работает при любом объявлении пространства
                # Берём САМУЮ БОЛЬШУЮ, а не первую попавшуюся. Ленты кладут
                # рядом несколько размеров, и <media:thumbnail> (обычно 320
                # пикселей) часто идёт первым — на весь экран такая картинка
                # разваливается в мыло. Прежний код так и делал, и качество
                # просело сразу у многих новостей
                best, best_w = None, -1
                for el in item_el.iter():
                    name = el.tag.rsplit("}", 1)[-1].lower()
                    if name not in ("content", "thumbnail"):
                        continue
                    url_img = el.get("url", "")
                    medium = (el.get("medium") or el.get("type") or "").lower()
                    is_img = ("image" in medium
                              or any(ext in url_img.lower()
                                     for ext in (".jpg", ".jpeg", ".png", ".webp")))
                    if not (url_img.startswith("http") and is_img):
                        continue
                    try:
                        width = int(el.get("width") or 0)
                    except ValueError:
                        width = 0
                    # Ширина указана не всегда; когда её нет, полноразмерная
                    # картинка всё равно должна выигрывать у миниатюры
                    score = width or (400 if name == "content" else 100)
                    if score > best_w:
                        best, best_w = url_img, score
                if best:
                    image = upscale_known_cdn(best)
                    # Мелкая копия из ленты — не повод довольствоваться ею.
                    # Пока мы вовсе не читали media-теги, картинки брались со
                    # страницы и были крупными; научившись их читать, мы стали
                    # брать у BBC миниатюру 240 точек вместо снимка 1024.
                    # Помечаем такие, чтобы дотяжка заменила их со страницы —
                    # правило общее, не про одну лишь BBC
                    if best_w and best_w < 600 and "1024" not in image:
                        low_res = True

            # Родной язык издания важнее языка пула: по нему приложение решит,
            # кому эту новость показывать
            item_lang = source.get("native") or source.get("lang") or lang
            # Исключение из «источник надёжнее детектора»: кириллица против
            # латиницы не путается, в отличие от испанского/португальского/
            # английского между собой. Vlast.kz помечен как «ru», но иногда
            # публикует материалы на английском — статичная метка это скрывала,
            # и needs_translation() считала статью уже переведённой
            # Явную пометку "native" не трогаем: узбекский пишется латиницей,
            # и проверка «латиница в кириллическом языке — ошибка» сбросила бы
            # ему язык на русский, а с ним и весь смысл затеи
            if not source.get("native") and item_lang in (
                    "ru", "ky", "uk", "kk", "be", "bg", "sr", "mk", "uz", "tg"):
                cyr = len(re.findall(r"[а-яё]", title + summary, re.I))
                lat = len(re.findall(r"[a-z]{3,}", title + summary, re.I))
                if cyr < 3 and lat >= 5:
                    item_lang = lang if lang not in ("unknown", "other") else "en"

            items.append({
                "title": title, "url": link, "summary": summary,
                "imageUrl": image, "imageLowRes": low_res, "source": source["source"],
                # Страна издания. Пока лежит про запас: приложение начнёт по ней
                # считать местные новости с 29-й версии, и тогда португалец
                # перестанет видеть бразильские заметки под заголовком
                # «Местные», а аргентинец — мексиканские
                "country": source_country({"source": source["source"], "url": link}),
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
TOKENS = {"in": 0, "out": 0, "calls": 0, "fallback_in": 0, "fallback_out": 0}

# Собственный потолок расхода, ниже остатка на счёте. Дважды деньги кончались
# внезапно: 15.08 — сами не заметили, 18.08 — чужой человек тратил по украденному
# ключу. Оба раза узнавали постфактум, со счёта. Теперь скрипт считает сам и,
# упершись в потолок, перестаёт звать ИИ до конца месяца: лента продолжает
# выходить на отборе по признакам (проверено — размеры и фото в порядке).
# Меняется переменной AI_MONTHLY_BUDGET в настройках Actions.
AI_BUDGET = float(os.environ.get("AI_MONTHLY_BUDGET", "8"))
AI_SPENT_MONTH = 0.0      # потрачено с начала месяца, читается из базы
AI_STOPPED = False        # потолок достигнут — ИИ не зовём вовсе


def _spend_month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def load_ai_spend():
    """Поднимает из базы, сколько ИИ съел с начала месяца."""
    global AI_SPENT_MONTH, AI_STOPPED
    try:
        AI_SPENT_MONTH = float(
            db.reference(f"/ai_spend/{_spend_month_key()}/usd").get() or 0.0)
    except Exception as e:
        print(f"  ⚠️ Счётчик расхода не прочитан ({e}) — считаем с нуля")
        AI_SPENT_MONTH = 0.0
    AI_STOPPED = AI_SPENT_MONTH >= AI_BUDGET
    share = AI_SPENT_MONTH / AI_BUDGET * 100 if AI_BUDGET else 0
    print(f"💳 Расход ИИ за {_spend_month_key()}: ${AI_SPENT_MONTH:.2f} "
          f"из ${AI_BUDGET:.2f} ({share:.0f}%)")
    if AI_STOPPED:
        print("::warning::Потолок расхода ИИ достигнут — лента выходит без ИИ. "
              "Пополните счёт и поднимите AI_MONTHLY_BUDGET.")
    elif share >= 75:
        print(f"::warning::Израсходовано {share:.0f}% месячного бюджета ИИ")


def save_ai_spend(run_cost: float):
    """Прибавляет расход прогона к месячной копилке."""
    try:
        ref = db.reference(f"/ai_spend/{_spend_month_key()}")
        ref.update({
            "usd": round(AI_SPENT_MONTH + run_cost, 6),
            "calls": int((db.reference(
                f"/ai_spend/{_spend_month_key()}/calls").get() or 0)
                + TOKENS["calls"]),
            "updatedAt": int(time.time() * 1000),
        })
    except Exception as e:
        print(f"  ⚠️ Счётчик расхода не сохранён: {e}")


def _editorial_charter() -> str:
    """Постоянная память ИИ о нашем издании.

    У модели нет памяти между запросами: каждый начинается с чистого листа, а
    то, что в чате выглядит памятью, — пересылка всей переписки заново. Значит
    помнить должны мы. Этот текст (EDITORIAL.md) уходит СИСТЕМНОЙ ИНСТРУКЦИЕЙ
    при каждом обращении: кто мы, кто нас читает, что считаем новостью, чего
    добиваемся и на каких ошибках уже обожглись.

    Правится вручную в EDITORIAL.md — это редакционная политика, а не код.
    """
    global _CHARTER
    if _CHARTER is None:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "EDITORIAL.md"), encoding="utf-8") as f:
                _CHARTER = f.read()
            print(f"  📜 Редакционная политика загружена: {len(_CHARTER)} знаков")
        except Exception as e:
            print(f"  ⚠️ EDITORIAL.md не прочитан ({e}) — работаем без неё")
            _CHARTER = ""
    return _CHARTER


_CHARTER = None


# Запасной поставщик ИИ. 20.08 потолок расходов заблокировал Gemini, и лента
# полдня выходила вообще без ИИ — без сверки заголовков, без перевода, без
# обзоров. Один поставщик означает, что его сбой становится нашим.
#
# Адрес и модель берутся из настроек:
# FALLBACK_BASE_URL, FALLBACK_API_KEY, FALLBACK_MODEL. Нет ключа — запасного пути просто нет,
# и всё работает как раньше.
# Имена AI_FALLBACK_*. Прежние QWEN_* понимаются тоже: секрет с этим именем
# уже создан, и ломать его переименованием ради красоты не стоит. Поставщик за
# год может смениться трижды, поэтому переменная названа по РОЛИ — запасной
# путь, — а не по имени модели, которая в ней сегодня.
# Запасной поставщик бесплатный, а бесплатное считает токены строже: у Groq
# 8 000 токенов в минуту, и наша обычная порция в 80 новостей с конституцией
# (9 тыс. токенов) не влезает в ОДИН запрос. Поэтому в запасном режиме порции
# мельче, а конституция идёт коротким изложением.
FALLBACK_MODE = False               # включается, когда Gemini недоступен
FALLBACK_CHUNK = 20

FALLBACK_API_KEY = (os.environ.get("AI_FALLBACK_KEY")
                    or os.environ.get("GROQ_API_KEY")
                    or os.environ.get("QWEN_API_KEY", ""))
FALLBACK_BASE_URL = (os.environ.get("AI_FALLBACK_URL")
                     or os.environ.get("QWEN_BASE_URL")
                     or "https://api.groq.com/openai/v1")
FALLBACK_MODEL = (os.environ.get("AI_FALLBACK_MODEL")
                  or os.environ.get("QWEN_MODEL")
                  or "openai/gpt-oss-120b")


_CULL_CHARTER = None


def _editorial_cull_charter() -> str:
    """Устав ПЕРВОГО этапа — только правила отсева мусора (EDITORIAL_CULL.md).

    Устав разделён надвое 23.08.2026. Полный весит 3 554 токена, и большая
    его часть — полки, приоритеты, калибровка срочности — первому этапу не
    нужна вовсе: там решается один вопрос, новость это или мусор. Урезанный
    весит 1 515 токенов, то есть вдвое с лишним дешевле.

    Граница между файлами проведена по смыслу: «что не новость» здесь, «как
    размечать» — в EDITORIAL.md. Пересекаться они не должны, иначе правило
    поправят в одном файле и забудут в другом.
    """
    global _CULL_CHARTER
    if _CULL_CHARTER is None:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "EDITORIAL_CULL.md"), encoding="utf-8") as f:
                _CULL_CHARTER = f.read()
            print(f"  📜 Устав отсева загружен: {len(_CULL_CHARTER)} знаков")
        except Exception as e:
            print(f"  ⚠️ EDITORIAL_CULL.md не прочитан ({e}), беру полный устав")
            _CULL_CHARTER = _editorial_charter()
    return _CULL_CHARTER


def _fallback_call(req, tries: int = 3):
    """Запрос с ожиданием при минутном пределе.

    Бесплатный уровень считает токены в минуту, и на нашей череде запросов он
    неизбежно упирается. Правильный ответ на «слишком часто» — подождать,
    а не отказаться: лента собирается раз в два часа, минута роли не играет.
    """
    for attempt in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == tries - 1:
                raise
            body = ""
            try:
                body = e.read().decode("utf-8", "ignore")
            except Exception:
                pass
            m = re.search(r"try again in ([0-9.]+)s", body)
            wait = min(float(m.group(1)) + 1, 45) if m else 20
            print(f"  ⏳ Запасной поставщик просит подождать {wait:.0f} с")
            time.sleep(wait)
    raise RuntimeError("запасной поставщик недоступен")


def ask_fallback(prompt, charter_text: str = "") -> str:
    """Запрос к запасному поставщику. Тот же ответ, что и от Gemini, — строкой."""
    if not FALLBACK_API_KEY:
        raise RuntimeError("FALLBACK_API_KEY не задан")
    messages = []
    if charter_text:
        # Бесплатный уровень считает каждый токен, а конституция весит четыре
        # тысячи. Берём её начало — там определения полок и правило инфоповода,
        # то есть самое нужное для суждения
        messages.append({"role": "system", "content": charter_text[:2500]})
    # Картинки запасной поставщик тоже понимает, но зовём его только на
    # текст: на
    # снимках мы проверяем деликатность, и менять там судью без замера нельзя
    text = prompt if isinstance(prompt, str) else next(
        (p for p in prompt if isinstance(p, str)), "")
    messages.append({"role": "user", "content": text})
    body = json.dumps({"model": FALLBACK_MODEL, "messages": messages,
                       "temperature": 0.2}).encode()
    req = urllib.request.Request(
        f"{FALLBACK_BASE_URL.rstrip('/')}/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {FALLBACK_API_KEY}",
                 # Cloudflare у Groq режет запросы по подписи клиента:
                 # стандартная библиотека Python представляется
                 # «Python-urllib», и в ответ приходит 403 с кодом 1010.
                 # Представляемся обычным клиентом
                 "User-Agent": "Ticker247/1.0 (+https://mirlanmmr.github.io/ticker247/)",
                 "Accept": "application/json"})
    try:
        data = _fallback_call(req)
    except urllib.error.HTTPError as e:
        # Тело ответа объясняет отказ («model not found», «terms not
        # accepted», «rate limit»), а без него остаётся только гадать —
        # 22.08 полчаса ушло на «403 Forbidden» без единой подробности
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:200].replace("\n", " ")
        except Exception:
            pass
        if e.code == 400 and "not found" in detail.lower():
            # Спрашиваем у самого сервера, какие модели у него есть, — это
            # быстрее и честнее, чем гадать по документации: 22.08 «grok-4-fast»
            # и «grok-4.1-fast» оказались устаревшими именами
            try:
                lreq = urllib.request.Request(
                    f"{FALLBACK_BASE_URL.rstrip('/')}/models",
                    headers={"Authorization": f"Bearer {FALLBACK_API_KEY}",
                             "User-Agent": "Ticker247/1.0 (+https://mirlanmmr.github.io/ticker247/)",
                             "Accept": "application/json",
                             "Content-Type": "application/json"})
                with urllib.request.urlopen(lreq, timeout=30) as lr:
                    names = [m.get("id") for m in json.load(lr).get("data", [])]
                detail += " | доступны: " + ", ".join(filter(None, names))[:300]
            except Exception as le:
                detail += f" | список моделей не получен: {str(le)[:60]}"
        if e.code == 401:
            # Ключ не показываем, но длина и начало — не секрет и сразу
            # объясняют, целиком ли он скопирован
            k = FALLBACK_API_KEY
            detail += f" | ключ: {len(k)} знаков, начинается с «{k[:4]}»"
            if k != k.strip():
                detail += ", ПО КРАЯМ ПРОБЕЛЫ"
        raise RuntimeError(f"запасной поставщик {e.code}: {detail}") from None
    usage = data.get("usage") or {}
    TOKENS["fallback_in"] += usage.get("prompt_tokens", 0) or 0
    TOKENS["fallback_out"] += usage.get("completion_tokens", 0) or 0
    TOKENS["calls"] += 1
    return (data["choices"][0]["message"]["content"] or "").strip()


def ask_gemini(prompt, charter=True) -> str:
    """Один запрос к ИИ с подсчётом токенов и запасной моделью.

    Принимает строку или список частей — во втором случае среди них может быть
    картинка ({"mime_type": ..., "data": ...}): так мы спрашиваем модель о самом
    снимке, а не о тексте вокруг него.
    """
    global _MODEL_IN_USE
    if AI_STOPPED:
        if FALLBACK_API_KEY:
            global FALLBACK_MODE
            FALLBACK_MODE = True
            return ask_fallback(prompt, _editorial_charter() if charter else "")
        raise RuntimeError(
            f"потолок расхода ИИ ${AI_BUDGET:.2f} за {_spend_month_key()} достигнут")
    # Конституция (14 КБ) уходит НЕ с каждым запросом. 20.08 счёт показал
    # 204 тыс. входящих токенов за прогон при 8 тыс. исходящих: платили почти
    # целиком за то, что отправляем, и 80% этого — редакционная политика,
    # приложенная к сорока запросам подряд. Переводчику, разборщику страницы и
    # взгляду на фотографию она не нужна: там нет решения «наша ли это
    # новость». Она нужна там, где ИИ судит — отбор, роли в обзоре, полки.
    # charter: True — полный устав, False — без устава, строка — свой устав
    # (первому этапу отсева нужен урезанный, EDITORIAL_CULL.md)
    if charter is True:
        charter = _editorial_charter()
    elif not isinstance(charter, str):
        charter = ""
    try:
        model = genai.GenerativeModel(
            _MODEL_IN_USE,
            system_instruction=charter or None,
        )
        resp = model.generate_content(prompt)
    except Exception as e:
        if "not found" in str(e).lower() or "404" in str(e):
            print(f"  ⚠️ Модель {_MODEL_IN_USE} недоступна, беру {GEMINI_MODEL_FALLBACK}")
            _MODEL_IN_USE = GEMINI_MODEL_FALLBACK
            model = genai.GenerativeModel(
                _MODEL_IN_USE,
                system_instruction=charter or None,
            )
            resp = model.generate_content(prompt)
        else:
            # Gemini недоступен — пробуем запасного поставщика. Тишина хуже
            # чужой модели: без ИИ лента теряет сверку заголовков и перевод
            if FALLBACK_API_KEY:
                globals()["FALLBACK_MODE"] = True
                print(f"  ↪️ Gemini не ответил ({str(e)[:50]}), беру запасного: {FALLBACK_MODEL}")
                return ask_fallback(prompt, charter)
            raise
    u = getattr(resp, "usage_metadata", None)
    if u:
        TOKENS["in"] += getattr(u, "prompt_token_count", 0) or 0
        TOKENS["out"] += getattr(u, "candidates_token_count", 0) or 0
        # Сколько из входящих Gemini взял из своего кэша. Неизменная часть
        # запроса — устав и текст промпта — весит 8000 токенов и уходит по
        # два десятка раз за прогон; если кэш срабатывает, она стоит вчетверо
        # дешевле. Без этого счётчика мы не знаем, работает ли он вообще
        TOKENS["cached"] = TOKENS.get("cached", 0) + (
            getattr(u, "cached_content_token_count", 0) or 0)
    TOKENS["calls"] += 1
    return resp.text.strip()


_MODEL_IN_USE = GEMINI_MODEL


# ─── Явный кэш неизменной части запроса ────────────────────────────────────
#
# Замер 23.08.2026: неизменная часть запроса отбора — устав (3 554 токена) и
# текст самого промпта (4 454) — весит 8 008 токенов и уходит по два десятка
# раз за прогон. Это 79% всех входящих токенов: одна и та же инструкция,
# отправленная девятнадцать раз.
#
# Неявный кэш Gemini у нас не срабатывает вовсе — счётчик показал ровно ноль
# попаданий. Google включает его для 2.5 Flash и старше, flash-lite в списке
# поддерживаемых не значится. Явный кэш для flash-lite доступен и стоит в
# десять раз дешевле обычного входа: $0.01 против $0.10 за миллион.
#
# Кэш заводится СВОЙ НА КАЖДЫЙ ПУЛ: в тексте промпта пул назван по имени
# («редактор пула RU», «регион», «домашняя страна»), поэтому общего для всех
# пулов текста сейчас нет. Сделать его общим можно, вынеся эти подстановки в
# короткую шапку рядом со списком новостей, — но это правка самого промпта, а
# менять разом и кэш, и текст нельзя: потом не поймёшь, из-за чего изменились
# решения модели.
GEMINI_CACHES = {}              # ключ -> CachedContent
GEMINI_CACHE_TTL = 900          # прогон длится 4 минуты, берём с запасом
# Выключатель ПОКЛЮЧЕВОЙ, а не общий. Кэшей теперь два вида: по одному на пул
# для второго этапа и один общий для первого. Общий выключатель означал бы,
# что сбой одного гасит другой — а причины у них разные (у первого этапа свой
# устав и свой размер блока)
GEMINI_CACHE_OFF = set()


def _gemini_cache_for(key: str, preamble: str, charter_text: str = None):
    """Кэш неизменной части. None — работаем как раньше.

    Кэш — ускоритель, а не опора: любая неудача здесь молча возвращает нас на
    прежний путь. Лента дороже экономии.
    """
    if key in GEMINI_CACHE_OFF or FALLBACK_MODE or not GEMINI_API_KEY:
        return None
    if key in GEMINI_CACHES:
        return GEMINI_CACHES[key]
    try:
        from google.generativeai import caching
        cc = caching.CachedContent.create(
            model=_MODEL_IN_USE,
            display_name=f"ticker247-{key}",
            system_instruction=charter_text or _editorial_charter(),
            contents=[preamble],
            ttl=timedelta(seconds=GEMINI_CACHE_TTL),
        )
        GEMINI_CACHES[key] = cc
        size = getattr(getattr(cc, "usage_metadata", None), "total_token_count", 0)
        print(f"  ♻️ Кэш заведён [{key}]: {size:,} токенов")
        return cc
    except Exception as e:
        # Причин может быть три: псевдоним модели не годится для кэша,
        # блок меньше минимального размера, метод недоступен в этой версии
        # SDK. Все три лечатся по-разному, поэтому текст ошибки печатаем
        # целиком — иначе следующий раз будем гадать так же, как сегодня
        GEMINI_CACHE_OFF.add(key)
        print(f"  ⚠️ Кэш [{key}] недоступен, работаем как раньше: {str(e)[:300]}")
        return None


def ask_gemini_cached(key: str, preamble: str, tail: str, charter=True) -> str:
    """Запрос, у которого неизменная часть лежит в кэше, а меняется только хвост.

    Не вышло — склеиваем обратно и идём обычным путём. Снаружи разницы нет.
    """
    charter_text = (_editorial_charter() if charter is True
                    else charter if isinstance(charter, str) else None)
    cc = _gemini_cache_for(key, preamble, charter_text)
    if cc is None:
        return ask_gemini(preamble + tail, charter=charter)
    try:
        model = genai.GenerativeModel.from_cached_content(cached_content=cc)
        resp = model.generate_content(tail)
    except Exception as e:
        GEMINI_CACHE_OFF.add(key)
        print(f"  ⚠️ Кэш [{key}] не подключился, работаем как раньше: {str(e)[:200]}")
        return ask_gemini(preamble + tail, charter=charter)
    u = getattr(resp, "usage_metadata", None)
    if u:
        TOKENS["in"] += getattr(u, "prompt_token_count", 0) or 0
        TOKENS["out"] += getattr(u, "candidates_token_count", 0) or 0
        TOKENS["cached"] = TOKENS.get("cached", 0) + (
            getattr(u, "cached_content_token_count", 0) or 0)
    TOKENS["calls"] += 1
    return resp.text.strip()


def drop_gemini_caches():
    """Снимает кэши после прогона: хранение оплачивается по времени."""
    for pool, cc in list(GEMINI_CACHES.items()):
        try:
            cc.delete()
        except Exception:
            pass          # не удалилось — истечёт само через GEMINI_CACHE_TTL
        GEMINI_CACHES.pop(pool, None)



# Происшествия: только у них имеет смысл смотреть на снимок. Проверять КАЖДУЮ
# фотографию было бы и дорого, и незачем — на бирже и на футболе тел не бывает.
_INCIDENT = re.compile(
    "дтп|наезд|авари|сбил|столкновени|погиб|пострадав|ранен|труп|тело |"
    "убийств|застрелил|стрельб|поножовщин|взрыв|пожар|обрушени|утонул|нападени|"
    "теракт|расстрел|загорел|возгорани|"
    "crash|collision|accident|shooting|stabbing|explosion|killed|injured|"
    "victim|fatal|attack|wreck|"
    "accidente|choque|atropell|tiroteo|apuñal|explosi|muert|herid|víctima|"
    "acidente|colisão|tiroteio|esfaquea|explos|mort|ferid|vítima",
    re.I)


def _looks_incident(item) -> bool:
    head = f"{item.get('title','')} {str(item.get('summary',''))[:200]}"
    return bool(_INCIDENT.search(head))


def _photo_is_graphic(url: str):
    """Есть ли на снимке пострадавший человек. None — спросить не удалось.

    Правило размытия судит о СНИМКЕ, а не о сюжете (см. SensitiveContent.kt в
    приложении). До сих пор оно смотрело на слова: «окровавлен», «тела
    погибших». Новость 19.08 «после ДТП водителя сначала признали пьяным, а
    затем трезвым» таких слов не содержала, а на фотографии человек лежал под
    машиной. Слова о снимке не знают ничего — поэтому показываем снимок.
    """
    try:
        r = requests.get(url, timeout=10, headers=BROWSER_HEADERS)
        if not r.ok or len(r.content) > 4_000_000:
            return None
        mime = r.headers.get("Content-Type", "image/jpeg").split(";")[0]
        if not mime.startswith("image/"):
            return None
        answer = ask_gemini([
            "Посмотри на фотографию. Виден ли на ней пострадавший человек: "
            "тело, кровь, следы увечий, человек под машиной или под завалом? "
            "Ответь одним словом: ДА или НЕТ. Разбитая машина, пожар, полиция, "
            "техника без людей — это НЕТ.",
            {"mime_type": mime, "data": r.content},
        ], charter=False)
        return answer.strip().upper().startswith("ДА")
    except Exception:
        return None


def mark_graphic_photos(items, lang):
    """Ставит пометку тем новостям, у которых тяжёлый именно СНИМОК."""
    shelf = AI_CACHE.setdefault("_images", {})
    if not isinstance(shelf, dict):
        shelf = AI_CACHE["_images"] = {}
    asked = marked = 0
    now = int(datetime.now().timestamp() * 1000)
    # Не больше восьми новых снимков за прогон на пул: картинка стоит дороже
    # текста, а на счету 20.08 оставалось $2.51. Уже виденные кадры считаются
    # бесплатно — вердикт лежит в памяти, поэтому предел бьёт только по
    # новинкам. Что не успели спросить сегодня — спросим следующим прогоном.
    ASK_LIMIT = 8
    for it in items:
        url = it.get("imageUrl")
        if not url or not _looks_incident(it):
            continue
        key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
        v = shelf.get(key)
        if not isinstance(v, dict):
            if asked >= ASK_LIMIT:
                continue
            verdict = _photo_is_graphic(url)
            if verdict is None:
                continue
            v = shelf[key] = {"graphic": verdict, "ts": now}
            asked += 1
        if v.get("graphic"):
            it["sensitiveImage"] = True
            marked += 1
    if asked or marked:
        print(f"  🩸 Снимки происшествий [{lang}]: спрошено {asked}, "
              f"под размытие {marked}")

# Номер свода правил. Меняем его при КАЖДОЙ правке промпта — иначе память
# вердиктов держит решения, принятые по старым правилам, двое суток, и новое
# правило будто не работает. Так после запрета светской болтовни она осталась
# в португальской ленте: ИИ одобрил её часом раньше, и мы больше не спрашивали.
# 6 — сброс памяти после починки одностороннего кэша: за время, пока
# одобрения не запоминались, а отказы копились, накопилось 9264 записи, почти
# сплошь отказы. Оставить их значит тащить чёрный список ещё двое суток
# Как часто выходит лента, в минутах. Приложение показывает это читателю —
# как радио объявляет «новости каждые пятнадцать минут». Цифра живёт здесь,
# чтобы обещание нигде не разошлось с делом: 22.08 в описании Play стояло
# «каждый час», а собирали мы раз в два часа с 18 августа.
# МЕНЯТЬ ВМЕСТЕ С cron в .github/workflows/fetch.yml
REFRESH_MINUTES = 60

# Версия приложения, опубликованная в Play. Поднимать вместе с versionCode.
#
# 31 / 1.7.7 одобрена 24.08.2026. Тридцатая до читателей не дошла: её
# заменили тридцать первой прямо на проверке, поэтому номер 30 в Play занят,
# но у людей его нет. Объявлять надо то, что реально лежит в магазине.
APP_LATEST_CODE = 31
APP_LATEST_NAME = "1.7.7"

# ⚠️ ПОДНИМАТЬ ПРИ КАЖДОЙ ПРАВКЕ ПРОМПТА ОТБОРА ИЛИ УСТАВА.
#
# Память вердиктов (AI_CACHE) хранит решение по статье двое суток. Решения,
# принятые СТАРЫМ промптом, остаются в силе, пока это число не изменится, —
# и правка промпта применяется только к новым статьям.
#
# 23-24.08 я дважды правил промпт второго этапа и оба раза забыл поднять
# версию. Замер показал «правка почти не помогла», хотя она просто не
# применялась: портреты Guardian и «EN DIRECT» от Figaro были осуждены
# накануне и держались кэшем. Признак этой ошибки — изменили правило, а
# лента почти не сдвинулась.
#
# 12 — возврат второму этапу права снимать материалы без инфоповода (24.08).
# 13 — сузили это право: не помогло, 9 из 36.
# 14 — ОТКАТ к состоянию до 12: право снимать по инфоповоду убрано совсем.
#      Двух попыток хватило, чтобы понять — вопрос не в формулировке, а в
#      том, что второй этап судит по заголовку. Возвращаться к этому только
#      с телами статей и через холостую сверку.
RULES_VERSION = 14

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


# Момент, когда сбор текста перестал обрываться на 700 знаках (20.08.2026).
# Всё, что разобрано раньше и подозрительно близко к прежнему пределу,
# перечитываем заново.
PAGE_BODY_CUT_FIX_TS = 1787220000000


def load_page_bodies():
    global PAGE_BODY_CACHE
    try:
        PAGE_BODY_CACHE = db.reference("/page_bodies").get() or {}
    except Exception as e:
        print(f"  ⚠️ Память разобранных страниц недоступна: {e}")
        PAGE_BODY_CACHE = {}
    # Разобранное однажды лежит здесь сутками, поэтому испорченный текст живёт
    # дольше самой поломки: правка кода читателю не поможет, пока страница
    # берётся из памяти. Выбрасываем всё, что начинается с курсов валют.
    bad = [k for k, v in PAGE_BODY_CACHE.items()
           if isinstance(v, dict)
           and _is_sidebar_table(str(v.get("text", ""))[:120].split("\n")[:6])]
    for k in bad:
        PAGE_BODY_CACHE.pop(k, None)
    # Половинки эпохи предела в 700 знаков. Читатель 20.08 открыл заметку о
    # ДТП в Казахстане и увидел «Двое граждан Кыргызстана — И.Г.В., 1963 г.р.,
    # и Е.Е.Ю., 1974 г.р.» — на этом текст кончался, и то, что оба погибли,
    # осталось за обрывом. Правка предела таким записям не поможет: страница
    # берётся из памяти, а не со свежего разбора.
    short = [k for k, v in PAGE_BODY_CACHE.items()
             if isinstance(v, dict) and v.get("ts", 0) < PAGE_BODY_CUT_FIX_TS
             and 600 < len(str(v.get("text", ""))) < 780]
    for k in short:
        PAGE_BODY_CACHE.pop(k, None)
    print(f"  📄 Память разобранных страниц: {len(PAGE_BODY_CACHE)}"
          + (f" (выброшено с курсами валют: {len(bad)})" if bad else "")
          + (f" (обрезанных по старому пределу: {len(short)})" if short else ""))


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


# ─── ЭТАП 1: дешёвый отсев ─────────────────────────────────────────────────
#
# В БОЮ с 23.08.2026. До этого сутки ходил вхолостую: помечал, но не удалял.
#
# Холостой прогон был не формальностью. Ошибка первого этапа необратима —
# выброшенная новость до второго этапа не дойдёт и в ленту не вернётся,
# поэтому право удалять он получил только после того, как его решения
# сверили глазами с решениями прежнего единого промпта.
#
# Итог сверки по русскому пулу: 203 новости на входе, ТРИ расхождения (1%).
# Все три оказались правотой этапа 1, а не его ошибкой:
#   · «Не пугайте ребенка школой: советы родителям» — подборка советов
#   · «le PSG est-il plus fort que la saison dernière?» — вопрос в заголовке,
#     то есть разбор, а не событие
#   · «En direct : Pezeshkian reconnaît…» — прямая трансляция
# Все три прежний конвейер пропускал в ленту.
#
# Вернуть холостой режим = поставить True. Сверка _cull_dry_report при этом
# продолжает печататься и в бою: она показывает, что этап 1 выбросил.
CULL_DRY_RUN = False
CULL_CHUNK = 120        # заголовки короткие, порция может быть втрое больше,
                        # чем у второго этапа: меньше порций — меньше накладных

_CULL_PROMPT = """Ты первичный фильтр новостного агрегатора Ticker 24/7.

Твоя ЕДИНСТВЕННАЯ задача — отсеять то, что новостью не является. Ты НЕ
размечаешь рубрики, НЕ определяешь срочность, НЕ выбираешь полку, НЕ
переводишь. Один вопрос по каждому пункту: это новость или мусор?

Ты видишь только заголовок и название издания. Этого достаточно, чтобы
опознать рекламу, гороскоп, прямую трансляцию или пересказ передачи, — и
недостаточно, чтобы судить о содержании статьи. СОМНЕВАЕШЬСЯ — ОСТАВЛЯЙ:
пропущенный мусор разберёт следующий этап, а выброшенная новость не вернётся.

Верни ТОЛЬКО JSON, без пояснений и без текста вокруг:
{"drop": [2, 7, 15]}

Если отсеивать нечего — верни {"drop": []}.

НОВОСТИ:
"""


def _cull_chunk_loop(news_list, lang="ru"):
    """ЭТАП 1. В холостом режиме только проставляет `_cull_drop_candidate`.

    Список возвращается НЕТРОНУТЫМ — ни одна новость отсюда не исчезает,
    пока CULL_DRY_RUN. Это главное свойство функции, и менять его следует
    одним осознанным движением, а не попутно.
    """
    if not news_list:
        return news_list
    marked, asked = 0, 0
    for i in range(0, len(news_list), CULL_CHUNK):
        part = news_list[i:i + CULL_CHUNK]
        titles = [f"{n + 1}. [{x.get('source', '?')}] {x.get('title', '')}"
                  for n, x in enumerate(part)]
        try:
            # Ключ один на все пулы: и промпт отсева, и его устав от пула не
            # зависят — вопрос «новость или мусор» одинаков для всех.
            # Второму этапу так нельзя, там в тексте назван пул
            text = ask_gemini_cached("cull", _CULL_PROMPT, chr(10).join(titles),
                                     charter=_editorial_cull_charter())
            asked += 1
            if "```" in text:
                text = text.split("```")[1].replace("json", "").strip()
            drop = json.loads(text).get("drop", [])
        except Exception as e:
            # Отказ первого этапа не должен стоить нам ленты: молча идём
            # дальше, второй этап отсеет всё сам, как и делал до сих пор
            print(f"  ⚠️ Этап 1 [{lang}] не ответил, порция пропущена: {str(e)[:90]}")
            continue
        for n in drop:
            try:
                idx = int(n) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(part):
                part[idx]["_cull_drop_candidate"] = True
                marked += 1

    mode = "холостой" if CULL_DRY_RUN else "боевой"
    print(f"  🧪 Этап 1 ({mode}) [{lang}]: помечено {marked} из {len(news_list)} "
          f"за {asked} запросов")
    if CULL_DRY_RUN:
        return news_list
    return [x for x in news_list if not x.get("_cull_drop_candidate")]


def _cull_dry_report(before, after, lang):
    """Сравнивает решения этапа 1 с решениями нынешнего единого промпта.

    `before` — что пошло в отбор, `after` — что дожило до ленты. Разница между
    ними и есть приговор нынешнего конвейера, с которым мы сверяемся.

    Две колонки ошибок, и они неравноценны:
      · ЛОЖНОЕ СРАБАТЫВАНИЕ — этап 1 выбросил бы то, что дошло до ленты. Это
        дорогая ошибка: в бою новость исчезла бы безвозвратно. Читать в первую
        очередь.
      · НЕ СОВПАЛО ИНАЧЕ — этап 1 оставил то, что до ленты не дошло. Читать
        эту цифру как «пропустил мусор» НЕЛЬЗЯ, и это ограничение самой
        сверки, а не этапа 1: второй этап возвращает только список
        оставленного и причину отказа не сообщает. Новость могла отпасть
        и потому, что она мусор, и потому, что она не для нашего читателя
        (английский теннис, индийское кино) — а отсеивать чужую повестку
        первому этапу не поручено вовсе, это работа второго.

    Поэтому решение о переводе в бой принимается по ПЕРВОЙ колонке. Вторая —
    справочная, по ней видно лишь верхнюю границу возможной экономии.
    """
    # Сличаем по адресу статьи, а не по id() объекта: конвейер местами
    # пересобирает словари, и тождество объектов ненадёжно
    survived = {x.get("url") for x in after if x.get("url")}
    false_drops = [x for x in before
                   if x.get("_cull_drop_candidate") and x.get("url") in survived]
    misses = [x for x in before
              if not x.get("_cull_drop_candidate") and x.get("url") not in survived]

    total = len(before) or 1

    # В БОЮ колонка ложных срабатываний бессмысленна: выброшенное этапом 1 до
    # ленты дойти не может по определению, и она всегда покажет ноль. Поэтому
    # в бою печатаем не сверку, а СПИСОК ВЫБРОШЕННОГО — то единственное, что
    # тут стоит смотреть глазами
    if not CULL_DRY_RUN:
        removed = [x for x in before if x.get("_cull_drop_candidate")]
        print(f"\n  ── Этап 1, что выброшено [{lang}] ───────────────────────")
        print(f"     на входе {len(before)}, снято этапом 1: {len(removed)} "
              f"({len(removed) * 100 // total}%), дожило до ленты {len(after)}")
        # Подробности печатаем по русскому пулу (его читает человек) И по
        # любому, где отсев зашкалил. 23.08 французский снял 34% против 9-23%
        # у прочих — такое надо видеть поимённо, а не узнавать из жалобы на
        # опустевшую ленту. Логи бесплатны, необратимый отсев дорог
        loud = len(removed) * 100 // total >= 25
        if removed and (lang == "ru" or loud):
            if loud and lang != "ru":
                print(f"     ⚠️ отсев выше обычного — показываю целиком:")
            for x in removed[:25]:
                print(f"        [{x.get('source', '?')}] {str(x.get('title', ''))[:96]}")
            if len(removed) > 25:
                print(f"        … и ещё {len(removed) - 25}")
        print("  ─────────────────────────────────────────────────────────────\n")
        return

    print(f"\n  ── Этап 1, холостая сверка [{lang}] ─────────────────────────")
    print(f"     на входе {len(before)}, дожило до ленты {len(after)}")
    print(f"     ложных срабатываний: {len(false_drops)} "
          f"({len(false_drops) * 100 // total}%) — выбросил бы живое")
    print(f"     не совпало иначе:    {len(misses)} "
          f"({len(misses) * 100 // total}%) — оставил то, что не дошло до ленты")
    print("     ⚠️ вторая цифра НЕ равна «пропустил мусор»: второй этап "
          "возвращает только список оставленного,")
    print("        причину отказа он не сообщает, и в этот список попадает "
          "как мусор, так и просто чужая повестка")

    if lang != "ru":
        return          # подробности только по русскому: остальное читать некому

    if false_drops:
        print(f"\n     ❗ ВЫБРОСИЛ БЫ ЗРЯ ({len(false_drops)}) — это цена ошибки:")
        for x in false_drops[:25]:
            print(f"        [{x.get('source', '?')}] {str(x.get('title', ''))[:96]}")
        if len(false_drops) > 25:
            print(f"        … и ещё {len(false_drops) - 25}")
    if misses:
        print(f"\n     ○ оставил, но до ленты не дошло ({len(misses)}) — "
              f"среди них и мусор, и чужая повестка:")
        for x in misses[:25]:
            print(f"        [{x.get('source', '?')}] {str(x.get('title', ''))[:96]}")
        if len(misses) > 25:
            print(f"        … и ещё {len(misses) - 25}")
    print("  ─────────────────────────────────────────────────────────────\n")


def _rule_cull(items, lang="?"):
    """ЭТАП 0: бесплатный отсев по правилам — ДО того, как звать ИИ.

    Эти четыре правила годами жили в quality_gate, то есть срабатывали ПОСЛЕ
    отбора. Мы платили модели за разбор гороскопов, прогнозов погоды,
    заглушек и материалов, которые издание само пометило рекламой, — а потом
    выбрасывали их сами, детерминированно и бесплатно.

    Здесь нет ни одного нового правила: те же регулярки, тот же список
    рекламных страниц. Изменился только момент вызова.

    В quality_gate они НАМЕРЕННО оставлены вторым рубежом. Во-первых, сюда
    новость приходит до перевода, а туда — после, и текст к тому времени
    другой. Во-вторых, дублирующая проверка ничего не стоит, а страхует от
    правки, которая однажды переставит стадии местами.
    """
    kept, why = [], Counter()
    for item in items:
        title = (item.get("title") or "").strip()
        low = (item.get("summary") or "").strip().lower()

        if any(m in low for m in QC_STUB_MARKERS):
            why["заглушка вместо текста"] += 1
            continue
        if item.get("url") in AD_PAGES:
            why["издание помечает рекламой"] += 1
            continue
        if _is_daily_filler(title):
            why["гороскоп или подсказка к игре"] += 1
            continue
        if QC_WEATHER.search(title):
            why["погода"] += 1
            continue
        kept.append(item)

    if why:
        total = sum(why.values())
        parts = ", ".join(f"{k} {v}" for k, v in why.most_common())
        print(f"  🧹 Этап 0 [{lang}]: отсеяно {total} до ИИ ({parts})")
    return kept


def filter_with_gemini(news_list, lang="ru"):
    """Прогоняет пул через ИИ порциями и склеивает результат.

    Про статьи с известным вердиктом ИИ не спрашиваем вовсе — берём из памяти.
    Порядок исходного списка сохраняется: и те, что вернулись из памяти, и те,
    что судили сейчас, встают на свои места.
    """
    if not news_list:
        return news_list

    # ЭТАП 0 — бесплатный отсев прежде всего, чтобы не платить за гороскопы
    news_list = _rule_cull(news_list, lang)
    if not news_list:
        return news_list

    global _LAST_CHUNK_FELL_BACK
    _LAST_CHUNK_FELL_BACK = False
    pool_cache = AI_CACHE.setdefault(lang, {})
    if not isinstance(pool_cache, dict):
        pool_cache = AI_CACHE[lang] = {}
    # Мировую новость все четыре пула судят порознь — и платим мы за неё
    # четырежды. Между тем вопрос «есть ли тут событие» от языка не зависит:
    # землетрясение остаётся землетрясением и для испанца, и для бразильца.
    # Общая полка вердиктов для мировых экономит почти половину расхода
    shared = AI_CACHE.setdefault("_world", {})
    if not isinstance(shared, dict):
        shared = AI_CACHE["_world"] = {}

    known_keep, to_ask = {}, []
    dropped_by_memory = 0
    for idx, item in enumerate(news_list):
        key = _cache_key(item)
        v = pool_cache.get(key)
        if v is None and item.get("scope") == "world":
            v = shared.get(key)
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
        chunk = FALLBACK_CHUNK if FALLBACK_MODE else GEMINI_CHUNK
        for start in range(0, len(asked_items), chunk):
            out.extend(_filter_chunk(asked_items[start:start + chunk], lang))
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
                    # мировую кладём и в общую полку — другим пулам не
                    # придётся спрашивать ИИ о том же самом
                    if item.get("scope") == "world":
                        shared[k] = dict(pool_cache[k])
            elif remember:
                pool_cache[k] = {"keep": False, "ts": now, "rules": RULES_VERSION}
                if item.get("scope") == "world":
                    shared[k] = dict(pool_cache[k])

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
    # Промпт разделён надвое: неизменная часть уходит в кэш и оплачивается
    # вдесятеро дешевле, меняется только список заголовков в хвосте
    # Промпт урезан 23.08.2026. Правила отсева — реклама, кликбейт, живые
    # трансляции, пересказ передач, инфоповод — переехали на ПЕРВЫЙ этап
    # (EDITORIAL_CULL.md, _cull_chunk_loop). Носить их здесь второй раз значит
    # платить за одно и то же дважды: до правки неизменная часть весила 8 008
    # токенов и уходила по два десятка раз за прогон.
    #
    # Что осталось намеренно: правила «для кого эта новость» — областные
    # происшествия, региональная повестка больших стран, спорт чужого
    # пространства. Первый этап их НЕ знает и знать не должен: он судит,
    # новость ли это вообще, а не кому она нужна. Убрать их отсюда — значит
    # залить пул чужой повесткой.
    preamble = f"""Ты редактор пула «{lang.upper()}» новостного агрегатора Ticker 24/7.
Аудитория: читатели на {pool['language_name']} языке, регион: {pool['region']}.

═══ ГЛАВНОЕ: ЧТО ОТ ТЕБЯ ТРЕБУЕТСЯ ═══
Новости уже прошли первичный отсев: явную рекламу, гороскопы, прогнозы погоды
и прямые трансляции сняли до тебя. Перебирать это заново не нужно.

Твоя работа — РАЗМЕТКА:
  · категория
  · приоритет (priority)
  · полка (scope)
  · сверка заголовка с текстом

Удалять можно ТОЛЬКО по одной причине — новость не для читателя этого пула
(правило №1). Больше поводов удалять у тебя нет.

ПОЧЕМУ ТАК, а не «снимай всё без инфоповода». 24.08 второму этапу дали право
снимать материалы без события — и он выкосил французские местные новости:
прошедших было 35 из 45, стало 4 из 49, у Franceinfo и Le Figaro по нулю.
Причина в том, что здесь видны ТОЛЬКО заголовки: французские ленты дают
назывные анонсы, событие раскрывается в тексте, которого тут нет. Сужение
формулировки не помогло — 9 из 36. Пока второй этап не получит тела статей,
права снимать по инфоповоду у него быть не должно.

Язык заголовка поводом не является: отбор шёл до перевода, всё отобранное
будет переведено следующим шагом. Суди по содержанию.

═══ ПРАВИЛО №1 — ДЛЯ КОГО ЭТА НОВОСТЬ ═══
Единственное правило, по которому ты вправе удалить. Событие настоящее, но
чужое: читателю этого пула оно не нужно.

- Происшествия областного масштаба: перевернулся бензовоз на трассе в
  Самарской области, столкнулись машины в районном центре, загорелся склад.
  Для читателя другой страны это шум, даже если пишет крупное агентство
- Региональные новости БЕЗ общенационального значения из больших стран
  (Россия, Казахстан и т.п.): рядовое ДТП, бытовое происшествие, местный суд,
  локальное коммунальное ЧП в конкретном городе или области — это новость ТОГО
  региона, не интересна читателю из другой страны СНГ и ЦА, даже если источник
  федеральный (РИА, ТАСС и т.п. репортят и локальные истории тоже).
  Оставляй только: федеральные решения и законы, события с общенациональным
  резонансом, крупные катастрофы и массовые жертвы, напрямую касающееся других
  стран пула (курс валют, миграция, санкции)
- СПОРТ ЧУЖОГО ПРОСТРАНСТВА. Вид спорта, которым в странах пула не занимаются
  и не смотрят: крикет и регби для испано- и португалоязычных, бейсбол для
  европейцев, американский футбол вне США. Исключение — мировые первенства,
  где участвует страна пула
- Нишевый развлекательный контент не для массовой аудитории (субкультуры,
  фандомы)

Сомневаешься, нужна ли новость читателю, — ОСТАВЛЯЙ. Лишняя новость займёт
место, выброшенная не вернётся.

═══ ПРАВИЛО №2 — ПРИОРИТЕТЫ ═══
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

═══ ПРАВИЛО №3 — ЗАГОЛОВОК ДОЛЖЕН ОТВЕЧАТЬ ТЕКСТУ ═══
Заголовок — единственное, что читатель видит в ленте. Если он обещает одно,
а в тексте другое, обмануты все, кто открыл. Проверь каждую новость на это и
номера несовпавших верни в "title_mismatch".

Несовпадение — это когда:
  · заголовок называет ФАКТ, которого в тексте нет: «Первый тест Snapdragon
    8 Elite: +22% CPU», а в тексте — что процессоры покажут в следующем
    месяце. Никакого теста и никаких процентов
  · заголовок обещает разбор или подробности, а текст — анонс чужого
    материала: «Почему Махачев проиграл — об этом РБК Спорт»
  · текст начинается как продолжение заголовка и сам по себе бессмыслен:
    «И Рита Азеведо Гомеш. И Ноэмия Делгадо»

Это НЕ несовпадение:
  · текст короткий, но подтверждает заголовок
  · текст добавляет подробности, которых в заголовке не было — так и должно быть
  · заголовок ярче текста, но факт тот же

Сомневаешься — не помечай: лучше пропустить кривую новость, чем снять с
эфира честную.

═══ ПРАВИЛО №4 — ПОДОЗРЕНИЕ НА СКРЫТУЮ РЕКЛАМУ ═══
Явную рекламу сняли до тебя. Но если что-то всё же похоже на промо — единственный
герой материала бренд, перечислены тарифы или условия, — не удаляй, а добавь
номер в "ad_suspects". Такие новости получат короткий срок жизни и сами исчезнут
при следующем обновлении. Это подстраховка, а не наказание: ошибиться не страшно.

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

  МОСТ (исключение из правила «где произошло»). Событие случилось за границей,
  но его участники — граждане {pool['home']} или сама эта страна как сторона:
  наш соотечественник попал в аварию, суд или беду в чужой стране; его там
  судят, награждают, спасают, выдают; чужая страна забирает или передаёт
  своего человека у нас. Такую новость ставь local и повышай приоритет на
  единицу.
  Почему: это новость про своих, и читателю ценно прочитать, ЧТО ПИШУТ ТАМ, а
  не пересказ местного издания, где половина подробностей потеряна. Работает в
  обе стороны: для кыргызстанского читателя — американский репортаж о
  кыргызстанце, для американского — бишкекская новость об американце.
  Не путать с обычной заграничной новостью: связь должна быть в людях или в
  государстве, а не в упоминании страны вскользь

Указывай полку ТОЛЬКО там, где нынешняя явно неверна — в поле "scope_fix".
Сомневаешься — не указывай, разметка по изданию останется как есть.

Верни ТОЛЬКО JSON без объяснений:
{{"keep": [1,3,5], "urgent": [2], "important": [3,5], "recategorize": {{"4": "SPORT", "7": "TECH"}}, "ad_suspects": [3], "title_mismatch": [6], "scope_fix": {{"5": "world", "9": "local"}}}}

В "keep" перечисли номера, которые ОСТАЮТСЯ. Помни: удалять можно только по
правилу №1 — новость не для читателя этого пула. Всё остальное оставляй.

НОВОСТИ:
"""

    try:
        # Псевдоним, а не конкретная версия: Google отключает старые модели
        # без предупреждения (так умерла gemini-2.0-flash), и тогда фильтр молча
        # уходит в запасной вариант — 60 случайных статей вместо отбора
        text = ask_gemini_cached(lang, preamble, chr(10).join(titles))
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        result = json.loads(text)
        keep = [i-1 for i in result.get("keep", [])]
        urgent = set(i-1 for i in result.get("urgent", []))
        important = set(i-1 for i in result.get("important", []))
        # Рубрику чистим от пробелов и приводим к верхнему регистру: 23.08 во
        # французском пуле завелась рубрика " NEWS" с ведущим пробелом — для
        # приложения это отдельная рубрика, то есть лишняя пустая вкладка
        recategorize = {int(k) - 1: str(v).strip().upper()
                        for k, v in result.get("recategorize", {}).items()
                        if str(v).strip()}
        ad_suspects = set(i-1 for i in result.get("ad_suspects", []))
        # Заголовок обещает то, чего в тексте нет. Такие снимаем с эфира:
        # заголовок — единственное, что видно в ленте, и если он врёт,
        # врёт всё приложение
        title_mismatch = set(i-1 for i in result.get("title_mismatch", []))
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
        dropped_mismatch = 0
        for i in keep:
            if 0 <= i < len(news_list):
                # Заголовок обещает то, чего в тексте нет — снимаем с эфира
                if i in title_mismatch:
                    dropped_mismatch += 1
                    continue
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
                # «Местная» полка — только для своих. Португальская заметка,
                # которую ИИ переставил в местные, вышла в русском пуле под
                # киргизским флагом: читатель видит флаг своей страны на
                # материале лиссабонской газеты. Чужому изданию местная полка
                # закрыта — кроме новостей, перевезённых мостом («наши за
                # границей»), для них это как раз и задумано
                if (i in scope_fix and scope_fix[i] == "local"
                        and not item.get("bridge")
                        and not _is_home_source(item, lang)):
                    scope_fix.pop(i, None)
                _demote_foreign_local(item, lang)
                # Запрета «своя страна не может быть мировой» здесь НЕТ, и
                # это осознанно. Мировую новость определяет масштаб, а не
                # география: этап мирового чемпионата или Всемирные игры
                # кочевников в Кыргызстане — мировое событие, случившееся у
                # нас. Отличить крупное от мелкого умеет только ИИ, и правило
                # для него записано в EDITORIAL.md
                if i in scope_fix and scope_fix[i] != item.get("scope"):
                    print(f"  📐 [{lang}] {item.get('scope')}→{scope_fix[i]}: "
                          f"[{item.get('source','?')}] {item.get('title','')[:70]}")
                    item["scope"] = scope_fix[i]
                    _demote_foreign_local(item, lang)
                filtered.append(item)
        if dropped_mismatch:
            print(f"  📰 [{lang}] заголовок не отвечает тексту: снято {dropped_mismatch}")
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
        # Случайная выборка была плохим запасным путём: без ИИ лента
        # наполнялась чем попало. Отбираем по признакам, которые видно без
        # понимания смысла: приоритет источника, свежесть, наличие фото,
        # длина текста. Хуже ИИ, но осмысленно — а сегодня, когда деньги на
        # ИИ кончились, это единственное, что стоит между читателем и хаосом
        def _plain_score(it):
            score = it.get("priority", 0) * 100
            age_h = (datetime.now().timestamp() * 1000 - it.get("publishedAt", 0)) / 3600000
            score += max(0, 48 - age_h)                       # свежесть
            if (it.get("imageUrl") or "").startswith("http"):
                score += 25                                   # с фотографией
            body = it.get("summary") or ""
            score += min(len(body) / 40.0, 25)                # с текстом, не огрызок
            if len(it.get("title", "")) < 25:
                score -= 20                                   # заголовок-обрубок
            return score

        keep_n = max(1, len(news_list) // 2)
        ranked = sorted(news_list, key=_plain_score, reverse=True)[:keep_n]
        print(f"  🧭 [{lang}] ИИ недоступен: отобрано по признакам, "
              f"{len(ranked)} из {len(news_list)}")
        return ranked

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

    # Понятные читателю ru-пула языки. Список ДОЛЖЕН совпадать с cyrillicLangs
    # в приложении (NewsBuffer.kt) — расхождение и вылезло 19.08: сервер считал
    # узбекский «своим» и не переводил, приложение считало чужим, и читатель
    # получал «Mixail Fedorov Ukrainada saylov o'tkazishga chaqirdi».
    #
    # Прежний список опирался на алфавит: раз кириллица — значит поймут. Дважды
    # ошибочно. Узбекский пишется латиницей, а казахский и таджикский тексты
    # русскоязычный читатель не понимает независимо от алфавита. Родство
    # алфавита — не родство языка, и решает здесь понятность, а не письменность.
    CYRILLIC = {"ru", "ky", "uk", "be"}
    if pool == "ru":
        # Разнобой внутри одной новости: заголовок на одном языке, текст на
        # другом. «Қазақстанның мұнай экспорты…» стоял над русским текстом —
        # читатель спотыкается на первой строке. Кириллица кириллице рознь:
        # ә, ғ, қ, ұ, һ, і есть в казахском и нет в русском
        # «і» здесь быть не должно: она есть и в украинском, и заголовок
        # «У Києві...» уезжал на перевод как казахский. Берём буквы, которых
        # нет ни в русском, ни в украинском, и требуем двух — одна случайная
        # буква в имени собственном ещё ничего не значит
        kz_only = set("әғқұһ")
        title_kz = sum(1 for c in item.get("title", "").lower() if c in kz_only)
        body_kz = any(c in kz_only for c in (item.get("summary", "") or "").lower()[:400])
        if title_kz >= 2 and not body_kz:
            return True
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
    # Французского здесь не было с самого появления пула: в промпт уходило
    # «Переведи новости на fr язык», и модель угадывала по коду. Угадывала
    # чаще всего верно, но просить перевод кодом языка — значит однажды
    # получить не тот язык на ровном месте
    LANG_NAME = {"ru": "русский", "en": "английский", "es": "испанский",
                 "pt": "португальский", "fr": "французский"}
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
        text = ask_gemini(prompt, charter=False)
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


# Падежные промахи машинного перевода. Форма существует, но не после этого
# предлога: «в бою» верно, «о бою» — нет, нужно «о бое». Машина выбирает по
# частотности и на таких парах мажет. Список короткий и растёт по находкам
# читателя: 21.08 — «ведёт переговоры о бою».
_CASE_FIXES = [
    (r"\bо бою\b", "о бое"),
    (r"\bо краю\b", "о крае"),
    (r"\bо строю\b", "о строе"),
    (r"\bо полку\b(?! Игорев)", "о полке"),
    (r"\bо саду\b", "о саде"),
    (r"\bо лесу\b", "о лесе"),
    (r"\bо снегу\b", "о снеге"),
    (r"\bо берегу\b", "о береге"),
    (r"\bо мосту\b", "о мосте"),
    (r"\bо порту\b", "о порте"),
]


def fix_russian_cases(text: str) -> str:
    """Правит падежные промахи перевода. Дёшево и без ИИ."""
    if not text:
        return text
    for wrong, right in _CASE_FIXES:
        text = re.sub(wrong, right, text, flags=re.I)
    return text


def _still_foreign(text: str, target: str) -> bool:
    """Остался ли текст на чужом языке после «перевода».

    21.08 читатель открыл новость Gazeta.uz: заголовок по-русски, пометка
    «Переведено автоматически», а всё тело — по-узбекски. Перевод считал работу
    сделанной, не глядя на результат, и наше правило «не переведённое не
    публикуем» верило пометке.

    Узбекская кириллица отличается от русской буквами ў, қ, ғ, ҳ; кыргызская —
    ө, ү, ң. Ни одной из них в русском нет.
    """
    t = (text or "").lower()
    if len(t) < 40:
        return False
    if target == "ru":
        # Порог два, а не три: этих букв в русском нет вовсе, и даже пара —
        # верный признак чужого языка
        # ў қ ғ ҳ — узбекский и таджикский, ө ү ң — кыргызский и казахский,
        # ӯ ҷ ӣ — таджикский. Ни одной из них в русском нет
        if sum(t.count(c) for c in "ўқғҳөүңӯҷӣ") >= 2:
            return True
        cyr = len(re.findall(r"[а-яё]", t))
        lat = len(re.findall(r"[a-z]{4,}", t))
        return cyr < 10 and lat >= 8
    # для латинских пулов чужой считаем кириллицу
    return len(re.findall(r"[а-яё]", t)) >= 10


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
        # Проверяем РЕЗУЛЬТАТ, а не факт вызова. Модель иногда возвращает
        # исходный текст, а мы ставили пометку «переведено» и публиковали
        if _still_foreign(summary, target_lang) or _still_foreign(title, target_lang):
            fixed_t = _gtx_translate(title, target_lang)
            fixed_s = _gtx_translate(summary, target_lang)
            if fixed_t and not _still_foreign(fixed_t, target_lang):
                title, summary = fixed_t, (fixed_s or summary)
            else:
                return False        # в эфир не пойдёт: правило о переводе
        if target_lang == "ru":
            title = fix_russian_cases(title)
            summary = fix_russian_cases(summary)
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
    # Служебные строки публикации: «Published Aug 15, 2026, 05:46 PM»,
    # «Updated ...». Даты и так показаны под карточкой, в тексте они лишние
    r"^\s*(published|updated)\s+[A-Z][a-z]{2}\s+\d{1,2},\s+\d{4}.*$",
    r"^\s*(опубликовано|обновлено)\s+\d{1,2}\s+\S+\s+\d{4}.*$",
    # Приглашение подписаться отдельной строкой. Ловим и в уже собранном
    # тексте, а не только при разборе страницы: часть новостей приходит с
    # этой строкой прямо из ленты
    # Подпись авторства В НАЧАЛЕ описания: «Автором материала является K-News .
    # K-News. Администрация США…». Вырезаем только саму подпись, а не строку
    # целиком — иначе потеряли бы вместе с ней первое предложение новости
    r"Автором материала является[^.]{0,40}\.\s*[A-Za-zА-Яа-яЁё\-]{0,20}\.?\s*",
    r"^.*\b(sign up now|newsletters? delivered to your inbox|subscribe to read|"
    r"подпишитесь на (рассылку|нашу)|получайте новости на почту)\b.*$",
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


# Погода и коммунальные сводки — не новости.
#
# «В Бишкеке сейчас +27°C. Текущая погода в городах Кыргызстана» ушло в
# МИРОВЫЕ новости да ещё и переведённым на английский — читателю в Лондоне.
# У погоды нет события: она меняется каждый час и ничего не сообщает. То же с
# ежедневными сводками об отключениях света и воды: их место в справочнике, а
# не в ленте.
QC_WEATHER = re.compile(
    r"(погода|прогноз погоды|температура воздуха|сейчас \+?\-?\d+ ?°|"
    r"current weather|weather for|weather in|forecast for|"
    r"el tiempo en|pronóstico del tiempo|previsão do tempo|clima em|"
    # кыргызский, казахский, узбекский: «аба ырайы» — это и есть погода
    r"аба ырайы|аптаптуу ысык|ауа райы|ob-havo|об-хаво)",
    re.I)

# Ежедневный корм ради поисковых запросов: подсказки к головоломкам, ответы
# на кроссворды, гороскопы. Forbes каждый день печатает «NYT Strands Hints,
# Spangram, ответы», The Sun — гороскопы. Событий там нет и быть не может:
# это тексты, написанные под запрос в поиске, а не под происшествие
# Название игры само по себе не приговор: «создатель Wordle продал игру New
# York Times» — настоящая новость. Приговор — сочетание игры со служебным
# словом: подсказки, ответы, разбор на сегодня
QC_FILLER_GAME = re.compile(r"(wordle|strands|spangram|connections|quordle|"
                            r"кроссворд|судоку|головоломк)", re.I)
QC_FILLER_SERVICE = re.compile(
    r"(подсказк|ответы|ответ на|hints?\b|answers?\b|solution|"
    r"на сегодня|today|за \d{1,2} \w+|,\s*\w+, \d{1,2})", re.I)
# А это служебное само по себе, без всяких игр
QC_FILLER_ALONE = re.compile(
    r"(гороскоп|horóscopo|astrological forecast|"
    r"результаты лотереи|lottery results|номера тиража)", re.I)


def _is_daily_filler(text: str) -> bool:
    if not text:
        return False
    if QC_FILLER_ALONE.search(text):
        return True
    # Название игры должно стоять В НАЧАЛЕ: служебные подсказки так и пишут
    # («NYT Strands Hints…»), а в настоящей новости игра упоминается по ходу
    # («Суд обязал компанию раскрыть ответы на кроссворды»)
    head = text[:30]
    return bool(QC_FILLER_GAME.search(head) and QC_FILLER_SERVICE.search(text))


# Начало текста, выдающее подпись к ролику, а не новость. Проверяем именно
# НАЧАЛО: фраза «лучшие моменты» внутри большого репортажа — обычные слова
QC_VIDEO_CAPTION = re.compile(
    r"^\s*(highlights of|highlights from|watch:|video:|"
    r"лучшие моменты|обзор матча|смотрите видео|видео:|"
    r"melhores momentos|veja o vídeo|"
    r"lo más destacado|lo destacado|los mejores momentos|"
    r"resumen del partido|destacados d)",
    re.I)


STORY_TTL_MS = 24 * 3600 * 1000     # предельный срок жизни обзора
# Сюжет живёт, пока о нём ПИШУТ. 21.08 читатель открыл ленту и увидел
# «Трамп всё ещё угрожает Ирану» вторые сутки, Ферстаппена, который давно
# никому не интересен, и Киев с устаревшим числом погибших. Обзор, к которому
# шесть часов не прибавилось ни строки, — уже не сюжет, а вчерашняя газета.
STORY_STALE_MS = 6 * 3600 * 1000
STORY_MAX_BLOCKS = 7
STORY_MIN_SOURCES = 3               # обычный порог: меньше трёх — не обзор
# Для крупного события хватает и двух. 20.08 про атаку на Киев в русской ленте
# писали только BBC и РБК — порог в три отсёк сюжет, который читателю нужнее
# всех прочих. Бедность пула по международной теме не повод молчать.
STORY_MIN_BIG = 2
# Потолок, а не норма: сколько в дне настоящих сюжетов — столько и собираем.
# В тихий день один, 20.08 их было сразу три (Киев, Трамп, безвиз с Китаем).
# Пятёрка стоит здесь не как цель, а как предохранитель от натянутых тем.
STORY_MAX_COUNT = 5


def _looks_kyrgyz(text: str) -> bool:
    """Буквы, которых нет в русском. Поле language врёт: кыргызские заметки
    Sputnik KG и Kabar приходят помеченными русскими."""
    return any(c in text.lower() for c in "өүң")


def _story_block(item, role, lang="ru"):
    """Блок обзора: наша выжимка, снимок издания, его имя.

    Ничего нового здесь не пишется — ни единого слова. ИИ раздаёт роли, текст
    берётся готовый. Поэтому обзор не делает нас автором: мы отбираем и
    расставляем, а говорят издания.

    Две правки 20.08, обе по живому разбору сюжета о безвизе с Китаем:

    1. Текста берём до 700 знаков, а не 420. Заголовок Kaktus обещал «назвали
       условие», выжимка в 207 знаков условия не содержала, а у Sputnik оно
       было — и обрывалось ровно на нём: «бир гана шарты бар — жар…». Если
       выжимка коротка, дотягиваем из разобранной страницы: она уже в памяти
       и денег не стоит.

    2. Обзор идёт НА ОДНОМ языке. Кыргызский абзац посреди русского сюжета
       заставляет читателя спотыкаться, а главное — самое ценное оказывалось
       непрочитанным только потому, что написано на другом языке. Переводим
       бесплатным переводчиком, без квот и без счёта.
    """
    summary = str(item.get("summary") or "")
    if len(summary) < 320:
        # Дотяжка из разобранной страницы: в выжимке часто только лид, а
        # обещанная заголовком суть — во втором абзаце
        body = ""
        try:
            cached = PAGE_BODY_CACHE.get(_cache_key({"url": item.get("url", "")}))
            if isinstance(cached, dict):
                body = str(cached.get("text") or "")
        except Exception:
            body = ""
        if len(body) > len(summary):
            summary = body
    # Прежде здесь при неудаче текст резался ровно по семисотому знаку —
    # посреди слова. Единое правило вместо третьей самописной копии
    summary = trim_to_boundary(summary, 700)

    title = str(item.get("title") or "")
    if (_still_foreign(summary, lang) or _still_foreign(title, lang)
            or (lang == "ru" and (_looks_kyrgyz(title) or _looks_kyrgyz(summary)))):
        title = _gtx_translate(title, lang) or title
        summary = _gtx_translate(summary, lang) or summary

    return {
        "role": role,
        "source": item.get("source", ""),
        "title": title,
        "summary": summary,
        "imageUrl": item.get("imageUrl", ""),
        "url": item.get("url", ""),
        "publishedAt": item.get("publishedAt", 0),
        "scope": item.get("scope", ""),
        # Своё ли это издание для пула. Нужно для первенства: маленький
        # киргизстанский сайт, быстро перепечатавший агентство, открывал
        # бразильцу сюжет про Трампа, а BBC и CBS шли следом. Первенство —
        # награда за добытую новость, и соревноваться должны те, кто в одной
        # лиге: издания языкового пространства читателя
        "own": bool(item.get("scope") in ("local", "pool")),
    }


_ETIQUETTE = re.compile(
    "приветству|поприветствова|благодар|признательн|поздрав|"
    "welcomes|congratulat|thanked|expressed gratitude|"
    "saluda|felicit|agradec|"
    "saúda|parabeniz|agradec", re.I)


def _fold_echoes(blocks):
    """Один текст на всех, кто сообщил то же самое.

    20.08 читатель увидел «Добавляет BBC World» — и следом тот же текст другими
    словами. Роль обещала дополнение, а его не было.

    Такие издания не выбрасываем: три редакции, сказавшие одно и то же, —
    это подтверждение факта, и читателю оно ценно. Но целого абзаца они не
    стоят. Их имена приписываются к тому блоку, который они повторяют:
    «Первым сообщил Knews.kg · то же: BBC World, CBS News».
    """
    def words(t):
        return {w[:5] for w in re.findall(r"[а-яёa-zà-ú]{5,}", (t or "").lower())}

    kept = []
    for b in blocks:
        wb = words(b.get("summary"))
        twin = None
        for k in kept:
            wk = words(k.get("summary"))
            # 0.45, а не 0.6: пересказы бывают вольными. «США нанесут удары»
            # и «США введут меры» — одна и та же новость разными словами, и
            # порог в 0.6 их не роднил
            if wb and wk and len(wb & wk) / min(len(wb), len(wk)) >= 0.45:
                twin = k
                break
        if twin is not None and b.get("source"):
            also = [x for x in str(twin.get("also", "")).split(" · ") if x]
            if b["source"] not in also:
                also.append(b["source"])
            twin["also"] = " · ".join(also)
        else:
            kept.append(dict(b))
    return kept


def _lead_first_reporter(blocks):
    """Затравка — тому, кто сообщил первым.

    ИИ выбирал затравкой того, у кого текст полнее и снимок лучше. Но новость
    добывает не тот, у кого красивее вёрстка: первенство — чужая работа, и
    ставить вперёд опоздавшего значит её присваивать.

    Осторожность: разницу считаем настоящей от четверти часа. Ленты изданий
    врут во времени на минуты, и гоняться за секундами бессмысленно.
    """
    timed = [b for b in blocks if b.get("publishedAt")]
    if len(timed) < 2:
        return blocks
    # Соревнуются издания одной лиги: сначала свои для этого пула, и лишь
    # если своих нет — все подряд
    own = [b for b in timed if b.get("own")]
    first = min(own or timed, key=lambda b: b["publishedAt"])
    current = blocks[0]
    if first is current:
        return blocks
    if current.get("publishedAt", 0) - first["publishedAt"] < 15 * 60 * 1000:
        return blocks
    rest = [b for b in blocks if b is not first]
    if rest and str(current.get("role", "")).startswith("затравк"):
        rest[0] = {**rest[0], "role": "дополнение"}
    return [{**first, "role": "затравка"}] + rest


def _fits_story(block_title: str, story_title: str, lead_title: str,
                lead_summary: str = "") -> bool:
    """Относится ли блок к теме обзора.

    22.08 в обзоре «US-Canada tariffs» оказались иск об имени Трампа, стройка
    бального зала и сокращение водозабора из Колорадо: ИИ собрал мешок «всё
    про США», а не сюжет. Просьба «объединяй только одно событие» помогает не
    всегда, поэтому проверяем сами.

    Правило простое: блок должен делить с названием темы или с затравкой хотя
    бы одно значимое слово. Сравниваем по началам слов — «tariffs» и «tariff»,
    «Канаде» и «Канада» должны считаться одним.
    """
    def stems(t):
        return {w[:5] for w in re.findall(r"[а-яёa-zà-ú]{4,}", (t or "").lower())
                if w not in _STORY_STOP}
    b = stems(block_title)
    if not b:
        return True                      # нечего проверять — не выбрасываем
    # Текст затравки берём тоже: в заголовках одно и то же называют разными
    # словами — «Оттава» вместо «Канады», «пошлины» вместо «тарифов»
    return bool(b & (stems(story_title) | stems(lead_title)
                     | stems(lead_summary[:400])))


_STORY_STOP = {
    "после", "перед", "через", "около", "более", "менее", "может", "будет",
    "стало", "стали", "сообщает", "заявил", "также", "этого", "может",
    "says", "said", "will", "with", "from", "that", "this", "have", "after",
    "into", "about", "than", "their", "would", "could", "первый", "новый",
    "para", "como", "sobre", "entre", "desde", "hasta", "mais", "pelo",
}


def _same_story(a, b) -> bool:
    """Один ли это сюжет. 20.08 Ферстаппен оказался в ленте дважды: один обзор
    собрал ИИ, второй сложила автоматическая группировка похожих, и друг о
    друге они не знали."""
    urls_a = {x.get("url") for x in a.get("blocks", []) if x.get("url")}
    urls_b = {x.get("url") for x in b.get("blocks", []) if x.get("url")}
    if len(urls_a & urls_b) >= 2:
        return True
    def words(st):
        return {w[:4] for w in re.findall(r"[а-яёa-zà-ú]{4,}",
                                          st.get("title", "").lower())}
    wa, wb = words(a), words(b)
    return bool(wa and wb and len(wa & wb) >= 2)


def _refresh_old_blocks(blocks, lang):
    """Приводит блоки прежних сборок к нынешним правилам.

    Обзор живёт сутки, и блок, собранный утром, доживает до вечера таким, каким
    был. 20.08 из-за этого кыргызский абзац остался кыргызским после того, как
    правило «обзор на одном языке» уже работало, а заметка «Кыргызстан
    приветствует решение Китая» — после того, как этикет объявлен не новостью.
    Правило, применённое только к новому, — половина правила.
    """
    out = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        if "own" not in b:
            # У блоков прежних сборок признака нет: восстанавливаем по полке,
            # она у нас уже проставлена (местная и «своего языка» — свои)
            b = {**b, "own": b.get("scope") in ("local", "pool")}
        text = f"{b.get('title','')} {b.get('summary','')}"
        if _ETIQUETTE.search(b.get("title", "")):
            continue                      # вежливость вместо события
        # Чужой для пула текст переводим — любой, не только кыргызский.
        # 21.08 в АНГЛИЙСКОМ обзоре стояли русские абзацы от Knews.kg: прежняя
        # проверка смотрела только на кыргызские буквы в русском пуле, а
        # «чужой язык» бывает в любом пуле и любой.
        if _still_foreign(text, lang) or (lang == "ru" and _looks_kyrgyz(text)):
            t = _gtx_translate(b.get("title", ""), lang)
            sm = _gtx_translate(b.get("summary", ""), lang)
            if t and not _still_foreign(t, lang):
                b = {**b, "title": t, "summary": sm or b.get("summary", "")}
            else:
                continue        # перевести не вышло — блок в обзор не идёт
        out.append(b)
    return out


def _story_id(title: str) -> str:
    return hashlib.sha1(title.strip().lower().encode("utf-8")).hexdigest()[:10]


def _tidy_stories(stories, lang):
    """Приводит уже собранные обзоры в порядок. Денег не стоит.

    20.08: предохранитель «не пересобирать чаще раза в три часа» берёг счёт, но
    заодно держал в ленте двойного Ферстаппена и кыргызский абзац посреди
    русского сюжета. Экономить надо на запросах к ИИ, а не на чистоте.
    """
    out = []
    for st in stories:
        if not isinstance(st, dict):
            continue
        blocks = _refresh_old_blocks(st.get("blocks", []), lang)
        if len({b.get("source") for b in blocks}) < STORY_MIN_BIG:
            continue
        title = st.get("title", "")
        # Имя автоматического обзора берётся из заголовка первой новости и
        # оставалось на её языке: «Салыктарды катталган жери боюнча…» в русской
        # ленте, «Контракт Ферстаппена с Red Bull» — в испанской
        if _still_foreign(title, lang) or (lang == "ru" and _looks_kyrgyz(title)):
            title = _gtx_translate(title, lang) or title
        # Опора — ТЕМА, а не первый блок: 22.08 затравкой обзора «US-Canada
        # tariffs» стоял иск об имени Трампа, и проверка «похож ли на затравку»
        # пропускала стройку бального зала, зато выбрасывала Канаду. Испорченной
        # оказалась сама затравка.
        if blocks and title:
            anchor = max(blocks, key=lambda b: len(
                {w[:5] for w in re.findall(r"[а-яёa-zà-ú]{4,}",
                                           (b.get("title", "") + " " +
                                            str(b.get("summary", ""))[:300]).lower())}
                & {w[:5] for w in re.findall(r"[а-яёa-zà-ú]{4,}", title.lower())}))
            kept = [b for b in blocks
                    if _fits_story(b.get("title", ""), title,
                                   anchor.get("title", ""),
                                   str(anchor.get("summary", "")))]
            if len(kept) < len(blocks):
                print(f"  ✂️ Из обзора «{title[:28]}» убрано не по теме: "
                      f"{len(blocks) - len(kept)}")
            blocks = kept
        blocks = _lead_first_reporter(blocks)
        if len({b.get("source") for b in blocks}) < STORY_MIN_BIG:
            continue
        st = {**st, "title": title, "blocks": _fold_echoes(blocks)}
        twin = next((m for m in out if _same_story(st, m)), None)
        if twin is None:
            out.append(st)
            continue
        seen = {publisher_family(b.get("source", "")) for b in twin["blocks"]}
        twin["blocks"] = _lead_first_reporter(
            (twin["blocks"] + [b for b in st["blocks"]
                               if publisher_family(b.get("source", "")) not in seen]
             )[:STORY_MAX_BLOCKS])
        if len(st.get("title", "")) < len(twin.get("title", "")):
            twin["title"] = st["title"]
        print(f"  🔗 Двойники обзора схлопнуты [{lang}]: «{twin['title'][:40]}»")
    return out


def build_press_reviews(items, lang):
    """Обзоры прессы: до трёх сюжетов, каждый — событие глазами изданий.

    Сперва обзор был один на пул, и 20.08 он забрал безвиз с Китаем, а Киев и
    Трамп с угрозами остались рассыпанными по ленте. Сюжетов в дне бывает
    несколько, поэтому обзор — не карточка, а раздел.

    Мы НЕ пишем текст. ИИ выбирает темы, сценарии и роли; всё остальное —
    чужие заголовки и наши прежние выжимки.

    Обзор живёт сутки и дополняется: событие разворачивается часами, а лента
    обновляется чаще, чем приходят подробности.

    Возвращает (оставшиеся новости, список обзоров).
    """
    now = int(datetime.now().timestamp() * 1000)
    try:
        old = db.reference(f"/news/{lang}/stories").get() or []
    except Exception:
        old = []
    if not isinstance(old, list):
        old = []
    def _alive(st):
        if not isinstance(st, dict):
            return False
        if now - st.get("createdAt", 0) >= STORY_TTL_MS:
            return False
        # Пока новое не приходило — считаем от рождения
        return now - st.get("freshAt", st.get("createdAt", 0)) < STORY_STALE_MS

    retired = [st for st in old if isinstance(st, dict) and not _alive(st)]
    if retired:
        print("  🗞 Обзоры отжили [%s]: %s" % (
            lang, "; ".join(f"«{x.get('title','')[:28]}»" for x in retired)))
    old = [st for st in old if _alive(st)]
    old = _tidy_stories(old, lang)      # чистка бесплатна и идёт каждый прогон

    if len(items) < 8:
        return items, old
    # Пересобираем не чаще раза в три часа: обзор живёт сутки, а запрос стоит
    # денег. За два часа сюжет редко обрастает новым изданием
    young = any(now - st.get("freshAt", st.get("createdAt", 0)) < 2 * 3600 * 1000
                for st in old)
    if old and not young and all(
            now - st.get("updatedAt", 0) < 3 * 3600 * 1000 for st in old):
        return items, old

    lines = [f"{i+1}. [{it.get('source','?')}] {it.get('title','')}"
             for i, it in enumerate(items)]
    roles = ("затравка, дополнение, расхождение, свидетельство с места, "
             "официальная реакция, предыстория, вывод, взгляд другой стороны, "
             "отклик у нас, опровержение, деталь")
    if old:
        have = "\n".join(
            f"   [{st.get('id')}] «{st.get('title')}» — уже есть: "
            + ", ".join(f"{b.get('source')} ({b.get('role')})"
                        for b in st.get("blocks", []))
            for st in old)
        known = (f"Уже собраны обзоры:\n{have}\n\n"
                 f"Новости, относящиеся к ним, добавляй в тот же обзор, указав "
                 f"его id, и только если они добавляют НОВОЕ — подробность, "
                 f"цифру, реакцию, вывод, расхождение. Пересказ уже сказанного "
                 f"не добавляй.\n\n")
    else:
        known = ""
    prompt = (
        "Ты редактор новостного агрегатора. " + known +
        f"Найди в списке ниже темы, о которых пишут сразу НЕСКОЛЬКО РАЗНЫХ "
        f"изданий, и собери обзоры прессы. Сколько в этом выпуске настоящих "
        f"сюжетов — столько и собери: в тихий день один, в насыщенный три-"
        f"четыре. Потолок {STORY_MAX_COUNT}, но это предохранитель, а не цель. "
        f"Если подходящих тем нет, верни пустой список: лучше не собрать "
        f"обзор, чем собрать натянутый.\n\n"
        f"ЗАТРАВКА — тому, кто сообщил ПЕРВЫМ, а не тому, у кого текст длиннее "
        f"или снимок красивее. Первенство видно по времени публикации.\n"
        f"Роли: {roles}. Роль назначай, только если издание ей ДЕЙСТВИТЕЛЬНО "
        "соответствует; лишние роли не выдумывай. Одно издание — один блок.\n"
        "Блоки не должны повторять друг друга: каждый следующий добавляет то, "
        "чего в предыдущих нет.\n"
        "Сценарий выбери один: хроника, спор о фактах, разные страны, тема.\n"
        "Обзоры верни В ПОРЯДКЕ ЗНАЧИМОСТИ: сначала то, что затрагивает больше "
        "людей и сильнее — война, катастрофа, крупная политика; потом спорт, "
        "происшествия, частные темы; местные административные новости последними. "
        "Читатель видит их в этом порядке и решает по первому.\n"
        f"Заголовок темы — назывной, 2-4 слова, без утверждений, на языке "
        f"пула ({lang}): «Атака на Киев», «Attack on Kyiv», «Ataque a Kiev». "
        f"Роли называй по-русски, как в списке выше, — читатель их не увидит.\n\n"
        "Верни ТОЛЬКО JSON:\n"
        '{"stories": [{"id": "abc1234567 или пусто для новой", "title": "...", '
        '"scenario": "...", "blocks": [{"n": 3, "role": "затравка"}]}]}\n\n'
        "НОВОСТИ:\n" + "\n".join(lines))
    try:
        text = ask_gemini(prompt)
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        data = json.loads(text)
        proposed = data.get("stories") or []
    except Exception as e:
        print(f"  ⚠️ Обзоры прессы не собраны: {str(e)[:60]}")
        return items, old

    by_id = {st.get("id"): st for st in old}
    used = set()
    result = []
    for pr in proposed[:STORY_MAX_COUNT]:
        title = str(pr.get("title", "")).strip()[:60]
        target = by_id.get(str(pr.get("id") or "").strip())
        base_blocks = _refresh_old_blocks(target.get("blocks", []), lang) if target else []
        # Сравниваем СЕМЬИ изданий, а не названия: BBC News и BBC Русская
        # служба — одна редакция, и два её блока в обзоре означают ровно тот
        # однобокий пересказ, от которого обзор должен спасать
        seen = {publisher_family(b.get("source", "")) for b in base_blocks}
        fresh = []
        for b in pr.get("blocks", []):
            n = b.get("n")
            if not isinstance(n, int) or not (0 < n <= len(items)) or n - 1 in used:
                continue
            it = items[n - 1]
            fam = publisher_family(it.get("source", ""))
            if fam in seen:
                continue
            role = str(b.get("role", "")).strip()
            # Блок не о том — не берём. Затравку не проверяем: она и задаёт тему
            lead_title = (base_blocks[0].get("title", "") if base_blocks
                          else (fresh[0]["title"] if fresh else ""))
            lead_sum = (base_blocks[0].get("summary", "") if base_blocks
                        else (fresh[0]["summary"] if fresh else ""))
            if (base_blocks or fresh) and not _fits_story(
                    it.get("title", ""), title, lead_title, lead_sum):
                continue
            seen.add(fam)
            # Затравка остаётся в ленте на своей полке. Это, как правило,
            # главная новость дня; убирая её, мы обедняли «Местные» и
            # «Мировые» и рисковали: читатель, пролиставший обзор не глядя,
            # не увидел бы её вовсе. Остальные взгляды живут только в обзоре
            if not role.startswith("затравк"):
                used.add(n - 1)
            fresh.append(_story_block(it, role, lang))
        blocks = _fold_echoes(
            _lead_first_reporter((base_blocks + fresh)[:STORY_MAX_BLOCKS]))
        big = any(items[i].get("priority", 0) >= 2 for i in used) or \
              any(b.get("role", "").startswith(("расхожден", "свидетель")) for b in blocks)
        need = STORY_MIN_BIG if big else STORY_MIN_SOURCES
        if len({b["source"] for b in blocks}) < need:
            for b in fresh:                      # не сложилось — вернём в ленту
                used.discard(next(i for i, x in enumerate(items)
                                  if x.get("url") == b["url"]))
            continue
        shelf = Counter(b.get("scope") for b in blocks if b.get("scope"))
        result.append({
            "id": (target or {}).get("id") or _story_id(title or str(now)),
            "title": title or (target or {}).get("title", ""),
            "scenario": str(pr.get("scenario", "")).strip()[:40]
                        or (target or {}).get("scenario", ""),
            "scope": shelf.most_common(1)[0][0] if shelf else "world",
            "blocks": blocks,
            "createdAt": (target or {}).get("createdAt", now),
            "updatedAt": now,
            "freshAt": now if fresh else (target or {}).get("freshAt", now),
        })

    # Уцелевшие прежние обзоры, которых ИИ не назвал, оставляем жить: сюжет не
    # исчезает оттого, что за два часа о нём не написали заново
    named = {st["id"] for st in result}
    for st in old:
        if st.get("id") not in named and len(result) < STORY_MAX_COUNT:
            fixed = _refresh_old_blocks(st.get("blocks", []), lang)
            if len({b["source"] for b in fixed}) >= STORY_MIN_SOURCES:
                result.append({**st, "blocks": fixed})

    # Схлопываем двойников В ИТОГОВОМ списке, а не только при появлении.
    # 20.08 Ферстаппен висел в ленте двумя обзорами: запрет на новые дубли уже
    # работал, но эти два лежали в базе и просто переносились из прогона в
    # прогон. Правило, применённое только к новому, — половина правила.
    merged = []
    for st in result:
        twin = next((m for m in merged if _same_story(st, m)), None)
        if twin is None:
            merged.append(st)
            continue
        seen = {publisher_family(b.get("source", "")) for b in twin["blocks"]}
        add = [b for b in st.get("blocks", [])
               if publisher_family(b.get("source", "")) not in seen]
        twin["blocks"] = _lead_first_reporter(
            (twin["blocks"] + add)[:STORY_MAX_BLOCKS])
        # Имя оставляем то, что короче: длинное обычно — обрубок заголовка
        if len(st.get("title", "")) < len(twin.get("title", "")):
            twin["title"] = st["title"]
        print(f"  🔗 Двойники обзора схлопнуты [{lang}]: «{twin['title'][:40]}»")
    result = merged

    if result:
        print(f"  📰 Обзоры прессы [{lang}]: "
              + "; ".join(f"«{st['title']}» {len(st['blocks'])} изд."
                          for st in result))
    else:
        print(f"  📰 Обзоры прессы [{lang}]: подходящих тем нет")

    rest = [it for i, it in enumerate(items) if i not in used]
    return rest, result


def collapse_same_event(items, lang, stories=None):
    """Схлопывает пересказы ОДНОГО события, оставляя лучший.

    Проверка на повторы сравнивает слова заголовков — и слепа там, где слова
    разные. 20.08 в ленте стояло пять новостей о безвизовом Китае, три из них
    по-кыргызски: «Кытайга визасыз» и «безвизовый въезд в Китай» не имеют ни
    одного общего слова. Тот же случай был с интервью президента, которое
    агентства разрезали на темы.

    Словарём это не лечится: у пересказов одного события общего только смысл.
    Поэтому спрашиваем ИИ — он и так читает каждую новость.

    Осторожность троякая: просим объединять только ПОЛНЫЕ совпадения события,
    при сомнении оставлять оба; не трогаем ленту, если ИИ молчит; и никогда не
    снимаем больше пятой части — ошибка модели не должна опустошить выпуск.
    """
    if len(items) < 8:
        return items, stories if stories is not None else []
    lines = [f"{i+1}. [{it.get('source','?')}] {it.get('title','')}"
             for i, it in enumerate(items)]
    prompt = (
        "Ниже заголовки одного выпуска новостей. Найди группы, которые "
        "рассказывают об ОДНОМ И ТОМ ЖЕ событии — даже если они на разных "
        "языках или написаны разными словами.\n\n"
        "ВАЖНО:\n"
        "· Объединяй, только если событие буквально одно. Разные решения, "
        "разные сроки, разные страны — это РАЗНЫЕ события.\n"
        "· «30 дней на Хайнане» и «10 дней в Китае» — разные события.\n"
        "· Сомневаешься — не объединяй.\n"
        "· Разные темы одного интервью или заседания — одно событие.\n\n"
        "Верни ТОЛЬКО JSON: список групп, каждая группа — список номеров. "
        "Одиночные новости не включай. Пример: [[3,17],[8,9,25]]\n\n"
        + "\n".join(lines))
    try:
        text = ask_gemini(prompt)
        if "```" in text:
            text = text.split("```")[1].replace("json", "").strip()
        groups = json.loads(text)
        if not isinstance(groups, list):
            return items, stories if stories is not None else []
    except Exception as e:
        print(f"  ⚠️ Группировка по событиям не удалась: {str(e)[:60]}")
        return items, stories if stories is not None else []

    # Повтор на ДВУХ ЯЗЫКАХ — не повтор. Одна и та же новость по-русски и
    # по-кыргызски служит разным читателям, и в двуязычной стране это скорее
    # достоинство ленты. Поэтому в группе оставляем лучшую НА КАЖДОМ ЯЗЫКЕ.
    #
    # Поле language здесь бесполезно: все три кыргызские заметки о безвизовом
    # Китае помечены русскими. Смотрим на буквы, которых в русском нет.
    def _lang_of(it):
        head = f"{it.get('title','')} {str(it.get('summary',''))[:200]}".lower()
        if any(c in head for c in "өүң"):
            return "ky"
        return (it.get("language") or "?").lower()

    stories = stories if stories is not None else []
    drop = set()
    for g in groups:
        idxs = [n - 1 for n in g if isinstance(n, int) and 0 < n <= len(items)]
        if len(idxs) < 2:
            continue
        # Похожие новости не выбрасываем, а СОБИРАЕМ. Если об одном событии
        # написали три разные редакции — это готовый обзор прессы, и удалять
        # две из трёх значит терять то самое сравнение взглядов, ради которого
        # обзор и затевался. Роли здесь простые, без ИИ: лучший рассказ —
        # затравка, остальные дополняют.
        fams = {}
        for i in idxs:
            fams.setdefault(publisher_family(items[i].get("source", "")), []).append(i)
        if len(fams) >= STORY_MIN_SOURCES and len(stories) < STORY_MAX_COUNT:
            probe = {"title": str(items[idxs[0]].get("title", "")),
                     "blocks": [{"url": items[i].get("url", "")} for i in idxs]}
            if any(_same_story(probe, st) for st in stories):
                continue        # об этом сюжете обзор уже есть
            picked = [max(v, key=lambda i: (
                items[i].get("priority", 0),
                1 if items[i].get("imageUrl") else 0,
                len(items[i].get("summary") or ""),
            )) for v in fams.values()]
            picked.sort(key=lambda i: (
                items[i].get("priority", 0),
                1 if items[i].get("imageUrl") else 0,
                len(items[i].get("summary") or ""),
            ), reverse=True)
            picked = picked[:STORY_MAX_BLOCKS]
            # Первым сообщивший — первым и стоит: заслуга в том, чтобы добыть
            # новость, а не в том, чтобы полнее её пересказать
            picked.sort(key=lambda i: items[i].get("publishedAt") or 0)
            # Имя обзору даём из заголовка лучшей новости, но режем ПО СЛОВАМ:
            # «Ферстаппен продлил контракт с Red Bull д» — обрубок, а не имя
            head = str(items[picked[0]].get("title", ""))
            if _still_foreign(head, lang) or (lang == "ru" and _looks_kyrgyz(head)):
                head = _gtx_translate(head, lang) or head
            if len(head) > 52:
                head = head[:52].rsplit(" ", 1)[0].rstrip(" ,:;—-") + "…"
            title = head
            now_ms = int(datetime.now().timestamp() * 1000)
            shelf = Counter(items[i].get("scope") for i in picked
                            if items[i].get("scope"))
            stories.append({
                "id": _story_id(title),
                "title": title,
                "scenario": "тема",
                "scope": shelf.most_common(1)[0][0] if shelf else "world",
                "blocks": [_story_block(items[i],
                                        "затравка" if k == 0 else "дополнение",
                                        lang)
                           for k, i in enumerate(picked)],
                "createdAt": now_ms,
                "updatedAt": now_ms,
                "freshAt": now_ms,
            })
            print(f"  📰 Похожие собраны в обзор [{lang}]: «{title[:40]}» "
                  f"— {len(picked)} изданий")
            # Лучший остаётся в ленте — он и есть затравка обзора
            drop.update(i for i in idxs if i != picked[0])
            continue
        by_lang = {}
        for i in idxs:
            by_lang.setdefault(_lang_of(items[i]), []).append(i)
        for same_lang in by_lang.values():
            best = max(same_lang, key=lambda i: (
                items[i].get("priority", 0),
                1 if items[i].get("imageUrl") else 0,
                len(items[i].get("summary") or ""),
            ))
            drop.update(i for i in same_lang if i != best)
    if len(drop) > len(items) // 3:
        print(f"  ⚠️ ИИ предложил снять {len(drop)} из {len(items)} — "
              f"слишком много, оставляем ленту как есть")
        return items, stories
    if drop:
        print(f"  🔗 Пересказы одного события [{lang}]: убрано из ленты {len(drop)}")
    return [it for i, it in enumerate(items) if i not in drop], stories


URGENT_MAX = 2                      # больше двух «срочно» разом — это шум
URGENT_MAX_AGE_MS = 3 * 3600 * 1000  # старше трёх часов будить поздно


# Разбор, объяснение и прейскурант срочными не бывают никогда. 22.08 читателя
# разбудило «Мост слишком далеко? Почему связь с Сицилией остаётся мечтой» и
# «Определены цены на билеты на закрытие Игр кочевников».
_NEVER_URGENT = re.compile(
    # Вопрос в заголовке — где угодно, а не только в конце: «Мост слишком
    # далеко? Почему связь с Сицилией остаётся мечтой»
    # «как» намеренно нет: «Как сообщает МЧС, сошёл сель» — обычный зачин
    # новости, а не разбор
    r"\?|\bпочему\b|\bзачем\b|^что известно|^что значит"
    r"|определены цены|сколько стоит|прейскурант|цены на билеты"
    r"|^why\b|^how\b|^what\b|ticket prices|price list"
    r"|^por qué|^cómo|precios de|^porque|^como|preços", re.I)


# Страны языкового пространства каждого пула. Издание соседней страны, пишущее
# о своей стране, — это полка «своего языка», а не «мировые»: 22.08 новость
# Kun.uz об институте цифровой безопасности в Узбекистане стояла среди мировых.
POOL_COUNTRIES = {
    "ru": {"KZ", "UZ", "TJ", "RU", "UA", "BY", "AM", "AZ", "GE", "MD", "TM"},
    "en": {"GB", "IE", "CA", "AU", "NZ", "IN", "NG", "ZA", "JM", "SG"},
    "es": {"ES", "AR", "CO", "PE", "CL", "EC", "VE", "GT", "CR", "SV", "DO", "UY", "PY", "BO", "PA", "HN", "NI", "CU"},
    "pt": {"PT", "AO", "MZ", "CV", "GW", "ST", "TL"},
    "fr": {"BE", "CH", "CA", "SN", "CI", "MA", "TN", "DZ", "CD", "CM", "ML",
           "BF", "NE", "GN", "TG", "BJ", "MG", "HT", "LU", "MC"},
}

# Городская повседневность: отключения, перекрытия, ремонты. ИИ иногда метит
# их спортом или деньгами, и читатель видит трофей вместо новости о дороге
_UTILITY = re.compile(
    r"ограничен\w* движени|перекр\w+ (?:движени|улиц|дорог)|отключ\w+ (?:свет|вод|газ|электро)"
    r"|ремонт (?:дорог|улиц|моста)|movimiento restringido|corte de (?:agua|luz)"
    r"|road closure|traffic restriction|water outage|power outage", re.I)


# Как страна называется в новости — на языках наших пулов
_COUNTRY_WORDS = {
    "KZ": ("казахстан", "kazakh", "kazajistán", "cazaquistão"),
    "UZ": ("узбекистан", "uzbek", "uzbekistán", "uzbequistão"),
    "TJ": ("таджикистан", "tajik", "tayikistán", "tajiquistão"),
    "RU": ("росси", "russia", "rusia", "rússia"),
    "UA": ("украин", "ukrain", "ucrania", "ucrânia"),
    "GB": ("британ", "britain", "british", "uk ", "англи", "reino unido"),
    "IE": ("ирланди", "ireland", "irish", "irlanda"),
    "CA": ("канад", "canada", "canadian", "canadá"),
    "AU": ("австрали", "australia", "australian"),
    "IN": ("инди", "india", "indian"),
    "NG": ("нигери", "nigeria", "nigerian"),
    "ZA": ("южной африк", "south africa"),
    "SG": ("сингапур", "singapore"),
    "ES": ("испани", "spain", "spanish", "españa"),
    "AR": ("аргентин", "argentina", "argentino"),
    "CO": ("колумби", "colombia"),
    "PE": ("перу", "peru", "perú"),
    "CL": ("чили", "chile"),
    "MX": ("мексик", "mexico", "méxico"),
    "PT": ("португал", "portugal", "português"),
    "BR": ("бразил", "brazil", "brasil"),
    "AO": ("ангол", "angola"),
    "MZ": ("мозамбик", "moçambique", "mozambique"),
}


def _mentions_country(text: str, code: str) -> bool:
    words = _COUNTRY_WORDS.get(code)
    if not words:
        return True          # страны не знаем — ведём себя как прежде
    low = text.lower()
    return any(w in low for w in words)


def fix_scope_and_category(items, lang):
    """Правит две ошибки разметки, которые видит читатель.

    Полка: издание соседней страны о своей стране — «свой язык», не «мир».
    Категория: перекрытая улица — не спорт, каким бы ни было решение ИИ.
    """
    space = POOL_COUNTRIES.get(lang, set())
    moved = recat = 0
    for x in items:
        country = x.get("country") or ""
        head = f"{x.get('title','')} {str(x.get('summary',''))[:200]}"
        # Понижаем, только если новость О САМОЙ этой стране. Прежнее правило
        # переводило в «свои» ЛЮБУЮ заметку издания из языкового пространства,
        # и BBC про Газу становилась британской новостью: в английском пуле
        # мировых осталось двенадцать из двадцати с лишним
        if (x.get("scope") == "world" and country and country in space
                and _mentions_country(head, country)):
            x["scope"] = "pool"
            moved += 1
        head = f"{x.get('title','')} {str(x.get('summary',''))[:120]}"
        if _UTILITY.search(head) and x.get("category") in ("SPORT", "STARS", "TECH", "MONEY", "CULTURE"):
            x["category"] = "KG" if x.get("scope") == "local" else "NEWS"
            recat += 1
    if moved or recat:
        print(f"  📐 Разметка [{lang}]: полка исправлена у {moved}, "
              f"категория у {recat}")
    return items


def cap_urgent(items, lang):
    """Оставляет не больше двух срочных, и только свежие.

    21.08 в английской ленте висело пять «срочно», среди них — отчёт о
    прошлогоднем взрыве и сообщение семичасовой давности. Метка, которой врут,
    перестаёт работать тогда, когда беда настоящая.

    Порядок отбора: сначала своё (местное ближе, чем чужое), потом свежее.
    Снятые с «срочно» из ленты не исчезают — просто перестают будить.
    """
    now = int(datetime.now().timestamp() * 1000)
    urgent = [x for x in items if x.get("category") in ("URGENT", "URGENT_LOCAL_ONLY")]
    if not urgent:
        return items
    # Сначала снимаем то, что срочным не бывает по природе: вопрос в
    # заголовке — это разбор, «определены цены» — это справка
    natural = 0
    for x in list(urgent):
        if _NEVER_URGENT.search(str(x.get("title", "")).strip()):
            x["category"] = "NEWS"
            urgent.remove(x)
            natural += 1
    if natural:
        print(f"  🔕 Не срочные по природе [{lang}]: {natural} "
              f"(вопрос в заголовке, цены, разбор)")
    if not urgent:
        return items
    shelf_rank = {"local": 0, "pool": 1, "world": 2}
    keep = sorted(
        [x for x in urgent if now - x.get("publishedAt", 0) <= URGENT_MAX_AGE_MS],
        key=lambda x: (shelf_rank.get(x.get("scope"), 3), -x.get("publishedAt", 0)),
    )[:URGENT_MAX]
    kept_urls = {x.get("url") for x in keep}
    demoted = 0
    for x in urgent:
        if x.get("url") not in kept_urls:
            x["category"] = "NEWS"
            demoted += 1
    if demoted:
        print(f"  🔕 Срочность снята [{lang}]: {demoted}, осталось {len(keep)}")
    return items


# Подписи к фотографиям, кредиты и телеграфные зачины. Читатель открывает
# новость, а первая строка — «Прицеп с мустангами перевозят во временный
# загон» или «Madrid, 21 ago (EFE).-». Это не начало новости, это служебное:
# издание подписывает снимок и помечает, чьё агентство. 21.08.2026 нашлось во
# всех четырёх пулах разом, в русском — переведённое, отчего ещё нелепее.
# Подписи к фотографиям, кредиты и телеграфные зачины. Читатель открывает
# новость, а первая строка — «Прицеп с мустангами перевозят во временный
# загон» или «Madrid, 21 ago (EFE).-». Это не начало новости, это служебное:
# издание подписывает снимок и помечает, чьё агентство. 21.08.2026 нашлось во
# всех четырёх пулах разом, в русском — переведённое, отчего ещё нелепее.
_DATELINE = [
    re.compile(r"^[A-Za-zА-Яа-я]{3,4}\.?\s*\d{1,2}\s*\([A-ZА-Я]{2,8}\)\s*-{1,2}\s*"),   # Aug. 21 (UPI) --
    re.compile(r"^[A-ZА-ЯÁÉÍÓÚÑÂÃÊÔÇ][\w\s.'-]{0,32},\s*\d{1,2}\s*[а-яa-zÁ-ú.]{3,12}\.?\s*\([A-ZА-Я]{2,8}\)\.?\s*-{0,2}\s*", re.U),
    re.compile(r"^[A-ZА-Я][\w\s.'-]{0,32},\s*\d[\d.]{0,9}\s*/[^/]{2,12}/\.?\s*"),        # Бишкек, 21.08.26 /Кабар/.
    re.compile(r"^Redacci[oó]n[^,]{0,20},\s*\d{1,2}\s*\w{3,10}\s*\([A-Z]{2,8}\)\.?-?\s*", re.I),
]
# Приметы подписи под снимком и кредита автора
_CREDIT = re.compile(
    r"Getty Images|Europa Press|Divulgação|/AFP|/EFE|/Reuters|\(Photo|\(Foto|\(Фото"
    r"|Photo by|Foto:|Фото:|Axios Visuals|Chart:|^Data:"
    r"|This article originally appeared|Esta nota apareci[oó] originalmente"
    # Подписка на рассылку и анонс вещания вместо новости: The Independent
    # начинал текст с «Я хотел бы получать по электронной почте информацию о
    # предложениях», BBC Sport — с расписания эфира
    r"|хотел бы получать по электронной почте|уведомление о конфиденциальности"
    r"|Sign up to our|newsletter|Прочтите наше уведомление"
    r"|будет доступно на BBC|will be available on BBC|каждую субботу в \d", re.I)


# Подпись под снимком без слова «фото»: «Брэди О'Рурк держит табличку…»,
# «Прицеп с мустангами перевозят во временный загон…». Узнаётся по глаголам,
# которыми подписывают кадр: человек на снимке что-то делает прямо сейчас.
# Список нарочно узкий и применяется ТОЛЬКО к первой фразе — чтобы не съесть
# настоящее начало новости.
_CAPTION_VERBS = re.compile(
    r"\b(?:holds? a sign|is transported|are transported|is seen|are seen|seen here"
    r"|pictured|poses? for|walks? past|stands? near|attends? a|speaks? during"
    r"|держит|перевозят|запечатлён|на снимке|позирует)\b", re.I)


def _sentences(t: str):
    """Грубое деление на предложения — точка после слова, а не в сокращении."""
    out, last = [], 0
    for m in re.finditer(r"[а-яёa-zà-ú\d]{2,}[.!?]\s+", t + " "):
        out.append(t[last:m.end()].strip())
        last = m.end()
    if t[last:].strip():
        out.append(t[last:].strip())
    return [x for x in out if x]


_HANGING_WORDS = {
    "и", "а", "но", "или", "что", "как", "для", "при", "над", "под", "из", "за",
    "на", "в", "с", "о", "у", "к", "по", "the", "of", "and", "for", "with",
    "from", "that", "de", "la", "el", "los", "las", "del", "que", "em", "no",
    "na", "do", "da", "dos", "das",
}


def polish_summary(text: str) -> str:
    """Снимает служебное начало и не оставляет фразу оборванной."""
    t = (text or "").strip()
    if not t:
        return t
    for _ in range(3):                      # зачин бывает двойным
        before = t
        for rx in _DATELINE:
            t = rx.sub("", t, count=1)
        t = t.strip(" —-–·|")
        if t == before:
            break
    # Первые предложения, в которых сидит кредит или подпись, выбрасываем
    # целиком: убрать одни скобки мало — «Вид на завод, 20 марта 2024 года»
    # остаётся подписью, а не новостью
    # Служебная строка без точки в конце — снимаем прямо куском
    t = re.sub(r"^Data:[^;]{0,60};\s*Chart:[^\n]{0,80}?Visuals\s*", "", t, flags=re.I)
    parts = _sentences(t)
    # Кредит бывает не в первом предложении, а во втором: сначала подпись
    # «Вид на завод, 20 марта 2024 года», и лишь потом «(Фото Getty Images)».
    # Ищем среди первых трёх и отрезаем всё по последнее найденное включительно
    cut = 0
    for i, part in enumerate(parts[:3]):
        if _CREDIT.search(part):
            cut = i + 1
    if not cut and len(parts) > 1 and len(parts[0]) < 220 and _CAPTION_VERBS.search(parts[0]):
        cut = 1
    if cut and cut < len(parts):
        parts = parts[cut:]
    t = re.sub(r"\s{2,}", " ", " ".join(parts)).strip()
    # Зазывалки в конце: «Подробности от Kaktus.media», «Читать далее»
    t = re.sub(r"[.\s]*(?:Подробности(?:\s+\w+){0,3}|Читать далее|Подробнее"
               r"|Read more|Leia mais|Leer más)\s*[.:…]*\s*$", "", t, flags=re.I).strip()
    # Оборванная на полуслове фраза: возвращаемся к последнему целому
    # предложению. Издания обрезают описания по своим правилам, не по нашим
    if t and t[-1] not in ".!?…»\"'":
        ends = [m.end() - 1 for m in re.finditer(r"[а-яёa-zà-ú]{3,}[.!?]\s", t + " ")]
        last = t.split()[-1] if t.split() else ""
        # Настоящий обрыв виден по хвосту: одна буква, инициал или предлог —
        # «…inside the Edward J». А Kaktus просто не ставит точку в конце
        # законченной фразы, и рубить её незачем — довольно точки
        dangling = (len(last.strip(".,")) <= 2
                    or last.lower() in _HANGING_WORDS)
        if dangling and ends and ends[-1] >= 80:
            t = t[:ends[-1] + 1]
        elif not dangling:
            t += "."
    return t.strip()


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

        # 1а. Издание само пометило материал рекламой («на правах рекламы»,
        #     маркировка erid). Спорить тут не о чем: это оплаченное
        #     размещение, а не новость
        if item.get("url") in AD_PAGES:
            dropped.append((item, "издание помечает материал рекламой"))
            continue

        # 1г. Ежедневный корм ради поиска: подсказки к играм, гороскопы
        if _is_daily_filler(title) or _is_daily_filler(item.get("origTitle") or ""):
            dropped.append((item, "подсказки к игре или гороскоп — не новость"))
            continue

        # 1в. Погода и коммунальные сводки: события нет, есть состояние
        if QC_WEATHER.search(title) or QC_WEATHER.search((item.get("origTitle") or "")):
            dropped.append((item, "погода — не новость"))
            continue

        # 1б. Подпись к видеонарезке вместо новости.
        #
        # Заголовок обещает событие («Уильямс проиграла Аранго»), а в тексте —
        # «Лучшие моменты матча»: это подпись к ролику, а не новость. Читать
        # нечего, смотреть у нас негде. У Sky Sports таких девять из двадцати,
        # но правило общее: так делают все спортивные ленты
        # Смотрим и на перевод, и на ОРИГИНАЛ. Перевод каждый раз чуть другой
        # («Highlights of the Super League game» стало «Lo destacado del
        # partido» — без «más», и правило промахнулось), а оригинал постоянен
        orig_body = (item.get("origSummary") or "").strip()
        if QC_VIDEO_CAPTION.match(body.strip()) or QC_VIDEO_CAPTION.match(orig_body):
            dropped.append((item, "подпись к видеонарезке вместо новости"))
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

        # 4. Заголовок, продублированный первой строкой текста.
        #    Прежде здесь сравнивались первые СОРОК знаков заголовка, а
        #    срезалась ВСЯ его длина — и нож уходил в живое, как только текст
        #    после сороковой буквы расходился с заголовком. См. strip_title_echo
        _echo = strip_title_echo(title, body)
        if _echo != body:
            body = _echo
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
    # Firebase отдаёт СПИСОК вместо словаря, когда ключи оказываются подряд
    # идущими числами. 22.08 на этом рухнул весь прогон: «list object has no
    # attribute items», и пулы после упавшего не собрались вовсе
    if isinstance(all_messages, list):
        all_messages = {str(i): v for i, v in enumerate(all_messages) if v}
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


# Свежесть, при которой прогон считает работу уже сделанной. Меньше
# REFRESH_MINUTES, иначе второй запуск часа никогда не сработает
FRESH_ENOUGH_MIN = 40


def _feed_is_fresh() -> bool:
    """Лента обновлялась только что — работать незачем.

    Нужно из-за того, что расписание GitHub Actions ненадёжно. Замер
    27.08.2026 по 38 плановым прогонам: медиана промежутка 59 минут, но пять
    разрывов больше полутора часов и один в 5 часов 14 минут. Ночью запуски
    просто не состоялись — лента стояла девять часов, хотя читателю мы
    обещаем обновление каждый час.

    Лечение: два запуска в час вместо одного. Пропустит GitHub первый —
    сработает второй. А чтобы не платить дважды, когда оба состоялись, и
    стоит эта проверка: второй прогон видит свежую ленту и выходит, потратив
    несколько запросов к базе.
    """
    if os.environ.get("FORCE_RUN") == "true":
        return False          # ручной запуск делает работу всегда
    try:
        ts = db.reference("/news/ru/updatedAt").get() or 0
        age_min = (datetime.now().timestamp() * 1000 - ts) / 60000
    except Exception:
        return False          # не смогли узнать — работаем, это дешевле ошибки
    if age_min < FRESH_ENOUGH_MIN:
        print(f"⏭ Лента обновлялась {age_min:.0f} мин назад — пропускаем прогон "
              f"(порог {FRESH_ENOUGH_MIN} мин). Это второй запуск часа, "
              f"он нужен на случай, если первый не состоялся")
        return True
    return False


def main():
    print("🚀 Ticker247 Backend — Fetching news...")

    if _feed_is_fresh():
        return

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
    # Сбор видео остановлен 19.08.2026: в приложении раздел убран, метод
    # fetchViral() остался без единого вызова — сервер каждый час ходил в
    # YouTube за роликами, которых никто не увидит. Тратились квота YouTube
    # и минуты Actions.
    #
    # Пишем пустые списки — и Firebase такие узлы удаляет совсем (проверено:
    # в /viral остались только live, radio и updatedAt). Для старых версий
    # приложения это то же самое, что пустой раздел: они увидят пустоту, а не
    # позавчерашние ролики.
    #
    # Прямые эфиры и радио собираются по-прежнему: они лежат в том же узле
    # /viral и приложением читаются.
    ru_local = ru_world = en_local = en_world = []
    es_local = es_world = pt_local = pt_world = []

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

    # Запись «вирусного» обёрнута попыткой намеренно: 19.08.2026 Firebase
    # ответил Internal server error, исключение вышло наружу — и весь сбор
    # новостей оборвался на второстепенном разделе. Видео, эфиры и радио
    # приятны, но новости важнее: не записалось — идём дальше, в приложении
    # останется прошлая выдача, а лента обновится.
    viral_ref = db.reference("/viral")
    viral_payload = {
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
    }
    for attempt in (1, 2, 3):
        try:
            viral_ref.set(viral_payload)
            break
        except Exception as e:
            if attempt == 3:
                print(f"  ⚠️ Раздел «вирусное» не записан ({str(e)[:60]}) — "
                      f"новости собираем дальше")
            else:
                time.sleep(3 * attempt)
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
            # Второй взгляд должен что-то ДОБАВЛЯТЬ. Правило про несколько
            # версий события задумано ради разных ракурсов, но оно не
            # спрашивало, чем именно второй лучше, — и рядом с полной заметкой
            # вставала куцая, без снимка. Читатель видит не два взгляда, а одно
            # и то же дважды, причём второй раз пустее (19.08: мужчина с
            # младенцем просил деньги в мечети — дважды, одна без фото).
            # Первый в списке уже лучший: сортировка выше ставит вперёд
            # важность, снимок и длину текста.
            if chosen and (not it.get("imageUrl")
                           or len(it.get("summary") or "") < 200):
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
    all_news = drop_bilingual_twins(all_news)

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

    load_ai_spend()
    load_ai_cache()
    load_page_bodies()
    load_translations()
    print("🤖 Фильтруем через Gemini AI...")

    # Мировые новости (scope=world) идут во ВСЕ пулы.
    # Локальные (scope=local) — только в пул по языку статьи.
    CYRILLIC_LANGS = {"ru", "ky", "uk", "be", "bg", "sr", "mk"}
    # Пулы берём из ACTIVE_POOLS, а не перечисляем здесь: 22.08 французские
    # источники уже работали, а лента не собиралась — статьи Le Monde уходили
    # в английский пул, потому что этот словарь про французский не знал
    lang_groups = {pool: [] for pool in ACTIVE_POOLS}
    ALL_POOLS = list(lang_groups.keys())

    # Приметы «своих за границей»: слова, по которым чужая местная новость
    # может оказаться новостью про нашего читателя. Ищем на всех языках сразу —
    # статья написана на языке своего источника, а не нашего пула
    # Ищем ЛЮДЕЙ, а не страну: упоминание государства встречается в каждой
    # второй мировой новости, и по нему мост тащил бы что попало. Связь должна
    # быть в гражданах — «киргизстанец», «американец», «гражданин США»
    BRIDGE_MARKERS = {
        # Для маленькой страны само упоминание уже сигнал: «Кыргызстан» в
        # американской или бразильской заметке случайно не появляется. Для
        # больших (США, Мексика, Бразилия) так нельзя — там нужны слова про
        # людей, иначе мост потащит любую мировую новость
        "ru": ("kyrgyz", "kirghiz", "kyrgyzstan", "bishkek",
               "quirguiz", "kirguis", "kirguís", "kirghizistan"),
        "en": ("американец", "американка", "американцы", "гражданин сша",
               "гражданка сша", "citizen of the united states",
               "estadounidense", "ciudadano estadounidense",
               "cidadão americano", "norte-americano"),
        "es": ("мексиканец", "мексиканка", "гражданин мексики", "mexican national",
               "mexican citizen", "ciudadano mexicano", "cidadão mexicano"),
        "pt": ("бразилец", "бразильянка", "гражданин бразилии", "brazilian national",
               "brazilian citizen", "ciudadano brasileño", "cidadão brasileiro"),
    }
    bridged = 0

    for item in all_news:
        detected_lang = item.get("language", "unknown")
        source_lang   = item.get("source_lang")   # явный язык источника (en/es/pt/ru)
        scope         = item.get("scope", "world")

        # МОСТ: чужая местная новость, где участники — граждане другой страны
        # пула. Пример пользователя: киргизстанец на грузовике выехал на
        # встречную в США — американский репортаж об этом ценнее пересказа
        # местного издания, потому что подробности там из первых рук. Работает
        # в обе стороны и для всех пулов.
        #
        # Без этой врезки правило в промпте было бы мёртвым: местные новости
        # уходят ТОЛЬКО в пул своего языка, и ИИ русского пула никогда бы не
        # увидел американскую заметку. Мы лишь ДОСТАВЛЯЕМ кандидата — решает
        # по-прежнему ИИ, он же поставит полку и приоритет
        if scope != "world":
            hay = (item.get("title", "") + " " + item.get("summary", "")[:300]).lower()
            # В свой же пул новость не «перевозим»: она туда попадёт обычным
            # путём ниже. Прежняя проверка смотрела на source_lang, а он есть
            # не у всех источников — и киргизстанские новости приезжали в
            # русский пул вторым экземпляром
            own = source_lang if source_lang in lang_groups else (
                "ru" if detected_lang in CYRILLIC_LANGS else
                "es" if detected_lang == "es" else
                "pt" if detected_lang == "pt" else "en")
            for target, markers in BRIDGE_MARKERS.items():
                if target == own or bridged >= 20:
                    continue
                if any(m in hay for m in markers):
                    # Помечаем перевезённую копию: в приложении такая новость
                    # получает метку «наши за границей». Родственник, ищущий
                    # вести о своих, не должен выуживать её из общей ленты
                    crossed = dict(item)
                    crossed["bridge"] = True
                    lang_groups[target].append(crossed)
                    bridged += 1
                    print(f"  🌉 [{target}] мост: {item.get('title','')[:60]}")
                    break

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
            elif detected_lang == "fr" and "fr" in lang_groups:
                lang_groups["fr"].append(item)
            else:
                lang_groups["en"].append(item)

    ts = int(datetime.now().timestamp() * 1000)
    all_filtered = []

    for lang, group in lang_groups.items():
        if not group:
            continue
        print(f"\n🌐 [{lang.upper()}] {len(group)} статей → Gemini...")

        # ЭТАП 1 — здесь, а не внутри filter_with_gemini: та зовётся порциями
        # по 80, и порция отсева никогда не набралась бы до своих 120
        # Слепок ДО отсева: в боевом режиме _cull_chunk_loop уже удаляет, и
        # снятый после него слепок не содержал бы выброшенного — сверка
        # показывала бы ноль расхождений всегда
        cull_input = list(group)
        group = _cull_chunk_loop(group, lang)

        filtered = []
        for i in range(0, len(group), 80):
            batch = group[i:i+80]
            filtered_batch = filter_with_gemini(batch, lang)
            filtered.extend(filtered_batch)
        # Куда деваются новости домашних изданий. В испанском пуле мексиканские
        # газеты дают два десятка статей, а до ленты доходит десяток — потери
        # надо видеть поимённо, иначе лечим вслепую
        home_in = Counter(x.get("source", "?") for x in group if _is_home_source(x, lang))
        home_out = Counter(x.get("source", "?") for x in filtered if _is_home_source(x, lang))
        if home_in:
            parts = [f"{s} {home_out.get(s,0)}/{n}" for s, n in home_in.most_common()]
            print(f"  🏠 Домашние издания [{lang}] (прошло/пришло): " + ", ".join(parts))
        # Удаляем новости старше 90 дней (требование Google Play News policy)
        cutoff = (datetime.now().timestamp() - 30 * 24 * 3600) * 1000
        filtered = [x for x in filtered if x.get("publishedAt", 0) >= cutoff]
        # Новость без снимка берём только если она срочная или важная — либо
        # если без неё не набирается лента. Третьего не дано: карточка с
        # эмодзи вместо фотографии выглядит как недогруженная страница, и
        # читатель винит приложение, а не издание.
        #
        # Правило не запрет, а очередь: безфотографийные встают в хвост своей
        # полки и попадают в эфир, когда впереди никого не осталось.
        def _rank(x):
            worthy = (x.get("priority", 0) >= 2
                      or x.get("category") in ("URGENT", "URGENT_LOCAL_ONLY")
                      or bool(x.get("imageUrl")))
            return (x.get("priority", 0), 1 if worthy else 0)
        filtered.sort(key=_rank, reverse=True)
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
        # Куда деваются местные новости. Мексиканские издания дают на входе 24
        # статьи, а до ленты доходят 7 — без этого разбора шаг потерь не найти
        def _shelves(items):
            c = Counter(x.get("scope", "?") for x in items)
            return f"местных {c.get('local',0)}, своего языка {c.get('pool',0)}, мировых {c.get('world',0)}"
        before = _shelves(filtered)
        # Бронь для своих полок.
        #
        # Отсечка до max_items шла строго по весу издания и полку не замечала.
        # Крупные мировые издания вытесняли местные новости: 19.08 в английском
        # пуле после отбора было 48 местных, а в ленту попал 21 — 27 своих
        # новостей выброшено ради мировых, которые читатель прочтёт где угодно.
        # Это прямо противоречит нашей же политике: «местная ценнее мировой».
        #
        # Даём местным 40% ленты, языковому пространству 20%, остальное
        # разыгрывается по важности между всеми. Это не квота, а ПОЛ: если
        # местных мало (испанский пул — их десяток), никто не простаивает,
        # свободные места забирают мировые, как и раньше.
        # Пол нужен КАЖДОЙ полке, а не только местной: на проверке бронь для
        # своих оставила английскому пулу восемь мировых новостей из тридцати
        # восьми. Читатель приходит и за миром тоже — «Тикер 24/7» обещает три
        # уровня, а не один. Сумма полов меньше ленты: остаток разыгрывается по
        # важности, и там, где своих новостей много, они его и заберут.
        floors = {"local": int(max_items * 0.40),
                  "pool": int(max_items * 0.20),
                  "world": int(max_items * 0.30)}
        chosen, taken = [], set()
        for shelf, floor in floors.items():
            for x in capped:
                if len(chosen) >= max_items:
                    break
                if x.get("scope") == shelf and id(x) not in taken \
                        and sum(1 for c in chosen if c.get("scope") == shelf) < floor:
                    chosen.append(x)
                    taken.add(id(x))
        for x in capped:                      # остаток — по важности, как раньше
            if len(chosen) >= max_items:
                break
            if id(x) not in taken:
                chosen.append(x)
                taken.add(id(x))
        filtered = chosen
        print(f"  📚 Полки [{lang}]: после ИИ — {before}; "
              f"после отсечки до {max_items} — {_shelves(filtered)}")
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
            # Не переведённое в эфир не идёт. Полагаться на то, что их отсеет
            # приложение, нельзя: узбекский и казахский пишутся латиницей и
            # проходят его проверку алфавита насквозь — читатель видел в
            # русской ленте «Prezident «Urganch – Xiva» pulli avtomobil...».
            # Лучше лента короче на несколько новостей, чем со строкой,
            # которую невозможно прочесть.
            stuck = [x for x in filtered if needs_translation(x, lang)]
            if stuck:
                langs = Counter(x.get("language", "?") for x in stuck)
                print(f"  🚫 Без перевода — снято с эфира: {len(stuck)} "
                      + "(" + ", ".join(f"{k}×{v}" for k, v in langs.most_common()) + ")")
                filtered = [x for x in filtered if x not in stuck]
        cats = {}
        for item in filtered:
            cats[item["category"]] = cats.get(item["category"], 0) + 1
        print(f"  После AI: {len(filtered)} | {cats}")
        # Последний рубеж перед эфиром: чиним что можно, снимаем что нельзя
        # Чистка текста: телеграфные зачины, подписи под снимками, кредиты
        # фотографов и оборванные на полуслове фразы. Треть ленты кончалась
        # многоточием в никуда, а начиналась подписью к фотографии
        for _x in filtered:
            _x["summary"] = polish_summary(_x.get("summary", ""))
        filtered = quality_gate(filtered, lang)
        # Сверяем ЗДЕСЬ, а не перед записью в базу: дальше ленту режет
        # ограничение по объёму (80 новостей на пул), и снятое им — не
        # мусор, а просто лишнее. Считать его пропуском этапа 1 нечестно
        _cull_dry_report(cull_input, filtered, lang)
        # Порог срочности: не больше двух и только свежие
        filtered = cap_urgent(filtered, lang)
        filtered = fix_scope_and_category(filtered, lang)
        # Обзор прессы собираем ДО схлопывания повторов: он и живёт тем, что
        # об одном событии написали несколько изданий. Сначала выбросить все
        # версии кроме лучшей, а потом просить обзор — как и вышло 20.08 —
        # значит просить его из пустоты
        filtered, stories = build_press_reviews(filtered, lang)
        # Пересказы одного события — их не видит проверка по словам
        filtered, stories = collapse_same_event(filtered, lang, stories)
        # Тяжёлый снимок под размытие: спрашиваем ИИ о самой
        # фотографии, но только у новостей про происшествия
        mark_graphic_photos(filtered, lang)
        payload = {
            "items": filtered,
            "updatedAt": ts,
            "count": len(filtered),
        }
        if stories:
            payload["stories"] = stories
        db.reference(f"/news/{lang}").set(payload)
        print(f"  ✅ /news/{lang} сохранено")
        all_filtered.extend(filtered)

        # Постим в языковой Telegram-канал — каждый пул в свой
        channel = TELEGRAM_CHANNELS.get(lang)
        if channel:
            print(f"📤 Постим [{lang}] в {channel}...")
            try:
                post_to_telegram(filtered, channel=channel, lang=lang)
            except Exception as e:
                # Телеграм — витрина, а не лента. Его сбой не должен уносить
                # с собой сбор новостей: 22.08 ошибка в архиве канала оборвала
                # прогон, и пулы после испанского остались вчерашними
                print(f"  ⚠️ Телеграм [{lang}] не отработал: {str(e)[:80]}")

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
    # Gemini Flash-Lite: $0.10 за миллион входящих, $0.40 за исходящие.
    # Запасного считаем отдельно и по его ценам (grok-4.1-fast у xAI —
    # $0.20 и $0.50 за миллион): счёт должен показывать правду, а не
    # усреднённую выдумку
    # Кэшированные входящие стоят вдесятеро дешевле обычных — $0.01 против
    # $0.10 за миллион. Считать их по полной цене нельзя: по этой сумме
    # работает наш потолок расхода, и завышенный счёт остановил бы ИИ раньше
    # времени. С 23.08 из кэша приходит больше половины входящих
    _cached_in = min(TOKENS.get("cached", 0), TOKENS["in"])
    cost = ((TOKENS["in"] - _cached_in) / 1e6 * 0.10
            + _cached_in / 1e6 * 0.01
            + TOKENS["out"] / 1e6 * 0.40
            + TOKENS["fallback_in"] / 1e6 * 0.03 + TOKENS["fallback_out"] / 1e6 * 0.30)
    if TOKENS["fallback_in"]:
        print(f"  ↪️ Через запасного ({FALLBACK_MODEL}): "
              f"{TOKENS['fallback_in']:,} входящих + "
              f"{TOKENS['fallback_out']:,} исходящих токенов")
    print(f"💰 Расход ИИ: {TOKENS['calls']} запросов, "
          f"{TOKENS['in']:,} входящих + {TOKENS['out']:,} исходящих токенов "
          f"≈ ${cost:.4f} за прогон (≈ ${cost * 24:.2f} в сутки при часовом графике)")
    drop_gemini_caches()
    _cached = TOKENS.get("cached", 0)
    if TOKENS["in"]:
        print(f"  ♻️ Из кэша Gemini: {_cached:,} входящих токенов "
              f"({_cached * 100 // TOKENS['in']}%)")
    save_ai_spend(cost)

    # Публикуем имена редакторских каналов — приложение читает их отсюда,
    # смена канала не требует обновления приложения
    db.reference("/config/editorial_channels").set({
        **{lang: ch.lstrip("@") for lang, ch in TELEGRAM_CHANNELS.items() if ch},
        "gl": "t247_gl",  # глобальный редакторский — посты для всех регионов
    })

    # Публикуем источники приложения (Telegram/YouTube каналы, которые
    # приложение парсит само) — правка здесь меняет контент у всех без релиза
    db.reference("/config/app_sources").set(APP_SOURCES)

    # Какая версия сейчас в Play. Приложение сравнивает с собственной и, если
    # отстало, предлагает обновиться при открытии. Play умеет это сам, но
    # его встроенный способ тянет ещё одну библиотеку и молчит первые сутки
    # после выпуска; здесь мы решаем сами и меняем цифру одной правкой.
    # ВАЖНО: поднимать ВМЕСТЕ с versionCode в build.gradle.kts, иначе
    # читатели получат предложение обновиться на версию, которой нет.
    db.reference("/config/app_version").set({
        "code": APP_LATEST_CODE,
        "name": APP_LATEST_NAME,
    })
    db.reference("/config/refresh_minutes").set(REFRESH_MINUTES)

if __name__ == "__main__":
    main()
