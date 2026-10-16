# -*- coding: utf-8 -*-
"""«Срочно» вне «Местных» только с масштабом (журнал J38, 15.10.2026).

Случай: сель в Кашкадарье с одной жертвой (Gazeta.uz, scope=pool, URGENT_LOCAL_ONLY,
priority=2) попал в шторку, строку и карусель читателя в Бишкеке. Тест — на класс:
любая беда местного масштаба × любой язык × обе чужие полки; и обратное — настоящая
беда и свой дом остаются срочными.
"""
import contextlib
import io
import sys

from urgent_guard import final_urgent_guard, foreign_small_urgent, final_prepared_guard, prepared_material, personnel_change, final_personnel_guard

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


def card(title, scope="pool", cat="URGENT", prio=2, summary="", **kw):
    return {"title": title, "summary": summary, "scope": scope, "category": cat,
            "priority": prio, "source": "t", **kw}


# тот самый случай
sel = card("Пассажир Damas погиб в Кашкадарье во время схода селя", cat="URGENT_LOCAL_ONLY")
check("сель, URGENT_LOCAL_ONLY на полке соседей — снимается", foreign_small_urgent(sel))
check("то же в «Мировых»", foreign_small_urgent(card(sel["title"], scope="world", cat="URGENT_LOCAL_ONLY")))
check("«только дома» вне дома — всегда, о чём бы ни было", foreign_small_urgent(
    card("Землетрясение в Японии", scope="world", cat="URGENT_LOCAL_ONLY")))

# класс: беда района, один и тот же вывод на всех языках
small = [
    "Один человек погиб при сходе селя в Кашкадарье",
    "Паводок затопил улицу в соседнем городе, погиб мужчина",
    "Пожар в жилом доме, погибла женщина",
    "ДТП на трассе, погиб водитель",
    "One person killed as flood hits village",
    "Wildfire kills one near Portland",
    "Un muerto por inundación en un pueblo",
    "Incendio en un edificio deja un fallecido",
    "Acidente na rodovia deixa um morto",
    "Un mort dans l'incendie d'un immeuble",
]
for t in small:
    for scope in ("pool", "world"):
        check(f"{scope}: {t[:40]}", foreign_small_urgent(card(t, scope=scope)))

# обратное: масштаб остаётся срочным
big = [
    ("Землетрясение магнитудой 7,1 в Турции", "pool"),
    ("Теракт в метро, погибли 12 человек", "world"),
    ("Hurricane makes landfall in Florida", "world"),
    ("Floods kill dozens in Nepal", "world"),
    ("Наводнение унесло жизни 25 человек", "world"),
    ("Сель сошёл в Узбекистане, погибли 6 человек", "pool"),
    ("Terremoto sacude Chile", "pool"),
    ("Plane crash in Kazakhstan, 40 dead", "pool"),
]
for t, scope in big:
    check(f"остаётся срочным: {t[:40]}", not foreign_small_urgent(card(t, scope=scope)))
check("дом: сель на «Местных» остаётся", not foreign_small_urgent(card(small[0], scope="local")))
check("дом: URGENT_LOCAL_ONLY на «Местных» остаётся", not foreign_small_urgent(
    card(sel["title"], scope="local", cat="URGENT_LOCAL_ONLY")))
check("жизненно важное не трогаем", not foreign_small_urgent(card(small[0], scope="pool", vital=True)))
check("несрочное не трогаем", not foreign_small_urgent(card(small[0], cat="NEWS")))
check("число в тексте статьи (не в заголовке) считается",
      not foreign_small_urgent(card("Сель в Кашкадарье", scope="pool", summary="Погибли 7 человек.")))

# страж: снимает метку и приоритет, карточку не убирает
items = [dict(sel), card("Землетрясение в Японии", scope="world"), card(small[0], scope="local")]
with contextlib.redirect_stdout(io.StringIO()):
    out = final_urgent_guard(items, "ru")
check("страж: карточка осталась в ленте", len(out) == 3)
check("страж: категория снята", out[0]["category"] == "NEWS")
check("страж: приоритет не выше 1", out[0]["priority"] <= 1)
check("страж: настоящая беда не тронута", out[1]["category"] == "URGENT" and out[1]["priority"] == 2)
check("страж: дом не тронут", out[2]["category"] == "URGENT" and out[2]["priority"] == 2)


# ── подготовленный без спешки материал не бывает срочным (J48) ──
feat = card("«Первая победа задаёт хорошую ноту»: как Элис Старцева завоевала историческое серебро для России",
            scope="local", cat="URGENT", prio=2)
