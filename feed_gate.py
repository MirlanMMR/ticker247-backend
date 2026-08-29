# -*- coding: utf-8 -*-
"""Последний рубеж перед публикацией: чиним что можно, отсекаем что нельзя.

ГЛАВНОЕ ПРАВИЛО: ВЫБРАСЫВАЕМ ТОЛЬКО НЕПОПРАВИМОЕ.

Каждая выброшенная новость — дыра в ленте. Подстановки, теги и кириллица в
имени издания чинятся здесь же, за доли миллисекунды, и терять из-за них
материал значит наказывать читателя за нашу неаккуратность. А вот текст на
чужом языке починить нечем: перевод стоит денег и времени, а на этом рубеже
уже поздно.

Рубеж НЕ ЗАМЕНЯЕТ извлечение и очистку. Он ловит то, что просочилось мимо
них, — и, судя по 28.08.2026, просачивается: цепочка извлечения даёт вчетверо
больше текста, но её первая ступень (JSON-LD) отдаёт сырьё, через разметку не
проходившее, и подстановки в нём остаются целыми.

Проверяется без сети, ключей и базы — см. test_feed_gate.py.
"""
import html
import re

from textcut import display_source

_TAG = re.compile(r"<[^>]{1,200}>")
_CYR = re.compile(r"[А-Яа-яЁё]")
_ENTITY = re.compile(r"&(quot|nbsp|amp|apos|lt|gt|#\d{2,4}|[a-z]{2,8});")

# Служебные слова: по ним отличаем язык текста. Не словарь языка, а горсть
# частотных и однозначных слов — этого хватает, чтобы отделить непереведённое
_LANGWORDS = {
    "ru": re.compile(r"\b(что|который|также|после|сообщает|заявил|году)\b", re.I),
    "en": re.compile(r"\b(the|and|that|with|which|according|said)\b", re.I),
    "es": re.compile(r"\b(que|para|según|también|dijo|los|las)\b", re.I),
    "pt": re.compile(r"\b(que|para|segundo|também|disse|dos|das)\b", re.I),
    "fr": re.compile(r"\b(que|pour|selon|également|dit|les|des)\b", re.I),
}


def _clean(text: str) -> str:
    """Разбирает подстановки и добивает уцелевшие теги.

    Порядок важен: теги снимаем ПОСЛЕ разбора, иначе &lt;p&gt; превратится в
    <p> уже после того, как разметку сняли, и уцелеет.
    """
    if not text:
        return text
    out = html.unescape(text)
    out = _TAG.sub(" ", out)
    out = out.replace("\xa0", " ").replace("​", "")
    return re.sub(r"[ \t]{2,}", " ", out).strip()


def repair(item: dict, pool_lang: str) -> dict:
    """Чинит то, что чинится. Новость не теряется никогда."""
    out = dict(item)
    for field in ("title", "summary"):
        val = out.get(field)
        if isinstance(val, str) and (_ENTITY.search(val) or "<" in val):
            out[field] = _clean(val)
    src = out.get("source", "")
    if src:
        out["source"] = display_source(src, pool_lang)
    return out


def unreadable(item: dict, pool_lang: str) -> bool:
    """Не сможет ли читатель этого пула прочесть новость.

    Считаем по ТЕКСТУ, а не по метке языка у источника: метка говорит, откуда
    новость взята, а не на каком языке она в итоге опубликована. Перевод у нас
    бывает и удачным, и несостоявшимся, и правду знает только сам текст.

    Порог намеренно грубый. Тонкая проверка языка ошибается на коротких
    заголовках и на именах собственных, а цена ошибки здесь — выброшенная
    новость. Пусть лучше проскочит сомнительная, чем пропадёт хорошая.
    """
    text = f"{item.get('title', '')} {item.get('summary') or ''}"
    if len(text) < 60:
        return False                     # на коротком тексте гадать нельзя
    has_cyr = bool(_CYR.search(text))
    if pool_lang == "ru":
        return not has_cyr
    if has_cyr:
        return True
    own = len(_LANGWORDS.get(pool_lang, _LANGWORDS["en"]).findall(text))
    alien = max((len(rx.findall(text))
                 for lg, rx in _LANGWORDS.items()
                 if lg not in (pool_lang, "ru")), default=0)
    return own == 0 and alien >= 3


