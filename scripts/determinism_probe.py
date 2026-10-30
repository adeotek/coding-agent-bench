#!/usr/bin/env python3
"""Measure how deterministic the model endpoint actually is.

The bench has spent a week explaining sampling noise and no time measuring the
part of it that might be removable. This probe answers one question with cents:
**if the same request is sent N times, does the endpoint answer the same thing —
and does `temperature: 0` + a fixed `seed` change that?**

Two arms, same prompt and model, N requests each:

  pinned    temperature 0, seed 42, top_p 1
  default   no sampling parameters at all (what every agent sends today)

If the provider rejects the pinned parameters the probe says so and stops — that
is a finding too (it means no agent in the bench can be made deterministic, and
the noise floor is the backend's).

Secrets: the key is read from OPENCODE_API_KEY in the environment and never
printed, logged or put on a command line.

Usage:
  python3 scripts/determinism_probe.py                 # 8 requests per arm
  python3 scripts/determinism_probe.py -n 3 --json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

BASE = "https://opencode.ai/zen/go/v1"
MODEL = os.environ.get("ZEN_MODEL", "deepseek-v4.1-flash").split("/")[-1]
# Deliberately high-entropy: many correct answers, so a sampler that varies has
# room to vary. A prompt with one obvious answer (the first version of this
# probe used "print the vowels count") comes back identical from almost any
# sampler and proves nothing.
PROMPT = (
    "Write a Python function called `bucket` that splits a list of integers into a dict of "
    "{digit_count: [numbers]} keyed by how many digits each number has, then return the three "
    "keys you find most useful in a docstring. Answer with code only."
)


def post(key: str, body: dict, session: str, timeout: float = 60.0) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{BASE}/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            # Cloudflare fronts this endpoint and rejects urllib's default UA
            # with `error code: 1010` before the request reaches the API — the
            # agents pass because their SDKs send a real one.
            "User-Agent": "coding-agent-bench/determinism-probe",
            # The go endpoint routes by session and rejects a request without
            # one (MissingSessionID, HTTP 400). That is itself a variance source
            # worth measuring: same session vs a fresh one per request.
            "x-opencode-session": session,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        try:
            return exc.code, json.loads(detail)
        except json.JSONDecodeError:
            return exc.code, {"raw": detail[:400]}
    except urllib.error.URLError as exc:
        return 0, {"raw": str(exc)[:200]}


def text_of(payload: dict) -> str:
    try:
        return (payload["choices"][0]["message"] or {}).get("content") or ""
    except (KeyError, IndexError, TypeError):
        return ""


def arm(key: str, name: str, extra: dict, n: int, fresh_sessions: bool = False) -> dict:
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": PROMPT}],
        # A reasoning model spends output tokens thinking first: at 200 the
        # content came back empty and the probe happily reported "6 identical
        # answers" — the empty string. 1500 leaves room for thought plus answer.
        "max_tokens": 1500,
        "stream": False,
    }
    body.update(extra)
    fixed = f"bench-probe-{uuid.uuid4()}"
    outs, rejected, empty = [], None, 0
    for _ in range(n):
        session = f"bench-probe-{uuid.uuid4()}" if fresh_sessions else fixed
        status, payload = post(key, body, session)
        if status != 200:
            rejected = {"status": status, **payload}
            break
        text = text_of(payload)
        if not text.strip():
            empty += 1
            continue
        outs.append(text)
    distinct = len(set(outs)) if outs else 0
    return {
        "arm": name,
        "requests": len(outs),
        "empty": empty,
        "distinct_answers": distinct,
        "identical": bool(outs) and distinct == 1,
        "rejected": rejected,
        "sample": outs[0][:120] if outs else None,
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-n", "--requests", type=int, default=8, help="requests per arm (default 8)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    opts = ap.parse_args(argv)

    key = os.environ.get("OPENCODE_API_KEY")
    if not key:
        sys.exit("determinism_probe: OPENCODE_API_KEY is not set (source .env)")

    arms = [
        arm(key, "pinned", {"temperature": 0, "seed": 42, "top_p": 1}, opts.requests),
        arm(key, "default", {}, opts.requests),
        # Same pinned request, but every call routed as its own session: if this
        # arm disagrees with `pinned`, the variance is in the provider's routing,
        # not in the sampler, and no agent can fix it.
        arm(key, "new-session", {"temperature": 0, "seed": 42, "top_p": 1}, opts.requests, fresh_sessions=True),
    ]
    result = {"base_url": BASE, "model": MODEL, "requests_per_arm": opts.requests, "arms": arms}

    if opts.json:
        print(json.dumps(result, indent=2))
        return 0
    print(f"model {MODEL} @ {BASE}, {opts.requests} requests per arm\n")
    for a in arms:
        if a["rejected"]:
            print(f"  {a['arm']:8} REJECTED: {json.dumps(a['rejected'])[:200]}")
            continue
        verdict = "deterministic" if a["identical"] else f"{a['distinct_answers']} distinct answers"
        note = f" ({a['empty']} empty: budget spent thinking)" if a.get("empty") else ""
        print(f"  {a['arm']:8} {a['requests']} requests -> {a['distinct_answers']} distinct -> {verdict}{note}")
        print(f"           first: {a['sample']!r}")
    print(
        "\nreading: `pinned` deterministic means the noise is removable at the model layer "
        "(temperature/seed are worth plumbing through every adapter); `default` deterministic "
        "would mean the endpoint ignores sampling and repeats byte-identically, which would make "
        "the bench's measured cell rates a mystery worth chasing."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
