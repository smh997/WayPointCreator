#!/usr/bin/env python3
"""
Backend E — Cloud LLM via Groq (free tier, LPU inference).

Same task, same schema, same FROZEN PROMPT as Backends B and D. The prompt is
imported from backend_b_ollama.py, not copied, so the backends cannot drift.

Why Groq is in the comparison:

  * llama-3.1-8b-instant is the SAME model lineage as Backend B's local Ollama
    llama3.1:8b (both meta-llama/Llama-3.1-8B-Instruct). That gives a controlled
    local-vs-cloud comparison: the model is held constant and only the serving
    stack changes.

    CAVEAT (state this in the paper): the local copy is 4-bit quantised (Q4_K_M,
    what Ollama ships by default) while Groq serves at higher precision. So the
    comparison is quantised-local vs. full-precision-cloud, not a pure
    infrastructure ablation. That is arguably the more realistic deployment
    question -- it is what you actually get on each -- but it is two variables,
    not one.

  * openai/gpt-oss-20b supports full structured_outputs (json_schema), matching
    the constraint mode used by Backends B and D, so the cloud tier is not
    represented by a single vendor.

CONSTRAINT MODE -- this differs by model and MUST be reported:
    openai/gpt-oss-20b     -> json_schema  (schema-constrained, same as B and D)
    llama-3.1-8b-instant   -> json_object  (valid JSON guaranteed, schema NOT enforced)
Groq only advertises structured_outputs on some models. Where json_schema is
unavailable we fall back to json_object and the model is steered by the prompt
alone. The script prints which mode it used, and it is a genuine methodological
difference, not an implementation detail to bury.

Usage:
  setx GROQ_API_KEY "..."
  py backend_e_groq.py --model llama-3.1-8b-instant --out preds_E_llama.jsonl
  py backend_e_groq.py --model openai/gpt-oss-20b   --out preds_E_oss.jsonl --few-shot
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

from backend_b_ollama import SYSTEM_PROMPT, get_prompt, COMMAND_SCHEMA

API_URL = "https://api.groq.com/openai/v1/chat/completions"

# Models that support full schema-constrained decoding on Groq.
STRUCTURED_OUTPUT_MODELS = {
    "openai/gpt-oss-20b",
    "openai/gpt-oss-safeguard-20b",
}

# ----------------------------------------------------------------------
# Schema, in OpenAI's json_schema dialect (Groq is OpenAI-compatible).
# Same fields and enums as SCHEMA_SPEC.md §2 and Backends B and D.
#
# `strict` is deliberately FALSE, and that choice cost us a run, so it is
# documented rather than left as a silent flag:
#
#   Under `strict: true`, OpenAI's dialect mandates that EVERY property appear in
#   `required` -- optionality is not expressible. Groq then validates server-side
#   and HARD-REJECTS (HTTP 400) any response missing a required key.
#
#   GPT-OSS 20B answers a reject row with {"type": "reject"} -- which is exactly
#   the correct object per SCHEMA_SPEC §2.4, where reject is type-only. Strict mode
#   threw that correct answer away for omitting seven inapplicable keys, yielding a
#   spurious 0% reject accuracy and 42 "malformed" rows for a model that had in fact
#   answered correctly.
#
#   With `strict: false` the schema still guides generation, but a minimal,
#   semantically correct object is no longer discarded.
#
# Note the providers enforce in OPPOSITE directions, so one `required` list cannot
# serve both:
#   Gemini -- a permissive schema lets its decoder silently OMIT fields, so every
#             property must be required (it dropped axis/offset otherwise).
#   Groq   -- a rigid schema causes server-side REJECTION of minimal objects, so
#             strictness must be relaxed.
# Fields and enums are identical across B, D, and E; only the enforcement plumbing
# differs, which is what keeps the comparison fair.
# ----------------------------------------------------------------------
JSON_SCHEMA = {
    "name": "aurapath_command",
    "strict": False,
    "schema": {
        "type": "object",
        "properties": {
            "type": {"type": "string",
                     "enum": ["authoring", "navigation", "execution", "reject"]},
            "operation": {"type": ["string", "null"],
                          "enum": ["create", "delete", "offset", "delete_all", None]},
            "reference": {"type": ["integer", "string", "null"]},
            "axis": {"type": ["string", "null"],
                     "enum": ["x", "y", "z", "rx", "ry", "rz", None]},
            "offset": {"type": ["number", "null"]},
            "intent": {"type": ["string", "null"],
                       "enum": ["configure", "trajectory", "preview", "run", "exit",
                                "create_mode", "edit_mode", "delete_mode", None]},
            "verb": {"type": ["string", "null"],
                     "enum": ["run", "confirm", "cancel", "stop", None]},
            "confidence": {"type": ["number", "null"]},
        },
        # Only the discriminator is universally required (SCHEMA_SPEC §2):
        # a reject object is legitimately {"type": "reject"} and nothing else.
        "required": ["type"],
    },
}


def response_format_for(model):
    """Schema-constrained where supported; plain JSON mode otherwise."""
    if model in STRUCTURED_OUTPUT_MODELS:
        return {"type": "json_schema", "json_schema": JSON_SCHEMA}, "json_schema"
    return {"type": "json_object"}, "json_object"


def build_payload(model, utterance, few_shot=False):
    rf, _mode = response_format_for(model)
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": get_prompt(few_shot)},
            {"role": "user", "content": utterance},
        ],
        "temperature": 0,          # deterministic, matching B and D
        "max_tokens": 512,
        "response_format": rf,
    }


def call_groq(model, api_key, utterance, few_shot=False, max_retries=5):
    """Return (obj_or_None, latency_of_successful_call, raw_text).

    Latency covers ONLY the successful request -- rate-limit backoff is excluded,
    so throttling cannot masquerade as model latency.
    """
    data = json.dumps(build_payload(model, utterance, few_shot)).encode("utf-8")
    delay = 5.0

    for attempt in range(max_retries):
        req = urllib.request.Request(
            API_URL, data=data,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {api_key}",
                     # Groq sits behind Cloudflare, which blocks urllib's default
                     # "Python-urllib/3.x" agent outright (error 1010). Any
                     # non-default value passes.
                     "User-Agent": "aurapath-eval/1.0"},
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            dt = time.perf_counter() - t0
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 or 500 <= e.code < 600:
                print(f"      HTTP {e.code}; backing off {delay:.0f}s "
                      f"(attempt {attempt+1}/{max_retries})", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            detail = e.read().decode("utf-8", "replace")[:300]
            return None, time.perf_counter() - t0, f"<HTTP {e.code}: {detail}>"
        except (urllib.error.URLError, TimeoutError):
            time.sleep(delay)
            delay = min(delay * 2, 60)
            continue
    else:
        return None, 0.0, "<exhausted retries>"

    try:
        raw = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None, dt, f"<unexpected envelope: {json.dumps(body)[:180]}>"

    try:
        obj = json.loads(_extract_json(raw))
        if not isinstance(obj, dict):
            obj = None
    except (json.JSONDecodeError, TypeError):
        obj = None
    return obj, dt, raw


def _extract_json(text):
    """Tolerate a ```json fence or prose wrapper (possible under json_object mode,
    where only validity -- not shape -- is guaranteed). Truncated or absent JSON
    still fails to parse and is correctly counted as malformed."""
    if not isinstance(text, str):
        return ""
    t = text.strip()
    if t.startswith("{"):
        return t
    if "```" in t:
        seg = t.split("```")[1]
        if seg.startswith("json"):
            seg = seg[4:]
        t = seg.strip()
        if t.startswith("{"):
            return t
    i, j = t.find("{"), t.rfind("}")
    return t[i:j + 1] if i != -1 and j > i else t


