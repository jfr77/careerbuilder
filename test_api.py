#!/usr/bin/env python3
"""Quick endpoint smoke test against a running backend (PORT env var, default 8787).

Run:  .venv/bin/python test_api.py
Covers every router; LLM endpoints are expected to return 503 when
ANTHROPIC_API_KEY is unset (that counts as a pass — graceful degradation).
"""

import os
import sys

import requests

BASE = f"http://localhost:{os.environ.get('PORT', '8787')}"
PASS, FAIL = 0, 0


def check(name, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


def llm_ok(resp):
    """LLM endpoints: success, or a clean 503 when no API key is configured."""
    return resp.status_code == 200 or (
        resp.status_code == 503 and "ANTHROPIC_API_KEY" in resp.json().get("detail", ""))


def main():
    r = requests.get(f"{BASE}/api/health", timeout=5)
    check("health", r.status_code == 200 and r.json()["ok"])
    llm_enabled = r.json().get("llm_available", False)
    print(f"  (llm_available={llm_enabled})")

    # ---- profiles
    r = requests.get(f"{BASE}/api/profiles")
    check("list profiles", r.status_code == 200 and len(r.json()) >= 1)
    julian = next(p for p in r.json() if p["name"] == "Julian")

    r = requests.post(f"{BASE}/api/profiles", json={"name": "Test Profile", "location": "Berlin"})
    check("create profile", r.status_code == 201)
    test_id = r.json()["id"]

    r = requests.patch(f"{BASE}/api/profiles/{test_id}",
                       json={"skills": ["Excel"], "learning_goals": "marketing"})
    check("update profile", r.status_code == 200 and r.json()["skills"] == ["Excel"])

    # ---- second profile isolation: empty pipeline, no scores, empty chat
    r = requests.get(f"{BASE}/api/pipeline", params={"profile_id": test_id})
    check("new profile: empty pipeline", r.status_code == 200 and r.json() == [])
    r = requests.get(f"{BASE}/api/chat", params={"profile_id": test_id})
    check("new profile: empty chat", r.status_code == 200 and r.json() == [])
    r = requests.get(f"{BASE}/api/jobs", params={"profile_id": test_id})
    check("new profile: jobs all unscored",
          r.status_code == 200 and all(j["fit_score"] is None for j in r.json()["results"]))

    # ---- query-time filtering + facets + saved filters
    r = requests.get(f"{BASE}/api/jobs", params={"profile_id": test_id, "q": "zzz-no-such-job-zzz"})
    check("jobs filter: q narrows to zero", r.status_code == 200 and r.json()["total"] == 0)
    r = requests.get(f"{BASE}/api/jobs", params={"profile_id": test_id, "status": "all", "page_size": 1})
    check("jobs filter: pagination caps results",
          r.status_code == 200 and len(r.json()["results"]) <= 1 and "total" in r.json())
    r = requests.get(f"{BASE}/api/jobs/facets")
    check("jobs facets", r.status_code == 200 and "companies" in r.json())
    r = requests.post(f"{BASE}/api/jobs/prompt-filter", params={"profile_id": test_id},
                      json={"prompt": "internships in Munich posted in the last 2 weeks"})
    check("prompt-filter (or graceful 503)", llm_ok(r))
    r = requests.post(f"{BASE}/api/filters", json={"name": "smoke test filter",
                                                   "filter": {"q": "intern", "language": "en"}})
    check("saved filter create", r.status_code == 201 and r.json()["filter"].get("q") == "intern")
    sf_id = r.json().get("id")
    r = requests.get(f"{BASE}/api/filters")
    check("saved filter listed", r.status_code == 200 and any(f["id"] == sf_id for f in r.json()))
    r = requests.delete(f"{BASE}/api/filters/{sf_id}")
    check("saved filter delete", r.status_code == 200)

    # ---- pipeline CRUD
    r = requests.get(f"{BASE}/api/pipeline", params={"profile_id": julian["id"]})
    check("julian pipeline seeded", r.status_code == 200 and len(r.json()) >= 12)

    r = requests.post(f"{BASE}/api/pipeline", params={"profile_id": test_id},
                      json={"company": "ACME", "role": "Intern", "type": "other", "stage": "researching"})
    check("create pipeline entry", r.status_code == 201)
    entry_id = r.json()["id"]

    r = requests.patch(f"{BASE}/api/pipeline/{entry_id}", json={"stage": "applied", "reached_out": True})
    check("move stage", r.status_code == 200 and r.json()["stage"] == "applied")

    r = requests.patch(f"{BASE}/api/pipeline/{entry_id}", json={"stage": "bogus"})
    check("reject bad stage", r.status_code == 400)

    # ---- documents (save path works without LLM)
    r = requests.post(f"{BASE}/api/documents/save",
                      json={"pipeline_id": entry_id, "doc_type": "cover_letter",
                            "title": "t", "content": "hello"})
    check("save document to entry", r.status_code == 200
          and len(r.json()["documents"]["cover_letters"]) == 1)

    # ---- events
    r = requests.get(f"{BASE}/api/events", params={"profile_id": julian["id"]})
    check("events seeded", r.status_code == 200 and len(r.json()) >= 10)
    ev_id = r.json()[0]["id"]
    r = requests.post(f"{BASE}/api/events/{ev_id}/save",
                      params={"profile_id": test_id}, json={"saved": True})
    check("save event", r.status_code == 200 and r.json()["saved"] is True)

    # ---- scrape watchlists
    r = requests.get(f"{BASE}/api/scrape/watchlist")
    check("watchlists", r.status_code == 200 and "join" in r.json() and "personio" in r.json())
    r = requests.post(f"{BASE}/api/scrape/watchlist/join", json={"slug": "tmp-test-slug"})
    check("watchlist add", r.status_code == 200 and "tmp-test-slug" in r.json()["slugs"])
    r = requests.delete(f"{BASE}/api/scrape/watchlist/join/tmp-test-slug")
    check("watchlist remove", r.status_code == 200 and "tmp-test-slug" not in r.json()["slugs"])
    r = requests.get(f"{BASE}/api/scrape/status")
    check("scrape status", r.status_code == 200 and "running" in r.json())

    # ---- scrape run log (ingestion is unrestricted; no constraint endpoints)
    r = requests.get(f"{BASE}/api/scrape/runs")
    check("scrape runs log", r.status_code == 200 and isinstance(r.json(), list))

    # ---- studio templates
    r = requests.get(f"{BASE}/api/templates")
    builtins = [t for t in r.json() if t["is_builtin"]] if r.status_code == 200 else []
    check("templates: built-ins seeded", r.status_code == 200 and len(builtins) >= 4)
    b = builtins[0]
    r = requests.patch(f"{BASE}/api/templates/{b['id']}", json={"name": "x"})
    check("templates: built-in is read-only (403)", r.status_code == 403)
    r = requests.delete(f"{BASE}/api/templates/{b['id']}")
    check("templates: built-in undeletable (403)", r.status_code == 403)
    r = requests.post(f"{BASE}/api/templates/{b['id']}/duplicate")
    check("templates: duplicate built-in", r.status_code == 201 and not r.json()["is_builtin"])
    dup_id = r.json()["id"]
    r = requests.patch(f"{BASE}/api/templates/{dup_id}", json={"name": "My custom letter"})
    check("templates: edit own copy", r.status_code == 200 and r.json()["name"] == "My custom letter")
    # render fills placeholders from card + profile and reports unresolved ones
    r = requests.post(f"{BASE}/api/templates/{dup_id}/render", params={"profile_id": test_id},
                      json={"pipeline_id": entry_id})
    rendered = r.json() if r.status_code == 200 else {}
    check("templates: render fills card+profile placeholders",
          r.status_code == 200 and "{{company}}" not in rendered.get("text", "{{company}}")
          and "{{my_name}}" not in rendered.get("text", "{{my_name}}"), rendered)
    check("templates: unresolved placeholders reported",
          "hiring_manager" in rendered.get("unresolved", []), rendered)
    r = requests.post(f"{BASE}/api/templates/{dup_id}/draft", params={"profile_id": test_id},
                      json={"pipeline_id": entry_id})
    check("templates: draft with AI (or graceful 503)", llm_ok(r))
    r = requests.delete(f"{BASE}/api/templates/{dup_id}")
    check("templates: delete own template", r.status_code == 200)

    # ---- LLM endpoints (200 with key, clean 503 without)
    r = requests.post(f"{BASE}/api/chat", params={"profile_id": test_id},
                      json={"message": "One sentence: what should I do next?"})
    check("chat (or graceful 503)", llm_ok(r))
    r = requests.post(f"{BASE}/api/pipeline/extract",
                      json={"text": "Looking for a Founder's Associate Intern at ACME GmbH in Munich, start October 2026. https://acme.example/jobs/1"})
    check("paste-extract (or graceful 503)", llm_ok(r))
    r = requests.post(f"{BASE}/api/events/recommend", params={"profile_id": test_id})
    check("event recs (or graceful 503)", llm_ok(r))
    r = requests.post(f"{BASE}/api/documents/cover-letter", params={"profile_id": test_id},
                      json={"pipeline_id": entry_id, "tone": "startup"})
    check("cover letter (or graceful 503)", llm_ok(r))
    r = requests.post(f"{BASE}/api/documents/trainer", params={"profile_id": test_id},
                      json={"industry": "Venture Capital"})
    check("trainer (or graceful 503)", llm_ok(r))

    # cv tailor on the test profile has no cv_base → clean 400
    r = requests.post(f"{BASE}/api/documents/cv-tailor", params={"profile_id": test_id},
                      json={"pipeline_id": entry_id})
    check("cv tailor without cv_base → 400", r.status_code == 400)

    # ---- delete test profile cascades
    r = requests.delete(f"{BASE}/api/profiles/{test_id}")
    check("delete test profile", r.status_code == 200)
    r = requests.get(f"{BASE}/api/pipeline", params={"profile_id": test_id})
    check("cascade: pipeline gone (404 on profile)", r.status_code == 404)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
