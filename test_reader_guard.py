# -*- coding: utf-8 -*-
"""Сторож — reader_guard.py (журнал J63, 17.10.2026).

ИИ просматривает собранную ленту глазами читателя; тест — на устройство (экран, запрос, разбор, отказ, боевые
действия), а не на модель: модель проверяет eval_guard.py в Actions на testdata/guard_golden.json.
"""
import json

import reader_guard as RG

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


def card(title, scope="world", t=100, **kw):
    c = {"title": title, "summary": "Текст новости.", "scope": scope, "source": "Src", "event_where": "US",
         "category": "NEWS", "priority": 0, "publishedAt": t}
    c.update(kw)
    return c


a = card("Мировая новость А", "world", 5)
b = card("Местная новость Б", "local", 9)
c = card("Соседи В", "pool", 7)
d = card("Срочное Г", "local", 3, category="URGENT", priority=2)
e = card("Интересное Д", "world", 8, interesting=True)
fx = card("Курс доллара", "local", 10, category="CURRENCY")
items = [a, b, c, d, e, fx]

# ── экран ──
shown = RG.screen(items)
check("порядок экрана: местные, соседи, мировые", [x["scope"] for x in shown] == ["local", "local", "pool", "world", "world"])
check("внутри полки свежее выше", shown[0] is b and shown[1] is d and shown[3] is e)
check("финансовые карточки не показываем", fx not in shown)
many = [card(f"М{i}", "world", i) for i in range(RG.PER_SHELF + 20)]
check("потолок карточек на полку", len(RG.screen(many)) == RG.PER_SHELF)

# ── запрос ──
p = RG.build_prompt(shown, "ru", "KG")
check("в запросе заголовки полок и плашки", "=== МЕСТНЫЕ ===" in p and "=== МИРОВЫЕ ===" in p and "[СРОЧНО]" in p and "[интересное]" in p)
check("в запросе пул и страна читателя", "«ru»" in p and "KG" in p)
check("в запросе все коды проблем", all(code in p for code in RG.PROBLEMS))
check("в запросе ошибки владельца примерами (Секретная служба, кортизол, кабели, казахстанцы)",
      "Секретной службы" in p and "Кортизол" in p and "Кража кабелей" in p and "казахстанцев" in p)
check("в запросе оговорки от ложных обвинений (срочное объявление, последствия за границей, развитие сюжета)", "НЕ включай:" in p and "жизненно важное, плашка верна" in p and "РАЗНЫМИ фактами" in p)
check("«сомневаешься — не включай»", "Сомневаешься — не включай" in p)
check("определений в запросе нет (их даёт EDITORIAL.md как системная инструкция)", "Белый список" not in p)

# ── разбор ──
good = '[{"n": 2, "problem": "курьёз", "note": "находка"}, {"n": 4, "problem": "повтор", "dup": 1, "note": "то же"}]'
fs = RG.parse(good, 5)
check("находки разобраны", [(f["n"], f["problem"]) for f in fs] == [(2, "курьёз"), (4, "повтор")] and fs[1]["dup"] == 1)
check("ответ в ```json``` и с пояснением разобран", len(RG.parse('Вот:\n```json\n' + good + '\n```', 5)) == 2)
check("неизвестный код, номер вне экрана и дубль номера отброшены",
      RG.parse('[{"n": 9, "problem": "курьёз"}, {"n": 1, "problem": "чушь"}, {"n": 2, "problem": "курьёз"}, {"n": 2, "problem": "повтор", "dup": 1}]', 5) == [
          {"n": 2, "problem": "курьёз", "note": "", "dup": None, "country": None}])
check("пустой массив — нет находок", RG.parse("[]", 5) == [])
check("двойник вне экрана игнорируется", RG.parse('[{"n": 2, "problem": "повтор", "dup": 99}]', 5)[0]["dup"] is None)
check("потолок находок", len(RG.parse(json.dumps([{"n": i, "problem": "курьёз"} for i in range(1, 60)]), 60)) == RG.MAX_FINDINGS)

