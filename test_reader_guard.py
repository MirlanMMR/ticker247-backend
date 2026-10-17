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
          {"n": 2, "problem": "курьёз", "note": "", "dup": None}])
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
kept, dropped = RG.apply(items, shown2, finds)
check("снимает чужое мелкое", a not in kept and len(dropped) == 1 and dropped[0][1]["problem"] == "чужое_мелкое")
check("курьёз, срочность, полку сторож только сообщает", e in kept)
check("срочное и жизненно важное не снимает", d in kept)
check("повтор без указанного двойника не снимает", c in kept)
check("повтор с двойником снимает отмеченную, двойник остаётся",
      RG.apply(items, shown2, [{"n": 3, "problem": "повтор", "note": "", "dup": 1}])[0].count(b) == 1 and c not in RG.apply(items, shown2, [{"n": 3, "problem": "повтор", "note": "", "dup": 1}])[0])
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
check("эталон: подложенных ошибок 7, нормальных 14, все коды известны", sum(1 for x in exp if x) == 7 and all((x is None) or x in RG.PROBLEMS for x in exp))
check("эталон: есть случаи владельца (Секретная служба, кортизол, кабели, пенсионер, повтор, анонс)",
      {x for x in exp if x} >= {"чужое_мелкое", "курьёз", "срочность", "не_новость", "повтор", "анонс"})
check("проверка сторожа подключена к Actions", "python eval_guard.py" in open(".github/workflows/eval_event.yml", encoding="utf-8").read())

print(f"пройдено {ok}, провалено {fail}")
raise SystemExit(1 if fail else 0)
