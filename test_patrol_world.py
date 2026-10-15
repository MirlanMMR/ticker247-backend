# -*- coding: utf-8 -*-
"""Боевой режим дозора: мировое срочное (3 редакции + слово беды + масштаб). Тест — на правило."""
import sys

import patrol_world as W
from patrol_rules import event_tier

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


# ── масштаб: что может быть мировым срочным ──
for t in ("Землетрясение магнитудой 7,1 произошло у берегов Японии",
          "Strong earthquake strikes off Japan",
          "Terror attack in Paris: several dead",
          "Plane crash in Nepal: airliner went down",
          "Declares war: parliament approves the decision",
          "Terremoto de magnitud 7 sacude Chile",
          "Furacão atinge o Caribe",
          "Séisme en Turquie",
          "Наводнение в Непале: погибли 25 человек",
          "Floods kill dozens in Nepal",
          "Государственный переворот в стране"):
    check(f"масштаб: {t[:44]}", W.world_scale(t))

# ── чего быть не может ──
for t in ("На заводе Intel Fab 38 в Израиле произошёл взрыв",          # J49: взрыв без пострадавших
          "Пожар на складе в Гватемале, погиб один человек",             # одиночная беда
          "Пассажир Damas погиб во время схода селя",                    # J38
          "Возможно землетрясение в регионе, предупредили сейсмологи",    # прогноз
          "Hurricane expected to hit the coast next week",               # прогноз
          "Взрыв на заводе: пострадали рабочие",                         # без масштаба
          "Flooding in a village, one dead",
          "Президент заявил о ядерной программе"):
    check(f"не масштаб: {t[:44]}", not W.world_scale(t))
check("прогноз вместе с совершившимся — событие", W.world_scale("Землетрясение произошло, ожидаются афтершоки: погибли 30"))
check("достаточно одного заголовка из событий", W.is_world_urgent(["Пожар в доме", "Earthquake strikes Chile"]))
check("все заголовки мелкие — нет", not W.is_world_urgent(["Пожар в доме", "Погиб рыбак"]))

# ── лестница редакций + масштаб (как работает дозор) ──
three = {"Reuters", "BBC", "AP"}
check("3 редакции + землетрясение: срочно и мировое",
      event_tier(three, {"europe", "north_america"}, ["Earthquake strikes Chile"]) == "urgent"
      and W.is_world_urgent(["Earthquake strikes Chile"]))
check("2 редакции — ни срочно, ни важно", event_tier({"Reuters", "BBC"}, {"europe"}, ["Earthquake strikes Chile"]) is None)
check("3 редакции + взрыв на заводе: срочно по слову, но не мировое по масштабу",
      event_tier(three, {"europe"}, ["Explosion at plant, blast heard"]) == "urgent"
      and not W.is_world_urgent(["Explosion at plant, blast heard"]))

# ── карточка ──
NOW = 1_000_000_000_000
ev = {"families": {"Reuters", "BBC", "AP"}, "items": [
    {"title": "Earthquake strikes Chile", "url": "https://b/2", "source": "BBC", "language": "en", "publishedAt": NOW - 600_000, "summary": "s"},
    {"title": "Strong earthquake hits Chile", "url": "https://r/1", "source": "Reuters", "language": "en", "publishedAt": NOW - 900_000, "imageUrl": "https://img"},
    {"title": "Chile quake", "url": "https://a/3", "source": "AP", "language": "en", "publishedAt": NOW - 300_000}]}
c = W.to_card(ev, NOW)
check("голос события — тот, кто первым (Reuters)", c["source"] == "Reuters" and c["url"] == "https://r/1")
check("карточка: срочно, мировая, приоритет 2, метка дозора",
      c["category"] == "URGENT" and c["scope"] == "world" and c["priority"] == 2 and c["patrol"] is True)
check("источники подтверждения названы", c["patrolSources"] == "AP, BBC, Reuters")
check("язык не нашего пула — нет карточки", W.to_card({"families": set(), "items": [dict(ev["items"][0], language="de")]}, NOW) is None)
check("без ссылки — нет карточки", W.to_card({"families": set(), "items": [dict(ev["items"][0], url="")]}, NOW) is None)

# ── слияние с лентой ──
same = lambda a, b: a.get("title", "")[:10] == b.get("title", "")[:10]
feed = [{"title": "Новость А", "category": "NEWS", "publishedAt": NOW}]
merged, why = W.merge(feed, c, same, NOW)
check("добавлена первой", why is None and merged[0] is c and len(merged) == 2)
dup = dict(c, title="Strong earthquake hits Chile, update")
_, why = W.merge(merged, dup, same, NOW)
check("то же событие в ленте — не дублируем", why == "событие уже в ленте")
two_urgent = [{"title": f"Срочная {i}", "category": "URGENT", "publishedAt": NOW - 3600_000} for i in range(2)]
_, why = W.merge(two_urgent, c, same, NOW)
check("уже два срочных свежих — не добавляем", why and "2 срочных" in why)
old_urgent = [{"title": f"Срочная {i}", "category": "URGENT", "publishedAt": NOW - 5 * 3600_000} for i in range(2)]
merged, why = W.merge(old_urgent, c, same, NOW)
check("старые срочные не мешают", why is None and merged[0] is c)

# ── запись в базу (поддельная база с транзакцией) ──
class FakeRef:
    def __init__(self, value):
        self.value = value

    def transaction(self, fn):
        self.value = fn(self.value)


class FakeDb:
    def __init__(self, items):
        self.ref = FakeRef(items)
        self.paths = []

    def reference(self, path):
        self.paths.append(path)
        return self.ref


db = FakeDb([{"title": "Новость А", "category": "NEWS", "publishedAt": NOW}])
done, why = W.publish(c, db, same, NOW)
check("публикация: узел ленты пула, карточка первой", done and db.paths == ["/news/en/items"] and db.ref.value[0] is c and len(db.ref.value) == 2)
done, why = W.publish(dict(c, title="Strong earthquake hits Chile, again"), db, same, NOW)
check("повтор того же события — не публикуем, лента не меняется", not done and why == "событие уже в ленте" and len(db.ref.value) == 2)
db = FakeDb(None)
done, why = W.publish(c, db, same, NOW)
check("пустой узел не создаём", not done and why == "лента пула пуста" and db.ref.value is None)
db = FakeDb({"0": {"title": "Новость Б", "category": "NEWS", "publishedAt": NOW}})
done, why = W.publish(c, db, same, NOW)
check("узел-словарь тоже читается", done and len(db.ref.value) == 2)

print(f"\n{ok} ✓, {fail} ✗")
sys.exit(1 if fail else 0)
