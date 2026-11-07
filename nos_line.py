# -*- coding: utf-8 -*-
"""Сжатие длинного предложения для режима НОС «Новости одной строкой» (J70, правила владельца 04.11.2026).

Сжимаем по смыслу, а не обрезаем: «…» и обрывки запрещены. Правила владельца:
  1. числа цифрами с окончанием: «четырёх» → «4х», «трёх» → «3х», «двух» → «2х» (остальные — просто цифра);
  2. придаточное уходит, предложение кончается точкой: «Тегеран заявил об уничтожении 4х танкеров в Ормузском проливе
     из-за …» → «Тегеран заявил об уничтожении 4х танкеров в Ормузском проливе.» («из-за чего — это детали»);
  3. точка вместо запятой на месте разреза.

Чистые функции, без сети и ИИ; результат ВСЕГДА проходит `editor.clean_line` (отрицание как у заголовка, числа только
из текста, длина): сжатие, потерявшее смысл, не принимается. Это запасной путь, когда ИИ строки не дал, и дожим,
когда строка ИИ чуть длиннее лимита. Языки: ru, en, es, pt, fr (слова чисел и союзы — свои у каждого).
"""
import re

# Порог — НЕ запас, а реальная ёмкость экрана виджета: метка и время стоят в верхней строке слайда и ширину не отнимают, поэтому
# предложение получает всю ширину — 2 строки × ~50 знаков (приложение: PagerWidgetStyle.capacity; 360 dp → 112, 320 dp → 100). Сокращаем только когда предложение не помещается и только по смыслу —
# убирая придаточное, а не обрезая по числу знаков (владелец 04.11)
LIMIT = 100


# ── даты: «5 ноября» → «05.11» (владелец 04.11: «месяцы тоже сократим», «с 05.11 изменятся схемы движения…»). В английском «5.11» читают и как 5 ноября, и как 11 мая,
# поэтому там цифровая дата не ставится — только «November» → «Nov».
MONTHS = {
    "ru": "января февраля марта апреля мая июня июля августа сентября октября ноября декабря".split(),
    "es": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split(),
    "pt": "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro".split(),
    "fr": "janvier février mars avril mai juin juillet août septembre octobre novembre décembre".split(),
}
_DATE = {
    "ru": r"(\d{1,2})\s+(%s)(?![\w])",
    "es": r"(\d{1,2})\s+de\s+(%s)(?![\w])",
    "pt": r"(\d{1,2})\s+de\s+(%s)(?![\w])",
    "fr": r"(\d{1,2}|1er)\s+(%s)(?![\w])",
}


def _date_sub(lang):
    names = MONTHS.get(lang)
    if not names:
        return None
    pat = re.compile(_DATE[lang] % "|".join(names), re.I | re.U)
    idx = {n: i + 1 for i, n in enumerate(names)}
    return pat, lambda m: f"{int(m.group(1).replace('er', '')):02d}.{idx[m.group(2).lower()]:02d}"


def normalize_dates(text: str, lang: str) -> str:
    """«5 ноября» → «05.11». Нужна и сжатию, и замку чисел: «05.11» в строке законно, когда в источнике «5 ноября»."""
    sub = _date_sub(lang)
    return sub[0].sub(sub[1], text) if sub else text

# ── числа словами → цифры (2…10; «один» не трогаем: «один из», «одним словом»). Окончание «х» — как просит владелец
NUMERALS = {
    "ru": {"двух": "2х", "трёх": "3х", "трех": "3х", "четырёх": "4х", "четырех": "4х",
           "два": "2", "две": "2", "три": "3", "четыре": "4", "пять": "5", "пяти": "5", "шесть": "6", "шести": "6",
           "семь": "7", "семи": "7", "восемь": "8", "восьми": "8", "девять": "9", "девяти": "9",
           "десять": "10", "десяти": "10"},
    "en": {"two": "2", "three": "3", "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
           "nine": "9", "ten": "10"},
    "es": {"dos": "2", "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6", "siete": "7", "ocho": "8",
           "nueve": "9", "diez": "10"},
    "pt": {"dois": "2", "duas": "2", "três": "3", "quatro": "4", "cinco": "5", "seis": "6", "sete": "7",
           "oito": "8", "nove": "9", "dez": "10"},
    "fr": {"deux": "2", "trois": "3", "quatre": "4", "cinq": "5", "six": "6", "sept": "7", "huit": "8",
           "neuf": "9", "dix": "10"},
}

