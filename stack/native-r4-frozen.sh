#!/bin/zsh
# Round-4 native Delphi stack at the frozen commit (91d76c1), used to score the
# SWE-bench Verified expansion. Mirrors the round-3 native configuration in
# context/DELPHI_WORKSTREAM.md exactly; only the database, cache file, port,
# and temp directory differ. Secrets come from ~/.delphi-r4-secrets.env and are
# never written here.
#
#   stack/native-r4-frozen.sh initdb   # create + migrate the isolated database
#   stack/native-r4-frozen.sh api      # run the API (foreground)
#   stack/native-r4-frozen.sh worker   # run the indexing worker (foreground)
set -euo pipefail

HERE=${0:A:h}
ARCHIVE=${HERE:h}
WORKTREE=$HERE/freeze-worktree
DB_NAME=${DELPHI_R4_DB:-delphi_r4_swebench_expansion_20260909}
PORT=${DELPHI_R4_PORT:-28742}

set -a; source ~/.delphi-r4-secrets.env; set +a
export DATABASE_URL="postgresql://$USER@127.0.0.1:5432/$DB_NAME"
export SYNSC_API_HOST=127.0.0.1
export SYNSC_API_PORT=$PORT
export SYNSC_LOG_FORMAT=json
export SERVER_SECRET=native-delphi-session-secret-local-only
export SYSTEM_PASSWORD=native-delphi-admin
export EMBEDDING_PROVIDER=openai
export OPENAI_EMBEDDING_MODEL=text-embedding-3-small
export SYNSC_RATE_LIMIT_SEARCH=10000/minute
export SYNSC_RATE_LIMIT_INDEX=10000/minute
export SYNSC_ENABLE_RERANKER=true
export SYNSC_USE_CODE_RERANKER=false
export RERANKER_BLEND_ALPHA=0.4
export SYNSC_HYBRID_CANDIDATES=50
export SYNSC_HYBRID_RERANK_K=30
export SYNSC_QUERY_EXPANSION=true
export SYNSC_LISTWISE_RERANK=true
export SYNSC_LISTWISE_RERANK_MODEL=gpt-4o
export SYNSC_LISTWISE_RERANK_K=20
export SYNSC_LLM_SEED=1042
export SYNSC_LLM_CACHE_ENTRIES=2048
export SYNSC_LLM_CACHE_DB="$ARCHIVE/results/native-delphi-r4-swebench-stage-cache.sqlite3"
export SYNSC_HNSW_EF_SEARCH=100
export SYNSC_VECTOR_EXACT_SCAN=true
export SYNSC_FILE_DIVERSE_BM25=false
export SYNSC_WORKER_THREADS=4
export SYNSC_TEMP_DIR=${DELPHI_R4_TEMP:-/tmp/native-delphi-r4}
export PYTHONUNBUFFERED=1
mkdir -p "$SYNSC_TEMP_DIR"

# Optional overrides for declared ablations (round-4 factorial, 2026-09-09).
# The frozen configuration above is the confirmatory one; these switches exist
# so that the same build can serve the no-reranker cell of the candidate x
# reranker factorial without editing the file. Every response still attests
# the configuration actually served.
if [[ -n ${DELPHI_R4_CACHE:-} ]]; then
  export SYNSC_LLM_CACHE_DB="$DELPHI_R4_CACHE"
fi
if [[ ${DELPHI_R4_NO_RERANK:-0} == 1 ]]; then
  export SYNSC_ENABLE_RERANKER=false
  export SYNSC_LISTWISE_RERANK=false
fi

case ${1:-} in
  initdb)
    createdb "$DB_NAME"
    psql -X -q -v ON_ERROR_STOP=1 -d "$DB_NAME" -f "$WORKTREE/database/supabase/setup_local.sql"
    (cd "$WORKTREE/backend" && .venv/bin/alembic upgrade head)
    psql -X -q -d "$DB_NAME" -c "select version_num from alembic_version;"
    ;;
  api)
    cd "$WORKTREE/backend" && exec .venv/bin/synsc-context-http
    ;;
  worker)
    cd "$WORKTREE/backend" && exec .venv/bin/synsc-context-worker
    ;;
  *)
    echo "usage: $0 {initdb|api|worker}" >&2; exit 2 ;;
esac
