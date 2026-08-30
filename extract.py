"""Извлечение текста статьи: цепочка обязанностей вместо регулярок под сайты.

    сырой HTML
        │
        ├─ 1. JSON-LD          articleBody из микроразметки — даром и начисто
        │
        ├─ 2. DOM-предчистка   выносим aside/nav/.byline и блоки-ссылки
        │       │                ИЗ ДЕРЕВА, до превращения в текст
        │       ├─ 3a. trafilatura
        │       └─ 3b. newspaper4k     (медленный, только если первый пас)
        │
        ├─ 4. Чистильщики      цепочка мелких правил, у каждого одна задача
        │
        └─ 5. Оценка качества   PASSED / NEEDS_FALLBACK / REJECTED

ЗАЧЕМ ТАК. Прежде правила чистки лежали в трёх местах (`_page_body`,
`polish_summary`, `quality_gate`) и дописывались под каждый попавшийся сайт.
Гонку с вёрсткой изданий так не выиграть: они меняют разметку чаще, чем мы
успеваем читать логи. Здесь ни одно правило не знает названия сайта — все
работают по признакам: плотность ссылок, доля букв, длина предложений.

ЧЕГО ЖДАТЬ ОТ JSON-LD (замер 24.08.2026 на сорока живых статьях наших
источников). Микроразметка есть у 80% страниц, но `articleBody` в ней —
только у 25%. Издания кладут headline, author и дату, а полный текст
намеренно не отдают: это подарок скраперам. Так что первая ступень —
бесплатный выигрыш на четверти страниц, а не замена разбору.

Модуль не знает ни про Firebase, ни про ИИ: на входе байты, на выходе текст.
Поэтому проверяется тестами без сети и ключей — см. test_extract.py
"""
import html
import json
import re
from dataclasses import dataclass, field
from enum import Enum

from bs4 import BeautifulSoup

try:
    import trafilatura
except ImportError:
    trafilatura = None

try:
    import newspaper
except ImportError:
    newspaper = None


class Verdict(Enum):
    PASSED = "годен"
    NEEDS_FALLBACK = "звать следующий разборщик"
    REJECTED = "негоден совсем"


@dataclass
class Extraction:
    text: str = ""
    extractor: str = ""
    verdict: Verdict = Verdict.REJECTED
    notes: list = field(default_factory=list)

    def ok(self) -> bool:
        return self.verdict is Verdict.PASSED and bool(self.text)


def _normalize(raw: str) -> str:
    """Схлопывает пробелы, СОХРАНЯЯ переводы строк между абзацами.

    Переводы строк нужны дальше: на них держатся перечни улиц и таблицы цен,
    а обрезка по границе абзаца без них вырождается в обрезку по предложению.
    """
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in (raw or "").splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()


# ─── 1. JSON-LD ─────────────────────────────────────────────────────────────

_ARTICLE_TYPES = ("Article", "NewsArticle", "ReportageNewsArticle",
                  "BackgroundNewsArticle", "OpinionNewsArticle")


def _walk_for_body(node):
    """Ищет articleBody в дереве микроразметки любой вложенности.

    Обходим рекурсивно, а не по фиксированному пути: издания заворачивают
    статью то в @graph, то в массив, то в mainEntityOfPage — единого способа
    нет, а рекурсия переживает любой из них.
    """
    if isinstance(node, dict):
        t = node.get("@type")
        for x in (t if isinstance(t, list) else [t]):
            if x and str(x).endswith(_ARTICLE_TYPES):
                body = node.get("articleBody")
                if isinstance(body, str) and len(body.strip()) > 200:
                    return body.strip()
        for v in node.values():
            found = _walk_for_body(v)
            if found:
                return found
    elif isinstance(node, list):
        for v in node:
            found = _walk_for_body(v)
            if found:
                return found
    return ""


def extract_jsonld(soup: BeautifulSoup, url: str = "") -> str:
    """Готовый текст статьи из микроразметки — без разбора вёрстки вообще.

    Самая надёжная ступень там, где она срабатывает: издание само отдаёт
    текст, отделённый от автора, времени чтения и кнопок «поделиться».
    Никакой мусор сюда попасть не может по устройству формата.
    """
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or tag.get_text() or "{}")
        except Exception:
            continue        # битая разметка у изданий обычное дело
        body = _walk_for_body(data)
        if body:
            return _normalize(body)
    return ""


