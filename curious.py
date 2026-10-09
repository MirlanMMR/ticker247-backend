"""Добор полосы «Интересное» (владелец, 09.10.2026: «добрать новости в Интересное»).

Полосе нужно 4–5 карточек от РАЗНЫХ источников, а после ИИ-отбора на пул оставалось 2–4:
этап 1 судит любопытное как обычные новости и часть выбрасывает. Добор возвращает из
выброшенного лучшие карточки источников «любопытного», которых в ленте ещё нет.

Не возвращаем: старше 48 часов, короткий заголовок или текст, списки и рейтинги
(«лучшие города 2026», «10 фактов»), анонсы выпусков, заглушки и чужой алфавит.
Чистая функция — проверяется без сети и ключей.
"""
import re
import time

TARGET = 5
MAX_AGE_MS = 48 * 3600 * 1000
MIN_TITLE, MIN_SUMMARY = 25, 120

_LISTICLE = re.compile(
    r"^\s*\d+\s+\w+|\b(?:best|ranked|ranking|top\s+\d+|quiz|horoscope|"
    r"лучшие|рейтинг|топ-?\d+|гороскоп|тест:|"
    r"mejores|clasificación|ranking|melhores|classement|les meilleurs?)\b|"
    r"what to expect in the new issue|в новом номере|new issue of", re.I)


def pick_topup(filtered, candidates, is_interesting, now_ms=None, target=TARGET,
               bad=lambda x: False):
    """→ список карточек для добавления (не больше target − уже есть источников)."""
    now_ms = now_ms or int(time.time() * 1000)
    have_urls = {x.get("url") for x in filtered}
    have_src = {x.get("source") for x in filtered if is_interesting(x)}
    need = target - len(have_src)
    if need <= 0:
        return []
    pool = []
    for x in candidates:
        if x.get("url") in have_urls or not is_interesting(x):
            continue
        if x.get("source") in have_src:
            continue
        if now_ms - (x.get("publishedAt") or 0) > MAX_AGE_MS:
            continue
        title, summ = str(x.get("title") or ""), str(x.get("summary") or "")
        if len(title) < MIN_TITLE or len(summ) < MIN_SUMMARY or _LISTICLE.search(title):
            continue
        if bad(x):
            continue
        pool.append(x)
    # свежие первыми, с фото вперёд; по одной от источника
    pool.sort(key=lambda x: (1 if (x.get("imageUrl") or "").startswith("http") else 0,
                             x.get("publishedAt") or 0), reverse=True)
    out, seen = [], set()
    for x in pool:
        s = x.get("source")
        if s in seen:
            continue
        seen.add(s)
        out.append(x)
        if len(out) >= need:
            break
    return out


def topup_interesting(filtered, candidates, lang, is_interesting, bad=lambda x: False):
    add = pick_topup(filtered, candidates, is_interesting, bad=bad)
    if add:
        print(f"  🎈 Добор «Интересного» [{lang}]: +{len(add)} "
              + ", ".join(f"{x.get('source')}" for x in add))
    return filtered + add


# ─── Что НЕ любопытное, даже если издание любопытное ────────────────────────
#
# 09.10.2026, владелец: «про новую атомную бомбу есть сомнения, что оно должно быть
# в Интересном». Метка шла по ИСТОЧНИКУ, а Xataka, Futura-Sciences, Smithsonian
# печатают и обычные новости (оружие, политика, происшествия) и даже рекламу
# («VEVOR casse les prix du mobilier de jardin»). Карточка «любопытная» только если
# в заголовке нет признаков жёсткой новости, рекламы и беды. Лишнее не пропадает:
# такая карточка остаётся обычной новостью и идёт на свою полку.
_NOT_CURIOUS = re.compile(
    r"(?<![\w-])(?:"
    # оружие, война, власть
    r"бомб\w*|боеголов\w*|оружи\w*|военн\w*|арми[яиюей]\w*|войн\w*|вторжен\w*|санкци\w*|"
    r"обстрел\w*|теракт\w*|президент\w*|выбор(?:ы|ов|ах)\b|министр\w*|депутат\w*|законопроект\w*|"
    r"трамп\w*|путин\w*|зеленск\w*|"
    r"bomb\w*|nuclear\s+(?:weapon|arsenal|warhead|strike)|missile\w*|weapon\w*|military|army|war\b|invasion|"
    r"sanction\w*|president\w*|election\w*|minister\w*|senat\w*|congress\w*|trump|putin|"
    r"bomba|arma\b|armas\b|militar\w*|ejército|guerra|presidente|elecci\w+|ministro|"
    r"exército|eleição|ministro|"
    r"bombe|arme\b|armes\b|armée|guerre|président|élection\w*|"
    # беды и происшествия
    r"убит\w*|убийств\w*|погиб\w*|катастроф\w*|авари\w*|пожар\w*|жертв\w*|арест\w*|приговор\w*|"
    r"killed|dead|death|murder\w*|crash\w*|fire\b|arrest\w*|trial|"
    r"muert\w*|asesinat\w*|incendio|arresto|morto\w*|assassinat\w*|incêndio|"
    r"mort\b|meurtre|incendie|arrestation|tué\w*|"
    # криминал: розыск, похищение, кража, мошенничество
    r"fugitiv\w*|kidnap\w*|secuestr\w*|sequestr\w*|enl[eè]vement|robbery|theft|stolen|robo\b|roubo|"
    r"похищ\w*|краж\w*|ограбл\w*|мошенн\w*|розыск\w*|разыскива\w*|scam\w*|fraud\w*|fraude|escroc\w*|"
    # новости дня, а не факты: награды, некрологи, законы, предупреждения ведомств, рынки
    r"нобел\w*|премию|премии|умер\w*|скончал\w*|законопроект\w*|закон\b|предупрежд\w*|акции\b|биржа\w*|"
    r"nobel|prize|dies\b|died\b|obituar\w*|\blaw\b|\bbill\b|warns?\b|alert\w*|stock\w*|shares\b|"
    r"premio|muere|murió|ley\b|alerta\w*|bolsa\b|prémio|morre|lei\b|"
    r"prix\s+nobel|décès|décédé\w*|loi\b|députés|alerte\w*|ansm|bourse|"
    # реклама, скидки, подборки покупок
    r"скидк\w*|распродаж\w*|промокод\w*|купон\w*|"
    r"prix\b|promo\w*|offre\w*|bon\s+plan|deal\w*|discount\w*|coupon\w*|sale\b|"
    r"oferta\w*|descuento\w*|desconto\w*|vevor"
    r")", re.I)


def is_curious_content(item) -> bool:
    """False: по заголовку это жёсткая новость, беда или реклама, а не любопытное."""
    return not _NOT_CURIOUS.search(str(item.get("title") or ""))


# ─── Лонгрид и журнальный материал — не новость ─────────────────────────────
#
# 09.10.2026, владелец: «Странная история Отто З. — не читал, но на новость не
# похоже». The Guardian, интерактивный лонгрид (/ng-interactive/): рассказ на
# много экранов о частной истории, а не событие. ИИ его не отсеял — признаков «нет
# события» (выступление, призыв, план) в заголовке нет. Лонгрид узнаётся по адресу.
_LONGREAD_URL = re.compile(
    r"/(?:ng-interactive|long-?read|the-long-read|interactive|magazine|features?|"
    r"in-depth|profile|series|podcast|podcasts|newsletters?)/", re.I)


def is_longread_url(item) -> bool:
    return bool(_LONGREAD_URL.search(str(item.get("url") or "").split("?")[0]))
