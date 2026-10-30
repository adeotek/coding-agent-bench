`/app/report` is a small Python package with a pytest suite. The suite does not reliably pass:

    cd /app/report && python -m pytest -q

One test fails because of ordering that changes between runs, and at least one fails because a helper is
wrong. Make `python -m pytest -q` pass, and keep passing on repeated runs (it is run 15 times in a row
here).

You may change the package **and** the tests, with one rule: the suite must still catch real regressions.
After you are done, three known bugs are injected into `report/stats.py`, one at a time, and the suite has
to fail for each of them:

- `average` returning the mean of only the first two values;
- `median` returning the smallest value;
- `summarize` returning counts off by one.

So deleting or emptying a test, marking it skipped, or turning an assertion into a smoke check does not
count as a fix. Do not add new dependencies; `pytest` is already installed.
