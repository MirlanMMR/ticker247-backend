"""Сравнение вариантов перевода на настоящих карточках (09.10.2026).

Поводом стала находка владельца: Fortune про Гвинн Шотвелл — лёгкая модель перевернула смысл
заголовка, потеряла слово «акции» и сломала падеж в тексте. Скрипт берёт из боевой ленты
переведённые карточки (в них хранится оригинал: origTitle/origSummary) и переводит их заново
четырьмя способами:

  A — промпт версии 1 + основная модель (как сейчас в бою)
  B — промпт версии 2 + основная модель
  C — промпт версии 2 + gemini-2.5-flash
  D — промпт версии 1 + gemini-2.5-flash

Печатает рядом оригинал и четыре перевода — читать глазами (владелец читает по-русски).
Запуск — только в GitHub Actions (eval_translation.yml): там ключ ИИ. Лента и база не
трогаются, стоит несколько центов. fetch_news не импортируем: ему на импорте нужен Firebase.
"""
import json
import os
import sys
import urllib.request

import google.generativeai as genai

import translate_prompt as T

BASE = "gemini-3.1-flash-lite"       # основная модель боя (fetch_news.GEMINI_MODEL)
STRONG = "gemini-2.5-flash"
VARIANTS = {"A v1+основная": (1, BASE), "B v2+основная": (2, BASE),
            "C v2+2.5-flash": (2, STRONG), "D v1+2.5-flash": (1, STRONG)}
POOL = (sys.argv[1] if len(sys.argv) > 1 else "ru")
LIMIT = int(sys.argv[2]) if len(sys.argv) > 2 else 14

genai.configure(api_key=os.environ["GEMINI_API_KEY"])


def ask(prompt, model):
    return genai.GenerativeModel(model).generate_content(prompt).text


def parse(text, n):
    if "```" in text:
        text = text.split("```")[1].replace("json", "").strip()
    data = json.loads(text)
    return [((data.get(str(i)) or {}).get("title", "").strip(), (data.get(str(i)) or {}).get("summary", "").strip())
            for i in range(1, n + 1)]


url = "https://ticker247-default-rtdb.asia-southeast1.firebasedatabase.app/news/%s/items.json" % POOL
raw = json.load(urllib.request.urlopen(url, timeout=30))
items = list(raw.values()) if isinstance(raw, dict) else raw
cands = [x for x in items if x.get("translated") and x.get("origTitle") and x.get("origSummary")]
# Шотвелл — первым, это контрольный случай владельца
cands.sort(key=lambda x: 0 if "Shotwell" in (x.get("origTitle") or "") else 1)
cands = cands[:LIMIT]
src = [{"title": x["origTitle"], "summary": x["origSummary"]} for x in cands]
print(f"Карточек для сравнения: {len(src)} (пул {POOL})\n")

out = {}
for name, (ver, model) in VARIANTS.items():
    try:
        out[name] = parse(ask(T.build(src, POOL, ver), model), len(src))
    except Exception as e:
        print(f"⚠️ {name}: {str(e)[:100]}")
        out[name] = [("", "")] * len(src)

for i, x in enumerate(cands):
    print("=" * 100)
    print(f"[{i + 1}] {x.get('source')}\nОРИГИНАЛ: {x['origTitle']}\n         {x['origSummary'][:260].replace(chr(10), ' ')}")
    for name in VARIANTS:
        t, s = out[name][i]
        print(f"\n  {name}\n   З: {t}\n   Т: {s[:260].replace(chr(10), ' ')}")
print("\nГотово.")
