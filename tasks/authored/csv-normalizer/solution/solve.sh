#!/bin/bash
set -euo pipefail

cat > /app/etl/normalize.py <<'PY'
#!/usr/bin/env python3
"""Normalize a delimited file to strict RFC 4180 CSV on stdout (streaming)."""
import csv
import sys

BOM = "\ufeff"


def sniff(path, override):
    if override:
        return override
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(8192)
    counts = {sep: sample.count(sep) for sep in (",", ";", "\t")}
    if not any(counts.values()):
        return ","
    return max(counts, key=lambda sep: counts[sep])


def quote(field, delimiter):
    if field == "":
        return ""
    needs = (
        delimiter in field
        or '"' in field
        or "\r" in field
        or "\n" in field
        or field != field.strip()
    )
    if not needs:
        return field
    return '"' + field.replace('"', '""') + '"'


def main(argv):
    if len(argv) < 2:
        print("usage: normalize.py <input> [--delimiter SEP] [--skip-rows N]", file=sys.stderr)
        return 2
    path = argv[1]
    delimiter = None
    skip = 0
    rest = argv[2:]
    while rest:
        flag = rest.pop(0)
        if flag == "--delimiter" and rest:
            delimiter = rest.pop(0)
        elif flag == "--skip-rows" and rest:
            skip = int(rest.pop(0))
        else:
            print(f"unknown argument: {flag}", file=sys.stderr)
            return 2

    try:
        sep = sniff(path, delimiter)
        out = sys.stdout
        expected = None
        row_no = 0
        with open(path, "r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, delimiter=sep, quotechar='"')
            for index, row in enumerate(reader):
                if index < skip:
                    continue
                row_no += 1
                if expected is None:
                    expected = len(row)
                elif len(row) != expected:
                    print(f"row {row_no}: expected {expected} fields, got {len(row)}", file=sys.stderr)
                    return 3
                out.write(",".join(quote(field, ",") for field in row) + "\n")
        return 0
    except OSError as exc:
        print(f"cannot read {path}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
PY

chmod +x /app/etl/normalize.py
