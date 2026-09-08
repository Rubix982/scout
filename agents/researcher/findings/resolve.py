import json,urllib.request,urllib.error,concurrent.futures as cf,itertools
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120"}
def get(u):
    try:
        with urllib.request.urlopen(urllib.request.Request(u,headers=UA),timeout=12) as f: return f.status,f.read()
    except urllib.error.HTTPError as e: return e.code,b""
    except Exception: return None,b""

def count(plat,body):
    try: d=json.loads(body)
    except Exception: return 0
    if plat=="lever": return len(d) if isinstance(d,list) else 0
    if plat=="ashby": return len(d.get("jobs",[]))
    if plat=="greenhouse": return d.get("meta",{}).get("total",len(d.get("jobs",[])))
    if plat=="smartrec": return d.get("totalFound",0)
    if plat=="workable": return len(d.get("jobs",[]))
    return 0

E={"greenhouse":"https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
   "greenhouse_eu":"https://boards-api.eu.greenhouse.io/v1/boards/{t}/jobs",
   "lever":"https://api.lever.co/v0/postings/{t}?mode=json",
   "ashby":"https://api.ashbyhq.com/posting-api/job-board/{t}",
   "smartrec":"https://api.smartrecruiters.com/v1/companies/{t}/postings",
   "workable":"https://apply.workable.com/api/v1/widget/accounts/{t}?details=true"}

def candidates(name,domain):
    stem=domain.split(".")[0]
    n=name.lower().replace(" ","").replace(".","")
    nd=name.lower().replace(" ","-")
    return list(dict.fromkeys([n,stem,nd,name.lower().replace(" ",""),name.replace(" ",""),name.capitalize()]))

def resolve(name,domain):
    found=[]
    jobs=[(p,t) for p in E for t in candidates(name,domain)]
    def probe(pt):
        p,t=pt; c,b=get(E[p].format(t=t))
        if c==200:
            n=count(p.replace("_eu",""),b)
            if n>0: return (p,t,n)
        return None
    with cf.ThreadPoolExecutor(16) as ex:
        for r in ex.map(probe,jobs):
            if r: found.append(r)
    return found

CO=[("Checkly","checklyhq.com"),("Cherry Ventures","cherryventures.com"),("Clari","clari.com"),
    ("Medable","medable.com"),("Strapi","strapi.io"),("Fingerprint","fingerprint.com"),
    ("Wolt","wolt.com"),("Everli","everli.com"),("Honeypot","honeypot.io"),("Affirm","affirm.com")]
for name,dom in CO:
    r=resolve(name,dom)
    print(f"{name:16} {(str(r) if r else 'UNRESOLVED')}")
