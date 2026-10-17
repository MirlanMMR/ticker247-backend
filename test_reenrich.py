# -*- coding: utf-8 -*-
"""Доборка текста — reenrich.py (журнал J60, 17.10.2026).

Случай: CNN Brasil «Caso Dark Horse: PF pede a Mendonça prorrogação do inquérito por 90 dias», в карточке
две фразы и «Em atualização», а на странице 3157 знаков. Тест — на класс: свежесть × источник текста ×
перевод × выигрыш × сюжет.
"""
import reenrich as R

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


H = 3_600_000
NOW = 1_800_000_000_000
TITLE = "Caso Dark Horse: PF pede a Mendonça prorrogação do inquérito por 90 dias"
SHORT = ("A PF (Polícia Federal) pediu ao ministro André Mendonça, do STF, a prorrogação do inquérito que "
         "investiga o financiamento do filme Dark Horse por 90 dias. Em atualização.")
FULL = ("A PF (Polícia Federal) pediu ao ministro André Mendonça, do STF, a prorrogação do inquérito que investiga "
        "o financiamento do filme Dark Horse por 90 dias. A solicitação foi registrada na quinta-feira (15).\n\n"
        "O inquérito foi instaurado no fim de julho e tinha prazo até 10 de outubro. Segundo a corporação, foram "
        "colhidas informações da Ancine e da produtora Go Up, responsável pelo filme.\n\n"
        "A PF também ressalta que novas informações foram obtidas por meio de depoimento do empresário Antônio "
        "Carlos Freixo Júnior, conhecido como Mineiro, sobre remessas ao fundo no exterior.\n\n"
        "O empresário prestou esclarecimentos como testemunha no inquérito sobre o filme Dark Horse e afirmou que "
        "a operação lhe foi apresentada como voltada a um fundo imobiliário.")


def card(**kw):
    c = {"url": "https://www.cnnbrasil.com.br/politica/caso-dark-horse/", "title": TITLE, "summary": SHORT,
         "publishedAt": NOW - 7 * H, "category": "NEWS"}
    c.update(kw)
    return c


# ── кому нужна доборка ──
check("тот самый случай: свежая, текст не со страницы — нужна", R.wants_upgrade(card(), NOW))
check("текст уже со страницы — не нужна", not R.wants_upgrade(card(fromPage=True), NOW))
check("издатель закрыл страницу — не нужна", not R.wants_upgrade(card(pageClosed=True), NOW))
check("переведённая (страница на другом языке) — не нужна", not R.wants_upgrade(card(translated=True), NOW))
check("старше срока — не нужна", not R.wants_upgrade(card(publishedAt=NOW - (R.MAX_AGE_H + 1) * H), NOW))
check("видео и живой блог — не нужна", not R.wants_upgrade(card(url="https://www.youtube.com/watch?v=x"), NOW)
      and not R.wants_upgrade(card(url="https://www.bbc.com/russian/live/abc"), NOW))
check("таймерный пост и финансы — не нужна", not R.wants_upgrade(card(expiresAt=NOW + H), NOW)
      and not R.wants_upgrade(card(category="CURRENCY"), NOW))
check("без адреса / пустая — не нужна", not R.wants_upgrade(card(url=""), NOW) and not R.wants_upgrade(None, NOW))

# ── подменять ли ──
new = R.card_text(FULL)
check("страница заметно длиннее и о том же — подменяем", R.accept_upgrade(card(), new))
check("выигрыш меньше порога — оставляем", not R.accept_upgrade(card(summary=new), new))
check("разбор выхватил чужой абзац (нет общих слов с заголовком) — оставляем",
      not R.accept_upgrade(card(), "Previsão do tempo para o fim de semana: sol e calor em todo o país, "
                           "sem previsão de chuva nas capitais do Sudeste até a próxima terça-feira, informou o instituto. " * 3))
check("пустая страница — оставляем", not R.accept_upgrade(card(), ""))

# ── план ──
fetched = []


def article_of(url):
    fetched.append(url)
    return FULL


items = [card(), card(url="https://x/2", fromPage=True), card(url="https://x/3", translated=True),
         card(url="https://x/4", title="Совсем другое", summary=SHORT)]
todo, stats = R.plan(items, NOW, article_of)
check("в плане только нужные и принятые", [i for i, _ in todo] == [0] and stats["подменено"] == 1)
check("страницы качаются только у кандидатов", fetched == ["https://www.cnnbrasil.com.br/politica/caso-dark-horse/", "https://x/4"])
check("не о том же сюжете — «не лучше»", stats["не лучше"] == 1)
todo2, stats2 = R.plan([card()], NOW, lambda u: "")
check("страница не отдалась — «страница пуста», карточку не трогаем", not todo2 and stats2["страница пуста"] == 1)
many = [card(url=f"https://x/{i}") for i in range(R.MAX_PER_POOL + 20)]
_, st = R.plan(many, NOW, lambda u: "")
check("потолок запросов на пул", st["страница пуста"] == R.MAX_PER_POOL)

# ── подключение ──
src = open("patrol.yml".replace("patrol.yml", ".github/workflows/patrol.yml"), encoding="utf-8").read()
check("patrol.yml запускает reenrich.py", "python reenrich.py" in src)
check("доборка не пишет заголовок, фото и полку", "ref.update({\"summary\": text, \"fromPage\": True, \"textUpgradedAt\": now})" in open("reenrich.py", encoding="utf-8").read())

print(f"пройдено {ok}, провалено {fail}")
raise SystemExit(1 if fail else 0)
