# -*- coding: utf-8 -*-
"""«Местное» с чужим событием, когда страну события ИИ не назвал (журнал J42, 15.10.2026).

Случай: «Шавкат Мирзиёев подписал закон о пожизненном наказании для педофилов» лежало на
«Местных» Кыргызстана — издание наше, президент и страна чужие. final_local_foreign_guard
смотрел только event_where (покрытие 27–58 %), у карточки без него не срабатывал.
Тест — на класс: любая страна и глава государства из пространства пула × дом; плюс защиты
от ложных срабатываний (мост, «своя страна названа», выбор ИИ главнее текста).
"""
import contextlib
import io
import sys

from topic_country import final_local_foreign_guard, local_event_country

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


SPACE = {"AM", "AZ", "BY", "GE", "KZ", "MD", "RU", "TJ", "TM", "UZ", "KG"}


def card(title, **kw):
    return {"title": title, "summary": kw.pop("summary", ""), "scope": "local", "country": "KG",
            "source": "Kaktus.media", "category": "NEWS", **kw}


def run(items, home="KG", space=SPACE):
    with contextlib.redirect_stdout(io.StringIO()):
        return final_local_foreign_guard(items, "ru", space, home)


# тот самый случай
x = card("Шавкат Мирзиёев подписал закон о пожизненном наказании для педофилов")
out = run([x])
check("Мирзиёев без event_where → «Новости из»", out and out[0]["scope"] == "pool")
check("страна события проставлена", out[0].get("event_where") == "UZ")
check("карточка не пропала из ленты", len(out) == 1)

# класс: страна/глава государства в заголовке × соседи
for t, code in [("Токаев подписал указ о новых льготах", "KZ"), ("Лукашенко назначил нового министра", "BY"),
                ("Рахмон открыл новую станцию", "TJ"), ("Алиев принял посла", "AZ"),
                ("Пашинян провёл встречу в Ереване", "AM"), ("В Узбекистане запретили курение в кафе", "UZ"),
                ("Власти Казахстана ввели новые правила", "KZ"), ("Правительство Таджикистана утвердило бюджет", "TJ"),
                ("В Грузии начался суд над бывшим министром", "GE")]:
    out = run([card(t)])
    check(f"{code}: «{t[:36]}» → pool", out and out[0]["scope"] == "pool" and out[0].get("event_where") == code)

# своя страна названа — это «мост», остаётся местным
for t in ["Жапаров встретился с Мирзиёевым в Ташкенте", "Кыргызстан и Узбекистан подписали соглашение",
          "Бишкек и Алматы свяжет новая трасса", "Токаев прибыл в Бишкек с визитом"]:
    out = run([card(t)])
    check(f"мост остаётся: «{t[:40]}»", out and out[0]["scope"] == "local")
check("название в тексте, не в заголовке — не считается", run([card("Новый закон о педофилах принят", summary="Подписал Мирзиёев")])[0]["scope"] == "local")

# выбор ИИ главнее слов
check("ИИ назвал страну — берём её", run([card("Подписан закон", event_where="UZ")])[0]["scope"] == "pool")
check("ИИ назвал свою страну — слова не перебивают", run([card("Мирзиёев и Жапаров", event_where="KG")])[0]["scope"] == "local")

# защиты
for k, v in [("bridge", True), ("interesting", True), ("vital", True), ("category", "URGENT")]:
    check(f"{k}: не трогаем", run([card("Мирзиёев подписал закон", **{k: v})])[0]["scope"] == "local")
check("не «Местное» — не трогаем", run([card("Мирзиёев подписал закон", scope="world")])[0]["scope"] == "world")

# слова, выведенные из текста, карточку НЕ снимают (снимает только выбор ИИ)
out = run([card("Трамп подписал закон о тарифах")])
check("чужая держава по словам, масштаб неясен — не снимаем", len(out) == 1)

# local_event_country
check("local_event_country: ИИ главнее", local_event_country({"event_where": "uz", "title": "x"}, SPACE, "KG") == ("UZ", False))
check("local_event_country: из заголовка", local_event_country({"title": "Мирзиёев подписал"}, SPACE, "KG") == ("UZ", True))
check("local_event_country: пусто", local_event_country({"title": "Цены на мясо выросли"}, SPACE, "KG") == ("", False))

# другой дом: Мексика, соседи по «es»
ES = {"AR", "CO", "ES", "PE", "CL", "VE", "CU", "UY", "MX"}
out = run([card("Argentina aprueba nueva ley de alquileres", country="MX")], home="MX", space=ES)
check("es: Аргентина названа, Мексика нет → «Новости из»", out and out[0]["scope"] == "pool" and out[0]["event_where"] == "AR")
out = run([card("México y Argentina firman acuerdo", country="MX")], home="MX", space=ES)
check("es: названа и Мексика — мост, остаётся", out and out[0]["scope"] == "local")

