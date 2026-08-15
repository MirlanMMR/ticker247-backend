# -*- coding: utf-8 -*-
import urllib.request, concurrent.futures
UA={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
C=[("CO","Colorado Newsline","https://coloradonewsline.com/feed/"),
   ("MI","Michigan Advance","https://michiganadvance.com/feed/"),
   ("NV","Nevada Current","https://nevadacurrent.com/feed/"),
   ("GA","Georgia Recorder","https://georgiarecorder.com/feed/"),
   ("PA","Pennsylvania Capital-Star","https://penncapital-star.com/feed/"),
   ("FL","Florida Phoenix","https://floridaphoenix.com/feed/"),
   ("OH","Ohio Capital Journal","https://ohiocapitaljournal.com/feed/"),
   ("VA","Virginia Mercury","https://virginiamercury.com/feed/"),
   ("MN","Minnesota Reformer","https://minnesotareformer.com/feed/"),
   ("AZ","Arizona Mirror","https://azmirror.com/feed/"),
   ("NC","NC Newsline","https://ncnewsline.com/feed/"),
   ("MO","Missouri Independent","https://missouriindependent.com/feed/")]
def t(c):
    st,name,url=c
    try:
        r=urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=30)
        b=r.read(); return st,name,b.count(b"<item"), b.count(b"<media:content")+b.count(b"<enclosure")
    except Exception as e: return st,name,0,type(e).__name__
with concurrent.futures.ThreadPoolExecutor(12) as ex:
    for st,name,n,img in ex.map(t,C):
        print(f"  {'OK ' if n else 'нет'} {st} {name:28} материалов {n if n else '—':>3} | фото {img if n else '—'}")
