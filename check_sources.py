"""
Еженедельная проверка здоровья источников (APP_SOURCES + все RSS-источники
в fetch_news.py). Источники умирают со временем (меняют URL, блокируют
User-Agent, закрываются) — эта проверка ловит такое автоматически, без
участия человека.

Не требует обновления приложения — чисто бэкенд, отдельный запуск GitHub
Actions по расписанию (см. .github/workflows/check_sources.yml).

Если находит мёртвые источники — выходит с ошибкой (exit 1), чтобы GitHub
показал красный крестик и прислал email-уведомление владельцу репозитория.
"""
import sys
import requests

from fetch_news import RSS_SOURCES, BROWSER_HEADERS, RETIRED_SOURCES

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

    print(f"\nИтого: {len(urls) - len(dead)} живых, {len(dead)} мёртвых/заблокированных")
    if dead:
        print("\n⚠️ ПРОБЛЕМНЫЕ ИСТОЧНИКИ:")
        for name, url, status in dead:
            print(f"  - {name} ({status}): {url}")
        sys.exit(1)

if __name__ == "__main__":
    main()
