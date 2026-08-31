# -*- coding: utf-8 -*-
"""ДОЗОР: быстро о срочном, без полного разбора.

ЗАЧЕМ. Полный прогон стоит три цента и семь минут — потому и ходит раз в час.
Но срочная новость на час не ждёт: пожар на рынке, бои в столице, землетрясение
нужны читателю через минуты, а не в конце часа.

Дорог при этом НЕ СБОР, а разбор: чтение лент — два десятка запросов и
секунды, деньги уходят на ИИ, судящий все триста новостей, и на дотяжку
статей. Срочной новости ни то, ни другое не нужно: у неё главное заголовок и
минута, а не полный текст и разметка рубрик.

Отсюда разделение, предложенное пользователем 30.08.2026: «можем брать реально
срочное отдельно, не прогоняя всё подряд?»

  · ДОЗОР (этот файл) — каждые 10-15 минут, почти даром;
  · РАЗБОР (fetch_news.py) — раз в час, как и был.

КАК ОТЛИЧИТЬ СРОЧНОЕ БЕЗ ИИ. По скорости: сколько НЕЗАВИСИМЫХ редакций
сообщили об одном событии за последние минуты. Так делают Google News и Apple
News — они не судят одну статью, они считают, сколько изданий сорвалось с
места. Двадцать редакций за двадцать минут — событие настоящее, и спрашивать,
переворот это или ограбление, не нужно.

Счёт по событию у нас уже есть: на нём стоит обзор прессы (feed_gate.
same_event). Здесь он же работает вторым ремеслом.

ЧЕГО СКОРОСТЬ НЕ ЗНАЕТ. «Событие настоящее» и «нужное нашему читателю» —
разные вещи. Именно этого не хватало, когда в Бишкек прилетало «Срочно: Луиджи
Манджоне признаёт вину по федеральному делу». Поэтому ИИ из дозора не убран —
но спрашивают его о ДВУХ-ТРЁХ кандидатах, а не о трёхстах: доли цента.

ХОЛОСТОЙ ХОД. Пока PATROL_LIVE не выставлен, дозор ничего не публикует —
только находит и печатает. Так же вводили первый этап отбора 23.08: сутки
вхолостую, сверка глазами, и лишь потом право действовать.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import fetch_news as fn
from feed_gate import same_event

LIVE = os.environ.get("PATROL_LIVE") == "true"

# Насколько свежим должно быть сообщение, чтобы считаться «прямо сейчас».
# Полтора часа, а не двадцать минут: ленты изданий врут во времени, часть
# отдаёт publishedAt с задержкой, и узкое окно теряло бы настоящие события.
WINDOW = timedelta(minutes=90)

# Сколько РАЗНЫХ редакций должно сообщить, чтобы событие считалось срочным.
#
# Три, а не пять: пять — это уже полдня разлёта новости, к тому времени её
# привезёт и обычный прогон. Три независимых редакции за полтора часа —
# самый ранний миг, когда можно быть уверенным, что событие не выдумка одного
# агентства.
MIN_OUTLETS = 3


# Страница-хроника («EN DIRECT», «AO VIVO», «LIVE UPDATES») — не событие.
# Она живёт сутками по одному адресу, а заголовок ей переписывают каждый час,
# и вместе с ним обновляется publishedAt. Поэтому она НИКОГДА не выпадает из
# окна дозора: в ночь на 31.08 пять таких страниц были единственной находкой
# за десять проходов, и с правом будить читателя дозор слал бы одну и ту же
# ссылку с новым заголовком каждые двенадцать минут.
#
# Метку ищем ТОЛЬКО В НАЧАЛЕ заголовка — так эти страницы и подписывают. Слово
# «live» посреди фразы (Live Aid, концерт вживую) к хронике отношения не имеет,
# и правило, ловящее его всюду, было бы шире своей причины.
_LIVEBLOG_HEAD = re.compile(
    r"^\W*(?:"
    r"en\s+direct|direct|suivi\s+en\s+direct"          # фр.
    r"|em\s+direto|ao\s+vivo"                          # порт.
    r"|en\s+vivo|en\s+directo|minuto\s+a\s+minuto"    # исп.
    r"|live(?:\s+updates|\s+blog|\s+news)?"            # англ.
    r"|онлайн|прямая\s+трансляция|онлайн-трансляция|хроника"   # рус.
    r")\W*[-–—:|]",
    re.IGNORECASE,
)


def _is_liveblog(item) -> bool:
    return bool(_LIVEBLOG_HEAD.match((item.get("title") or "").strip()))


def _fresh(item) -> bool:
    ts = item.get("publishedAt") or 0
    if not ts:
        return False
    age = datetime.now(timezone.utc) - datetime.fromtimestamp(ts / 1000, timezone.utc)
    return timedelta(0) <= age <= WINDOW


def _already_published(item, lang) -> bool:
    """Не сообщали ли мы об этом в прошлом прогоне.

    Сравниваем по СОБЫТИЮ, а не по ссылке: та же новость от другого издания —
    это то же событие, и второй раз будить человека незачем.
    """
    try:
        live = fn.db.reference(f"/news/{lang}/items").get() or []
    except Exception:
        return True          # не смогли проверить — молчим, это дешевле ошибки
    items = live if isinstance(live, list) else list(live.values())
    return any(x and same_event(x, item) for x in items)


def find_candidates():
    """События, о которых сорвались писать сразу несколько редакций."""
    sources = [s for s in fn.RSS_SOURCES if (s.get("priority") or 0) >= 2]
    print(f"🔭 Дозор: смотрим {len(sources)} быстрых лент")

    fresh, skipped = [], []
    for src in sources:
        try:
            for it in fn.fetch_rss(src):
                if _fresh(it) and not _is_liveblog(it):
                    fresh.append(it)
                elif _fresh(it):
                    skipped.append(it.get("title", "")[:70])
        except Exception as e:
            print(f"  ✗ {src.get('source','?')}: {type(e).__name__}")
    print(f"  свежее полутора часов: {len(fresh)}")
    if skipped:
        print(f"  ⏭ хроник пропущено: {len(skipped)} — {skipped[0]}")

    # Сбиваем в события. Считаем РЕДАКЦИИ, а не заметки: три текста одного
    # агентства — это одно сообщение, а не подтверждение
    events = []
    for it in fresh:
        for ev in events:
            if same_event(ev["lead"], it):
                ev["items"].append(it)
                ev["families"].add(fn.publisher_family(it.get("source", "")))
                break
        else:
            events.append({
                "lead": it, "items": [it],
                "families": {fn.publisher_family(it.get("source", ""))},
            })

    hot = [e for e in events if len(e["families"]) >= MIN_OUTLETS]
    hot.sort(key=lambda e: -len(e["families"]))
    return hot


def main():
    hot = find_candidates()
    if not hot:
        print("  спокойно: событий, о которых пишут разом, нет")
        return 0

    print(f"  🔥 кандидатов: {len(hot)}")
    for e in hot[:5]:
        names = ", ".join(sorted(e["families"]))
        print(f"     · {len(e['families'])} редакций: {e['lead'].get('title','')[:70]}")
        print(f"       {names}")

    if not LIVE:
        print("  🧪 холостой ход: ничего не публикуем (PATROL_LIVE не выставлен)")
        return 0

    # Боевой режим включается отдельно и осознанно — см. заголовок файла
    print("  ⚠️ боевой режим дозора ещё не написан: публикация будет здесь")
    return 0


if __name__ == "__main__":
    sys.exit(main())