# ── где главная мысль кончается и начинается «из-за чего»: союзы придаточных и обстоятельств причины/фона
CUT_MARKERS = {
    "ru": r"из-за|на\s+фоне|на\s+этом\s+фоне|после\s+того,?\s+как|в\s+связи\s+с|вследствие|по\s+причине|"
          r"в\s+то\s+время,?\s+как|тогда\s+как|несмотря\s+на|в\s+ответ\s+на|чтобы|после|перед|пока",
    "en": r"because\s+of|due\s+to|amid|after|following|despite|in\s+response\s+to|while|as\s+a\s+result\s+of|"
          r"ahead\s+of|before",
    "es": r"debido\s+a|por\s+culpa\s+de|tras|después\s+de|en\s+medio\s+de|a\s+raíz\s+de|pese\s+a|mientras|antes\s+de",
    "pt": r"por\s+causa\s+de|devido\s+a|após|depois\s+de|em\s+meio\s+a|apesar\s+de|enquanto|antes\s+de",
    "fr": r"à\s+cause\s+de|en\s+raison\s+de|suite\s+à|après|alors\s+que|dans\s+un\s+contexte\s+de|malgré|"
          r"en\s+réponse\s+à|avant",
}


# ── общепринятые сокращения (ярус А, владелец 04.11: «какие слова ещё можно сокращать?»). Только то, что читатель понимает
# без расшифровки и что не меняет смысл; склоняемые слова заменяются несклоняемыми (США, ООН, ЕС, ЧС). Применяются по одному
# и только пока предложение не влезает: хватает места — слова остаются полными.
ABBREVIATIONS = {
    "ru": [
        (r"Соединённ(?:ые|ых|ым|ыми)\s+Штат(?:ы|ов|ам|ами|ах)(?:\s+Америки)?", "США"),
        (r"Соединенн(?:ые|ых|ым|ыми)\s+Штат(?:ы|ов|ам|ами|ах)(?:\s+Америки)?", "США"),
        (r"Российск(?:ая|ой|ую)\s+Федераци(?:я|и|ю|ей)", "РФ"),
        (r"Организаци(?:я|и|ю|ей)\s+Объединённых\s+Наций", "ООН"),
        (r"Европейск(?:ий|ого|ому|им|ом)\s+союз(?:а|у|ом|е)?", "ЕС"),
        (r"Министерств(?:о|а|у|ом|е)\s+иностранных\s+дел", "МИД"),
        (r"Министерств(?:о|а|у|ом|е)\s+внутренних\s+дел", "МВД"),
        (r"Министерств(?:о|а|у|ом|е)\s+по\s+чрезвычайным\s+ситуациям", "МЧС"),
        (r"чрезвычайн(?:ая|ой|ую|ую|ые)\s+ситуаци(?:я|и|ю|ей|й)", "ЧС"),
        (r"чрезвычайн(?:ое|ого|ым|ом)\s+положени(?:е|я|ю|ем|и)", "ЧП"),
        (r"дорожно-транспортн(?:ое|ого|ому|ым|ом)\s+происшестви(?:е|я|ю|ем|и)", "ДТП"),
        (r"беспилотн(?:ый|ого|ому|ым|ом|ые|ых|ыми)\s+летательн(?:ый|ого|ому|ым|ом|ые|ых|ыми)\s+аппарат(?:а|у|ом|е|ы|ов|ам|ами|ах)?", "БПЛА"),
        (r"Следственн(?:ый|ого|ому|ым|ом)\s+комитет(?:а|у|ом|е)?", "СК"),
        (r"Генеральн(?:ая|ой|ую)\s+прокуратур(?:а|ы|е|у|ой)", "Генпрокуратура"),
        (r"(\d)\s*процент(?:а|ов|ы)?", r"\1%"),
        (r"(\d)\s+миллиард(?:а|ов|ы)?", r"\1 млрд"),
        (r"(\d)\s+миллион(?:а|ов|ы)?", r"\1 млн"),
        (r"(\d)\s+тысяч(?:а|и)?(?![\w])", r"\1 тыс."),
        (r"(\d)\s+километр(?:а|ов)?", r"\1 км"),
        (r"(\d[\d\s.,]*)(\s(?:млн|млрд|тыс\.))?\s+доллар(?:а|ов|ы)?(?:\s+США)?", r"$\1\2"),
        (r"(\d[\d\s.,]*)(\s(?:млн|млрд|тыс\.))?\s+евро", r"€\1\2"),
        (r"премьер-министр(\w*)", r"премьер\1"),
    ],
    "en": [
        (r"United\s+States", "US"), (r"United\s+Nations", "UN"), (r"European\s+Union", "EU"),
        (r"Prime\s+Minister", "PM"), (r"(\d)\s+percent", r"\1%"), (r"(\d)\s+million", r"\1M"),
        (r"(\d)\s+billion", r"\1B"), (r"(\d)\s+kilometers?", r"\1 km"),
        (r"\$(\d[\d.,]*)\s*M\b", r"$\1M"),
        (r"\b(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]{2,8}\b", r"\1"),
        (r"\bSept(?:ember)?\b", "Sep"),
    ],
    "es": [
        (r"Estados\s+Unidos", "EE.UU"), (r"Naciones\s+Unidas", "ONU"), (r"Unión\s+Europea", "UE"),
        (r"(\d)\s+por\s+ciento", r"\1%"), (r"(\d)\s+millones", r"\1 M"), (r"(\d)\s+kilómetros", r"\1 km"),
    ],
    "pt": [
        (r"Estados\s+Unidos", "EUA"), (r"Organização\s+das\s+Nações\s+Unidas", "ONU"), (r"União\s+Europeia", "UE"),
        (r"(\d)\s+por\s+cento", r"\1%"), (r"(\d)\s+milhões", r"\1 mi"), (r"(\d)\s+quilômetros", r"\1 km"),
    ],
    "fr": [
        (r"États-Unis", "É.-U."), (r"Nations\s+unies", "ONU"), (r"Union\s+européenne", "UE"),
        (r"(\d)\s+pour\s+cent", r"\1%"), (r"(\d)\s+millions", r"\1 M"), (r"(\d)\s+kilomètres", r"\1 km"),
    ],
}


