`/app/cleanup.sh` deletes old files under a directory. It is currently dangerous, and it is about to be
run as root on a production host.

Rewrite it so that it is safe by default, keeping the same job:

    cleanup.sh [--days N] [--apply] <directory>

Contract (the tests in `/tests` check exactly this):

- `--days N` defaults to `7`. N must be a positive integer; anything else is a usage error.
- The tool is **dry-run by default**: without `--apply` it prints what it *would* delete and deletes
  nothing. With `--apply` it deletes.
- One line per candidate on stdout: `would remove <path>` in a dry run, `removed <path>` when applied.
  Paths are printed as given on the command line plus the relative part.
- Exit `2` (with a message on stderr and **nothing deleted**) when: no directory is given, the directory
  does not exist or is not a directory, the directory is `/` or resolves to `/`, or `--days` is invalid.
- Never delete anything outside `<directory>`. Do not follow symlinks: a symlink is skipped, never
  descended and never deleted through.
- A file is a candidate when its modification time is older than `N` days.
- Exit `0` when the run completes, including when there were no candidates.

Do not change the file's name or interpreter. `bash -n` must stay clean.
