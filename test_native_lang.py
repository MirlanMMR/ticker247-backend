"""Языки кириллицы: пометка по тексту и потолок 50/50 (native_lang.py)."""
import sys
from native_lang import apply, cap_native_share, detect_native

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else: fail += 1; print(f"  ✗ {name}")

def card(title, scope="local", lang="ru", summ="", cat="NEWS", pr=0, t=0):
    return {"title": title, "summary": summ, "scope": scope, "language": lang,
            "category": cat, "url": title, "priority": pr, "publishedAt": t}

# Настоящие заголовки Kabar.kg из ленты 06.10.2026
ky_w = card("Окумуштуулар электромобилдер үчүн зымсыз кубаттагыч иштеп чыкты", "world")
ky_l = card("Манас шаарында 375 орундуу жаңы мектеп ачылды")
ru = card("Депутат предложил по-новому определять семьи для получения пособий")
kk = card("Қазақстанда жаңа мектеп ашылды және оқушылар үшін әртүрлі бағдарлама")
uz = card("Ўзбекистонда ҳукумат янги қарор қабул қилди")
tg = card("Ҷумҳурии Тоҷикистон дар соли нав ҳадафҳо муқаррар кард")

check("кыргызский по буквам", detect_native(ky_w) == "ky" and detect_native(ky_l) == "ky")
check("казахский по букве ә", detect_native(kk) == "kk")
check("узбекский (кириллица) по ў и ҳ", detect_native(uz) == "uz")
check("таджикский по ӣ ӯ ҷ", detect_native(tg) == "tg")
check("русский не принят за родной", detect_native(ru) is None)
check("кыргызский по служебным словам без особых букв",
      detect_native(card("Кыргызстан менен Монголия кызматташат жана алыс")) == "ky")

kept, relab = apply([ky_w, ky_l, ru, kk], "ru")
check("ничего не снимается: мировая на кыргызском остаётся", len(kept) == 4)
check("каждому родному — свой код", ky_w["language"] == "ky" and kk["language"] == "kk")
check("русская не тронута", ru["language"] == "ru")
check("apply (метки по буквам) только для русского пула", apply([card("Манас шаарында жаңы мектеп")], "en")[1] == [])
check("финансовые карточки не трогаем", apply([card("USD", cat="CURRENCY")], "ru")[1] == [])

# 50/50 на «Местных»: 3 русских и 6 кыргызских → остаётся не больше 3 кыргызских
loc = [card(f"русская {i}") for i in range(3)] + [
    card(f"кыргызча {i}", lang="ky", pr=i % 2, t=i) for i in range(6)]
kept, dropped = cap_native_share(loc, "ru")
nat_left = [x for x in kept if x["language"] == "ky"]
check("родного после потолка не больше половины", len(nat_left) <= len(kept) / 2)
check("снимаются слабейшие (приоритет, давность)", all(d["priority"] <= min(x["priority"] for x in nat_left) for d in dropped))
check("русские не снимаются", all(x["language"] != "ru" for x in dropped))
check("до половины — ничего не снимается", cap_native_share(loc[:3] + loc[3:6], "ru")[1] == [])
# Потолок работает во всех пулах: Канада в английском — французская половина
en_loc = [card(f"English story {i}", lang="en") for i in range(2)] + [
    card(f"Histoire française {i}", lang="fr", t=i) for i in range(5)]
kept_en, dropped_en = cap_native_share(en_loc, "en")
check("английский пул: французского не больше половины",
      sum(1 for x in kept_en if x["language"] == "fr") <= len(kept_en) / 2 and len(dropped_en) == 3)
check("мировая на кыргызском потолком не задета",
      cap_native_share([ky_w] + [card(f"р{i}") for i in range(2)], "ru")[1] == [])
print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
