# -*- coding: utf-8 -*-
"""Проверки последнего рубежа перед публикацией.

Случаи из ленты за 28.08.2026 — те самые, что дошли до читателя.
"""
import sys

from feed_gate import gate, repair, unreadable

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

print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
