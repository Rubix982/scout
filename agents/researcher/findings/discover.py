import re, urllib.request, urllib.error, concurrent.futures as cf
UA={"User-Agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"}

PATTERNS=[
 ("greenhouse", r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9_-]+)"),
 ("greenhouse", r"greenhouse\.io/v1/boards/([a-z0-9_-]+)"),
 ("lever",      r"jobs\.(?:eu\.)?lever\.co/([a-z0-9_-]+)"),
 ("ashby",      r"jobs\.ashbyhq\.com/([a-zA-Z0-9_.-]+)"),
 ("smartrec",   r"careers\.smartrecruiters\.com/([a-zA-Z0-9_-]+)"),
 ("workable",   r"apply\.workable\.com/([a-z0-9_-]+)"),
 ("teamtailor", r"([a-z0-9-]+)\.teamtailor\.com"),
 ("personio",   r"([a-z0-9-]+)\.jobs\.personio\.(?:de|com)"),
 ("recruitee",  r"([a-z0-9-]+)\.recruitee\.com"),
 ("rippling",   r"ats\.rippling\.com/([a-z0-9-]+)"),
]
SKIP={"embed","job_board","www","jobs","api","careers","help","support","boards"}

def fetch(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers=UA),timeout=20) as f:
            return f.read(900000).decode("utf-8","ignore")
    except Exception: return ""

def discover(domain):
    hits={}
    for path in ["/careers","/jobs","/company/careers","/about/careers",""]:
        html=fetch(f"https://{domain}{path}")
        if not html: continue
        for plat,pat in PATTERNS:
            for m in re.findall(pat,html):
                if m.lower() not in SKIP: hits.setdefault(plat,set()).add(m)
        if hits: return path or "/", hits
    return None, hits

TARGETS=["clari.com","medable.com","strapi.io","fingerprint.com","checklyhq.com",
         "honeypot.io","wolt.com","everli.com","tendermint.com","sideos.io"]
def one(d):
    p,h=discover(d)
    return f"{d:20} via {str(p):22} {({k:sorted(v)[:2] for k,v in h.items()} if h else 'NO ATS FOUND')}"
with cf.ThreadPoolExecutor(10) as ex:
    for l in ex.map(one,TARGETS): print(l)
