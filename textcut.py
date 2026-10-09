"""Обрезка текста и распознавание страниц-заслонов.

Вынесено из fetch_news.py отдельным модулем ради одной вещи: сюда можно
написать тесты. Монолит не импортируется без ключа Gemini и служебного
аккаунта Firebase — он лезет в облако прямо при загрузке, поэтому проверить
в нём хоть что-нибудь без сети нельзя. Эти же функции чистые: строка на
входе, строка на выходе. См. test_trim.py.
"""
import re

# Конец предложения. Требуем перед знаком слово из трёх букв и длиннее:
# точка бывает и в сокращении — «1974 г.р.», «ул.», «им.», «U.S.», «No.» — и
# обрезка по такой точке рвёт мысль на середине. Именно так 20.08 из заметки
# о ДТП исчезло «оба погибли». После знака должен идти пробел, кавычка,
# скобка или конец текста, иначе это середина числа или адреса.
# \w с флагом UNICODE ловит буквы всех пяти наших языков разом.
# Между словом и точкой допускаем закрывающую кавычку или скобку: прямая
# речь кончается как «мы уходим». и "we are leaving". — без этого допуска
# конец такого предложения границей не считался и цитата резалась по
# предыдущей точке (нашлось тестом 23.08).
_SENTENCE_END = re.compile(
    r"[^\W\d_]{3,}[»\"'”’)\]]?[.!?…](?=[\s»\"'”’)\]]|$)", re.UNICODE)

# Висячий хвост анонса: издание обрезало фразу на предлоге. Само слово
# убираем; живое последнее слово не трогаем — иначе обрыв на предпоследнем.
_HANGING_TAIL = {
    "и", "а", "но", "или", "что", "как", "для", "при", "над", "под", "из", "за",
    "на", "в", "с", "о", "у", "к", "по", "the", "of", "and", "for", "with",
    "from", "that", "de", "la", "el", "los", "las", "del", "que", "em", "no",
    "na", "do", "da", "dos", "das",
}


# ─── Перечни ───────────────────────────────────────────────────────────────
#
# Заметка Sputnik KG о медалях борцов вышла так: «Алтын алгандар:» — и одна
# фамилия. Девушка с фотографии, выигравшая золото, в текст не попала: рез
# пришёлся ВНУТРЬ перечня. Тот же класс, что «перечень улиц Бишкека оборван
# на улице Д.» (15.08.2026).
#
# Перечень тем и отличается от прочего текста, что он либо целый, либо
# бессмысленный: «золото взяли: Иванов» — это не сокращённая правда, а другая
# и неверная. Поэтому если целиком он не влезает, честнее не начинать его
# вовсе, оборвав текст перед зачином.

# Строка перечня: «— Иванов, 87 кг», «· Иванов», «1. Иванов», «Иванов;»
# и места: «1-орун — …», «2-е место», «1st place», «1º lugar».
# 07.09.2026 Kabar оборвал победителей армрестлинга после «1-орун»:
# прежний шаблон ждал «1.» / «1)», а кыргызские и русские итоги пишут
# «1-орун» / «1-е место». «3-сентябрда» сюда не попадает — там не место.
_RANK = (
    r"\d{1,2}[-–—](?:чи\s+)?(?:орун\w*|(?:[ео]е?\s+)?место)"
    r"|\d{1,2}(?:st|nd|rd|th|º|o|er|re|ère)\s+(?:place|lugar)?"
    r"|\d{1,2}\s+(?:место|орун|place|lugar)\b"
)
_LIST_ITEM = re.compile(
    r"^\s*(?:[-—–•·*]\s+|\d{1,2}[.)]\s+|" + _RANK + r")"
    r"|;\s*\.?\s*$",
    re.I,
)
# Зачин перечня: строка, кончающаяся двоеточием
_LIST_LEAD = re.compile(r":\s*\.?\s*$")


def _list_start_before(text: str, cut: int) -> int | None:
    """Начало перечня, внутрь которого попал рез, — или None.

    Возвращает место, ДО которого текст можно оставить: сам зачин («Золото
    взяли:») тоже уходит, потому что без списка он ничего не обещает.
    """
    head = text[:cut]
    lines, pos = [], 0
    for ln in head.split("\n"):
        lines.append((pos, ln))
        pos += len(ln) + 1
    # Ищем последний зачин, за которым идут строки-пункты
    for i in range(len(lines) - 1, -1, -1):
        start, ln = lines[i]
        if not _LIST_LEAD.search(ln):
            continue
        after = [x for _, x in lines[i + 1:] if x.strip()]
        tail_lines = [x for x in text[cut:].split("\n") if x.strip()]
        if not after:
            # Зачин оказался ПОСЛЕДНЕЙ строкой: «Алтын алгандар:» — и обрыв.
            # Обещание без исполнения хуже, чем его отсутствие: убираем зачин
            if tail_lines and _LIST_ITEM.search(tail_lines[0]):
                return start
            return None
        # Хотя бы одна строка после зачина выглядит пунктом — значит перечень
        if any(_LIST_ITEM.search(x) for x in after):
            # Обрываем ли мы его? Да, если после реза текст продолжается
            # такими же пунктами
            if tail_lines and _LIST_ITEM.search(tail_lines[0]):
                return start
        return None
    return None


# Оформлено как список, но списком новости не является — навигация издания,
# кнопки «поделиться», ссылки на другие материалы. У них нет отношения к
# этой новости, и добирать их сверх лимита незачем.
_TRAILING_LIST_JUNK = re.compile(
    r"читайте так|подробнее|по теме|смотрите также|поделит|источник\s*:|"
    r"read (also|more)|related (articles?|posts?)|see also|share this|"
    r"lee tambi[ée]n|leer m[áa]s|comparte esto|"
    r"lire aussi|[àa] lire|partager cet|"
    r"leia tamb[ée]m|compartilh",
    re.I,
)


