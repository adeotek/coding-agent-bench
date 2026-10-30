#!/bin/bash
set -euo pipefail

cat > /app/cleanup.sh <<'SH'
#!/bin/bash
# Delete files older than N days under a directory. Dry run unless --apply.
set -uo pipefail

usage() {
    echo "usage: cleanup.sh [--days N] [--apply] <directory>" >&2
    exit 2
}

DAYS=7
APPLY=0
DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        --days)
            [ $# -ge 2 ] || usage
            DAYS="$2"
            shift 2
            ;;
        --apply)
            APPLY=1
            shift
            ;;
        --)
            shift
            break
            ;;
        -*)
            usage
            ;;
        *)
            [ -z "$DIR" ] || usage
            DIR="$1"
            shift
            ;;
    esac
done
[ -n "$DIR" ] || usage

case "$DAYS" in
    ''|*[!0-9]*) echo "cleanup: --days needs a positive integer, got '$DAYS'" >&2; exit 2 ;;
esac
[ "$DAYS" -gt 0 ] || { echo "cleanup: --days must be greater than 0" >&2; exit 2; }

[ -d "$DIR" ] || { echo "cleanup: not a directory: $DIR" >&2; exit 2; }
RESOLVED=$(cd "$DIR" 2>/dev/null && pwd -P) || { echo "cleanup: cannot resolve $DIR" >&2; exit 2; }
[ "$RESOLVED" != "/" ] || { echo "cleanup: refusing to clean /" >&2; exit 2; }

# -P: never follow symlinks. Symlinks are skipped explicitly so a link to an old file is not removed
# either (removing the link is harmless, but the contract says skipped, and a link out of the tree
# makes "is it older" a question about someone else's file).
while IFS= read -r -d '' path; do
    if [ -L "$path" ]; then
        continue
    fi
    if [ "$APPLY" = "1" ]; then
        rm -f -- "$path" && echo "removed $path"
    else
        echo "would remove $path"
    fi
done < <(find -P "$DIR" -type f -mtime +"$DAYS" -print0 | sort -z)

exit 0
SH

chmod +x /app/cleanup.sh
bash -n /app/cleanup.sh
