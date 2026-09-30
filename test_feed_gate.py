# -*- coding: utf-8 -*-
"""Проверки последнего рубежа перед публикацией.

Случаи из ленты за 28.08.2026 — те самые, что дошли до читателя.
"""
import sys

from feed_gate import gate, repair, unreadable, is_video_page, foreign_video
from textcut import is_known_stub, strip_known_stubs

ok = fail = 0


def check(name, got, want=True):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}: получили {got!r}, ждали {want!r}")


LONG_RU = ("Президент подписал закон, который вступает в силу с января. "
           "Правительство сообщает, что документ готовился больше года.")
LONG_FR = ("Le président a signé la loi qui entre en vigueur en janvier. "
           "Selon le gouvernement, le texte était préparé depuis plus d'un an.")

# ─── Чиним, а не выбрасываем ────────────────────────────────────────────────
#
# Каждая выброшенная новость — дыра в ленте. Подстановки чинятся за доли
# миллисекунды, и терять из-за них материал нельзя.

r = repair({"title": "Mort d&#39;Émile",
            "summary": "Toujours aucune &quot;avancée&quot;. " + LONG_FR,
            "source": "BFMTV"}, "fr")
check("подстановка в заголовке разобрана", r["title"], "Mort d'Émile")
check("подстановка в тексте разобрана", '&quot;' in r["summary"], False)
check("кавычки на месте", '"avancée"' in r["summary"])

r2 = repair({"title": "Chelsea news",
             "summary": "closes. <p>There are no talks yet. " + LONG_FR,
             "source": "Sky Sports"}, "en")
check("сырой тег снят", "<p>" in r2["summary"], False)

r3 = repair({"title": "Guerra na Ucrânia", "summary": LONG_FR,
             "source": "BBC Русская служба"}, "pt")
check("кириллица ушла из имени издания", r3["source"], "BBC")

r4 = repair({"title": "Обычный заголовок", "summary": LONG_RU,
             "source": "24.kg"}, "ru")
check("чистая новость не тронута", r4 == {
    "title": "Обычный заголовок", "summary": LONG_RU, "source": "24.kg"})

# ─── Выбрасываем только непоправимое ────────────────────────────────────────

check("русский текст во французском пуле — не прочтут",
      unreadable({"title": "Заголовок", "summary": LONG_RU}, "fr"))
check("французский текст во французском пуле — годится",
      unreadable({"title": "Titre", "summary": LONG_FR}, "fr"), False)
check("латиница в русском пуле — не прочтут",
      unreadable({"title": "Title", "summary": LONG_FR}, "ru"))
check("русский текст в русском пуле — годится",
      unreadable({"title": "Заголовок", "summary": LONG_RU}, "ru"), False)

# Порог намеренно грубый: цена ошибки — выброшенная новость
check("короткий текст не судим",
      unreadable({"title": "Nepal", "summary": "Flood"}, "ru"), False)
check("имена собственными латиницей не выдают чужой язык",
      unreadable({"title": "Wildberries и Ozon",
                  "summary": "Компания Wildberries сообщает, что склад "
                             "полностью сгорел. Ozon заявил о поддержке."},
                 "ru"), False)

# ─── Рубеж целиком ──────────────────────────────────────────────────────────

items = [
    {"title": "Titre", "summary": LONG_FR, "source": "BFMTV"},
    {"title": "Mort d&#39;Émile", "summary": LONG_FR, "source": "BBC Русская служба"},
    {"title": "Заголовок", "summary": LONG_RU, "source": "24.kg"},
]
kept, dropped, fixed = gate(items, "fr")
check("годные оставлены", len(kept), 2)
check("непрочитаемая выброшена", len(dropped), 1)
check("починенных посчитали", fixed, 1)
check("починка не мешает публикации", kept[1]["title"], "Mort d'Émile")
check("имя издания исправлено у оставшейся", kept[1]["source"], "BBC")

# Пустая лента не должна ронять рубеж
k2, d2, f2 = gate([], "es")
check("пустая лента переживается", (k2, d2, f2), ([], [], 0))


# ─── Одна редакция об одном событии ─────────────────────────────────────────
#
# Найдено пользователем 28.08.2026 по снимку ленты: одно фото короля Норвегии
# дважды подряд, от BBC Mundo и BBC Brasil. Ссылки разные, заголовки разные,
# редакция одна, событие одно.

from feed_gate import drop_family_repeats, same_event

_fam = lambda src: "bbc" if "BBC" in src else src.lower()

MUNDO = {"source": "BBC Mundo", "publishedAt": 2, "imageUrl": "http://a",
         "title": "Король Норвегии Харальд скончался в возрасте 89 лет",
         "summary": "a" * 300}
BRASIL = {"source": "BBC Brasil", "publishedAt": 3, "imageUrl": "http://b",
          "title": "Умерший в возрасте 89 лет король Норвегии был монархом",
          "summary": "b" * 100}
