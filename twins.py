"""Близнецы в ленте: одна история, показанная дважды (06.10.2026, владелец:
«надо, чтобы дублей не было ни от BBC, ни от France 24, ни от кого другого»).

Дубли по словам заголовка ловит storydedup, но он смотрит заголовки ДО перевода:
у «France 24» (английский) и «France 24 FR» (французский) общих слов нет, а после
перевода на язык пула слова расходятся. Здесь проверка ПОСЛЕ перевода и по
признакам, которые от языка не зависят:

  А) тот же снимок (адрес без размеров и параметров) + хотя бы одно общее слово
     заголовка. Одно слово обязательно: общая заставка издания (Reforma кладёт
     один снимок на разные новости) сама по себе близнецов не делает.
  Б) РАЗНЫЕ языковые выпуски одной редакции (France 24 и France 24 FR, BBC Mundo
     и BBC Русская служба; список — editions.EDITION_LANG) + одни сутки + два и больше общих слов в заголовках; оба
     заголовка уже на языке пула. Два материала ОДНОГО выпуска сюда не попадают:
     G1 Santa Catarina в один день пишет про двух разных избранных депутатов, и
     слов у них общих много (проверено на живой ленте 06.10.2026).

Остаётся лучшая: выше приоритет, есть фото, длиннее текст, раньше вышла.
Чистая функция — проверяется без сети и ключей.
"""
import re

_SIZE = re.compile(r"/(?:w|h|resizer|resize|size)[:_/]?\d+[^/]*|_\d+x\d*|-\d+x\d+", re.I)
_STUB = re.compile(r"logo|placeholder|default|stub|sprite|blank", re.I)
WINDOW_MS = 24 * 3600 * 1000
MIN_SHARED_B = 2


def norm_image(url):
    if not url:
        return None
    u = _SIZE.sub("", re.sub(r"[?#].*$", "", url)).lower()
    return None if _STUB.search(u) else u


def stems(title):
    return {w[:5] for w in re.split(r"[^\w]+", (title or "").lower()) if len(w) > 4}


def are_twins(a, b, family=lambda s: s, editions=frozenset()):
    if a.get("url") == b.get("url"):
        return False
    shared = stems(a.get("title")) & stems(b.get("title"))
    ia, ib = norm_image(a.get("imageUrl")), norm_image(b.get("imageUrl"))
    if ia and ia == ib and shared:
        return True
    sa, sb = a.get("source", ""), b.get("source", "")
    # Б — только для известных ЯЗЫКОВЫХ выпусков (editions.EDITION_LANG). Сайты
    # одной сети по областям (51.ru и 74.ru — «сирены» в разных областях) — разные
    # новости, хотя слова общие: найдено на живой ленте 06.10.2026
    if sa != sb and sa in editions and sb in editions and family(sa) == family(sb) and abs(a.get("publishedAt", 0) - b.get("publishedAt", 0)) <= WINDOW_MS:
        return len(shared) >= MIN_SHARED_B
    return False


def _rank(x):
    return (x.get("priority", 0), 1 if x.get("imageUrl") else 0,
            len(x.get("summary") or ""), -x.get("publishedAt", 0))


def drop_twins(items, family=lambda s: s, editions=frozenset()):
    """→ (список без близнецов, [(оставлен, снят)])."""
    drop, pairs = set(), []
    for i, a in enumerate(items):
        if i in drop or a.get("category") in ("CURRENCY", "CRYPTO"):
            continue
        for j in range(i + 1, len(items)):
            if j in drop:
                continue
            b = items[j]
            if b.get("category") in ("CURRENCY", "CRYPTO") or not are_twins(a, b, family, editions):
                continue
            keep, lose = (i, j) if _rank(a) >= _rank(b) else (j, i)
            drop.add(lose)
            pairs.append((items[keep], items[lose]))
            if lose == i:
                break
    return [x for k, x in enumerate(items) if k not in drop], pairs


# ─── Повтор прошлых дней (журнал J55, 17.10.2026) ───────────────────────────────────────────
# Владелец: «СМИ: девять казахстанцев вывезли из зоны боевых действий в Украине — видел несколько
# дней назад, появилась в третий раз, даже фото одно и то же». Развивающийся сюжет (семеро → девять)
# выходит новыми материалами с новым адресом и датой, а близнецов (drop_twins) ищем только среди
# карточек ОДНОГО прогона: прежние к тому времени уже вышли из ленты.
#
# Решение владельца: возвращаться к новости МОЖНО, если событие развивается; решает не правило, а
# рассуждение — «что нового в самой новости, стоит ли её вообще показывать». Поэтому код здесь только
# ЗАМЕЧАЕТ (тот же снимок и ≥ MIN_SHARED_REPOST общих корней слов при другом адресе), записывает
# памятку на карточку (`_repost_of`), а выпускающий редактор получает её вместе с ссылками «по теме»
# страницы и сам решает: есть новый факт — выпустить, нет — снять с причиной «повтор».
# Память живёт, пока сюжет жив: каждое новое совпадение продлевает запись (нет обрыва «4 дня и минута»).
REPOST_TTL_MS = 7 * 24 * 3600 * 1000
MIN_SHARED_REPOST = 2     # против общей заставки издания: одного слова мало, как и в близнецах


def memory_entry(card, now_ms):
    return {"img": norm_image(card.get("imageUrl")) or "", "stems": sorted(stems(card.get("title"))),
            "src": card.get("source", ""), "at": now_ms, "title": (card.get("title") or "")[:90],
            "lead": (card.get("summary") or "")[:240]}


def remember_shown(memory, items, now_ms):
    """Добавляет показанные карточки (адрес → запись), забывает записи старше REPOST_TTL_MS."""
    memory = {u: e for u, e in (memory or {}).items()
              if isinstance(e, dict) and now_ms - e.get("at", 0) < REPOST_TTL_MS}
    for x in items:
        u = x.get("url")
        if u and u not in memory and x.get("category") not in ("CURRENCY", "CRYPTO"):
            memory[u] = memory_entry(x, now_ms)
    return memory


def find_reposts(items, memory):
    """→ [(карточка, адрес прежней, запись прежней)]: новая карточка о том же сюжете, что уже показывали.

    Не повтор: карточка уже показывалась (её адрес в памяти — это она же, дожившая до нового
    прогона), и сравнение с карточкой, которая есть в этом же прогоне (тут решает drop_twins)."""
    memory = memory or {}
    current = {x.get("url") for x in items}
    found = []
    for x in items:
        img = norm_image(x.get("imageUrl"))
        if (not img or x.get("url") in memory or x.get("category") in ("CURRENCY", "CRYPTO")):
            continue
        mine = stems(x.get("title"))
        for u, e in memory.items():
            if (u not in current and e.get("img") == img
                    and len(mine & set(e.get("stems") or ())) >= MIN_SHARED_REPOST):
                found.append((x, u, e))
                break
    return found


def touch(memory, urls, now_ms):
    """Сюжет жив — продлеваем запись, чтобы цепочка не рвалась по сроку."""
    for u in urls:
        if u in memory:
            memory[u]["at"] = now_ms
    return memory