# ── отказ ИИ: лента как была ──
check("ИИ не ответил — None, не «всё хорошо»", RG.review(items, "ru", "KG", lambda q: (_ for _ in ()).throw(RuntimeError("503"))) is None)
check("ответ без JSON — None", RG.review(items, "ru", "KG", lambda q: "всё нормально") is None)
sh, found = RG.review(items, "ru", "KG", lambda q: good)
check("review отдаёт показанные карточки и находки", len(sh) == 5 and len(found) == 2)
check("пустая лента — запрос не нужен", RG.review([], "ru", "KG", lambda q: 1 / 0) == ([], []))

# ── боевой режим ──
shown2 = RG.screen(items)           # b, d, c, e, a
finds = [{"n": 5, "problem": "чужое_мелкое", "note": "", "dup": None},      # a — снимается
         {"n": 4, "problem": "курьёз", "note": "", "dup": None},             # e — только отчёт
         {"n": 2, "problem": "не_новость", "note": "", "dup": None},         # d срочное — не снимается
         {"n": 3, "problem": "повтор", "note": "", "dup": None}]             # c без двойника — не снимается
_floor = RG.SHELF_FLOOR
RG.SHELF_FLOOR = 0        # эти проверки — про классы проблем, а не про пол полки (он проверяется ниже)
kept, dropped = RG.apply(items, shown2, finds)
check("снимает чужое мелкое", a not in kept and len(dropped) == 1 and dropped[0][1]["problem"] == "чужое_мелкое")
check("курьёз, срочность, полку сторож только сообщает", e in kept)
check("срочное и жизненно важное не снимает", d in kept)
check("повтор без указанного двойника не снимает", c in kept)
check("повтор с двойником снимает отмеченную, двойник остаётся",
      RG.apply(items, shown2, [{"n": 3, "problem": "повтор", "note": "", "dup": 1}])[0].count(b) == 1 and c not in RG.apply(items, shown2, [{"n": 3, "problem": "повтор", "note": "", "dup": 1}])[0])
RG.SHELF_FLOOR = _floor
vc = card("Жизненно важное", "local", vital=True)
check("vital не снимается", RG.apply([vc], [vc], [{"n": 1, "problem": "не_новость", "note": "", "dup": None}])[0] == [vc])

# ── подключение ──
src = open("fetch_news.py", encoding="utf-8").read()
check("конвейер зовёт сторожа до пункта пропуска", src.index("reader_guard_step(filtered, lang)") < src.index("border.control(filtered, lang"))
check("режим по умолчанию — тень, выключается READER_GUARD=off", 'os.environ.get("READER_GUARD") or "shadow"' in src and 'READER_GUARD_MODE == "off"' in src)
check("в режиме тени лента не меняется (live снимает через RG.apply)", 'if READER_GUARD_MODE == "live":' in src and "RG.apply(" in src)
check("системная инструкция — EDITORIAL.md (charter=True)", "ask_gemini(p, charter=True)" in src)
check("отчёт guard_report.md пишется и коммитится", "guard_report.md" in src and "guard_report.md" in open(".github/workflows/fetch.yml", encoding="utf-8").read())

# ── эталонный набор и проверка ──
gold = json.load(open("testdata/guard_golden.json", encoding="utf-8"))
exp = [g["expected"] for g in gold]
check("эталон: подложенных ошибок 9, нормальных 15, все коды известны", sum(1 for x in exp if x) == 9 and all((x is None) or x in RG.PROBLEMS for x in exp))
check("эталон: есть случаи владельца (Секретная служба, кортизол, кабели, пенсионер, повтор, анонс)",
      {x for x in exp if x} >= {"чужое_мелкое", "курьёз", "срочность", "не_новость", "повтор", "анонс"})
check("проверка сторожа подключена к Actions", "python eval_guard.py" in open(".github/workflows/eval_event.yml", encoding="utf-8").read())

