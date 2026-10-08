"""Полки стран (country_shelves.py): чистые функции без сети и ключей."""
import json
import sys

import country_shelves as cs

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else: fail += 1; print(f"  ✗ {name}")

TOPICS = {"politics", "society", "economy", "incidents"}
feeds = cs.load_json("country_feeds.json")
langs = cs.load_json("country_langs.json")

check("ленты 64 стран перенесены", len(feeds) == 64 and sum(len(v) for v in feeds.values()) == 129)
check("у каждой страны с лентами есть языки", all(c in langs for c in feeds))
check("Молдова: румынский", langs["MD"] == ["ro"])
check("у стран пулов есть названия", all(c in cs.COUNTRY_NAMES for c in feeds))

# ─── Цели ───
pc = {"ru": {"KZ", "MD", "KG", "RU", "UA"}, "en": {"CA", "US", "GB"}, "fr": {"CA", "BE", "FR"}}
tg = cs.targets(pc, feeds)
check("жирные дома (KG, US, RU) не берём", not any(i in ("KG", "US", "RU") for _, i in tg))
check("Канада — в двух пулах, у каждого своя полка", ("en", "CA") in tg and ("fr", "CA") in tg)
check("фильтр по странам", cs.targets(pc, feeds, only={"MD"}) == [("ru", "MD")])

# ─── Язык ───
c = lambda t, s="": {"title": t, "summary": s}
check("MD: румынский по служебным словам",
      cs.label_language(c("Călătoriile cu transportul public vor fi plătite electronic", "CMC a aprobat sistemul de plată în capitală"), "ru", ["ro"]) == "ro")
check("MD: русский", cs.label_language(c("Санду встретилась с руководством НАТО"), "ru", ["ro"]) == "ru")
check("KZ: казахский по буквам", cs.label_language(c("Қазақстанда жаңа мектеп ашылды және оқушылар үшін"), "ru", ["kk"]) == "kk")
check("AM: армянский по письму", cs.label_language(c("Հայաստանում նոր դպրոց բացվեց"), "ru", ["hy"]) == "hy")
check("GE: грузинский по письму", cs.label_language(c("საქართველოში ახალი სკოლა გაიხსნა"), "ru", ["ka"]) == "ka")
check("CA (английский пул): французский",
      cs.label_language(c("Le gouvernement a annoncé de nouvelles mesures pour les familles", "Les mesures sont dans le budget"), "en", ["en", "fr"]) == "fr")
check("CA (английский пул): английский",
      cs.label_language(c("The government has announced new measures for the families"), "en", ["en", "fr"]) == "en")
check("BE (французский пул): нидерландский",
      cs.label_language(c("De regering heeft nieuwe maatregelen aangekondigd voor het gezin", "Het is een besluit van de minister"), "fr", ["fr", "nl"]) == "nl")
check("текст без букв — языка нет", cs.label_language(c("12345 !!!"), "ru", ["ro"]) is None)

# ─── Свежесть, дубли ───
now = 10_000_000_000
items = [{"url": "a", "title": "A", "publishedAt": now - 1000}, {"url": "a", "title": "A2", "publishedAt": now - 500},
         {"url": "old", "title": "Old", "publishedAt": now - cs.FRESH_MS - 1}, {"url": "b", "title": "B", "publishedAt": now - 2000}]
fu = cs.fresh_unique(items, now, 10)
check("дубль адреса и старьё убраны", [x["url"] for x in fu] == ["a", "b"])
check("лимит кандидатов", len(cs.fresh_unique(items, now, 1)) == 1)

# ─── Разбор ответа ИИ ───
v = cs.parse_verdict('вот ответ {"keep": [1, 3], "urgent": [3], "important": [1], "where": {"1": "md", "2": "-"}, '
                     '"world": [2], "region": [], "topic": {"1": "politics", "9": "politics", "2": "nonsense"}}', 3, TOPICS)
check("keep/urgent/important по номерам", v["keep"] == {0, 2} and v["urgent"] == {2} and v["important"] == {0})
check("where и масштаб", v["where"][0] == "MD" and v["where"][1] is None and v["scale"][1] == "world")
check("тема только из списка и в пределах порции", v["topic"] == {0: "politics"})
check("мусор вместо JSON → None", cs.parse_verdict("извините, не могу", 3, TOPICS) is None)
check("JSON не словарь → None", cs.parse_verdict("[1, 2]", 3, TOPICS) is None)
check("keep не списком не роняет", cs.parse_verdict('{"keep": "всё"}', 3, TOPICS)["keep"] == set())