def abbreviate(text: str, lang: str, limit: int = LIMIT) -> str:
    """Общепринятые сокращения по одному, пока длина больше [limit]; хватает места — слова остаются полными."""
    t = text
    if len(t) > limit:
        t = normalize_dates(t, lang)                       # «5 ноября» → «5.11»
    for pat, repl in ABBREVIATIONS.get(lang, []):
        if len(t) <= limit:
            break
        t = re.sub(pat, repl, t, flags=re.I | re.U)
    return t


_SENT_END = re.compile(r"(?<=[.!?])\s+(?=[«\"“„(]?[^\W\d_][^\W_]*)", re.U)


def numerals_to_digits(text: str, lang: str) -> str:
    """«четырёх танкеров» → «4х танкеров»; слова вне словаря и «один» не трогаются."""
    table = NUMERALS.get(lang) or {}
    if not table:
        return text
    pat = re.compile(r"(?<![\w-])(" + "|".join(sorted(map(re.escape, table), key=len, reverse=True)) + r")(?![\w-])",
                     re.I | re.U)
    return pat.sub(lambda m: table[m.group(1).lower()], text)


def first_sentence(text: str) -> str:
    t = re.sub(r"\s+", " ", text or "").strip()
    first = _SENT_END.split(t, 1)[0] if t else ""
    return first if len(first) >= 25 else t


def _finish(head: str):
    """Предложение кончается точкой (не запятой, не двоеточием, не «…»)."""
    head = head.strip().rstrip(" ,;:—–-…").strip()
    if not head:
        return None
    return head if head[-1] in ".!?" else head + "."


# Слова, на которых предложение кончаться не может: после них мысль обрывается («…, then», «…в», «…of the»)
DANGLING = {
    "ru": "и а но или в на с со к по из от до за для при о об про над под у не ни же бы как что чтобы то это его её их",
    "en": "and or but the a an of in on at to for with from by as that then than who which is are was were its his her their",
    "es": "y o pero el la los las un una de en a con por para que su sus como entre sobre del al",
    "pt": "e ou mas o a os as um uma de em a com por para que seu sua como entre sobre do da no na",
    "fr": "et ou mais le la les un une de du des en à avec par pour que son sa ses comme entre sur au aux",
}
MIN_KEEP = 0.55   # голова должна сохранить не меньше 55% предложения: «Un jeune de 18 ans arrêté.» (из 114 знаков — 26) — это уже не суть


def _dangling(head: str, lang: str) -> bool:
    words = re.findall(r"[^\W\d_]+", head.lower(), re.U)
    return bool(words) and words[-1] in set(DANGLING.get(lang, "").split())