def _trailing_list(text: str, start: int, extra_limit: int = 600) -> str:
    """Список сразу после `start`, если это НАСТОЯЩИЙ список — не в счёт лимита.

    03.09.2026: список улиц с отключением света не влезал в основной объём,
    и правило «зачин без списка — убираем» (см. _list_start_before) резало
    ровно ту часть, ради которой жизненно важная новость и нужна. Список —
    не проза: он либо влезает целиком (в разумных пределах), либо не
    начинается вовсе. Добираем его СВЕРХ основного предела, отдельным более
    щедрым потолком (extra_limit), а не долей от лимита прозы.

    Строго: список принимается, только если КАЖДАЯ строка подряд от самого
    начала — пункт (см. _LIST_ITEM), и ни одна не похожа на «читайте также»
    или кнопку «поделиться». Один непохожий на пункт признак — и на этом
    список кончается: лучше короче, чем с мусором на конце.
    """
    tail = text[start:]
    if tail.startswith("\n"):
        tail = tail[1:]
    lines = tail.split("\n")
    picked, used = [], 0
    for ln in lines:
        stripped = ln.strip()
        if not stripped or _TRAILING_LIST_JUNK.search(ln):
            break
        # Последний пункт перечня по-русски и по-кыргызски принято закрывать
        # точкой, а не точкой с запятой — «Иванов; Петров; Сидоров.». Строка
        # без своего маркера, но идущая сразу за пунктом на «;» и кончающаяся
        # точкой, — это ОН, а не новый абзац. Найдено на медалях 03.09.2026:
        # без этой строки _trailing_list ровно повторял бы старую беду —
        # отрезал бы последний пункт перечня, как улицу Д. и фото призёрши.
        closes_enum = (picked and picked[-1].rstrip().endswith(";")
                       and stripped.endswith("."))
        if not (_LIST_ITEM.search(ln) or closes_enum):
            break
        if used + len(ln) > extra_limit:
            break
        picked.append(ln)
        used += len(ln) + 1
    return "\n".join(picked)


# ─── Цитата не должна оставаться открытой ───────────────────────────────────
#
# 08.10.2026: BBC о ударе по Прилукам — текст кончался на «Удалось сбить только
# часть. Рез по границе предложения был «законным», но пришёлся ВНУТРЬ слов
# Зеленского: кавычка открыта, закрывающей нет, мысль оборвана. Тот же класс,
# что перечень, оборванный посередине (_whole_or_none): граница предложения
# годна, только если вне цитаты и вне списка. Правило одно и стоит в двух
# местах: при обрезке (trim_to_boundary) и последним рубежом после редактора
# (final_end_guard), потому что редактор тоже режет.
def ends_inside_quote(text: str) -> bool:
    """True, если в конце текста остаётся открытая цитата.

    Парные знаки читаем стеком: «…» и “…” (англ./исп.), „…“ (нем./рус.
    вложенные) — “ закрывает „ и открывает сам, если открытого „ нет. Прямая
    кавычка " то открывает, то закрывает: открывает, если перед ней пробел,
    начало или открывающий знак либо за ней сразу буква («chilling."The»).
    Апостроф и одинарные ‘’ не берём: don't, l'état, 'L'Equipe' — не цитата."""
    stack = []
    straight = 0
    n = len(text)
    for i, ch in enumerate(text):
        if ch in "«":
            stack.append("«")
        elif ch == "»":
            if "«" in stack:
                stack.reverse(); stack.remove("«"); stack.reverse()
        elif ch == "„":
            stack.append("„")
        elif ch == "“":
            if stack and stack[-1] == "„":
                stack.pop()
            else:
                stack.append("“")
        elif ch == "”":
            if "“" in stack:
                stack.reverse(); stack.remove("“"); stack.reverse()
        elif ch == '"':
            prev = text[i - 1] if i else " "
            nxt = text[i + 1] if i + 1 < n else " "
            opener = prev.isspace() or prev in "([—–-:" or (nxt.isalnum() and not prev.isalnum())
            if opener:
                straight += 1
            elif straight:
                straight -= 1
    return bool(stack) or straight > 0


# Подзаголовок на конце: BBC о Прилуках после правки цитат кончался на «Удар по
# пятиэтажке в Прилуках» — это заголовок следующего раздела статьи, а текст под
# ним в карточку не вошёл. Строка без знака в конце, короткая, после неё
# (в оригинале) шёл абзац — не мысль, а вывеска. Тот же класс «рез по границе
# абзаца годен, только если граница настоящая».
_ENDS_SENTENCE = re.compile(r"[.!?…:»”\"')\]]$")


def drop_trailing_heading(text: str) -> str:
    """Снимает с конца многострочного текста подзаголовки (строки ≤ 90 знаков
    без знака конца). Однострочный текст и последний абзац не трогаем."""
    t = (text or "").rstrip()
    while "\n" in t:
        head, last = t.rsplit("\n", 1)
        last = last.strip()
        if last and len(last) <= 90 and not _ENDS_SENTENCE.search(last) and head.strip():
            t = head.rstrip()
        else:
            break
    return t


def _with_closers(text: str, e: int) -> int:
    """Конец предложения «…продолжим.» + закрывающая кавычка, идущая за точкой."""
    while e < len(text) and text[e] in "»”\"')":
        e += 1
    return e


def _quote_safe_cut(text: str, cut: int, floor_chars: int) -> int:
    """Сдвигает рез так, чтобы он не попал внутрь цитаты.

    Сначала пробуем досказать цитату (до 500 знаков вперёд, до конца
    предложения, где кавычки закрыты), затем отступаем до последней границы
    предложения вне цитаты. Не вышло ни то ни другое — возвращаем cut как есть:
    пустая карточка хуже обрубка."""
    if not ends_inside_quote(text[:cut]):
        return cut
    for m in _SENTENCE_END.finditer(text, cut, min(len(text), cut + 500)):
        e = _with_closers(text, m.end())
        if not ends_inside_quote(text[:e]):
            return e
    ends = [_with_closers(text, m.end()) for m in _SENTENCE_END.finditer(text, 0, cut)]
    for e in reversed(ends):
        if e < floor_chars:
            break
        if not ends_inside_quote(text[:e]):
            return e
    return cut


def ensure_terminated(text: str) -> str:
    """Текст короче лимита, но обрублен уже ДО нас — страховка от этого.

    03.09.2026: заметка Expansión MX обрывалась на «...es razonable» без
    точки и без нашего многоточия — 832 знака при лимите PAGE_BODY_LIMIT в
    1300. trim_to_boundary тут вообще не срабатывал: он режет только то, что
    ДЛИННЕЕ лимита, а этот текст короче. Обрыв случился раньше, внутри
    trafilatura — там же нашёлся и след: «Extranjeras.Para» без пробела
    после точки, читальня наткнулась на встроенный элемент страницы (ссылку,
    имя жирным) и не досчитала остаток — вероятно, упёрлась в подписной
    блок и молча остановилась, ничего не сообщив.

    Раз trim_to_boundary больше не единственная дверь для многоточия, сюда
    заходит КАЖДЫЙ текст, включая короткие: см. вызов из самого
    trim_to_boundary при len(text) <= limit.
    """
    text = (text or "").strip()
    if not text or re.search(r"[.!?…»\"'”’)\]]$", text):
        return text
    ends = [m.end() for m in _SENTENCE_END.finditer(text)]
    if ends and ends[-1] >= len(text) * 0.5:
        return text[:ends[-1]].strip()
    # Раньше откусывали последнее слово и ставили многоточие. Анонс РБК
    # и так обрывается изданием на полуфразе; второе откусывание давало
    # обрыв на ПРЕДПОСЛЕДНЕМ слове. Висячий предлог убираем, живое слово
    # оставляем и честно ставим многоточие.
    last = text.split()[-1].lower().strip(".,;:—–-") if text.split() else ""
    hanging = len(last) <= 2 or last in _HANGING_TAIL
    if hanging:
        cut = text.rsplit(" ", 1)[0].strip()
        return (cut + "…") if cut else text
    return text + "…"


