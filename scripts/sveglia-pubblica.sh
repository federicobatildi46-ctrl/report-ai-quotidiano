#!/usr/bin/env bash
# Sveglia per i post LinkedIn programmati. La lancia una routine Claude nel cloud ogni 30 minuti
# (l'orologio interno di GitHub su questo repo parte con ore di ritardo e salta molti giri).
# Se c'è un post in uscita nei prossimi 45 minuti, fa un push su un ramo claude/... con un file in
# sveglia-pubblica/: parte subito il workflow "Pubblica post programmati", che aspetta l'orario,
# pubblica e cancella il ramo. Altrimenti non fa niente.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git fetch -q origin main && git checkout -q origin/main -- outputs/linkedin/coda.json 2>/dev/null || true

due=$(python3 - <<'PY'
import json, os
from datetime import datetime, timedelta, timezone
p = "outputs/linkedin/coda.json"
limit = datetime.now(timezone.utc) + timedelta(minutes=45)
n = 0
if os.path.exists(p):
    for e in json.load(open(p, encoding="utf-8")):
        if e.get("status") == "programmato" and datetime.fromisoformat(e["publish_at"]) <= limit:
            n += 1
print(n)
PY
)
if [ "$due" = "0" ]; then
  echo "RISULTATO: nessun post in uscita nei prossimi 45 minuti, niente da fare."
  exit 0
fi

branch=$(git branch --show-current)
case "$branch" in
  claude/*) ;;
  *) branch="claude/pubblica-$(date -u +%Y%m%d-%H%M%S)"; git checkout -q -b "$branch" ;;
esac
mkdir -p sveglia-pubblica
date -u +%Y-%m-%dT%H:%M:%SZ > sveglia-pubblica/ora.txt
git add sveglia-pubblica/ora.txt
git commit -q -m "Sveglia pubblicazione LinkedIn $(date -u +%H:%M)"
for i in 1 2 3 4; do
  if git push -q -u origin HEAD; then
    echo "RISULTATO: $due post in uscita, workflow svegliato (ramo $branch)."
    exit 0
  fi
  sleep $((i * 3))
done
echo "RISULTATO: push non riuscito (ramo $branch)."
exit 1
