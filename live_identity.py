# -*- coding: utf-8 -*-
"""Тот ли это канал, за который мы его принимаем.

28.08.2026 в ленту попали два самозванца, и оба — из-за одной и той же
ошибки: каналы добавлялись по «собачке», и проверялось, что трансляция ИДЁТ,
но не проверялось, ЧЕЙ это канал.

  @ntv   → турецкий NTV, а не русский НТВ. Читатель русского пула получил
           «NTV Canlı Yayın - Full HD İzle».
  @CNEWS → тайваньский CNEWS匯流新聞網, а не французский. Во французском пуле
           шло заседание тайбэйского городского совета.

Совпадение «собачки» ничего не доказывает: короткие имена вроде ntv, cnews,
abc заняты в десятке стран, и достаётся она тому, кто раньше пришёл.
"""
import re

_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯]")
_CYR = re.compile(r"[А-Яа-яЁё]")
_ARAB = re.compile(r"[؀-ۿ]")


def _norm(s: str) -> str:
    return re.sub(r"[^0-9a-zа-яё]", "", (s or "").lower())


def name_matches(ours: str, theirs: str) -> bool:
    """Похоже ли имя канала на то, которое мы ждали.

    Правило нарочно мягкое: вещатели пишут себя по-разному — «ABC News
    Australia» против «ABC News (Australia)», «Bloomberg TV» против «Bloomberg
    Television». Отвергать из-за скобки значило бы терять живые каналы.

    Но общее начало в шесть букв турецкое NTV от русского НТВ отделяет: после
    приведения это «ntv» и «нтв», у них нет ни одной общей буквы.
    """
    a, b = _norm(ours), _norm(theirs)
    if not a or not b:
        return True                    # нечего сравнивать — не придираемся
    if a in b or b in a:
        return True
    common = 0
    for x, y in zip(a, b):
        if x != y:
            break
        common += 1
    return common >= 6


def alien_script(title: str, pool: str) -> str:
    """Письмо, которого в этом пуле быть не может. Возвращает пустую строку, если всё в порядке.

    Имя канала самозванца может совпасть с настоящим — тайваньский CNEWS
    зовётся «CNEWS匯流新聞網», и по началу имени он от французского неотличим.
    Выдаёт его НАЗВАНИЕ ЭФИРА: иероглифы. Ни один наш пул на них не вещает.

    Кириллица в нерусском пуле — тот же признак, и наоборот: латиница сама по
    себе в русском пуле законна (названия, латинские вкрапления), поэтому её
    здесь не ловим — на этом легко потерять живой канал.
    """
    if not title:
        return ""
    if _CJK.search(title):
        return "иероглифы"
    if _ARAB.search(title):
        return "арабское письмо"
    if pool != "ru" and _CYR.search(title):
        return "кириллица"
    return ""


def verdict(our_name: str, their_name: str, stream_title: str, pool: str) -> str:
    """Пустая строка — канал наш. Иначе — чем он себя выдал."""
    if not name_matches(our_name, their_name):
        return f"канал зовётся «{their_name}», а не «{our_name}»"
    bad = alien_script(stream_title, pool)
    if bad:
        return f"в названии эфира {bad}: «{stream_title[:40]}»"
    return ""
