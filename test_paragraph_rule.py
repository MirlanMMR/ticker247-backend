# -*- coding: utf-8 -*-
"""Правило абзацев (решение владельца 09.10.2026, журнал J29).

До трёх абзацев — целиком; больше — ⌈2n/3⌉, но не больше восьми (4→3, 8→6, 12→8);
последний абзац остаётся за кадром даже с выводом. Числа знаков не участвуют. Тесты — на правило, а не на статью: любая
длина абзацев, любое их число, выбор редактора не вправе ни урезать тело, ни
отдать последний абзац.
"""
import math
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
for size in (90, 200, 700, 1400):
    for n in range(1, 41):
        got = TC.card_text(article(n, size)).split("\n\n")
        want = n if n <= 3 else min(math.ceil(2 * n / 3), 8)
        check(f"{n} абзацев по {size} знаков → {want}", len(got) == want)
        check(f"  непрерывный префикс статьи; при n≥4 последний не отдан (n={n}, {size})",
              got == [para(i, size) for i in range(1, want + 1)])

check("заявленные точки владельца: 4→3, 8→6, 12→8", [TC.shown_count(n) for n in (4, 8, 12)] == [3, 6, 8])
check("последний абзац не отдаётся никогда (n≥4)", all(TC.shown_count(n) < n for n in range(4, 200)))
check("потолок восемь", all(TC.shown_count(n) <= 8 for n in range(4, 200)))
check("доля не убывает с ростом статьи", all(TC.shown_count(n) <= TC.shown_count(n + 1) for n in range(1, 200)))

# ── гигантский кусок (сбой разбора, нет переводов строк) делится по предложениям ──
sent = "Это отдельное законченное предложение новости с цифрами и фактами для проверки правила. "
giant = (sent * 60).strip()
parts = TC.real_paragraphs(giant)
check("гигантский абзац делится на куски", len(parts) > 3 and all(len(p) <= 800 for p in parts))
shown = TC.card_text(giant)
check("гигант: показана часть, а не всё", 0 < len(shown) < len(giant))
check("гигант: рез по границе предложения", shown.rstrip().endswith("."))
normal = para(1, 1400)
check("абзац в пределах 1500 знаков не делится", TC.real_paragraphs(normal) == [normal])

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
# редактор КОМПОНУЕТ (отсекает воду), код держит рамку: заход, нижняя планка (3), потолок K, без последнего
expect = {
    (1,): [1, 2, 3],             # выбрал слишком мало — добираем до планки «три»
    (1, 2): [1, 2, 3],
    (3,): [1, 2, 3],             # заход остаётся всегда
    (2, 5): [1, 2, 5],           # вода между ними (3, 4, 6) отсечена — это и есть компоновка
    (1, 2, 3, 4, 5, 6, 7): [1, 2, 3, 4, 5, 6],   # потолок K=6 из 8
    (8,): [1, 2, 3, 4, 5, 6],    # выбрал только последний — он не берётся, каркас по правилу
}
for picked, want_idx in expect.items():
    ok_, x, _ = ED.apply_verdict(item, {"publish": True, "paragraphs": list(picked)}, win, [])
    got = x["summary"].split("\n\n")
    check(f"выбор {list(picked)} → абзацы {want_idx}", ok_ and got == [para(i, 300) for i in want_idx])
# замок цифр: «второстепенный» абзац с главными цифрами не теряется (Sputnik KG 06.10)
facts = [para(i, 300) for i in range(1, 9)]
facts[3] = "Абзац 4: построено 12 электростанций, погибли 1455 человек, ущерб оценили в 340 млн."
fi = {"title": "T", "summary": "x", "_full": "\n\n".join(facts)}
fw = ED.split_paragraphs(fi["_full"])
ok_, x, _ = ED.apply_verdict(fi, {"publish": True, "paragraphs": [1, 2, 5, 6]}, fw, [])
check("абзац с потерянными цифрами возвращён", ok_ and facts[3] in x["summary"])
check("и вода без цифр по-прежнему отсечена", facts[2] not in x["summary"])
check("последний абзац не отдан", facts[7] not in x["summary"])
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
