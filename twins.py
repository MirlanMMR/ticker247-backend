"""Близнецы в ленте: одна история, показанная дважды (06.10.2026, владелец:
«надо, чтобы дублей не было ни от BBC, ни от France 24, ни от кого другого»).

Дубли по словам заголовка ловит storydedup, но он смотрит заголовки ДО перевода:
у «France 24» (английский) и «France 24 FR» (французский) общих слов нет, а после
перевода на язык пула слова расходятся. Здесь проверка ПОСЛЕ перевода и по
признакам, которые от языка не зависят:

  А) тот же снимок (адрес без размеров и параметров) + хотя бы одно общее слово
     заголовка. Одно слово обязательно: общая заставка издания (Reforma кладёт
     один снимок на разные новости) сама по себе близнецов не делает.
  Б) РАЗНЫЕ выпуски одной редакции (France 24 и France 24 FR, BBC Mundo и BBC
     Русская служба) + одни сутки + два и больше общих слов в заголовках; оба
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


def are_twins(a, b, family=lambda s: s):
    if a.get("url") == b.get("url"):
        return False
    shared = stems(a.get("title")) & stems(b.get("title"))
    ia, ib = norm_image(a.get("imageUrl")), norm_image(b.get("imageUrl"))
    if ia and ia == ib and shared:
        return True
    sa, sb = a.get("source", ""), b.get("source", "")
    if sa != sb and family(sa) == family(sb) and abs(a.get("publishedAt", 0) - b.get("publishedAt", 0)) <= WINDOW_MS:
        return len(shared) >= MIN_SHARED_B
    return False


def _rank(x):
    return (x.get("priority", 0), 1 if x.get("imageUrl") else 0,
            len(x.get("summary") or ""), -x.get("publishedAt", 0))


def drop_twins(items, family=lambda s: s):
    """→ (список без близнецов, [(оставлен, снят)])."""
    drop, pairs = set(), []
    for i, a in enumerate(items):
        if i in drop or a.get("category") in ("CURRENCY", "CRYPTO"):
            continue
        for j in range(i + 1, len(items)):
            if j in drop:
                continue
            b = items[j]
            if b.get("category") in ("CURRENCY", "CRYPTO") or not are_twins(a, b, family):
                continue
            keep, lose = (i, j) if _rank(a) >= _rank(b) else (j, i)
            drop.add(lose)
            pairs.append((items[keep], items[lose]))
            if lose == i:
                break
    return [x for k, x in enumerate(items) if k not in drop], pairs
