# -*- coding: utf-8 -*-
"""Официальные каналы тревог: разбор настоящих страниц (Курск, Севастополь, 15.10.2026) и решения."""
import sys
from datetime import datetime, timezone

import official_alerts as O

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


def ms(s):
    return int(datetime.fromisoformat(s).astimezone(timezone.utc).timestamp() * 1000)


kursk = O.parse_posts(open("testdata/tg_gubernator_46.html", encoding="utf-8").read())
sev = O.parse_posts(open("testdata/tg_razvozhaev.html", encoding="utf-8").read())
check("Курск: страница разобрана", len(kursk) >= 15 and all(p["post"].startswith("gubernator_46/") for p in kursk))
check("Севастополь: страница разобрана", len(sev) >= 6)

# настоящие посты оперштаба Курской области 14–15.10.2026
t = lambda p: p["text"]
check("«ракетная опасность» — тревога", any(O.ALERT.search(t(p)) and not O.CANCEL.search(t(p)) and "ракетная" in t(p).lower() for p in kursk))
check("«Отбой» — отбой, не тревога", any(O.CANCEL.search(t(p)) for p in kursk))
check("«опасность атаки БПЛА» — тревога", any("опасность атаки БПЛА" in t(p) and O.ALERT.search(t(p)) for p in kursk))
check("«Внимание всем! Воздушная тревога!» (Севастополь) — тревога", any(O.ALERT.search(t(p)) for p in sev))
check("благоустройство — не тревога", not any(O.ALERT.search(t(p)) for p in sev if "переулок" in t(p)))

# решение «тревога сейчас»: последний относящийся к делу пост
def post(text, when):
    return {"post": "x/1", "text": text, "ts": ms(when)}

a = post("⚠️ Курская область: ракетная опасность!", "2026-10-14T18:51:00+00:00")
c = post("🟢 Курская область: внимание! Отбой ракетной опасности.", "2026-10-14T19:52:00+00:00")
now = ms("2026-10-14T19:00:00+00:00")
check("тревога без отбоя, свежая → тревога", O.current_alert([a], now) is a)
check("после отбоя тревоги нет", O.current_alert([a, c], ms("2026-10-14T20:00:00+00:00")) is None)
b = post("⚡️ Курская область: опасность атаки БПЛА.", "2026-10-14T21:00:00+00:00")
check("новая тревога после отбоя поднимает снова", O.current_alert([a, c, b], ms("2026-10-14T21:10:00+00:00")) is b)
check("тревога старше окна без отбоя уже не «сейчас»", O.current_alert([a], ms("2026-10-14T21:00:00+00:00")) is None)
check("пост без времени игнорируем", O.current_alert([{"post": "x/2", "text": "ракетная опасность", "ts": 0}], now) is None)
check("итоги ночи — не тревога", not O.ALERT.search("Сбиты 12 беспилотников над областью за прошедшую ночь"))
check("«отражена атака» — итог, не тревога", not O.ALERT.search("Отражена атака беспилотников на Москву"))

# карточка и сбой канала
item = O.to_item("gubernator_46", a)
check("карточка: источник, город, официальная", item["source"] == "Оперштаб Курской области" and item["_city"] == "RU-KRS" and item["official"])
check("карточка: эмодзи в начале заголовка срезан", item["title"].startswith("Курская область"))
def fetcher(h):
    if h == "razvozhaev":
        raise RuntimeError("down")
    return [a] if h == "gubernator_46" else []
got = O.alert_items(a["ts"] + 60_000, fetcher=fetcher)
check("сбой одного канала не роняет остальные", [x["source"] for x in got] == ["Оперштаб Курской области"])

print(f"\n{ok} ✓, {fail} ✗")
sys.exit(1 if fail else 0)