def compress(text, lang: str, limit: int = LIMIT):
    """Сжатое предложение (≤ limit знаков, с точкой в конце) или None, если сжать нечем БЕЗ ПОТЕРИ СМЫСЛА.

    Порядок: первое предложение → числа цифрами → сокращения слов (смысл целиком) → если всё ещё длинно, режем:
      1) на союзе придаточного («из-за», «на фоне», «после того как»…) — самая длинная голова, что влезает;
      2) только если союзов нет — на запятой («точка вместо запятой»).
    Голова принимается, если: ≥ 25 знаков, сохранила ≥ 55% предложения (MIN_KEEP), не кончается висячим словом («и», «в», «then»).
    Иначе None: лучше не показывать, чем показать обрывок (владелец 04.11: «никаких сокращений»)."""
    if not isinstance(text, str) or not text.strip():
        return None
    t = numerals_to_digits(first_sentence(text), lang).rstrip(" …")
    t = abbreviate(t, lang, limit - 1)                    # сначала сокращения слов: смысл остаётся целиком
    if len(t) <= limit - (0 if t[-1:] in ".!?" else 1):
        return _finish(t)
    room, need = limit - 1, max(25, int(len(t) * MIN_KEEP))   # место под точку; минимум смысла

    def fit(heads):
        ok = [h.rstrip(" ,;:—–-") for h in heads]
        ok = [h for h in ok if need <= len(h) <= room and not _dangling(h, lang)]
        return max(ok, key=len) if ok else None

    marker = CUT_MARKERS.get(lang)
    heads = [t[:m.start()] for m in re.finditer(r"[\s,]+(?:%s)(?=[\s,])" % marker, t, re.I | re.U)] if marker else []
    best = fit(heads) or fit([t[:m.start()] for m in re.finditer(r",\s", t)])      # сначала придаточное, потом запятая
    return _finish(best) if best else None


_TAG = re.compile(r"^\s*(?:срочно|важно|breaking|urgent|urgente|à la une)\s*[!:.\-–—]*\s*", re.I)
_NUM = re.compile(r"\d[\d\s.,]*\d|\d")
TITLE_CARD = 72   # заголовок в карточке карусели при шрифте не мельче 16sp: 3 строки по ≈ 26 знаков с переносами


MIN_COVER = 0.4    # строка обязана сохранить не меньше 40% ключевых слов заголовка (банки крови: 30% → отклонена; пример владельца: 67%)
_STOPSTEMS = set()


def _stems(text: str) -> set:
    """Основы ключевых слов: первые 5 букв слов от 5 букв (грубо, но одинаково для всех языков)."""
    return {w[:5] for w in re.findall(r"[^\W\d_]{5,}", (text or "").lower(), re.U)}


def _script(text: str) -> str:
    cyr = len(re.findall(r"[а-яёіїєөүң]", (text or "").lower()))
    lat = len(re.findall(r"[a-zà-ÿ]", (text or "").lower()))
    return "cyr" if cyr > lat else "lat"


def keeps_title_essence(line: str, title: str) -> bool:
    """Строка — сжатие ЗАГОЛОВКА, а не новый пересказ из текста (владелец 04.11: «Кибератака на французские банки крови: системы
    холодильников затронуты» вместо «Банки крови пострадали от кибератаки на следующий день после ложных сообщений о минировании»
    потеряла связь событий). Меряем долю ключевых слов заголовка, оставшихся в строке (≥ 40%); у коротких заголовков (< 5 основ) не проверяем."""
    t = _stems(title)
    if len(t) < 5:
        return True
    return len(t & _stems(line)) / len(t) >= MIN_COVER


