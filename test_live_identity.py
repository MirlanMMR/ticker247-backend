# -*- coding: utf-8 -*-
"""Проверки опознания канала. Случаи настоящие, из ленты 28.08.2026."""
import sys

from live_identity import alien_script, name_matches, verdict

ok = fail = 0


def check(name, got, want=True):
    global ok, fail
    if got == want:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}: получили {got!r}, ждали {want!r}")


# ─── Двое самозванцев, попавших в ленту ─────────────────────────────────────

check("турецкий NTV не выдаёт себя за русский НТВ",
      name_matches("НТВ", "NTV"), False)
check("и потому отвергается",
      verdict("НТВ", "NTV", "NTV Canlı Yayın - Full HD İzle", "ru") != "")

# Имя тайваньского CNEWS начинается так же — по имени его не отличить.
# Выдаёт его название эфира
check("тайваньский CNEWS по имени неотличим",
      name_matches("CNEWS", "CNEWS匯流新聞網"))
check("но иероглифы в эфире его выдают",
      alien_script("台北市議會定期大會第08次會議【CNEWS】", "fr"), "иероглифы")
check("и он отвергается",
      verdict("CNEWS", "CNEWS匯流新聞網",
              "台北市議會定期大會第08次會議【CNEWS】", "fr") != "")


# ─── Настоящие каналы отвергать нельзя ──────────────────────────────────────
#
# Вещатели пишут себя по-разному, и придирка к скобке стоит нам живого канала.

check("скобки не мешают", name_matches("ABC News Australia", "ABC News (Australia)"))
check("сокращение не мешает", name_matches("Bloomberg TV", "Bloomberg Television"))
check("регистр не мешает", name_matches("Africanews", "africanews"))
check("уточнение в скобках не мешает",
      name_matches("euronews (français)", "euronews (en français)"))
check("русский канал в русском пуле проходит",
      verdict("Настоящее Время", "Настоящее Время",
              "Прямой эфир телеканала Настоящее Время", "ru"), "")
check("французский канал проходит",
      verdict("franceinfo", "franceinfo",
              "franceinfo - DIRECT TV - actualité France", "fr"), "")


# ─── Письмо, которого в пуле быть не может ──────────────────────────────────

check("кириллица в французском пуле — признак чужого",
      alien_script("Прямой эфир", "fr"), "кириллица")
check("кириллица в русском пуле законна",
      alien_script("Прямой эфир Euronews", "ru"), "")
# Латиницу в русском пуле НЕ ловим: названия и вкрапления законны, и на этом
# легко потерять живой канал
check("латиница в русском пуле допустима",
      alien_script("DW на русском 24/7", "ru"), "")
check("пустое название не роняет проверку", alien_script("", "es"), "")
check("неизвестное имя не придирается", name_matches("", "Что угодно"))

print(f"\nпройдено {ok}, провалено {fail}")
sys.exit(1 if fail else 0)
