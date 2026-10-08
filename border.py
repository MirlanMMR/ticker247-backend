"""Пункт пропуска: фотороботы всех видов ошибок, с которыми мы уже сталкивались.

Последний шаг конвейера перед записью в базу (после редакторов и стражей).
Для каждого класса из docs/defects_journal.md здесь есть детектор — чистая
функция «карточка → да/нет». Пункт пропуска прогоняет по ним итоговую ленту и:

  · печатает таблицу «класс → сколько нашли» (видно в логе запуска);
  · если класс закрыт (CLOSED) и нашёлся — это ВОЗВРАТ ошибки: печатает
    ::error:: (виден в GitHub Actions) и пишет в border_report.md, который
    коммитится вместе с editor_report.md;
  · НИЧЕГО не снимает и не правит: чинят стражи выше (final_*_guard, cap_dull),
    здесь только проверка их работы. Владелец: «как полицейский с фотографией
    преступника» — полицейский задерживает, но решает суд; а у нас суд — тесты.

Номера (J1…) — строки журнала. Добавляя класс в журнал, добавь сюда детектор.
Класс CLOSED = мы считаем его побеждённым; любое срабатывание тогда тревога.
"""
import re

from dull import is_dull
from shelves import pool_shelf_fix, world_to_home_fix, POOL_HOME
from topic_country import foreign_topic
from textcut import ends_inside_quote, drop_trailing_heading, sentence_start, is_stub_summary, has_foreign_script

TITLE_FIT = 120
_CREDIT = re.compile(r"^\s*(автор фото|подпись к фото|image source|image caption|photo credit|"
                     r"фото:|foto:|crédito)", re.I)


def _summary(x):
    return (x.get("summary") or "").rstrip()


def _pool_foreign(x, ctx):
    return pool_shelf_fix(x, ctx["space"]) == "world" or foreign_topic(x, ctx["space"])


def _world_but_home(x, ctx):
    return world_to_home_fix(x, ctx["home"], ctx["space"]) is not None


def _open_quote(x, ctx):
    return bool(_summary(x)) and ends_inside_quote(_summary(x))


def _trailing_heading(x, ctx):
    s = _summary(x)
    return bool(s) and drop_trailing_heading(s) != s


def _title_too_long(x, ctx):
    return len(x.get("title") or "") > TITLE_FIT


def _credit_instead_of_text(x, ctx):
    return bool(_CREDIT.match(x.get("summary") or ""))


def _half_phrase_start(x, ctx):
    s = x.get("summary") or ""
    return bool(s) and sentence_start(s) != s


def _foreign_script(x, ctx):
    return has_foreign_script(x)


def _stub_summary(x, ctx):
    return is_stub_summary(x)


def _dull_local(x, ctx):
    return ctx["lang"] == "ru" and x.get("scope") == "local" and is_dull(x)


# (код журнала, имя, детектор, закрыт ли класс)
REGISTRY = [
    ("J1", "«Новости из» с мировым или чужим событием", _pool_foreign, True),
    ("J2", "«своё о своём» лежит в «Мировых»", _world_but_home, True),
    ("J3", "текст оборван внутри цитаты", _open_quote, True),
    ("J4", "подзаголовок раздела на конце текста", _trailing_heading, True),
    ("J5", "заголовок длиннее карточки (>120)", _title_too_long, False),
    ("J8", "подпись к фото вместо текста", _credit_instead_of_text, True),
    ("J9", "текст начат с полуфразы", _half_phrase_start, True),
    ("J18", "чужой алфавит без перевода (грузинский и др.)", _foreign_script, True),
    ("J15", "аннотация страницы-трансляции вместо текста", _stub_summary, True),
    ("J11", "ведомственное на «Местных» (>25% полки)", None, False),   # доля, см. control
]


def control(items, lang, report=None):
    """→ {код: [карточки]}. Печатает таблицу; тревога на возврат закрытых."""
    ctx = {"lang": lang, "home": POOL_HOME.get(lang, ""), "space": _space(lang)}
    found, returned = {}, []
    for code, name, det, closed in REGISTRY:
        if det is None:
            continue
        hits = [x for x in items if det(x, ctx)]
        found[code] = hits
        if hits and closed:
            returned.append((code, name, hits))
    # J11 считаем долей: одна скучная карточка — норма, четверть полки — нет
    local = [x for x in items if x.get("scope") == "local" and not x.get("bridge")]
    dull = [x for x in local if _dull_local(x, ctx)]
    share = len(dull) / len(local) if local else 0
    found["J11"] = dull if share > 0.25 else []

    print(f"  🛂 Пункт пропуска [{lang}]: " + (
        ", ".join(f"{c}={len(v)}" for c, v in found.items() if v) or "чисто"))
    for code, name, hits in returned:
        print(f"::error title=Возврат ошибки {code} [{lang}]::{name}: {len(hits)} "
              f"— см. docs/defects_journal.md")
        for x in hits[:3]:
            print(f"       · {x.get('source','?')}: {(x.get('title') or '')[:70]}")
    if report is not None:
        report.append((lang, {c: len(v) for c, v in found.items()},
                       [(c, n) for c, n, _ in returned]))
    return found


def _space(lang):
    import ast
    try:
        tree = ast.parse(open("fetch_news.py", encoding="utf-8").read())
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    getattr(t, "id", "") == "POOL_COUNTRIES" for t in node.targets):
                return set(ast.literal_eval(node.value).get(lang, ())) | {POOL_HOME.get(lang, "")}
    except Exception:
        pass
    return {POOL_HOME.get(lang, "")}


def write_report(report, path="border_report.md"):
    """Короткий отчёт для репозитория: что нашли на выходе по каждому пулу."""
    lines = ["# Пункт пропуска — итог последнего запуска", ""]
    for lang, counts, returned in report:
        row = ", ".join(f"{c}: {n}" for c, n in counts.items() if n) or "чисто"
        lines.append(f"- **{lang}** — {row}")
        for code, name in returned:
            lines.append(f"  - ⚠️ ВОЗВРАТ {code}: {name}")
    lines += ["", "Коды — строки `docs/defects_journal.md`."]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
