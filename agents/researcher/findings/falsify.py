import json, urllib.request, urllib.error
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
def get(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=15) as f:
            return f.status, f.read()
    except urllib.error.HTTPError as e: return e.code, b""
    except Exception as e: return None, str(e).encode()[:60]

E={"greenhouse":"https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
   "lever":"https://api.lever.co/v0/postings/{t}?mode=json",
   "ashby":"https://api.ashbyhq.com/posting-api/job-board/{t}",
   "smartrec":"https://api.smartrecruiters.com/v1/companies/{t}/postings",
   "workable":"https://apply.workable.com/api/v1/widget/accounts/{t}?details=true"}

print("=== CONTROL: nonsense token (does 200 mean anything?) ===")
for p,u in E.items():
    c,b=get(u.format(t="zzqqxnotarealcompany7391"))
    print(f"  {p:11} {str(c):5} body={b[:70]!r}")

print("\n=== real tokens: what's the actual job count? ===")
for p,t in [("smartrec","Wolt"),("workable","strapi"),("workable","billie"),("ashby","checkly"),("lever","swissborg")]:
    c,b=get(E[p].format(t=t))
    if c==200:
        d=json.loads(b)
        if isinstance(d,dict):
            keys=list(d.keys())
            cnt={k:(len(v) if isinstance(v,list) else v) for k,v in d.items() if k in("content","jobs","offers","totalFound","total")}
            print(f"  {p:11} {t:12} keys={keys[:6]} counts={cnt}")
        else: print(f"  {p:11} {t:12} list len={len(d)}")
