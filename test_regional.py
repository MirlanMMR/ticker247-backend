# -*- coding: utf-8 -*-
"""Областные новости: склейка через границу областей и отбор по кругу.

Случаи — из разбора 04.10.2026 («сто новостей превращаются в ноль»): разные
события с шаблонным заголовком склеивались и выбрасывались как «общая лента».
"""
import sys

from feed_gate import regions_agree, pick_regionals

ok = fail = 0


def check(name, got, want=True):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}: получили {got!r}, ждали {want!r}")


def n(title, region, **kw):
    return {"title": title, "region": region, **kw}


# ─── Разные события через границу областей НЕ склеиваем ─────────────────────
check("пожар в Новосибирске ≠ пожар в Северодвинске",
      regions_agree(n("Пожар вспыхнул в двухэтажном здании на Грибоедова", "RU-NVS"),
                    n("Пожар в Северодвинске: очевидцы опубликовали видео", "RU-ARK")), False)
check("прогноз погоды для разных городов",
      regions_agree(n("Previsão do tempo hoje para o Recife (PE): sol", "BR-PE"),
                    n("Previsão do tempo hoje para São Gonçalo (RJ): muito", "BR-RJ")), False)
check("«как смотреть» разные матчи",
      regions_agree(n("How to watch Ravens vs. Titans NFL Week 4", "US-MD"),
                    n("How to watch Bengals vs. Jaguars NFL Week 4", "US-OH")), False)
check("«vota em» разные кандидаты",
      regions_agree(n("Pimenta (PT) vota em Santa Maria", "BR-RS"),
                    n("Maria Bona (PCO) vota em Rio de Contas", "BR-BA")), False)
check("прогноз First Alert двух штатов",
      regions_agree(n("First Alert Weather: Off and on showers Sunday", "US-AL"),
                    n("First Alert Forecast: Showers are possible this afternoon", "US-CT")), False)
check("заголовки без имён собственных через границу не склеиваем",
      regions_agree(n("пожар в частном доме, никто не пострадал", "RU-NVS"),
                    n("пожар в частном доме, пострадавших нет", "RU-OMS")), False)

# ─── Одно событие через границу областей — склеиваем ────────────────────────
check("слово в слово у сестринских станций",
      regions_agree(n("Armed 18-year-old shot, killed by Newnan police officer", "US-FL"),
                    n("Armed 18-year-old shot, killed by Newnan police officer", "US-GA")), True)
check("слово в слово, без заглавных",
      regions_agree(n("пожар в частном доме, никто не пострадал", "RU-NVS"),
                    n("Пожар в частном доме — никто не пострадал!", "RU-OMS")), True)
check("то же событие другими словами, имена совпадают",
      regions_agree(n("Coast Guard searching for missing jet heading to Louisiana", "US-LA"),
                    n("Coast Guard searching for plane with 6 aboard", "US-MA")), True)

# ─── Внутри области и без области проверка ничего не меняет ─────────────────
check("одна область",
      regions_agree(n("Пожар в Новосибирске", "RU-NVS"), n("Пожар в Омске", "RU-NVS")), True)
check("одна без области",
      regions_agree(n("Пожар в Новосибирске", ""), n("Пожар в Омске", "RU-OMS")), True)

# ─── Отбор: устаревшие — ДО потолка, свежие вперёд ──────────────────────────
H = 3600 * 1000
NOW = 1_000_000 * H


def r(i, region, age_h, prio=0):
    return n(f"Новость {i}", region, publishedAt=NOW - age_h * H, priority=prio)


rows = [r(1, "A", 50), r(2, "A", 49), r(3, "A", 2), r(4, "A", 1), r(5, "B", 40)]
picked, per, stale = pick_regionals(rows, NOW, cap_per_region=2, total=300)
check("устаревшие не занимают места: взяты две свежие области A", sorted(x["title"] for x in picked if x["region"] == "A"),
      ["Новость 3", "Новость 4"])
check("устарело посчитано", stale, 3)
check("в областях без свежего пусто", "B" in per, False)

many = [r(i, "A", 60) for i in range(10)] + [r(100 + i, "B", 1) for i in range(5)]
picked, per, stale = pick_regionals(many, NOW, cap_per_region=16, total=4)
check("потолок 4: все четыре места у свежих", [x["region"] for x in picked], ["B"] * 4)

rows = [r(i, "A", 5) for i in range(6)] + [r(10 + i, "B", 5) for i in range(6)]
picked, per, stale = pick_regionals(rows, NOW, cap_per_region=16, total=6)
check("по кругу: поровну между областями", per, {"A": 3, "B": 3})

rows = [r(1, "A", 10, prio=0), r(2, "A", 20, prio=2), r(3, "A", 1, prio=0)]
picked, per, stale = pick_regionals(rows, NOW, cap_per_region=16, total=300)
check("внутри области: важное, потом свежее",
      [x["title"] for x in picked], ["Новость 2", "Новость 3", "Новость 1"])

rows = [r(i, "A", 1) for i in range(30)]
picked, per, stale = pick_regionals(rows, NOW, cap_per_region=16, total=300)
check("потолок на область", per, {"A": 16})

picked, per, stale = pick_regionals([], NOW, 16, 300)
check("пусто — пусто", (picked, per, stale), ([], {}, 0))

# без даты — не считаем устаревшим (как в эталоне новости)
picked, per, stale = pick_regionals([n("Без даты", "A")], NOW, 16, 300)
check("без даты проходит", len(picked), 1)

print(f"\n{ok} ✓, {fail} ✗")
sys.exit(1 if fail else 0)
