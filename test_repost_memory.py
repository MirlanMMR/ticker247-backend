# -*- coding: utf-8 -*-
"""Повтор прошлых дней и ссылки «по теме» (журнал J55, 17.10.2026).

Случай: Азаттык «СМИ: девять казахстанцев вывезли из зоны боевых действий в Украине» — третий
материал одного развивающегося сюжета (семеро → девять), с тем же снимком; прежние к тому времени
вышли из ленты, и drop_twins (сравнивает карточки одного прогона) их не видел.

Решение владельца: код только ЗАМЕЧАЕТ, выпускать ли — решает редактор («что нового в самой
новости»), возвращаться можно, пока событие развивается. Тест — на класс: память × снимок × слова
× адрес × срок, разбор ссылок страницы, что именно получает редактор.
"""
import editor as ED
from twins import find_reposts, remember_shown, touch, REPOST_TTL_MS

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


H = 3_600_000
IMG = "https://gdb.rferl.org/abc-123/w1023_h574_q80.jpg"
IMG_OTHER = "https://gdb.rferl.org/zzz-999/w1023_h574_q80.jpg"


def card(url, title, img=IMG, cat="NEWS", summary=""):
    return {"url": url, "title": title, "imageUrl": img, "source": "Азаттык", "category": cat, "summary": summary}


first = card("u1", "Семерых казахстанцев вывезли из зоны боевых действий в Украине", summary="Семерых граждан вывезли в Воронеж.")
mem = remember_shown({}, [first], 0)
third = card("u3", "СМИ: девять казахстанцев вывезли из зоны боевых действий в Украине")

# ── замечаем ──
f = find_reposts([third], mem)
check("тот же снимок, тот же сюжет, другой адрес, прежней уже нет в ленте — замечено", len(f) == 1 and f[0][1] == "u1")
check("в памяти есть заголовок и начало прежней — редактору есть с чем сравнивать",
      "Семерых" in f[0][2]["title"] and "Воронеж" in f[0][2]["lead"])
check("другая новость на той же заставке (нет общих слов) — не замечено",
      not find_reposts([card("u9", "Суд в Алматы вынес приговор по делу о пожаре")], mem))
check("одно общее слово при общей заставке — не замечено (нужно ≥ 2)",
      not find_reposts([card("u9", "Казахстанцев на войне встретили в Воронеже семьи")], mem))
check("другой снимок — не замечено", not find_reposts([card("u3", third["title"], IMG_OTHER)], mem))
check("снимка нет — не замечено", not find_reposts([card("u3", third["title"], None)], mem))
check("та же карточка, дожившая до следующего прогона — не повтор", not find_reposts([card("u1", first["title"])], mem))
check("прежняя карточка ещё в этой ленте — решает drop_twins, не память",
      not find_reposts([card("u3", third["title"]), first], mem))
check("финансовые карточки не трогаем", not find_reposts([card("u3", third["title"], cat="CURRENCY")], mem))
check("память пуста (первый прогон, нет связи) — ничего", not find_reposts([third], {}))

# ── память без обрыва ──
check("запись старше срока забывается", not remember_shown(mem, [], REPOST_TTL_MS + 1))
check("повторная запись не меняет время первого показа", remember_shown(mem, [first], 5 * H)["u1"]["at"] == 0)
m2 = remember_shown({}, [first], 0)
touch(m2, ["u1"], REPOST_TTL_MS - H)
check("сюжет жив (было совпадение) — запись продлена и не умирает по сроку",
      "u1" in remember_shown(m2, [], REPOST_TTL_MS + 2 * H))

# ── ссылки «по теме» на странице (разметка Азаттыка 17.10.2026) ──
PAGE = "https://www.azattyqasia.org/a/smi-devyat-kazahstantsev/33878140.html"
HTML = """<html><body><header><a href="/a/menu-item/111111.html">меню</a></header>
<p>Девятерых граждан доставили в Воронеж. МИД
<a href="https://www.azattyqasia.org/a/mid-kazahstana-prizval-rodstvennikov/33869591.html">призвало</a> сообщить данные.</p>
<div class="media-block also-read"><a href="/a/kazahstanets-uehal-na-zarabotki-v-kursk/33862957.html"
 title="«Мам, заживем круто». Казахстанец уехал на заработки в Курск и оказался в рядах российской армии"
 class="img-wrap also-read__img"><img src="x.jpg"></a></div>
<p>Другой сайт: <a href="https://example.org/a/other/123456.html">чужое издание</a>, эта же страница: <a href="/a/smi-devyat-kazahstantsev/33878140.html">я</a></p>
<footer><a href="/a/footer-item/222222.html">подвал</a></footer></body></html>"""
rel = ED.page_related(HTML, PAGE)
urls = [r["url"] for r in rel]
check("блок «читайте также» найден, заголовок из атрибута title", any("33862957" in u and "Курск" in r["title"] for u, r in zip(urls, rel)))
check("ссылка в тексте найдена, заголовок из адреса (в тексте только слово «призвало»)",
      any("33869591" in u and "mid kazahstana prizval" in r["title"] for u, r in zip(urls, rel)))