def _finish_paragraph(text: str, cut: int, max_extra_sentences: int = 3) -> int:
    """Досказывает абзац ЕЩЁ ДО ТРЁХ предложений сверх границы `cut`.

    Резать посреди абзаца, когда за одним-двумя предложениями сразу следует
    его конец, — обрывать мысль ради круглого числа знаков. Мера — не запас
    символов, а количество предложений: абзац, как правило, укладывается в
    одно-два, редко в три, и это и есть естественный предел добора.

    Если абзац кончается раньше max_extra_sentences — останавливаемся на
    его конце. Если предложений в остатке нет вовсе (`cut` уже у конца
    абзаца) — возвращаем `cut` как есть.
    """
    para_end = text.find("\n", cut)
    para_end = len(text) if para_end < 0 else para_end
    rest = text[cut:para_end]
    ends = [cut + m.end() for m in _SENTENCE_END.finditer(rest)]
    if not ends:
        return cut
    return ends[min(max_extra_sentences, len(ends)) - 1]


def trim_to_boundary(text: str, limit: int, floor: float = 0.35,
                     para_floor: float = 0.6, max_extra_sentences: int = 0) -> str:
    """Обрезает текст до limit знаков по ближайшей осмысленной границе.

    Границы по убыванию предпочтения:
      1. КОНЕЦ АБЗАЦА — лучшая. Текст, оборванный посреди абзаца, читается
         как обрубок, даже когда последняя фраза целая: мысль абзаца не
         досказана. Берём абзац, только если он занимает хотя бы para_floor
         от лимита, иначе ради ровного края потеряли бы половину новости.
      2. Конец предложения — если подходящего абзаца нет.
      3. Конец слова с многоточием — если нет и предложения.

    Абзацы различимы потому, что разбор страницы сохраняет переводы строк.
    В тексте из одного абзаца (а таких в лентах большинство) правило само
    сводится к границе предложения.

    До 23.08.2026 такая обрезка была написана в трёх местах тремя разными
    способами — в _page_body, в extract_full_summary и в сборке обзора прессы.
    Расходились они не в мелочах: одна брала последнюю границу, другая —
    первую попавшуюся, и обе при неудаче молча резали по счётчику знаков,
    посреди слова. Теперь правило одно.

    floor — доля лимита, ниже которой граница не годится. Без него текст из
    одного длинного предложения с точкой на сотом знаке схлопывался бы до
    этой сотни: формально по границе, а по существу потеря девяноста
    процентов новости.

    Если подходящей границы нет вовсе, обрезаем по слову и ставим многоточие.
    Это честнее обрыва на полуслове: читатель видит, что текст продолжается, а
    не что издание не дописало. Многоточие заодно говорит и нашему же
    _looks_mangled, что текст оборван нами намеренно, — и платный
    _ai_rescue_body на него не тратится.
    """
    text = (text or "").strip()
    if len(text) <= limit:
        return ensure_terminated(text)
    # Ищем в окне на один знак шире лимита: предложение, кончающееся ровно на
    # границе, — законная граница, терять его незачем
    window = text[:limit + 1]

    # 1. Конец абзаца
    breaks = [m.start() for m in re.finditer(r"\n", window)]
    if breaks and breaks[-1] >= limit * para_floor:
        return drop_trailing_heading(_whole_or_none(text, breaks[-1], limit, floor))

    # 2. Конец предложения
    ends = [m.end() for m in _SENTENCE_END.finditer(window)]
    if ends and ends[-1] >= limit * floor:
        cut = ends[-1]
        # ДОБОР ДО КОНЦА АБЗАЦА ПРЕДЛОЖЕНИЯМИ, А НЕ ЗНАКАМИ — только если
        # звали с max_extra_sentences (тело статьи в читалке; короткие
        # тексты вроде превью и уведомлений режутся строго по границе, как
        # раньше). 03.09.2026: обсуждали запас «плюс сто знаков», отклонили —
        # читателя интересует законченная мысль, а не число символов до неё.
        if max_extra_sentences:
            cut = _finish_paragraph(text, cut, max_extra_sentences)
        cut = _quote_safe_cut(text, cut, int(limit * floor))
        return drop_trailing_heading(_whole_or_none(text, cut, limit, floor))

    # 3. Конец слова. Неполное слово на границе лимита отбрасываем;
    # висячий предлог тоже. Живое последнее слово оставляем.
    cut = window[:limit].rstrip()
    if limit < len(text) and not text[limit].isspace() and not text[limit - 1].isspace():
        cut = cut.rsplit(" ", 1)[0].strip()
    last = cut.split()[-1].lower().strip(".,;:—–-") if cut.split() else ""
    if last in _HANGING_TAIL or (last and len(last) <= 2):
        cut = cut.rsplit(" ", 1)[0].strip()
    return (cut + "…") if cut else window[:limit].strip()


# Страница-заслон вместо статьи: блокировка робота, требование подписки,
# капча. Проверка нужна именно из-за библиотечного разбора: trafilatura
# честно достаёт основной текст страницы, но не знает, что перед ней не
# статья. На проверке 23.08.2026 из тридцати страниц она «спасла» три, где
# наш разбор давал пустоту, — и две из трёх оказались заслонами Le Parisien
# («Access Denied») и Le Monde («Votre trafic a été identifié comme
# automatisé»). Без этой проверки читатель французского пула получил бы
# сообщение об ошибке в качестве новости.
_BLOCKED_MARKERS = re.compile(
    r"access denied|permission to access|403 forbidden|"
    r"identifié comme automatisé|automated (?:traffic|bot)|"
    r"enable javascript|activez javascript|"
    r"are you a robot|vérification de sécurité|security check|"
    r"checking your browser|cloudflare|captcha|"
    r"subscribe to (?:continue|read)|abonnez-vous pour|"
    r"suscríbete para|assine para continuar|"
    r"этот контент доступен только подписчикам|errors\.edgesuite\.net",
    re.I)