# ─── 2. DOM-предчистка ──────────────────────────────────────────────────────
#
# Чистим ДЕРЕВО, а не текст. Разница принципиальна: вырезав <aside> из
# разметки, мы избавляемся от него навсегда; вычищая ту же врезку регуляркой
# из готового текста, мы каждый раз угадываем её границы и каждый раз
# ошибаемся по-новому.

_DROP_TAGS = ("script", "style", "noscript", "iframe", "form", "svg",
              "aside", "nav", "footer", "header")

# Приметы служебных блоков в class/id. Список общий для всех изданий: это
# слова из словаря вёрстки, а не названия сайтов
# Слова сопоставляем с ЦЕЛЫМ токеном класса, а не с подстрокой. Замер
# 24.08.2026: подстрочное совпадение выкосило статьи на восьми страницах из
# сорока — издания заворачивают материал в контейнеры вроде
# «article__meta-content» и «content-navigation», и поиск подстроки «meta»
# или «nav» уносил статью вместе с обёрткой. То есть получилась та же
# «регулярка под сайт», только грубее и незаметнее
# Имя класса сравнивается ЦЕЛИКОМ, включая дефисы. Составные имена
# перечислены явно: если резать токен по дефисам, «reading-time» распадётся
# на «reading» и «time», а таких слов в списке нет и быть не должно —
# «time» встречается в половине классов интернета
_DROP_HINTS = re.compile(
    r"^(byline|bylines|author|authors|author-info|meta|metadata|timestamp|"
    r"reading-time|read-time|time-to-read|share|sharing|share-tools|social|"
    r"social-share|social-links|subscribe|subscription|newsletter|promo|"
    r"advert|advertisement|ad|ads|related|related-articles|related-content|"
    r"recommended|recommendations|trending|breadcrumb|breadcrumbs|comment|"
    r"comments|cookie|cookies|paywall|nav|navigation|menu|sidebar|widget|"
    r"tags|tag-list|share-bar|article-tools)$", re.I)

LINK_DENSITY_MAX = 0.4

# Доля текста страницы, при которой узел неприкосновенен, что бы ни было
# написано в его классе. Так работает Readability: сначала находим, где
# лежит основной текст, и только потом чистим вокруг него
KEEP_IF_TEXT_SHARE = 0.25


def _link_density(node) -> float:
    """Доля слов, спрятанных в ссылки. Выше 40% — это навигация, не текст."""
    words = len((node.get_text(" ", strip=True) or "").split())
    if words < 12:
        return 0.0            # на коротком куске доля неустойчива
    linked = sum(len((a.get_text(" ", strip=True) or "").split())
                 for a in node.find_all("a"))
    return linked / words


def _text_len(node) -> int:
    try:
        return len(node.get_text(" ", strip=True) or "")
    except Exception:
        return 0


