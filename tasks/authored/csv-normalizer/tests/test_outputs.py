"""Verifier for the CSV normalizer.

Fixtures live here (mounted at /tests only during verification) so the agent cannot tune to them.
Checks are behavioural: the output is parsed back and compared, plus the byte-level rules the
instruction states explicitly (no BOM, LF endings, one trailing newline, minimal quoting).
"""
import csv
import io
import subprocess
import sys
from pathlib import Path

TOOL = Path("/app/etl/normalize.py")
FIXTURES = Path("/tests/fixtures")


def run(*args, expect=0):
    result = subprocess.run([sys.executable, str(TOOL), *map(str, args)], capture_output=True, text=True)
    assert result.returncode == expect, (
        f"normalize.py {' '.join(map(str, args))} exited {result.returncode}, expected {expect}\n"
        f"stdout: {result.stdout[:400]}\nstderr: {result.stderr[:400]}"
    )
    return result


def rows_of(text):
    return list(csv.reader(io.StringIO(text)))


def assert_clean_csv(text):
    assert "\r" not in text, "output contains a carriage return"
    assert not text.startswith("\ufeff"), "output starts with a BOM"
    assert text.endswith("\n") and not text.endswith("\n\n"), "output must end with exactly one newline"


def test_tool_exists():
    assert TOOL.exists(), "/app/etl/normalize.py does not exist"


def test_semicolon_input_autodetected():
    out = run(FIXTURES / "messy_semicolon.csv").stdout
    assert_clean_csv(out)
    rows = rows_of(out)
    assert rows[0] == ["id", "name", "note"], rows[0]
    assert rows[1] == ["1", "ada", "likes, commas"], rows[1]
    assert rows[2] == ["2", "linus", 'says "hi"'], rows[2]
    assert rows[3] == ["3", "grace", ""], f"empty field became {rows[3][2]!r}"
    assert '""' not in out.split("\n")[3], "an empty field was written as a quoted empty string"


def test_crlf_tab_input_normalized():
    out = run(FIXTURES / "crlf_tabs.tsv").stdout
    assert_clean_csv(out)
    assert rows_of(out) == [["id", "name"], ["1", "ada"], ["2", "grace"]]


def test_bom_removed_and_header_skippable():
    out = run(FIXTURES / "bom_header.csv", "--skip-rows", "1").stdout
    assert_clean_csv(out)
    assert rows_of(out) == [["1", "ada"]]


def test_embedded_newline_preserved():
    out = run(FIXTURES / "multiline.csv").stdout
    rows = rows_of(out)
    assert rows[1] == ["1", "line one\nline two"], rows[1]
    assert '\n' in out.split("\n", 1)[1], "the embedded newline was flattened"


def test_explicit_delimiter_wins():
    path = FIXTURES / "messy_semicolon.csv"
    result = run(path, "--delimiter", ";")
    assert rows_of(result.stdout)[1][2] == "likes, commas"


def test_leading_space_field_is_quoted():
    import tempfile

    source = Path(tempfile.mkdtemp()) / "spaces.csv"
    source.write_text("id,note\n1, padded \n")
    out = run(source).stdout
    assert '" padded "' in out, f"a field with surrounding spaces must be quoted, got {out!r}"


def test_ragged_row_exits_3_with_message():
    import tempfile

    tmp = Path(tempfile.mkdtemp()) / "ragged.csv"
    tmp.write_text("id,name\n1,ada\n2\n")
    result = run(tmp, expect=3)
    # input rows: 1 = "id,name", 2 = "1,ada", 3 = "2" (the ragged one)
    assert "row 3: expected 2 fields, got 1" in result.stderr, result.stderr
    assert result.stdout in ("id,name\n1,ada\n", ""), "no partial garbage on stdout after a ragged row"


def test_streams_a_large_file():
    import tempfile

    tmp = Path(tempfile.mkdtemp()) / "big.csv"
    with tmp.open("w") as handle:
        handle.write("id,value\n")
        for i in range(200_000):
            handle.write(f"{i},v{i}\n")
    result = subprocess.run([sys.executable, str(TOOL), str(tmp)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[:400]
    lines = result.stdout.splitlines()
    assert len(lines) == 200_001, f"expected 200001 output lines, got {len(lines)}"
    assert lines[0] == "id,value" and lines[-1] == "199999,v199999"