def _looks_blocked(text: str) -> bool:
    """True, если вместо статьи нам отдали заслон.

    Смотрим только начало: слово «captcha» в подвале настоящей статьи о
    кибербезопасности не должно снимать её с эфира.
    """
    head = (text or "")[:600]
    if not head.strip():
        return False
    if not _BLOCKED_MARKERS.search(head):
        return False
    # Настоящая статья про блокировки и подписки бывает длинной; заслон —
    # почти всегда короткая страница. Длинный текст с одним таким словом
    # оставляем в покое
    return len(text) < 1200


# Слова-связки не считаем при сравнении заголовка с первой фразой: они есть
# везде и создают ложное сходство
_STOPWORDS = {
    "в", "на", "и", "с", "по", "из", "за", "к", "у", "о", "от", "до", "для",
    "the", "a", "an", "of", "in", "on", "to", "and", "for", "at", "by",
    "de", "la", "le", "les", "des", "du", "el", "los", "las", "da", "do",
}


def _words(t: str) -> list:
    return [w for w in re.findall(r"[^\W\d_]+", (t or "").lower(), re.UNICODE)
            if w not in _STOPWORDS and len(w) > 2]


def strip_title_echo(title: str, body: str) -> str:
    """Убирает заголовок, продублированный первой фразой текста.

    Прежнее правило сравнивало ПЕРВЫЕ СОРОК знаков заголовка, а срезало ВСЮ
    его длину. Как только текст после сороковой буквы расходился с заголовком
    — а он расходится почти всегда, потому что подробностей в тексте больше —
    нож уходил в живое.

    24.08.2026: заголовок «…на свалке в столице Гвинеи» (81 знак), текст
    «…на свалке в Конакри, столице Гвинеи, сообщило правительство». Первые
    сорок знаков совпали, срезали восемьдесят один — «Конакр» исчезло, и
    читатель увидел «и, столице Гвинеи, сообщило…».

    Теперь режем ПРЕДЛОЖЕНИЕ, а не количество знаков. Ровно два случая:
      · текст начинается с заголовка буква в букву — срезаем его;
      · первая фраза текста пересказывает заголовок (три четверти значимых
        слов общие) — срезаем эту фразу целиком.
    Во всех прочих случаях не трогаем: лучше оставить повтор, чем обрубок.
    """
    title = (title or "").strip()
    body = (body or "").strip()
    if not title or not body:
        return body

    # 1. Точное совпадение — единственный случай, когда резать по длине безопасно
    if body.lower().startswith(title.lower()):
        rest = body[len(title):].lstrip(" .,—–-:\n")
        # Кроме заголовка в тексте ничего нет — оставляем как есть: пустая
        # карточка хуже повтора, а эталон качества снимет её сам, если пусто
        return rest if len(rest) >= 20 else body

    # 2. Первая фраза пересказывает заголовок
    m = _SENTENCE_END.search(body[:400])
    if not m:
        return body
    first, rest = body[:m.end()], body[m.end():].lstrip()
    if not rest:
        return body          # кроме этой фразы ничего нет — оставляем

    tw, fw = set(_words(title)), set(_words(first))
    if not tw or not fw:
        return body

    # Срезаем, только если фраза почти НИЧЕГО не добавляет к заголовку.
    #
    # Первая фраза новости — это лид, и в нём обычно есть то, чего в заголовке
    # нет: город, источник сообщения, время. У гвинейского оползня заголовок
    # говорил «в столице Гвинеи», а лид — «в Конакри, сообщило в воскресенье
    # правительство». Вырезав его ради устранения повтора, мы потеряли бы и
    # город, и ссылку на правительство.
    #
    # Поэтому: пересказ заголовка убираем, лид с подробностями оставляем.
    # Лёгкий повтор читатель простит, потерю подробностей — нет.
    covers_title = len(tw & fw) >= max(3, int(len(tw) * 0.75))
    adds_little = len(fw - tw) <= 2
    # Вариант «Б» (владелец, 01.10.2026). Фраза добавляет подробности (даты,
    # город), но ОТКРЫВАЕТСЯ заголовком слово в слово — Kaktus: «Сборная
    # Кыргызстана U-16 заняла второе место на [международном] турнире…».
    # Читатель видит заголовок и сразу его же. Режем, только если совпали
    # первые шесть слов целиком и фраза покрывает заголовок: у гвинейского
    # оползня заголовок и лид расходились на пятом слове («в столице» /
    # «в Конакри»), и такой лид остаётся. Подробности из фразы уходят вместе
    # с ней — это цена варианта, выбранная сознательно
    def _raw(s):
        return re.findall(r"\w+", (s or "").lower(), re.UNICODE)
    rt, rf = _raw(title), _raw(first)
    opens_with_title = len(rt) >= 6 and rt[:6] == rf[:6]
    if covers_title and (adds_little or (opens_with_title and len(rest) >= 80)):
        return rest
    return body


# ─── Служебный зачин до новости ─────────────────────────────────────────────
#
# 07.09.2026: статья Straits Times в читалке начиналась словами
# «Подпишитесь сейчас: получайте информационные бюллетени ST на свой
# почтовый ящик». Это перевод «Sign up now: Get ST's newsletters…».
# Английскую фразу мы уже ловили точечно — после перевода правило молчало.
#
# Пользователь: не плодить фразы, а научиться отличать служебный мусор
# от текста новости. Примета не в словах одного сайта, а в устройстве:
# такое всегда стоит В НАЧАЛЕ и говорит с читателем про рассылку, почту
# или дату публикации — а не про событие. Событие начинается следом
# («АФИНЫ – Военный самолет…»).
#
# Два признака сразу: обращение подписаться/получать И канал доставки.
# Одного мало: «президент подписал указ» и «компания запустила рассылку»
# — живые новости.

_SERVICE_ASK = re.compile(
    r"(?i)\b(?:sign[\s-]?up|subscribe|get (?:st'?s|our|the)\b|"
    r"подпиши(?:тесь|сь)|подписыва(?:йтесь|ться)|получайте|"
    r"suscr[ií]b\w*|inscreva(?:-se)?|assine|"
    r"abonnez(?:-vous)?|inscrivez(?:-vous)?|recevez)\b")

_SERVICE_CHANNEL = re.compile(
    r"(?i)\b(?:newsletters?|inbox|e-?mails?|"
    r"бюллетен\w*|рассылк\w*|почтовый ящик|электронн\w*\s+почт\w*|уведомлен\w*|"
    r"boletines?|bolet[ií]n(?:es)?|correo(?:s)?|bandeja de entrada|"
    r"boletins?|caixa de entrada|"
    r"lettres?\s+d['’]information|bo[iî]te de r[eé]ception|courriels?)\b")

