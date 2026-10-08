"""Где должна лежать новость: проверка полки по стране события (черновик).

Определения полок — EDITORIAL.md и docs/shelves_and_order.md. Здесь ЧИСТАЯ
проверка, чтобы ИЗМЕРИТЬ расхождения опубликованных полок с определением
(quality_audit.py), прежде чем переделывать конвейер.

ВАЖНО, что нашла первая версия этой проверки (06.10.2026): поле event_country
заполняют ДВА источника с разным смыслом — ИИ-отбор (только для «внутренних
дел» одной страны) и выпускающий редактор (место ЛЮБОГО события, в том числе
мирового: война в Йемене, протесты во Франции). Поэтому из одной страны события
нельзя сказать «полка неверна»: масштаб события (мировое или нет) отдельного
поля не имеет. Проверка честно говорит только «под подозрением», и это и есть
довод за пункт 1 плана: ИИ обязан возвращать для каждой карточки И страну
события, И масштаб.

Вердикт для опубликованной карточки:
  ok       — полка согласуется со страной события
  suspect  — не согласуется; верна лишь если событие мирового масштаба
  unknown  — страны события нет, проверить нельзя
"""
import re



def shelf_expected(item, home, space):
    """Полка по месту события и его масштабу.

    Новые поля ИИ (event_where + scale) дают ответ однозначно: мировой масштаб —
    world; иначе по стране; событие вне пространства при небольшом масштабе —
    «drop» (чужое внутреннее дело, в ленте быть не должно). Старое поле
    event_country (два смысла) даёт только осторожный ответ.
    """
    if item.get("bridge"):
        return "local"
    if item.get("scale"):
        if item["scale"] == "world":
            return "world"
        ev = item.get("event_where")
        if not ev:
            return None
        if ev == home:
            return "local"
        return "pool" if ev in space else "drop"
    ev = item.get("event_country")
    if not ev:
        return None
    if ev == home:
        return "local"
    if ev in space:
        return "pool"
    return "world"


def verdict(item, home, space):
    exp = shelf_expected(item, home, space)
    if exp is None:
        return "unknown"
    if exp == "drop":
        return "suspect"            # чужое внутреннее дело вообще не для этой ленты
    return "ok" if item.get("scope") == exp else "suspect"


# ─── Ответ ИИ: где случилось и какого масштаба (пункт 1 плана, 06.10.2026) ───

_ISO = re.compile(r"[A-Z]{2}")


def parse_where_scale(result, count=None):
    """Разбирает поля ответа ИИ "where" (страна КАЖДОЙ новости), "world" и
    "region" (номера мирового и регионального масштаба; остальные — местные).

    Номера 1-based, как у остальных полей ответа. → (where, scale), оба словари
    по индексу с нуля. where[i] — ISO-код или None («-»: несколько стран или
    страны нет). scale[i] есть только у карточек, о которых ИИ сказал "where":
    нет записи — значит ИИ не ответил, и мы не притворяемся, что знаем.
    """
    if not isinstance(result, dict):
        return {}, {}

    def ids(key):
        out = set()
        raw = result.get(key)
        for v in raw if isinstance(raw, (list, tuple)) else []:
            try:
                out.add(int(v) - 1)
            except (TypeError, ValueError):
                continue
        return out

    world, region = ids("world"), ids("region")
    where, scale = {}, {}
    raw_where = result.get("where")
    for k, v in (raw_where.items() if isinstance(raw_where, dict) else ()):
        try:
            i = int(k) - 1
        except (TypeError, ValueError):
            continue
        if count is not None and not (0 <= i < count):
            continue
        code = str(v).strip().upper()
        where[i] = code if _ISO.fullmatch(code) else None
        scale[i] = "world" if i in world else "region" if i in region else "local"
    return where, scale


# Родина пула — страна, чьи новости на этой полке видят соседи (для читателя из
# Казахстана «Новости из» включает Кыргызстан); в POOL_COUNTRIES её нет
POOL_HOME = {"ru": "KG", "en": "US", "es": "MX", "pt": "BR", "fr": "FR"}


def pool_shelf_fix(item, space):
    """Что делать с карточкой на полке «Новости из…» (scope == pool).

    Полка — ВНУТРЕННИЕ дела стран пула (владелец, 08.10.2026: «а у нас мировые
    новости изданий соседних стран»). Приложение метке сервера верит и страну
    события не читает, поэтому рубеж стоит здесь. Возвращает «world», если
    карточка не для этой полки, иначе None:
      · масштаб мировой — мировая, откуда бы её ни опубликовали (Уфа: «сбили
        сотни беспилотников»);
      · событие вне стран пула (РИА о Стамбуле, о Египте; РБК о Донецке) —
        мировая: издание из пула, а событие не из пула;
      · события нет, но и издание не из пула (ITC.ua, iXBT без страны).
    Новость без метки масштаба и места, от издания из пула — остаётся: недоказанное
    не снимаем, это дело замера (quality_audit.py, изъян region).
    """
    if item.get("scope") != "pool" or item.get("bridge"):
        return None
    if item.get("scale") == "world":
        return "world"
    ev = item.get("event_where")
    if ev:
        return None if ev in space else "world"
    country = (item.get("country") or "").strip().upper()
    return None if country in space else "world"


def final_shelf_guard(items, lang, space):
    """После редактора: чужое и мировое уезжает с «Новости из» в «Мировые»."""
    moved = []
    for x in items:
        if pool_shelf_fix(x, space) == "world":
            x["scope"] = "world"
            moved.append(x)
    if moved:
        print(f"  🗺️ С «Новости из» в «Мировые» [{lang}]: {len(moved)}")
        for x in moved[:5]:
            print(f"       · {x.get('source','?')} [{x.get('event_where') or x.get('country') or '—'}]: "
                  f"{(x.get('title') or '')[:56]}")
    return items
