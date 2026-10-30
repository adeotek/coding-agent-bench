Write `/app/etl/normalize.py`: a command-line tool that normalizes a messy delimited file to strict
RFC 4180 CSV on stdout.

    python /app/etl/normalize.py <input-file> [--delimiter SEP] [--skip-rows N]

Rules:

- The input may be comma-, semicolon- or tab-separated; `--delimiter` overrides the autodetection.
- Leading UTF-8 BOM is removed; output is UTF-8 without a BOM.
- Output line endings are `\n` only (never `\r\n`), and the file ends with exactly one `\n`.
- Quoting is minimal: a field is quoted only when it contains the delimiter, a double quote, a carriage
  return or a line feed, or when it has leading/trailing spaces. Inside a quoted field, `"` is doubled.
- Embedded newlines inside quoted fields are preserved as-is.
- `--skip-rows N` drops the first N input rows (header rows), counted as CSV rows, not lines.
- Empty fields stay empty (they must not turn into `""`).
- Field count must be constant across rows: if a row has a different number of fields, exit 3 and print
  `row <n>: expected <k> fields, got <m>` to stderr, where `<n>` is the row's 1-based position in the
  input file, counting every CSV row from 1 and including skipped header rows (so with no `--skip-rows`
  the first data row is row 1 and a header is row 1 too).

Exit codes: 0 on success, 2 for usage/IO errors, 3 for ragged rows. Nothing but CSV goes to stdout.
The tool must stream (work on files larger than memory) — do not read the whole file into a list.