_SERVICE_META = re.compile(
    r"(?i)^\s*(?:published|updated|опубликовано|обновлено|"
    r"publicado|actualizado|atualizado|"
    r"publi[eé]|mis à jour)\b")


def is_service_lead(text: str) -> bool:
    """Служебный кусок, а не начало новости.

    Смешанный абзац («подпишитесь… АФИНЫ – …») не считаем служебным целиком:
    в нём уже есть событие, зачин снимет нарезка по предложениям.
    """
    t = (text or "").strip()
    if not t or len(t) > 280:
        return False
    if _SERVICE_META.match(t):
        return True
    if len(re.findall(r"[.!?…](?:\s+|$)", t)) > 1:
        return False
    return bool(_SERVICE_ASK.search(t) and _SERVICE_CHANNEL.search(t))


def strip_leading_service(text: str) -> str:
    """Снимает служебные абзацы и фразы только с начала текста.

    Середину не трогаем: новость про запуск рассылки должна остаться.
    Если после снятия ничего не осталось — возвращаем как было: пустая
    карточка хуже приглашения подписаться.

    Сначала режем по предложениям: иначе абзац «подпишитесь… АФИНЫ – …»
    целиком выглядит служебным — в нём есть и рассылка, и новость.
    """
    src = (text or "").strip()
    if not src:
        return src
    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", src) if p.strip()]
    kept, skipping = [], True
    for p in paras:
        if not skipping:
            kept.append(p)
            continue
        peeled = _drop_leading_service_sentences(p)
        if peeled:
            kept.append(peeled)
            skipping = False
    return "\n\n".join(kept) if kept else src


def _drop_leading_service_sentences(para: str) -> str:
    parts, last = [], 0
    for m in re.finditer(r"[.!?…](?:\s+|$)", para):
        parts.append(para[last:m.end()].strip())
        last = m.end()
    tail = para[last:].strip()
    if tail:
        parts.append(tail)
    if not parts:
        return para
    if len(parts) == 1:
        return "" if is_service_lead(parts[0]) else para
    i = 0
    while i < len(parts) and is_service_lead(parts[i]):
        i += 1
    return " ".join(parts[i:]).strip()


# ─── Имя издания на языке читателя ──────────────────────────────────────────

_CYR = re.compile(r"[А-Яа-яЁё]")
_LAT = re.compile(r"[A-Za-zÀ-ÿ0-9]")


def display_source(name: str, pool_lang: str) -> str:
    """Имя издания так, как его должен видеть читатель ЭТОГО пула.

    Найдено 28.08.2026: во ВСЕХ четырёх нерусских пулах стояло «BBC Русская
    служба» — по четыре новости в каждом. Заголовок и текст переводились
    исправно, а имя издания ехало из настроек как есть, кириллицей. Испанец,
    португалец, француз и американец видели русские буквы под своей новостью.

    Правило общее, а не заплатка под Би-би-си: в нерусском пуле имя не должно
    содержать кириллицы. Отбрасываем кириллические слова и оставляем
    латинскую часть — «BBC Русская служба» становится «BBC», и это честно: для
    испанца это и есть Би-би-си.

    ЕСЛИ ЛАТИНСКОЙ ЧАСТИ НЕТ ВОВСЕ — возвращаем имя как было. Издание вроде
    «Кактус» не переименовать выбрасыванием букв, а безымянная новость хуже
    новости с непонятным именем: читатель хотя бы видит, что источник указан.
    Такие издания в чужие пулы и не попадают, но правило обязано это выдержать.
    """
    if not name or pool_lang == "ru" or not _CYR.search(name):
        return name
    kept = [w for w in name.split() if not _CYR.search(w)]
    out = " ".join(kept).strip(" -–—·,")
    return out if out and _LAT.search(out) else name

# ─── Сколько новости показывать ─────────────────────────────────────────────

def lead(text: str, target: int = 700, max_paras: int = 5,
         max_sentences: int = 8) -> str:
    """Начало новости целыми абзацами. Знак — ориентир, а не предел.

    Решение пользователя 28.08.2026, дословно: «я против замеров количеством
    знаков» и «нужна гибкая система, плюс-минус больше-меньше ничего
    страшного».

    И он прав дважды. Новость коротка не потому, что в ней шестьсот символов,
    а потому что в ней сказано главное и поставлена точка; знак — мера бумаги,
    а не смысла. Но и совсем без ориентира нельзя: у одних изданий абзац в две
    строки, у других в двадцать, и «первые три абзаца» дало бы то заметку, то
    простыню.

    Поэтому набираем ЦЕЛЫЕ АБЗАЦЫ, пока не наберётся примерно target. Целые —
    значит перебор неизбежен, и это не беда: лучше на треть длиннее, чем
    абзац, разрезанный пополам. Недобор тоже не беда: если новость уложилась в
    один абзац, значит, она такая и есть.

    ЕСЛИ АБЗАЦ ОДИН — тем же способом набираем предложения. Так выходит у
    большинства: издания отдают описание одним куском, абзацев в нём нет
    вовсе, и правило про абзацы там не за что зацепить.

    Верхние границы (max_paras, max_sentences) — не про длину, а про ЖАНР, и
    поставлены заведомо выше ориентира. Решать должен ориентир; границы ловят
    редкий случай, когда абзацы совсем короткие и набор шёл бы без конца.
    Больше пяти абзацев — это уже не «коротко о важном», сколько бы знаков в
    них ни было.
    """
    text = (text or "").strip()
    if not text:
        return text

    def take(units, joiner, cap):
        out, total, i = [], 0, 0
        while i < len(units):
            # Первую единицу берём всегда: новость из одного длинного абзаца
            # иначе исчезла бы целиком
            if out and (total >= target or len(out) >= cap):
                break
            # Подчищаем КАЖДУЮ единицу, а не только итог: издания оставляют
            # хвостовой пробел в конце абзаца, и он всплывал бы перед разрывом
            out.append(units[i].strip())
            total += len(units[i])
            i += 1
        # Перечень либо целый, либо врёт. 07.09 Kabar: после «1-орун»
        # ориентир уже был набран, и 2-е с 3-м местами остались за кадром.
        extra = 0
        while i < len(units) and extra < 600:
            nxt = units[i].strip()
            if not nxt or _TRAILING_LIST_JUNK.search(nxt):
                break
            if not _LIST_ITEM.search(nxt):
                break
            out.append(nxt)
            extra += len(nxt) + 1
            i += 1
        return joiner.join(p for p in out if p).strip()

    paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    if len(paras) > 1:
        return take(paras, "\n\n", max_paras)
    sents = re.split(r"(?<=[.!?…])\s+", text)
    if len(sents) <= 1:
        return text
    return take(sents, " ", max_sentences)


