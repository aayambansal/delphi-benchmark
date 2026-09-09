#!/usr/bin/env python3
"""Publish the executable-pilot agent trajectories as a Hugging Face dataset.

Uploads ``results/pilot/`` (every mini-SWE-agent trajectory, the SWE-bench
harness reports and per-instance logs, the seeded datasets, and the analyses)
under ``pilot/`` in the dataset repository, together with a dataset card and a
flat ``trajectories.jsonl`` index (one row per trajectory, joined with its
harness verdict) so the Hub viewer can browse the runs.

The trajectories (``results/pilot/runs/``) and per-instance logs are not kept in
git; restore them from the published dataset first (see results/pilot/README.md)
or regenerate them with ``stack/run_pilot.sh``.

Authentication, in order of precedence:

  HF_TOKEN                                     a user access token with write scope
  HF_OAUTH_CLIENT_ID + HF_OAUTH_CLIENT_SECRET  a Hugging Face OAuth app; the
                                               device-code flow prints a URL and a
                                               code to approve in a browser

Usage:
  .venv-agent/bin/python harness/upload_traces_hf.py --repo-id aayambansall/delphi-benchmark-traces
  .venv-agent/bin/python harness/upload_traces_hf.py --dry-run     # build card + index only
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEVICE_URL = "https://huggingface.co/oauth/device"
TOKEN_URL = "https://huggingface.co/oauth/token"
GITHUB_URL = "https://github.com/aayambansal/delphi-benchmark"
RUN_RE = re.compile(r"^(?P<condition>.+?)-s(?P<steps>\d+)(?:-r(?P<repeat>\d+))?$")


# --------------------------------------------------------------------------- auth
def _post_form(url: str, fields: dict, headers: dict) -> dict:
    body = urllib.parse.urlencode(fields).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/x-www-form-urlencoded", **headers})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def device_flow(client_id: str, client_secret: str) -> str:
    """RFC 8628 device-code grant against the Hub; returns an access token."""
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {"Authorization": f"Basic {basic}"}
    dev = _post_form(DEVICE_URL, {"client_id": client_id,
                                  "scope": "openid profile write-repos manage-repos"}, headers)
    print(f"\n==> Approve access: open {dev['verification_uri']} and enter code "
          f"{dev['user_code']}  (expires in {dev['expires_in']} s)\n", flush=True)
    deadline = time.time() + int(dev["expires_in"])
    interval = int(dev.get("interval", 5))
    while time.time() < deadline:
        time.sleep(interval)
        try:
            tok = _post_form(TOKEN_URL, {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": dev["device_code"], "client_id": client_id}, headers)
            print("==> approved", flush=True)
            return tok["access_token"]
        except urllib.error.HTTPError as e:
            err = json.loads(e.read() or b"{}").get("error")
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval += 5
                continue
            sys.exit(f"device flow failed: {err}")
    sys.exit("device code expired before approval; rerun and approve within the window")


def resolve_token() -> str:
    if os.environ.get("HF_TOKEN"):
        return os.environ["HF_TOKEN"]
    cid, sec = os.environ.get("HF_OAUTH_CLIENT_ID"), os.environ.get("HF_OAUTH_CLIENT_SECRET")
    if cid and sec:
        return device_flow(cid, sec)
    sys.exit("set HF_TOKEN, or HF_OAUTH_CLIENT_ID and HF_OAUTH_CLIENT_SECRET")


# -------------------------------------------------------------------------- index
def load_verdicts(eval_dir: Path) -> tuple[dict, dict]:
    """Map instance_id -> verdict (and -> failure reason) from the harness report."""
    verdict, reason = {}, {}
    for report in sorted(eval_dir.glob("*.json")):
        rep = json.loads(report.read_text())
        for key, label in (("unresolved_ids", "unresolved"), ("resolved_ids", "resolved"),
                           ("error_ids", "error"), ("empty_patch_ids", "empty_patch")):
            for iid in rep.get(key, []):
                verdict[iid] = label
        for iid in rep.get("ambiguous_failure_ids", []):
            reason[iid] = (rep.get("failure_reasons") or {}).get(iid, "ambiguous")
    return verdict, reason


def build_index(pilot: Path) -> list[dict]:
    rows = []
    for run_dir in sorted((pilot / "runs").iterdir()):
        m = RUN_RE.match(run_dir.name)
        if not run_dir.is_dir() or not m:
            continue
        verdict, reason = load_verdicts(pilot / "eval" / run_dir.name)
        for traj in sorted(run_dir.glob("*/*.traj.json")):
            d = json.loads(traj.read_text())
            info = d.get("info", {})
            stats = info.get("model_stats", {})
            iid = d.get("instance_id") or traj.parent.name
            rows.append({
                "run": run_dir.name,
                "condition": m["condition"],
                "repeat": int(m["repeat"] or 1),
                "step_limit": int(m["steps"]),
                "instance_id": iid,
                "repo": iid.rsplit("-", 1)[0].replace("__", "/"),
                "agent": f"mini-swe-agent {info.get('mini_version', '')}".strip(),
                "model": (info.get("config", {}).get("model") or {}).get("model_name"),
                "exit_status": info.get("exit_status"),
                "api_calls": stats.get("api_calls"),
                "cost_usd": stats.get("instance_cost"),
                "n_messages": len(d.get("messages", [])),
                "submitted_patch": bool(info.get("submission")),
                "verdict": verdict.get(iid, "not_evaluated"),
                "ambiguous_failure": iid in reason,
                "failure_reason": reason.get(iid),
                "trajectory_path": f"pilot/{traj.relative_to(pilot).as_posix()}",
            })
    return rows


def dataset_card(repo_id: str, rows: list[dict]) -> str:
    conditions = sorted({r["condition"] for r in rows})
    n_inst = len({r["instance_id"] for r in rows})
    n_resolved = sum(r["verdict"] == "resolved" for r in rows)
    return f"""---
