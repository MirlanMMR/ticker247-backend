# -*- coding: utf-8 -*-
"""Проверки склейки сюжетов обзора прессы.

Случаи не выдуманы: взяты из ленты русского пула за 28.08.2026, где обзор на
три четверти состоял из Непала.
"""
import sys

from storydedup import same_story

ok = fail = 0


def check(name, got, want=True):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}: получили {got!r}, ждали {want!r}")


def story(title, *urls):
    return {"title": title, "blocks": [{"url": u} for u in urls]}


# ─── Настоящие сюжеты из ленты 28.08.2026 ───────────────────────────────────

NAVOD = story("Наводнение в Непале",
              "sputnik.kg/nepal-deti", "bbc.com/nepal-track",
              "g1.globo/nepal-lago", "eluniversal.mx/nepal",
              "rte.ie/nepal-469", "rfi.fr/nepal-tsunami")
LEDNIK = story("Обрушение ледника в Непале",
               "rfi.fr/nepal-kosmos", "bbc.com/brasil-nepal-tibet",
               "sputnik.kg/nepal-deti")
POGIB = story("Наводнения в Непале: 469 погибших, почти 1000…",
              "rte.ie/nepal-469", "prensalibre.gt/nepal-lavina",
              "bbc.com/brasil-4-voprosa", "france24.fr/nepal-po-minutam")

check("наводнение и ледник — один сюжет (общая статья Sputnik)",
      same_story(NAVOD, LEDNIK))
check("наводнение и 469 погибших — один сюжет (общая статья RTÉ)",
      same_story(NAVOD, POGIB))
# У этих двух общих ссылок нет; спасают два общих корня — «непа» и «навод».
# После склейки обоих с первым все три всё равно сойдутся в один
check("ледник и 469 погибших — разные ссылки, но заголовки выдают",
      same_story(LEDNIK, POGIB), False)

NORWAY = story("Смерть короля Норвегии",
               "g1.globo/harald", "bbcmundo.com/harald")
check("Норвегия и Непал — разные сюжеты", same_story(NAVOD, NORWAY), False)


# ─── Одной общей ссылки достаточно ──────────────────────────────────────────
#
# Статья пишется об одном событии. Попала блоком в два сюжета — сюжеты об
# одном. Прежний порог в ДВЕ ссылки и промахивался ровно на единицу.

check("одна общая ссылка склеивает",
      same_story(story("Один заголовок", "a.com/x", "b.com/y"),
                 story("Совершенно иной", "c.com/z", "a.com/x")))
check("общих ссылок нет и заголовки разные — не склеиваем",
      same_story(story("Выборы в Молдавии", "a.com/1"),
                 story("Погода в Испании", "b.com/2")), False)


# ─── Порог по заголовкам не снижаем ─────────────────────────────────────────
#
# Одного общего корня хватило бы, чтобы склеить всё про одну страну подряд.

check("одного общего слова мало",
      same_story(story("Выборы в Молдавии", "a.com/1"),
                 story("Землетрясение в Молдавии", "b.com/2")), False)
check("двух общих слов достаточно",
      same_story(story("Наводнение в Непале", "a.com/1"),
                 story("Наводнения в Непале унесли жизни", "b.com/2")))


# ─── Мелочи, на которых легко споткнуться ───────────────────────────────────

check("пустые ссылки не считаются общими",
      same_story({"title": "Первый", "blocks": [{"url": ""}]},
                 {"title": "Второй", "blocks": [{"url": ""}]}), False)
check("сюжет без блоков не роняет проверку",
      same_story({"title": "Пустой"}, NAVOD), False)
check("сюжет без заголовка не роняет проверку",
      same_story({"blocks": [{"url": "q.com/1"}]}, NORWAY), False)


# ─── Третий признак: об одном ли говорят САМИ МАТЕРИАЛЫ ─────────────────────
#
# Нужен для сюжетов, собранных из РАЗНЫХ статей об одном событии и названных
# по-разному. Случай из французского пула 28.08.2026: у «Catastrophe au Népal»
# и «Crues meurtrières au Népal» нет ни общей статьи, ни двух общих слов в
# названии — общее слово одно, «Népal». А блоки говорят об одном паводке.
#
# Пороги подобраны по живым данным: у этой пары 14 общих корней и 39%
# пересечения, у ВСЕХ остальных пар во всех пяти пулах — не больше четырёх.

def with_blocks(title, *block_titles):
    """Сюжет с РАЗНЫМИ адресами у блоков.

    Адреса обязаны быть уникальными для каждого сюжета: иначе сработает
    правило общей ссылки, и третий признак так и останется непроверенным.
    На этом я и споткнулся, когда писал проверку.
    """
    key = abs(hash(title))
    return {"title": title,
            "blocks": [{"url": f"{key}/{i}", "title": t}
                       for i, t in enumerate(block_titles)]}


NEPAL_A = with_blocks(
    "Catastrophe au Népal",
    "Crue dévastatrice au Népal : une centaine d'ouvriers disparus",
    "Crue au Népal et au Tibet : les secours face à la montagne",
    "Vidéo : Sur les traces de la crue éclair meurtrière au Népal",
    "Rupture de glacier au Népal : les images vues de l'espace")
NEPAL_B = with_blocks(
    "Crues meurtrières au Népal : des ruptures de glacier",
    "Crues meurtrières au Népal : des ruptures de glacier en cause",
    "Crues meurtrières au Népal et au Tibet : au moins 550 morts",
    "Inondations au Népal : plus de 500 morts, plus d'un millier disparus",
    "Le Népal face aux crues : la montagne a lâché")
IRAN = with_blocks(
    "Guerre Iran-Etats-Unis",
    "Six mois de guerre entre les Etats-Unis et l'Iran : que reste-t-il",
    "Régime, capacités militaires, économie... L'Iran sort affaibli",
    "Des milliers de morts, un chaos économique et une région instable")

check("два непальских сюжета — одно событие", same_story(NEPAL_A, NEPAL_B))
check("Непал и Иран — разные события", same_story(NEPAL_A, IRAN), False)
check("Непал и Норвегия — разные события",
      same_story(NEPAL_B, with_blocks("Le roi Harald",
                                      "Le roi Harald de Norvège décède à 89 ans",
                                      "Harald V, roi depuis plus de trente ans")), False)

# Требуем и число, и долю: одно число обманывается длиной сюжета, доля —
# короткими сюжетами
check("короткий сюжет случайным пересечением не склеить",
      same_story(with_blocks("Мелочь", "Одна короткая новость"),
                 NEPAL_A), False)
check("сюжет без блоков не роняет проверку",
      same_story({"title": "Пусто"}, NEPAL_A), False)

print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
