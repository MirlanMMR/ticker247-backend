# -*- coding: utf-8 -*-
"""Срочное из чужой страны — последний страж (журнал J38, 15.10.2026).

Случай: «Пассажир Damas погиб в Кашкадарье во время схода селя» (Gazeta.uz, Узбекистан)
лежал на полке «Новости из…» русского пула с category=URGENT_LOCAL_ONLY и priority=2 — и
оказался в шторке, бегущей строке и карусели читателя в Бишкеке.

Корень: метка URGENT_LOCAL_ONLY значит «срочно только дома», но НИ ОДИН последний шаг
не проверял, что она стоит на карточке scope=local. Приложение же будит по priority>=2.
Метку ставят четыре независимых места (ключевые слова, ИИ-разметка, режим «жизненно
важного», масса погибших); итог после всех не смотрел никто.

Правило (одно, для всех языков):
  · URGENT_LOCAL_ONLY вне полки «Местные» не бывает никогда;
  · URGENT вне «Местных» — только если беда не местного масштаба (землетрясение,
    теракт, ураган…) либо погибших достаточно (≥5 у соседей, ≥20 в дальнем мире).
    Сель, паводок, пожар, ДТП, утонувший — события района: за рубежом это не срочно.
"""
import re

_NUM_WORDS = {"двое": 2, "трое": 3, "четверо": 4, "пятеро": 5, "шестеро": 6,
              "семеро": 7, "восемь": 8, "девять": 9, "десять": 10, "десятки": 20,
              "сотни": 100, "dozens": 20, "hundreds": 100, "decenas": 20,
              "centenas": 100, "dizaines": 20, "centaines": 100}
_CASUALTY = re.compile(
    r"(\d+|" + "|".join(_NUM_WORDS) + r")[^\d.!?]{0,40}?"
    r"(погиб|утонул|жертв|пропал|скончал|killed|dead|died|drown|missing|victims?"
    r"|muert|fallec|desaparec|mort[oa]s?|morreram|desaparecid|tués?|morts?|disparu)",
    re.I)
# то же, но глагол раньше числа: «погибли 6 человек», «унесло жизни 15», «kill dozens»
_CASUALTY_REV = re.compile(
    r"(погиб|жертв|унёс|унес|жизни|утонул|пропал|скончал|kill|dead|died|claim|death|toll|"
    r"muert|fallec|mort|tu[eé]s?)[^\d.!?]{0,25}?(\d+|" + "|".join(_NUM_WORDS) + r")",
    re.I)
CASUALTY_NEAR, CASUALTY_FAR = 5, 20

# События района: случаются каждую неделю в каждой стране
_SMALL = re.compile(
    r"сел[ьяеюи](?![а-яё])|селев|паводо?к|наводнен|затоплен|оползн|лавин|пожар|"
    r"\bдтп\b|авари|столкновен|утонул|упал|сгорел|"
    r"flood|wildfire|landslide|mudslide|crash|collision|drown|fire\b|"
    r"inundaci|incendio|accidente|choque|acidente|deslizamiento|deslizamento|incêndio|"
    r"inondation|incendie|accident|noyé", re.I)
# Беда по природе масштабная: счёт погибших не нужен
_BIG = re.compile(
    r"землетряс|цунами|ураган|тайфун|торнадо|теракт|авиакатастроф|взрыв|"
    r"earthquake|tsunami|hurricane|typhoon|tornado|terror|plane crash|airliner|explosion|"
    r"terremoto|atentado|furacão|tufão|attentat|séisme|ouragan", re.I)

URGENT_CATS = ("URGENT", "URGENT_LOCAL_ONLY")


def casualties(text):
    """Число названных погибших/пропавших (числа от 1000 — годы и суммы, не считаем)."""
    def count(rx, grp):
        total = 0
        for m in rx.finditer(text or ""):
            w = m.group(grp).lower()
            n = int(w) if w.isdigit() else _NUM_WORDS.get(w, 0)
            if n < 1000:
                total += n
        return total
    return max(count(_CASUALTY, 1), count(_CASUALTY_REV, 2))


def foreign_small_urgent(x):
    """Карточка вне «Местных» с метками срочности, которых там быть не должно."""
    if x.get("category") not in URGENT_CATS or x.get("vital"):
        return False
    scope = x.get("scope")
    if scope not in ("pool", "world"):
        return False
    if x.get("category") == "URGENT_LOCAL_ONLY":
        return True                     # «только дома» — и точка
    text = f"{x.get('title') or ''} {(x.get('summary') or '')[:400]}"
    if _BIG.search(text) or not _SMALL.search(text):
        return False
    need = CASUALTY_NEAR if scope == "pool" else CASUALTY_FAR
    return casualties(text) < need


def final_urgent_guard(items, lang):
    """Снимает «срочно» и приоритет у чужого местного. Карточку из ленты не убирает."""
    hit = [x for x in items if foreign_small_urgent(x)]
    for x in hit:
        x["category"] = "NEWS"
        x["priority"] = min(int(x.get("priority") or 0), 1)
    if hit:
        print(f"  🔕 Срочное из чужой страны без масштаба [{lang}]: снято {len(hit)}")
        for x in hit[:6]:
            print(f"       · {x.get('source','?')} [{x.get('country')}]: {(x.get('title') or '')[:60]}")
    return items
