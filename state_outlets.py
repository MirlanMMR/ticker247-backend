# -*- coding: utf-8 -*-
"""Штатные редакции и речевое радио.

Живут отдельно от мировой ленты: иначе пятьдесят штатов делят 70 мест с NPR,
и техасец видит три карточки, а флоридские занимают слоты, которых ему
не показывают.

Радио — общественные новостные станции своего штата. Музыкальные не берём.
Молчащую станцию часовая проверка погасит сама.
"""

# Квота на источник была маленькой (2) как раз ради широты охвата — но это
# было ДО брони по региону (REGION_CAP/REGION_TOTAL в fetch_news.py), которая
# и так не даёт одному штату вытеснить другой. Раз бронь уже держит охват,
# маленькая квота на входе только вредит: 22.09.2026 сетевой репортаж Gray
# Media (Атланта, Джорджия) разошёлся по филиалам в четырёх штатах — WCTV,
# WKYT, WAFB, KFYR-TV, — дедуп законно оставил одну копию, а вторая кандидатура
# на замену не нашлась, потому что квота=2 не оставила источнику запасных
# новостей. Подняли до 10 — вровень с потолком REGION_CAP, — чтобы у дедупа
# и ИИ-фильтра было из чего выбирать, а не только единственный вариант.
def _paper(url, source, region, quota=10, priority=0, lang="en"):
    return {
        "url": url, "source": source, "category": "NEWS",
        "priority": priority, "quota": quota, "scope": "local",
        "lang": lang, "region": region,
    }


def _radio(name, url, region, pool="en", country=None, colors=None):
    country = country or region.split("-")[0]
    frm, to = colors or _color(name)
    return {
        "name": name, "url": url, "pool": pool,
        "colorFrom": frm, "colorTo": to,
        "countries": country, "region": region,
    }


_PALETTE = [
    ("FF1B2A44", "FF35558C"), ("FF3A2418", "FF8A5230"),
    ("FF1E3040", "FF3A6A82"), ("FF1A332C", "FF2F7A64"),
    ("FF2A1C28", "FF6A3A58"), ("FF1C2A38", "FF3A5A78"),
    ("FF241E32", "FF4A3E70"), ("FF2C2418", "FF6A5838"),
    ("FF16343A", "FF2C6A74"), ("FF3A2816", "FF7A542E"),
]


def _color(name):
    n = sum(ord(c) for c in name)
    return _PALETTE[n % len(_PALETTE)]


# ── Редакции штатов: States Newsroom + техасские андердоги + G1 штатов ──
#
# Уже стоят в RSS_SOURCES (с region допишем там): Florida Phoenix, Ohio
# Capital Journal, Michigan Advance, Georgia Recorder, Pennsylvania
# Capital-Star, Arizona Mirror, Minnesota Reformer, Colorado Newsline,
# Nevada Current, Virginia Mercury, Missouri Independent, Texas Tribune,
# Mississippi Today, LA Times, NY Post, Gazeta do Povo, Metrópoles.

