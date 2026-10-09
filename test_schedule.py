# -*- coding: utf-8 -*-
"""Расписание по часовым поясам (09.10.2026): таблица слотов, строки cron в fetch.yml, режим POOLS.

Замок на три вещи, которые ломались молча: (1) строка расписания, которой нет в таблице, стала
бы полным прогоном всех пулов (в 5 раз дороже); (2) пул, у которого пропал слот, оставался
бы с лентой двенадцатичасовой давности; (3) слот, сдвинутый на ночь по местному времени,
обновлял бы читателю то, чего ещё нет — издания просыпаются к 9–10 утра.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import schedule_pools as S

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


HERE = os.path.dirname(os.path.abspath(__file__))
wf = open(os.path.join(HERE, ".github", "workflows", "fetch.yml"), encoding="utf-8").read()
crons = re.findall(r"^\s+- cron: '([^']+)'", wf, re.M)

# ── fetch.yml и таблица совпадают ──
want = [c for c, _ in S.cron_lines()]
check("строки cron в fetch.yml совпадают с таблицей слотов (порядок и состав)", crons == want)
check("нет дублей строк cron", len(set(crons)) == len(crons))
check("каждая строка cron известна таблице", all(S.pools_for_cron(c) for c in crons))
check("незнакомая строка cron → пусто (workflow упадёт, а не запустит все пулы)", S.pools_for_cron("0 */2 * * *") == ())
check("каждый слот стоит дважды (запасной запуск)", all(crons.count(f"{m} {h} * * *") == 1 for h in S.SLOTS_UTC for m in S.CRON_MINUTES) and len(crons) == 2 * len(S.SLOTS_UTC))
check("минуты запуска не :00 (GitHub задерживает их сильнее всего)", all(int(c.split()[0]) != 0 for c in crons))
check("минуты — те, что в таблице", {int(c.split()[0]) for c in crons} == set(S.CRON_MINUTES))

# ── у каждого пула три слота — утро, обед, после обеда по местному времени ──
for pool in S.ACTIVE_POOLS:
    hours = sorted(h for h, ps in S.SLOTS_UTC.items() if pool in ps)
    locs = [S.local_hour(h, pool) for h in hours]
    check(f"{pool}: ровно три слота в сутки", len(hours) == 3)
    for want_h, name in ((9, "утро"), (13, "обед"), (17, "после обеда")):
        near = [l for l in locs if abs(l - want_h) <= S.DST_TOLERANCE_H]
        check(f"{pool}: есть слот «{name}» (≈{want_h}:00 местного, допуск перехода на зимнее время)", len(near) == 1)
    check(f"{pool}: ни одного слота ночью (с 21:00 до 07:00 местного)", all(7 <= l <= 20 for l in locs))
    # утро строго не раньше 8:00 даже после перехода на зимнее время (издания просыпаются к 9–10)
    check(f"{pool}: утренний слот не раньше 8:00 при зимнем времени", min((l - S.DST_TOLERANCE_H) for l in locs) >= 8)

# ── разбор строки cron ──
check("cron слота ru+fr → ru, fr", S.pools_for_cron("7 7 * * *") == ("ru", "fr"))
check("запасной запуск того же слота — те же пулы", S.pools_for_cron("37 7 * * *") == S.pools_for_cron("7 7 * * *"))
check("«полки стран» — один раз в сутки (первый слот)", [h for h in S.SLOTS_UTC if S.wants_country_shelves(f"7 {h} * * *")] == [S.COUNTRY_SHELVES_HOUR])

# ── режим POOLS ──
check("POOLS пусто → все пулы", S.selected_pools("") == S.ACTIVE_POOLS and S.selected_pools(None) == S.ACTIVE_POOLS)
check("POOLS='ru,fr'", S.selected_pools("ru,fr") == ("ru", "fr"))
check("POOLS в любом порядке и регистре", S.selected_pools(" FR , ru ") == ("ru", "fr"))
check("незнакомые имена отброшены, остальное работает", S.selected_pools("xx,es") == ("es",))
check("только незнакомые имена → все (а не ничего)", S.selected_pools("xx") == S.ACTIVE_POOLS)
check("разделитель «;»", S.selected_pools("pt;en") == ("en", "pt"))

# ── шлюз свежести по пулам ──
check("свежий пул пропущен, старый обновлён", S.stale_pools(("ru", "fr"), {"ru": 10, "fr": 90}, 25) == ("fr",))
check("все свежие → пусто (запуск выходит, ничего не потратив)", S.stale_pools(("ru", "fr"), {"ru": 5, "fr": 24.9}, 25) == ())
check("ровно на пороге — обновляем", S.stale_pools(("ru",), {"ru": 25}, 25) == ("ru",))
check("возраст неизвестен → обновляем (дешевле ошибки)", S.stale_pools(("ru",), {"ru": None}, 25) == ("ru",))
check("запасной запуск через 30 минут после первого видит свежую ленту (первый писал ~20 мин назад)", S.stale_pools(("ru",), {"ru": 10}, 25) == ())

# ── patrol.yml рядом: полчаса, круглосуточно ──
pw = open(os.path.join(HERE, ".github", "workflows", "patrol.yml"), encoding="utf-8").read()
check("дозор: расписание каждые полчаса в :07 и :37", "- cron: '7,37 * * * *'" in pw)
check("дозор: своя очередь, не ждёт разбор", "group: ticker-patrol" in pw and "group: ticker-fetch" in wf)
check("в разборе больше нет холостого цикла ожидания (sleep 708)", "sleep 708" not in wf and "patrol.py" not in wf)

# ── режим POOLS действительно подключён в конвейере ──
fn = open(os.path.join(HERE, "fetch_news.py"), encoding="utf-8").read()
check("fetch_news: пулы берутся из POOLS", 'selected_pools(os.environ.get("POOLS")' in fn)
check("fetch_news: цикл по пулам пропускает чужие", "if lang not in run_pools:" in fn)
check("fetch_news: шлюз свежести по каждому пулу", "stale_pools(run_pools, ages, FRESH_ENOUGH_MIN)" in fn)
check("fetch_news: без POOLS остаётся прежний шлюз по ru", "elif _feed_is_fresh():" in fn)
check("fetch_news: ручной запуск (FORCE_RUN) шлюз обходит", 'os.environ.get("FORCE_RUN") != "true"' in fn)

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
