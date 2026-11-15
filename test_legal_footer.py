# -*- coding: utf-8 -*-
"""Журнал J76 (15.11.2026): подвал сайта вместо статьи в обзоре прессы («Трагедия в Оше», 24.kg).

Замок на ПРАВИЛО, а не на одну статью. Цепочка поломки была из трёх звеньев, и замок стоит на каждом:
1. предчистка DOM выбрасывала КОНТЕЙНЕР со статьёй, если рядом лежал список ссылок (доля ссылок
   колонки > 0,4), — статья пропадала вместе со списком;
2. ворота качества не отличали юридическую плашку от текста (по метрикам она — обычная проза);
3. дальше плашка шла по всем путям (память страниц, ИИ-спасение, блок обзора) без единой проверки.
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
import extract as X

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}")


# ── Плашки на разных языках и у разных изданий ───────────────────────────────
FOOTERS = {
    "24.kg": "© ИА «24.kg» - Новости Кыргызстана. Все права защищены. Вся информация, размещенная на "
             "данном веб-сайте, предназначена только для персонального использования и не подлежит "
             "распространению без письменного разрешения ИА «24.kg». Редакция не несет ответственности "
             "за содержимое перепечатанных материалов и высказывания отдельных лиц.",
    "en": "Copyright 2026 Example News. All rights reserved. The material on this site may not be "
          "reproduced, distributed or republished without the prior written permission of Example News.",
    "en-c": "© 2026 The Daily Example Ltd.",
    "es": "© 2026 Diario Ejemplo. Todos los derechos reservados. Política de privacidad y términos de uso.",
    "pt": "© 2026 Jornal Exemplo. Todos os direitos reservados. Política de privacidade.",
    "fr": "© 2026 Le Journal Exemple. Tous droits réservés. Politique de confidentialité et conditions.",
    "ru-no-sign": "Все права защищены. Любое копирование материалов возможно только с письменного разрешения редакции.",
}
for name, t in FOOTERS.items():
    check(f"плашка опознана: {name}", T.is_legal_footer(t))
    check(f"карточка с плашкой — заглушка: {name}", T.is_stub_summary({"summary": t}))

# Настоящий текст плашкой не считается — в том числе новость про авторские права
REAL = [
    "Трое детей погибли в Оше при пожаре в частном доме. Об этом сообщили в МЧС. По предварительным "
    "данным, огонь вспыхнул около 4.00, однако звонок в Пожарную службу поступил лишь спустя 42 минуты.",
    "Суд в Лондоне рассмотрел иск о нарушении авторских прав: издатель требует компенсацию, а ответчик "
    "утверждает, что использовал цитаты в рамках закона и все права защищены договором лицензирования.",
    "The court ruled that the copyright claim was valid, and the studio must pay damages. Lawyers said "
    "the privacy policy of the platform was not at issue in the case, which dragged on for three years.",
    "",
]
for t in REAL:
    check(f"настоящий текст не плашка: {t[:30]!r}", not T.is_legal_footer(t))


# ── Звено 2: ворота качества ────────────────────────────────────────────────
v, why = X.GATE.evaluate(FOOTERS["24.kg"])
check("ворота: плашка не PASSED", v is not X.Verdict.PASSED)
check("ворота: причина названа", "плашка" in why)
v, _ = X.GATE.evaluate(REAL[0] + " " + REAL[0])
check("ворота: настоящий текст проходит", v is X.Verdict.PASSED)


# ── Звено 1: предчистка DOM не режет контейнер со статьёй ────────────────────
ARTICLE = (
    "<p>Трое детей погибли в Оше при пожаре в частном доме. Об этом сообщили в МЧС.</p>"
    "<p>По предварительным данным, огонь вспыхнул около 4.00, однако звонок в Пожарную службу поступил "
    "лишь спустя 42 минуты. На месте пожара обнаружили тела троих девочек — 2013, 2016 и 2018 годов "
    "рождения.</p>"
    "<p>Причиной пожара могло стать короткое замыкание электропроводки на кухне либо неисправный "
    "электрообогреватель. Площадь возгорания составила 120 квадратных метров, огонь тушили два расчёта "
    "пожарной службы, к семи часам утра пожар был полностью потушен.</p>")
RELATED = "".join(f'<a href="/article/n{i}"><h2>Новость {i}</h2></a>' for i in range(30))
LEGAL = ("<div><p>" + FOOTERS["24.kg"] + "</p></div>")
MENU = "".join(f'<a href="/{i}">Раздел {i}</a>' for i in range(30))


# Остальная страница (боковая колонка со ссылками на другие новости) — много текста, поэтому доля колонки со
# статьёй у предчистки получается малой (у 24.kg 0,14), а не «статья = полстраницы»
FILLER = "".join("<div class='side'><a href='/x'>" + ("Заголовок соседней новости из ленты. " * 6) + "</a></div>" for _ in range(20))


def page(column_inner):
    return ("<html><head><title>Страшная трагедия</title></head><body><div><div class='wrap'>"
            f"<div class='top'>{MENU}</div>"
            f"<div class='col'><div class='bg-white' id='main'><div id='article-content'>{ARTICLE}</div></div>"
            f"{column_inner}</div><div class='aside-col'>{FILLER}</div></div>{LEGAL}</div></body></html>").encode("utf-8")


# Колонка = статья + длинный список ссылок: доля ссылок колонки выше 0,4 — как у 24.kg
html = page(f"<div class='more'>{RELATED}</div>")
col = X.BeautifulSoup(html, "html.parser").find("div", class_="col")
_tot = X._text_len(X.BeautifulSoup(html, "html.parser").body)
check("условие: у колонки доля ссылок выше порога", X._link_density(col) > X.LINK_DENSITY_MAX)
check("условие: доля текста колонки ниже порога неприкосновенности", X._text_len(col) / _tot <= X.KEEP_IF_TEXT_SHARE)
soup = X.presanitize_dom(html)
check("предчистка: статья жива", soup.find(id="article-content") is not None)
check("предчистка: список «другие новости» срезан", soup.find(class_="more") is None)
check("предчистка: меню срезано", soup.find(class_="top") is None)

res = X.extract_article(html, "https://example.test/a")
check("разбор: достали статью, не подвал", "Трое детей погибли" in res.text and not T.is_legal_footer(res.text))
check("разбор: подвала в тексте нет", "Все права защищены" not in res.text)

# Страница, где статьи нет вовсе, а есть только подвал: пустота честнее подвала
bare = ("<html><body><div class='top'>" + MENU + "</div>" + LEGAL + "</body></html>").encode("utf-8")
res2 = X.extract_article(bare, "https://example.test/b")
check("страница без статьи: подвал не выдан за текст", not (res2.ok() and T.is_legal_footer(res2.text)))



# ── Звено 3: путь в блок обзора ──────────────────────────────────────────────
item = {"source": "24.kg", "title": "Страшная трагедия. Трое детей погибли в Оше", "url": "https://24.kg/a",
        "summary": "Трое детей погибли в Оше при пожаре в частном доме. Об этом сообщили в МЧС.",
        "publishedAt": 1}
key = FN._cache_key({"url": item["url"]})
FN.PAGE_BODY_CACHE[key] = {"text": FOOTERS["24.kg"], "ts": 1}
blk = FN._story_block(item, "затравка", "ru")
check("блок обзора: подвал из памяти страниц не подменил текст", not T.is_legal_footer(blk.get("summary")))
check("блок обзора: остался свой короткий текст", "Трое детей" in blk.get("summary", ""))

item2 = {**item, "summary": FOOTERS["24.kg"]}
check("блок обзора: карточка-плашка не даёт текста", not T.is_legal_footer(FN._story_block(item2, "затравка", "ru").get("summary")))

# Память страниц: плашка, записанная однажды, выбрасывается при загрузке
FN.db.reference.return_value.get.return_value = {
    "a": {"text": FOOTERS["24.kg"], "ts": 9999999999999},
    "b": {"text": REAL[0] + " " + REAL[0], "ts": 9999999999999}}
FN.load_page_bodies()
check("память страниц: плашка выброшена, статья осталась",
      "a" not in FN.PAGE_BODY_CACHE and "b" in FN.PAGE_BODY_CACHE)

# ИИ-спасение: ответ-плашка отбрасывается
FN.GEMINI_API_KEY = "x"
FN.PAGE_BODY_CACHE.clear()
FN.ask_gemini = lambda *a, **k: FOOTERS["24.kg"]
soup_stub = X.BeautifulSoup("<html><body><p>x</p></body></html>", "html.parser")
check("ИИ-спасение: плашка вместо новости отброшена",
      FN._ai_rescue_body("https://24.kg/zzz", "обрыв:", soup_stub) == "")


# ── Последний шаг: обзор с плашкой в блоке ───────────────────────────────────
def blk_of(src, summary):
    return {"source": src, "title": "t", "summary": summary, "role": "дополнение"}


story = {"id": "s1", "title": "Трагедия в Оше", "blocks": [
    blk_of("24.kg", FOOTERS["24.kg"]), blk_of("Kabar.kg", REAL[0]), blk_of("Kaktus.media", REAL[0] + " Ещё.")]}
out = T.drop_legal_footer_blocks([story], "ru", 2)
check("последний шаг: блок-плашка снят", len(out) == 1 and [b["source"] for b in out[0]["blocks"]] == ["Kabar.kg", "Kaktus.media"])
thin = {"id": "s2", "title": "Слабый", "blocks": [blk_of("24.kg", FOOTERS["24.kg"]), blk_of("Kabar.kg", REAL[0])]}
check("последний шаг: обзор без двух изданий снят целиком", T.drop_legal_footer_blocks([thin], "ru", 2) == [])
clean = {"id": "s3", "title": "Чистый", "blocks": [blk_of("A", REAL[0]), blk_of("B", REAL[0] + " Ещё.")]}
check("последний шаг: чистый обзор не тронут", T.drop_legal_footer_blocks([clean], "ru", 2) == [clean])

print(f"test_legal_footer: {ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