def gate(items, pool_lang):
    """Возвращает (что публикуем, что выбросили и почему, сколько починили)."""
    kept, dropped, fixed = [], [], 0
    for it in items:
        good = repair(it, pool_lang)
        if good != it:
            fixed += 1
        if unreadable(good, pool_lang):
            dropped.append(good)
            continue
        kept.append(good)
    return kept, dropped, fixed

# ─── Одна редакция об одном событии — одна новость ──────────────────────────

def _stems(title: str) -> set:
    return {w[:4] for w in re.findall(r"[a-zà-ÿа-яё]{4,}", (title or "").lower())}


def same_event(a: dict, b: dict) -> bool:
    """Об одном ли событии эти две новости.

    Порог подобран по живой ленте 28.08.2026: у настоящих пар (BBC Mundo и BBC
    Brasil о смерти короля Норвегии; две заметки Kabar.kg об одной подготовке)
    выходило 3 общих корня при половине пересечения. У разных новостей столько
    не набиралось ни разу во всех пяти пулах.
    """
    sa, sb = _stems(a.get("title", "")), _stems(b.get("title", ""))
    if not sa or not sb:
        return False
    common = sa & sb
    return len(common) >= 3 and len(common) / min(len(sa), len(sb)) >= 0.5


def _worth(item: dict, pool_lang: str = "") -> tuple:
    """Какая из двух новостей лучше.

    ПЕРВЫМ ДЕЛОМ — РОДНАЯ РЕДАКЦИЯ. Если издание пишет на языке пула, берём
    его, а не перевод с третьего языка.

    Найдено 29.08.2026: в испанскую ленту пришла заметка о краже колье из
    венского музея — из РУССКОЙ службы Би-би-си, при живой BBC Mundo. Путь
    вышел английский → русский → испанский, и вместе с ним доехала служебная
    сноска «это перевод материала корреспондента Би-би-си». Смысл на двойном
    переводе садится неизбежно, а спрашивать было не у кого: правило смотрело
    на длину и фото, но не на язык.

    Дальше как было: с фотографией, длиннее, раньше вышедшая.
    """
    native = 1 if (pool_lang and item.get("source_lang") == pool_lang) else 0
    return (native,
            1 if (item.get("imageUrl") or "").startswith("http") else 0,
            len(item.get("summary") or ""),
            -(item.get("publishedAt") or 0))


def drop_family_repeats(items, family_of, pool_lang: str = ""):
    """Убирает вторую новость об одном событии ОТ ТОЙ ЖЕ РЕДАКЦИИ.

    Найдено пользователем 28.08.2026 по снимку ленты: одно и то же фото короля
    Норвегии дважды подряд — от BBC Mundo и BBC Brasil. Ссылки разные,
    заголовки разные, редакция одна, событие одно.

    ПОЧЕМУ ТОЛЬКО ВНУТРИ РЕДАКЦИИ, а не вообще между всеми. Две газеты об одном
    событии — это не повтор, а разные взгляды; на них у нас построен обзор
    прессы, и склеивать их в ленте значило бы обеднять её. А вот BBC Mundo и
    BBC Brasil — это одна редакция на двух языках: взгляд один, и второй раз
    его показывать незачем.

    Из пары остаётся лучшая: с фотографией, длиннее и раньше вышедшая.
    """
    kept, dropped = [], []
    for it in items:
        fam = family_of(it.get("source", ""))
        twin_i = next((i for i, k in enumerate(kept)
                       if family_of(k.get("source", "")) == fam
                       and same_event(k, it)), None)
        if twin_i is None:
            kept.append(it)
            continue
        if _worth(it, pool_lang) > _worth(kept[twin_i], pool_lang):
            dropped.append(kept[twin_i])
            kept[twin_i] = it
        else:
            dropped.append(it)
    return kept, dropped
