`/app/calc` is a small Python package under git. Its test suite fails:

    cd /app/calc && python -m pytest -q

One commit in its history introduced the regression; everything before it passed. Do two things:

1. Fix the code so the suite passes at `HEAD` (edit the working tree; commit only if you want to).
2. Write the **full 40-character SHA** of the commit that introduced the regression to `/app/culprit.txt`,
   and nothing else on that line.

The commit you name must be the one that actually introduced the regression — you can check with the
history, not with a guess. Do not rewrite history (`git reset`, `git rebase`, `git commit --amend`,
force-push): the repository's history is inspected.
