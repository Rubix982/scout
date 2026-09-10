import json, urllib.request, collections

APP, KEY = "W6KM1UDIB3", "d1d7f2c8696e7b36837d5ed337c4a319"
H = {"X-Algolia-Application-Id": APP, "X-Algolia-API-Key": KEY,
     "Content-Type": "application/json", "User-Agent": "scout-research/0.1"}

def query(index, params):
    url = f"https://{APP}-dsn.algolia.net/1/indexes/{index}/query"
    req = urllib.request.Request(url, data=json.dumps({"params": params}).encode(),
                                 headers=H, method="POST")
    with urllib.request.urlopen(req, timeout=25) as f:
        return json.loads(f.read())

# 1. facet on company to size the company set
d = query("jobs_prod", "query=&hitsPerPage=0&facets=%5B%22company_name%22%5D&maxValuesPerFacet=1000")
companies = d["facets"]["company_name"]
print(f"jobs_prod: {d['nbHits']} jobs across {len(companies)} distinct companies")

# 2. paginate to collect company -> career_page_url and the evergreen/repost flags
seen, evergreen, repost, pages = {}, 0, 0, 0
page = 0
while True:
    d = query("jobs_prod", f"query=&hitsPerPage=1000&page={page}")
    for h in d["hits"]:
        evergreen += bool(h.get("evergreen"))
        repost += bool(h.get("repost"))
        cid = h.get("company_id") or h.get("company_name")
        if cid and cid not in seen:
            seen[cid] = {
                "name": h.get("company_name", ""),
                "career": h.get("company_career_page_url") or "",
                "site": h.get("company_url") or "",
            }
    pages += 1
    if page >= d.get("nbPages", 1) - 1:
        break
    page += 1
print(f"collected over {pages} page(s): {len(seen)} companies")
print(f"  evergreen-flagged jobs: {evergreen}   repost-flagged: {repost}")

# 3. how many career_page_urls point at an ATS we already support?
import re, sys
sys.path.insert(0, "/Users/saifulislam/code/scout")
from src.sources.ats.platforms import parse_board_url, SUPPORTED_PLATFORMS

hits = collections.Counter()
resolvable = []
for cid, info in seen.items():
    for url in (info["career"], info["site"]):
        parsed = parse_board_url(url)
        if parsed and parsed.token:
            hits[parsed.platform.value] += 1
            if parsed.is_supported:
                resolvable.append((info["name"], parsed.platform.value, parsed.token))
            break
print(f"\ncareer_page_url parses to an ATS board for {sum(hits.values())}/{len(seen)} companies")
for plat, n in hits.most_common():
    mark = "v1" if plat in {p.value for p in SUPPORTED_PLATFORMS} else "--"
    print(f"  [{mark}] {plat:16} {n}")
print(f"\nimmediately usable (v1 platforms, token present): {len(resolvable)}")
for name, plat, tok in resolvable[:12]:
    print(f"    {name[:34]:36} {plat:14} {tok}")

json.dump({"companies": seen}, open("eighty_k_companies.json", "w"), indent=2, sort_keys=True)
