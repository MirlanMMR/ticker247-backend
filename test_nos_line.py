"""НОС: сжатие длинного предложения (nos_line.py) и приём строки (editor.clean_line) — правила владельца 04.11.2026."""
import sys
import editor as ED
import nos_line as N

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else: fail += 1; print(f"  ✗ {name}")

# ── пример владельца: числа цифрами, придаточное уходит, точка ──
t = "Тегеран заявил об уничтожении четырёх танкеров в Ормузском проливе из-за ответных санкций, введённых против страны США и ЕС"
t_short = "Тегеран заявил об уничтожении четырёх танкеров в Ормузском проливе из-за ответных санкций"
check("пример владельца при лимите 70: «4х танкеров», на «из-за» точка",
      N.compress(t_short, "ru", 70) == "Тегеран заявил об уничтожении 4х танкеров в Ормузском проливе.")
check("при лимите 100 причина остаётся, если помещается (не сокращаем зря)",
      N.compress(t_short, "ru") == "Тегеран заявил об уничтожении 4х танкеров в Ормузском проливе из-за ответных санкций.")
check("длиннее 100 — режем по смыслу, на придаточном, с точкой",
      N.compress(t, "ru") == "Тегеран заявил об уничтожении 4х танкеров в Ормузском проливе из-за ответных санкций.")
check("числа: двух → 2х, трёх → 3х, пять → 5", N.numerals_to_digits("двух, трёх и пять", "ru") == "2х, 3х и 5")
check("«один» не трогаем", N.numerals_to_digits("один из двух", "ru") == "один из 2х")
check("слово внутри другого не заменяется (пятиэтажка)", N.numerals_to_digits("пятиэтажка", "ru") == "пятиэтажка")
check("не режем, если влезает: полные слова остаются",
      N.compress("Власти объявили чрезвычайную ситуацию в Оше", "ru") == "Власти объявили чрезвычайную ситуацию в Оше.")
check("точка вместо запятой, когда союза нет и смысл сохранён",
      N.compress("Сель сошёл в Оше и перекрыл трассу на юг страны вчера вечером, власти эвакуируют жителей", "ru", 70)
      == "Сель сошёл в Оше и перекрыл трассу на юг страны вчера вечером.")
check("обрезок, потерявший смысл (меньше 55%), не принимается — None",
      N.compress("Предприниматель, его жена, дети и друзья оказались среди погибших при крушении самолёта над океаном вчера вечером", "ru") is None)
check("висячее слово в конце головы не принимается",
      N.compress("Полиция ищет мужчину, который убил женщину, а затем напал на подростка и скрылся с места происшествия на машине", "ru") is None
      or not N.compress("Полиция ищет мужчину, который убил женщину, а затем напал на подростка и скрылся с места происшествия на машине", "ru").rstrip(".").endswith((" а", " и", " в")))
check("придаточное предпочтительнее запятой",
      N.compress("Власти объявили ЧС в трёх районах области, жителей предупредили по радио, из-за схода селей на юге страны и в горах Тянь-Шаня", "ru")
      .startswith("Власти объявили ЧС в 3х районах области, жителей предупредили по радио."))
check("сначала сокращения слов, смысл целиком",
      "США" in N.compress("Соединённые Штаты Америки объявили чрезвычайную ситуацию в десяти штатах из-за ураганов на восточном побережье страны", "ru"))
check("сокращения только когда нужно (влезает — слова полные)",
      N.abbreviate("Соединённые Штаты ввели пошлины", "ru", 70) == "Соединённые Штаты ввели пошлины")
check("млн и доллары: «12 миллионов долларов» → «$12 млн»", "$12 млн" in N.abbreviate("выделит 12 миллионов долларов на дороги в трёх районах области страны", "ru", 40))
check("нечем сжать — None (в виджет не идёт), а не обрезок",
      N.compress("Правительство выделит двенадцать миллионов на восстановление дорог в районах области страны и ещё на ремонт школ и больниц", "ru") is None)
