# -*- coding: utf-8 -*-
"""ЧИНИЛКА красных флагов эталона (docs/STANDARD.md, раздел 10): знает, как мы лечили класс ошибки раньше.

Новой логики здесь нет. Справочник PLAYBOOK — это колонка «замок» журнала docs/defects_journal.md: для каждого
класса (J…) записана та правка, которой он уже был вылечен (final_*_guard, drop_*, first_sentence_title…).
Чинилка вызывает ровно её, а не придумывает своё. Порядок на карточку с флагом:

  1. прежняя правка класса (PLAYBOOK) — она идемпотентна: если страж уже сработал, ничего не изменится;
  2. повторная проверка тем же детектором (border.REGISTRY);
  3. не вылечилось и класс в LAST_RESORT — карточка снимается («лучше без карточки, чем с браком»,
     EDITORIAL.md; снимаем только то, где правильного текста взять неоткуда);
  4. остальное остаётся красным и уходит дальше: журнал прогона, Telegram, дежурный агент.

Режим (STANDARD_FIX): shadow (по умолчанию) — только печатает, что сделала бы, лента не меняется; live — меняет;
off — выключена. Включать live после двух-трёх прогонов тени, как reader_guard (J63).
Каждое действие — строка «🔧 чинилка J…» в журнале прогона и в border_report.md через вызывающего.
"""
import copy
import os

import border
import shelves
import textcut
import topic_country
import urgent_guard
import dull

MODE = os.environ.get("STANDARD_FIX", "shadow")        # shadow | live | off

# Классы, где при неудаче снимаем карточку: исправного текста/полки взять неоткуда
LAST_RESORT = {"J1", "J2", "J3", "J4", "J8", "J9", "J15", "J18", "J23", "J32", "J44"}


def _list(res):
    """Стражи возвращают список или (остались, снятые) — приводим к списку оставшихся."""
    if isinstance(res, tuple):
        return res[0]
    return res


def _title(items, lang, ctx):
    for x in items:
        short = textcut.first_sentence_title(x.get("title") or "") if len(x.get("title") or "") > border.TITLE_FIT else None
        if short:
            x["title"] = short
    return items


def _heading(items, lang, ctx):
    for x in items:
        s = x.get("summary") or ""
        cut = textcut.drop_trailing_heading(s) if s else s
        if cut != s:
            x["summary"] = cut
    return items


def _stub_photo_off(items, lang, ctx):
    """J68: общая картинка сайта вместо фото — карточка идёт без фото (EDITORIAL: лучше без фото, чем с чужим)."""
    for x in items:
        if x.get("imageUrl") and border.STUB_IMG.search(x["imageUrl"]):
            x["imageUrl"] = None
    return items


# J-класс → [(имя правки из журнала, вызов)]
PLAYBOOK = {
    "J1": [("final_shelf_guard", lambda it, l, c: shelves.final_shelf_guard(it, l, c["space"], c["home"]))],
    "J2": [("final_shelf_guard", lambda it, l, c: shelves.final_shelf_guard(it, l, c["space"], c["home"]))],
    "J3": [("final_end_guard", lambda it, l, c: textcut.final_end_guard(it, l))],
    "J4": [("drop_trailing_heading", _heading)],
    "J5": [("first_sentence_title", _title)],
    "J9": [("final_start_guard", lambda it, l, c: textcut.final_start_guard(it, l))],
    "J11": [("cap_dull", lambda it, l, c: dull.cap_dull(it, l))],
    "J15": [("drop_stub_summaries", lambda it, l, c: textcut.drop_stub_summaries(it, l))],
    "J18": [("drop_foreign_script", lambda it, l, c: textcut.drop_foreign_script(it, l))],
    "J23": [("final_local_foreign_guard",
             lambda it, l, c: topic_country.final_local_foreign_guard(it, l, c["space"], c["home"]))],
    "J32": [("final_foreign_region_guard", lambda it, l, c: topic_country.final_foreign_region_guard(it, l, c["space"]))],
    "J38": [("final_urgent_guard", lambda it, l, c: urgent_guard.final_urgent_guard(it, l))],
    "J39": [("final_category_guard", lambda it, l, c: urgent_guard.final_category_guard(it, l))],
    "J40": [("final_category_guard", lambda it, l, c: urgent_guard.final_category_guard(it, l))],
    "J68": [("убрать заглушку вместо фото", _stub_photo_off)],
    "J44": [("final_foreign_tech_guard", lambda it, l, c: topic_country.final_foreign_tech_guard(it, l, c["home"]))],
}


def _hits(items, lang):
    """{класс: [карточки]} теми же детекторами пункта пропуска, что в конвейере."""
    ctx = {"lang": lang, "home": shelves.POOL_HOME.get(lang, ""), "space": border._space(lang)}
    found = {}
    for code, _name, det, _closed in border.REGISTRY:
        if det is None:
            continue
        hit = [x for x in items if det(x, ctx)]
        if hit:
            found[code] = hit
    return found, ctx


def repair(items, lang):
    """→ (карточки, действия). В режиме shadow возвращает карточки без изменений."""
    if MODE == "off":
        return items, []
    work = copy.deepcopy(items)
    actions = []
    found, ctx = _hits(work, lang)
    for code, cards in sorted(found.items(), key=lambda kv: int(kv[0][1:])):
        steps = PLAYBOOK.get(code)
        if not steps:
            actions.append((code, "красный, правки в справочнике нет", len(cards)))
            continue
        before = len(cards)
        for name, fn in steps:
            try:
                res = fn(work, lang, ctx)
                if isinstance(res, (list, tuple)):
                    work = _list(res)
            except Exception as e:                      # чинилка не должна ронять прогон
                actions.append((code, f"{name}: ошибка {type(e).__name__}: {str(e)[:60]}", before))
        again, _ = _hits(work, lang)
        left = again.get(code, [])
        if left and code in LAST_RESORT:
            ids = {id(x) for x in left}
            work = [x for x in work if id(x) not in ids]
            actions.append((code, f"{steps[0][0]} не помогла — снято карточек: {len(left)}", before))
        elif left:
            actions.append((code, f"{steps[0][0]}: осталось {len(left)} из {before}", before))
        else:
            actions.append((code, f"{steps[0][0]}: вылечено {before}", before))
    for code, text, n in actions:
        print(f"  🔧 чинилка [{lang}] {code}: {text}" + (" (тень)" if MODE != "live" else ""))
    return (work if MODE == "live" else items), actions