pretty_name: Delphi executable-pilot agent trajectories
license: cc-by-4.0
language:
- en
tags:
- code
- swe-bench
- agent-trajectories
- software-engineering
- retrieval
size_categories:
- n<1K
configs:
- config_name: default
  data_files: trajectories.jsonl
---

# Delphi executable-pilot agent trajectories

All {len(rows)} mini-SWE-agent trajectories from the preregistered executable pilot in
*Where Do Context-Engine Gains Come From? A Component-Level Decomposition of Repository
Retrieval Under Matched Baselines and Audited Exposure* (Bansal and Gangwani, 2026),
together with the official SWE-bench harness verdicts and logs for every trajectory.
Code, per-case retrieval results, analyses, and the paper source are at
[{GITHUB_URL}]({GITHUB_URL}).

## What was run

- **Tasks:** {n_inst} SWE-bench Verified instances (the paper's 62-instance C0 set).
- **Agent:** mini-SWE-agent 2.4.6, text-based action format, `gpt-5.4-mini`, step budget 50,
  2.0 USD cost cap, official `x86_64` instance images.
- **Conditions** (`condition` column): `none` (no seed), `random` (five non-gold files, seed 1042),
  `delphi` (top five files of the frozen Delphi ranking), `hybrid_rerank_expand` (top five of the
  fully matched conventional stack); each run twice (`repeat` 1 and 2). `delphi_paths` (Delphi's top five
  paths, no content) and `delphi_chunks` (paths plus the best-matching chunk instead of the file head)
  are the exploratory seed-interface arms, one repeat each.
- **Seed block:** identical wording across conditions, up to five paths with the first 40 lines of
  each file at the base commit, capped at 3,000 tokens.
- **Outcome:** verified repair under the official SWE-bench harness. {n_resolved} of {len(rows)}
  trajectories are `resolved`.

## Layout

| Path | Contents |
|---|---|
| `trajectories.jsonl` | one row per trajectory: run, condition, repeat, instance, model, exit status, API calls, cost, harness verdict, path to the trajectory file |
| `pilot/runs/<run>/<instance_id>/<instance_id>.traj.json` | full mini-SWE-agent trajectory (every model call and action, final submission) |
| `pilot/runs/<run>/preds.json` | submitted patches per run |
| `pilot/eval/<run>/*.json` | official SWE-bench harness report per run |
| `pilot/eval/<run>/logs/run_evaluation/...` | per-instance harness logs: `patch.diff`, `eval.sh`, `test_output.txt`, `report.json`, `run_instance.log` |
| `pilot/datasets/<condition>/` | the seeded SWE-bench inputs given to the agent under each condition |
| `pilot/analysis-*.json`, `pilot/seed-content-analysis.json` | pooled, per-repeat, seed-interface, and seed-content analyses |
| `pilot/instances-round3-62.txt` | the instance list |
| `pilot/smoke-native/` | a single smoke-test trajectory (not part of the pilot) |

Runs are named `<condition>-s50` (repeat 1) and `<condition>-s50-r2` (repeat 2); `s50` is the
50-step budget. Conditions in this release: {", ".join(f"`{c}`" for c in conditions)}.

## Loading

```python
from datasets import load_dataset
index = load_dataset("{repo_id}", split="train")          # the trajectories.jsonl index

from huggingface_hub import hf_hub_download
import json
row = index[0]
path = hf_hub_download("{repo_id}", row["trajectory_path"], repo_type="dataset")
traj = json.load(open(path))                                # {{"info", "messages", ...}}
```

## Notes

Trajectories embed problem statements, file contents, and patches from the public repositories in
SWE-bench Verified; that content keeps its upstream licenses. The trajectories, verdicts, and
analyses themselves are released under CC BY 4.0. Hosted model calls were made with
`gpt-5.4-mini`; API credentials are not included.

## Citation

```bibtex
@article{{bansal2026contextengine,
  title   = {{Where Do Context-Engine Gains Come From? A Component-Level Decomposition of
             Repository Retrieval Under Matched Baselines and Audited Exposure}},
  author  = {{Bansal, Aayam and Gangwani, Ishaan}},
  year    = {{2026}},
  note    = {{Preprint. Code and artifacts: {GITHUB_URL}}}
}}
```
"""


# --------------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-id", default="aayambansall/delphi-benchmark-traces")
    ap.add_argument("--pilot-dir", default=str(ROOT / "results" / "pilot"))
    ap.add_argument("--dry-run", action="store_true", help="build the card and index locally; do not upload")
    ap.add_argument("--stage-dir", help="where to stage the upload (default: a temp dir)")
    args = ap.parse_args()

    pilot = Path(args.pilot_dir)
    rows = build_index(pilot)
    stage = Path(args.stage_dir or tempfile.mkdtemp(prefix="hf-traces-"))
    stage.mkdir(parents=True, exist_ok=True)
    (stage / "trajectories.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (stage / "README.md").write_text(dataset_card(args.repo_id, rows))
    print(f"index: {len(rows)} trajectories, {sum(r['verdict']=='resolved' for r in rows)} resolved; staged at {stage}")
    if args.dry_run:
        return

    token = resolve_token()
    from huggingface_hub import HfApi  # imported late so --dry-run needs no extra deps

    api = HfApi(token=token)
    me = api.whoami()
    print(f"authenticated as {me.get('name')}")
    api.create_repo(args.repo_id, repo_type="dataset", exist_ok=True, private=False)

    dest = stage / "pilot"
    if not dest.exists():
        shutil.copytree(pilot, dest, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
    api.upload_large_folder(repo_id=args.repo_id, repo_type="dataset", folder_path=str(stage),
                            print_report=True, print_report_every=30)
    print(f"\ndone: https://huggingface.co/datasets/{args.repo_id}")


if __name__ == "__main__":
    main()
