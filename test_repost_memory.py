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

# ── одна и та же обложка: уместна только у новостей одного сюжета (владелец, 17.10.2026) ──
from twins import cover_conflict, reused_covers, norm_image, related_cover_conflict
mem_c = remember_shown({}, [card("u1", "Суд по делу о пожаре в Алматы начался", IMG)], 0)
ED.SHOWN_MEMORY = mem_c
other_story = card("u7", "Совсем другая новость про футбол", IMG)
check("тот же снимок у другой новости — конфликт", cover_conflict(other_story, mem_c) is not None)
check("тот же снимок у продолжения того же сюжета — тоже конфликт (пусть издание меняет фото)",
      cover_conflict(card("u7", "Приговор по делу о пожаре в Алматы вынесли", IMG), mem_c) is not None)
check("свой же адрес себе не конфликт", cover_conflict(card("u1", "Суд по делу о пожаре в Алматы начался", IMG), mem_c) is None)
check("другой снимок — нет конфликта", cover_conflict(card("u7", "Совсем другая новость", IMG_OTHER), mem_c) is None)
check("снимка нет — нет конфликта", cover_conflict(card("u7", "Совсем другая новость", None), mem_c) is None)
check("память пуста (первый прогон) — не снимаем", reused_covers([other_story], {}) == [])
check("конфликт со старой записью, которая ещё в ленте, решает drop_twins",
      reused_covers([other_story, card("u1", "Суд по делу о пожаре в Алматы начался", IMG)], mem_c) == [])
rc = reused_covers([other_story, card("u8", "Новость со свежим снимком", IMG_OTHER)], mem_c)
check("снимается только новость со знакомой обложкой", len(rc) == 1 and rc[0][0]["url"] == "u7")
blk = ED.card_block(1, other_story, ["Текст."], [])
check("редактор предупреждён: другой снимок или новость не выйдет", "уже стоял на другой нашей карточке" in blk and "новость не выйдет" in blk)
check("своя же карточка — строки нет", "уже стоял на другой" not in ED.card_block(1, card("u1", "Суд по делу о пожаре в Алматы начался", IMG), ["Т."], []))
ED.SHOWN_MEMORY = {}
md0 = open("EDITOR.md", encoding="utf-8").read()
check("EDITOR.md: тот же снимок у предыдущей новости — не берём, другой снимок страницы", "Тот же снимок уже стоял у предыдущей новости" in md0 and "пусть издание" in md0)
check("конвейер снимает такие новости до записи ленты", "reused_covers(filtered" in open("fetch_news.py", encoding="utf-8").read())

# ── ссылки «по теме»: у связанной страницы тот же снимок — не берём (владелец, 17.10.2026) ──
az_card = "https://gdb.rferl.org/256e66c6-85a4-42bf-42ae-08df13a884cb_w800_h450.jpeg"
az_og = "https://gdb.rferl.org/256e66c6-85a4-42bf-42ae-08df13a884cb_w1200_h630.jpeg"
az_crop = "https://gdb.rferl.org/01ef7085-d068-4af5-70fc-08df13a869ed_cx0_cy60_cw0_w1200_h630.jpeg"
check("один снимок разных размеров у Азаттыка — один и тот же (w800_h450 = w1200_h630)", norm_image(az_card) == norm_image(az_og))
check("кадрирование (cx/cy/cw) тоже не делает снимок другим", norm_image(az_crop) == norm_image("https://gdb.rferl.org/01ef7085-d068-4af5-70fc-08df13a869ed_w100_r1.jpeg"))
check("разные снимки Азаттыка не склеиваются", norm_image(az_card) != norm_image(az_crop))
c1 = card("u3", "СМИ: девять казахстанцев вывезли", az_card)
c1["_related"] = [{"url": "r1", "title": "Казахстанец уехал на заработки в Курск", "cover": az_crop},
                  {"url": "r2", "title": "Родители пришли в МИД", "cover": az_og}]
check("у связанной страницы тот же снимок — конфликт, названа именно она", (related_cover_conflict(c1) or {}).get("url") == "r2")
c2 = dict(c1, _related=[{"url": "r1", "title": "x", "cover": az_crop}])
check("у связанных другие снимки — конфликта нет (так на странице Азаттыка 17.10.2026)", related_cover_conflict(c2) is None)
check("обложка связанной не скачалась (пусто) — не конфликт", related_cover_conflict(dict(c1, _related=[{"url": "r", "title": "x", "cover": ""}])) is None)
rc2 = reused_covers([c1, c2, card("u9", "Другая новость", IMG_OTHER)], {})
check("конвейер снимает новость, у связанной страницы которой тот же снимок, и только её", len(rc2) == 1 and rc2[0][0] is c1)
check("редактор видит строку о том же снимке у связанной", "ТАКОЙ ЖЕ снимок" in ED.card_block(1, c1, ["Т."], []))
check("page_cover берёт og:image", ED.page_cover('<meta property="og:image" content="https://a/b_w1200_h630.jpg">') == "https://a/b_w1200_h630.jpg")
check("page_cover без разметки — пусто", ED.page_cover("<html></html>") == "" and ED.page_cover("") == "")

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