# слово внутри чужого слова — не страна и не глава государства (нашла сессия добора, 15.10)
for t in ["Маматалиев высказался о строительстве дороги", "Камила Талиева определила почерк омбудсмена",
          "Миранда открыла новую школу"]:
    out = run([card(t)])
    check(f"не страна: «{t[:38]}»", out and out[0]["scope"] == "local" and not out[0].get("event_where"))
check("а настоящая основа с окончанием находится", run([card("Алиеву доложили о ходе работ")])[0]["scope"] == "pool")

# ── Решение владельца 15.10: чужая держава → «Мировые», событие в «ЦА» → «Новости из…» ──
def where(x):
    out = run([x])
    return out[0]["scope"] if out else "снята"


for scale in (None, "world", "region", "local"):
    kw = {"scale": scale} if scale else {}
    check(f"Трамп без страны ИИ (масштаб {scale}) → Мировые",
          where(card("Трампа критикуют за публикацию жуткого видео", **kw)) == "world")
for ev in ("US", "UZ", ""):
    for scale in (None, "region", "world"):
        kw = {k: v for k, v in (("event_where", ev), ("scale", scale)) if v}
        check(f"Рубио в ЦА (ИИ: {ev or '—'}/{scale}) → Новости из…, не снимать",
              where(card("Рубио едет в ЦА", **kw)) == "pool")
check("ЦА: флаг space_wide", run([card("Рубио едет в Центральную Азию")])[0].get("space_wide") is True)
check("Рубио в Бишкек и Ташкент — мост, местное", where(card("Рубио посетит Бишкек и Ташкент")) == "local")
check("Рубио в ЦА, Кыргызстан в лиде — мост", where(card("Рубио едет в ЦА", summary="Визит включит Кыргызстан.")) == "local")
check("«ЦА» как целевая аудитория не регион", where(card("Как привлечь вашу ЦА: маркетинг для малого бизнеса")) == "local")
check("Technovation в Ташкенте про рост ЦА → Новости из…", where(card("Technovation 2026 в Ташкенте: как инновации способствуют развитию и росту ЦА")) == "pool")
check("слово «ца» внутри слова не регион", where(card("Новый цех открылся в городе")) == "local")
check("чужое мелкое вердикт ИИ «регион» вне пула — как раньше, снимаем",
      where(card("Мэр города подписал бюджет", event_where="US", scale="region")) == "снята")

# ── ЦА не монолит (владелец, 15.10): страны события — из заголовка, а если их там нет, из текста ──
def full(x):
    out = run([x])
    return out[0] if out else None


tech = full(card("Technovation 2026 в Ташкенте: как инновации способствуют развитию и росту ЦА",
                 summary="В форуме участвуют стартапы Казахстана, Таджикистана и Кыргызстана."))
check("Ташкент в заголовке: страна события только UZ, а не все из текста", tech["event_countries"] == "UZ")
check("и для дома (KG) это «Новости из…»", tech["scope"] == "pool")

rubio_all = full(card("Рубио едет в ЦА", summary="Госсекретарь США посетит Бишкек, Ташкент и Алматы."))
check("Рубио: страны из текста + США", rubio_all["event_countries"] == "KG,KZ,US,UZ")
check("Бишкек среди них — для дома местная", rubio_all["scope"] == "local")

rubio_two = full(card("Рубио едет в ЦА", summary="Госсекретарь США посетит Ташкент и Алматы."))
check("Рубио в две страны без дома: KZ, US, UZ", rubio_two["event_countries"] == "KZ,US,UZ")
check("дома нет среди стран — «Новости из…»", rubio_two["scope"] == "pool")

rubio_tj = full(card("Рубио едет в ЦА", summary="Госсекретарь США посетит Душанбе."))
check("только Таджикистан: TJ, US", rubio_tj["event_countries"] == "TJ,US" and rubio_tj["scope"] == "pool")

check("текст страны не назвал — «Новости из…» с флагом региона",
      full(card("Рубио едет в ЦА", summary="Визит запланирован на ноябрь."))["space_wide"] is True)
cn = full(card("Си Цзиньпин едет в ЦА", summary="Он посетит Китай… то есть Казахстан и Узбекистан."))
check("Китай и ЦА: страны пула из текста", "KZ" in cn["event_countries"] and cn["scope"] == "pool")
only_world = full(card("Рубио едет в ЦА", summary="Госсекретарь США встретится с лидерами. Китай обеспокоен."))
check("стран региона не названо, актёры США и Китай — регион без уточнения, «Новости из…»",
      only_world["scope"] == "pool" and only_world["space_wide"] is True and only_world["event_countries"] == "CN,US")
