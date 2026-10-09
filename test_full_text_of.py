# -*- coding: utf-8 -*-
"""Карточка переведённой новости не строится из статьи на языке оригинала.

Регрессия #47 (поймана 09.10.2026 до первого прогона): `_article` (целая страница) лежит
на языке оригинала, и для переведённой карточки правило абзацев взяло бы английский
или русский текст под испанским заголовком. Тест — на правило: для ЛЮБОЙ переведённой
карточки текст берётся из summary, а не из _article.
"""
import sys

from textcut import full_text_of, card_text

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


EN = "\n\n".join(f"English paragraph {i}: this is a long enough original paragraph of the page text." for i in range(1, 7))
ES = "\n\n".join(f"Párrafo {i}: este es un párrafo traducido lo bastante largo del texto de la página." for i in range(1, 4))

orig = {"summary": ES, "_article": EN, "translated": True}
check("переведённая: берётся перевод", full_text_of(orig) == ES)
check("переведённая: нет английского в карточке", "English" not in card_text(full_text_of(orig)))
check("не переведённая: целая статья", full_text_of({"summary": "x", "_article": EN}) == EN)
check("нет _article: summary", full_text_of({"summary": "abc"}) == "abc")
check("пусто — пустая строка", full_text_of({}) == "")
for lang_title in ("es", "pt", "fr", "ru", "en"):
    it = {"summary": ES, "_article": EN, "translated": True, "language": lang_title}
    check(f"любой язык пула ({lang_title}): перевод побеждает оригинал", full_text_of(it) == ES)

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
