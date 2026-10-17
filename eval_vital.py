"""Проверка судьи «жизненно важное» на размеченных случаях (J61, 17.10.2026).

Берёт testdata/vital_golden.json (заголовок, начало текста, vital: 1 — будить, 0 — нет), считает точность
СТАРОГО правила (только слова, vital_ai.VITAL_LOCAL) и НОВОГО (слова предлагают, ИИ решает по определению из
EDITOR.md). Каждая жалоба владельца добавляется сюда случаем. Запуск — GitHub Actions (eval_event.yml): ключ
ИИ лежит там; стоит доли цента.

Выход 1, если ИИ-судья ошибся больше, чем слова, или принял хоть одну ложную тревогу (ложная тревога —
уведомление в шторке — дороже пропущенной заметки).
"""
import json
import os
import sys

import google.generativeai as genai

from vital_ai import VITAL_LOCAL, definition_of, judge

MODEL = "gemini-3.1-flash-lite"      # та же модель, что в боевом отборе
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
GOLD = json.load(open("testdata/vital_golden.json", encoding="utf-8"))
DEFINITION = definition_of(open("EDITOR.md", encoding="utf-8").read())


def ask(prompt):
    return genai.GenerativeModel(MODEL).generate_content(prompt).text


def main():
    assert DEFINITION, "определение не найдено в EDITOR.md"
    words = {i + 1: bool(VITAL_LOCAL.search(f"{g['title']} {g['lead']}")) for i, g in enumerate(GOLD)}
    cards = [{"title": g["title"], "lead": g["lead"]} for g in GOLD]
    runs = [judge(cards, DEFINITION, ask) for _ in range(2)]       # модель не детерминирована
    assert all(r is not None for r in runs), "ИИ не ответил"

    def right(ans):
        return sum(1 for i, g in enumerate(GOLD, 1) if bool(ans.get(i)) == bool(g["vital"]))

    def wrong(ans):
        fp = [GOLD[i - 1]["title"][:60] for i in ans if ans[i] and not GOLD[i - 1]["vital"]]
        fn = [GOLD[i - 1]["title"][:60] for i, g in enumerate(GOLD, 1) if not ans.get(i) and g["vital"]]
        return fp, fn
    worst = min(runs, key=right)
    lines = [f"## Только слова (старое правило): верно {right(words)} из {len(GOLD)}"]
    fp, fn = wrong(words)
    lines += [f"- ложные тревоги ({len(fp)}): " + "; ".join(fp), f"- пропущено настоящее ({len(fn)}): " + "; ".join(fn)]
    for name, ans in (("ИИ-судья", max(runs, key=right)), ("ИИ-судья (худший прогон)", worst)):
        fp, fn = wrong(ans)
        lines += [f"## {name}: верно {right(ans)} из {len(GOLD)}",
                  f"- ложные тревоги ({len(fp)}): " + "; ".join(fp), f"- пропущено настоящее ({len(fn)}): " + "; ".join(fn)]
    report = "\n".join(lines)
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        open(summary, "a", encoding="utf-8").write(report + "\n")
    fp_worst, _ = wrong(worst)
    print(f"\nИТОГ: слова {right(words)}/{len(GOLD)}, ИИ {right(worst)}/{len(GOLD)} (худший), ложных тревог у ИИ: {len(fp_worst)}")
    sys.exit(0 if right(worst) >= right(words) and not fp_worst else 1)


if __name__ == "__main__":
    main()