def _whole_or_none(text: str, cut: int, limit: int, floor: float) -> str:
    """Отдаёт текст до `cut`, но не обрывая перечень посередине.

    Если рез попал внутрь списка, сперва пробуем ДОБРАТЬ его целиком сверх
    лимита (см. _trailing_list) — список улиц с отключением света и есть та
    польза, ради которой жизненно важная новость существует, обещание без
    исполнения не годится. Не вышло (список — мусор, или его вовсе нет) —
    тогда убираем зачин, как раньше. Отступать бесконечно нельзя: если после
    отката остаётся меньше floor от лимита, от новости не осталось бы ничего,
    и тогда лучше обычный рез — половина перечня хуже целого, но пустота
    хуже половины.
    """
    start = _list_start_before(text, cut)
    if start is not None and start >= limit * floor:
        rest = text[start:]
        nl = rest.find("\n")
        lead_end = start + (len(rest) if nl < 0 else nl + 1)
        extra = _trailing_list(text, lead_end)
        if extra:
            return (text[:lead_end].rstrip() + "\n" + extra).strip()
        return text[:start].strip()
    base = text[:cut].strip()
    extra = _trailing_list(text, cut)
    return (base + "\n" + extra).strip() if extra else base


# Начало, которое предложением быть не может: строчная буква, многоточие,
# знак препинания. Кавычка, скобка, тире диалога и цифра — законные начала
# «iPhone», «eBay» начинаются со строчной законно: за ней сразу прописная
_BAD_START = re.compile(r"^(?:[…,.;:)\]]|[a-zа-яёөүң](?![A-ZА-ЯЁ]))", re.U)
_NEXT_SENTENCE = re.compile(r"[.!?…][»\"”)]?\s+(?=[«\"„(—–-]?\s?[A-ZА-ЯЁӨҮҢ0-9])", re.U)


def sentence_start(body: str) -> str:
    """Текст, начатый с полуфразы, — с первой целой фразы (29.09.2026).

    Пользователь: «начало должно быть предложением». Обрывок снимаем, только
    если после него остаётся что читать: пустая карточка хуже обрубка.
    """
    t = (body or "").lstrip()
    if not t or not _BAD_START.match(t):
        return body
    m = _NEXT_SENTENCE.search(t[:500])
    if not m:
        return body
    rest = t[m.end():].lstrip()
    return rest if len(rest) >= 80 else body


def final_start_guard(items, lang):
    """ПОСЛЕДНИЙ взгляд на начало текста — после редактора, перед записью.

    Контроль качества и последний рубеж работают ДО редактора, а редактор
    выбирает абзацы и режет обрывки уже после них: итог не смотрел никто
    (Kaktus про леса, 30.09.2026 — «гектаров. По данным…»). Чиним тем же
    правилом, что контроль качества, и громко пишем в журнал: если сюда
    что-то дошло, значит, где-то выше правило резало криво."""
    bad = 0
    for x in items:
        s = x.get("summary") or ""
        fixed = sentence_start(s)
        if fixed != s:
            x["summary"] = fixed
            bad += 1
            print(f"  🧨 Полуфраза в эфире [{lang}]: [{x.get('source','?')}] "
                  f"{(x.get('title') or '')[:60]}")
    if bad:
        print(f"  🧨 Начало текста после редактора починено у {bad} [{lang}]")
    return items


def close_open_quote(text: str) -> str:
    """Дописывает закрывающую кавычку, если откатиться до фразы вне цитаты некуда
    (09.10.2026: Ars Technica и El Universal MX — текст в 600 знаков кончается «…» внутри
    одной длинной цитаты). Не вышло закрыть за два знака — текст без изменений."""
    t = (text or "").rstrip()
    if not ends_inside_quote(t):
        return t
    for c1 in ("”", "»", "“", '"'):
        if not ends_inside_quote(t + c1):
            return t + c1
    for c1 in ("”", "»", "“", '"'):
        for c2 in ("”", "»", "“", '"'):
            if not ends_inside_quote(t + c1 + c2):
                return t + c1 + c2
    return t


def final_end_guard(items, lang):
    """ПОСЛЕДНИЙ взгляд на КОНЕЦ текста — парный к final_start_guard.

    Если текст кончается внутри открытой цитаты, отступаем до последнего
    предложения вне цитаты. Остаётся меньше 150 знаков — не трогаем (пустая
    карточка хуже обрубка), но пишем в журнал."""
    fixed_n = 0
    for x in items:
        s = (x.get("summary") or "").rstrip()
        bare = drop_trailing_heading(s)
        if bare != s and len(bare) >= 150:
            x["summary"] = s = bare
            fixed_n += 1
            print(f"  🧨 Подзаголовок на конце текста снят [{lang}]: "
                  f"[{x.get('source','?')}] {(x.get('title') or '')[:60]}")
        if not s or not ends_inside_quote(s):
            continue
        ends = [_with_closers(s, m.end()) for m in _SENTENCE_END.finditer(s)]
        new = next((s[:e] for e in reversed(ends)
                    if e >= 150 and not ends_inside_quote(s[:e])), None)
        tag = f"[{x.get('source','?')}] {(x.get('title') or '')[:60]}"
        if new:
            x["summary"] = new.strip()
            fixed_n += 1
            print(f"  🧨 Цитата оборвана в эфире [{lang}], текст укорочен: {tag}")
        else:
            closed = close_open_quote(s)
            if closed != s:
                x["summary"] = closed
                fixed_n += 1
                print(f"  🧨 Цитата оборвана, откатиться некуда — закрыта кавычка [{lang}]: {tag}")
            else:
                print(f"  🧨 Цитата оборвана, укоротить некуда [{lang}]: {tag}")
    if fixed_n:
        print(f"  🧨 Конец текста после редактора починен у {fixed_n} [{lang}]")
    return items


# ─── Длинный заголовок → первое предложение ─────────────────────────────────
#
# 08.10.2026, владелец о BBC: «Россия нанесла массированный ракетный удар по
# Украине. В городе Прилуки обрушилась пятиэтажка, погибли 22 человека» — в
# карточку не влезает, берём первое предложение. Только если заголовок
# длиннее TITLE_CUT и в нём есть второе предложение и первое предложение само годится: ≥ 30 знаков и не
# теряет отрицание полного заголовка (урок Sputnik KG: «не» — смысл). Полный
# заголовок издания сохраняем в titleOriginal.
TITLE_CUT = 90   # длиннее — и если есть второе предложение — берём первое
_TITLE_NEG = re.compile(
    r"\b(не|нет|ни|без|нельзя|not|no|never|sin|nunca|pas|jamais|não|nunca|non|ne|nicht|kein)\b", re.I)
