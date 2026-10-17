# -*- coding: utf-8 -*-
"""Судья «жизненно важное» — vital_ai.py (журнал J61, 17.10.2026).

Случай: G1 Rio «Furtos de cabos deixam imóveis sem luz…» (кража кабелей) висела в шторке с «URGENTE»: слово
«sem luz» поставило vital. Слова теперь только предлагают, решает ИИ; тест — на устройство, не на модель
(модель проверяет eval_vital.py в Actions).
"""
import json

import vital_ai as V

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


NOW = 1_800_000_000_000
H = 3_600_000


def card(title, summary="", scope="local", age_h=1, **kw):
    c = {"title": title, "summary": summary, "scope": scope, "publishedAt": NOW - age_h * H, "url": "u/" + title[:12]}
    c.update(kw)
    return c


THEFT = card("Furtos de cabos deixam imóveis sem luz a cerca de 50 metros de delegacia em São João de Meriti; VÍDEO")
OUTAGE = card("Бүгүн Бишкектин айрым райондорунда суу өчөт")
OUTAGE2 = card("В Бишкеке отключат воду в нескольких районах", "18 октября с 9:00 до 17:00")

# ── слова предлагают кандидатов ──
c = V.candidates([THEFT, OUTAGE, OUTAGE2, card("Футбол: сборная выиграла")], NOW)
check("кандидаты — только то, что поймали слова", len(c) == 3)
check("кража кабелей — кандидат (слова её ловят; решает ИИ)", THEFT in c)
check("не «местные» не рассматриваем", not V.candidates([card("Отключат воду", scope="world")], NOW))
check("старше срока не рассматриваем", not V.candidates([card("Отключат воду", age_h=20)], NOW))
check("потолок кандидатов на один запрос", len(V.candidates([card(f"Отключат воду {i}") for i in range(40)], NOW)) == V.MAX_CANDIDATES)
check("свежие первыми", V.candidates([card("Отключат воду А", age_h=5), card("Отключат воду Б", age_h=1)], NOW)[0]["title"].endswith("Б"))

# ── определение берётся из EDITOR.md, а не копируется ──
md = open("EDITOR.md", encoding="utf-8").read()
d = V.definition_of(md)
check("определение найдено в EDITOR.md (заголовок не переименован)", len(d) > 500 and "НЕ жизненно важное" in d)
check("определение — дословно из EDITOR.md", d in md)
check("нет раздела — пусто, не падает", V.definition_of("# ничего") == "")

# ── запрос к ИИ ──
p = V.build_prompt(d, [THEFT, OUTAGE])
check("в запросе определение, обе карточки и «сомневаешься — false»", "НЕ жизненно важное" in p and "Furtos de cabos" in p and "суу өчөт" in p and "Сомневаешься — false" in p)

# ── разбор ответа и отказ ──
check("ответ ИИ разобран по номерам", V.judge([THEFT, OUTAGE], d, lambda q: '{"1": false, "2": true}') == {1: False, 2: True})
check("ответ в ```json``` и с пояснением тоже разобран", V.judge([THEFT], d, lambda q: 'Вот: ```json\n{"1": false}\n``` готово') == {1: False})
check("ИИ не ответил (исключение) — None, не «всё true»", V.judge([THEFT], d, lambda q: (_ for _ in ()).throw(RuntimeError("503"))) is None)
check("ответ без JSON — None", V.judge([THEFT], d, lambda q: "не знаю") is None)
check("нет кандидатов — запрос не нужен", V.judge([], d, lambda q: 1 / 0) == {})

# ── подключение в конвейер ──
src = open("fetch_news.py", encoding="utf-8").read()
check("mark_vital_local решает ИИ-судья, нет ответа — не помечаем", "_vital_judge(" in src and "ИИ не ответил" in src and "кандидатов не помечены" in src)
check("слова больше не ставят vital сами", "if VITAL_LOCAL.search(text):\n            found.append(it)" not in src)
check("память vital возвращает только подтверждённое ИИ", 'x.get("vitalConfirmed")' in src)
check("набор проверки есть и размечен", len(json.load(open("testdata/vital_golden.json", encoding="utf-8"))) >= 16)
check("проверка судьи подключена к Actions", "python eval_vital.py" in open(".github/workflows/eval_event.yml", encoding="utf-8").read())

print(f"пройдено {ok}, провалено {fail}")
raise SystemExit(1 if fail else 0)
