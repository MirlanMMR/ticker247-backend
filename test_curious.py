"""Добор «Интересного» (curious.py), 09.10.2026."""
import sys
from curious import pick_topup

ok = fail = 0
def check(name, got, want):
    global ok, fail
    if got == want: ok += 1
    else: fail += 1; print(f"  ✗ {name}: получили {got}, ждали {want}")

NOW = 1_800_000_000_000
INT = {"A", "B", "C", "D", "E", "F"}
isint = lambda x: x.get("source") in INT
def c(src, i=1, **k):
    d = dict(source=src, url=f"u/{src}/{i}", title="Учёные нашли необычную находку в ледниках",
             summary="Подробный текст о находке. " * 8, publishedAt=NOW - 3600_000, imageUrl="https://x/y.jpg")
    d.update(k); return d

have = [c("A"), c("B")]
cands = have + [c("C"), c("D"), c("E"), c("F")]
got = pick_topup(have, cands, isint, NOW)
check("добираем до 5 источников", sorted(x["source"] for x in got), ["C", "D", "E"])
check("уже 5 — не добираем", pick_topup([c(s) for s in "ABCDE"], cands, isint, NOW), [])
check("старше 48 часов не берём", pick_topup(have, [c("C", publishedAt=NOW - 49 * 3600_000)], isint, NOW), [])
check("список «лучшие города» не берём", pick_topup(have, [c("C", title="America's Best Small Cities in 2026, Ranked")], isint, NOW), [])
check("«10 фактов» не берём", pick_topup(have, [c("C", title="10 вещей, которые вы забыли о сериале")], isint, NOW), [])
check("анонс выпуска не берём", pick_topup(have, [c("C", title="A future worth building. What to expect in the new issue of Positive News")], isint, NOW), [])
check("короткий текст не берём", pick_topup(have, [c("C", summary="Коротко")], isint, NOW), [])
check("источник уже в ленте — второй не берём", pick_topup(have, [c("A", 2)], isint, NOW), [])
check("не из «любопытного» не берём", pick_topup(have, [c("Z")], isint, NOW), [])
check("по одной от источника, с фото вперёд",
      [x["url"] for x in pick_topup([c("A")], [c("C", 1, imageUrl=None), c("C", 2), c("D", 1, imageUrl=None)], isint, NOW, target=3)],
      ["u/C/2", "u/D/1"])
check("плохая по внешнему признаку (bad) не берём", pick_topup(have, [c("C")], isint, NOW, bad=lambda x: True), [])

from curious import is_curious_content as CC
# Содержание решает, а не только источник (09.10.2026, атомная бомба в Xataka)
check("атомная бомба США — не любопытное", CC({"title": "Ученые, работающие над новой атомной бомбой США, завершили ключевой этап"}), False)
check("VEVOR (реклама Futura) — не любопытное", CC({"title": "VEVOR casse les prix du mobilier de jardin avec ce lot de deux fauteuils"}), False)
check("en: nuclear weapon — не любопытное", CC({"title": "US completes key stage of new nuclear weapon ahead of schedule"}), False)
check("убит/погиб — не любопытное", CC({"title": "Из-за пожара погибли двое"}), False)
check("светящийся паук — любопытное", CC({"title": "Эта гигантская морская паук освещает глубины океана"}), True)
check("ядерный синтез (наука) — любопытное", CC({"title": "Учёные впервые получили термоядерный синтез с избытком энергии"}), True)
check("древняя ложка — любопытное", CC({"title": "A 3,000-year-old spoon was found inside a glacier in Norway"}), True)
check("«Саша» не «САУ»/«войн»: слово-начало", CC({"title": "Саша открыл кафе в старой башне"}), True)

check("Нобелевская премия — новость дня", CC({"title": "Нобелевскую премию по литературе 2026 года присудили канадской писательнице"}), False)
check("некролог — новость дня", CC({"title": "Muere la mujer de la NASA que cambió para siempre lo que significaba ser programador"}), False)
check("депутаты хотят ограничить — политика", CC({"title": "Caféine, sucre, taurine, les députés veulent limiter les boissons énergisantes"}), False)
check("ANSM alerte — предупреждение ведомства", CC({"title": "Anti-diabète : l'ANSM alerte sur des effets indésirables parfois graves"}), False)
check("падение численности дикой природы — оставляем", CC({"title": "Глобальное сокращение численности дикой природы: в среднем на 73%"}), True)

from curious import is_longread_url as LR
check("Guardian ng-interactive — лонгрид", LR({"url": "https://www.theguardian.com/news/ng-interactive/2026/oct/08/a-death-a-plagiarism-scandal"}), True)
check("long-read — лонгрид", LR({"url": "https://www.theguardian.com/news/2026/oct/08/the-long-read/x"}), True)
check("NYT interactive — лонгрид", LR({"url": "https://www.nytimes.com/interactive/2026/10/08/world/story.html"}), True)
check("обычная новость — не лонгрид", LR({"url": "https://www.bbc.com/russian/articles/c933xexyx2k2o"}), False)
check("слово magazine в домене — не лонгрид", LR({"url": "https://smithsonianmag.com/smart-news/glacier-spoon/"}), False)

check("беглец — не любопытное", CC({"title": "Chef living quietly in San Diego revealed to be violent fugitive on the run"}), False)
check("похитила собаку — не любопытное", CC({"title": "Cae mujer que secuestró a una perrita en calles de Iztapalapa"}), False)
check("мошенничество — не любопытное", CC({"title": "Мошенники придумали новую схему обмана пенсионеров"}), False)
check("кража века — не любопытное", CC({"title": "Кража в музее: у грабителей нашли картину"}), False)

print(f"пройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