# ── J73 (04.11): метка места исправляется, карточка остаётся; предохранители боевого режима ──
onl = card("Самосвал задел высоковольтную линию и загорелся — водитель погиб", "pool", 50, event_where="KG", country="BY",
           event_countries="KG")
raw = '[{"n": 1, "problem": "метка_места", "country": "by", "note": "белорусское издание о Беларуси"}]'
fs = RG.parse(raw, 1)
check("parse: код страны из ответа сторожа, в верхнем регистре", fs and fs[0]["country"] == "BY")
check("parse: плохой код страны отбрасывается", RG.parse('[{"n": 1, "problem": "метка_места", "country": "Беларусь"}]', 1)[0]["country"] is None)
done = RG.relabel([onl], fs)
check("relabel: метка места KG → BY, старая запомнена", onl["event_where"] == "BY" and onl["_event_where_ai"] == "KG" and len(done) == 1)
check("relabel: список стран события тоже исправлен", onl["event_countries"] == "BY")
card2 = card("Карточка без страны издания", "pool", 40, event_where="KG", country="")
RG.relabel([card2], [{"n": 1, "problem": "метка_места", "country": None, "note": ""}])
check("relabel: без кода и без страны издания метку не трогаем", card2["event_where"] == "KG")
kept, dropped = RG.apply([onl], [onl], fs)
check("метка_места карточку не снимает", kept == [onl] and not dropped)
check("в подсказке сторожа видно и издание, и событие", "издание: BY" in RG.build_prompt([onl], "ru", "KG") and "метка_места" in RG.build_prompt([onl], "ru", "KG"))

many = [card(f"Мелкая чужая {i}", "pool", i) for i in range(40)]
finds = [{"n": i + 1, "problem": "чужое_мелкое", "note": "", "dup": None, "country": None} for i in range(40)]
kept, dropped = RG.apply(many, many, finds)
check("предохранитель: снимается не больше четверти показанного", len(dropped) <= 10 and len(kept) >= 30)
few = [card(f"Полка {i}", "pool", i) for i in range(7)]
kept, dropped = RG.apply(few, few, [{"n": i + 1, "problem": "чужое_мелкое", "note": "", "dup": None, "country": None} for i in range(7)])
check("предохранитель: полка не опускается ниже пола 6", len(kept) >= 6)
wf = open(".github/workflows/fetch.yml", encoding="utf-8").read()
check("боевые режимы включены в fetch.yml (решение владельца 04.11)", "READER_GUARD: live" in wf and "STANDARD_FIX: live" in wf)

# ── J71: ложное «срочно» понижается, карточка остаётся ──
bus = card("В Бишкеке с 5 ноября изменятся схемы движения автобусных маршрутов", "local", 60, category="URGENT", priority=2, event_where="KG")
d = RG.demote([bus], [{"n": 1, "problem": "срочность", "note": "плановое объявление", "dup": None, "country": None}])
check("demote: URGENT → NEWS, приоритет ≤ 1, карточка остаётся", bus["category"] == "NEWS" and bus["priority"] == 1 and len(d) == 1)
vit = card("Отключение воды в Оше", "local", 61, category="URGENT", priority=3, vital=True)
RG.demote([vit], [{"n": 1, "problem": "срочность", "note": "", "dup": None, "country": None}])
check("demote: жизненно важное (vital) не понижается", vit["category"] == "URGENT" and vit["priority"] == 3)
plain = card("Обычная новость", "local", 62)
check("demote: обычную карточку не трогает", RG.demote([plain], [{"n": 1, "problem": "срочность", "note": "", "dup": None, "country": None}]) == [] and plain["priority"] == 0)
check("в подсказке сторожа пример планового «срочно»", "плановое объявление" in RG.build_prompt([bus], "ru", "KG"))

print(f"пройдено {ok}, провалено {fail}")
raise SystemExit(1 if fail else 0)