for lang, text in [("en", "Prime Minister said two million people lost power after the storm hit the east coast"),
                   ("es", "El presidente dijo que tres millones de personas perdieron la luz tras la tormenta en la costa"),
                   ("pt", "O presidente disse que quatro milhões de pessoas ficaram sem luz após a tempestade na costa leste"),
                   ("fr", "Le président a dit que trois millions de personnes ont perdu le courant après la tempête sur la côte")]:
    r = N.compress(text, lang)
    check(f"[{lang}] результат ≤ 100, с точкой, без «…»", r is not None and len(r) <= 100 and r.endswith(".") and "…" not in r)
check("результат никогда не заканчивается запятой или «…»",
      all(not (N.compress(x, "ru") or ".").rstrip().endswith((",", "…", ":")) for x in [t, "Раз, два, три четыре пять шесть семь восемь девять десять одиннадцать двенадцать тринадцать"]))

# ── замки приёмки: сжатие, потерявшее смысл, не принимается (clean_line) ──
neg = {"title": "Власти так и не нашли пропавших туристов в горах из-за сильного снегопада в районе", "language": "ru", "category": "URGENT"}
head = N.compress(neg["title"], "ru")
check("отрицание в голове сохранено — принято", head is not None and ED.clean_line(head, neg) is not None)
neg2 = {"title": "Из-за сильного снегопада власти не нашли пропавших туристов в горах района до сих пор", "language": "ru", "category": "URGENT"}
check("число из слов принимается замком (4х ← «четырёх»)", ED.clean_line("Тегеран заявил об уничтожении 4х танкеров в Ормузском проливе.", {"title": t_short, "language": "ru"}) is not None)
check("придуманное число отклоняется", ED.clean_line("Тегеран заявил об уничтожении 5х танкеров в Ормузском проливе.", {"title": t_short, "language": "ru"}) is None)

# ── сквозной путь: ИИ строки не дал — сжатие из заголовка; строка ИИ длиннее лимита — сжимается кодом ──
item = {"title": t, "language": "ru", "category": "URGENT", "priority": 2, "summary": ""}
ok_, x, notes = ED.apply_verdict(dict(item), {}, [], [])
check("ИИ строки не дал — строка из заголовка по правилам владельца",
      x.get("line") == "Тегеран заявил об уничтожении 4х танкеров в Ормузском проливе из-за ответных санкций." and "строка НОС: из заголовка" in notes)
long_ai = t + ", которые ввели Вашингтон и Брюссель"
ok_, x, notes = ED.apply_verdict(dict(item), {"line": long_ai}, [], [])
check("строка ИИ длиннее лимита сжата кодом", x.get("line") == "Тегеран заявил об уничтожении 4х танкеров в Ормузском проливе из-за ответных санкций." and "строка НОС: сжата кодом" in notes)

# ─── J72: заголовок карусели сжимается по смыслу (владелец 04.11: точка вместо запятой, придаточное уходит) ───
ti = "Тегеран заявил об уничтожении четырёх танкеров в Ормузском проливе из-за ответных санкций, введённых против страны"
cards = [{"title": ti, "priority": 2, "category": "NEWS", "summary": ""},                       # карусель — сжимаем
         {"title": ti, "priority": 1, "category": "NEWS", "summary": ""},                       # обычная — не трогаем
         {"title": "Власти так и не нашли пропавших туристов в горах района из-за сильного снегопада и тумана", "priority": 2,
          "category": "NEWS", "summary": ""}]
out = N.final_title_compress([dict(c) for c in cards], "ru")
check("карусельный заголовок сжат: точка, придаточное ушло, «…» нет",
      out[0]["title"].endswith(".") and "…" not in out[0]["title"] and len(out[0]["title"]) <= 72 and "4х" in out[0]["title"])
