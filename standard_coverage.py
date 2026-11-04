# -*- coding: utf-8 -*-
"""Карта «исправленная ошибка → замок → чинилка» (эталон, docs/STANDARD.md, раздел 13).

Ничего не принимается на веру: у каждого класса из docs/defects_journal.md записаны имена того, что его
держит (детектор, чинилка, тест), а скрипт ищет эти имена в коде обоих репозиториев. Класс без замка, без
чинилки или с именем, которого в коде нет, печатается красным. Новая строка журнала без записи здесь —
тоже красная: журнал и карта обязаны совпадать.

  python standard_coverage.py            # таблица и пробелы
  python standard_coverage.py --strict   # выход 1, если есть красное (для проверки в PR)

Только чтение.
"""
import re
import subprocess
import sys

import border

APP = "../Ticker247"

# id: (о чём, где живёт замок, [имена в коде], детектор в живой проверке, чинилка в конвейере)
#   детектор: "border" — в border.REGISTRY (гоняется на каждом прогоне), "check" — в standard_check, "audit" — только
#             ручной quality_audit.py, "test" — только тест, None — нет
#   чинилка: имя функции/шага, который чинит на лету; None — чинилки нет (красный флаг остаётся красным)
LOCKS = {
    "J1": ("«Новости из…» не внутренние", ["pool_shelf_fix", "final_shelf_guard"], "border", "final_shelf_guard"),
    "J2": ("«своё о своём» в «Мировых»", ["world_to_home_fix"], "border", "final_shelf_guard"),
    "J3": ("текст оборван в цитате", ["ends_inside_quote", "final_end_guard"], "border", "final_end_guard"),
    "J4": ("подзаголовок на конце текста", ["drop_trailing_heading"], "border", "drop_trailing_heading"),
    "J5": ("заголовок не влезает", ["first_sentence_title", "FitTitle"], "border", "first_sentence_title"),
    "J6": ("потеря отрицания в заголовке", ["NEG"], "audit", None),
    "J7": ("текст короче правила абзацев", ["card_text"], "audit", "reenrich"),
    "J8": ("подпись к фото вместо текста", ["_credit_instead_of_text"], "border", None),
    "J9": ("текст с полуфразы", ["final_start_guard", "_half_phrase_start"], "border", "final_start_guard"),
    "J10": ("родной язык с пометкой ru", ["native_lang"], "audit", "native_lang"),
    "J11": ("ведомственная скука на «Местных»", ["is_dull", "cap_dull"], "border-special", "cap_dull"),
    "J12": ("страны пула без изданий", ["POOL_COUNTRIES", "SOURCE_COUNTRY"], "test", "n/a"),
    "J13": ("признак «интересное» не доходит до базы", ["interesting"], "check", "interesting"),
    "J14": ("источники любопытного дают каталоги", ["is_longread_url"], "check", "n/a"),
    "J15": ("аннотация трансляции вместо текста", ["drop_stub_summaries", "is_stub_summary"], "border", "drop_stub_summaries"),
    "J16": ("длинный заголовок одним предложением", ["trim_context_tail"], "test", "trim_context_tail"),
    "J17": ("одно событие — несколько карточек", ["event_lines", "storydedup"], "test", "storydedup"),
    "J18": ("чужой алфавит в эфире", ["drop_foreign_script", "has_foreign_script"], "border", "drop_foreign_script"),
    "J19": ("исправления сервера не доходят до телефона", ["applyServerSnapshot", "NewsBufferSyncTest"], "test", "applyServerSnapshot"),
    "J20": ("ложная срочность по отрицанию", ["_NEGATION_BEFORE"], "test", "_NEGATION_BEFORE"),
    "J21": ("одно событие на двух языках", ["collapse_same_event"], "test", "collapse_same_event"),
    "J22": ("«Интересное» не по содержанию", ["is_curious_content"], "border", "is_curious_content"),
    "J23": ("«Местное» с чужим событием", ["final_local_foreign_guard"], "border", "final_local_foreign_guard"),
    "J24": ("лонгрид выдан за новость", ["is_longread_url"], "test", "is_longread_url"),
    "J25": ("потолок текста ~600", ["wants_page_body"], "audit", "wants_page_body"),
    "J26": ("перевод анонса вместо статьи", ["full_text_of"], "audit", None),
    "J27": ("страница взята, текста мало", ["card_text"], "audit", "reenrich"),
    "J28": ("шаг режет последнее предложение", ["strip_tail", "test_strip_tail"], "test", "strip_tail"),
    "J29": ("мера текста — знаки, а не абзацы", ["compose_card", "shown_count"], "test", "compose_card"),
    "J30": ("пропала полоса «Интересное»", ["InterestingMarkTest"], "test", "InterestingMark"),
    "J31": ("областные издания забивают «Новости из…»", ["PoolBalanceTest", "isRegionalPaper"], "test", "isRegionalPaper"),
    "J32": ("областное издание чужой страны", ["final_foreign_region_guard"], "border", "final_foreign_region_guard"),
    "J33": ("правило написано под один язык", ["test_rules_all_languages"], "test", "n/a"),
    "J34": ("карточки приложения минуют серверный конвейер", ["originOfPublisher", "PublisherOriginTest"], "test", "originOfPublisher"),
    "J35": ("тон правил один для всех пулов", ["Тон зависит от потока"], "test", "n/a"),
    "J36": ("лента пустеет, пока сервер молчит", ["shelfTopUp", "FeedFloor"], "check", "shelfTopUp"),
    "J37": ("дозор будил по любой громкой новости", ["event_tier"], "test", "event_tier"),
    "J38": ("«срочно» вне «Местных» без масштаба", ["final_urgent_guard"], "border", "final_urgent_guard"),
    "J39": ("рубрика вне списка вёрстки", ["final_category_guard", "layout_category"], "border", "final_category_guard"),
    "J40": ("«важное» сверх потолка", ["p2_excess"], "border-special", "p2_excess"),
    "J41": ("слово-признак внутри чужого слова", ["test_kw_boundary"], "test", "n/a"),
    "J42": ("«Местное» с чужим событием без страны от ИИ", ["local_event_country"], "test", "local_event_country"),
    "J43": ("полка не учитывала, откуда читают", ["final_local_foreign_guard", "ShelfByReaderTest"], "test", "shelfFor"),
    "J44": ("заявление зарубежной компании на «Местных»", ["tech_statement_country"], "border", "tech_statement_country"),
    "J45": ("«Новости из…» американца пуста", ["POOL_COUNTRIES"], "check", None),
    "J46": ("полки стран не читались приложением", ["fetchCountryShelf", "CountryShelves"], "test", "n/a"),
    "J48": ("подготовленное висело как срочное", ["prepared_material", "final_prepared_guard"], "test", "final_prepared_guard"),
    "J50": ("заявление о гражданах за рубежом на «Местных»", ["final_statement_country_guard"], "test", "final_statement_country_guard"),
    "J51": ("издание о своей стране на «Местных» москвича", ["final_own_subject_guard"], "test", "final_own_subject_guard"),
    "J52": ("дозор ничего не публиковал", ["patrol_world"], "test", "n/a"),
    "J53": ("слоты под один город", ["POOL_MAIN_BANDS", "test_schedule"], "test", "n/a"),
    "J54": ("у ИИ-этапов нет общего устава", ["shared_charter"], "test", "shared_charter"),
    "J55": ("продолжение сюжета новой карточкой", ["find_reposts"], "test", "find_reposts"),
    "J56": ("расход ИИ вдвое выше плана", ["slot_served"], "test", "slot_served"),
    "J57": ("заголовок в дайджесте обрезан", ["DigestTextTest"], "test", "n/a"),
    "J58": ("мелкое чужое / кадровый ход в «Мировых»", ["плановый уход"], "test", "n/a"),
    "J59": ("освобождение зама в «Срочном»", ["personnel_change", "final_personnel_guard"], "test", "final_personnel_guard"),
    "J60": ("анонс вместо статьи при дописанной странице", ["reenrich"], "test", "reenrich"),
    "J61": ("«срочно» ставят слова, а не смысл", ["vital_ai", "serverVital"], "test", "vital_ai"),
    "J62": ("лицо не видно в плитке", ["FocalCrop", "FaceFocus"], "test", "FocalCrop"),
    "J63": ("итог после шагов не смотрит никто", ["reader_guard"], "test", "reader_guard"),
    "J64": ("потолок расхода смотрит на сброшенный счёт", ["save_ai_spend", "test_ai_spend"], "test", "save_ai_spend"),
    "J65": ("срочное чужой страны через полку соседа", ["serverVital", "URGENT_LOCAL_ONLY"], "test", "serverVital"),
    "J66": ("полка соседей США пуста", ["FAT_ONLY_IN"], "check", None),
    "J71": ("плановое объявление помечено «срочно»", ["URGENT_LOCAL_ONLY"], "audit", None),
    "J70": ("суть новости не ясна из одной строки", ["clean_line", "needs_line", "compress"], "test", "clean_line"),
    "J69": ("читателю вне пула «Новости из…»", ["LiveMatrixTest", "isNeighbour"], "test", "isNeighbour"),
    "J68": ("заглушка вместо фото", ["_stub_photo", "STUB_IMG"], "border", "_stub_photo_off"),
    "J67": ("«каша» у читателя из России", ["muscovitesLocalNeverHolds"], "test", None),
}


