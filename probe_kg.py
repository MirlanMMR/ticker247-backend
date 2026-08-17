# -*- coding: utf-8 -*-
import urllib.request, concurrent.futures
UA={"User-Agent":"Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120 Mobile Safari/537.36",
    "Accept":"application/rss+xml,application/xml,text/xml,*/*"}
C=[("Kaktus ?rss=1","https://kaktus.media/?rss=1"),
   ("Kabar rss","https://kabar.kg/rss/"),("Kabar ru","https://kabar.kg/ru/rss/"),
   ("Kabar news","https://kabar.kg/news/rss/"),
   ("VB rss.xml","https://www.vb.kg/rss.xml"),("VB rss","https://www.vb.kg/rss/"),
   ("Zakon rss.xml","https://www.zakon.kz/rss.xml"),("Zakon rss","https://www.zakon.kz/rss/"),
   ("Kun.uz rss","https://kun.uz/rss"),("Kun.uz uz","https://kun.uz/uz/rss"),
   ("Tengri rss","https://tengrinews.kz/rss/"),("Tengri news","https://tengrinews.kz/rss/news/"),
   ("Akipress","https://akipress.org/rss/news.rss"),("Akipress com","https://akipress.com/rss/news.rss"),
   ("Turmush","https://www.turmush.kg/rss"),
   ("Economist.kg","https://economist.kg/feed/"),
   ("Super.kg","https://super.kg/rss/"),
   ("Azattyk","https://www.azattyk.org/api/zrqiteuuir"),
   ("Podrobno.uz","https://podrobno.uz/rss/"),
   ("Gazeta.uz","https://www.gazeta.uz/ru/rss/"),
   ("Asia-Plus","https://asiaplustj.info/ru/rss.xml")]
def t(c):
    n,u=c
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=25)
        b=r.read(); return n,u,str(r.status),b.count(b"<item")+b.count(b"<entry")
    except Exception as e:
        return n,u,f"{type(e).__name__} {getattr(e,'code','')}",0
with concurrent.futures.ThreadPoolExecutor(12) as ex:
    for n,u,st,cnt in ex.map(t,C):
        print(f"  {'OK ' if cnt else 'нет'} {n:16} {(str(cnt) if cnt else st):>16}  {u}")
