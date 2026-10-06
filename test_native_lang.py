"""Кыргызский текст — только на местной полке (native_lang.py)."""
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

kept, relab, dropped = apply([w, l, r], "ru")
check("кыргызская мировая снята", dropped == [w] and w not in kept)
check("кыргызская местная остаётся и помечена ky", l in kept and l["language"] == "ky")
check("русская местная не тронута", r in kept and r["language"] == "ru")
check("перемечено две (мировая и местная)", len(relab) == 2)

pool_item = card("Кыргызстан менен Монголия медицина боюнча жана өнүктүрүү кызматташат", "pool")
check("кыргызская на полке «Новости из» тоже снимается", apply([pool_item], "ru")[2] == [pool_item])
check("в других пулах ничего не меняем", apply([w], "en") == ([w], [], []))
fin = card("USD 89", "world", cat="CURRENCY")
check("финансовые карточки не трогаем", apply([fin], "ru")[0] == [fin])
print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