REUTERS = {"source": "Reuters", "publishedAt": 1, "imageUrl": "http://c",
           "title": "Король Норвегии Харальд скончался в возрасте 89 лет",
           "summary": "c" * 400}

check("сёстры об одном событии — это повтор", same_event(MUNDO, BRASIL))
_kept, _dropped = drop_family_repeats([MUNDO, BRASIL, REUTERS], _fam)
check("вторая от той же редакции снята", len(_dropped), 1)
check("снята именно она", _dropped[0]["source"], "BBC Brasil")
# Разные ИЗДАНИЯ об одном событии — не повтор, а разные взгляды; на них
# построен обзор прессы, и склеивать их в ленте значило бы обеднять её
check("чужое издание об том же остаётся",
      any(x["source"] == "Reuters" for x in _kept))
check("из пары осталась лучшая", _kept[0]["source"], "BBC Mundo")

# Разные события одной редакции трогать нельзя
check("разные события одной редакции — обе остаются",
      len(drop_family_repeats([
          {"source": "BBC Mundo", "title": "Выборы в Молдавии завершились"},
          {"source": "BBC Brasil", "title": "Землетрясение в Японии унесло жизни"},
      ], _fam)[0]), 2)
check("пустая лента переживается", drop_family_repeats([], _fam), ([], []))

# ─── родная редакция важнее перевода ───────────────────────────────────────
# 29.08.2026: в испанскую ленту пришла кража колье из венского музея от
# РУССКОЙ службы Би-би-си при живой BBC Mundo — путь английский → русский →
# испанский, да ещё со служебной сноской переводчика.
_RU_BBC = {"source": "BBC Русская служба", "source_lang": "ru",
           "title": "Ladrones roban un collar con 600 diamantes en Viena",
           "summary": "x" * 900, "imageUrl": "http://i/1.jpg", "publishedAt": 100}
_ES_BBC = {"source": "BBC Mundo", "source_lang": "es",
           "title": "Roban un collar de 600 diamantes de un museo en Viena",
           "summary": "y" * 300, "imageUrl": "http://i/2.jpg", "publishedAt": 200}
_fam = lambda src: "bbc" if "BBC" in src else src

_kept, _drop = drop_family_repeats([_RU_BBC, _ES_BBC], _fam, pool_lang="es")
check("в испанском пуле остаётся BBC Mundo, а не русская служба",
      [k["source"] for k in _kept], ["BBC Mundo"])

# Язык главнее длины и фото — но только он: при одном языке всё как было
_kept2, _ = drop_family_repeats([_ES_BBC, _RU_BBC], _fam, pool_lang="ru")
check("в русском пуле остаётся русская служба",
      [k["source"] for k in _kept2], ["BBC Русская служба"])

# Родной версии нет — перевод лучше пустоты, новость не теряем
_kept3, _ = drop_family_repeats([_RU_BBC], _fam, pool_lang="fr")
check("без родной версии перевод остаётся",
      [k["source"] for k in _kept3], ["BBC Русская служба"])

# Разные ИЗДАНИЯ об одном событии — разные взгляды, их не трогаем
_OTHER = dict(_RU_BBC, source="Reuters", source_lang="en")
_kept4, _ = drop_family_repeats([_ES_BBC, _OTHER], _fam, pool_lang="es")
check("разные издания об одном событии остаются оба", len(_kept4), 2)

# ─── две редакции одного издания на разных языках ──────────────────────────
# С 30.08 в русском пуле идут обе ленты Sputnik KG. Одну новость на двух
# языках не показываем, а какую оставить — решает первенство.
_SP_RU = {"source": "Sputnik KG", "source_lang": "ru", "publishedAt": 900,
          "title": "Массовая драка произошла в Бишкеке",
          "summary": "x" * 400, "imageUrl": "https://s.sputnik.kg/1042543486_0:252:4800.jpg"}
_SP_KY = {"source": "Sputnik KG (кыргызча)", "source_lang": "ru", "native": "ky",
          "publishedAt": 500,
          "title": "Бишкекте массалык мушташ болуп, бир нече киши жабыркады",
          "summary": "y" * 200, "imageUrl": "https://s.sputnik.kg/1042543486_0:67:2908.jpg"}
_fam2 = lambda src: "sputnik" if "Sputnik" in src else src

# Заголовки не делят ни одного корня — связывает их только снимок
check("разноязычные версии связаны по снимку",
      len(drop_family_repeats([_SP_RU, _SP_KY], _fam2, pool_lang="ru")[0]), 1)

# Кыргызская вышла раньше — она и остаётся, хотя русская длиннее
_kept5, _ = drop_family_repeats([_SP_RU, _SP_KY], _fam2, pool_lang="ru")
check("остаётся тот, кто сообщил первым", _kept5[0].get("native"), "ky")

# Если раньше вышла русская — остаётся она
_SP_RU_FIRST = dict(_SP_RU, publishedAt=100)
_kept6, _ = drop_family_repeats([_SP_KY, _SP_RU_FIRST], _fam2, pool_lang="ru")
check("первенство решает в обе стороны", _kept6[0].get("source"), "Sputnik KG")

