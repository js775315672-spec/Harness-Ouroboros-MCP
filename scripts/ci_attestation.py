#!/usr/bin/env python3
"""Read-only GitHub Actions attestation for development ledger records.

The local ledger schema is necessary but not sufficient: this module checks
GitHub's run API before a cycle is considered externally verified.
"""
import argparse,json,re,sys,urllib.error,urllib.request
from development_ledger import validate

RUN_URL=re.compile(r"^https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/actions/runs/([1-9][0-9]*)$")

def verify_record(record,fetch=None):
    match=RUN_URL.fullmatch(record["ci_url"])
    if not match:raise ValueError("invalid GitHub Actions URL")
    owner,repo,run_id=match.groups()
    url=f"https://api.github.com/repos/{owner}/{repo}/actions/runs/{run_id}"
    if fetch is None:
        def fetch(api_url):
            request=urllib.request.Request(api_url,headers={"Accept":"application/vnd.github+json","User-Agent":"Harness-Ouroboros-readonly-attestor"})
            with urllib.request.urlopen(request,timeout=10) as response:
                return json.load(response)
    data=fetch(url)
    if not isinstance(data,dict):raise ValueError("invalid API response")
    if data.get("status")!="completed" or data.get("conclusion")!="success":
        raise ValueError("CI not completed successfully")
    if data.get("html_url")!=record["ci_url"]:
        raise ValueError("CI URL mismatch")
    repository=data.get("repository")
    if not isinstance(repository,dict) or repository.get("full_name")!=f"{owner}/{repo}":
        raise ValueError("CI repository mismatch")
    # GitHub pull_request workflows may report a synthetic merge SHA. A strict
    # commit check must use head_commit SHA when present, or head_sha otherwise.
    head_commit=data.get("head_commit")
    observed=head_commit.get("id") if isinstance(head_commit,dict) else None
    if observed is None:observed=data.get("head_sha")
    if observed!=record["commit"]:
        raise ValueError("CI commit mismatch")
    return {"cycle":record["cycle"],"commit":record["commit"],"run_id":int(run_id),"verified":True}

def verify_ledger(records,fetch=None):
    validate(records)
    return [verify_record(record,fetch) for record in records]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("ledger")
    args=parser.parse_args()
    try:
        with open(args.ledger,encoding="utf-8") as stream:records=json.load(stream)
        result=verify_ledger(records)
    except (OSError,ValueError,urllib.error.URLError) as exc:
        print("BLOCK:",str(exc),file=sys.stderr)
        return 1
    print(json.dumps({"externally_verified_cycles":len(result),"runs":result},sort_keys=True))
    return 0

if __name__=="__main__":sys.exit(main())
