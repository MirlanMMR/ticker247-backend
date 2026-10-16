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


# ── Подготовленный без спешки материал не бывает срочным (журнал J48, 15.10.2026) ──────────
# Случай: «Первая победа задаёт хорошую ноту»: как Элис Старцева завоевала историческое серебро для
# России» висела в шторке читателя (пул «Россия», регион Москва). Правило «национальная гордость»
# поднимает победу (медаль + «завоевала»), а это не новость, а подготовленная статья: цитата в начале,
# двоеточие, «как…». Владелец: «статья подготовлена без спешки». Срочное — то, что случилось сейчас и
# меняет день человека. Признаки неспешного материала: цитата-зачин с двоеточием, «: как …»,
# интервью, колонка, разбор, портрет, лонгрид. Исключение — беда (жертвы, взрыв, землетрясение):
# «Землетрясение: как это было» всё равно срочное, пока идёт.
PREPARED = re.compile(
    r"^\W*[«\"“„][^»\"”]{5,100}[»\"”]\s*:"                        # «Цитата»: пояснение
    r"|:\s*(?:как|how|cómo|como|comment)\s+\w+"                    # …: как X добился
    r"|\b(?:интервью|колонка|лонгрид|репортаж|портрет|разбор|мнение|эксклюзив)\b\s*[:|—-]"
    r"|^\W*(?:интервью|колонка|лонгрид|репортаж|портрет|разбор|мнение)\b"
    r"|\b(?:interview|entrevista|opinion|column|longread|profile)\s*[:|—-]|^\W*(?:interview|entrevista|entretien)\b",
    re.I)


def prepared_material(x):
    """Карточка со «срочно» или «важным», но по форме — подготовленный материал, а не новость момента."""
    if x.get("vital"):
        return False
    if x.get("category") not in URGENT_CATS and (x.get("priority") or 0) < 2:
        return False
    title = (x.get("title") or "").strip()
    if not PREPARED.search(title):
        return False
    text = f"{title} {(x.get('summary') or '')[:400]}"
    return not (_BIG.search(text) or casualties(text) >= 1)


def final_prepared_guard(items, lang):
    """Снимает «срочно» и «важное» с подготовленных материалов. Карточку из ленты не убирает."""
    hit = [x for x in items if prepared_material(x)]
    for x in hit:
        if x.get("category") in URGENT_CATS:
            x["category"] = "NEWS" if not str(x.get("topic") or "").lower().startswith("sport") else "SPORT"
        x["priority"] = min(int(x.get("priority") or 0), 1)
    if hit:
        print(f"  📰 Подготовленный материал без «срочно» [{lang}]: снято {len(hit)}")
        for x in hit[:6]:
            print(f"       · {x.get('source','?')}: {(x.get('title') or '')[:60]}")
    return items


# ── Кадровая перестановка чиновника — не срочное (журнал J54, 16.10.2026) ─────────────────
# Случай: «освобождён от должности» заместитель (не председатель, не министр) попал в «Срочное».
# Освобождения, назначения и увольнения чиновников — рутина власти: происходят каждую неделю и
# не меняют день человека. Срочным остаётся только уход главы государства или правительства
# (президент, премьер, канцлер, король…) — это и в подъёме мировых («смерть или отставка главы
# государства»). Исключения те же, что везде: беда (жертвы, взрыв), жизненно важное.
_PERSONNEL = re.compile(
    r"освобожд[её]н\w*\s+от\s+(?:занимаемой\s+)?должност|освободил\w*\s+от\s+должност|"
    r"снят\w*\s+с\s+(?:занимаемой\s+)?должност|сняли\s+с\s+должност|"
    r"уволен\w*\s+с\s+должност|отправлен\w*\s+в\s+отставк|отправил\w*\s+в\s+отставк|"
    r"освобождение\s+от\s+должност|отстранён\w*\s+от\s+должност|отстранен\w*\s+от\s+должност|"
    r"назначен\w*\s+(?:на\s+должност|(?:нов\w+\s+)?(?:заместител|вице|первы|исполня|врио))|"
    r"кызматынан\s+(?:бошотул|алынды|кеткен)|кызматтан\s+(?:бошотул|алын)|"
    r"лавозимидан\s+(?:озод|бўшат|бушат)|лаузимидан\s+озод|"
    r"relieved\s+of\s+(?:his|her|their)\s+(?:post|duties|position)|removed\s+from\s+(?:his|her|their)\s+(?:post|position)|"
    r"dismissed\s+from\s+(?:his|her|their)\s+(?:post|position)|(?:fired|sacked|dismissed|removed|replaced)\s+as\s+(?:deputy|vice|head of|director|chief)|"
    r"destituid[oa]\s+de\s+su\s+cargo|cesad[oa]\s+(?:de|en)\s+su\s+cargo|relev[oó]\s+del\s+cargo|"
    r"exonerad[oa]\s+do\s+cargo|demitid[oa]\s+do\s+cargo|"
    r"relevé\s+de\s+ses\s+fonctions|limogé", re.I)
