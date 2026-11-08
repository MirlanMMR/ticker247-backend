# -*- coding: utf-8 -*-
"""Журнал J75 (08.11.2026): армянский текст в обзоре прессы русской ленты.

Замок на ПРАВИЛО, а не на одну статью: любой алфавит, которого не читает ни один пул, считается
чужим текстом — в проверке перевода (`_still_foreign`, пять языков пулов) и в последнем шаге перед
записью обзоров (`drop_foreign_script_stories`). Прежде проверка знала только кириллицу и латиницу:
армянский заголовок «Կրակովում հրաձգության…» в 45 знаков считался «переведённым» и уходил в эфир.
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
import fetch_news as FN
import textcut as T

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


POOLS = ("ru", "en", "es", "pt", "fr")

# Чужие алфавиты: заголовки новостей, по одному на письменность
FOREIGN = {
    "армянский": "Կրակովում հրաձգության զոհերի թիվը հասել է 6-ի, վիրավորվել է 15 մարդ",
    "грузинский": "ქრაკოვში სროლის შედეგად დაღუპულთა რაოდენობა 6-მდე გაიზარდა",
    "арабский": "ارتفاع عدد ضحايا إطلاق النار في كراكوف إلى ستة قتلى",
    "иврит": "מספר הנספים בירי בקרקוב עלה לשישה והפצועים חמישה עשר",
    "тайский": "จำนวนผู้เสียชีวิตจากเหตุยิงในเมืองคราคูฟเพิ่มขึ้นเป็น 6 คน",
    "хинди": "क्राकोव में गोलीबारी में मरने वालों की संख्या बढ़कर छह हो गई",
    "китайский": "克拉科夫枪击事件死亡人数升至六人，十五人受伤",
    "японский": "クラクフでの銃撃事件の死者は6人に増えた、15人が負傷",
    "корейский": "크라쿠프 총격 사건 사망자 수가 6명으로 늘어났다",
    "греческий": "Ο αριθμός των θυμάτων της επίθεσης στην Κρακοβία έφτασε τους έξι",
    "амхарский": "በክራኮው የተኩስ ጥቃት የሞቱት ሰዎች ቁጥር ስድስት ደረሰ",
    "тибетский": "ཁྲ་ཁོབ་ནང་མེ་མདའ་བཏང་བའི་ཤི་གྲངས་དྲུག་ཏུ་ཡར་སོང་།",
}
# Свои тексты каждого пула: ничего из этого не должно считаться чужим
OWN = {
    "ru": "В Кракове число жертв стрельбы достигло шести, ещё 15 человек ранены",
    "ky": "Кыргызстандын түндүгүндө жаан-чачындын айынан жолдор жабылды, кыймыл токтоду",
    "en": "The death toll from the shooting in Krakow has risen to six, police said",
    "es": "El número de víctimas del tiroteo en Cracovia ha subido a seis, según la policía",
    "pt": "O número de vítimas do tiroteio em Cracóvia subiu para seis, disse a polícia",
    "fr": "Le bilan de la fusillade à Cracovie s'élève à six morts, a indiqué la police",
    "pl": "Liczba ofiar strzelaniny w Krakowie wzrosła do sześciu, poinformowała policja",
    "mixed": "Гражданин Грузии (გიორგი) задержан в Тбилиси, сообщили в полиции",
    "math": "Постоянная α и β в формуле для δ равна π, объяснили физики из института",
}

# ── 1. Детектор: каждый чужой алфавит — чужой, каждый свой текст — свой ──
for name, text in FOREIGN.items():
    check(f"{name}: чужой алфавит распознан", T.is_foreign_script_text(text))
for name, text in OWN.items():
    check(f"{name}: свой текст не считается чужим", not T.is_foreign_script_text(text))

# ── 2. Проверка перевода `_still_foreign`: ПЯТЬ языков пулов × каждый алфавит, и короткие заголовки ──
for pool in POOLS:
    for name, text in FOREIGN.items():
        check(f"_still_foreign[{pool}]: {name}", FN._still_foreign(text, pool))
    for name in ("ru", "en", "es", "pt", "fr", "pl"):
        if (pool == "ru" and name in ("en", "es", "pt", "fr", "pl")) or (pool != "ru" and name == "ru"):
            continue          # прежняя логика кириллица ↔ латиница не меняется
        check(f"_still_foreign[{pool}]: свой текст «{name}» не чужой", not FN._still_foreign(OWN[name], pool))
check("короткий армянский заголовок (до 40 знаков) — чужой", FN._still_foreign("Կրակովում հրաձգություն", "ru"))
check("кыргызская кириллица в русском пуле — по-прежнему чужой", FN._still_foreign(OWN["ky"], "ru"))

# ── 3. Последний шаг перед записью обзоров ──
def block(src, title, summary="Текст обзора на языке пула."):
    return {"role": "дополнение", "source": src, "title": title, "summary": summary}


good = {"id": "a", "title": "В Кракове стрельба", "blocks": [block("РИА", OWN["ru"]), block("Радио Свобода", OWN["ru"] + " (2)")]}
arm_block = {"id": "b", "title": "Стрельба в Кракове",
             "blocks": [block("РИА", OWN["ru"]), block("Радио Свобода", OWN["ru"] + " (2)"),
                        block("Азатутюн", FOREIGN["армянский"], FOREIGN["армянский"])]}
arm_title = {"id": "c", "title": FOREIGN["армянский"], "blocks": good["blocks"]}
only_two = {"id": "d", "title": "Стрельба", "blocks": [block("РИА", OWN["ru"]), block("Азатутюн", FOREIGN["армянский"])]}
arm_summary = {"id": "e", "title": "Стрельба", "blocks": [block("РИА", OWN["ru"]), block("ТАСС", OWN["ru"] + "!"),
                                                         block("Азатутюн", OWN["ru"], FOREIGN["грузинский"])]}

out = T.drop_foreign_script_stories([good, arm_block, arm_title, only_two, arm_summary], "ru", 2)
ids = [s["id"] for s in out]
check("чистый обзор остаётся без изменений", good in out)
check("блок с чужим алфавитом снят, обзор остаётся (два издания)", "b" in ids and
      [b["source"] for b in out[ids.index("b")]["blocks"]] == ["РИА", "Радио Свобода"])
check("обзор с чужим заголовком снят целиком", "c" not in ids)
check("после снятия блока изданий меньше двух — обзор снят", "d" not in ids)
check("чужой алфавит в тексте блока (не в заголовке) — блок снят", "e" in ids and
      [b["source"] for b in out[ids.index("e")]["blocks"]] == ["РИА", "ТАСС"])
check("вход не изменён (копии, не правка на месте)", len(arm_block["blocks"]) == 3)
check("пустой список и None безопасны", T.drop_foreign_script_stories([], "ru") == [] and T.drop_foreign_script_stories(None, "ru") == [])
check("не-словарь в списке пропущен", T.drop_foreign_script_stories(["x", good], "ru", 2) == [good])
for pool in POOLS:
    check(f"[{pool}] замок работает для каждого пула", [s["id"] for s in T.drop_foreign_script_stories([arm_title, good], pool, 2)] == ["a"])

# ── 4. Проводка: замок стоит последним шагом перед записью в базу ──
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fetch_news.py"), encoding="utf-8").read()
guard = "stories = drop_foreign_script_stories(stories, lang, STORY_MIN_BIG)"
write = 'db.reference(f"/news/{lang}").set(payload)'
check("fetch_news: замок обзоров стоит перед записью ленты", guard in src and write in src and src.index(guard) < src.index(write, src.index(guard)))
check("fetch_news: проверка перевода берёт общий детектор алфавитов", "if is_foreign_script_text(text):" in src)

# ── 5. Прежняя защита ленты (J18) работает на том же перечне ──
check("J18: карточка на армянском в ленте по-прежнему снимается",
      T.has_foreign_script({"title": FOREIGN["армянский"], "summary": ""}))
check("J18: греческий заголовок теперь тоже снимается", T.has_foreign_script({"title": FOREIGN["греческий"], "summary": ""}))
check("J18: обычная новость не задета", not T.has_foreign_script({"title": OWN["ru"], "summary": OWN["ru"]}))

print(f"{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
