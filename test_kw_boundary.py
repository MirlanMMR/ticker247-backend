# -*- coding: utf-8 -*-
"""Короткое слово-признак — целое слово (журнал J41, 15.10.2026).

Случай: серверный auto_categorize ставил рубрику «ТУРЫ» по слову «тур», которое находилось в
«Турции», «туркменский», «турак жай» (6 из 7 карточек ТУРЫ в ru были ошибкой). Начало слова
проверялось, конец — нет. Тест — на класс: любое слово до 4 букв × кириллица/латиница.
"""
import ast
import re
import sys

src = open("fetch_news.py", encoding="utf-8").read()
ns = {"re": re}
for n in ast.parse(src).body:
    if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "_NEGATION_BEFORE" for t in n.targets):
        exec(compile(ast.Module([n], []), "x", "exec"), ns)
    if isinstance(n, ast.FunctionDef) and n.name == "_kw_hit":
        exec(compile(ast.Module([n], []), "x", "exec"), ns)
hit = ns["_kw_hit"]

ok = fail = 0


def check(name, got, want):
    global ok, fail
    if got == want:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}: получили {got}, ждали {want}")


# тот самый случай
check("«тур» не в «Турции»", hit("тур", "власти турции взяли под контроль телеканал"), False)
check("«тур» не в «туркменский»", hit("тур", "редкий туркменский ушан обнаружен"), False)
check("«тур» не в «турак жай»", hit("тур", "манаста уруксат документтери жок турак жайдын курулушу"), False)
check("«тур» в «тур по Алтаю»", hit("тур", "новый тур по алтаю откроют в мае"), True)
check("«тур» в «туры»", hit("тур", "горящие туры в египет подешевели"), True)
# класс: короткие кириллические
check("«ош» не в «ошибка»", hit("ош", "ошибка в расчётах привела к убыткам"), False)
check("«ош» в «в Оше»", hit("ош", "в оше открыли новый рынок"), True)
check("«дом» не в «домашний»", hit("дом", "домашний арест продлили до декабря"), False)
check("«дом» в «дома»", hit("дом", "цены на дома выросли"), True)
check("«ИИ» в «ИИ-агенты»", hit("ии", "ии-агенты займутся продажами"), True)
check("«ИИ» не в «Интернет-ИИнфраструктуре»", hit("ии", "бытовые приборы стали умнее"), False)
check("«сель» не в «селькор»", hit("сель", "селькор написал заметку"), False)
check("«сель» в «сель сошёл»", hit("сель", "сель сошёл на трассе"), True)
# латиница
check("war не в warm", hit("war", "warm weather returns to the city"), False)
check("war в war", hit("war", "war breaks out near the border"), True)
check("war в wars", hit("war", "wars and sanctions"), True)
check("ufc не в ufcs-слове", hit("ufc", "ufc champion retires"), True)
check("bomb не в Bombay", hit("bomb", "bombay stock exchange closes higher"), False)
check("bomb в bombing", hit("bomb", "bombing reported in the capital"), True)
check("bomb в bombs", hit("bomb", "bombs fell on the town"), True)
# длинные слова — по-прежнему с флексией (кроме границы начала)
check("«землетрясение» с флексией", hit("землетрясение", "землетрясением разрушены дома"), True)
check("«матч» — 4 буквы, хвост до 2", hit("матч", "матчи недели"), True)
check("«рейс» — рейсе", hit("рейс", "на рейсе из москвы"), True)
# составное слово-признак не рвётся
check("многословный признак", hit("отключение воды", "завтра отключение воды в районе"), True)

print(f"пройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
