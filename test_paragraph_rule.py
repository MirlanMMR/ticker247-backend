# -*- coding: utf-8 -*-
"""Правило абзацев (решение владельца 09.10.2026, журнал J29).

До трёх абзацев — целиком; больше трёх — все, кроме последнего (даже если там
вывод). Числа знаков не участвуют. Тесты — на правило, а не на статью: любая
длина абзацев, любое их число, выбор редактора не вправе ни урезать тело, ни
отдать последний абзац.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import editor as ED
import textcut as TC

ok = fail = 0


def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✓ {name}")
    else:
        fail += 1
        print(f"  ✗ {name}")


def para(n, size=120):
    base = f"Абзац {n}: достаточно длинный связный текст новости, который читается как настоящий. "
    return (base * (size // len(base) + 1))[:size].rstrip(" ,") + "."


def article(n, size=120):
    return "\n\n".join(para(i, size) for i in range(1, n + 1))


# ── само правило, любое число абзацев и любая их длина ──
for size in (90, 200, 700, 1500):
    for n in range(1, 13):
        got = TC.card_text(article(n, size)).split("\n\n")
        want = n if n <= 3 else n - 1
        check(f"{n} абзацев по {size} знаков → {want}", len(got) == want)
        check(f"  непрерывный префикс статьи, последний не отдан или статья ≤3 (n={n}, {size})",
              got == [para(i, size) for i in range(1, want + 1)])

# ── тело не обрезается по знакам: один огромный абзац = «до трёх», показываем целиком ──
big = para(1, 5000)
check("один абзац на 5000 знаков — целиком", TC.card_text(big) == big)

# ── подписи и хвост издания не входят в тело и не считаются абзацем ──
tail = article(5) + "\n\nЧитайте также: другая новость"
got = TC.card_text(tail).split("\n\n")
check("хвост «читайте также» не абзац статьи: 5 абзацев → 4", len(got) == 4)
head = "Рубрика\n\n" + article(5)
check("вывеска раздела в начале не берётся", TC.card_text(head).split("\n\n")[0] == para(1))

# ── предохранитель памяти режет по абзацам и не искажает абзацы ──
capped = TC.cap_article(article(60, 900), cap=20000)
check("предохранитель: целые абзацы", all(p == para(i + 1, 900) for i, p in enumerate(capped.split("\n\n"))))
check("предохранитель: не больше предела", len(capped) <= 20000)

# ── редактор: выбор ИИ — только опора, тело строит правило по ЦЕЛОЙ статье ──
full = article(8, 300)
item = {"title": "T", "summary": "старая обрезка", "_full": full}
win = ED.split_paragraphs(full)
check("окно редактора — начало настоящих абзацев", win == TC.real_paragraphs(full)[:len(win)])
for picked in ([1], [1, 2], [3], [2, 5], [1, 2, 3, 4, 5, 6, 7, 8]):
    ok_, x, _ = ED.apply_verdict(item, {"publish": True, "paragraphs": picked}, win, [])
    got = x["summary"].split("\n\n")
    check(f"выбор {picked}: тело = абзацы 1..7 (последний, 8-й, не отдан)",
          ok_ and got == [para(i, 300) for i in range(1, 8)])
short = {"title": "T", "summary": "x", "_full": article(3, 300)}
w3 = ED.split_paragraphs(short["_full"])
ok_, x, _ = ED.apply_verdict(short, {"publish": True, "paragraphs": [1]}, w3, [])
check("статья из трёх абзацев — целиком, даже если ИИ выбрал один", x["summary"].split("\n\n") == [para(i, 300) for i in range(1, 4)])
# хвост издания после тела: редактор остановил тело на 4-м, дальше промо
promo = article(4, 300) + "\n\nПрочитайте, как уберечь ребёнка.\n\n" + para(6, 300)
it2 = {"title": "T", "summary": "x", "_full": promo}
w2 = ED.split_paragraphs(promo)
ok_, x, _ = ED.apply_verdict(it2, {"publish": True, "paragraphs": [1, 2, 3, 4]}, w2, [])
check("промо после тела не попадает; 4 абзаца → 3", x["summary"].split("\n\n") == [para(i, 300) for i in range(1, 4)])

print(f"\n{ok} ok, {fail} fail")
sys.exit(1 if fail else 0)
