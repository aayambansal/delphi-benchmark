#!/bin/zsh
# Executable agent pilot: run one seeded condition at one step budget, then
# evaluate with the official SWE-bench harness. See context/PILOT_PROTOCOL.md.
#
#   stack/run_pilot.sh <condition> <step_limit> [workers]
set -uo pipefail
HERE=${0:A:h}
ARCHIVE=${HERE:h}
cd "$ARCHIVE"
COND=$1; STEPS=$2; WORKERS=${3:-3}
LABEL="$COND-s$STEPS"
PKG=.venv-agent/lib/python3.12/site-packages/minisweagent
set -a; source ~/.delphi-r4-secrets.env; set +a
export MSWEA_SILENT_STARTUP=1

RUN_DIR=results/pilot/runs/$LABEL
EVAL_DIR=results/pilot/eval/$LABEL
mkdir -p "$RUN_DIR" "$EVAL_DIR"

echo "=== $(date -u +%FT%TZ) agent start $LABEL"
.venv-agent/bin/mini-extra swebench \
  --subset "results/pilot/datasets/$COND" --split test \
  --model gpt-5.4-mini -o "$RUN_DIR" -w "$WORKERS" \
  -c "$PKG/config/benchmarks/swebench_xml.yaml" \
  -c model.model_class=litellm_textbased \
  -c agent.step_limit="$STEPS" -c agent.cost_limit=2.0 \
  -c 'environment.run_args=["--rm","--platform","linux/amd64"]' \
  -c environment.pull_timeout=3600 \
  > "$RUN_DIR/agent.stdout.log" 2>&1
echo "=== $(date -u +%FT%TZ) agent end $LABEL exit=$? preds=$(python3 -c "import json;print(len(json.load(open('$RUN_DIR/preds.json'))))" 2>/dev/null)"

echo "=== $(date -u +%FT%TZ) eval start $LABEL"
( cd "$EVAL_DIR" && ../../../../.venv-agent/bin/python -m swebench.harness.run_evaluation \
    --dataset_name SWE-bench/SWE-bench_Verified --split test \
    --predictions_path "../../runs/$LABEL/preds.json" \
    --max_workers 2 --run_id "$LABEL" --timeout 1800 \
    > eval.stdout.log 2>&1 )
echo "=== $(date -u +%FT%TZ) eval end $LABEL exit=$? $(ls $EVAL_DIR/*.json 2>/dev/null | head -1)"