check("полный заголовок издания сохранён в titleOriginal", out[0]["titleOriginal"] == ti)
check("обычную карточку (не карусель) не трогаем", out[1]["title"] == ti and "titleOriginal" not in out[1])
check("отрицание в голове сохранено", "не нашли" in out[2]["title"] and out[2]["title"].endswith("."))
short = [{"title": "Сель в Оше перекрыл трассу", "priority": 2}]
check("короткий заголовок не меняется", N.final_title_compress(short, "ru")[0]["title"] == "Сель в Оше перекрыл трассу")
lost_neg = [{"title": "Из-за сильного снегопада и тумана власти не нашли пропавших туристов в горах района и закрыли трассу", "priority": 2,
             "category": "NEWS", "summary": ""}]
r = N.final_title_compress([dict(lost_neg[0])], "ru")[0]["title"]
check("отрицание в отсечённой части — заголовок не сжимается (смысл важнее длины)", r == lost_neg[0]["title"])
check("замок общий: клин НОС и заголовок используют nos_line.clean", N.clean("Сель сошёл в Оше и перекрыл трассу.", "Сель сошёл в Оше и перекрыл трассу", "", "ru") is not None)

# ─── даты: «5 ноября» → «05.11» (владелец 04.11) ───
check("ru: «5 ноября» → «05.11»", N.normalize_dates("с 5 ноября и 12 декабря", "ru") == "с 05.11 и 12.12")
check("es/pt/fr: «5 de noviembre», «5 de novembro», «1er novembre»",
      N.normalize_dates("el 5 de noviembre", "es") == "el 05.11" and N.normalize_dates("em 5 de novembro", "pt") == "em 05.11"
      and N.normalize_dates("le 1er novembre", "fr") == "le 01.11")
check("en: цифровой даты нет (5.11 двусмысленно), месяц до трёх букв",
      N.normalize_dates("on November 5", "en") == "on November 5" and "Nov 5" in N.abbreviate("The vote on November 5 was held", "en", 10))
dt = {"title": "Власти Бишкека объявили, что с 5 ноября изменятся схемы движения автобусных маршрутов в центре города и на юге", "language": "ru"}
check("замок чисел принимает «05.11», если в источнике «5 ноября»", N.clean("С 05.11 в Бишкеке изменятся схемы движения автобусов.", dt["title"], "", "ru") is not None)
check("замок отклоняет выдуманную дату (06.11 при «5 ноября»)", N.clean("С 06.11 в Бишкеке изменятся схемы движения автобусов.", dt["title"], "", "ru") is None)

# замок: ИИ написал «5 ноября» — строка приводится к «05.11» и принимается (3-й прогон 04.11 отклонил её зря)
bus_item = {"title": "В Бишкеке с 5 ноября изменятся схемы движения 8 автобусных маршрутов", "summary": "Мэрия: изменятся схемы восьми маршрутов.", "language": "ru"}
got = N.clean("С 5 ноября изменятся схемы движения 8 автобусных маршрутов в Бишкеке.", bus_item["title"], bus_item["summary"], "ru")
check("строка ИИ с «5 ноября» принимается и становится «05.11»", got == "С 05.11 изменятся схемы движения 8 автобусных маршрутов в Бишкеке.")
check("выдуманная дата по-прежнему отклоняется", N.clean("С 6 ноября изменятся схемы движения 8 автобусных маршрутов.", bus_item["title"], bus_item["summary"], "ru") is None)

# ─── замок смысла: строка — сжатие заголовка, а не пересказ из текста (владелец 04.11, банки крови) ───
bt = "Банки крови пострадали от кибератаки на следующий день после ложных сообщений о минировании авиарейсов в Европе"
bsrc = "Кибератака затронула системы мониторинга и управления холодильными камерами EFS во Франции."
check("плохая строка (деталь из текста вместо сути заголовка) отклоняется",
      N.clean("Кибератака на французские банки крови: системы холодильников затронуты.", bt, bsrc, "ru") is None)
