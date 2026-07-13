#!/usr/bin/env python3
"""
Backend B — Local LLM via Ollama (schema-constrained structured output).

Calls a locally-served model through Ollama's REST API and maps each utterance
to one structured command object, constrained by a JSON Schema so the model
cannot emit free text. No third-party packages: uses urllib from the standard
library, so there is no pip dependency and no Python 3.14 wheel risk.

Design notes that matter for the paper:
  * temperature = 0 (deterministic decoding), per SCHEMA_SPEC §5.4.
  * The system prompt describes the schema and the UR10 base-frame convention.
    It deliberately contains NO utterances or paraphrases from the evaluation
    dataset — the prompt was written from SCHEMA_SPEC.md only. Leaking test
    phrasings into the prompt would contaminate the benchmark.
  * `latency_s` times ONLY the model call (not file IO, not scoring), which is
    what Table 2 reports.
  * Malformed / unparseable output is emitted as prediction=null; score.py
    counts that as an exact-match failure and logs it (SCHEMA_SPEC §5.4).

Usage:
  py backend_b_ollama.py --model qwen2.5:7b-instruct --out preds_B_qwen.jsonl
  py backend_b_ollama.py --model llama3.1:8b        --out preds_B_llama.jsonl

  # warm the model first (excludes cold-load time from latency stats):
  py backend_b_ollama.py --model qwen2.5:7b-instruct --out preds_B_qwen.jsonl --warmup
"""
import argparse
import json
import time
import urllib.request
import urllib.error

OLLAMA_URL = "http://localhost:11434/api/chat"

# ----------------------------------------------------------------------
# JSON Schema — mirrors SCHEMA_SPEC.md §2 exactly.
# Ollama passes this to llama.cpp's grammar-constrained decoder, so the model
# structurally cannot produce an object outside this shape.
# ----------------------------------------------------------------------
COMMAND_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["authoring", "navigation", "execution", "reject"],
        },
        # authoring fields
        "operation": {
            "type": ["string", "null"],
            "enum": ["create", "delete", "offset", "delete_all", None],
        },
        "reference": {
            "type": ["integer", "string", "null"],
        },
        "axis": {
            "type": ["string", "null"],
            "enum": ["x", "y", "z", "rx", "ry", "rz", None],
        },
        "offset": {
            "type": ["number", "null"],
        },
        # navigation field
        "intent": {
            "type": ["string", "null"],
            "enum": ["configure", "trajectory", "preview", "run", "exit",
                     "create_mode", "edit_mode", "delete_mode", None],
        },
        # execution field
        "verb": {
            "type": ["string", "null"],
            "enum": ["run", "confirm", "cancel", "stop", None],
        },
        # model-reported, NOT scored for correctness (SCHEMA_SPEC §2.5)
        "confidence": {
            "type": ["number", "null"],
        },
    },
    "required": ["type"],
}

# ----------------------------------------------------------------------
# System prompt — written from SCHEMA_SPEC.md, NOT from the dataset.
# No dataset utterances or paraphrases appear here.
# ----------------------------------------------------------------------
SYSTEM_PROMPT = """You map a spoken command into ONE structured JSON command for an augmented-reality robot waypoint authoring system (AURaPath, a UR10 arm).

Output exactly one JSON object. No prose.

There are four command types.

1) "authoring" — edit the waypoint list.
   operation: "create" | "delete" | "offset" | "delete_all"
   reference: which waypoint. An integer id (1-indexed), or the string "last", or null.
              Use null for "create" and "delete_all" (they need no target).
   axis:      only for "offset". One of x, y, z (translation) or rx, ry, rz (rotation). Otherwise null.
   offset:    only for "offset". A signed number in SI base units:
              METERS for x/y/z, RADIANS for rx/ry/rz. Otherwise null.

   Direction-to-axis mapping, in the UR10 BASE frame (fixed convention):
     up      -> axis z, positive
     down    -> axis z, negative
     forward -> axis x, positive
     back    -> axis x, negative
     left    -> axis y, positive
     right   -> axis y, negative

   Unit conversion is required:
     centimeters -> meters   (e.g. 5 cm  -> 0.05)
     degrees     -> radians  (e.g. 10 deg -> 0.174533)

2) "navigation" — move between menus/modes.
   intent: "configure" | "trajectory" | "preview" | "run" | "exit"
         | "create_mode" | "edit_mode" | "delete_mode"
   Also report confidence, a number between 0 and 1.

3) "execution" — a safety-critical verb.
   verb: "run" | "confirm" | "cancel" | "stop"
   Also report confidence, a number between 0 and 1.

   Map by MEANING, not by exact wording. Users express these verbs naturally:
     - Any instruction to start/execute/send the authored motion  -> verb "run"
     - Any expression of agreement, assent, or approval           -> verb "confirm"
     - Any expression of withdrawal, dismissal, or calling it off -> verb "cancel"
     - Any demand to immediately cease or abandon robot motion    -> verb "stop"
   These are in scope even when phrased indirectly or colloquially. A short
   utterance whose intent is clearly one of these four verbs is "execution",
   NOT "reject" and NOT an authoring command.

4) "reject" — REFUSE rather than guess. Use this when the command is:
   - out of scope for this system (not about waypoints, menus, or running the robot),
   - an operation this system does not support,
   - or under-specified / ambiguous (e.g. an offset with no target, no direction, or no amount).
   For "reject", output only {"type": "reject"}.

Do not guess. If a required field for the operation is missing from the command, return reject.
Set fields that do not apply to null."""


