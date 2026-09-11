# -*- coding: utf-8 -*-
"""Штатные редакции и речевое радио.

Живут отдельно от мировой ленты: иначе пятьдесят штатов делят 70 мест с NPR,
и техасец видит три карточки, а флоридские занимают слоты, которых ему
не показывают.

Радио — общественные новостные станции своего штата. Музыкальные не берём.
Молчащую станцию часовая проверка погасит сама.
"""

# Квота маленькая: ширина охвата, не объём. Одна-две новости со штата,
# зато в каждом штате хоть кто-то есть.
def _paper(url, source, region, quota=2, priority=0, lang="en"):
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
    # Остаток сети States Newsroom — некоммерческие редакции столиц штатов.
    # Ленты WordPress /feed/, тот же шаблон, что у уже работающих двенадцати.
    _paper("https://alabamareflector.com/feed/", "Alabama Reflector", "US-AL"),
    _paper("https://alaskabeacon.com/feed/", "Alaska Beacon", "US-AK"),
    _paper("https://arkansasadvocate.com/feed/", "Arkansas Advocate", "US-AR"),
    _paper("https://calmatters.org/feed/", "CalMatters", "US-CA"),
    _paper("https://ctmirror.org/feed/", "Connecticut Mirror", "US-CT"),
    _paper("https://www.civilbeat.org/feed/", "Honolulu Civil Beat", "US-HI"),
    _paper("https://idahocapitalsun.com/feed/", "Idaho Capital Sun", "US-ID"),
    _paper("https://capitolnewsillinois.com/feed/", "Capitol News Illinois", "US-IL"),
    _paper("https://indianacapitalchronicle.com/feed/", "Indiana Capital Chronicle", "US-IN"),
    _paper("https://iowacapitaldispatch.com/feed/", "Iowa Capital Dispatch", "US-IA"),
    _paper("https://kansasreflector.com/feed/", "Kansas Reflector", "US-KS"),
    _paper("https://kentuckylantern.com/feed/", "Kentucky Lantern", "US-KY"),
    _paper("https://lailluminator.com/feed/", "Louisiana Illuminator", "US-LA"),
    _paper("https://mainemorningstar.com/feed/", "Maine Morning Star", "US-ME"),
    _paper("https://www.marylandmatters.org/feed/", "Maryland Matters", "US-MD"),
    _paper("https://commonwealthbeacon.org/feed/", "CommonWealth Beacon", "US-MA"),
    _paper("https://montanafreepress.org/feed/", "Montana Free Press", "US-MT"),
    _paper("https://nebraskaexaminer.com/feed/", "Nebraska Examiner", "US-NE"),
    _paper("https://newhampshirebulletin.com/feed/", "New Hampshire Bulletin", "US-NH"),
    _paper("https://newjerseymonitor.com/feed/", "New Jersey Monitor", "US-NJ"),
    _paper("https://sourcenm.com/feed/", "Source New Mexico", "US-NM"),
    _paper("https://ncnewsline.com/feed/", "NC Newsline", "US-NC"),
    _paper("https://northdakotamonitor.com/feed/", "North Dakota Monitor", "US-ND"),
    _paper("https://oklahomavoice.com/feed/", "Oklahoma Voice", "US-OK"),
    _paper("https://oregoncapitalchronicle.com/feed/", "Oregon Capital Chronicle", "US-OR"),
    _paper("https://rhodeislandcurrent.com/feed/", "Rhode Island Current", "US-RI"),
    _paper("https://scdailygazette.com/feed/", "South Carolina Daily Gazette", "US-SC"),
    _paper("https://southdakotasearchlight.com/feed/", "South Dakota Searchlight", "US-SD"),
    _paper("https://tennesseelookout.com/feed/", "Tennessee Lookout", "US-TN"),
    _paper("https://utahnewsdispatch.com/feed/", "Utah News Dispatch", "US-UT"),
    _paper("https://vtdigger.org/feed/", "VTDigger", "US-VT"),
    _paper("https://washingtonstatestandard.com/feed/", "Washington State Standard", "US-WA"),
    _paper("https://westvirginiawatch.com/feed/", "West Virginia Watch", "US-WV"),
    _paper("https://wisconsinexaminer.com/feed/", "Wisconsin Examiner", "US-WI"),
    _paper("https://wyofile.com/feed/", "WyoFile", "US-WY"),
    _paper("https://www.thedccline.org/feed/", "The DC Line", "US-DC"),
    _paper("https://delawarecurrent.org/feed/", "Delaware Current", "US-DE"),

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
    _paper("https://www.informador.mx/rss/jalisco.xml", "El Informador", "MX-JAL", quota=3, lang="es"),
    _paper("https://indianexpress.com/section/cities/mumbai/feed/", "Indian Express Mumbai", "IN-MH", quota=2),
    _paper("https://www.thenewsminute.com/rss.xml", "The News Minute", "IN-KA", quota=2),
    _paper("https://www.fontanka.ru/fontanka.rss", "Фонтанка", "RU-SPE", quota=3, lang="ru"),
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
    # Бразилия и Мексика — городские разговорные, не музыка.
    _radio("CBN Recife", "https://video09.logicahost.com.br/cbnrecife/cbnrecife/playlist.m3u8", "BR-PE", pool="pt"),
    _radio("El Heraldo Guadalajara", "https://stream.radiojar.com/21h1m4cch8nwv", "MX-JAL", pool="es"),
    _radio("El Heraldo Monterrey", "https://stream.radiojar.com/951bffq8h8nwv", "MX-NLE", pool="es"),
    _radio("W Radio Monterrey", "https://streaming.servicioswebmx.com/8214/stream", "MX-NLE", pool="es"),
    _radio("Radio Fórmula Tijuana", "https://stream.radiojar.com/nce1peen3p8uv", "MX-BCN", pool="es"),
    _radio("Радио Зенит", "https://radiozenit.hostingradio.ru:8015/radiozenit128.mp3", "RU-SPE", pool="ru"),
]
