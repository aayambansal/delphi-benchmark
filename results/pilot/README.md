# Executable pilot artifacts

This directory keeps the small, derived pilot artifacts that the paper's tables
and figures are built from:

| Path | Contents |
|---|---|
| `analysis-s50.json`, `analysis-s50-r2.json` | per-repeat analysis (verified repairs per condition, paired differences with instance- and repository-cluster intervals) |
| `analysis-s50_s50-r2.json` | pooled analysis over both repeats |
| `analysis-seed-interface.json` | the exploratory seed-interface check (paths only; paths + best-matching chunk) |
| `seed-content-analysis.json` | the seed audit: how often a seed's file head covered the region the gold patch edits |
| `eval/<run>/gpt-5.4-mini.<run>.json` | the official SWE-bench harness report for each run |
| `datasets/<condition>/` | the seeded SWE-bench Verified inputs given to the agent under each condition, with a manifest of the seed files per instance |
| `instances-round3-62.txt` | the 62 instances |

The bulky artifacts—all 620 mini-SWE-agent trajectories (`runs/`) and the
per-instance harness logs (`eval/<run>/logs/`)—are published as a Hugging Face
dataset instead of being kept in git:

<https://huggingface.co/datasets/aayambansall/delphi-benchmark-traces>

To re-run the pilot analysis (`harness/analyze_pilot.py`) or rebuild the dataset
(`harness/upload_traces_hf.py`), restore them here first:

```bash
python -m pip install huggingface_hub
python - <<'EOF'
from huggingface_hub import snapshot_download
snapshot_download("aayambansall/delphi-benchmark-traces", repo_type="dataset",
                  allow_patterns=["pilot/runs/**", "pilot/eval/**"],
                  local_dir="results/_hf")  # then move results/_hf/pilot/* into results/pilot/
EOF
```

Runs are named `<condition>-s50` (repeat 1) and `<condition>-s50-r2` (repeat 2);
`s50` is the 50-step budget. See Appendix "Executable pilot" of the paper for
the protocol.