# ─── Сборка полки ───
def card(i, title, t, lang="ru", **k):
    return dict(url=f"u{i}", title=title, summary="", source="S", category="NEWS", publishedAt=t, language=lang, **k)
its = [card(0, "Мэрия планирует построить парк", 5), card(1, "Мэрия построила парк", 4), card(2, "Нужная новость", 3),
       card(3, "Убрана ИИ", 2)]
verdict = {"keep": {0, 1, 2}, "urgent": {2}, "important": {1}, "where": {1: "MD"}, "scale": {1: "local"}, "topic": {1: "society"}}
shelf = cs.assemble(its, verdict, "MD", "ru", ["ro"])
check("убранное ИИ не попало на полку", all(x["title"] != "Убрана ИИ" for x in shelf))
check("страна и полка проставлены", all(x["country"] == "MD" and x["scope"] == "local" for x in shelf))
check("намерение помечено noEvent (не в карусель), но осталось в ленте",
      next(x for x in shelf if "планирует" in x["title"]).get("noEvent") is True and len(shelf) == 3)
check("срочная получила категорию", next(x for x in shelf if x["title"] == "Нужная новость")["category"] == "URGENT_LOCAL_ONLY")
check("свежее сверху", [x["publishedAt"] for x in shelf] == sorted((x["publishedAt"] for x in shelf), reverse=True))
many = [card(i, f"Новость {i}", i) for i in range(30)]
check("не больше 12 на страну", len(cs.assemble(many, {"keep": set(range(30)), "urgent": set(), "important": set(), "where": {}, "scale": {}, "topic": {}}, "KZ", "ru", ["kk"])) == 12)
three = [card(i, f"Срочное {i}", i) for i in range(5)]
sh3 = cs.assemble(three, {"keep": set(range(5)), "urgent": set(range(5)), "important": set(), "where": {}, "scale": {}, "topic": {}}, "KZ", "ru", ["kk"])
check("срочных не больше двух", sum(1 for x in sh3 if x["category"] == "URGENT_LOCAL_ONLY") == 2)
mixed = [card(i, f"Русская {i}", 10 + i) for i in range(2)] + [card(10 + i, f"Роднаяя {i}", i, lang="ky") for i in range(6)]
shm = cs.assemble(mixed, {"keep": set(range(8)), "urgent": set(), "important": set(), "where": {}, "scale": {}, "topic": {}}, "KG", "ru", ["ky"])
check("потолок 50/50: родной не больше половины", sum(1 for x in shm if x["language"] == "ky") <= len(shm) / 2)

# Армения: обе ленты по-армянски — потолок 50/50 не должен снести всю полку
am = [card(i, "Հայաստանում նոր դպրոց բացվեց", i, lang="hy") for i in range(5)]
sham = cs.assemble(am, {"keep": set(range(5)), "urgent": set(), "important": set(), "where": {}, "scale": {}, "topic": {}}, "AM", "ru", ["hy"])
check("Армения: полка из одного родного языка остаётся", len(sham) == 5)
# Грузия: английский не читает местный читатель — не на полку
ge = [card(0, "Georgia expelled around 3,300 foreign nationals as of October 2026 according to the data", 5),
      card(1, "Сообщение по-русски об открытии школы в Тбилиси", 4)]
shge = cs.assemble(ge, {"keep": {0, 1}, "urgent": set(), "important": set(), "where": {}, "scale": {}, "topic": {}}, "GE", "ru", ["ka"])
check("Грузия: английский текст отфильтрован, русский остался", [x["title"][:7] for x in shge] == ["Сообщен"])
check("английский определяется как en, а не ru (Грузия)",
      cs.label_language(c("Georgia expelled around 3,300 foreign nationals as of October 2026 according to the data"), "ru", ["ka"]) == "en")
ca = [card(i, f"The government has announced new measures for the families number {i}", i, lang="en") for i in range(4)]
shca = cs.assemble(ca, {"keep": set(range(4)), "urgent": set(), "important": set(), "where": {}, "scale": {}, "topic": {}}, "CA", "fr", ["en", "fr"])
check("fr/CA: английские карточки без французских остаются (читает оба языка)", len(shca) == 4)

print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