# Разные снимки — разные события, обе остаются
_OTHER_PHOTO = dict(_SP_KY, imageUrl="https://s.sputnik.kg/9999999_0:1:2.jpg")
check("разные снимки не склеиваем",
      len(drop_family_repeats([_SP_RU, _OTHER_PHOTO], _fam2, pool_lang="ru")[0]), 2)

# Фото по http Android не покажет — рубеж переводит его на https
_HTTP = {"title": "Новая волна ударов", "source": "24.kg",
         "imageUrl": "http://24.kg/files/media/473/473198.jpeg"}
check("фото по http → https", repair(_HTTP, "ru")["imageUrl"],
      "https://24.kg/files/media/473/473198.jpeg")

from feed_gate import closed_teaser
_RBC = {"title": "Брата экс-звезды мадридского «Реала» уволили из клуба MLS",
        "summary": "Коротко." * 10, "pageClosed": True, "priority": 0,
        "category": "SPORT"}
check("закрытый короткий анонс снимается", closed_teaser(_RBC), True)
check("закрытое, но срочное остаётся",
      closed_teaser(dict(_RBC, priority=2)), False)
check("закрытое с меткой URGENT остаётся",
      closed_teaser(dict(_RBC, category="URGENT_LOCAL_ONLY")), False)
check("начало статьи отдали — остаётся",
      closed_teaser(dict(_RBC, summary="слово " * 100)), False)
check("открытая короткая заметка остаётся",
      closed_teaser(dict(_RBC, pageClosed=False)), False)

from feed_gate import balance_quotes as BQ
check("потерянная «ёлочка» в начале заголовка возвращена",
      BQ("Манчестер Юнайтед» продает кусочки газона «Олд Траффорд» по 125 фунтов"),
      "«Манчестер Юнайтед» продает кусочки газона «Олд Траффорд» по 125 фунтов")
check("целый заголовок не тронут", BQ("«Реал» обыграл «Барселону»"), "«Реал» обыграл «Барселону»")
check("закрывающая далеко от начала — не гадаем",
      BQ("Президент страны подписал закон о защите прав» и другие"),
      "Президент страны подписал закон о защите прав» и другие")


# 01.10.2026: видео на чужом языке — не в этот пул; на родном — остаётся
_V = {"title": "Украденное детство: как девочка из Газы обрела свободу в плавании",
      "origTitle": "Robbed of a childhood: how one girl in Gaza found freedom in swimming – video",
      "url": "https://www.theguardian.com/world/video/2026/sep/30/robbed-of-a-childhood-video",
      "summary": LONG_RU, "translated": True}
check("страница-видео узнаётся по адресу", is_video_page({"url": "https://x.com/world/video/1"}))
check("страница-видео узнаётся по заголовку «– video»", is_video_page({"title": "Something – video", "url": "https://x.com/a"}))
check("обычная статья — не видео", is_video_page({"title": "Обычная новость", "url": "https://x.com/news/1"}), False)
check("видео на чужом языке (переведён заголовок) — снимается", foreign_video(_V))
check("то же видео на родном языке пула — остаётся", foreign_video(dict(_V, translated=False)), False)
check("переведённая статья без видео — остаётся", foreign_video(dict(_V, url="https://x.com/n/1", origTitle="Plain")), False)
check("gate выбрасывает чужое видео", len(gate([_V], "ru")[1]), 1)


# 01.10.2026: известная заглушка Straits Times «ST» — не фото
_STUB = ("https://cassette.sphdigital.com.sg/image/straitstimes/"
         "4e77bf2f50f582021268b732c0c75bc468d09bd4549f5672fd2ca6140ad0dada")
_REAL = ("https://cassette.sphdigital.com.sg/image/straitstimes/"
         "42ca8dad087d8c70e229bbdb72d23c14b2e44fd11ab684a1d8414f22d431a551")
check("заглушка ST узнаётся", is_known_stub(_STUB))
check("настоящее фото того же издания — не заглушка", is_known_stub(_REAL), False)
_r = repair({"title": "t", "summary": LONG_RU, "imageUrl": _STUB, "photoChecked": True, "source": "Straits Times"}, "en")
check("рубеж снимает заглушку и просит другое фото", (_r["imageUrl"], _r.get("_need_photo"), "photoChecked" in _r), ("", True, False))
_r2 = repair({"title": "t", "summary": LONG_RU, "imageUrl": _REAL, "source": "Straits Times"}, "en")
check("рубеж настоящее фото не трогает", _r2["imageUrl"], _REAL)
_items = strip_known_stubs([{"imageUrl": _STUB}, {"imageUrl": _REAL}], "en")
check("финальная чистка: заглушка снята, фото осталось", (_items[0]["imageUrl"], _items[1]["imageUrl"]), ("", _REAL))

print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
