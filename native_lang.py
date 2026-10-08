"""Государственные языки кириллицы: пометка по тексту и потолок 50/50.

Правило владельца (06.10.2026): кыргызский — только для Кыргызстана, казахский —
только для Казахстана, и так далее. Там, где кириллица, лента — до 50/50 на
русском и на государственном языке. Показ по странам решает приложение
(NewsPlace.readableFor + NATIVE_LANGS: KG→ky, KZ→kk, UZ→uz, TJ→tg, BY→be).

Беда была в разметке: тексты Kabar.kg по-кыргызски лежали в базе с language="ru"
(язык берётся с настройки пула, а не из текста). Приложение принимало их за
русские и показывало ВСЕМ читателям русского пула, а не только дома в Киргизии.
Мировая новость на кыргызском допустима (владелец 06.10.2026): снимать такие
карточки нельзя, только правильно помечать.

Здесь два действия, оба без ИИ:
  1. detect_native — язык по самому тексту (буквы, затем служебные слова);
  2. cap_native_share — на «Местных» родного языка не больше половины.
"""
import re

# Буквы, которых нет в русском. Порядок проверки важен: у языков они пересекаются
_KK_ONLY = re.compile(r"[әұһ]")           # казахский
_TG_ONLY = re.compile(r"[ӣӯҷ]")           # таджикский
_UZ_LETTERS = re.compile(r"[ўҳ]")         # узбекская кириллица (ў есть и у белорусского)
_SHARED = re.compile(r"[өүң]")            # кыргызский и казахский
_KQ = re.compile(r"[қғ]")                 # казахский, узбекский, таджикский

_KY_WORDS = re.compile(
    r"\b(жана|менен|үчүн|боюнча|болду|болуп|кылды|деп|эле|ошондой|аркылуу|"
    r"тарабынан|жөнүндө|катары|анын|алардын)\b")
_KK_WORDS = re.compile(
    r"\b(және|мен|үшін|туралы|болды|болып|сонымен|арқылы|бойынша|деп|ол|бұл)\b")


def detect_native(item):
    """→ код языка ('ky', 'kk', 'uz', 'tg') или None, если текст русский."""
    text = ((item.get("title") or "") + " " + (item.get("summary") or "")[:300]).lower()
    if _KK_ONLY.search(text):
        return "kk"
    if _TG_ONLY.search(text):
        return "tg"
    if _UZ_LETTERS.search(text):
        return "uz" if re.search(r"ҳ|қ|ғ", text) else None   # ў без ҳ — белорусский, не наш случай
    if _KQ.search(text):
        return "kk"
    if _SHARED.search(text):
        return "ky"
    ky, kk = len(_KY_WORDS.findall(text)), len(_KK_WORDS.findall(text))
    if ky >= 2 and ky > kk:
        return "ky"
    if kk >= 2 and kk > ky:
        return "kk"
    return None


def looks_kyrgyz(item) -> bool:
    return detect_native(item) == "ky"


def apply(items, pool_lang: str):
    """→ (список, [перемеченные]). Ничего не снимает. Только для русского пула."""
    if pool_lang != "ru":
        return items, []
    relabeled = []
    for x in items:
        if x.get("category") in ("CURRENCY", "CRYPTO"):
            continue
        code = detect_native(x)
        if code and x.get("language") != code:
            x["language"] = code
            relabeled.append(x)
    return items, relabeled


def _rank(x):
    return (x.get("priority", 0), x.get("publishedAt", 0))


def cap_native_share(items, pool_lang: str, share: float = 0.5):
    """На полке local родной язык — не больше [share] карточек (50/50).

    «Родной» — любой язык, кроме языка пула. Лишние снимаются из родного языка,
    слабейшие первыми (приоритет, затем давность). → (список, [снятые]). Карточки на
    языке пула не трогаем: цель — не дать родному вытеснить язык пула, а не наоборот.
    Работает для всех пулов: русский + кыргызский, английский + французский (Канада),
    французский + нидерландский (Бельгия).
    """
    local = [x for x in items if x.get("scope") == "local"
             and x.get("category") not in ("CURRENCY", "CRYPTO")]
    native = [x for x in local if x.get("language") not in (None, "", pool_lang, "unknown")]
    main_lang = len(local) - len(native)
    # Нет карточек на языке пула — вытеснять нечего. У Армении обе ленты по-армянски,
    # и потолок «родного не больше половины» снёс бы полку целиком (06.10.2026)
    if main_lang == 0:
        return items, []
    # n родных при r основных укладываются в долю: n / (n + r) ≤ share
    allowed = int(share * main_lang / (1 - share)) if share < 1 else len(native)
    if len(native) <= max(allowed, 0):
        return items, []
    drop = sorted(native, key=_rank)[:len(native) - max(allowed, 0)]
    ids = {id(x) for x in drop}
    return [x for x in items if id(x) not in ids], drop