def build_payload(model, utterance):
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": utterance},
        ],
        "stream": False,
        "format": COMMAND_SCHEMA,   # schema-constrained decoding
        "options": {
            "temperature": 0,       # deterministic (SCHEMA_SPEC §5.4)
            "seed": 0,
            "num_predict": 128,
        },
    }


def call_ollama(model, utterance, timeout=120):
    """Returns (parsed_obj_or_None, latency_seconds, raw_text)."""
    payload = json.dumps(build_payload(model, utterance)).encode("utf-8")
    req = urllib.request.Request(
        OLLAMA_URL, data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as e:
        dt = time.perf_counter() - t0
        return None, dt, f"<request failed: {e}>"
    dt = time.perf_counter() - t0

    raw = body.get("message", {}).get("content", "")
    try:
        obj = json.loads(raw)
        if not isinstance(obj, dict):
            obj = None
    except (json.JSONDecodeError, TypeError):
        obj = None
    return obj, dt, raw


def normalize(obj):
    """Light cleanup that does NOT change semantics:
    - drop nulled-out fields the schema allowed but that don't apply
    - coerce a numeric string reference ("2") to int
    Scoring compares field values, so we keep everything else verbatim.
    """
    if obj is None:
        return None
    out = dict(obj)
    ref = out.get("reference")
    if isinstance(ref, str) and ref.strip().isdigit():
        out["reference"] = int(ref.strip())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset.jsonl")
    ap.add_argument("--model", required=True, help="e.g. qwen2.5:7b-instruct")
    ap.add_argument("--out", required=True)
    ap.add_argument("--warmup", action="store_true",
                    help="send one throwaway call first so cold-load time is not in the stats")
    ap.add_argument("--limit", type=int, default=None, help="only run first N rows (smoke test)")
    args = ap.parse_args()

    rows = []
    with open(args.dataset) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    if args.limit:
        rows = rows[:args.limit]

    if args.warmup:
        print(f"Warming up {args.model} ...", flush=True)
        _, dt, _ = call_ollama(args.model, "warm up")
        print(f"  cold call took {dt:.2f}s (excluded from results)\n", flush=True)

    out = []
    malformed = 0
    t_start = time.perf_counter()

    for i, r in enumerate(rows, 1):
        obj, dt, raw = call_ollama(args.model, r["utterance"])
        obj = normalize(obj)
        if obj is None or "type" not in obj:
            malformed += 1
            print(f"  [{i:3d}/{len(rows)}] MALFORMED  {r['utterance'][:45]!r}  raw={raw[:60]!r}",
                  flush=True)
            obj = None
        out.append({"id": r["id"], "prediction": obj, "latency_s": round(dt, 4)})

        if i % 20 == 0 or i == len(rows):
            elapsed = time.perf_counter() - t_start
            rate = elapsed / i
            eta = rate * (len(rows) - i)
            print(f"  [{i:3d}/{len(rows)}]  {elapsed:5.1f}s elapsed  "
                  f"~{rate:.2f}s/call  ETA {eta:4.0f}s", flush=True)

    with open(args.out, "w") as f:
        for o in out:
            f.write(json.dumps(o) + "\n")

    lat = [o["latency_s"] for o in out]
    lat.sort()
    p95 = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]
    print(f"\nBackend B — {args.model}")
    print(f"  wrote {len(out)} predictions -> {args.out}")
    print(f"  malformed outputs: {malformed}")
    print(f"  latency  mean {sum(lat)/len(lat):.3f}s   "
          f"median {lat[len(lat)//2]:.3f}s   p95 {p95:.3f}s")
    print(f"\nNow score it:")
    print(f"  py score.py --pred {args.out} --system \"B — {args.model}\" "
          f"--by-category --json-out results_B_{args.model.split(':')[0]}.json")


if __name__ == "__main__":
    main()
