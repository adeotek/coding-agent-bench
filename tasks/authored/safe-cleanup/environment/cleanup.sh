#!/bin/bash
# Delete files older than N days under a directory.
#
# Known problems (this is the version you are asked to fix):
#   * an empty or missing argument deletes from the current directory or from /
#   * it follows symlinks, so a link inside the tree can delete files outside it
#   * there is no dry run: it deletes on the first invocation
#   * --days accepts 0, which matches everything

set -u

DAYS=7
if [ "${1:-}" = "--days" ]; then
    DAYS="$2"
    shift 2
fi

DIR="${1:-}"

find -L "$DIR" -type f -mtime +"$DAYS" -delete
