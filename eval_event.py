"""Проверка определения «событие» на размеченных заголовках (06.10.2026).

Берёт testdata/event_golden.json (заголовок, начало текста, разметка: 1 — событие,
0 — не событие) и просит ИИ классифицировать каждый материал дважды: по СТАРОМУ
определению (testdata/event_definition_old.txt) и по НОВОМУ (белый список из
EDITORIAL.md). Печатает точность и расхождения. Запуск — в GitHub Actions
(eval_event.yml): ключ ИИ лежит там. Стоит несколько центов.
"""
import json
import os
import re
import sys

from fetch_news import ask_gemini

GOLD = json.load(open("testdata/event_golden.json", encoding="utf-8"))
OLD = open("testdata/event_definition_old.txt", encoding="utf-8").read()
EDITORIAL = open("EDITORIAL.md", encoding="utf-8").read()
a = EDITORIAL.index("## Что такое событие и новость")
NEW = EDITORIAL[a:EDITORIAL.index("## Этикет — не новость")]


def classify(definition):
    cards = "\n".join(f"{i + 1}. {g['title']} — {g['lead']}" for i, g in enumerate(GOLD))
    prompt = (f"Ты выпускающий редактор новостного приложения. Определение события и новости:\n\n"
              f"{definition}\n\nДля каждого материала реши: СОБЫТИЕ (1) или НЕ СОБЫТИЕ (0) по этому "
              f"определению. Верни ТОЛЬКО JSON вида {{\"1\": 1, \"2\": 0, ...}} по всем номерам.\n\n{cards}")
    raw = ask_gemini(prompt, charter=False)
    m = re.search(r"\{.*\}", raw, re.S)
    data = json.loads(m.group(0))
    return {int(k): int(v) for k, v in data.items()}


def score(name, answer):
    right = sum(1 for i, g in enumerate(GOLD) if answer.get(i + 1) == g["event"])
    fp = [GOLD[i - 1]["title"] for i, v in answer.items() if v == 1 and GOLD[i - 1]["event"] == 0]
    fn = [GOLD[i - 1]["title"] for i, v in answer.items() if v == 0 and GOLD[i - 1]["event"] == 1]
    lines = [f"## {name}: верно {right} из {len(GOLD)}",
             f"- принято за событие, а это слова ({len(fp)}): " + "; ".join(t[:60] for t in fp),
             f"- потеряно настоящее событие ({len(fn)}): " + "; ".join(t[:60] for t in fn)]
    return right, "\n".join(lines)


def main():
    results = {}
    for name, text in (("СТАРОЕ определение", OLD), ("НОВОЕ (белый список)", NEW)):
        runs = [classify(text) for _ in range(2)]            # два прогона: модель не детерминирована
        best = max(runs, key=lambda r: sum(1 for i, g in enumerate(GOLD) if r.get(i + 1) == g["event"]))
        results[name] = score(name, best)
        results[name + " (худший)"] = score(name + " (худший прогон)", min(
            runs, key=lambda r: sum(1 for i, g in enumerate(GOLD) if r.get(i + 1) == g["event"])))
    report = "\n\n".join(v[1] for v in results.values())
    print(report)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        open(summary, "a", encoding="utf-8").write(report + "\n")
    old, new = results["СТАРОЕ определение"][0], results["НОВОЕ (белый список)"][0]
    print(f"\nИТОГ: старое {old}/{len(GOLD)}, новое {new}/{len(GOLD)}")
    sys.exit(0 if new >= old else 1)


if __name__ == "__main__":
    main()
