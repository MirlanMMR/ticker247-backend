"""Кыргызский текст помечается ky, не снимается (native_lang.py)."""
import sys
from native_lang import apply, looks_kyrgyz

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else: fail += 1; print(f"  ✗ {name}")

def card(title, scope, lang="ru", summ="", cat="NEWS"):
    return {"title": title, "summary": summ, "scope": scope, "language": lang, "category": cat, "url": title}

# Настоящие заголовки Kabar.kg из ленты 06.10.2026
w = card("Окумуштуулар электромобилдер үчүн зымсыз кубаттагыч иштеп чыкты", "world")
l = card("Манас шаарында 375 орундуу жаңы мектеп ачылды", "local")
r = card("Депутат предложил по-новому определять семьи для получения пособий", "local")
check("кыргызский заголовок опознан", looks_kyrgyz(w) and looks_kyrgyz(l))
check("русский не принят за кыргызский", not looks_kyrgyz(r))
check("слова без особых букв: «Кыргызстан менен Монголия … кызматташат» опознан по служебным словам",
      looks_kyrgyz(card("Кыргызстан менен Монголия медицина тармагында кызматташат жана алыс", "local")))

kept, relab = apply([w, l, r], "ru")
check("ничего не снимается: мировая на кыргызском остаётся", w in kept and l in kept and len(kept) == 3)
check("кыргызские помечены ky (и мировая, и местная)", w["language"] == "ky" and l["language"] == "ky")
check("русская местная не тронута", r["language"] == "ru")
check("перемечено две", len(relab) == 2)
check("уже помеченное ky не считается перемеченным", apply([card("Манас шаарында жаңы мектеп", "local", lang="ky")], "ru")[1] == [])
check("в других пулах ничего не меняем", apply([card("Манас шаарында жаңы мектеп", "world")], "en")[1] == [])
fin = card("USD 89", "world", cat="CURRENCY")
check("финансовые карточки не трогаем", apply([fin], "ru")[1] == [])
print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
