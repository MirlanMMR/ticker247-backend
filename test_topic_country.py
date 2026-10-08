"""Тема не из страны пула → «Мировые» (topic_country.py), 08.10.2026."""
import sys
from topic_country import foreign_topic, final_foreign_topic_guard, outside_in_title

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1
    else: fail += 1; print(f"  ✗ {name}")

RU = {"KZ", "UZ", "TJ", "RU", "BY", "AM", "AZ", "GE", "MD", "TM", "KG"}
P = lambda title, **k: dict(scope="pool", title=title, summary=k.pop("summary", ""), **k)

# Владелец: «новости про Америку от узбекских изданий — не в Новости из»
check("США в заголовке узбекского издания", foreign_topic(P("Трамп заявил о новых пошлинах для стран ЕАЭС", country="UZ"), RU))
check("«американские» учёные", foreign_topic(P("В США создали препарат против диабета"), RU))
check("Китай", foreign_topic(P("Китай ввёл ограничения на экспорт редкоземельных металлов"), RU))
check("Украина вне пула ru", foreign_topic(P("Украина сообщила о новых ударах по Киеву"), RU))
# Свою страну назвали — остаётся
check("«Узбекистан и США подписали» — своя названа", not foreign_topic(P("Узбекистан и США подписали соглашение о торговле"), RU))
check("своя страна в начале текста", not foreign_topic(P("Трамп приедет в регион", summary="Визит в Ташкент намечен на весну"), RU))
check("сосед по пулу — не чужое", not foreign_topic(P("Россия и Казахстан обсудили поставки газа"), RU))
check("новость о своём без чужих", not foreign_topic(P("В Ташкенте открылся новый рынок"), RU))
# Не трогаем
check("страна события известна — не здесь", not foreign_topic(P("Трамп заявил", event_where="US"), RU))
check("не pool — не трогаем", not foreign_topic(dict(scope="world", title="Трамп заявил"), RU))
check("мост не трогаем", not foreign_topic(P("Наши в США", bridge=True), RU))
check("«газ» — не Газа", not foreign_topic(P("Тарифы на газ вырастут в Ташкенте"), RU))
check("слово 'Саша' — не США", outside_in_title("Саша открыл кафе", RU) is None)
# Другие пулы: пул fr, пространство — Бельгия/Швейцария/… (США вне)
FR = {"BE", "CH", "CA", "SN", "CI", "MA", "TN", "DZ", "CD", "CM", "FR"}
check("fr: Trump во французском пуле у бельгийского издания", foreign_topic(P("Trump annonce de nouveaux droits de douane", country="BE"), FR))
check("fr: Canada — своё пространство", not foreign_topic(P("Le Canada annonce un budget militaire"), FR))
# Страж
it = [P("Трамп заявил о пошлинах", source="s", sourceCount=3), P("В США закрыли школу", source="s"),
      P("В Ташкенте открылся рынок", source="s")]
out = final_foreign_topic_guard(it, "ru", RU)
check("страж: весомое → мировое, лёгкое чужое → долой, своё осталось",
      [(x["title"], x["scope"]) for x in out] == [("Трамп заявил о пошлинах", "world"), ("В Ташкенте открылся рынок", "pool")])
it = [P("Школа в США закрыта", source="s", scale="local"), P("Трамп ввёл пошлины", source="s", scale="world")]
out = final_foreign_topic_guard(it, "ru", RU)
check("масштаб решает: local долой, world мировая", [(x["scope"]) for x in out] == ["world"])

from topic_country import final_local_foreign_guard as LFG
L = lambda title, **k: dict(scope="local", title=title, summary=k.pop("summary", ""), **k)
SP2 = RU | {"KG"}
_o = LFG([L("Сооснователь Anthropic опасается, что создал нечто, обреченное на «вечные муки»", event_where="US", scale="local")], "ru", SP2, "KG")
check("Anthropic на «Местных»: чужое событие, про КР нет — снято", _o == [])
_o = LFG([L("Трое кыргызстанцев задержаны в Москве", event_where="RU", scale="local")], "ru", SP2, "KG")
check("мост: наши в Москве остаются местными", [x["scope"] for x in _o] == ["local"])
_o = LFG([L("Садыр Жапаров прилетел в Туркменистан", event_where="TM", scale="local")], "ru", SP2, "KG")
check("Жапаров за границей — местное", [x["scope"] for x in _o] == ["local"])
_o = LFG([L("Пакистан разместил войска в Саудовской Аравии", event_where="SA", scale="world")], "ru", SP2, "KG")
check("мировой масштаб → Мировые", [x["scope"] for x in _o] == ["world"])
_o = LFG([L("Президент Казахстана подписал закон", event_where="KZ", scale="local")], "ru", SP2, "KG")
check("событие в стране пула → Новости из", [x["scope"] for x in _o] == ["pool"])
_o = LFG([L("Любопытная находка в Тихом океане", event_where="US", scale="local", interesting=True)], "ru", SP2, "KG")
check("интересное не трогаем", [x["scope"] for x in _o] == ["local"])
_o = LFG([L("Дом обрушился в Бишкеке", event_where="KG", scale="local")], "ru", SP2, "KG")
check("событие дома — местное", [x["scope"] for x in _o] == ["local"])

print(f"пройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
