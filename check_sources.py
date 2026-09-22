"""
Еженедельная проверка здоровья источников (APP_SOURCES + все RSS-источники
в fetch_news.py). Источники умирают со временем (меняют URL, блокируют
User-Agent, закрываются) — эта проверка ловит такое автоматически, без
участия человека.

Не требует обновления приложения — чисто бэкенд, отдельный запуск GitHub
Actions по расписанию (см. .github/workflows/check_sources.yml).

Один-два источника почти всегда отвечают с перебоями (429 из-за лимита,
секундный таймаут, антибот) — это шум, а не авария, и сборщик новостей
такие источники и так пропускает по отдельности, не трогая остальные.
Поэтому тревогу (exit 1 → красный крестик и письмо владельцу) поднимаем,
только если не отвечает 40% источников и больше — это уже похоже на
общую проблему (сеть, ключи, блокировка раннера), а не на дохлую ленту.
Отчёт по единичным сбоям всё равно печатается каждый раз, просто без exit 1.
"""
import sys
import requests

from fetch_news import RSS_SOURCES, BROWSER_HEADERS, RETIRED_SOURCES

DEAD_SHARE_THRESHOLD = 0.4

def collect_rss_urls():
    # Отставленные не проверяем: они мертвы намеренно, и еженедельный отчёт
    # о них — шум, из-за которого перестают читать весь отчёт
    return [(src["source"], src["url"]) for src in RSS_SOURCES
            if src.get("url", "").startswith("http")
            and not any(dead in src["url"].lower() for dead in RETIRED_SOURCES)]

def check_url(name, url):
    try:
        r = requests.get(url, timeout=10, headers=BROWSER_HEADERS)
        return r.status_code
    except Exception as e:
        return f"ERROR: {e}"

def main():
    urls = collect_rss_urls()
    print(f"Проверяю {len(urls)} источников...")
    dead = []
    for name, url in urls:
        status = check_url(name, url)
        ok = status == 200
        mark = "✅" if ok else "❌"
        print(f"{mark} {status}  {name}  {url}")
        if not ok:
            dead.append((name, url, status))

    dead_share = len(dead) / len(urls) if urls else 0
    print(f"\nИтого: {len(urls) - len(dead)} живых, {len(dead)} мёртвых/заблокированных "
          f"({dead_share:.0%})")
    if dead:
        print("\n⚠️ ПРОБЛЕМНЫЕ ИСТОЧНИКИ:")
        for name, url, status in dead:
            print(f"  - {name} ({status}): {url}")

    if dead_share >= DEAD_SHARE_THRESHOLD:
        print(f"\n❌ Не отвечает {dead_share:.0%} источников (порог {DEAD_SHARE_THRESHOLD:.0%}) "
              f"— похоже на общий сбой, а не на пару дохлых лент.")
        sys.exit(1)
    elif dead:
        print(f"\nℹ️ {len(dead)} источник(ов) не отвечает, но это меньше порога "
              f"{DEAD_SHARE_THRESHOLD:.0%} — остальные добираются как обычно, тревогу не поднимаю.")

if __name__ == "__main__":
    main()
