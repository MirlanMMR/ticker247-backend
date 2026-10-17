# -*- coding: utf-8 -*-
"""Решение «жизненно важное → срочно» принимает ИИ, а не слова (журнал J61, 17.10.2026).

Случай: G1 Rio «Furtos de cabos deixam imóveis sem luz a cerca de 50 metros de delegacia em São João de
Meriti; VÍDEO» — кража кабелей в одном районе — висела в шторке с «URGENTE». Её поставило слово-правило
`sem luz` (серверное VITAL_LOCAL, а на телефоне — второе такое же, VitalNews.LOCAL_REGEX): слова не
отличают объявление об отключении света от рассказа о краже. Редактор остановить не мог: пометка стояла
ДО него, а его «не срочно» для `vital` отключено. ИИ-пометка «жизненно важное» была выключена 24.09.2026
(VITAL_FROM_AI=False): модель ошибалась без набора проверки. Условие возврата — «только с проверкой на
наборе настоящих случаев»; набор теперь есть (testdata/vital_golden.json, проверка eval_vital.py в Actions).

Как устроено: слова только ПРЕДЛАГАЮТ кандидатов (дёшево, без ИИ) — VITAL_LOCAL; решает ИИ одним запросом на
пул по определению из EDITOR.md («Наша фишка: жизненно важное для жителя», одно определение для редактора
и для судьи). Нет ответа ИИ — не помечаем (ложное уведомление дороже пропущенной заметки: она остаётся
обычной местной новостью).
"""
import json
import re

VITAL_LOCAL = re.compile(
    r"отключ\w* (?:вод|свет|газ|электр|отоплен|горяч)|без (?:воды|света|газа)"
    r"|(?:воды|света|газа) не будет|подач\w+ (?:воды|газа|тепла)"
    r"|перекр\w+ (?:движени|улиц|дорог)|ограничен\w* движени|закрыт\w* перевал"
    r"|суу (?:өч|берилбей)|жарык өч|электр\w* өч|газ өч|жол жабыл|кыймыл чектел"
    r"|су өшір|жарық өшір|электр\w* өшір"
    r"|suv (?:o'chiril|berilmay)|svet o'chiril|elektr\w* o'chiril|gaz o'chiril"
    r"|coupure d'(?:eau|électricité)|coupure de courant|panne d'électricité"
    r"|corte de (?:agua|luz)|sin (?:agua|luz)\b|apagón"
    r"|falta de água|sem (?:água|luz)\b|apagão|corte de energia"
    r"|water (?:outage|shutoff)|power (?:outage|cut)|boil[- ]water|road clos",
    re.I)

VITAL_MAX = 2
VITAL_MAX_AGE_MS = 14 * 3600 * 1000   # объявили утром — важно до вечера
MAX_CANDIDATES = 12
SECTION_START = "## Наша фишка: жизненно важное для жителя"
SECTION_END = "## Когда снимать"


def definition_of(editor_md: str) -> str:
    """Определение жизненно важного — раздел EDITOR.md дословно (единственное место, где оно записано)."""
    a = editor_md.find(SECTION_START)
    if a < 0:
        return ""
    b = editor_md.find(SECTION_END, a)
    return editor_md[a:b if b > a else len(editor_md)].strip()


def candidates(items, now_ms):
    """Кандидаты по словам: «местные» не старше срока, свежие первыми, не больше MAX_CANDIDATES."""
    found = []
    for it in items:
        if it.get("scope") != "local" or now_ms - it.get("publishedAt", 0) > VITAL_MAX_AGE_MS:
            continue
        if VITAL_LOCAL.search(f"{it.get('title', '')} {str(it.get('summary', ''))[:400]}"):
            found.append(it)
    found.sort(key=lambda x: -x.get("publishedAt", 0))
    return found[:MAX_CANDIDATES]


def build_prompt(definition: str, cards) -> str:
    lines = []
    for i, c in enumerate(cards, 1):
        lines.append(f"{i}. {c['title']} — {str(c.get('summary') or c.get('lead') or '')[:300]}")
    return (
        "Ты выпускающий редактор новостного приложения. Ниже определение «жизненно важного для жителя» "
        "— новости, ради которой приложение БУДИТ человека уведомлением. Ошибка в сторону «да» стоит дорого: "
        "ложная тревога. Отвечай «да» только если по определению читателю надо учесть это в своём дне.\n\n"
        f"{definition}\n\n"
        "Реши по каждой карточке: true — жизненно важное (объявление или идущее сейчас событие, которое "
        "меняет день жителей: где, когда, что делать), false — нет (уже случившееся происшествие, кража, "
        "ДТП, пожар, суд, расследование, статистика, жалобы о прошлом, политика). Сомневаешься — false. "
        "Верни ТОЛЬКО JSON вида {\"1\": true, \"2\": false, ...} по всем номерам.\n\n" + "\n".join(lines))


def judge(cards, definition, ask):
    """→ {номер карточки (с 1): bool} или None, если ИИ не ответил. ask(prompt) → текст ответа."""
    if not cards:
        return {}
    try:
        raw = ask(build_prompt(definition, cards))
        m = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(m.group(0))
        return {int(k): bool(v) for k, v in data.items() if str(k).isdigit()}
    except Exception:
        return None