def presanitize_dom(html: bytes) -> BeautifulSoup:
    """Выносит из дерева служебные узлы и блоки с высокой плотностью ссылок.

    Главное правило: НЕ ТРОГАТЬ узел, в котором лежит заметная доля всего
    текста страницы, что бы ни было написано в его классе. Иначе рано или
    поздно попадётся издание, обернувшее статью в <div class="article-meta">,
    и мы вырежем её целиком — молча, без ошибки, просто выйдет пустая
    карточка. Так и случилось на восьми страницах при первом замере.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in list(soup.find_all(_DROP_TAGS)):
        try:
            tag.decompose()
        except Exception:
            pass

    body = soup.body or soup
    total = max(_text_len(body), 1)

    # Список собираем ЗАРАНЕЕ: decompose() правит дерево, и обход на лету
    # пропускает узлы. А у части элементов живой вёрстки атрибутов нет вовсе
    # (доктайпы, комментарии, битые теги) — отсюда getattr со значением по
    # умолчанию: на настоящих страницах это падало на первой же
    for tag in list(soup.find_all(True)):
        try:
            a = getattr(tag, "attrs", None) or {}
            cls = a.get("class") or []
            attrs = " ".join(filter(None, [
                " ".join(cls) if isinstance(cls, list) else str(cls),
                str(a.get("id") or ""), str(a.get("data-testid") or ""),
                str(a.get("role") or ""),
            ]))
        except Exception:
            continue
        if not attrs:
            continue
        tokens = attrs.split()
        if not any(_DROP_HINTS.match(t) for t in tokens if t):
            continue
        if _text_len(tag) / total > KEEP_IF_TEXT_SHARE:
            continue          # здесь лежит статья — не трогаем
        try:
            tag.decompose()
        except Exception:
            pass

    # Списки ссылок: меню, «читайте также», плитки рубрик
    for tag in list(soup.find_all(["div", "section", "ul", "ol"])):
        try:
            if (tag.parent is not None
                    and _link_density(tag) > LINK_DENSITY_MAX
                    and _text_len(tag) / total <= KEEP_IF_TEXT_SHARE):
                tag.decompose()
        except Exception:
            continue
    return soup


# ─── 3. Разборщики ──────────────────────────────────────────────────────────

def extract_trafilatura(html: bytes, url: str = "") -> str:
    if trafilatura is None:
        return ""
    # Передаём БАЙТЫ: кодировку определит парсер. На декодированной строке
    # французские страницы приходили в мохибейке («Ã©» вместо «é»)
    return _normalize(trafilatura.extract(
        html, include_tables=True, include_comments=False,
        include_images=False, favor_precision=True, deduplicate=True) or "")


def extract_newspaper(html: bytes, url: str = "") -> str:
    """Запасной разборщик.

    Замер 23.08.2026 на тридцати страницах: 918 знаков против 972 у
    trafilatura, пустых 5 против 1, и 0.69 секунды против 0.03 — в двадцать
    раз медленнее. Как основной не годится, как запасной окупается: полсекунды
    на редкую страницу дешевле пустой карточки.
    """
    if newspaper is None:
        return ""
    art = newspaper.Article(url or "https://example.com")
    art.download(input_html=html.decode("utf-8", "ignore"))
    art.parse()
    return _normalize(art.text or "")


# ─── 4. Чистильщики ─────────────────────────────────────────────────────────
#
# Один класс — одна задача. Добавить правило значит дописать класс и внести
# его в SANITIZERS, не трогая ничего вокруг.

class BaseSanitizer:
    name = "правило"

    def apply(self, text: str) -> str:
        raise NotImplementedError


class EntitySanitizer(BaseSanitizer):
    """Разбирает HTML-подстановки и добивает уцелевшие теги.

    Найдено 28.08 в опубликованной ленте: пять новостей из семи с замечаниями
    несли читателю сырьё — &quot;, &nbsp;, &#39;, &apos; — а Sky Sports ещё и
    открытый тег <p> прямо в тексте.

    Почему так вышло: извлекатели отдают текст, уже вынутый из разметки, и
    считается, что подстановки они разбирают сами. Разбирают — НО НЕ ВСЕГДА:
    когда текст приходит из JSON-LD или из атрибута, он остаётся в исходном
    виде, потому что через разметку не проходил вовсе. Именно французские
    издания, где мы чаще берём JSON-LD, и дали четыре случая из семи.

    ПОРЯДОК ВАЖЕН: это правило идёт ПЕРВЫМ. Остальные ищут слова в начале
    строки, а «&quot;Подпишитесь» началом строки не выглядит.

    Теги снимаем ПОСЛЕ разбора подстановок, а не до: &lt;p&gt; превращается в
    <p> именно на этом шаге, и снятая раньше разметка его бы не увидела.
    """
    name = "HTML-подстановки"
    _TAG = re.compile(r"<[^>]{1,200}>")

    def apply(self, text: str) -> str:
        out = html.unescape(text)
        out = self._TAG.sub(" ", out)
        # Неразрывный пробел выглядит как обычный, но ломает подсчёт слов и
        # переносы; строке от него ни тепло ни холодно
        out = out.replace("\xa0", " ").replace("\u200b", "")
        out = re.sub(r"[ \t]{2,}", " ", out)
        return out.strip()


class PromoLineSanitizer(BaseSanitizer):
    """Выбрасывает ОТДЕЛЬНЫЕ строки-зазывалки, не трогая статью.

    «Subscribe to The Y'all — a weekly dispatch about the people, places and
    policies defining Texas» — это врезка про рассылку ПОСРЕДИ материала, а не
    его хвост. Хвостовое правило (FooterLinkSanitizer) её не берёт: оно режет
    всё, что ниже, и, встретив такую врезку в середине, выбросило бы половину
    статьи. Поэтому здесь снимаем строку и идём дальше.
    """
    name = "врезка про рассылку"
    _RX = re.compile(
        r"(subscribe to |sign up for |newsletter|inscrivez-vous|"
        r"abonnez-vous|suscríb[ae]|assine (a )?newsletter|"
        r"подпишитесь на (нашу |рассылку))", re.I)

    def apply(self, text: str) -> str:
        lines = [l for l in text.split("\n") if not self._RX.search(l)]
        out = "\n".join(lines).strip()
        return out if len(out) >= 200 else text


class VideoPlaylistSanitizer(BaseSanitizer):
    """Выбрасывает список роликов видеоплеера, принятый за текст статьи.

    Найдено пользователем 28.08.2026 на NBC News. Вместо новости читатель
    получил расписание:

        Trump orders Lake Ontario renamed 'Lake America' 01:25.
        Americans missing in deadly flood disaster 02:08.
        Now PlayingPatient battles insurance over coverage 03:28.
        UP NEXTJury deliberates in Lindsay Clancy murder trial 02:20.

    Он назвал это программой передач, и это точное описание: страница с видео
    отдаёт не статью, а плейлист. Извлекатель честно берёт самый текстовый
    блок страницы — и на таких страницах им оказывается именно список.

    Признак надёжный и не требует словаря: СТРОКИ, КОНЧАЮЩИЕСЯ ХРОНОМЕТРАЖЕМ
    вида 01:25. У живого текста так не бывает. Двух таких строк довольно —
    одна может оказаться цитатой со временем.

    Слова «Now Playing» и «Up Next» проверяем тоже, но вторым признаком: они
    английские, а плееры бывают и на других языках, хронометраж же везде один.
    """
    name = "плейлист видеоплеера"
    _STAMP = re.compile(r"\d{1,2}:\d{2}\s*\.?\s*$")
    _MARK = re.compile(r"(now playing|up next|watch:|см\. также видео)", re.I)

    def apply(self, text: str) -> str:
        lines = [l for l in text.split("\n") if l.strip()]
        if not lines:
            return text
        stamped = sum(1 for l in lines if self._STAMP.search(l.strip()))
        if stamped < 2 and not self._MARK.search(text):
            return text
        kept = [l for l in lines
                if not self._STAMP.search(l.strip()) and not self._MARK.search(l)]
        out = "\n".join(kept).strip()
        # Если после чистки не осталось текста — значит вся «статья» и была
        # плейлистом. Возвращаем пустоту: пусть решает оценка качества, ей
        # виднее, звать ли следующий извлекатель
        return out


class HeaderNoiseSanitizer(BaseSanitizer):
    """Срезает авторскую плашку ПЕРЕД первым абзацем.

    «Автор, Иван Петров / Отдел новостей, Лондон / Время чтения: 5 мин» — это
    префикс хорошей статьи. Её надо срезать, а статью оставить: отвергать
    материал из-за подписи автора значит терять его на ровном месте.

    Признак не в словах, а в ФОРМЕ: короткие строки без точки в конце,
    идущие подряд до первого настоящего абзаца. Останавливаемся на первой
    же строке, похожей на текст, — длинной и с точкой.
    """
    name = "плашка автора"

    def apply(self, text: str) -> str:
        lines = text.split("\n")
        i = 0
        while i < min(len(lines), 8):
            ln = lines[i].strip()
            if len(ln) >= 60 and any(c in ln for c in ".!?"):
                break                      # начался настоящий текст
            if len(ln) <= 45 and not ln.endswith((".", "!", "?", "…")):
                i += 1
                continue
            break
        rest = "\n".join(lines[i:]).strip()
        return rest if len(rest) >= 200 else text


class CreditSanitizer(BaseSanitizer):
    """Убирает строки-кредиты: «Источник изображения: Autohome»."""
    name = "кредит изображения"
    _RX = re.compile(
        r"^\s*(источник изображени[яй]|фото|photo|image|getty|reuters|afp|epa|"
        r"credit|crédit|imagen|imagem)\s*[:—–-].{0,80}$", re.I)

    def apply(self, text: str) -> str:
        return "\n".join(l for l in text.split("\n") if not self._RX.match(l)).strip()


class FooterLinkSanitizer(BaseSanitizer):
    """Снимает хвост: «Читайте также», «Подпишитесь», «Следите за нами»."""
    name = "хвост со ссылками"
    _RX = re.compile(
        r"^\s*(читайте также|подпишитесь|следите за нами|read more|"
        r"follow us|subscribe|lire aussi|abonnez-vous|suivez-nous|"
        r"lea también|siga-nos|leia também|voir aussi)\b", re.I)

    def apply(self, text: str) -> str:
        lines = text.split("\n")
        for i, ln in enumerate(lines):
            if self._RX.match(ln):
                head = "\n".join(lines[:i]).strip()
                return head if len(head) >= 200 else text
        return text


class TranslationNoteSanitizer(BaseSanitizer):
    """Снимает примечание переводчика в начале материала.

    Переводные редакции — Би-би-си по-русски, DW, Euronews — ставят первой
    фразой «Это перевод материала корреспондента Би-би-си. Оригинал на
    английском можно прочитать здесь». Это не новость, а служебная сноска, и
    ссылки за словом «здесь» у нас всё равно нет.

    Найдено 29.08.2026 в испанской ленте: заметка о краже колье из венского
    музея начиналась словами «Esta es una traducción de un reportaje de un
    corresponsal de la BBC. El original en inglés se puede consultar aquí» —
    то есть сноску мы не вырезали, а ДОБРОСОВЕСТНО ПЕРЕВЕЛИ и показали
    читателю обещание ссылки, которой нет.

    Режем в оригинале, до перевода: после перевода фраза выглядит всякий раз
    по-новому, и ловить её пришлось бы на пяти языках вместо двух. Тот же
    урок, что с подписями к видеонарезкам 17.08.
    """
    name = "примечание переводчика"
    _RX = re.compile(
        r"^\s*(это перевод|этот материал.{0,20}перевод|"
        r"this (is|article is) a translation|"
        r"esta es una traducci[oó]n|este art[ií]culo es una traducci[oó]n|"
        r"esta [eé] uma tradu[cç][aã]o|"
        r"cet article est une traduction|ceci est une traduction)\b",
        re.I)

    def apply(self, text: str) -> str:
        # Сноска — первое предложение, редко два. Дальше по тексту такая
        # фраза уже часть материала, и трогать её нельзя
        head, sep, tail = text.partition("\n")
        if self._RX.match(head) and tail.strip():
            return tail.strip()
        # Бывает и одной строкой со всей заметкой — тогда режем по точке
        if self._RX.match(text):
            parts = re.split(r"(?<=[.!?])\s+", text, maxsplit=2)
            rest = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
            # Вторая фраза — «оригинал можно прочитать здесь» — тоже сноска
            if rest.lower().startswith((
                    "оригинал", "the original", "el original",
                    "o original", "l'original", "l’original")):
                rest = " ".join(parts[2:]).strip() if len(parts) > 2 else ""
            return rest if len(rest) >= 120 else text
        return text


class AgencyLeadSanitizer(BaseSanitizer):
    """Снимает выжимку агентства, стоящую ПЕРЕД телеграфным зачином.

    РИА, ТАСС, Интерфакс отдают в ленту сперва два-три тезиса, а следом ту же
    новость целиком — с зачина вида «ПЕКИН, 29 авг - РИА Новости». Читатель
    получает один и тот же текст дважды подряд.

    Найдено пользователем 29.08.2026: заметка про обезьян на Хайнане. Три
    тезиса, и сразу за ними абзац, повторяющий первый из них слово в слово.

    Правило узкое нарочно: режем ТОЛЬКО если зачин найден не в самом начале —
    значит, перед ним стоит служебный блок. Зачин в первой строке (обычный
    случай) не трогаем вовсе, и материалы без зачина тоже.
    """
    name = "выжимка агентства перед зачином"
    # «ПЕКИН, 29 авг - РИА Новости.» / «MOSCOW, Aug 29 (Reuters) -»
    _RX = re.compile(
        # Зачин бывает и не с начала строки: Sputnik шлёт всё одним абзацем,
        # и второй зачин стоит после точки. Само сочетание — ГОРОД ПРОПИСНЫМИ,
        # запятая, число с месяцем, тире — слишком редкое, чтобы совпасть
        # случайно, так что послабление ничего лишнего не захватит
        r"(?:^|\n|[.,]\s+)\s*([А-ЯЁ][А-ЯЁ \-]{2,30}|[A-Z][A-Z \-]{2,30}),\s*"
        # Между числом и месяцем бывает и пробел, и дефис: РИА пишет
        # «29 авг», Sputnik — «30-авг». Из-за одного дефиса правило молчало
        r"\d{1,2}[\s-]*[^\W\d_]{3,12}\.?\s*[-–—(]",
        re.M)

    def apply(self, text: str) -> str:
        # БЕРЁМ ПОСЛЕДНИЙ ЗАЧИН, А НЕ ПЕРВЫЙ.
        #
        # У Sputnik заметка приходит так: «Sputnik Кыргызстан. БИШКЕК,
        # 30-авг. — Sputnik. [аннотация оборвана многоточием] 30.08.2026,
        # Sputnik Кыргызстан. БИШКЕК, 30-авг. — Sputnik. [полный текст]».
        # Зачинов два, и первый стоит в самом начале — правило считало его
        # обычным началом заметки и не трогало ничего. Читатель получал текст
        # дважды: пользователь 30.08 «повторы в тексте».
        #
        # Последний зачин и есть начало настоящего материала: всё, что до
        # него, — служебные обёртки агентства.
        best = None
        for m in self._RX.finditer(text):
            if m.start() < 20:
                continue          # зачин в самом начале — обычная заметка
            if len(text) - m.start() < 200:
                break             # дальше остаётся огрызок, не режем
            best = m
        if best is None:
            return text
        # Режем по НАЧАЛУ ГОРОДА, а не по разделителю перед ним: иначе точка
        # или запятая от прежней фразы уехала бы в начало новости
        return text[best.start(1):].strip()


class RepeatedLeadSanitizer(BaseSanitizer):
    """Убирает аннотацию, за которой идёт та же новость с начала.

    Издание кладёт в ленту короткую выжимку, а на странице она стоит перед
    самим материалом — и разбор берёт оба куска подряд. Читатель получает одно
    и то же дважды, а на стыке пропадает точка: «…для производителей цифровых
    продуктов С 11 сентября в Евросоюзе начнёт действовать…» Пользователь
    30.08 заметил именно её: «нет точки в конце предложения». Точка не
    потерялась — там не конец предложения, там шов.

    Ищем ПОВТОР НАЧАЛА: если первые тридцать знаков встречаются ещё раз
    дальше, всё до второго вхождения — выжимка, и её место в мусоре.

    Тридцать знаков, а не десять: короткое начало вроде «В Бишкеке» повторится
    в любой заметке о городе. Тридцать совпавших подряд — это уже не
    совпадение, а тот же текст.

    От AgencyLeadSanitizer отличается тем, что здесь НЕТ телеграфного зачина:
    у iXBT, Wired и прочих сетевых изданий его не бывает вовсе.
    """
    name = "повтор начала"

    # Шов: строчная буква, пробел, прописная — и ни одного знака конца
    # предложения между ними. Так выглядит место склейки лида с материалом
    _SEAM = re.compile(r"(?<=[а-яёa-z]) (?=[А-ЯЁA-Z])")

    def apply(self, text: str) -> str:
        body = " ".join((text or "").split())
        # 1. Прямой повтор: первые тридцать знаков встречаются ещё раз.
        #    Так шла заметка про искусственный интеллект и диких животных —
        #    весь текст дважды подряд
        head = body[:30]
        if len(head) == 30:
            second = body.find(head, 60)
            if second > 0 and len(body[second:].strip()) >= 200:
                return body[second:].strip()

        # 2. Шов без знака препинания: лид оборван, за ним пересказ.
        #    «…для производителей цифровых продуктов С 11 сентября в
        #    Евросоюзе начнёт действовать…» — точки нет, потому что там не
        #    конец предложения, а шов.
        for m in self._SEAM.finditer(body[:400]):
            prefix, tail = body[:m.start()], body[m.end():]
            if len(prefix) < 60 or len(tail) < 200:
                continue
            # В лиде НЕТ ни одного знака конца — законченный абзац так не
            # выглядит, а оборванная выжимка выглядит именно так
            if re.search(r"[.!?…]", prefix):
                continue
            # И тот же смысл идёт дальше: три значимых слова из лида
            # встречаются в начале материала
            words = {w.lower() for w in re.findall(r"[^\W\d_]{5,}", prefix)}
            again = sum(1 for w in words if w in tail[:400].lower())
            if again >= 3:
                return tail.strip()
        return text


SANITIZERS = [
    # ПЕРВЫМ — разбор подстановок и снятие тегов: остальные правила ищут слова
    # в начале строки, а «&quot;Подпишитесь» началом строки не выглядит
    EntitySanitizer(),
    VideoPlaylistSanitizer(),
    HeaderNoiseSanitizer(),
    TranslationNoteSanitizer(),
    AgencyLeadSanitizer(),
    RepeatedLeadSanitizer(),
    CreditSanitizer(),
    PromoLineSanitizer(),
    FooterLinkSanitizer(),
]


# ─── 5. Оценка качества ─────────────────────────────────────────────────────

class QualityGate:
    """Считает метрики текста и выносит вердикт — без списков слов.

    Все проверки статистические намеренно. Список запрещённых фраз пришлось
    бы дописывать под каждое издание и каждый язык, а доля букв и плотность
    точек одинаковы для французского меню и для казахского.
    """
    MIN_CHARS = 200
    MIN_LETTER_SHARE = 0.55
    MIN_SENTENCE_LEN = 25

    # Страницы-заслоны — единственное место, где без слов не обойтись: по
    # форме «Access Denied» неотличим от короткой новости. 23.08 trafilatura
    # «спасла» две страницы, где наш разбор давал пустоту, и обе оказались
    # заслонами Le Parisien и Le Monde — читатель получил бы сообщение об
    # ошибке вместо новости
    _BLOCKED = re.compile(
        r"access denied|permission to access|403 forbidden|"
        r"identifié comme automatisé|automated (?:traffic|bot)|"
        r"enable javascript|activez javascript|are you a robot|"
        r"vérification de sécurité|security check|checking your browser|"
        r"cloudflare|captcha|subscribe to (?:continue|read)|"
        r"abonnez-vous pour|suscríbete para|assine para continuar|"
        r"этот контент доступен только подписчикам|errors\.edgesuite\.net", re.I)

    def metrics(self, text: str) -> dict:
        lines = [l for l in text.split("\n") if l.strip()]
        sentences = [s for s in re.split(r"(?<=[.!?…])\s+", text) if s.strip()]
        letters = sum(1 for c in text if c.isalpha())
        return {
            "chars": len(text),
            "letter_share": letters / len(text) if text else 0.0,
            "avg_sentence": (sum(len(s) for s in sentences) / len(sentences)
                             if sentences else 0.0),
            "short_line_share": (sum(1 for l in lines if len(l) < 40) / len(lines)
                                 if lines else 0.0),
            "dotted_line_share": (sum(1 for l in lines if any(c in l for c in ".!?"))
                                  / len(lines) if lines else 0.0),
            "unique_line_share": (len(set(lines)) / len(lines)) if lines else 1.0,
            "lines": len(lines),
        }

    def evaluate(self, text: str):
        """Возвращает (вердикт, причина). Причина — фраза для лога."""
        # Заслон проверяем ПЕРВЫМ, до длины: «Access Denied» короче двухсот
        # знаков, и по длине он выглядел бы обрывком — тогда мы звали бы
        # следующий разборщик, который увидит ту же самую страницу
        if text and self._BLOCKED.search(text[:600]) and len(text) < 1200:
            return Verdict.REJECTED, "страница-заслон вместо статьи"

        if not text or len(text) < self.MIN_CHARS:
            return Verdict.NEEDS_FALLBACK, f"короче {self.MIN_CHARS} знаков"

        m = self.metrics(text)

        # Меню сайта: много коротких строк и почти нет точек. 24.08, Le Figaro:
        # «Toutes les infos sport / Tous les formats / À la une / Sports…»,
        # дальше счёт матча столбиком
        if (m["lines"] >= 5 and m["short_line_share"] > 0.7
                and m["dotted_line_share"] < 0.3):
            return Verdict.NEEDS_FALLBACK, "меню сайта вместо текста"

        if m["letter_share"] < self.MIN_LETTER_SHARE and m["chars"] > 400:
            return Verdict.NEEDS_FALLBACK, "мало букв — таблица или сводка цифр"

        if m["avg_sentence"] < self.MIN_SENTENCE_LEN and m["chars"] > 400:
            return Verdict.NEEDS_FALLBACK, "предложения слишком коротки — метаданные"

        if m["lines"] >= 6 and m["unique_line_share"] < 0.6:
            return Verdict.NEEDS_FALLBACK, "строки повторяются — это разметка"

        return Verdict.PASSED, ""


GATE = QualityGate()


# ─── Оркестратор ────────────────────────────────────────────────────────────

def extract_article(html: bytes, url: str = "", extra_extractors=None) -> Extraction:
    """Проводит страницу по цепочке до первого годного результата.

    `extra_extractors` — чтобы вызывающий подставил свои разборщики. У нас
    это прежний обход абзацев, где накоплено то, чего библиотеки не знают:
    таблицы цен на топливо, перечни улиц в <li> после двоеточия, контейнер
    Kaktus со всей статьёй внутри одного элемента. Оркестратор о них не знает
    и знать не должен.

    Если годного нет ни у кого — арбитраж: отдаём САМЫЙ ПОЛНЫЙ из негодных,
    но с честным вердиктом. Решать, публиковать ли его, будет вызывающий: у
    него есть контекст, которого здесь нет, — например срочность, ради
    которой стоит взять и куцый текст.
    """
    notes, best = [], Extraction()
    # ДВА дерева, и это не расточительство. Микроразметка лежит в <script
    # type="application/ld+json">, а предчистка выносит все <script> подряд —
    # то есть первая ступень цепочки читала бы дерево, из которого её данные
    # уже удалены. Поймано тестом при написании, 24.08.2026
    raw_soup = BeautifulSoup(html, "html.parser")
    soup = presanitize_dom(html)
    clean_html = str(soup).encode("utf-8", "ignore")

    stages = [("json-ld", lambda h, u: extract_jsonld(raw_soup, u)),
              ("trafilatura", extract_trafilatura),
              ("newspaper4k", extract_newspaper)]
    stages += list(extra_extractors or [])

    for name, fn in stages:
        try:
            text = fn(clean_html, url) or ""
        except Exception as e:
            notes.append(f"{name}: сбой — {str(e)[:60]}")
            continue
        if not text:
            notes.append(f"{name}: пусто")
            continue

        for s in SANITIZERS:
            before = text
            try:
                text = s.apply(text) or before
            except Exception:
                text = before
            if text != before:
                notes.append(f"{name}: снята {s.name}")

        verdict, why = GATE.evaluate(text)
        if verdict is Verdict.PASSED:
            return Extraction(text, name, verdict, notes)
        notes.append(f"{name}: {why}")
        if verdict is Verdict.REJECTED:
            return Extraction("", name, verdict, notes)
        if len(text) > len(best.text):
            best = Extraction(text, name, verdict, [why])

    best.notes = notes + best.notes
    return best
