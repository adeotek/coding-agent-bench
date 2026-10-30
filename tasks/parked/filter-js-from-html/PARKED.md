# PARKED — do not run this cell for scores

This copy exists because the repair got two thirds of the way and the remaining third is not worth
spending on. Read `docs/task-repairs.json` → `filter-js-from-html` for the full account.

What was fixed and is worth keeping:

- the 417-vector html-sanitizer-testbed corpus is **vendored** in `tests/testcases.tar.gz` (24 KB), so the
  verification no longer downloads it from GitHub;
- every fail-open path in the old browser check now raises instead of returning "no alert" — including the
  `signal.alarm` timeout that used to print "treating as passed";
- a deterministic, browser-free variant of the XSS check is written and runnable.

Why it is parked:

- **The browser oracle is not dependable here.** With the fail-open paths closed, the *reference
  solution's own output* wedged headless Chrome twice (20 s, then 90 s on the retry). A check that hangs
  on the reference solution reports on Chrome, not on the agent.
- **The static oracle over-fails.** Asked the same question without a browser, the reference filter leaves
  `<script>`, `onerror=` handlers, `javascript:` and `vbscript:` in 63 of 439 vectors — it is an
  incomplete sanitiser that passed upstream only because the browser check was fail-open. A static check
  also cannot tell an inert leftover (inside a comment or `<textarea>`) from live script, so it cannot be
  the oracle either.
- Repairing it properly means rewriting the reference solution *and* deciding what "removes JavaScript"
  means operationally. That is authoring work, and `tasks/authored/` is where authoring belongs.

Keep the cell in `docs/task-side.json`: its verdicts are not about the agents.
