# -*- coding: utf-8 -*-
"""Боевой режим дозора: МИРОВОЕ СРОЧНОЕ (15.10.2026, решение владельца).

Владелец: «включи боевой режим дозора только для мирового срочного (3 редакции + слово беды)».
Только для мирового: тревоги по городам и официальные каналы отклонены («города тревоги не надо»).

Дозор находит событие, о котором за полтора часа написали ТРИ И БОЛЬШЕ независимых редакции
(patrol_rules.event_tier == 'urgent': слово беды в заголовке), и кладёт карточку со «срочно» в ленту
пула прямо сейчас, не дожидаясь полного разбора (он идёт по слотам три раза в сутки).

Слова беды из patrol_rules.DISASTER слишком широки для права будить (журнал J37, J49: «пожар»,
«погиб», «взрыв» — это и одиночная авария, и взрыв на заводе без пострадавших). Поэтому здесь второе
сито — МАСШТАБ, тот же, что у стража urgent_guard: либо событие по природе массовое (землетрясение,
цунами, ураган, теракт, крушение самолёта, переворот, объявление войны), либо названо не менее
20 погибших. Прогноз беды («возможно землетрясение») — не событие.

Модуль чистый: без сети и без fetch_news (тест test_patrol_world.py).
"""
import re
import time

from urgent_guard import casualties, CASUALTY_FAR

# События, которые массовы по природе: масштаб считать не надо
BIG_EVENT = re.compile(
    r"землетряс|цунами|ураган|тайфун|торнадо|извержени\w*\s+вулкан|авиакатастроф|"
    r"(?:крушени|падени)\w*\s+(?:пассажирск\w+\s+)?самол|теракт|массов\w+\s+(?:расстрел|стрельб)|"
    r"государственн\w+\s+переворот|попытк\w+\s+переворот|объявил\w*\s+войну|ядерн\w+\s+(?:удар|взрыв|авари)|"
    r"earthquake|tsunami|hurricane|typhoon|tornado|volcan\w*\s+erupt|eruption|plane\s+crash|airliner|"
    r"terror(?:ist)?\s+attack|mass\s+shooting|massacre|\bcoup\b|declares?\s+war|nuclear\s+(?:strike|blast|accident)|"
    r"terremoto|hurac[aá]n|tif[oó]n|atentado|golpe\s+de\s+estado|declara\s+la\s+guerra|"
    r"furac[aã]o|tuf[aã]o|golpe\s+de\s+estado|"
    r"s[eé]isme|ouragan|attentat|coup\s+d.[eé]tat", re.I)

# Прогноз и предположение — не событие
FORECAST = re.compile(
    r"возможн|ожида|прогноз|может\s|могут\s|грозит|угроз|не\s+исключ|"
    r"\b(?:may|might|could|expected|forecast|warns?|risk\s+of)\b|podr[ií]a|se\s+espera|pourrait|pode\s", re.I)
HAPPENED = re.compile(
    r"произошл|случил|погиб|пострадал|унёс|унес|обрушил|разрушил|эвакуир|"
    r"\b(?:killed|dead|died|dies|kills)\b|muri[oó]|muertos|mortos|morreu", re.I)

WORLD_CASUALTIES = CASUALTY_FAR     # 20 погибших — как у стража чужого срочного

MAX_AGE_MS = 90 * 60 * 1000         # событие не старше полутора часов (окно дозора)
URGENT_IN_FEED_MAX = 2              # больше двух «срочно» разом — шум (как cap_urgent)
URGENT_FEED_AGE_MS = 3 * 3600 * 1000
POOLS = ("ru", "en", "es", "pt", "fr")


def world_scale(title):
    """True, если заголовок о массовой беде: по природе события или по числу погибших."""
    t = title or ""
    if FORECAST.search(t) and not HAPPENED.search(t):
        return False
    return bool(BIG_EVENT.search(t)) or casualties(t) >= WORLD_CASUALTIES


def is_world_urgent(titles):
    """Событие по заголовкам редакций: достаточно ОДНОГО заголовка с масштабом."""
    return any(world_scale(t) for t in titles)


def pick_lead(items):
    """Карточка-«голос» события: первая по времени публикации (кто сообщил раньше всех)."""
    dated = [i for i in items if i.get("publishedAt")]
    return min(dated or items, key=lambda i: i.get("publishedAt") or 0)


def to_card(event, now_ms):
    """Карточка ленты для события дозора; None, если язык не наш или нет заголовка/ссылки."""
    items = [i for i in event["items"] if i.get("title") and i.get("url")]
    if not items:
        return None
    lead = pick_lead(items)
    lang = (lead.get("language") or "").lower()
    if lang not in POOLS:
        return None
    return {
        "title": lead["title"],
        "summary": (lead.get("summary") or "")[:400],
        "url": lead["url"],
        "imageUrl": lead.get("imageUrl"),
        "source": lead.get("source", ""),
        "country": lead.get("country", ""),
        "category": "URGENT",
        "priority": 2,
        "scope": "world",
        "language": lang,
        "publishedAt": lead.get("publishedAt") or now_ms,
        "patrol": True,
        "patrolAt": now_ms,
        "patrolSources": ", ".join(sorted(event.get("families") or []))[:200],
    }


def merge(items, card, same_event, now_ms):
    """Добавляет карточку первой, если такого события в ленте нет и «срочных» там не больше двух.

    Возвращает (новый список, причина|None): причина — строка, если карточка не добавлена.
    """
    for x in items:
        if isinstance(x, dict) and same_event(x, card):
            return items, "событие уже в ленте"
    urgent = [x for x in items if isinstance(x, dict)
              and x.get("category") in ("URGENT", "URGENT_LOCAL_ONLY")
              and now_ms - (x.get("publishedAt") or 0) <= URGENT_FEED_AGE_MS]
    if len(urgent) >= URGENT_IN_FEED_MAX:
        return items, f"в ленте уже {len(urgent)} срочных"
    return [card] + [x for x in items if isinstance(x, dict)], None


def publish(card, db, same_event, now_ms):
    """Кладёт карточку в /news/<язык>/items атомарно (транзакция); возвращает (опубликовано, причина).

    Разбор ленты пишет тот же узел целиком, поэтому правка идёт транзакцией: если разбор успел
    записаться между чтением и записью, транзакция повторится на свежих данных. Пустой узел не
    трогаем: ленту создаёт только разбор.
    """
    ref = db.reference(f"/news/{card['language']}/items")
    out = {}

    def update(cur):
        if isinstance(cur, dict):
            cur = list(cur.values())
        if not cur:
            out["why"] = "лента пула пуста"
            return cur
        new, why = merge(cur, card, same_event, now_ms)
        out["why"] = why
        return cur if why else new

    ref.transaction(update)
    return out.get("why") is None, out.get("why")