def journal_ids():
    ids = []
    for line in open("docs/defects_journal.md", encoding="utf-8"):
        m = re.match(r"\| (J\d+) ", line)
        if m:
            ids.append(m.group(1))
    return ids


def present(token):
    """Есть ли имя в коде бэкенда или приложения."""
    for root in (".", APP):
        r = subprocess.run(["grep", "-rqsF", "--include=*.py", "--include=*.kt", "--include=*.md", "--include=*.yml",
                            "--exclude-dir=.git", "--exclude-dir=build", "--exclude=standard_coverage.py",
                            "--exclude=defects_journal.md", token, root], capture_output=True)
        if r.returncode == 0:
            return True
    return False


def main():
    strict = "--strict" in sys.argv
    border_codes = {c for c, _, d, _ in border.REGISTRY if d is not None}
    red, rows = [], []
    ids = journal_ids()
    for jid in ids:
        if jid not in LOCKS:
            red.append((jid, "в журнале есть, в карте нет"))
            continue
        what, tokens, det, fix = LOCKS[jid]
        missing = [t for t in tokens if not present(t)]
        if missing:
            red.append((jid, f"имени нет в коде: {missing}"))
        if det == "border-special" and jid not in ("J11", "J40"):
            red.append((jid, "особый детектор заявлен для неизвестного класса"))
        if det == "border" and jid not in border_codes:
            red.append((jid, "заявлен детектор в border.REGISTRY, а его там нет"))
        if det is None:
            red.append((jid, "нет ни детектора, ни теста"))
        if fix is None:
            red.append((jid, "нет чинилки: красный флаг останется красным"))
        elif fix != "n/a" and not present(fix):
            red.append((jid, f"чинилки «{fix}» нет в коде"))
        rows.append((jid, what, det, fix))
    for jid in LOCKS:
        if jid not in ids:
            red.append((jid, "есть в карте, нет в журнале"))
    print(f"Классов в журнале: {len(ids)}; в карте: {len(LOCKS)}")
    kinds = {}
    for _, _, det, fix in rows:
        kinds[(det, bool(fix))] = kinds.get((det, bool(fix)), 0) + 1
    for (det, fx), n in sorted(kinds.items(), key=lambda x: -x[1]):
        print(f"  детектор={det or 'нет'}, чинилка={'есть' if fx else 'нет'}: {n}")
    print(f"\nКРАСНОЕ: {len(red)}")
    for jid, why in red:
        print(f"  🔴 {jid} {LOCKS.get(jid, ('',))[0][:45]} — {why}")
    sys.exit(1 if (strict and red) else 0)


if __name__ == "__main__":
    main()
