#!/bin/bash
# Build /app/calc with a deterministic history: fixed dates and identities keep every commit id stable,
# so the verifier can assert the culprit by SHA without keeping the answer in the image.
set -euo pipefail

mkdir -p /app/calc/calc /app/calc/tests
cd /app/calc
export TZ=UTC
git init -q -b main

commit() { # commit <date> <message>
  git add -A
  GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1" git commit -q -m "$2"
}

echo '[pytest]
testpaths = tests' > pytest.ini
echo '"""Arithmetic helpers."""' > calc/__init__.py
echo '"""Empty for now."""' > calc/ops.py
commit "2026-01-01T09:00:00+0000" "initial commit"

cat > calc/ops.py <<'PY'
"""Arithmetic helpers used by the invoicing code."""


def add(a, b):
    return a + b


def multiply(a, b):
    return a * b
PY
commit "2026-01-02T09:00:00+0000" "ops: add and multiply"

cat > tests/test_ops.py <<'PY'
from calc import ops


def test_add():
    assert ops.add(2, 3) == 5


def test_multiply():
    assert ops.multiply(4, 2.5) == 10
PY
commit "2026-01-03T09:00:00+0000" "tests: cover the arithmetic helpers"

cat > calc/format.py <<'PY'
"""Formatting helpers."""


def money(cents):
    return f"${cents / 100:.2f}"
PY
commit "2026-01-04T09:00:00+0000" "format: add money()"

cat > calc/ops.py <<'PY'
"""Arithmetic helpers used by the invoicing code."""


def add(a, b):
    return a + b


def multiply(a, b):
    return a * b


def net_total(gross, tax_rate):
    """Total after tax, rounded to cents."""
    return round(gross * (1 + tax_rate), 2)
PY
commit "2026-01-05T09:00:00+0000" "ops: add net_total()"

cat > tests/test_ops.py <<'PY'
from calc import ops


def test_add():
    assert ops.add(2, 3) == 5


def test_multiply():
    assert ops.multiply(4, 2.5) == 10


def test_net_total_rounds_to_cents():
    assert ops.net_total(19.99, 0.21) == 24.19
PY
commit "2026-01-06T09:00:00+0000" "tests: cover net_total rounding"

cat > calc/ops.py <<'PY'
"""Arithmetic helpers used by the invoicing code."""


def add(a, b):
    return a + b


def multiply(a, b):
    return a * b


def net_total(gross, tax_rate):
    """Total after tax, rounded to cents."""
    return round(gross * (1 + tax_rate), 2)


def apply_discount(price, percent):
    """Price after a percentage discount, rounded to cents."""
    return round(price - percent / 100, 2)
PY
cat >> tests/test_ops.py <<'PY'


def test_apply_discount():
    assert ops.apply_discount(200, 10) == 180.0
PY
commit "2026-01-07T09:00:00+0000" "ops: add apply_discount()"

cat > README.md <<'MD'
# calc

Arithmetic helpers for the invoicing code. Run the tests with `python -m pytest -q`.
MD
commit "2026-01-08T09:00:00+0000" "docs: add a README"

cat >> calc/ops.py <<'PY'


def apply_many(prices, percent):
    """Apply the same discount to a list of prices."""
    return [apply_discount(price, percent) for price in prices]
PY
commit "2026-01-09T09:00:00+0000" "ops: add apply_many()"

cat > calc/cli.py <<'PY'
"""Tiny CLI: calc <price> <percent> -> discounted price."""
import sys

from calc import ops


def main(argv):
    price, percent = float(argv[1]), float(argv[2])
    print(ops.apply_discount(price, percent))


if __name__ == "__main__":
    main(sys.argv)
PY
commit "2026-01-10T09:00:00+0000" "cli: add a discount calculator"
