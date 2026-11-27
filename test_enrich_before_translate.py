# -*- coding: utf-8 -*-
"""J80 (27.11.2026): текст по правилу абзацев — ДО перевода; перевод не режет его до 900 знаков.

ru 27.11: все 15 «коротких» карточек — переведённые иностранные (Straits Times, Engadget, El Mundo…). Причина:
`_gemini_translate` брал `summary[:900]`, дотяжка «переведённых не трогает», память переводов (ключ — адрес)
возвращала старый короткий перевод. Замок: (1) текст собирается до перевода и помечается `_ruled`;
(2) правило абзацев повторно не режет такой текст (в основном пути, у запасных, у редактора);
(3) длинные тексты переводятся малыми порциями; (4) память верна только для того же исходного текста."""
import os
import sys
from unittest.mock import MagicMock

for m in ("google.generativeai", "firebase_admin", "firebase_admin.credentials", "firebase_admin.db"):
    sys.modules[m] = MagicMock()
import google
google.generativeai = sys.modules["google.generativeai"]
os.environ.setdefault("GEMINI_API_KEY", "x")
os.environ["FIREBASE_SERVICE_ACCOUNT"] = "{}"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_news as F
import editor as ED
import textcut as TC

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


def para(i, n=300):
    return (f"Абзац {i}. " + "слово " * 80)[:n].rstrip() + "."


ART = "\n\n".join(para(i) for i in range(1, 12))          # 11 абзацев → правило даёт 8
RULE = TC.card_text(ART)


def foreign(**kw):
    return {"title": "Title", "summary": "One sentence from RSS.", "url": "https://x.test/a", "language": "en",
            "source": "T", "scope": "world", **kw}


def fake_enrich(items, budget=0, annotations_too=False, **k):
    for x in items:
        x["_article"] = ART
        x["fromPage"] = True


F.enrich_short_summaries = fake_enrich

# ── (1) текст по правилу — до перевода ──
a = foreign()
n = F.compose_before_translation([a], "ru")
check("иностранная карточка: текст = правило абзацев от целой статьи", n == 1 and a["summary"] == RULE)
check("метка _ruled стоит", a.get("_ruled") is True)
check("правило даёт 8 абзацев из 11", len(RULE.split("\n\n")) == 8)
for name, kw in (("уже переведена", {"translated": True}), ("страница закрыта издателем", {"pageClosed": True}),
                 ("Telegram", {"url": "https://t.me/x"}), ("уже на языке пула", {"language": "ru"})):
    b = foreign(**kw)
    F.compose_before_translation([b], "ru")
    check(f"не трогаем: {name}", b["summary"] == "One sentence from RSS." and not b.get("_ruled"))
c = foreign()
F.enrich_short_summaries = lambda items, **k: None          # страницу не дали
F.compose_before_translation([c], "ru")
check("страницы нет — карточка как была", c["summary"] == "One sentence from RSS." and not c.get("_ruled"))
F.enrich_short_summaries = fake_enrich

# ── (2) повторно правило не режет ──
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_news.py"), encoding="utf-8").read()
pos = src.index
check("основной путь: компоновка до перевода", pos("compose_before_translation(filtered, lang)") < pos("to_translate = [x for x in filtered if needs_translation(x, lang)]"))
check("основной путь: _ruled обходит card_text", 'if _x.get("_ruled"):' in src)
check("запас: компоновка до перевода", pos("compose_before_translation(cands, lang)") < pos("need = [x for x in cands if needs_translation(x, lang)]"))
r = {"title": "T", "summary": "x", "_full": RULE, "_ruled": True}
ok_, x, _ = ED.apply_verdict(r, {"publish": True, "paragraphs": [1]}, ED.split_paragraphs(RULE), [])
check("редактор: _ruled — текст целиком, без повторной компоновки", ok_ and x["summary"].split("\n\n") == RULE.split("\n\n"))
plain = {"title": "T", "summary": "x", "_full": ART}
ok_, x, _ = ED.apply_verdict(plain, {"publish": True, "paragraphs": [1]}, ED.split_paragraphs(ART), [])
check("редактор: обычная карточка по-прежнему компонуется (не целиком и не меньше трёх)", ok_ and 3 <= len(x["summary"].split("\n\n")) < 11)

# ── (3) длинные тексты — малыми порциями ──
sizes = []


def fake_chunk(items, target):
    sizes.append(len(items))
    return [("T", "S")] * len(items)


F._gemini_translate_chunk = fake_chunk
longs = [foreign(summary="слово " * 400, url=f"https://x.test/{i}") for i in range(10)]
res = F._gemini_translate(longs, "ru")
check("10 длинных → порции не больше 4", sizes == [4, 4, 2] and len(res) == 10)
sizes.clear()
F._gemini_translate([foreign() for _ in range(10)], "ru")
check("короткие — одной порцией, как раньше", sizes == [10])
check("потолок текста в переводе не 900", F.TRANSLATE_TEXT_MAX > 900)

# ── (4) память переводов верна только для того же текста ──
F.TRANSLATIONS = {"ru": {F._cache_key({"url": "https://x.test/a"}): {
    "title": "Старый", "summary": "Старый короткий перевод.", "origTitle": "Title",
    "origSummary": "One sentence from RSS.", "ts": 1}}}
calls = []
F._gemini_translate = lambda items, t: calls.append(len(items)) or [("Новый", "Полный перевод.")] * len(items)
F._still_foreign = lambda text, lang: False
F._wrong_alphabet = lambda text, lang: False
long_item = foreign(summary=RULE)
F.translate_batch([long_item], "ru")
check("текст изменился — старый короткий перевод из памяти не берём", calls == [1] and long_item["summary"] == "Полный перевод.")
same = foreign(url="https://x.test/b")
F.TRANSLATIONS["ru"][F._cache_key(same)] = {"title": "Старый", "summary": "Старый короткий перевод.", "origTitle": "Title", "origSummary": "One sentence from RSS.", "ts": 1}
F.translate_batch([same], "ru")
check("тот же текст — перевод из памяти, ИИ не зовём", calls == [1] and same["summary"] == "Старый короткий перевод.")

print(f"enrich_before_translate: {ok} ok, {fail} fail")
raise SystemExit(1 if fail else 0)