def normalize(obj):
    """Coerce a stringly-typed reference back to int|'last'|None. Semantics unchanged."""
    if obj is None:
        return None
    out = dict(obj)
    ref = out.get("reference")
    if isinstance(ref, str):
        r = ref.strip().lower()
        if r in ("", "null", "none"):
            out["reference"] = None
        elif r.isdigit():
            out["reference"] = int(r)
        else:
            out["reference"] = r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset.jsonl")
    ap.add_argument("--model", required=True,
                    help="llama-3.1-8b-instant | openai/gpt-oss-20b")
    ap.add_argument("--out", required=True)
    ap.add_argument("--few-shot", action="store_true")
    ap.add_argument("--rpm", type=float, default=25.0,
                    help="pace requests (Groq free tier is generous; 25 is conservative)")
    ap.add_argument("--limit", type=int, default=None, help="smoke test on first N rows")
    args = ap.parse_args()

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        sys.exit('ERROR: GROQ_API_KEY not set.\n'
                 '  Windows:  setx GROQ_API_KEY "your-key"   (then reopen the terminal)')

    rows = []
    with open(args.dataset) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    if args.limit:
        rows = rows[:args.limit]

    _rf, mode = response_format_for(args.model)
    shot = "few-shot" if args.few_shot else "zero-shot"
    min_gap = 60.0 / args.rpm

    print(f"Backend E — {args.model}  [{shot}]")
    print(f"  constraint mode: {mode}"
          + ("  (schema-constrained, same as B/D)" if mode == "json_schema"
             else "  (JSON validity only; schema NOT enforced -- report this)"))
    print(f"  {len(rows)} utterances at {args.rpm:.0f} RPM\n", flush=True)

    out, malformed = [], 0
    last_start = 0.0
    t_start = time.perf_counter()

    for i, r in enumerate(rows, 1):
        wait = min_gap - (time.perf_counter() - last_start)
        if wait > 0:
            time.sleep(wait)
        last_start = time.perf_counter()

        obj, dt, raw = call_groq(args.model, api_key, r["utterance"], args.few_shot)
        obj = normalize(obj)

        if obj is None or "type" not in obj:
            malformed += 1
            print(f"  [{i:3d}/{len(rows)}] MALFORMED {r['utterance'][:40]!r} "
                  f"raw={raw[:70]!r}", flush=True)
            obj = None

        out.append({"id": r["id"], "prediction": obj, "latency_s": round(dt, 4)})

        if i % 25 == 0 or i == len(rows):
            elapsed = time.perf_counter() - t_start
            eta = (elapsed / i) * (len(rows) - i)
            print(f"  [{i:3d}/{len(rows)}]  {elapsed/60:4.1f} min  "
                  f"ETA {eta/60:4.1f} min", flush=True)

    with open(args.out, "w") as f:
        for o in out:
            f.write(json.dumps(o) + "\n")

    lat = sorted(o["latency_s"] for o in out if o["latency_s"] > 0)
    print(f"\n  wrote {len(out)} predictions -> {args.out}")
    print(f"  malformed: {malformed}")
    if lat:
        p95 = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]
        print(f"  latency  mean {sum(lat)/len(lat):.3f}s  "
              f"median {lat[len(lat)//2]:.3f}s  p95 {p95:.3f}s")


if __name__ == "__main__":
    main()
