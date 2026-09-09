import json, urllib.request, urllib.error, concurrent.futures as cf

UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

def get(url, timeout=15):
    try:
        r=urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(r, timeout=timeout) as f:
            return f.status, f.read()
    except urllib.error.HTTPError as e: return e.code, b""
    except Exception as e: return None, str(e).encode()[:60]

ENDPOINTS = {
 "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
 "lever":      "https://api.lever.co/v0/postings/{t}?mode=json",
 "ashby":      "https://api.ashbyhq.com/posting-api/job-board/{t}",
 "smartrec":   "https://api.smartrecruiters.com/v1/companies/{t}/postings",
 "recruitee":  "https://{t}.recruitee.com/api/offers/",
 "workable":   "https://apply.workable.com/api/v1/widget/accounts/{t}?details=true",
 "personio":   "https://{t}.jobs.personio.de/search.json",
 "teamtailor": "https://{t}.teamtailor.com/jobs.json",
}
# (platform, token) guesses drawn from the sheet's own companies
CASES=[("greenhouse","affirm"),("greenhouse","wolt"),("greenhouse","clari"),("greenhouse","medable"),
       ("greenhouse","strapi"),("greenhouse","checkly"),("greenhouse","billie"),
       ("lever","strapi"),("lever","checkly"),("lever","everli"),("lever","swissborg"),
       ("ashby","checkly"),("ashby","strapi"),("ashby","fingerprint"),
       ("smartrec","Wolt"),("smartrec","Everli"),
       ("recruitee","everli"),("workable","strapi"),("workable","billie"),
       ("personio","billie"),("teamtailor","wolt"),("teamtailor","swissborg")]

def one(c):
    plat,tok=c
    code,body=get(ENDPOINTS[plat].format(t=tok))
    n=0
    if code==200:
        try:
            d=json.loads(body)
            n = d.get("meta",{}).get("total") if isinstance(d,dict) and "meta" in d else (
                len(d) if isinstance(d,list) else len(d.get("jobs",d.get("offers",d.get("data",[])))) )
        except Exception: n="?"
    return f"{'OK ' if code==200 else '   '} {plat:11} {tok:14} {str(code):5} jobs={n}"

with cf.ThreadPoolExecutor(12) as ex:
    for line in ex.map(one, CASES): print(line)