_TITLE_SENT = re.compile(r"(?<=[^\W\d_]{3}[.!?])\s+(?=[«\"“„(]?[A-ZА-ЯЁ0-9])", re.U)


_TITLE_ABBR = {"gov", "sen", "rep", "dr", "mr", "mrs", "ms", "st", "inc", "corp", "co",
               "jr", "sr", "lt", "col", "gen", "sgt", "cmdr", "prof", "vs", "no", "u.s",
               "sra", "sr", "dra", "ud", "uds", "mme", "mlle", "m"}
_TITLE_Q = re.compile(
    r"^(?:почему|как|что|когда|где|зачем|кто|чем|сколько|why|how|what|when|where|who|"
    r"por qu[eé]|c[oó]mo|qu[eé]|cu[aá]ndo|pourquoi|comment|que|quand|por que|como|quando)\b", re.I)


# Хвост-контекст: «…погибли 30 человек НА ФОНЕ ухудшения электроснабжения в Киеве».
# Главное сказано до него; хвост — фон, а не событие (владелец, 09.10.2026).
_CONTEXT_TAIL = re.compile(
    r"\s+(?:на\s+фоне|на\s+этом\s+фоне|в\s+то\s+время,?\s+как|тогда\s+как|"
    r"amid|while|en\s+medio\s+de|mientras\s+que|alors\s+que|dans\s+un\s+contexte\s+de|"
    r"em\s+meio\s+a|enquanto)\s+", re.I)


def trim_context_tail(title: str):
    """Заголовок без хвоста-контекста или None, если резать нельзя.

    Не режем: голова < 40 знаков, хвост < 12, в голове меньше отрицаний, чем во
    всём заголовке (урок Sputnik KG), цитата открыта."""
    t = (title or "").strip()
    if len(t) <= TITLE_CUT:
        return None
    m = _CONTEXT_TAIL.search(t)
    if not m:
        return None
    head, tail = t[:m.start()].rstrip(" ,;:—–-"), t[m.end():]
    if len(head) < 40 or len(tail) < 12 or ends_inside_quote(head):
        return None
    if len(_TITLE_NEG.findall(head)) < len(_TITLE_NEG.findall(t)):
        return None
    return head


def first_sentence_title(title: str):
    """Заголовок короче: первое предложение или без хвоста-контекста; None, если резать нельзя."""
    t = (title or "").strip()
    if len(t) <= TITLE_CUT:
        return None
    cut = _first_sentence(t)
    return trim_context_tail(cut or t) or cut


def _first_sentence(title: str):
    """Первое предложение длинного заголовка или None, если резать нельзя."""
    t = (title or "").strip()
    if len(t) <= TITLE_CUT:
        return None
    m = _TITLE_SENT.search(t)
    if not m:
        return None
    first, rest = t[:m.start()].strip(), t[m.end():].strip()
    if len(first) < 30 or len(rest) < 15 or ends_inside_quote(first):
        return None
    # «Gov.», «Dr.», «St.» — не конец предложения
    if (first.rsplit(" ", 1)[-1].rstrip(".").lower() in _TITLE_ABBR):
        return None
    # «Тема. Почему/Как/Что…?» — первое предложение лишь зацепка, суть во
    # втором («Шесть тысяч эвакуаций за месяц.» без «как справляются» — обрывок)
    if rest.rstrip().endswith("?") or _TITLE_Q.match(rest):
        return None
    if len(_TITLE_NEG.findall(first)) < len(_TITLE_NEG.findall(t)):
        return None
    return first


def final_title_guard(items, lang):
    """После редактора: заголовок, не влезающий в карточку, → первое предложение."""
    n = 0
    for x in items:
        short = first_sentence_title(x.get("title") or "")
        if short:
            x["titleOriginal"] = x["title"]
            x["title"] = short
            n += 1
    if n:
        print(f"  ✂️ Длинные заголовки сведены к первому предложению [{lang}]: {n}")
    return items


# ─── Заглушка вместо текста ─────────────────────────────────────────────────
#
# 09.10.2026: онлайн-трансляция BBC (/russian/live/…) попала в эфир с текстом
# «Последние новости, комментарии и видео о войне России против Украины…» —
# это подпись страницы, а не новость; рядом лежали ещё две карточки о том же
# событии. Класс: аннотация страницы-ленты вместо статьи.
_STUB_SUMMARY = re.compile(
    r"последние новости, комментарии и видео|latest news, comment(?:ary)? and video|"
    r"últimas noticias, comentarios y vídeos?|dernières informations, analyses et vidéos|"
    r"últimas notícias, comentários e vídeos", re.I)


def is_stub_summary(item) -> bool:
    return bool(_STUB_SUMMARY.search((item.get("summary") or "")[:200]))


def drop_stub_summaries(items, lang):
    kept = [x for x in items if not is_stub_summary(x)]
    if len(kept) != len(items):
        print(f"  🧻 Заглушка вместо текста снята [{lang}]: {len(items) - len(kept)}")
        for x in items:
            if is_stub_summary(x):
                print(f"       · {x.get('source','?')}: {(x.get('title') or '')[:64]}")
    return kept


# ─── Непереведённый чужой алфавит ───────────────────────────────────────────
#
# 09.10.2026, владелец: в «Новости из» карточка на грузинском. Перевод на язык
# пула не сработал (или издание отдало грузинский текст), и карточка ушла в
# эфир как есть. Пул читает кириллицу (ru) или латиницу (en/es/pt/fr); текст
# грузинским, армянским, арабским, ивритом, индийскими письменностями, тайским
# или иероглифами читателю не нужен — ни как заголовок, ни как «родной язык»
# (родные языки пулов — ky, kk, uz, tg — пишутся кириллицей или латиницей).
_FOREIGN_SCRIPT = re.compile(
    r"[\u10A0-\u10FF\u0530-\u058F\u0590-\u05FF\u0600-\u06FF\u0900-\u0DFF"
    r"\u0E00-\u0E7F\u1000-\u109F\u1100-\u11FF\u3040-\u30FF\u3400-\u9FFF\uAC00-\uD7AF]")
_OWN_LETTER = re.compile(r"[A-Za-zÀ-ÿА-Яа-яЁёӨөҮүҢң]")


