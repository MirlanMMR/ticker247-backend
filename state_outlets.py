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
    # США, 03.10.2026: владелец не верил, что в Америке мало изданий — и был прав.
    # Перебрано ~400 телеканалов, газет и радио по штатам; взяты живые ленты со
    # свежими материалами (до 30 часов), до трёх на штат. Квота 6 — вровень с тем,
    # сколько на штат остаётся после общего потолка.
    _paper("https://www.alaskasnewssource.com/arc/outboundfeeds/rss/?outputType=xml", "KTUU", "US-AK", quota=6),
    _paper("https://www.ktva.com/arc/outboundfeeds/rss/?outputType=xml", "KTVA", "US-AK", quota=6),
    _paper("https://www.ktuu.com/arc/outboundfeeds/rss/?outputType=xml", "KTUU (ktuu)", "US-AK", quota=6),
    _paper("https://www.waff.com/arc/outboundfeeds/rss/?outputType=xml", "WAFF", "US-AL", quota=6),
    _paper("https://www.wbrc.com/arc/outboundfeeds/rss/?outputType=xml", "WBRC", "US-AL", quota=6),
    _paper("https://www.wsfa.com/arc/outboundfeeds/rss/?outputType=xml", "WSFA", "US-AL", quota=6),
    _paper("https://www.5newsonline.com/feeds/syndication/rss/news", "KFSM RSS Feed: news", "US-AR", quota=6),
    _paper("https://www.thv11.com/feeds/syndication/rss/news", "KTHV RSS Feed: news", "US-AR", quota=6),
    _paper("https://www.kark.com/feed/", "KARK", "US-AR", quota=6),
    _paper("https://www.12news.com/feeds/syndication/rss/news", "KPNX RSS Feed: news", "US-AZ", quota=6),
    _paper("https://www.kold.com/arc/outboundfeeds/rss/?outputType=xml", "KOLD", "US-AZ", quota=6),
    _paper("https://www.azfamily.com/arc/outboundfeeds/rss/?outputType=xml", "Arizona's Family", "US-AZ", quota=6),
    _paper("https://www.kron4.com/feed/", "KRON4", "US-CA", quota=6),
    _paper("https://www.laist.com/index.rss", "laist", "US-CA", quota=6),
    _paper("https://www.fox5sandiego.com/feed/", "FOX 5 San Diego &amp; KUSI News", "US-CA", quota=6),
    _paper("https://www.9news.com/feeds/syndication/rss/news", "KUSA RSS Feed: news", "US-CO", quota=6),
    _paper("https://www.kdvr.com/feed/", "KDVR", "US-CO", quota=6),
    _paper("https://www.cpr.org/feed/", "Colorado Public Radio", "US-CO", quota=6),
    _paper("https://www.wfsb.com/arc/outboundfeeds/rss/?outputType=xml", "WFSB", "US-CT", quota=6),
    _paper("https://www.wtnh.com/feed/", "WTNH", "US-CT", quota=6),
    _paper("https://www.wusa9.com/feeds/syndication/rss/news", "WUSA9", "US-DC", quota=6),
    _paper("https://www.fox5dc.com/rss.xml", "Latest &amp; Breaking News", "US-DC", quota=6),
    _paper("https://www.wtop.com/feed/", "WTOP", "US-DC", quota=6),
    _paper("https://www.whyy.org/feed/", "WHYY", "US-DE", quota=6),
    _paper("https://www.wfla.com/feed/", "WFLA", "US-FL", quota=6),
    _paper("https://www.fox35orlando.com/rss.xml", "Latest &amp; Breaking News (fox35orlando)", "US-FL", quota=6),
    _paper("https://www.news4jax.com/arc/outboundfeeds/rss/?outputType=xml", "WJXT News4JAX", "US-FL", quota=6),
    _paper("https://www.khon2.com/feed/", "KHON2", "US-HI", quota=6),
    _paper("https://www.staradvertiser.com/feed/", "Honolulu Star-Advertiser", "US-HI", quota=6),
    _paper("https://www.hawaiinewsnow.com/arc/outboundfeeds/rss/?outputType=xml", "Hawaii News Now", "US-HI", quota=6),
    _paper("https://www.weareiowa.com/feeds/syndication/rss/news", "WOI RSS Feed: news", "US-IA", quota=6),
    _paper("https://www.kcrg.com/arc/outboundfeeds/rss/?outputType=xml", "KCRG", "US-IA", quota=6),
    _paper("https://www.kmvt.com/arc/outboundfeeds/rss/?outputType=xml", "KMVT", "US-ID", quota=6),
    _paper("https://www.boisestatepublicradio.org/index.rss", "News", "US-ID", quota=6),
    _paper("https://www.wcia.com/feed/", "WCIA", "US-IL", quota=6),
    _paper("https://www.wgntv.com/feed/", "WGNTV", "US-IL", quota=6),
    _paper("https://www.chicago.suntimes.com/feed/", "Chicago Sun-Times", "US-IL", quota=6),
    _paper("https://www.wthr.com/feeds/syndication/rss/news", "WTHR", "US-IN", quota=6),
    _paper("https://www.wane.com/feed/", "WANE", "US-IN", quota=6),
    _paper("https://www.wishtv.com/feed/", "WISH-TV", "US-IN", quota=6),
    _paper("https://www.ksn.com/feed/", "KSN", "US-KS", quota=6),
    _paper("https://www.kwch.com/arc/outboundfeeds/rss/?outputType=xml", "KWCH", "US-KS", quota=6),
    _paper("https://www.kcur.org/feeds/syndication/rss/news", "KCUR (kcur)", "US-KS", quota=6),
    _paper("https://www.wave3.com/arc/outboundfeeds/rss/?outputType=xml", "WAVE3", "US-KY", quota=6),
    _paper("https://www.wfpl.org/feed/", "WFPL", "US-KY", quota=6),
    _paper("https://www.wwltv.com/feeds/syndication/rss/news", "WWLTV", "US-LA", quota=6),
    _paper("https://www.kplctv.com/arc/outboundfeeds/rss/?outputType=xml", "KPLC", "US-LA", quota=6),
    _paper("https://www.brproud.com/feed/", "Louisiana First News", "US-LA", quota=6),
    _paper("https://www.masslive.com/arc/outboundfeeds/rss/?outputType=xml", "masslive.com", "US-MA", quota=6),
    _paper("https://www.wwlp.com/feed/", "WWLP", "US-MA", quota=6),
    _paper("https://www.wbur.org/feed/", "WBUR", "US-MA", quota=6),
    _paper("https://www.wbal.com/feed/", "WBAL", "US-MD", quota=6),
    _paper("https://www.thebaltimorebanner.com/arc/outboundfeeds/rss/?outputType=xml", "Outbound Feeds", "US-MD", quota=6),
    _paper("https://www.newscentermaine.com/feeds/syndication/rss/news", "WCSH RSS Feed: news", "US-ME", quota=6),
    _paper("https://www.wabi.tv/arc/outboundfeeds/rss/?outputType=xml", "WABI", "US-ME", quota=6),
    _paper("https://www.bangordailynews.com/feed/", "Bangor Daily News", "US-ME", quota=6),
    _paper("https://www.mlive.com/arc/outboundfeeds/rss/?outputType=xml", "mlive.com", "US-MI", quota=6),
    _paper("https://www.wzzm13.com/feeds/syndication/rss/news", "WZZM13", "US-MI", quota=6),
    _paper("https://www.wlns.com/feed/", "WLNS", "US-MI", quota=6),
    _paper("https://www.kare11.com/feeds/syndication/rss/news", "KARE11", "US-MN", quota=6),
    _paper("https://www.kstp.com/feed/", "KSTP", "US-MN", quota=6),
    _paper("https://www.startribune.com/rss/", "Startribune News", "US-MN", quota=6),
    _paper("https://www.ksdk.com/feeds/syndication/rss/news", "KSDK", "US-MO", quota=6),
    _paper("https://www.fox2now.com/feed/", "FOX 2", "US-MO", quota=6),
    _paper("https://www.kfvs12.com/arc/outboundfeeds/rss/?outputType=xml", "KFVS12", "US-MO", quota=6),
    _paper("https://www.wdam.com/arc/outboundfeeds/rss/?outputType=xml", "WDAM", "US-MS", quota=6),
    _paper("https://www.wlbt.com/arc/outboundfeeds/rss/?outputType=xml", "WLBT", "US-MS", quota=6),
    _paper("https://www.wtva.com/arc/outboundfeeds/rss/?outputType=xml", "WTVA", "US-MS", quota=6),
    _paper("https://www.wcnc.com/feeds/syndication/rss/news", "WCNC", "US-NC", quota=6),
    _paper("https://www.wfmynews2.com/feeds/syndication/rss/news", "WFMY RSS Feed: news", "US-NC", quota=6),
    _paper("https://www.wect.com/arc/outboundfeeds/rss/?outputType=xml", "WECT", "US-NC", quota=6),
    _paper("https://www.inforum.com/index.rss", "InForum", "US-ND", quota=6),
    _paper("https://www.grandforksherald.com/index.rss", "Grand Forks Herald", "US-ND", quota=6),
    _paper("https://www.kxnet.com/feed/", "KXNET", "US-ND", quota=6),
    _paper("https://www.wowt.com/arc/outboundfeeds/rss/?outputType=xml", "WOWT", "US-NE", quota=6),
    _paper("https://www.klkntv.com/feed/", "KLKN-TVKLKN-TV", "US-NE", quota=6),
    _paper("https://www.unionleader.com/rss.xml", "NH Union Leader Latest News", "US-NH", quota=6),
    _paper("https://www.concordmonitor.com/feed/", "Concord Monitor", "US-NH", quota=6),
    _paper("https://www.nj.com/arc/outboundfeeds/rss/?outputType=xml", "nj.com", "US-NJ", quota=6),
    _paper("https://www.nj1015.com/feed/", "New Jersey 101.5", "US-NJ", quota=6),
    _paper("https://www.krqe.com/feed/", "KRQE", "US-NM", quota=6),
    _paper("https://www.kob.com/feed/", "KOB", "US-NM", quota=6),
    _paper("https://www.reviewjournal.com/feed/", "reviewjournal", "US-NV", quota=6),
    _paper("https://www.8newsnow.com/feed/", "KLAS", "US-NV", quota=6),
    _paper("https://www.kolotv.com/arc/outboundfeeds/rss/?outputType=xml", "KOLO", "US-NV", quota=6),
    _paper("https://www.syracuse.com/arc/outboundfeeds/rss/?outputType=xml", "syracuse.com", "US-NY", quota=6),
    _paper("https://www.wgrz.com/feeds/syndication/rss/news", "WGRZ", "US-NY", quota=6),
    _paper("https://www.gothamist.com/feed/", "Gothamist", "US-NY", quota=6),
    _paper("https://www.nbc4i.com/feed/", "NBC4 WCMH-TV", "US-OH", quota=6),
    _paper("https://www.wkyc.com/feeds/syndication/rss/news", "WKYC", "US-OH", quota=6),
    _paper("https://www.10tv.com/feeds/syndication/rss/news", "WBNS RSS Feed: news", "US-OH", quota=6),
    _paper("https://www.kfor.com/feed/", "KFOR", "US-OK", quota=6),
    _paper("https://www.news9.com/index.rss", "OKC News", "US-OK", quota=6),
    _paper("https://www.kgw.com/feeds/syndication/rss/news", "KGW", "US-OR", quota=6),
    _paper("https://www.opb.org/arc/outboundfeeds/rss/?outputType=xml", "OPB", "US-OR", quota=6),
    _paper("https://www.ktvz.com/feed/", "KTVZ", "US-OR", quota=6),
    _paper("https://www.inquirer.com/arc/outboundfeeds/rss/?outputType=xml", "Inquirer.com", "US-PA", quota=6),
    _paper("https://www.triblive.com/feed/", "triblive", "US-PA", quota=6),
    _paper("https://www.post-gazette.com/rss/", "All Feed", "US-PA", quota=6),
    _paper("https://www.wltx.com/feeds/syndication/rss/news", "WLTX", "US-SC", quota=6),
    _paper("https://www.scpr.org/index.rss", "scpr", "US-SC", quota=6),
    _paper("https://www.wspa.com/feed/", "WSPA", "US-SC", quota=6),
    _paper("https://www.kotatv.com/arc/outboundfeeds/rss/?outputType=xml", "KOTA", "US-SD", quota=6),
    _paper("https://www.ksfy.com/arc/outboundfeeds/rss/?outputType=xml", "KSFY", "US-SD", quota=6),
    _paper("https://www.sdnewswatch.org/feed/", "South Dakota News Watch", "US-SD", quota=6),
    _paper("https://www.wbir.com/feeds/syndication/rss/news", "WBIR", "US-TN", quota=6),
    _paper("https://www.wsmv.com/arc/outboundfeeds/rss/?outputType=xml", "WSMV", "US-TN", quota=6),
    _paper("https://www.wreg.com/feed/", "WREG", "US-TN", quota=6),
    _paper("https://www.texasstandard.org/feed/", "Texas Standard", "US-TX", quota=6),
    _paper("https://www.kens5.com/feeds/syndication/rss/news", "KENS5", "US-TX", quota=6),
    _paper("https://www.kvue.com/feeds/syndication/rss/news", "KVUE", "US-TX", quota=6),
    _paper("https://www.abc4.com/feed/", "ABC4 Utah", "US-UT", quota=6),
    _paper("https://www.sltrib.com/arc/outboundfeeds/rss/?outputType=xml", "The Salt Lake Tribune", "US-UT", quota=6),
    _paper("https://www.deseret.com/arc/outboundfeeds/rss/?outputType=xml", "Deseret News", "US-UT", quota=6),
    _paper("https://www.13newsnow.com/feeds/syndication/rss/news", "WVEC RSS Feed: news", "US-VA", quota=6),
    _paper("https://www.wavy.com/feed/", "WAVY", "US-VA", quota=6),
    _paper("https://www.wdbj7.com/arc/outboundfeeds/rss/?outputType=xml", "WDBJ7", "US-VA", quota=6),
    _paper("https://www.wcax.com/arc/outboundfeeds/rss/?outputType=xml", "WCAX", "US-VT", quota=6),
    _paper("https://www.vermontpublic.org/feeds/syndication/rss/news", "Local News", "US-VT", quota=6),
    _paper("https://www.sevendaysvt.com/feed/", "Seven Days", "US-VT", quota=6),
    _paper("https://www.king5.com/feeds/syndication/rss/news", "KING5", "US-WA", quota=6),
    _paper("https://www.krem.com/feeds/syndication/rss/news", "KREM", "US-WA", quota=6),
    _paper("https://www.seattletimes.com/feed/", "seattletimes", "US-WA", quota=6),
    _paper("https://www.wearegreenbay.com/feed/", "WFRV Local 5", "US-WI", quota=6),
    _paper("https://www.tmj4.com/index.rss", "Homepage", "US-WI", quota=6),
    _paper("https://www.wbay.com/arc/outboundfeeds/rss/?outputType=xml", "WBAY", "US-WI", quota=6),
    _paper("https://www.wvmetronews.com/feed/", "WV MetroNews", "US-WV", quota=6),
    _paper("https://www.wsaz.com/arc/outboundfeeds/rss/?outputType=xml", "WSAZ", "US-WV", quota=6),
    _paper("https://www.wboy.com/feed/", "WBOY", "US-WV", quota=6),
    _paper("https://www.cowboystatedaily.com/rss.xml", "Untitled RSS Feed", "US-WY", quota=6),
    _paper("https://www.county17.com/feed/", "County 17", "US-WY", quota=6),
    _paper("https://www.oilcity.news/feed/", "Oil City News", "US-WY", quota=6),
    _paper("https://missoulacurrent.com/feed/", "Missoula Current", "US-MT", quota=6),
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
