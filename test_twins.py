"""Близнецы в ленте — twins.py (06.10.2026)."""
import sys
from twins import are_twins, drop_twins, norm_image

ok = fail = 0
def check(name, cond):
    global ok, fail
    if cond: ok += 1; print(f"  ✓ {name}")
    else: fail += 1; print(f"  ✗ {name}")

FAM = {"France 24": "f24", "France 24 FR": "f24", "BBC Mundo": "bbc", "BBC Русская служба": "bbc"}
fam = lambda s: FAM.get(s, s)
def card(url, title, source, img=None, t=1_000_000, pr=0, summ=""):
    return {"url": url, "title": title, "source": source, "imageUrl": img,
            "publishedAt": t, "priority": pr, "summary": summ, "category": "NEWS"}

IMG = "https://cdn.example.org/media/display/abc123/w:1024/p:16x9/gaza.jpg"
IMG_S = "https://cdn.example.org/media/display/abc123/w:300/p:16x9/gaza.jpg?x=1"

# France 24, ru-лента, 06.10.2026: одно фото, один сюжет, разные языки оригинала
a = card("u1", "Израиль предупредил жителей Газы о «тяжелой цене» за атаки 7 октября", "France 24", IMG)
b = card("u2", "7 октября: Израиль пригрозил Газе «высокой ценой» в случае нападения", "France 24 FR", IMG_S)
check("тот же снимок (разные размеры) и общее слово — близнецы", are_twins(a, b, fam))
kept, pairs = drop_twins([a, b], fam)
check("остаётся один", len(kept) == 1 and len(pairs) == 1)

# Reforma: одна заставка на разные новости — не близнецы
r1 = card("r1", "Investiga FGE posible atentado contra Gobernador", "Reforma", IMG)
r2 = card("r2", "Militarizan Aduanas; persiste huachicoleo", "Reforma", IMG)
check("общая заставка без общих слов — не близнецы", not are_twins(r1, r2, fam))

# Разные выпуски одной редакции, фото разные, но два общих слова за сутки
m1 = card("m1", "Trump anunció aranceles contra China esta semana", "BBC Mundo", "https://a/1.jpg")
m2 = card("m2", "Трамп анонсировал aranceles против China на этой неделе", "BBC Русская служба", "https://a/2.jpg")
check("разные выпуски одной редакции, два общих слова — близнецы", are_twins(m1, m2, fam))
m3 = card("m3", "Трамп анонсировал aranceles против China на этой неделе", "BBC Русская служба",
          "https://a/3.jpg", t=1_000_000 + 30 * 3600 * 1000)
check("прошло больше суток — не близнецы", not are_twins(m1, m3, fam) )

# G1: два разных материала одного выпуска с общими словами — не близнецы
g1 = card("g1", "Eleições 2026: Napoleão Bernardes é eleito deputado estadual", "G1 Santa Catarina")
g2 = card("g2", "Saiba quem é Adriano Silva, vice-governador eleito em Santa Catarina", "G1 Santa Catarina")
check("один выпуск, разные люди — не близнецы", not are_twins(g1, g2, fam))

# Выбор лучшего: выше приоритет, потом фото, потом длина
x = card("x", "Израиль Газа 7 октября предупредил", "France 24", IMG, summ="коротко")
y = card("y", "Израиль Газа 7 октября пригрозил", "France 24 FR", IMG, pr=2, summ="длинно" * 50)
kept, _ = drop_twins([x, y], fam)
check("остаётся карточка с высшим приоритетом", [k["url"] for k in kept] == ["y"])

fin = {"url": "c1", "title": "USD 89", "source": "s", "category": "CURRENCY", "imageUrl": IMG}
fin2 = dict(fin, url="c2")
check("финансовые карточки не трогаем", len(drop_twins([fin, fin2], fam)[0]) == 2)
check("заставка с logo в адресе не считается снимком", norm_image("https://a/logo.png") is None)

print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