# ── действующее лицо (J74, владелец 07.11: «Саудовские бомбардировки в Йемене привели к гибели не менее 22 человек» → строка
# «Не менее 22 человек погибли при бомбардировках в Йемене.» — на вопрос «кто бомбил» ответа нет). Замок «≥ 40% ключевых слов»
# такое пропускает: слов осталось много, а то, что делает новость новостью, — нет. Исполнитель силового действия обязан остаться.
# Исполнитель = слово ПРЯМО перед существительным действия, если это народ/страна/организация («саудовские бомбардировки»),
# или слово с заглавной ПРЯМО после него без предлога («бомбардировки Саудовской Аравией», «удар России», «атака ВСУ»).
# «по Украине», «в Йемене» — не исполнитель (перед ним предлог).
FORCE = {
    "ru": r"бомбардировк\w*|бомбежк\w*|бомбёжк\w*|удар(?:ы|ов|ам|ами|ах)?|ударн\w*|атак\w*|обстрел\w*|налёт\w*|налет\w*|"
          r"вторжени\w*|блокад\w*|санкци\w*|арест\w*|нападени\w*|вмешательств\w*",
    "en": r"airstrikes?|strikes?|bombings?|bombardments?|attacks?|shelling|raids?|invasions?|blockades?|"
          r"sanctions?|arrests?|offensives?|assaults?",
    "es": r"bombardeos?|ataques?|ofensivas?|invasi[oó]n(?:es)?|sanciones|bloqueos?|redadas?|arrestos?|detenciones",
    "pt": r"bombardeios?|ataques?|ofensivas?|invas[aã]o|invas[oõ]es|san[cç][oõ]es|bloqueios?|pris[aã]o|pris[oõ]es",
    "fr": r"bombardements?|frappes?|attaques?|offensives?|invasions?|sanctions|blocus|arrestations?|raids?",
}
# народы, страны и организации — основы: слово перед существительным действия, совпавшее с основой, считается исполнителем
ACTOR_ADJ = {
    "ru": "сауд росси украин израил иран америк китай турец сирий афган пакист индий северокоре южнокоре британ француз немец "
          "польск ливан йемен хуси ирак катар египет эфиоп судан нато европ палестин хамас хезбол талиб".split(),
    "en": "saudi russian ukrainian israeli iranian american chinese turkish syrian afghan pakistani indian british "
          "french german polish lebanese yemeni iraqi qatari egyptian ethiopian sudanese nato european palestinian houthi us".split(),
    "es": "saudí saudita ruso rusa ucraniano ucraniana israelí iraní estadounidense chino china turco turca sirio "
          "siria afgano pakistaní indio india británico francés alemán polaco libanés yemení iraquí".split(),
    "pt": "saudita russo russa ucraniano ucraniana israelense iraniano iraniana americano americana chinês chinesa turco turca "
          "sírio síria afegão paquistanês indiano indiana britânico francês alemão polonês libanês iemenita iraquiano".split(),
    "fr": "saoudien saoudienne russe ukrainien ukrainienne israélien israélienne iranien iranienne américain américaine chinois "
          "chinoise turc turque syrien syrienne afghan pakistanais indien britannique français allemand polonais libanais yéménite".split(),
}
# форма названия или аббревиатура, которой строка вправе заменить слово: «американские» = «США», «саудовские» = «Саудовской Аравии»
ACTOR_ALIAS = {
    "ru": {"америк": {"сша", "америк", "американ"}, "росси": {"рф", "росси", "российс"},
           "европ": {"ес", "европ", "евросоюз"}, "сауд": {"сауд", "аравии", "аравия", "аравией", "аравию"}},
    "en": {"american": {"us", "u.s.", "america", "american"}, "russian": {"russia", "russian"},
           "saudi": {"saudi", "arabia"}, "european": {"eu", "european", "europe"}, "us": {"us", "u.s.", "america", "american"}},
}


# предлог между действием и исполнителем: «ataque DE Israel», «strike BY US» (по-русски исполнитель идёт без предлога)
BY_PREP = {"en": ("by",), "es": ("de", "del"), "pt": ("de", "do", "da", "dos", "das"), "fr": ("de", "du", "des", "d")}


def _tok(w: str) -> str:
    return re.sub(r"[^\w.\-]", "", w.lower().replace("ё", "е"), flags=re.U).strip(".-")


def _actor_forms(word: str, lang: str) -> set:
    """Допустимые «следы» исполнителя в строке: основа слова (4–5 букв) плюс псевдонимы страны/организации."""
    w = _tok(word)
    forms = {w[:5], w[:4]} if len(w) >= 4 else {w}
    for k, v in ACTOR_ALIAS.get(lang, {}).items():
        if w.startswith(k):
            forms |= v
    return forms


