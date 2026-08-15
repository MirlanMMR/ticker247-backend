# -*- coding: utf-8 -*-
"""Ищет речевые радиостанции по странам пулов в открытой базе radio-browser.

Запускается вручную из GitHub Actions: из домашней сети база отвечает с
перебоями, из раннера — надёжно.

Отбираем по трём признакам: страна, отметка «эфир проверен» и метки,
говорящие о разговорном формате. Окончательное решение всё равно за
человеком — машина не измерит, читают ли новости дважды в час.
"""
import json
import urllib.request
from collections import OrderedDict

MIRRORS = ["de1", "nl1", "at1", "fi1", "de2"]

# Страны пулов. Первой идёт домашняя страна пула
COUNTRIES = OrderedDict([
    ("ru", ["KG", "KZ", "UZ", "TJ", "RU"]),
    ("en", ["US", "GB", "IE", "CA", "AU", "NZ", "IN", "NG", "ZA", "JM"]),
    ("es", ["MX", "ES", "AR", "CO", "PE", "CL", "VE", "EC", "GT", "CR"]),
    ("pt", ["BR", "PT", "AO", "MZ"]),
])

TALK_TAGS = ("news", "talk", "noticias", "notícias", "informa", "actualidad",
             "jornal", "разговор", "новости", "public radio", "current affairs")


def fetch(path):
    last = None
    for host in MIRRORS:
        for scheme in ("https", "http"):
            try:
                req = urllib.request.Request(f"{scheme}://{host}.api.radio-browser.info{path}",
                                             headers={"User-Agent": "Ticker247/1.0 (news app)"})
                return json.load(urllib.request.urlopen(req, timeout=45))
            except Exception as e:
                last = e
    raise RuntimeError(f"ни одно зеркало не ответило: {last}")


def main():
    for pool, codes in COUNTRIES.items():
        print(f"\n{'=' * 70}\nПУЛ {pool.upper()}\n{'=' * 70}")
        for code in codes:
            try:
                stations = fetch(f"/json/stations/bycountrycodeexact/{code}")
            except Exception as e:
                print(f"\n  {code}: ошибка — {e}")
                continue
            live = [s for s in stations if s.get("lastcheckok") == 1 and s.get("url_resolved")]
            talk = [s for s in live
                    if any(t in ((s.get("tags") or "") + " " + s.get("name", "")).lower()
                           for t in TALK_TAGS)]
            talk.sort(key=lambda s: -(s.get("clickcount") or 0))
            print(f"\n  ── {code}: всего {len(stations)}, в эфире {len(live)}, "
                  f"речевых {len(talk)}")
            for s in talk[:6]:
                print(f"     {s['name'][:36]:38} {str(s.get('codec')):5} "
                      f"{s.get('bitrate') or 0:3}k  {(s.get('tags') or '')[:38]}")
                print(f"       {s['url_resolved'][:100]}")


if __name__ == "__main__":
    main()