check("реклама «целевая аудитория» не регион", full(card("Как найти свою целевую аудиторию (ЦА) за неделю"))["scope"] == "local")

# ── Правило одно для ВСЕХ пулов (владелец, 15.10): те же регионы и те же полки на es / pt / fr / en ──
ES_SPACE = {"AR", "BO", "CL", "CO", "CR", "CU", "DO", "EC", "ES", "GT", "HN", "NI", "PA", "PE", "PY", "SV", "UY", "VE", "MX"}
PT_SPACE = {"AO", "CV", "GW", "MZ", "PT", "ST", "TL", "BR"}
FR_SPACE = {"BE", "BF", "BJ", "CA", "CD", "CH", "CI", "CM", "DZ", "GN", "HT", "LU", "MA", "MC", "MG", "ML", "NE", "SN", "TG", "TN", "FR"}
EN_SPACE = {"AU", "CA", "GB", "IE", "IN", "JM", "NG", "NZ", "SG", "ZA", "US"}


def pool_card(title, summary="", home="MX", **kw):
    return {"title": title, "summary": summary, "scope": "local", "country": home, "source": "x",
            "category": "NEWS", **kw}


def run_pool(x, home, space):
    with contextlib.redirect_stdout(io.StringIO()):
        out = final_local_foreign_guard([x], "xx", space, home)
    return out[0] if out else None


# es, дом Мексика: «Латинская Америка» — не монолит
r = run_pool(pool_card("El papa visitará América Latina", "Estará en Argentina y Chile en noviembre."), "MX", ES_SPACE)
check("es: Латинская Америка → места AR, CL (+папа как актёр)", r["event_countries"] == "AR,CL,VA")
check("es: Мексики среди стран нет → «Новости из…»", r["scope"] == "pool")
r = run_pool(pool_card("El papa visitará América Latina", "Estará en México y Argentina."), "MX", ES_SPACE)
check("es: Мексика названа в тексте — местная", r["scope"] == "local" and r["event_countries"] == "AR,MX,VA")

# pt, дом Бразилия: «África»
r = run_pool(pool_card("Papa Leão visita a África em março", "Passará por Angola e Moçambique.", home="BR"), "BR", PT_SPACE)
check("pt: África → AO, MZ", r["event_countries"] == "AO,MZ,VA" and r["scope"] == "pool")
r = run_pool(pool_card("Presidente viaja pela África do Sul e Angola", home="BR"), "BR", PT_SPACE)
check("pt: «África do Sul» — страна, не регион", "event_countries" not in r and "space_wide" not in r)

# fr, дом Франция: актёр (Макрон) — не место события
r = run_pool(pool_card("Macron en tournée en Afrique", "Le président sera à Dakar et à Abidjan.", home="FR"), "FR", FR_SPACE)
check("fr: места SN, CI; Франция — актёр", r["event_countries"] == "CI,FR,SN")
check("fr: Франция среди стран → остаётся местной для дома", r["scope"] == "local")

# en, дом США: Latin America, дом назван как актёр
r = run_pool(pool_card("Rubio heads to Latin America", "The Secretary of State will visit Argentina and Mexico.", home="US"), "US", EN_SPACE)
check("en: актёр США есть → местная для американцев", r["scope"] == "local" and "US" in r["event_countries"])

# Кавказ в русском пуле
r = run_pool(pool_card("Лавров отправится на Кавказ", "Он посетит Тбилиси и Ереван.", home="KG"), "KG", SPACE)
check("ru: Кавказ → GE, AM + актёр RU", r["event_countries"] == "AM,GE,RU" and r["scope"] == "pool")

# сравнение с регионом — не регион события: G1 São Paulo 15.10 («…entre metrópoles da América Latina»)
sp = run_pool(pool_card("Chuva reduz velocidade do trânsito de SP; impacto é o maior entre metrópoles da América Latina",
                        "Em São Paulo a lentidão chegou a 15%. Buenos Aires e Bogotá também sofrem.", home="BR"), "BR", PT_SPACE)
check("сравнение с Латинской Америкой в заголовке без страны — не трогаем", sp["scope"] == "local" and "event_countries" not in sp)
check("«ЦА» без названной страны/актёра в заголовке — тоже не трогаем",
      full(card("В ЦА растёт интерес к стартапам", summary="Об этом сообщили в Бишкеке и Алматы."))["scope"] == "local")

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
