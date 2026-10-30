#!/bin/bash
set -euo pipefail
cd /app/calc

# The regression is the commit that changed apply_discount to subtract `percent / 100` instead of
# `percent` percent of the price. Find it by content, then confirm with the test:
CULPRIT=$(git log --format='%H %s' -S 'price - percent / 100' -- calc/ops.py | tail -1 | cut -d' ' -f1)

# Fix the working tree (no history rewrite).
python - <<'PY'
import pathlib
p = pathlib.Path("/app/calc/calc/ops.py")
src = p.read_text()
src = src.replace("    return round(price - percent / 100, 2)", "    return round(price * (1 - percent / 100), 2)")
p.write_text(src)
PY

printf '%s\n' "$CULPRIT" > /app/culprit.txt
python -m pytest -q
