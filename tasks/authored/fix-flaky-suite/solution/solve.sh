#!/bin/bash
set -euo pipefail

# The order-dependence lives in summarize(): a set is not ordered across runs.
python - <<'PY'
import pathlib
p = pathlib.Path("/app/report/stats.py")
src = p.read_text()
src = src.replace(
    "    labels = set(counts)\n    return \"\\n\".join(f\"{label}: {counts[label]}\" for label in labels)",
    "    return \"\\n\".join(f\"{label}: {counts[label]}\" for label in sorted(counts))",
)
p.write_text(src)
PY

# Float arithmetic: compare against the mean within a tolerance rather than by exact equality.
python - <<'PY'
import pathlib
p = pathlib.Path("/app/report/tests/test_stats.py")
src = p.read_text()
src = src.replace(
    "import stats",
    "import pytest\nimport stats",
)
src = src.replace(
    "    assert stats.average([0.1, 0.2, 0.3]) == 0.2",
    "    assert stats.average([0.1, 0.2, 0.3]) == pytest.approx(0.2)",
)
p.write_text(src)
PY

cd /app/report
for run in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  python -m pytest -q >/dev/null || { echo "suite failed on run $run"; exit 1; }
done
echo "suite passed 15 consecutive runs"