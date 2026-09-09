"""R-002: measure ATS board-token resolution across the real company list.

Answers the falsification criterion in plan.md lens 4: does resolution clear
~50% across the full sheet, including link-seeding? Research only -- no writes,
no project imports beyond config/client.

Validation is content-based, never status-code-based: SmartRecruiters returns
HTTP 200 with totalFound:0 for companies that do not exist (R-001).
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import re
import sys
import urllib.error
import urllib.request

UA = {"User-Agent": "scout-research/0.1 (+https://github.com/Rubix982/scout)"}

ENDPOINTS = {
    "greenhouse":    "https://boards-api.greenhouse.io/v1/boards/{t}/jobs",
    "greenhouse_eu": "https://boards-api.eu.greenhouse.io/v1/boards/{t}/jobs",
    "lever":         "https://api.lever.co/v0/postings/{t}?mode=json",
    "ashby":         "https://api.ashbyhq.com/posting-api/job-board/{t}",
    "workable":      "https://apply.workable.com/api/v1/widget/accounts/{t}?details=true",
    "smartrec":      "https://api.smartrecruiters.com/v1/companies/{t}/postings",
}
V1_PLATFORMS = {"greenhouse", "greenhouse_eu", "lever", "ashby"}

LINK_PATTERNS = [
    ("greenhouse_eu", r"boards\.eu\.greenhouse\.io/([a-z0-9_-]+)"),
    ("greenhouse",    r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9_-]+)"),
    ("lever",         r"jobs\.(?:eu\.)?lever\.co/([a-z0-9_-]+)"),
    ("ashby",         r"jobs\.ashbyhq\.com/([a-zA-Z0-9_.-]+)"),
    ("workable",      r"apply\.workable\.com/([a-z0-9_-]+)"),
    ("smartrec",      r"careers\.smartrecruiters\.com/([a-zA-Z0-9_-]+)"),
]
SKIP_TOKENS = {"embed", "job_board", "www", "jobs", "api", "careers", "boards", "j", "o"}


def fetch(url: str):
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=15) as f:
            return f.status, f.read()
    except urllib.error.HTTPError as e:
        return e.code, b""
    except Exception:
        return None, b""


def role_count(platform: str, body: bytes) -> int:
    """Number of open roles, or 0. Content-based by design."""
    try:
        d = json.loads(body)
    except Exception:
        return 0
    p = platform.replace("_eu", "")
    if p == "lever":
        return len(d) if isinstance(d, list) else 0
    if p == "ashby":
        return len(d.get("jobs") or [])
    if p == "greenhouse":
        meta = d.get("meta") or {}
        return int(meta.get("total") or len(d.get("jobs") or []))
    if p == "workable":
        return len(d.get("jobs") or [])
    if p == "smartrec":
        return int(d.get("totalFound") or 0)
    return 0


def candidates(name: str) -> list[str]:
    n = name.strip().lower()
    n = re.sub(r"\.(io|co|com|dev|studio|inc|ai|so|cx)$", "", n)
    n = n.split("/")[0].strip()
    words = re.split(r"[^a-z0-9]+", n)
    words = [w for w in words if w]
    out = [
        "".join(words),
        "-".join(words),
        words[0] if words else "",
    ]
    # drop generic trailing words like "companies", "talent", "jobs"
    trimmed = [w for w in words if w not in {"companies", "company", "talent", "jobs", "careers", "solutions"}]
    if trimmed and trimmed != words:
        out += ["".join(trimmed), "-".join(trimmed)]
    seen, res = set(), []
    for c in out:
        if len(c) >= 2 and c not in seen and c not in SKIP_TOKENS:
            seen.add(c)
            res.append(c)
    return res


def seeds_from_link(link: str) -> list[tuple[str, str]]:
    hits = []
    for plat, pat in LINK_PATTERNS:
        for m in re.findall(pat, link or ""):
            if m.lower() not in SKIP_TOKENS:
                hits.append((plat, m))
    return hits


def probe(job):
    company, plat, tok, source = job
    code, body = fetch(ENDPOINTS[plat].format(t=tok))
    n = role_count(plat, body) if code == 200 else 0
    return company, plat, tok, source, code, n


def main():
    from src import config
    from src.clients.gsuite import get_gsheet_client

    ws = get_gsheet_client().open_by_url(config.sheet_url()).worksheet("Sheet1")
    rows = [r for r in ws.get_all_values()[1:] if any(c.strip() for c in r)]
    companies = [(r[0].strip(), (r[2].strip() if len(r) > 2 else "")) for r in rows if r[0].strip()]
    print(f"companies: {len(companies)}", file=sys.stderr)

    jobs, seeded = [], {}
    for name, link in companies:
        for plat, tok in seeds_from_link(link):
            seeded.setdefault(name, []).append((plat, tok))
            jobs.append((name, plat, tok, "link_seed"))
        for tok in candidates(name):
            for plat in ENDPOINTS:
                jobs.append((name, plat, tok, "generated"))

    print(f"probes: {len(jobs)}", file=sys.stderr)
    results = []
    with cf.ThreadPoolExecutor(8) as ex:
        for i, r in enumerate(ex.map(probe, jobs), 1):
            results.append(r)
            if i % 150 == 0:
                print(f"  ...{i}/{len(jobs)}", file=sys.stderr)

    hits = {}
    for company, plat, tok, source, code, n in results:
        if code == 200 and n > 0:
            prev = hits.get(company)
            # prefer link_seed, then v1 platforms, then higher role count
            rank = (source != "link_seed", plat not in V1_PLATFORMS, -n)
            if prev is None or rank < prev[0]:
                hits[company] = (rank, plat, tok, n, source)

    out = {
        "total": len(companies),
        "resolved": {c: {"platform": v[1], "token": v[2], "roles": v[3], "via": v[4]}
                     for c, v in hits.items()},
        "unresolved": [c for c, _ in companies if c not in hits],
        "link_seeds": seeded,
    }
    with open("agents/researcher/findings/sweep_results.json", "w") as f:
        json.dump(out, f, indent=2, sort_keys=True)

    print("\n=== RESOLVED ===")
    for c, v in sorted(out["resolved"].items(), key=lambda kv: -kv[1]["roles"]):
        print(f"  {c:24} {v['platform']:14} {v['token']:20} {v['roles']:4d} roles  [{v['via']}]")
    print("\n=== UNRESOLVED ===")
    for c in out["unresolved"]:
        print(f"  {c}")

    n_res, n_tot = len(out["resolved"]), out["total"]
    v1 = sum(1 for v in out["resolved"].values() if v["platform"] in V1_PLATFORMS)
    print(f"\n=== SUMMARY ===")
    print(f"  resolved:        {n_res}/{n_tot}  ({100*n_res/n_tot:.0f}%)")
    print(f"  within v1 scope: {v1}/{n_tot}  ({100*v1/n_tot:.0f}%)")
    print(f"  total roles:     {sum(v['roles'] for v in out['resolved'].values())}")
    from collections import Counter
    print(f"  by platform:     {dict(Counter(v['platform'] for v in out['resolved'].values()))}")
    print(f"  by method:       {dict(Counter(v['via'] for v in out['resolved'].values()))}")


if __name__ == "__main__":
    main()
