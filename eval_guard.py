"""Проверка сторожа на эталонной ленте (J63, 17.10.2026): подложенные ошибки владельца и нормальные карточки.

testdata/guard_golden.json — экран ru-пула (дом KG): у каждой карточки `expected` — код проблемы или null.
Считаем: поймано ли подложенное (любым кодом / нужным кодом) и сколько нормальных карточек сторож зря
обвинил. Определения даёт EDITORIAL.md как системная инструкция — как в боевом прогоне. Запуск — Actions
(eval_event.yml); ключ ИИ там. Стоит доли цента.
"""
import json
import os
import sys

import google.generativeai as genai

import reader_guard as RG

MODEL = "gemini-3.1-flash-lite"
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
EDITORIAL = open("EDITORIAL.md", encoding="utf-8").read()
GOLD = json.load(open("testdata/guard_golden.json", encoding="utf-8"))


def ask(prompt):
    return genai.GenerativeModel(MODEL, system_instruction=EDITORIAL).generate_content(prompt).text


def one_run():
    items = [dict(g["item"]) for g in GOLD]
    for i, x in enumerate(items):
        x["_gold"] = GOLD[i]["expected"]
    res = RG.review(items, "ru", "KG", ask)
    assert res is not None, "ИИ не ответил"
    shown, findings = res
    by_n = {f["n"]: f for f in findings}
    seeded = [(n, x) for n, x in enumerate(shown, 1) if x["_gold"]]
    caught_any = [x["title"][:55] for n, x in seeded if n in by_n]
    caught_exact = [x["title"][:55] for n, x in seeded if n in by_n and by_n[n]["problem"] == x["_gold"]]
    missed = [(x["title"][:55], x["_gold"]) for n, x in seeded if n not in by_n]
    false = [(x["title"][:55], by_n[n]["problem"]) for n, x in enumerate(shown, 1) if not x["_gold"] and n in by_n]
    return len(seeded), caught_any, caught_exact, missed, false, len(shown)


def main():
    runs = [one_run() for _ in range(2)]               # модель не детерминирована
    lines = []
    for i, (total, any_, exact, missed, false, n) in enumerate(runs, 1):
        lines += [f"## Прогон {i}: подложено {total} ошибок из {n} карточек",
                  f"- поймано любым кодом: {len(any_)}; тем самым кодом: {len(exact)}",
                  f"- пропущено ({len(missed)}): " + "; ".join(f"{t} [{c}]" for t, c in missed),
                  f"- ложные обвинения нормальных ({len(false)}): " + "; ".join(f"{t} [{c}]" for t, c in false)]
    report = "\n".join(lines)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        open(summary, "a", encoding="utf-8").write(report + "\n")
    worst_false = max(len(r[4]) for r in runs)
    worst_caught = min(len(r[1]) for r in runs)
    print(f"\nИТОГ: поймано {worst_caught}/{runs[0][0]} (худший прогон), ложных обвинений до {worst_false}")
    sys.exit(0)        # тень: набор меряет, но не валит прогон


if __name__ == "__main__":
    main()