check("чужой сайт, сама страница, меню и подвал не берутся", len(rel) == 2)
check("пустая страница — пусто", ED.page_related("", PAGE) == [])

# ── что получает редактор ──
ED.SHOWN_MEMORY = {"https://www.azattyqasia.org/a/mid-kazahstana-prizval-rodstvennikov/33869591.html":
                   {"title": "МИД Казахстана призвал родственников сообщить данные"}}
c = dict(third, _related=rel, _repost_of=f[0][2])
block = ED.card_block(1, c, ["Девятерых граждан доставили в Воронеж."], [])
check("редактор видит памятку о похожей карточке с её началом", "Похожая карточка уже была" in block and "Воронеж" in block)
check("редактор видит связанные материалы издания", "Связанные материалы издания" in block and "Курск" in block)
check("прежнее, что мы уже показывали, помечено", "НАШИ ЧИТАТЕЛИ ЭТО УЖЕ ВИДЕЛИ" in block)
check("карточка без связей не получает лишних строк", "Связанные" not in ED.card_block(1, card("u5", "Новость"), ["Текст."], []))
ED.SHOWN_MEMORY = {}

# ── одна и та же обложка на разных карточках (владелец: «зрительная память запомнила») ──
ED.SHOWN_MEMORY = {"u1": {"img": "https://gdb.rferl.org/abc-123/w1023_h574_q80.jpg".lower().replace("/w1023_h574_q80", ""),
                          "title": "Прежняя новость с этой обложкой", "src": "Азаттык"}}
from twins import norm_image
ED.SHOWN_MEMORY["u1"]["img"] = norm_image(IMG)
other_story = card("u7", "Совсем другая новость про суд", IMG)
blk = ED.card_block(1, other_story, ["Текст."], [])
check("тот же снимок на другой, несхожей по смыслу новости — редактору сказано", "Этот снимок уже был" in blk and "Прежняя новость" in blk)
check("снимок свежий — строки нет", "Этот снимок уже был" not in ED.card_block(1, card("u8", "Новость", IMG_OTHER), ["Т."], []))
check("своя же карточка (тот же адрес) себе не повтор", "Этот снимок уже был" not in ED.card_block(1, card("u1", "Прежняя", IMG), ["Т."], []))
ED.SHOWN_MEMORY = {}
md0 = open("EDITOR.md", encoding="utf-8").read()
check("EDITOR.md: знакомая обложка — взять другой снимок страницы", "Снимок уже стоял на другой нашей карточке" in md0 and "возьми его" in md0)

# ── правило решает редактор, а не код ──
md = open("EDITOR.md", encoding="utf-8").read()
check("EDITOR.md: причина «повтор» и вопрос «что нового в самой новости»", "**повтор**" in md and "что нового в самой новости" in md)
check("EDITOR.md: развитие сюжета выпускать", "это развитие сюжета, выпускай" in md)
check("«повтор» — допустимая причина снятия", "повтор" in ED.REASONS)
ok_, x, notes = ED.apply_verdict(dict(third, summary="Текст."), {"publish": False, "reason": "повтор"}, ["Текст."], [])
check("вердикт «повтор» снимает карточку", ok_ is False and notes == ["снято: повтор"])
ok2, _, _ = ED.apply_verdict(dict(third, summary="Текст."), {"publish": True}, ["Текст."], [])
check("без вердикта карточка выпускается (редактор не ответил — не теряем)", ok2 is True)
check("версия правил поднята (память редактора пересудит карточки)", ED.EDITOR_VERSION >= 6)
src = open("fetch_news.py", encoding="utf-8").read()
check("конвейер только помечает: drop_reposts не зовётся", "drop_reposts" not in src and "find_reposts(filtered" in src)

print(f"пройдено {ok}, провалено {fail}")
raise SystemExit(1 if fail else 0)
