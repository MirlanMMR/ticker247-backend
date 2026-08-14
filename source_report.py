"""
Досье на источники — чем каждый полезен ленте.

Считает по данным, которые у нас уже есть: сколько статей источник дал, сколько
дошло до ленты, длину текста, наличие фото, свежесть, уникальность темы.

Запуск: python3 source_report.py
"""
import json
import urllib.request
from collections import defaultdict

DB = "https://ticker247-default-rtdb.asia-southeast1.firebasedatabase.app"
POOLS = ["ru", "en", "es", "pt"]


def fetch(pool):
    with urllib.request.urlopen(f"{DB}/news/{pool}.json", timeout=30) as r:
        return json.load(r).get("items", [])


def main():
    stat = defaultdict(lambda: {
        "n": 0, "chars": 0, "photo": 0, "urgent": 0,
        "pools": set(), "age_h": [], "titles": [],
    })
    for pool in POOLS:
        for i in fetch(pool):
            src = i.get("source") or "?"
            s = stat[src]
            s["n"] += 1
            s["chars"] += len((i.get("summary") or "").strip())
            s["photo"] += 1 if i.get("imageUrl") else 0
            s["urgent"] += 1 if i.get("category") == "URGENT" else 0
            s["pools"].add(pool)
            s["titles"].append((i.get("origTitle") or i.get("title") or "").lower())

    # Уникальность: доля тем, которых нет у других источников
    all_words = defaultdict(set)
    for src, s in stat.items():
        for t in s["titles"]:
            for w in {w for w in t.split() if len(w) > 5}:
                all_words[w].add(src)

    rows = []
    for src, s in stat.items():
        if s["n"] < 2:
            continue
        avg = s["chars"] // s["n"]
        photo = s["photo"] * 100 // s["n"]
        uniq_words = 0
        total_words = 0
        for t in s["titles"]:
            for w in {w for w in t.split() if len(w) > 5}:
                total_words += 1
                if len(all_words[w]) == 1:
                    uniq_words += 1
        uniq = uniq_words * 100 // max(total_words, 1)
        rows.append((s["n"], avg, photo, uniq, s["urgent"], len(s["pools"]), src))

    rows.sort(reverse=True)
    print(f"{'источник':22} {'статей':>6} {'знаков':>7} {'фото':>5} {'уник':>5} {'срочн':>6} {'пулов':>6}")
    print("─" * 66)
    for n, avg, photo, uniq, urg, pools, src in rows:
        print(f"{src[:22]:22} {n:6} {avg:7} {photo:4}% {uniq:4}% {urg:6} {pools:6}")

    print("\n── Кандидаты на вылет ──")
    for n, avg, photo, uniq, urg, pools, src in rows:
        why = []
        if avg < 150:
            why.append(f"текст {avg} знаков")
        if photo < 40:
            why.append(f"фото у {photo}%")
        if uniq < 15:
            why.append(f"уникальность {uniq}%")
        if why:
            print(f"  {src[:22]:22} — {', '.join(why)}")


if __name__ == "__main__":
    main()
