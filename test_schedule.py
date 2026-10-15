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

# ── у каждого пула три слота — в дневных часах ОБОИХ главных поясов (8 поясов по три часа) ──
check("восемь поясов по три часа, центры через три часа", S.BANDS == (-9, -6, -3, 0, 3, 6, 9, 12))
for pool in S.ACTIVE_POOLS:
    hours = sorted(h for h, ps in S.SLOTS_UTC.items() if pool in ps)
    mains = S.POOL_MAIN_BANDS[pool]
    check(f"{pool}: ровно три слота в сутки", len(hours) == 3)
    check(f"{pool}: два главных пояса, оба из восьми", len(mains) == 2 and all(b in S.BANDS for b in mains))
    for b in mains:
        locs = [S.band_hour(h, b) for h in hours]
        check(f"{pool}: все слоты в дневных часах пояса {b:+d} ({S.DAY_FROM}:00–{S.DAY_TO}:00): {locs}",
              all(S.DAY_FROM <= l <= S.DAY_TO for l in locs))
        check(f"{pool}: пояс {b:+d} получает слоты от полудня до вечера (не позже 12:00 первый, не раньше 16:00 последний)", min(locs) <= 12 and max(locs) >= 16)
    # слоты по кругу суток не чаще чем раз в два часа и не реже чем раз в шесть (по UTC от слота к слоту)
    gaps = [(hours[(i + 1) % 3] - hours[i]) % 24 for i in range(3)]
    check(f"{pool}: промежутки между слотами {gaps} (не меньше 2 ч); ночной провал один", min(gaps) >= 2 and sum(gaps) == 24)
check("всего 15 пул-прогонов в сутки (3 × 5), как с 9 октября", sum(len(ps) for ps in S.SLOTS_UTC.values()) == 15)
check("в одном запуске не больше двух пулов", all(len(ps) <= 2 for ps in S.SLOTS_UTC.values()))
check("«полки стран» — в часе, где есть слот", S.COUNTRY_SHELVES_HOUR in S.SLOTS_UTC)

# ── внешний планировщик: worker.js и wrangler.toml совпадают с таблицей ──
import json
wt = open(os.path.join(HERE, "scheduler", "wrangler.toml"), encoding="utf-8").read()
wcrons = re.findall(r'crons = \[(.*?)\]', wt, re.S)
check("wrangler.toml: один триггер «2 * * * *» (бесплатный тариф: не больше 5 триггеров)", len(wcrons) == 1 and re.findall(r'"([^"]+)"', wcrons[0]) == ["2 * * * *"])
wj = open(os.path.join(HERE, "scheduler", "worker.js"), encoding="utf-8").read()
slots_js = json.loads(re.search(r"const SLOTS = (\{.*?\});", wj, re.S).group(1))
check("worker.js: таблица слотов совпадает с schedule_pools.SLOTS_UTC", {int(k): tuple(v) for k, v in slots_js.items()} == S.SLOTS_UTC)
check("worker.js: слот выбирается по часу срабатывания", "getUTCHours()" in wj)
check("worker.js: час «полок стран» совпадает", f"const SHELVES_HOUR = {S.COUNTRY_SHELVES_HOUR};" in wj)
check("worker.js: запуск через workflow_dispatch с from_scheduler (шлюз свежести работает)", '"fetch.yml"' in wj and 'from_scheduler: "true"' in wj and "inputs" in wj)
check("fetch.yml: вход from_scheduler не обходит шлюз свежести", "!inputs.from_scheduler" in wf)
check("секрет токена не лежит в репозитории", "ghp_" not in wj and "github_pat_" not in wj and "github_pat_" not in wt)

# ── разбор строки cron ──
check("cron слота fr+pt → fr, pt", S.pools_for_cron("7 12 * * *") == ("fr", "pt"))
check("запасной запуск того же слота — те же пулы", S.pools_for_cron("37 12 * * *") == S.pools_for_cron("7 12 * * *"))
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