# Глава государства/правительства: его уход — событие страны, поэтому срочное остаётся
_TOP_OFFICE = re.compile(
    r"(?<!вице-)(?<!вице )президент|(?<!вице-)(?<!вице )премьер|канцлер|король|королев|император|шах\b|эмир|султан|"
    r"глав[аыуе]\s+(?:государств|правительств)|председател\w+\s+(?:правительств|кабинет\w*\s+министр|совет\w*\s+министр)|"
    r"спикер\s+(?:парламент|жогорку|мажилис)|"
    r"\b(?:president|prime\s+minister|chancellor|king|queen|emperor|head\s+of\s+(?:state|government))\b|"
    r"presidente|primer\s+ministro|primeiro[- ]ministro|premier\s+ministre|chancelier|roi\b|rey\b|rei\b", re.I)


def personnel_change(x):
    """Срочная/важная карточка о кадровой перестановке не первого лица страны."""
    if x.get("vital"):
        return False
    if x.get("category") not in URGENT_CATS and (x.get("priority") or 0) < 2:
        return False
    title = (x.get("title") or "").strip()
    if not _PERSONNEL.search(title):
        return False
    text = f"{title} {(x.get('summary') or '')[:400]}"
    return not (_TOP_OFFICE.search(title) or _BIG.search(text) or casualties(text) >= 1)


def final_personnel_guard(items, lang):
    """Снимает «срочно» и «важное» с кадровых перестановок. Карточку из ленты не убирает."""
    hit = [x for x in items if personnel_change(x)]
    for x in hit:
        if x.get("category") in URGENT_CATS:
            x["category"] = "NEWS"
        x["priority"] = min(int(x.get("priority") or 0), 1)
    if hit:
        print(f"  🧑‍💼 Кадровая перестановка без «срочно» [{lang}]: снято {len(hit)}")
        for x in hit[:6]:
            print(f"       · {x.get('source','?')}: {(x.get('title') or '')[:60]}")
    return items


# ── Рубрика и приоритет на выходе (журнал J39, J40, 15.10.2026) ──────────────────────────
#
# Читатель рубрик не видит: полки «Местные», «Мировые», «Новости из…», штат/регион, а внутри
# полки новости ложатся как в мировых изданиях — политика выше, культура и спорт ниже
# (решение владельца). Рубрика нужна ОДНОМУ — порядку. Поэтому на выходе сервер отдаёт рубрики
# только из списка вёрстки приложения (LayoutCategory.kt), а подрубрику — в поле topic.
# Рубрика вне списка раньше уезжала в хвост полки по алфавиту: война и общество — ниже моды.
LAYOUT = {"URGENT", "URGENT_LOCAL_ONLY", "POLITICS", "WORLD", "INCIDENTS", "NEWS", "TECH", "CULTURE",
          "SPORT", "MONEY", "HEALTH", "LIFE", "TOURS", "AUTO", "FASHION", "STARS", "GOOD", "KG",
          "CRYPTO", "CURRENCY"}
ALIAS = {"WAR": "WORLD", "SCIENCE": "TECH", "ECONOMY": "MONEY", "SOCIETY": "NEWS",
         "EDUCATION": "NEWS", "REALTY": "LIFE"}


def layout_category(cat):
    """Рубрика из списка вёрстки: подрубрика после «/» отбрасывается, незнакомое — NEWS."""
    main = (cat or "").split("/")[0].strip().upper()
    if not main:
        return "NEWS"
    return main if main in LAYOUT else ALIAS.get(main, "NEWS")


# «Важное» (priority 2) — валюта карусели: у es и fr рубрики URGENT нет вовсе, и карусель
# собирается из двоек. Но в en двоек 49 из 190 (26%): ИИ-разметка ставит 2 всему, что назвала
# срочным, а cap_urgent снимает рубрику, не трогая приоритет. Потолок на полку — не больше
# P2_CAP_PER_SCOPE самых свежих; остальным 1 («важное, тихо»). Карусель берёт 10 мест по кругу
# между полками, так что по 6 на полку её не оставляют пустой.
P2_CAP_PER_SCOPE = 6


def p2_excess(items):
    """Карточки с priority>=2 вне срочных/жизненно важных/выбора редактора сверх потолка полки."""
    by = {}
    for x in items:
        if (x.get("priority") or 0) != 2 or x.get("category") in URGENT_CATS or x.get("vital") \
                or x.get("isEditorCarousel") or x.get("isEditorImportant"):
            continue
        by.setdefault(x.get("scope"), []).append(x)
    out = []
    for lst in by.values():
        lst.sort(key=lambda x: x.get("publishedAt") or 0, reverse=True)
        out.extend(lst[P2_CAP_PER_SCOPE:])
    return out


def final_category_guard(items, lang):
    """Рубрика — из списка вёрстки; «важного» не больше потолка на полку."""
    fixed = 0
    for x in items:
        c = x.get("category")
        b = layout_category(c)
        if b != c and c not in ("CURRENCY", "CRYPTO"):
            if "/" in (c or "") and not x.get("topic"):
                x["topic"] = c.lower()           # подрубрика не пропадает: «sport/football»
            x["category"] = b
            fixed += 1
    cut = p2_excess(items)
    for x in cut:
        x["priority"] = 1
    if fixed or cut:
        print(f"  🗂 Рубрики вёрстки и потолок «важного» [{lang}]: рубрик приведено {fixed}, "
              f"приоритет снижен {len(cut)}")
    return items