STATE_RSS = [
    # Остаток сети States Newsroom и не только — некоммерческие редакции и
    # местные телеканалы/газеты столиц штатов.
    # States Newsroom здесь умер под Cloudflare 14.09.2026 (403 и с ноутбука,
    # и с GitHub Actions — см. RETIRED_SOURCES в fetch_news.py) — 22.09.2026
    # заменено на местные издания того же штата, каждое проверено: код 200 и
    # реальные <item> при разборе XML. Живыми из старой сети остались (не
    # трогаем): CalMatters, CT Mirror, Civil Beat, Capitol News Illinois,
    # CommonWealth Beacon, Montana Free Press, VTDigger, WyoFile, The DC Line.
    _paper("https://www.al.com/arc/outboundfeeds/rss/", "AL.com", "US-AL"),
    _paper("https://www.adn.com/arc/outboundfeeds/rss/", "Anchorage Daily News", "US-AK"),
    _paper("https://www.arktimes.com/arkansas/Rss.xml", "Arkansas Times", "US-AR"),
    _paper("https://calmatters.org/feed/", "CalMatters", "US-CA"),
    _paper("https://ctmirror.org/feed/", "Connecticut Mirror", "US-CT"),
    _paper("https://www.civilbeat.org/feed/", "Honolulu Civil Beat", "US-HI"),
    _paper("https://www.ktvb.com/feeds/syndication/rss/news/local", "KTVB", "US-ID"),
    _paper("https://capitolnewsillinois.com/feed/", "Capitol News Illinois", "US-IL"),
    _paper("https://mirrorindy.org/feed/", "Mirror Indy", "US-IN"),
    _paper("https://who13.com/feed/", "WHO 13", "US-IA"),
    _paper("https://www.wibw.com/arc/outboundfeeds/rss/", "WIBW", "US-KS"),
    # Джорджия (03.10.2026, владелец: «в штате нет новостей» — был один
    # SaportaReport, две карточки). Каждая лента проверена живой, 20–40 записей
    _paper("https://www.11alive.com/feeds/syndication/rss/news", "11Alive", "US-GA"),
    _paper("https://www.gpb.org/rss.xml", "Georgia Public Broadcasting", "US-GA"),
    _paper("https://www.wtoc.com/arc/outboundfeeds/rss/?outputType=xml", "WTOC", "US-GA"),
    _paper("https://www.walb.com/arc/outboundfeeds/rss/?outputType=xml", "WALB", "US-GA"),
    _paper("https://www.wrdw.com/arc/outboundfeeds/rss/?outputType=xml", "WRDW", "US-GA"),
    _paper("https://www.wkyt.com/arc/outboundfeeds/rss/", "WKYT", "US-KY"),
    _paper("https://www.wafb.com/arc/outboundfeeds/rss/", "WAFB", "US-LA"),
    _paper("https://www.pressherald.com/feed/", "Portland Press Herald", "US-ME"),
    _paper("https://marylandreporter.com/feed/", "MarylandReporter.com", "US-MD"),
    _paper("https://commonwealthbeacon.org/feed/", "CommonWealth Beacon", "US-MA"),
    _paper("https://montanafreepress.org/feed/", "Montana Free Press", "US-MT"),
    _paper("https://www.1011now.com/arc/outboundfeeds/rss/", "1011NOW", "US-NE"),
    _paper("https://www.nhpr.org/rss.xml", "NHPR", "US-NH"),
    _paper("https://njspotlightnews.org/feed/", "NJ Spotlight News", "US-NJ"),
    _paper("https://www.santafenewmexican.com/search/?f=rss", "Santa Fe New Mexican", "US-NM"),
    _paper("https://cardinalpine.com/feed/", "Cardinal & Pine", "US-NC"),
    _paper("https://www.kfyrtv.com/arc/outboundfeeds/rss/", "KFYR-TV", "US-ND"),
    _paper("https://nondoc.com/feed/", "NonDoc", "US-OK"),
    _paper("https://www.oregonlive.com/arc/outboundfeeds/rss/", "The Oregonian", "US-OR"),
    _paper("https://www.wpri.com/feed/", "WPRI", "US-RI"),
    _paper("https://www.wistv.com/arc/outboundfeeds/rss/", "WIS-TV", "US-SC"),
    _paper("https://www.keloland.com/feed/", "KELOLAND", "US-SD"),
    _paper("https://wpln.org/feed/", "WPLN", "US-TN"),
    _paper("https://www.ksl.com/rss/news", "KSL.com", "US-UT"),
    _paper("https://vtdigger.org/feed/", "VTDigger", "US-VT"),
    _paper("https://cascadepbs.org/feed", "Cascade PBS", "US-WA"),
    _paper("https://www.wvgazettemail.com/search/?f=rss", "Charleston Gazette-Mail", "US-WV"),
    _paper("https://wisconsinwatch.org/feed/", "Wisconsin Watch", "US-WI"),
    _paper("https://wyofile.com/feed/", "WyoFile", "US-WY"),
    _paper("https://thedcline.org/feed/", "The DC Line", "US-DC"),
    _paper("https://spotlightdelaware.org/feed/", "Spotlight Delaware", "US-DE"),

    # Техас. Tribune уже в общем списке; здесь городские некоммерческие —
    # Хьюстон, Даллас/Форт-Уэрт, Сан-Антонио, Эль-Пасо, Остин.
    _paper("https://www.texasobserver.org/feed/", "Texas Observer", "US-TX", quota=3, priority=1),
    _paper("https://houstonlanding.org/feed/", "Houston Landing", "US-TX", quota=3, priority=1),
    _paper("https://sanantonioreport.org/feed/", "San Antonio Report", "US-TX", quota=2),
    _paper("https://elpasomatters.org/feed/", "El Paso Matters", "US-TX", quota=2),
    _paper("https://fortworthreport.org/feed/", "Fort Worth Report", "US-TX", quota=2),
    _paper("https://www.austinmonitor.com/feed/", "Austin Monitor", "US-TX", quota=2),

    # Бразилия: ленты G1 по штатам. Национальный G1 остаётся без region.
    _paper("https://g1.globo.com/rss/g1/sp/sao-paulo/", "G1 São Paulo", "BR-SP", quota=3, lang="pt"),
    _paper("https://g1.globo.com/rss/g1/rj/rio-de-janeiro/", "G1 Rio", "BR-RJ", quota=3, lang="pt"),
    _paper("https://g1.globo.com/rss/g1/mg/minas-gerais/", "G1 Minas", "BR-MG", quota=2, lang="pt"),
    _paper("https://g1.globo.com/rss/g1/pr/parana/", "G1 Paraná", "BR-PR", quota=2, lang="pt"),
    _paper("https://g1.globo.com/rss/g1/rs/rio-grande-do-sul/", "G1 Rio Grande do Sul", "BR-RS", quota=2, lang="pt"),
    _paper("https://g1.globo.com/rss/g1/ba/bahia/", "G1 Bahia", "BR-BA", quota=2, lang="pt"),
    _paper("https://g1.globo.com/rss/g1/df/distrito-federal/", "G1 Distrito Federal", "BR-DF", quota=2, lang="pt"),
    _paper("https://g1.globo.com/rss/g1/pe/pernambuco/", "G1 Pernambuco", "BR-PE", quota=2, lang="pt"),
    _paper("https://g1.globo.com/rss/g1/ce/ceara/", "G1 Ceará", "BR-CE", quota=2, lang="pt"),
    _paper("https://g1.globo.com/rss/g1/sc/santa-catarina/", "G1 Santa Catarina", "BR-SC", quota=2, lang="pt"),

    # Мексика, Индия, Россия — по сильной региональной редакции, не сеть.
    # Индия и Мексика убраны 03.10.2026 (владелец): лент у 2 регионов из 36 и 32 —
    # выбор региона там бессмыслен, а три одиноких издания (El Informador,
    # Indian Express Mumbai, The News Minute) читателю ничего не давали.
    _paper("https://www.fontanka.ru/fontanka.rss", "Фонтанка", "RU-SPE", quota=3, lang="ru"),
    # РОССИЯ: сеть городских порталов одного холдинга (Shkulev Media, ~55 сайтов
    # на одной платформе) отдаёт ленту по ОДНОМУ адресу https://www.{сайт}/text/rss.xml —
    # по 100 записей. Подсказка владельца 03.10.2026: «в регионах есть агрегаторы
    # одного разработчика». Проверено живыми с обычного адреса; с серверов GitHub
    # покажет первый прогон. Полку «Новости из» эти новости не заваливают: она
    # берёт не больше трёх на страну.
    _paper("https://www.14.ru/text/rss.xml", "14.ru — Якутск", "RU-SA", quota=8, lang="ru"),
    _paper("https://www.26.ru/text/rss.xml", "26.ru — Ставрополь", "RU-STA", quota=8, lang="ru"),
    _paper("https://www.29.ru/text/rss.xml", "29.ru — Архангельск", "RU-ARK", quota=8, lang="ru"),
    _paper("https://www.35.ru/text/rss.xml", "35.ru — Вологда", "RU-VLG", quota=8, lang="ru"),
    _paper("https://www.43.ru/text/rss.xml", "43.ru — Киров", "RU-KIR", quota=8, lang="ru"),
    _paper("https://www.45.ru/text/rss.xml", "45.ru — Курган", "RU-KGN", quota=8, lang="ru"),
    _paper("https://www.48.ru/text/rss.xml", "48.ru — Липецк", "RU-LIP", quota=8, lang="ru"),
    _paper("https://www.51.ru/text/rss.xml", "51.ru — Мурманск", "RU-MUR", quota=8, lang="ru"),
    _paper("https://www.53.ru/text/rss.xml", "53.ru — Великий Новгород", "RU-NGR", quota=8, lang="ru"),
    _paper("https://www.56.ru/text/rss.xml", "56.ru — Оренбург", "RU-ORE", quota=8, lang="ru"),
    _paper("https://www.59.ru/text/rss.xml", "59.ru — Пермь", "RU-PER", quota=8, lang="ru"),
    _paper("https://www.60.ru/text/rss.xml", "60.ru — Псков", "RU-PSK", quota=8, lang="ru"),
    _paper("https://www.62.ru/text/rss.xml", "62.ru — Рязань", "RU-RYA", quota=8, lang="ru"),
    _paper("https://www.63.ru/text/rss.xml", "63.ru — Самара", "RU-SAM", quota=8, lang="ru"),
    _paper("https://www.68.ru/text/rss.xml", "68.ru — Тамбов", "RU-TAM", quota=8, lang="ru"),
    _paper("https://www.71.ru/text/rss.xml", "71.ru — Тула", "RU-TUL", quota=8, lang="ru"),
    _paper("https://www.72.ru/text/rss.xml", "72.ru — Тюмень", "RU-TYU", quota=8, lang="ru"),
    _paper("https://www.74.ru/text/rss.xml", "74.ru — Челябинск", "RU-CHE", quota=8, lang="ru"),
    _paper("https://www.76.ru/text/rss.xml", "76.ru — Ярославль", "RU-YAR", quota=8, lang="ru"),
    _paper("https://www.86.ru/text/rss.xml", "86.ru — Ханты-Мансийск", "RU-KHM", quota=8, lang="ru"),
    _paper("https://www.89.ru/text/rss.xml", "89.ru — Салехард", "RU-YAN", quota=8, lang="ru"),
    _paper("https://www.93.ru/text/rss.xml", "93.ru — Краснодар", "RU-KDA", quota=8, lang="ru"),
    _paper("https://www.116.ru/text/rss.xml", "116.ru — Казань", "RU-TA", quota=8, lang="ru"),
    _paper("https://www.161.ru/text/rss.xml", "161.ru — Ростов-на-Дону", "RU-ROS", quota=8, lang="ru"),
    _paper("https://www.164.ru/text/rss.xml", "164.ru — Саратов", "RU-SAR", quota=8, lang="ru"),
    _paper("https://www.173.ru/text/rss.xml", "173.ru — Ульяновск", "RU-ULY", quota=8, lang="ru"),
    _paper("https://www.178.ru/text/rss.xml", "178.ru — Санкт-Петербург", "RU-SPE", quota=8, lang="ru"),
    _paper("https://www.e1.ru/text/rss.xml", "e1.ru — Екатеринбург", "RU-SVE", quota=8, lang="ru"),
    _paper("https://www.ngs.ru/text/rss.xml", "ngs.ru — Новосибирск", "RU-NVS", quota=8, lang="ru"),
    _paper("https://www.ngs24.ru/text/rss.xml", "ngs24.ru — Красноярск", "RU-KYA", quota=8, lang="ru"),
    _paper("https://www.ngs55.ru/text/rss.xml", "ngs55.ru — Омск", "RU-OMS", quota=8, lang="ru"),
    _paper("https://www.nn.ru/text/rss.xml", "nn.ru — Нижний Новгород", "RU-NIZ", quota=8, lang="ru"),
    _paper("https://www.ufa1.ru/text/rss.xml", "ufa1.ru — Уфа", "RU-BA", quota=8, lang="ru"),
    _paper("https://www.v1.ru/text/rss.xml", "v1.ru — Волгоград", "RU-VGG", quota=8, lang="ru"),
    _paper("https://www.chita.ru/text/rss.xml", "chita.ru — Чита", "RU-ZAB", quota=8, lang="ru"),
    _paper("https://www.sochi1.ru/text/rss.xml", "sochi1.ru — Сочи", "RU-KDA", quota=8, lang="ru"),
]