def actors_of(title: str, lang: str) -> list:
    """Исполнители силового действия в заголовке: список слов (в исходной форме)."""
    force = FORCE.get(lang)
    if not force or not title:
        return []
    words = re.findall(r"\S+", title)
    out = []
    for i, raw in enumerate(words):
        if not re.fullmatch(r"(?:%s)" % force, _tok(raw), re.I | re.U):
            continue
        if i > 0:                                          # слово перед действием: «саудовские бомбардировки»
            prev = words[i - 1]
            pt = _tok(prev)
            if any(pt == a or (len(a) >= 4 and pt.startswith(a)) for a in ACTOR_ADJ.get(lang, [])):
                out.append(prev.strip(",.;:«»\"'"))
        if i + 1 < len(words):                             # слово после действия: «удар России», «атака ВСУ», «ataque de Israel», «strike by US»
            j = i + 1
            if _tok(words[j]) in BY_PREP.get(lang, ()) and j + 1 < len(words):
                j += 1
            nxt = re.sub(r"^[dDlL][’']", "", words[j]).strip(",.;:«»\"'")      # fr: «d'Israël»
            nt = _tok(nxt)
            if (nxt[:1].isupper() and len(nt) >= 2) or (
                    lang in ("es", "pt", "fr") and any(nt == a or (len(a) >= 5 and nt.startswith(a[:5])) for a in ACTOR_ADJ[lang])):
                out.append(nxt)                            # и «bombardeos saudíes»: в es/pt/fr прилагательное стоит после
    seen, uniq = set(), []
    for a in out:
        if _tok(a) not in seen:
            seen.add(_tok(a)); uniq.append(a)
    return uniq


def keeps_actor(line: str, title: str, lang: str) -> bool:
    """Исполнитель, названный в заголовке, остаётся в строке — в любой форме слова или как принятое сокращение.
    Нет исполнителя в заголовке — проверять нечего (строка не вправе его придумать, это держит замок сути)."""
    need = actors_of(title, lang)
    if not need:
        return True
    have = {_tok(w) for w in re.findall(r"[^\s'’]+", line or "")}      # «d'Israël» → «israël»
    haves = have | {h[:5] for h in have} | {h[:4] for h in have}
    return all(_actor_forms(a, lang) & haves for a in need)


def clean(line, title: str, source_text: str, lang: str, limit: int = LIMIT):
    """Строка/заголовок после сжатия → принятый текст или None. Один набор замков на строку НОС и заголовок карусели:
      · длина 12…limit; без метки «Срочно:» (её рисует виджет);
      · отрицание как у исходного заголовка (не потеряно и не добавлено — J6);
      · каждое число есть в заголовке или тексте (с учётом «слов → цифры»): ничего не придумано."""
    from textcut import _TITLE_NEG
    if not isinstance(line, str):
        return None
    t = _TAG.sub("", re.sub(r"\s+", " ", line).strip()).strip(" \"«»")
    t = normalize_dates(t, lang)                          # «5 ноября» → «05.11»: короче и сверяется с источником по той же форме
    if not 12 <= len(t) <= limit:
        return None
    if len(_TITLE_NEG.findall(t)) != len(_TITLE_NEG.findall(title or "")):
        return None
    if not keeps_title_essence(t, title):
        return None
    if not keeps_actor(t, title, lang):                   # J74: «кто бомбил» не выбрасываем
        return None
    if _script(t) != _script(title):                     # строка на другом алфавите, чем заголовок (русская у английской карточки)
        return None
    src = normalize_dates(numerals_to_digits(f"{title} {source_text or ''}", lang), lang)
    nums = {re.sub(r"\D", "", m) for m in _NUM.findall(src)}
    if any(re.sub(r"\D", "", m) not in nums for m in _NUM.findall(t)):
        return None
    return t


def carousel_candidate(item: dict) -> bool:
    """Карточка, которая может встать в карусель (hero): срочная или «важная» (priority ≥ 2)."""
    return item.get("category") in ("URGENT", "URGENT_LOCAL_ONLY") or (item.get("priority") or 0) >= 2


def final_title_compress(items, lang, limit: int = TITLE_CARD):
    """J72 (владелец 04.11: «заголовок обрезан на одну букву», «сжать по смыслу на сервере»): заголовок карточки карусели,
    не помещающийся в карточку целиком, сжимается теми же правилами, что строка НОС — числа цифрами, общепринятые сокращения,
    придаточное уходит, точка вместо запятой, никаких «…». Остальные карточки не трогаем (60% заголовков длиннее 72 знаков,
    а заголовок издания не наш: переписывать всё подряд — рисковать смыслом). Не сжалось или замок не пропустил — заголовок
    как есть. Полный заголовок издания сохраняем в titleOriginal."""
    n, shown = 0, []
    for x in items:
        t = x.get("title") or ""
        if not carousel_candidate(x) or len(t) <= limit:
            continue
        c = clean(compress(t, lang, limit), t, x.get("summary") or x.get("_full") or "", lang, limit)
        if c and c != t:
            x.setdefault("titleOriginal", t)
            x["title"] = c
            n += 1
            shown.append(f"       · {t[:70]} → {c}")
    if n:
        print(f"  ✂️ Заголовки карусели сжаты по смыслу [{lang}]: {n}")
        print("\n".join(shown[:5]))
    return items
