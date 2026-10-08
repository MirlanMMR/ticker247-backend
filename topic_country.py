"""Тема не из страны пула → «Мировые» (владелец, 08.10.2026).

«Чтобы новости про Америку от узбекских изданий не попадали в Новости из…»

Страну события ставит ИИ (event_where), но не у всех карточек: покрытие 27–58 %.
Когда её нет, остаётся только текст. Правило по заголовку: карточка полки
«Новости из» (scope=pool), если в ЗАГОЛОВКЕ названа страна/сила ВНЕ стран пула
(США, Китай, ЕС, Иран…), а ни одна страна пула в заголовке и начале текста не
названа, — мировая. «Узбекистан и США подписали…» остаётся: своя страна названа.
Страна вне пула — та, что не входит в POOL_COUNTRIES пула и не его родина.

Заголовок, а не текст: в тексте упомянуть Америку может любая местная новость.
"""
import re

# код → слова (подстроки, нижний регистр) и слова с границами (короткие)
_WORDS = {
    "US": ("сша", "америк", "трамп", "trump", "вашингтон", "белый дом", "pentágono", "estados unidos",
           "états-unis", "etats-unis", "estados-unidos", "eua", "u.s.", "united states"),
    "CN": ("китай", "пекин", "китае", "china", "chine", "chinese", "chinês", "chino"),
    "EU": ("евросоюз", "брюссел", "еврокомисс", "european union", "union européenne",
           "unión europea", "união europeia", "bruxelles", "bruselas"),
    "IL": ("израил", "israel", "israël", "сектор газа", "gaza", "hamas", "хамас"),
    "IR": ("иран", "iran", "irán", "tehran", "тегеран"),
    "UA": ("украин", "ukrain", "ucrania", "ucrânia", "kiev", "киев", "zelensk", "зеленск"),
    "TR": ("турци", "turkey", "turquie", "turquía", "turquia", "эрдоган", "erdoğan", "erdogan"),
    "JP": ("япони", "japan", "japon", "japón", "japão", "токио", "tokyo"),
    "KR": ("южной коре", "южная коре", "северной коре", "south korea", "corée du", "corea del"),
    "DE": ("германи", "germany", "allemagne", "alemania", "alemanha", "берлин"),
    "GB": ("британ", "britain", "british", "великобритан", "reino unido", "royaume-uni"),
    "FR": ("франци", "france", "francia", "frança", "париж", "macron", "макрон"),
    "RU": ("росси", "russia", "rusia", "rússie", "russie", "путин", "putin", "москв", "moscow"),
}
# у каждой страны пула — свои слова (для проверки «своя страна названа»)
_OWN = {
    "KZ": ("казахстан", "kazakh", "астан", "алмат"), "UZ": ("узбекистан", "uzbek", "ташкент", "самарканд"),
    "TJ": ("таджикистан", "tajik", "душанбе"), "KG": ("кыргыз", "киргиз", "бишкек", "kyrgyz", "ош "),
    "BY": ("беларус", "белорус", "минск"), "AM": ("армени", "ереван"), "AZ": ("азербайджан", "баку"),
    "GE": ("грузи", "тбилиси"), "MD": ("молдов", "кишин"), "TM": ("туркмен", "ашхабад"),
    "RU": _WORDS["RU"], "GB": _WORDS["GB"], "FR": _WORDS["FR"], "DE": _WORDS["DE"],
    "US": _WORDS["US"], "CN": _WORDS["CN"], "UA": _WORDS["UA"], "TR": _WORDS["TR"],
    "IE": ("ирланди", "ireland", "irlande", "irlanda"), "CA": ("канад", "canada", "canadá"),
    "AU": ("австрали", "australia"), "NZ": ("новой зеланди", "new zealand"), "IN": ("инди", "india", "inde"),
    "NG": ("нигери", "nigeria"), "ZA": ("южной африк", "south africa"), "SG": ("сингапур", "singapore"),
    "JM": ("ямайк", "jamaica"),
    "ES": ("испани", "spain", "españa", "espagne"), "MX": ("мексик", "mexico", "méxico", "mexique"),
    "AR": ("аргентин", "argentin"), "CO": ("колумби", "colombia"), "PE": ("перу", "peru", "perú", "pérou"),
    "CL": ("чили", "chile", "chili"), "VE": ("венесуэл", "venezuela"), "CU": ("кубинск", "на кубе", "кубы", "cuba"),
    "UY": ("уругва", "uruguay"), "BR": ("бразил", "brazil", "brasil", "brésil"),
    "PT": ("португал", "portugal"), "AO": ("ангол", "angola"), "MZ": ("мозамбик", "moçambique", "mozambique"),
    "BE": ("бельги", "belgi", "belgique", "bélgica"), "CH": ("швейцар", "suisse", "suiza", "suíça", "switzerland"),
    "TN": ("тунис", "tunisie", "túnez", "tunisia"), "DZ": ("алжир", "algérie", "argelia", "algeria"),
    "HT": ("гаити", "haïti", "haiti"), "CD": ("конго", "congo", "rdc"), "BJ": ("бенин", "bénin", "benin"),
    "SN": ("сенегал", "sénégal"), "CI": ("кот-д", "côte d", "costa de marfil"), "MA": ("марокк", "maroc", "marruecos", "morocco"),
}
_SHORT = {"US": re.compile(r"\bсша\b|\bus\b|\busa\b|\beua\b", re.I), "EU": re.compile(r"\bес\b|\beu\b|\bue\b", re.I)}


def _hit(code, text):
    if code in _SHORT and _SHORT[code].search(text):
        return True
    return any(w in text for w in _WORDS.get(code, ()))


def outside_in_title(title, space):
    """→ код страны вне пула, названной в заголовке, или None."""
    low = (title or "").lower()
    for code in _WORDS:
        if code in space:
            continue
        if _hit(code, low):
            return code
    return None


def names_own(text, space):
    low = (text or "").lower()
    for code in space:
        if any(w in low for w in _OWN.get(code, ())):
            return True
        if code in _WORDS and _hit(code, low):
            return True
    return False


def foreign_topic(item, space):
    """True: карточка полки «Новости из» говорит о стране вне пула, своей не называя."""
    if item.get("scope") != "pool" or item.get("bridge") or item.get("event_where"):
        return False
    code = outside_in_title(item.get("title"), space)
    if not code:
        return False
    head = f"{item.get('title','')} {str(item.get('summary',''))[:300]}"
    return not names_own(head, space)


def final_foreign_topic_guard(items, lang, space):
    moved = []
    for x in items:
        if foreign_topic(x, space):
            x["scope"] = "world"
            moved.append(x)
    if moved:
        print(f"  🌎 Чужая тема с «Новости из» в «Мировые» [{lang}]: {len(moved)}")
        for x in moved[:5]:
            print(f"       · {x.get('source','?')}: {(x.get('title') or '')[:64]}")
    return items