def has_foreign_script(item) -> bool:
    """True: заголовок (или начало текста) в основном чужим алфавитом."""
    for field, take in (("title", 200), ("summary", 200)):
        t = str(item.get(field) or "")[:take]
        foreign = len(_FOREIGN_SCRIPT.findall(t))
        if foreign >= 3 and foreign > len(_OWN_LETTER.findall(t)):
            return True
    return False


def drop_foreign_script(items, lang):
    kept = [x for x in items if not has_foreign_script(x)]
    if len(kept) != len(items):
        print(f"  🔤 Чужой алфавит без перевода снят [{lang}]: {len(items) - len(kept)}")
        for x in items:
            if has_foreign_script(x):
                print(f"       · {x.get('source','?')}: {(x.get('title') or '')[:64]}")
    return kept


# ─── Известные заглушки изданий ─────────────────────────────────────────────
#
# Straits Times на месте фото отдаёт свой логотип «ST» (белые буквы на синем,
# 1140×760, 6 КБ). Картинки у них адресуются по содержимому, поэтому адрес у
# заглушки ОДИН на все статьи (проверено 01.10.2026). Плотность (см.
# drop_flat_placeholders) её ловит, но не во всех путях: заглушка возвращалась
# через og:image страницы и через выбор редактора. Владелец: «они не особенные,
# надо добавить их для распознавания и игнорировать». Дописывать сюда адреса
# других изданий по мере находок.
KNOWN_STUB_IMAGES = (
    "cassette.sphdigital.com.sg/image/straitstimes/"
    "4e77bf2f50f582021268b732c0c75bc468d09bd4549f5672fd2ca6140ad0dada",
)


def is_known_stub(url) -> bool:
    u = url or ""
    return any(s in u for s in KNOWN_STUB_IMAGES)


def strip_known_stubs(items, lang=""):
    """Снимает известную заглушку с карточки: лучше без фото, чем с логотипом.
    Помечает _need_photo — код попробует взять снимок у другого издания."""
    n = 0
    for x in items:
        if is_known_stub(x.get("imageUrl")):
            x["imageUrl"] = ""
            x["_need_photo"] = True
            x.pop("photoChecked", None)
            n += 1
    if n:
        print(f"  🪧 Известная заглушка издания [{lang}]: снята у {n}")
    return items



def wants_page_body(item: dict, min_len: int = 400, annotations_too: bool = False) -> bool:
    """Нужна ли новости дотяжка текста со страницы.

    Правило (09.10.2026, «потолок 600 знаков»): RSS-аннотация — не текст статьи,
    какой бы длины она ни была. extract_full_summary режет её до 600, а порог
    «≥400 — уже полный» оставлял зону 400–600 без сверки со страницей навсегда
    (Knews 544 из 1876, iXBT 449 из 1131, Naked Science 500 из 3899). Для
    новостей в эфире (annotations_too) дотягивается всё, что не взято со
    страницы (fromPage), независимо от длины; подменяет страница, лишь когда она
    заметно длиннее (это проверяет вызывающий)."""
    if annotations_too:
        return not item.get("fromPage")
    return len(item.get("summary", "")) < min_len


# ─── Правило абзацев (решение владельца, 09.10.2026) ───────────────────────
#
# Сколько показать карточке — решают АБЗАЦЫ, а не знаки:
#   · статья до трёх абзацев включительно — целиком;
#   · больше трёх — все, КРОМЕ ПОСЛЕДНЕГО. Его не добираем, даже если там вывод:
#     событие описывают в начале, подробности дальше, а вывод читатель делает
#     сам, на сайте издания.
# Числа знаков (600, 1200+100, 1300) больше не мера: они были приближением к
# этому правилу. Обрезка тела на скачивании — брак: «последний абзац» у
# обрезанного текста уже не последний, и правило ломается молча.

SHOW_WHOLE_UP_TO = 3
ARTICLE_HARD_CAP = 20000     # технический предохранитель памяти, а не редакционный предел
_PROSE_MIN = 80
_JUNK_PARA = re.compile(
    r"^\s*(читайте также|читайте ещё|читайте еще|подписывайтесь|подписаться|"
    r"фото\b|источник\b|реклама|по теме|read also|see also|subscribe)", re.I)


def real_paragraphs(text: str):
    """Настоящие абзацы страницы: без склейки, без деления длинных."""
    return [p.strip() for p in re.split(r"\n\s*\n|\n", (text or "").strip()) if p.strip()]


def cap_article(text: str, cap: int = ARTICLE_HARD_CAP) -> str:
    """Предохранитель от многомегабайтных страниц: режет по границе абзаца, не по знакам
    внутри абзаца. Правило абзацев работает уже над этим текстом."""
    text = (text or "").strip()
    if len(text) <= cap:
        return text
    paras, out, total = real_paragraphs(text), [], 0
    for p in paras:
        if out and total + len(p) > cap:
            break
        out.append(p)
        total += len(p) + 2
    return "\n\n".join(out)


def is_prose(p: str) -> bool:
    return len(p) >= _PROSE_MIN and not _JUNK_PARA.match(p)


def article_region(paras, idx=()):
    """Номера (с 1) абзацев тела статьи: опорные `idx` (выбор редактора; нет —
    первый связный текст), дыры между ними заполнены, а вперёд и назад — пока идёт
    связный текст. Подписи, «читайте также», короткие вывески раздела и хвост
    издания не берутся: на них область кончается."""
    n = len(paras)
    idx = sorted({i for i in idx if isinstance(i, int) and 1 <= i <= n})
    if not idx:
        first = next((i for i in range(1, n + 1) if is_prose(paras[i - 1])), None)
        if first is None:
            return []
        idx = [first]
    chosen = set(idx)
    for i in range(idx[0], idx[-1] + 1):
        if is_prose(paras[i - 1]):
            chosen.add(i)
    i = idx[-1] + 1
    while i <= n and is_prose(paras[i - 1]):
        chosen.add(i)
        i += 1
    i = idx[0] - 1
    while i >= 1 and is_prose(paras[i - 1]):
        chosen.add(i)
        i -= 1
    return sorted(chosen)


def paragraph_rule(items):
    """До трёх — целиком; больше — без последнего. Работает над списком чего угодно."""
    items = list(items)
    return items if len(items) <= SHOW_WHOLE_UP_TO else items[:-1]


def card_text(text: str) -> str:
    """Текст карточки по правилу абзацев из ПОЛНОЙ статьи (без выбора редактора)."""
    paras = real_paragraphs(text)
    if not paras:
        return (text or "").strip()
    region = article_region(paras)
    if not region:                       # связного текста нет — отдаём как есть
        return (text or "").strip()
    return "\n\n".join(paras[i - 1] for i in paragraph_rule(region))