check("хорошая строка (событие и его связь) принимается",
      N.clean("Банки крови пострадали от кибератаки после ложных сообщений о минировании рейсов", bt, bsrc, "ru") is not None)
check("пример владельца с отсечённым придаточным проходит замок смысла",
      N.clean("Тегеран заявил об уничтожении 4х танкеров в Ормузском проливе.", t_short, "", "ru") is not None)
check("короткие заголовки замком смысла не проверяются", N.keeps_title_essence("Сель в Оше", "Сель в Оше перекрыл трассу"))

check("строка на русском у английской карточки отклоняется (найдено в замере 04.11)",
      N.clean("Пешеход погиб в результате наезда автомобиля в Браун-Дир.", "Report: Pedestrian killed after being struck by vehicle in Brown Deer", "", "en") is None)
check("английская строка у английской карточки принимается",
      N.clean("Pedestrian killed after being struck by a vehicle in Brown Deer.", "Report: Pedestrian killed after being struck by vehicle in Brown Deer", "", "en") is not None)

# ── J74: исполнитель действия обязан остаться в строке (владелец 07.11, Йемен) ──
TY = "Саудовские бомбардировки в Йемене привели к гибели не менее 22 человек"
item = {"title": TY, "language": "ru"}
check("J74: пример владельца — строка без «кто бомбил» отклонена", ED.clean_line("Не менее 22 человек погибли при бомбардировках в Йемене.", item) is None)
check("J74: версия владельца принята", ED.clean_line("Не менее 22 человек погибли в Йемене от бомбардировок Саудовской Аравии.", item) is not None)
check("J74: «Саудовские бомбардировки …» (исполнитель на месте) принята", ED.clean_line("Саудовские бомбардировки в Йемене убили не менее 22 человек.", item) is not None)
check("J74: исполнитель найден", N.actors_of(TY, "ru") == ["Саудовские"])
check("J74: «по Украине», «в Йемене» — не исполнитель", N.actors_of("Удары по Украине и бомбардировки в Йемене продолжаются", "ru") == [])
check("J74: «удар России» — исполнитель после действия", N.actors_of("Удар России по Харькову: 5 погибших", "ru") == ["России"])
check("J74: «американские» = «США» (сокращение — законная замена)",
      N.keeps_actor("США нанесли удары по хуситам: 8 погибших.", "Американские удары по хуситам привели к гибели 8 человек", "ru"))
check("J74: заголовок без исполнителя — проверять нечего", N.keeps_actor("Погибли 8 человек.", "Удары по хуситам привели к гибели 8 человек", "ru"))
for lang, title, bad, good in [
    ("en", "Saudi airstrikes in Yemen kill at least 22 people", "At least 22 people died in airstrikes in Yemen.", "Saudi airstrikes in Yemen killed at least 22 people."),
    ("en", "Strike by US kills five in Iran, officials say", "Five killed in a strike in Iran.", "Five killed in US strike in Iran."),
    ("es", "Ataque de Israel en Gaza deja cinco muertos", "Cinco muertos en un ataque en Gaza.", "Cinco muertos en Gaza por un ataque de Israel."),
    ("es", "Bombardeos saudíes en Yemen dejan 22 muertos", "22 muertos en bombardeos en Yemen.", "22 muertos en bombardeos saudíes en Yemen."),
    ("pt", "Bombardeio de Israel em Gaza deixa cinco mortos", "Cinco mortos em bombardeio em Gaza.", "Cinco mortos em Gaza por bombardeio de Israel."),
    ("fr", "Frappes d'Israël sur Gaza: cinq morts", "Cinq morts dans des frappes sur Gaza.", "Cinq morts à Gaza dans des frappes d'Israël."),
]:
    check(f"J74 [{lang}]: без исполнителя — отклонена", not N.keeps_actor(bad, title, lang))
    check(f"J74 [{lang}]: с исполнителем — принята", N.keeps_actor(good, title, lang))

print(f"\nпройдено {ok}, провалено {fail}"); sys.exit(1 if fail else 0)
