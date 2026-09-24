"""Проверки выпускающего редактора без сети и без ИИ (editor.py)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import editor as ED

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        print(f"  ✗ {name}")


HERE = os.path.dirname(os.path.abspath(__file__))
RIA = open(os.path.join(HERE, "testdata", "ria_fsb.html"), encoding="utf-8").read()
RIA_URL = "https://ria.ru/20260924/fsb-2119936553.html"
NEKOGLAI = ("https://cdnn21.imgria.ru/images/07e6/0b/09/1830273607_0:86:960:626_"
            "1920x1080_80_0_0_4cfa8ad8e3e2ae4006bbe117624e22d4.jpg")

# ── снимки со страницы ──
ph = ED.page_photos(RIA, RIA_URL, NEKOGLAI)
check("№1 — снимок, что стоит в карточке", ph[0]["url"] == NEKOGLAI)
check("у №1 нашлась подпись со страницы (Некоглай)", "Некоглай" in ph[0]["alt"])
check("главное фото страницы в списке",
      any("2119935127" in p["url"] and p["where"] == "главное фото страницы" for p in ph))
check("обложка соцсетей помечена карточкой",
      any(p["where"] == "обложка для соцсетей" and p["flag"] for p in ph))

# ── абзацы ──
P1 = "Первый абзац: что произошло и где."
P2 = "Второй абзац: цифры и последствия."
paras = ED.split_paragraphs(f"{P1}\n\n{P2}\n\nПодписывайтесь на наш канал!")
check("три абзаца", len(paras) == 3)
long = " ".join(f"Предложение номер {i}." for i in range(1, 80))
check("длинный кусок режется на части", len(ED.split_paragraphs(long)) > 3)

# ── разбор ответа ──
raw = '```json\n[{"id": 1, "publish": true, "paragraphs": [1, 2], "photo": 2}]\n```'
v = ED.parse_verdicts(raw)
check("ответ в ```json``` разобран", v.get(1, {}).get("paragraphs") == [1, 2])
check("испорченный JSON — пусто, без падения", ED.parse_verdicts("[{id: 1,") == {})

# ── исполнение ──
item = {"title": "Huawei Mate 90 получит съемный супертелеобъектива",
        "summary": "x", "imageUrl": NEKOGLAI, "scope": "pool", "category": "TECH"}
ok, x, notes = ED.apply_verdict(item, {
    "publish": True, "paragraphs": [1, 2],
    "title": "Huawei Mate 90 получит съемный супертелеобъектив", "photo": 2}, paras, ph)
check("выпущено", ok)
check("текст — абзацы 1 и 2 дословно", x["summary"] == f"{P1}\n\n{P2}")
check("опечатка в заголовке исправлена", x["title"].endswith("супертелеобъектив"))
check("фото заменено на №2", x["imageUrl"] == ph[1]["url"])
check("оригинал не тронут", item["title"].endswith("супертелеобъектива"))

ok, x, _ = ED.apply_verdict(item, {"publish": True, "title": "Китайский флагман получит оптику"},
                            paras, ph)
check("переписанный заголовок отвергнут", x["title"] == item["title"])

ok, _, notes = ED.apply_verdict(item, {"publish": False, "reason": "не нравится"}, paras, ph)
check("снятие без причины из списка не проходит", ok)
ok, _, _ = ED.apply_verdict(item, {"publish": False, "reason": "нет события"}, paras, ph)
check("снятие по причине «нет события» проходит", not ok)
urgent = dict(item, category="URGENT")
ok, _, _ = ED.apply_verdict(urgent, {"publish": False, "reason": "закрыто"}, paras, ph)
check("закрытое, но срочное — выпускается", ok)

water = {"title": "Бүгүн Бишкектин айрым райондорунда суу өчөт", "summary": "…",
         "scope": "local", "category": "KG"}
ok, x, _ = ED.apply_verdict(water, {"publish": True, "vital": True, "vital_kind": "вода-свет-газ"},
                            ["Суу өчөт."], [], vital_ok=True)
check("жизненно важное местное → URGENT", x["category"] == "URGENT" and x["vital"])
ok, x, _ = ED.apply_verdict(dict(water, title="Автобус и катафалк столкнулись, двое погибли"),
                            {"publish": True, "vital": True, "vital_kind": "происшествие"}, ["x"], [])
check("«жизненно важное» без вида из списка не принимается", x.get("category") != "URGENT")
ok, x, _ = ED.apply_verdict(water, {"publish": True, "vital": True}, ["x"], [])
check("«жизненно важное» без вида вовсе не принимается", x.get("category") != "URGENT")
ok, x, _ = ED.apply_verdict(dict(water, title="Бесплатный проезд военным пенсионерам хотят дать"),
                            {"publish": True, "vital": True, "vital_kind": "дороги-транспорт"}, ["x"], [])
check("по умолчанию ИИ жизненно важное не ставит", x.get("category") != "URGENT")
ok, x, _ = ED.apply_verdict(dict(water, scope="pool"), {"publish": True, "vital": True},
                            ["x"], [])
check("жизненно важное чужой страны — не срочно", x.get("category") != "URGENT")

# ── прогон целиком с подставной моделью ──
calls = {"n": 0, "strong": 0}


def fake_ask(tail):
    calls["n"] += 1
    return '[{"id": 1, "publish": true, "paragraphs": [1], "unsure": true}]'


def fake_strong(tail):
    calls["strong"] += 1
    assert "ВТОРОЙ редактор" in tail
    return '[{"id": 1, "publish": false, "reason": "нет события"}]'


cache = {}
items = [{"url": "https://ex.com/a", "title": "Интервью", "summary": "Абзац один.\n\nДва.",
          "scope": "pool"}]
res, asked, second = ED.review(items, "ru", ask=fake_ask, ask_strong=fake_strong,
                               fetch_html=lambda u: "", cache=cache,
                               cache_key=lambda it: it["url"], header="", now_ms=1)
check("спорное ушло второму редактору", second == 1 and calls["strong"] == 1)
check("решение второго — окончательное", res[0][1]["publish"] is False)
res, asked, _ = ED.review(items, "ru", ask=fake_ask, ask_strong=fake_strong,
                          fetch_html=lambda u: "", cache=cache,
                          cache_key=lambda it: it["url"], header="", now_ms=2)
check("второй раз — из памяти, без запроса", asked == 0 and calls["n"] == 1)
check("снятая статья из памяти остаётся снятой",
      ED.apply_verdict(items[0], res[0][1], ["a"], [])[0] is False)
m = ED.compact({"publish": True, "photo": 0, "need_photo": True}, ["a"], [{"url": "u"}], 1)
check("фото №0 («нужно другое») переживает память",
      m["verdict"]["photo"] == 0 and m["verdict"]["need_photo"])
check("память компактна (без полного списка снимков)",
      len(str(cache)) < 600)


def broken(tail):
    raise RuntimeError("503")


res, _, _ = ED.review([dict(items[0], url="https://ex.com/b")], "ru", ask=broken,
                      ask_strong=broken, fetch_html=lambda u: "", cache={},
                      cache_key=lambda it: it["url"], header="", now_ms=3)
check("ИИ упал — решения нет, но и падения нет", res[0][1] is None)

print(f"пройдено {passed}, провалено {failed}")
sys.exit(1 if failed else 0)
