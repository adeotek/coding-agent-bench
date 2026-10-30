#!/bin/bash
# Repaired verifier for the `configure-git-webserver` cell.
#
# Upstream's version ran the five clone/commit/push commands and then asserted only that the string
# "TEST PASSED" appeared in its own output, so a *stale* file left in the webroot could pass it while
# a working push failed — and every intermediate failure was swallowed into one anonymous assertion.
# It also hardcoded user `git` + password `password` while the instruction said the login was handled
# ("you don't have to worry about that"), which no agent could infer: agents created `user`, `ubuntu`
# or a key-only account and failed a cell they had actually built.
#
# This version (a) states the credential contract in the instruction, (b) asserts every step, and
# (c) pushes a file with a random name whose content cannot pre-exist, so passing requires a live
# push -> deploy path rather than a leftover artifact.
#
# Writes a machine-readable report to /tmp/verify-report.json and exits 0 unless the verifier itself
# could not run; pytest asserts the individual checks.

set -u

REPORT=/tmp/verify-report.json
TMPROOT=$(mktemp -d)
ERRORS=()
STEPS_CLONE=""
STEPS_COMMIT=""
STEPS_PUSH=""

note() { echo "--- $*"; }

# sshpass answers the password prompt non-interactively; expect was the fragile part of upstream.
if ! command -v sshpass >/dev/null 2>&1; then
  note "installing sshpass"
  apt-get update -qq >/dev/null 2>&1 || true
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq sshpass >/dev/null 2>&1 || true
fi
if ! command -v sshpass >/dev/null 2>&1; then
  ERRORS+=("could not install sshpass (verifier infrastructure, not the agent's fault)")
fi

mkdir -p ~/.ssh && chmod 700 ~/.ssh
cat > ~/.ssh/config <<'EOF'
Host localhost
    StrictHostKeyChecking no
    UserKnownHostsFile=/dev/null
    PubkeyAuthentication no
    PreferredAuthentications password
EOF
chmod 600 ~/.ssh/config

export GIT_SSH_COMMAND="sshpass -p password ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PubkeyAuthentication=no -o PreferredAuthentications=password -o ConnectTimeout=5"

# The agent's sshd may still be coming up; the clone is the step that waits for it.
cd "$TMPROOT" || exit 1
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if git clone -q git@localhost:/git/server server-test 2>"$TMPROOT/clone.err"; then
    STEPS_CLONE=true
    break
  fi
  sleep 1
done
if [ "${STEPS_CLONE:-}" != "true" ]; then
  ERRORS+=("git clone git@localhost:/git/server failed: $(tail -3 "$TMPROOT/clone.err" | tr '\n' ' ')")
fi

TOKEN=$(head -c 6 /dev/urandom | od -An -tx1 | tr -d ' \n')
PROOF="proof-$TOKEN.html"

if [ "${STEPS_CLONE:-}" = "true" ]; then
  cd "$TMPROOT/server-test" || exit 1
  git config --local user.email "test@example.com"
  git config --local user.name "Bench Verifier"

  echo "hello world" > hello.html
  git add hello.html
  if git commit -q -m "add hello.html" 2>"$TMPROOT/commit.err"; then
    STEPS_COMMIT=true
  else
    ERRORS+=("git commit failed: $(tail -3 "$TMPROOT/commit.err" | tr '\n' ' ')")
  fi

  if [ "${STEPS_COMMIT:-}" = "true" ]; then
    # `git push origin master` exactly as the instruction writes it.
    if git push -q origin master 2>"$TMPROOT/push.err"; then
      STEPS_PUSH=true
    else
      ERRORS+=("git push origin master failed: $(tail -3 "$TMPROOT/push.err" | tr '\n' ' ')")
    fi
  fi

  # The proof file: a name that cannot exist before this push, carrying a random body.
  if [ "${STEPS_PUSH:-}" = "true" ]; then
    echo "$TOKEN" > "$PROOF"
    git add "$PROOF"
    git commit -q -m "proof $TOKEN" 2>>"$TMPROOT/commit.err" || ERRORS+=("commit of $PROOF failed")
    git push -q origin master 2>>"$TMPROOT/push.err" || ERRORS+=("push of $PROOF failed")
  fi
fi

# --- HTTP checks ------------------------------------------------------------
fetch() { # fetch <name> <body-file> -> status on stdout
  curl -s --max-time 10 --retry 5 --retry-delay 1 --retry-connrefused \
       -o "$2" -w '%{http_code}' "http://localhost:8080/$1" 2>/dev/null || echo 000
}

HELLO_STATUS=$(fetch hello.html "$TMPROOT/hello.body")
HELLO_BODY=$(tr -d '\r' < "$TMPROOT/hello.body" 2>/dev/null | sed -e 's/[[:space:]]*$//')
PROOF_STATUS=$(fetch "$PROOF" "$TMPROOT/proof.body")
PROOF_BODY=$(tr -d '\r' < "$TMPROOT/proof.body" 2>/dev/null | sed -e 's/[[:space:]]*$//')

note "clone=${STEPS_CLONE:-false} commit=${STEPS_COMMIT:-false} push=${STEPS_PUSH:-false}"
note "hello.html -> HTTP $HELLO_STATUS body=[$HELLO_BODY]"
note "$PROOF -> HTTP $PROOF_STATUS body=[$PROOF_BODY]"

python3 - "$REPORT" "${STEPS_CLONE:-false}" "${STEPS_COMMIT:-false}" "${STEPS_PUSH:-false}" \
          "$HELLO_STATUS" "$HELLO_BODY" "$PROOF" "$PROOF_STATUS" "$PROOF_BODY" "$TOKEN" \
          "${ERRORS[@]-}" <<'PY'
import json, sys
args = sys.argv[1:]
report, clone, commit, push, hstatus, hbody, proof, pstatus, pbody, token = args[:10]
errs = args[10:]
data = {
    "steps": {"clone": clone == "true", "commit": commit == "true", "push": push == "true"},
    "hello_html": {"status": int(hstatus or 0), "body": hbody},
    "proof": {"name": proof, "status": int(pstatus or 0), "body": pbody, "token": token},
    "errors": [e for e in errs if e],
}
open(report, "w").write(json.dumps(data, indent=2))
print(json.dumps(data, indent=2))
PY

rm -rf "$TMPROOT"
exit 0
