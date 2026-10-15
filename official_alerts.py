# -*- coding: utf-8 -*-
"""Официальные каналы тревог по городам (15.10.2026).

Владелец: «ищи региональные каналы глав регионов и местных МЧС, проверяя чей канал по
заголовку». Проверка шла по ТРЁМ признакам, а не по одной «собачке» (урок @ntv 28.08.2026):
  1. заголовок канала (og:title) назвал именно того, кого мы думаем;
  2. канал свежий (последний пост не старше суток);
  3. в постах действительно есть тревоги, а не только благоустройство.
Так отсеялись: @vvgladkov («Настоящий Гладков» пишет про посольство в Абхазии, не губернатор
Белгородской области), каналы МЧС Брянской, Ульяновской, Нижегородской, Свердловской областей
и Краснодара (последний пост месяцы назад: «МЧС теперь в MAX» — у MAX нет открытого чтения),
Минниханов, Дюмин, Гусев, Куйвашев (посты 2022–2025).

Канал глав регионов и МЧС можно взломать, как и эфир (2022–2023: ложные тревоги по радио и ТВ),
поэтому здесь они дают ПОДТВЕРЖДЕНИЕ в лестнице уверенности (vital_city.alert_level), а не
право будить громко в одиночку: официальный канал сам по себе — уровень 2, с независимым
источником — уровень 3.

Модуль: разбор страницы t.me/s/<канал> (чистая функция parse_posts), решение «тревога сейчас»
(current_alert) и запрос (fetch). Тест — на настоящих страницах каналов (testdata/tg_*.html).
"""
import html as _html
import re
from datetime import datetime, timezone

# handle → (издание, id города из vital_city.CITIES, область канала).
# Проверены 15.10.2026 (заголовок + свежесть + тревоги в постах). Добавлять только после такой же проверки.
CHANNELS = {
    "gubernator_46": ("Оперштаб Курской области", "RU-KRS"),
    "razvozhaev": ("Развожаев (Севастополь)", "RU-SEV"),
    "mos_sobyanin": ("Собянин (Москва)", "RU-MOW"),
}

# Что считаем тревогой. Только начало тревоги: «отражена атака», «сбито N беспилотников» —
# это итоги, а не тревога.
ALERT = re.compile(
    r"(?:ракетн\w+|авиационн\w+|беспилотн\w+)\s+опасност|воздушн\w+\s+тревог|"
    r"опасност\w*\s+(?:атаки\s+)?(?:бпла|беспилотник)|угроз\w+\s+(?:атаки\s+)?(?:бпла|беспилотник)|"
    r"режим\w*\s+[«\"]?ковёр|режим\w*\s+[«\"]?ковер",
    re.I,
)
CANCEL = re.compile(r"\bотбой\b", re.I)

WINDOW_MS = 90 * 60 * 1000       # тревога старше полутора часов без отбоя — уже не «сейчас»


def parse_posts(page):
    """[{post, text, ts}] из страницы t.me/s/<канал>; ts в мс, 0 — время не указано."""
    out = []
    for m in re.finditer(r'<div class="tgme_widget_message_wrap.*?(?=<div class="tgme_widget_message_wrap|\Z)',
                         page, flags=re.S):
        b = m.group(0)
        post = re.search(r'data-post="([^"]+)"', b)
        t = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', b, re.S)
        d = re.search(r'<time datetime="([^"]+)"', b)
        if not post or not t:
            continue
        text = re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", t.group(1)))).strip()
        ts = 0
        if d:
            try:
                ts = int(datetime.fromisoformat(d.group(1)).astimezone(timezone.utc).timestamp() * 1000)
            except ValueError:
                ts = 0
        out.append({"post": post.group(1), "text": text, "ts": ts})
    return out


def current_alert(posts, now_ms):
    """Последняя тревога, если после неё нет отбоя и она не старше окна; иначе None.

    Решает ПОСЛЕДНИЙ относящийся к делу пост: «Отбой ракетной опасности» после тревоги гасит её,
    а тревога после отбоя поднимает снова.
    """
    last = None
    for p in sorted((p for p in posts if p["ts"]), key=lambda p: p["ts"]):
        if CANCEL.search(p["text"]):
            last = ("cancel", p)
        elif ALERT.search(p["text"]):
            last = ("alert", p)
    if not last or last[0] != "alert":
        return None
    return last[1] if 0 <= now_ms - last[1]["ts"] <= WINDOW_MS else None


def to_item(handle, post):
    """Карточка ленты из поста официального канала."""
    source, city = CHANNELS[handle]
    text = re.sub(r"^[^\wА-Яа-я«\"]+", "", post["text"])
    return {
        "title": text[:140],
        "summary": text[:400],
        "url": f"https://t.me/{post['post']}",
        "source": source,
        "publishedAt": post["ts"],
        "language": "ru",
        "scope": "pool",
        "category": "NEWS",
        "priority": 2,
        "imageUrl": "",
        "official": True,
        "_city": city,
    }


def fetch(handle, timeout=15):
    import requests
    r = requests.get(f"https://t.me/s/{handle}", timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return parse_posts(r.text)


def alert_items(now_ms, fetcher=fetch):
    """Карточки о тревогах «сейчас» по всем проверенным каналам; сбой канала не роняет остальные."""
    out = []
    for handle in CHANNELS:
        try:
            p = current_alert(fetcher(handle), now_ms)
        except Exception as e:
            print(f"  ✗ официальный канал {handle}: {type(e).__name__}")
            continue
        if p:
            out.append(to_item(handle, p))
    return out