check("случай 15.10: статья-цитата с «как» — не срочное", prepared_material(feat))
for t in ("«Мы не сдаёмся»: как жители Бишкека спасают старые дворы",
          "Интервью: министр рассказал о планах на зиму",
          "Колонка: почему дорожает хлеб",
          "Разбор: что изменится в налогах с января",
          "Цена победы: как футболист стал тренером",
          "«No nos rendimos»: cómo una familia reconstruyó su casa",
          "«On ne lâche rien»: comment une équipe a gagné le titre",
          "Interview: the mayor on winter plans"):
    for cat, prio in (("URGENT", 2), ("NEWS", 2), ("SPORT", 2)):
        check(f"{t[:36]} [{cat}/{prio}]", prepared_material(card(t, scope="local", cat=cat, prio=prio)))
check("обычная новость момента не трогается", not prepared_material(card("Россиянка завоевала серебро на чемпионате мира", cat="URGENT", prio=2)))
check("«Как сообщает МЧС…» — не разбор", not prepared_material(card("Как сообщает МЧС, в Бишкеке отключат воду", cat="URGENT", prio=2)))
check("приоритет 1 без срочного не трогаем", not prepared_material(card("Интервью: о планах", cat="NEWS", prio=1)))
check("беда остаётся срочной: «Землетрясение: как это было»", not prepared_material(card("Землетрясение: как это было в Бишкеке", cat="URGENT", prio=2)))
check("жертвы остаются: «Взрыв: как погибли трое»", not prepared_material(card("Взрыв: как погибли трое рабочих", cat="URGENT", prio=2)))
check("жизненно важное не снимаем", not prepared_material(card("«Воды не будет»: как отключат воду в районах", cat="URGENT", prio=2, vital=True)))
lst = [dict(feat), card("Землетрясение магнитудой 7", cat="URGENT", prio=2)]
with contextlib.redirect_stdout(io.StringIO()):
    final_prepared_guard(lst, "ru")
check("страж: статья в NEWS, приоритет 1", lst[0]["category"] == "NEWS" and lst[0]["priority"] == 1)
check("страж: землетрясение не тронуто", lst[1]["category"] == "URGENT" and lst[1]["priority"] == 2)

# ── кадровая перестановка чиновника — не срочное (J54) ──
staff = [
    "Заместитель министра освобождён от должности",
    "Заместитель председателя комитета освобожден от занимаемой должности",
    "Первый вице-мэр Бишкека освобождён от должности",
    "Назначен новый заместитель акима области",
    "Чиновник отправлен в отставку",
    "Вице-премьера сняли с должности",
    "Директор департамента уволен с должности",
    "Орун басары кызматынан бошотулду",
    "Deputy minister relieved of his post",
    "Deputy governor dismissed from his post",
    "Viceministro destituido de su cargo",
    "Vice-ministro exonerado do cargo",
    "Sous-préfet relevé de ses fonctions",
    "Заместителя министра уволили",
    "Уволен заместитель акима области",
    "Замглавы района уволен",
    "Уволили заместителя мэра Бишкека",
    "Премьер-министр уволил заместителя",
    "Deputy minister fired",
    "Viceministro despedido",
    "Vice-ministro demitido",
]
for t in staff:
    for cat, prio in (("URGENT", 2), ("URGENT_LOCAL_ONLY", 2), ("NEWS", 2)):
        check(f"{t[:36]} [{cat}/{prio}]", personnel_change(card(t, scope="local", cat=cat, prio=prio)))
check("несрочное с приоритетом 1 не трогаем", not personnel_change(card(staff[0], cat="NEWS", prio=1)))
check("рядовых рабочих не трогаем", not personnel_change(card("Уволили 500 рабочих завода", cat="URGENT")))
check("уход президента остаётся срочным", not personnel_change(card("Президент освобождён от должности", cat="URGENT")))
check("премьер-министр остаётся срочным", not personnel_change(card("Премьер-министр отправлен в отставку", cat="URGENT")))
check("prime minister остаётся срочным", not personnel_change(card("Prime minister dismissed from his post", cat="URGENT")))
check("с жертвами остаётся срочным", not personnel_change(card("Замминистра освобождён от должности после того, как погибли 3 рабочих", cat="URGENT")))
check("жизненно важное не снимаем", not personnel_change(card(staff[0], cat="URGENT", vital=True)))
check("обычная новость не трогается", not personnel_change(card("Землетрясение магнитудой 7", cat="URGENT")))
lst = [card(staff[0], scope="local"), card("Президент освобождён от должности", scope="local"),
       card("Землетрясение магнитудой 7", scope="local")]
with contextlib.redirect_stdout(io.StringIO()):
    final_personnel_guard(lst, "ru")
check("страж: замминистра в NEWS, приоритет 1", lst[0]["category"] == "NEWS" and lst[0]["priority"] == 1)
check("страж: президент не тронут", lst[1]["category"] == "URGENT" and lst[1]["priority"] == 2)
check("страж: землетрясение не тронуто", lst[2]["category"] == "URGENT" and lst[2]["priority"] == 2)

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