# Речевое радио штатов. Национальные (NPR, BandNews) остаются в общем списке
# без region. Потоки https; uuid у streamtheworld не храним — он одноразовый.
STATE_RADIO = [
    _radio("Alabama Public Radio", "https://playerservices.streamtheworld.com/api/livestream-redirect/WUAL_HD1.mp3", "US-AL"),
    _radio("Alaska Public Media", "https://alaskapublic-live.streamguys1.com/aac-web", "US-AK"),
    _radio("KPCC", "https://laist.streamguys1.com/kpcc-mp3", "US-CA"),
    _radio("WAMU", "https://wamu.streamguys1.com/WAMU-1", "US-DC"),
    _radio("WLRN", "https://wlrn.streamguys1.com/wlrn-news-web-icy", "US-FL"),
    _radio("Boise State Public Radio", "https://boisestate.streamguys1.com/News1-aac-96k-icy", "US-ID"),
    _radio("KCUR", "https://kcur.streamguys1.com/kcur-website-icy", "US-MO"),
    _radio("WWNO", "https://tektite.streamguys1.com:5145/wwnolive", "US-LA"),
    _radio("Maine Public", "https://playerservices.streamtheworld.com/api/livestream-redirect/WMEAFM.mp3", "US-ME"),
    _radio("WYPR", "https://wtmd-ice.streamguys1.com/wypr-1", "US-MD"),
    _radio("WDET", "https://wdet.cdnstream1.com/4550_256.aac", "US-MI"),
    _radio("Mississippi Public Broadcasting", "https://playerservices.streamtheworld.com/api/livestream-redirect/WMPNFM_128.mp3", "US-MS"),
    _radio("Montana Public Radio", "https://playerservices.streamtheworld.com/api/livestream-redirect/KUFMFM.mp3", "US-MT"),
    _radio("KNPR", "https://playerservices.streamtheworld.com/api/livestream-redirect/KNPRFM.mp3", "US-NV"),
    _radio("NHPR", "https://nhpr.streamguys1.com/nhpr", "US-NH"),
    _radio("KUNM", "https://playerservices.streamtheworld.com/api/livestream-redirect/KUNMFM_128.mp3", "US-NM"),
    _radio("WOSU", "https://wosu.streamguys1.com/NPR_128", "US-OH"),
    _radio("KOSU", "https://playerservices.streamtheworld.com/api/livestream-redirect/KOSUFM_NEWS.mp3", "US-OK"),
    _radio("The Public's Radio", "https://amber.streamguys1.com:5595/riprdeskweb", "US-RI"),
    _radio("South Carolina Public Radio", "https://playerservices.streamtheworld.com/api/livestream-redirect/WRJAFM.mp3", "US-SC"),
    _radio("WPLN", "https://wpln.streamguys1.com/wplnfm.mp3", "US-TN"),
    _radio("Houston Public Media", "https://stream.houstonpublicmedia.org/news-aac", "US-TX"),
    _radio("Texas Public Radio", "https://playerservices.streamtheworld.com/api/livestream-redirect/KSTXFMAAC.aac", "US-TX"),
    _radio("KEDT", "https://kedt.streamguys1.com/live-aac", "US-TX"),
    _radio("KUER", "https://kuer.streamguys1.com/high_icy", "US-UT"),
    _radio("Vermont Public", "https://vpr.streamguys1.com/vpr64.aac", "US-VT"),
    _radio("VPM News", "https://playerservices.streamtheworld.com/api/livestream-redirect/WCVEFM.mp3", "US-VA"),
    _radio("West Virginia Public Broadcasting", "https://wvpublic.streamguys1.com/wvpb256k.aac", "US-WV"),
    # 30.09.2026: добавлены штаты без радио. Каждый поток проверен живым (аудио,
    # https) и по icy-name узнан. Нет пока: HI, IN, OR, SD — подходящей речевой
    # станции с https-потоком не нашлось.
    _radio("KUAF", "https://war.streamguys1.com:7031/kuaf1", "US-AR"),
    _radio("WNPR", "https://playerservices.streamtheworld.com/api/livestream-redirect/WNPRFM.mp3", "US-CT"),
    _radio("WHYY", "https://whyy.streamguys1.com/whyy-mp3", "US-DE"),
    _radio("WABE", "https://playerservices.streamtheworld.com/api/livestream-redirect/WABEFM_HD1_SC.mp3", "US-GA"),
    _radio("Iowa Public Radio News", "https://news-stream.iowapublicradio.org/News.mp3", "US-IA"),
    _radio("Radio Kansas", "https://audio-edge-w4d68.yul.o.radiomast.io/5567306a-66f6-4d8f-a399-520e2936e3a0", "US-KS"),
    _radio("WKU Public Radio", "https://dal-wku-stream-1.neighborhoodca.com/stream", "US-KY"),
    _radio("WUNC", "https://wunc-ice.streamguys1.com/wunc-128-mp3", "US-NC"),
    _radio("Prairie Public", "https://playerservices.streamtheworld.com/api/livestream-redirect/KCNDFM.mp3", "US-ND"),
    _radio("Nebraska Public Media News", "https://playerservices.streamtheworld.com/api/livestream-redirect/KUCVFM.mp3", "US-NE"),
    _radio("New Jersey Public Radio", "https://fm939.wnyc.org/wnycfm-web", "US-NJ"),
    _radio("Wisconsin Public Radio", "https://wpr-ice.streamguys1.com/wpr-ideas-mp3-64", "US-WI"),
    _radio("Wyoming Public Radio", "https://wyoming-public-ice.streamguys1.com/WPR128MP3", "US-WY"),
    # Бразилия и Мексика — городские разговорные, не музыка.
    _radio("CBN Recife", "https://video09.logicahost.com.br/cbnrecife/cbnrecife/playlist.m3u8", "BR-PE", pool="pt"),
    # El Heraldo Guadalajara/Monterrey и Radio Fórmula Tijuana убраны
    # 22.09.2026: весь куст ссылок на stream.radiojar.com лёг меньше чем за
    # сутки после добавления (id потоков там недолговечны и перевыпускаются),
    # источник больше не используется.
    _radio("W Radio Monterrey", "https://streaming.servicioswebmx.com/8214/stream", "MX-NLE", pool="es"),
    _radio("Радио Зенит", "https://radiozenit.hostingradio.ru:8015/radiozenit128.mp3", "RU-SPE", pool="ru"),
]
