"""Тесты цепочки извлечения. Запуск: python test_extract.py — без сети и ключей.

Каждый случай взят из живой находки, а не выдуман: рядом с проверкой указано,
когда и на каком издании это всплыло.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import (BeautifulSoup, CreditSanitizer, FooterLinkSanitizer,
                     HeaderNoiseSanitizer, QualityGate, Verdict,
                     extract_article, extract_jsonld, presanitize_dom)

ok = fail = 0


def check(name, got, want):
    global ok, fail
    if got == want:
        ok += 1
    else:
        fail += 1
        print(f"  ✗ {name}\n     ждали: {want!r}\n     вышло: {got!r}")


# Статья намеренно длинная. Предчистка НЕ удаляет узлы, в которых лежит
# заметная доля текста страницы, — иначе на живых сайтах она вырезает статью
# вместе с обёрткой вроде «article__meta-content». Значит и в тесте служебные
# блоки должны быть малой долей, как на настоящей странице
ARTICLE = ("Правительство сообщило о принятом решении в понедельник вечером. "
           "Мера коснётся нескольких тысяч человек и вступит в силу с первого "
           "января следующего года. Ведомство обещает разъяснения позже. "
           "Представители профсоюзов уже заявили о намерении обжаловать эту "
           "инициативу в суде в ближайшие недели после публикации документа. "
           "Профильный комитет парламента рассмотрит поправки на следующей "
           "неделе, сообщил его председатель журналистам в кулуарах заседания. "
           "По оценке ведомства, расходы бюджета вырастут на четыре процента, "
           "а выпадающие доходы регионов будут компенсированы из резервного "
           "фонда в течение трёх лет с момента вступления решения в силу. "
           "Независимые экономисты считают эту оценку заниженной и указывают "
           "на прошлогодний опыт соседней страны, где похожая мера обошлась "
           "казне вдвое дороже первоначального расчёта министерства финансов.")

# ─── JSON-LD ────────────────────────────────────────────────────────────────

LD = ('<html><head><script type="application/ld+json">'
      '{"@context":"https://schema.org","@graph":[{"@type":"NewsArticle",'
      '"headline":"Заголовок","author":{"@type":"Person","name":"Иван"},'
      '"articleBody":"' + ARTICLE + '"}]}'
      '</script></head><body><nav>Меню</nav></body></html>')

check("articleBody достаётся из @graph",
      extract_jsonld(BeautifulSoup(LD, "html.parser")).startswith("Правительство"), True)

check("битая разметка не роняет разбор",
      extract_jsonld(BeautifulSoup(
          '<script type="application/ld+json">{сломано</script>', "html.parser")), "")

check("короткий articleBody не берём (это анонс, а не статья)",
      extract_jsonld(BeautifulSoup(
          '<script type="application/ld+json">'
          '{"@type":"NewsArticle","articleBody":"Коротко."}</script>', "html.parser")), "")

# ─── DOM-предчистка ─────────────────────────────────────────────────────────

DIRTY = """<html><body>
<nav>Главная Спорт Культура Погода</nav>
<div class="byline">Автор, Иван Петров</div>
<div class="reading-time">Время чтения: 5 мин</div>
<article><p>%s</p></article>
<aside class="related">Читайте также</aside>
<div class="social-share">Поделиться</div>
</body></html>""" % ARTICLE

_clean = presanitize_dom(DIRTY.encode())
_txt = _clean.get_text(" ", strip=True)
check("nav вынесен из дерева", "Главная Спорт" in _txt, False)
check("плашка автора вынесена", "Иван Петров" in _txt, False)
check("время чтения вынесено", "Время чтения" in _txt, False)
check("кнопки «поделиться» вынесены", "Поделиться" in _txt, False)
check("сама статья на месте", "Правительство сообщило" in _txt, True)

# Плотность ссылок: блок, где почти все слова в ссылках, — навигация
LINKY = ("<html><body><div>" + "".join(
    f'<a href="/{i}">Раздел номер {i}</a> ' for i in range(12)) +
    "</div><article><p>" + ARTICLE + "</p></article></body></html>")
_t2 = presanitize_dom(LINKY.encode()).get_text(" ", strip=True)
check("блок из одних ссылок вынесен", "Раздел номер 5" in _t2, False)
check("статья рядом с ним уцелела", "Правительство сообщило" in _t2, True)

# ─── Чистильщики ────────────────────────────────────────────────────────────

check("плашка автора срезается, статья остаётся",
      HeaderNoiseSanitizer().apply(
          "Автор, Иван Петров\nОтдел новостей, Лондон\nВремя чтения: 5 мин\n" + ARTICLE
      ).startswith("Правительство"), True)

check("статья без плашки не трогается",
      HeaderNoiseSanitizer().apply(ARTICLE), ARTICLE)

# 24.08, iXBT: «Источник изображения: Autohome» осталось в теле новости
check("кредит изображения убирается",
      "Autohome" in CreditSanitizer().apply(
          ARTICLE + "\nИсточник изображения: Autohome"), False)

check("хвост «Читайте также» отрезается",
      "Читайте также" in FooterLinkSanitizer().apply(
          ARTICLE + "\nЧитайте также\nДругая новость"), False)

check("короткий текст хвостом не режем в ноль",
      FooterLinkSanitizer().apply("Читайте также\nещё"), "Читайте также\nещё")

# ─── Оценка качества ────────────────────────────────────────────────────────

g = QualityGate()
check("нормальная статья проходит", g.evaluate(ARTICLE)[0], Verdict.PASSED)
check("короткий обрывок — звать следующего",
      g.evaluate("Две фразы. Всё.")[0], Verdict.NEEDS_FALLBACK)

# 23.08: trafilatura «спасла» две страницы, и обе оказались заслонами
check("заслон отвергается совсем",
      g.evaluate("Access Denied. You don't have permission to access this page.")[0],
      Verdict.REJECTED)

# 24.08, Le Figaro «DIRECT. Angers-Lille»: в теле оказалось меню сайта
MENU = "\n".join(["Toutes les infos sport", "Tous les formats", "À la une",
                  "Sports", "Émissions", "En plus", "Suivez-nous sur",
                  "A. Bermont (22')", "62'", "SCO", "0", "2", "LIL"] * 3)
check("меню сайта не проходит", g.evaluate(MENU)[0], Verdict.NEEDS_FALLBACK)

check("повторяющиеся строки не проходят",
      g.evaluate("\n".join(["Одна и та же строка вёрстки повторяется."] * 8))[0],
      Verdict.NEEDS_FALLBACK)

# ─── Цепочка целиком ────────────────────────────────────────────────────────

res = extract_article(LD.encode(), "https://example.com/a")
check("цепочка берёт json-ld первым", res.extractor, "json-ld")
check("и признаёт результат годным", res.verdict, Verdict.PASSED)

res2 = extract_article(DIRTY.encode(), "https://example.com/b")
check("без json-ld доходит до разборщика", res2.ok(), True)
check("плашка автора в итог не попала", "Иван Петров" in res2.text, False)

print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
