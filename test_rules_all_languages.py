# -*- coding: utf-8 -*-
"""Правила для ВСЕХ пулов (журнал J33, 09.10.2026): ru, en, es, pt, fr.

Владелец: «правила пишем для всех». Находка: служебные абзацы («Lee también», «Leia também»,
«À lire aussi») были описаны только по-русски и по-английски, а `strip_tail` отрезал последнее
целое предложение у текста, кончающегося на .” .) .’ — во ВСЕХ языках. Тест прогоняет каждое
правило по каждому языку, поэтому «написано под один язык» теперь краснеет.
"""
import os
import sys
from unittest.mock import MagicMock

for m in ("google.generativeai", "firebase_admin", "firebase_admin.credentials", "firebase_admin.db"):
    sys.modules[m] = MagicMock()
import google
google.generativeai = sys.modules["google.generativeai"]
os.environ.setdefault("GEMINI_API_KEY", "x")
os.environ["FIREBASE_SERVICE_ACCOUNT"] = "{}"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fetch_news import strip_tail
import textcut as T

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


LEAD = {
    "ru": "Первое предложение достаточно длинное, чтобы пройти порог в восемьдесят знаков и ещё немного слов. ",
    "en": "The first sentence is long enough to pass the eighty character threshold with a few more words added. ",
    "es": "La primera oración es lo bastante larga para superar el umbral de ochenta caracteres con algunas palabras más. ",
    "pt": "A primeira frase é longa o suficiente para passar o limite de oitenta caracteres com mais algumas palavras. ",
    "fr": "La première phrase est assez longue pour dépasser le seuil de quatre-vingts caractères avec quelques mots de plus. ",
}
LAST = {"ru": "Второе целое предложение", "en": "The second whole sentence", "es": "La segunda oración completa",
        "pt": "A segunda frase completa", "fr": "La deuxième phrase complète"}
JUNK = {
    "ru": ["Читайте также: другая новость", "Подписывайтесь на наш канал", "Фото: Reuters", "Источник: ТАСС", "Реклама"],
    "en": ["Read also: another story", "See also: another story", "Subscribe to our newsletter", "Photo: Reuters",
           "Source: AP", "Advertisement", "Related coverage: another story"],
    "es": ["Lee también: otra noticia", "Te puede interesar: otra noticia", "Suscríbete a nuestro boletín",
           "Foto: Reuters", "Fuente: Europa Press", "Publicidad", "Sigue leyendo en nuestro sitio"],
    "pt": ["Leia também: outra notícia", "Veja também: outra notícia", "Assine a nossa newsletter",
           "Foto: Reuters", "Fonte: Lusa", "Publicidade", "Continue lendo no nosso site"],
    "fr": ["À lire aussi : une autre actualité", "Lire aussi : une autre actualité", "Abonnez-vous à notre newsletter",
           "Photo : Reuters", "Source : AFP", "Publicité", "Lire la suite sur notre site"],
}
# обычный текст, который НЕ должен считаться служебным (слово-подпись без двоеточия)
PROSE = {
    "ru": "Источник в правительстве сообщил, что решение будет принято на следующей неделе, пишет издание.",
    "en": "Source close to the matter said the decision will be made next week, the outlet reported on Tuesday.",
    "es": "Fuente cercana al caso dijo que la decisión se tomará la próxima semana, informó el medio este martes.",
    "pt": "Fonte próxima ao caso disse que a decisão será tomada na próxima semana, informou o veículo na terça.",
    "fr": "Source proche du dossier a indiqué que la décision sera prise la semaine prochaine, selon le média.",
}

for lang in LEAD:
    # концовка с любым закрывающим знаком — последнее предложение цело
    for end in (".", "!", "?", "…", ".»", ".”", ".’", ".)", ".\"", ".]"):
        s = LEAD[lang] + LAST[lang] + end
        check(f"{lang}: strip_tail не режет конец «{end}»", strip_tail(s) == s)
    # служебные абзацы не попадают в карточку, даже длинные и не последние
    for j in JUNK[lang]:
        junk = (j + " — " + LEAD[lang]).strip()[:140]
        art = "\n\n".join([LEAD[lang].strip() + f" Parte {i}." for i in range(1, 4)] + [junk, LEAD[lang].strip() + " Cola."])
        check(f"{lang}: служебное «{j[:22]}» не в карточке", junk not in T.card_text(art))
        check(f"{lang}: служебное «{j[:22]}» опознано", bool(T._JUNK_PARA.match(j)))
    # обратное: обычный текст не считается служебным
    check(f"{lang}: «{PROSE[lang][:18]}…» — текст, не подпись", not T._JUNK_PARA.match(PROSE[lang]))
    art = "\n\n".join([LEAD[lang].strip() + f" Parte {i}." for i in range(1, 3)] + [PROSE[lang], LEAD[lang].strip() + " Cola."])
    check(f"{lang}: абзац про источника остаётся в теле", PROSE[lang] in T.card_text(art))

# гигантский абзац (сбой разбора) делится по предложениям в КАЖДОМ языке, в том числе с «¿» и «¡»
GIANT = {
    "ru": "Это отдельное законченное предложение новости с цифрами и фактами для проверки правила. ",
    "en": "This is a separate complete news sentence with figures and facts to check the rule. ",
    "es": "¡Es una oración completa de la noticia con cifras y datos para comprobar la regla! ¿Y qué pasó después con todo esto en la ciudad? ",
    "pt": "Esta é uma frase completa da notícia com números e fatos para verificar a regra. ",
    "fr": "Voici une phrase complète de l'actualité avec des chiffres et des faits pour vérifier la règle. ",
}
for lang, sent in GIANT.items():
    g = (sent * 30).strip()
    parts = T.real_paragraphs(g)
    check(f"{lang}: гигантский абзац делится на куски", len(parts) > 3 and all(len(p) <= 900 for p in parts))
    check(f"{lang}: куски кончаются знаком конца", all(p.rstrip()[-1] in ".!?…»”" for p in parts))

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
