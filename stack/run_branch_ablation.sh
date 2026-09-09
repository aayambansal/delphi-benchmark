#!/bin/zsh
# Branch-level ablation of Delphi's candidate generator on the fresh C0 draw.
#
# Serves the frozen build with both learned rerankers disabled and a fusion
# weight override per configuration, scores the 60-instance draw once per
# configuration with the served weights attested on every response, and stops
# the server. Expansion stays on (Delphi's gate). See Appendix "Branch-level
# ablation" and harness/analyze_branch_ablation.py.
#
#   stack/run_branch_ablation.sh <db> <port> <sources.jsonl> <cases.jsonl>
set -uo pipefail
HERE=${0:A:h}
ARCHIVE=${HERE:h}
cd "$ARCHIVE"
DB=$1; PORT=$2; SOURCES=$3; CASES=$4
PY=/Users/aayambansal/Desktop/syntheticsciences/delphi/backend/.venv/bin/python

# name|SYNSC_FUSION_WEIGHTS override (empty = tuned defaults)
CONFIGS=(
  "all|"
  "no_symbol|symbol=0"
  "no_path|path=0"
  "no_path_affinity|path_affinity=0"
  "no_trigram|trigram=0"
  "no_bm25|bm25=0"
  "no_vector|vector=0"
  "vector_bm25_equal|vector=0.5,bm25=0.5,symbol=0,path=0,path_affinity=0,trigram=0"
  "vector_bm25_tuned|vector=0.5,bm25=0.25,symbol=0,path=0,path_affinity=0,trigram=0"
  "vector_only|vector=0.5,bm25=0,symbol=0,path=0,path_affinity=0,trigram=0"
)

expected_weights() {
  # Compose the full attested weight vector from the defaults plus overrides.
  $PY - "$1" <<'EOF'
import json, sys
w = {"vector": 0.5, "bm25": 0.25, "symbol": 0.20, "path": 0.15, "path_affinity": 0.15, "trigram": 0.05}
for part in [p for p in sys.argv[1].split(",") if "=" in p]:
    k, v = part.split("=", 1); w[k.strip()] = float(v)
print(json.dumps({"vector_mode": "exact", "embedding_model": "text-embedding-3-small", "hybrid_candidates": 50,
                  "file_diverse_bm25": False, "query_expansion_enabled": True, "reranker_enabled": False,
                  "listwise_rerank_enabled": False, "llm_seed": 1042, "fusion_weights": w}))
EOF
}

for spec in "${CONFIGS[@]}"; do
  NAME=${spec%%|*}; WEIGHTS=${spec#*|}
  RUN="D3-ablation-delphi-norerank-$NAME-v1"
  if [[ -f results/$RUN-summary.json ]]; then echo "=== skip $RUN (exists)"; continue; fi
  echo "=== $(date -u +%FT%TZ) START $NAME weights='${WEIGHTS:-defaults}'"
  DELPHI_R4_DB=$DB DELPHI_R4_PORT=$PORT DELPHI_R4_NO_RERANK=1 \
  DELPHI_R4_CACHE=$PWD/results/native-delphi-r5-fresh-stage-cache.sqlite3 DELPHI_R4_TEMP=/tmp/native-delphi-r5-abl \
  SYNSC_FUSION_WEIGHTS=$WEIGHTS zsh stack/native-r4-frozen.sh api > results/logs/r5-api-ablation-$NAME.log 2>&1 &
  API_PID=$!
  for i in $(seq 1 60); do
    if curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/health 2>/dev/null | grep -q 200; then break; fi
    sleep 2
  done
  CFG=$(expected_weights "$WEIGHTS")
  PYTHONPATH=. $PY -u -m harness.run_arb --engine delphi --split final --sample-files "$CASES" --sources "$SOURCES" \
    --delphi-url http://127.0.0.1:$PORT --delphi-key native-delphi-admin --expected-retrieval-config-json "$CFG" \
    --run-id "$RUN" --system "delphi-frozen-norerank-$NAME" \
    --notes "round-4 branch ablation on the fresh C0 draw: rerankers off, expansion on, fusion weights ${WEIGHTS:-tuned defaults}" \
    > results/logs/$RUN.log 2>&1
  echo "=== $(date -u +%FT%TZ) END $NAME exit=$? $(tail -1 results/logs/$RUN.log | cut -c1-200)"
  kill $API_PID 2>/dev/null; wait $API_PID 2>/dev/null
  sleep 2
done
echo "=== $(date -u +%FT%TZ) branch ablation complete"
