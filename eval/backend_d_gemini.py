#!/usr/bin/env python3
"""
Backend D — Cloud LLM API (Gemini Flash, free tier).

Same task, same schema, and — critically — the SAME FROZEN PROMPT as Backend B.
The prompt is imported from backend_b_ollama.py rather than copied, so the two
backends cannot drift apart. Any difference in the results is therefore
attributable to the model/deployment, not to prompt differences.

Design notes that matter for the paper:
  * temperature = 0 (deterministic decoding), matching Backend B.
  * Schema-constrained structured output (responseSchema), matching Backend B.
  * `latency_s` times ONLY the successful API call. Rate-limit sleeps and retries
    are EXCLUDED — otherwise free-tier throttling would masquerade as model
    latency and corrupt the B-vs-D comparison, which is the paper's headline result.
  * Free-tier RPM limits are low (~10-15 RPM depending on model/project), so the
    script paces requests and retries on HTTP 429 with exponential backoff.
  * The API key is read from the GEMINI_API_KEY environment variable. It is never
    written to disk and must never be committed.

Note on data handling: Google's free tier permits prompts to be used to improve
their models. The evaluation dataset is synthetic robot commands (no proprietary
or personal data), but this is a real deployment consideration for the local-vs-
cloud comparison and is noted in the paper's limitations.

Usage:
  set GEMINI_API_KEY=...            (Windows: setx GEMINI_API_KEY "...")
  py backend_d_gemini.py --model gemini-2.5-flash      --out preds_D_flash.jsonl
  py backend_d_gemini.py --model gemini-2.5-flash-lite --out preds_D_lite.jsonl
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

# Import the FROZEN prompt from Backend B so the two backends stay identical.
from backend_b_ollama import SYSTEM_PROMPT, get_prompt

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"

# ----------------------------------------------------------------------
# Gemini's responseSchema dialect (OpenAPI-subset). Same fields/enums as
# SCHEMA_SPEC.md §2 and the Ollama JSON Schema, expressed in Gemini's format.
# Gemini has no union types, so nullable fields use "nullable": True.
# ----------------------------------------------------------------------
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "type": {
            "type": "STRING",
            "enum": ["authoring", "navigation", "execution", "reject"],
        },
        "operation": {
            "type": "STRING",
            "enum": ["create", "delete", "offset", "delete_all"],
            "nullable": True,
        },
        # reference may be an int or the string "last" -> ask for STRING and
        # coerce numerics back to int in normalize(). Gemini cannot express a union.
        "reference": {"type": "STRING", "nullable": True},
        "axis": {
            "type": "STRING",
            "enum": ["x", "y", "z", "rx", "ry", "rz"],
            "nullable": True,
        },
        "offset": {"type": "NUMBER", "nullable": True},
        "intent": {
            "type": "STRING",
            "enum": ["configure", "trajectory", "preview", "run", "exit",
                     "create_mode", "edit_mode", "delete_mode"],
            "nullable": True,
        },
        "verb": {
            "type": "STRING",
            "enum": ["run", "confirm", "cancel", "stop"],
            "nullable": True,
        },
        "confidence": {"type": "NUMBER", "nullable": True},
    },
    # Every property must be listed as required.
    #
    # This is not cosmetic. With `required: ["type"]` (i.e. only the discriminator
    # mandatory and the rest merely `nullable`), Gemini's constrained decoder is free
    # to emit an arbitrary *subset* of properties -- and empirically it drops exactly
    # the conditionally-relevant ones we need. On "raise waypoint two by five
    # centimeters" it returned {type, operation, reference, verb:null} and silently
    # omitted `axis` and `offset`, producing a uniform 0% on both fields across the
    # whole dataset. That looked like a model failure but was a schema defect: with
    # `responseSchema` removed entirely, the same model answered correctly
    # (axis "z", offset 0.05), proving it understood the task.
    #
    # Listing every property as required forces the decoder to emit them all, using
    # null where a field does not apply to the row's type. This keeps Backend D
    # schema-constrained -- and therefore symmetric with Backend B -- rather than
    # fixing the bug by dropping structured output on one side of the comparison.
    "required": ["type", "operation", "reference", "axis", "offset",
                 "intent", "verb", "confidence"],
}


def build_payload(utterance, model="", few_shot=False):
    cfg = {
        "temperature": 0,
        "responseMimeType": "application/json",
        "responseSchema": RESPONSE_SCHEMA,
        # Generous budget: Gemini 3.x are THINKING models and spend output tokens
        # on internal reasoning before emitting the answer. A tight cap (e.g. 256)
        # gets consumed by the preamble and truncates the JSON, which looks like a
        # model failure but is actually a configuration error.
        "maxOutputTokens": 2048,
    }
    # Gemini 3.x: disable the thinking budget outright. This is a deterministic
    # slot-filling task, not a reasoning task -- we want the JSON, not a rationale.
    if "gemini-3" in model:
        cfg["thinkingConfig"] = {"thinkingBudget": 0}
    return {
        "systemInstruction": {"parts": [{"text": get_prompt(few_shot)}]},
        "contents": [{"role": "user", "parts": [{"text": utterance}]}],
        "generationConfig": cfg,
    }


def call_gemini(model, api_key, utterance, max_retries=6, few_shot=False):
    """Return (obj_or_None, latency_of_successful_call, raw_text).

    Retries on 429 / 5xx with exponential backoff. The returned latency covers
    ONLY the successful request -- backoff sleeps are deliberately excluded.
    """
    url = f"{API_ROOT}/{model}:generateContent"
    data = json.dumps(build_payload(utterance, model, few_shot)).encode("utf-8")

    delay = 5.0
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url, data=data,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            dt = time.perf_counter() - t0
            break
        except urllib.error.HTTPError as e:
            code = e.code
            if code == 429 or 500 <= code < 600:
                # rate limited / transient -> back off (NOT counted as latency)
                print(f"      HTTP {code}; backing off {delay:.0f}s "
                      f"(attempt {attempt+1}/{max_retries})", flush=True)
                time.sleep(delay)
                delay = min(delay * 2, 90)
                continue
            # non-retryable (401 bad key, 400 bad request, 404 bad model)
            detail = e.read().decode("utf-8", "replace")[:300]
            return None, time.perf_counter() - t0, f"<HTTP {code}: {detail}>"
        except (urllib.error.URLError, TimeoutError) as e:
            print(f"      network error; backing off {delay:.0f}s", flush=True)
            time.sleep(delay)
            delay = min(delay * 2, 90)
            continue
    else:
        return None, 0.0, "<exhausted retries>"

    # ---- extract the JSON text from the response envelope ----
    try:
        cand = body["candidates"][0]
        raw = cand["content"]["parts"][0]["text"]
    except (KeyError, IndexError, TypeError):
        fr = ""
        try:
            fr = body["candidates"][0].get("finishReason", "")
        except (KeyError, IndexError, TypeError):
            pass
        hint = f" finishReason={fr}" if fr else ""
        return None, dt, f"<no text in response;{hint} {json.dumps(body)[:180]}>"

    # MAX_TOKENS means the budget was exhausted (e.g. by thinking tokens) --
    # that is a config problem on our side, not a model mapping error. Surface it.
    if cand.get("finishReason") == "MAX_TOKENS":
        return None, dt, f"<TRUNCATED (MAX_TOKENS) raw={raw[:80]!r}>"

    try:
        obj = json.loads(_extract_json(raw))
        if not isinstance(obj, dict):
            obj = None
    except (json.JSONDecodeError, TypeError):
        obj = None
    return obj, dt, raw


def _extract_json(text):
    """Return the JSON object from a response.

    With responseMimeType=application/json the model should return bare JSON.
    Some preview models ignore that and wrap it in prose and/or a ```json fence.
    We tolerate that rather than scoring it as a model error, since it is a
    formatting artifact of the API, not a mapping failure. Truncated / absent
    JSON still fails to parse and is correctly counted as malformed.
    """
    if not isinstance(text, str):
        return ""
    t = text.strip()
    if t.startswith("{"):
        return t
    # strip a fenced block if present
    if "```" in t:
        seg = t.split("```")[1]
        if seg.startswith("json"):
            seg = seg[4:]
        t = seg.strip()
        if t.startswith("{"):
            return t
    # otherwise take the outermost {...}
    i, j = t.find("{"), t.rfind("}")
    return t[i:j + 1] if i != -1 and j > i else t


def normalize(obj):
    """Coerce Gemini's stringly-typed reference back to the schema's int|'last'|null.
    Does not alter semantics -- only repairs the union type Gemini cannot express.
    """
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
            out["reference"] = r  # "last"
    return out


def load_resume_state(out_path, canonical_ids):
    """Read an existing (possibly partial) output file and return {id: entry}
    for rows that actually received a server response (latency_s > 0).

    Rows that never got a response -- retry-exhausted or network failure, which
    call_gemini encodes as latency_s == 0.0 -- are dropped here so a resumed run
    retries them, instead of freezing them in a permanently-failed state.
    Corrupt/partial lines (the process was killed mid-write) are dropped too.
    Ids outside the current dataset/--limit selection are ignored.
    """
    done = {}
    if not os.path.exists(out_path):
        return done
    with open(out_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            _id = entry.get("id")
            if _id in canonical_ids and entry.get("latency_s", 0) > 0:
                done[_id] = entry
    return done


def rescore_file(out_path):
    """Malformed/latency accounting over the WHOLE file, not just the rows this
    invocation processed -- correct regardless of how many resumes it took."""
    malformed = 0
    lat = []
    with open(out_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            pred = entry.get("prediction")
            if not isinstance(pred, dict) or "type" not in pred:
                malformed += 1
            ls = entry.get("latency_s", 0)
            if ls and ls > 0:
                lat.append(ls)
    return malformed, sorted(lat)


def canonicalize_file(out_path, rows):
    """Rewrite the file in canonical dataset order.

    The "done" rows carried over from a previous run are not necessarily a
    contiguous prefix -- some rows in the middle of an interrupted run can
    succeed while later-retried ones fail, then get appended after the resume.
    Writing the done-block first and appending afterwards (as this script does
    during the run, for crash-safety) does NOT reproduce canonical dataset
    order in that case, even though every row is present and correct. This
    final pass guarantees the promised "same order" property outright, rather
    than relying on the weaker "re-sortable by id" fallback.
    """
    by_id = {}
    with open(out_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            by_id[entry["id"]] = entry
    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(by_id[r["id"]]) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset.jsonl")
    ap.add_argument("--model", required=True,
                    help="gemini-2.5-flash | gemini-2.5-flash-lite")
    ap.add_argument("--out", required=True)
    ap.add_argument("--rpm", type=float, default=10.0,
                    help="requests per minute to pace at (free tier is ~10-15)")
    ap.add_argument("--limit", type=int, default=None, help="smoke test on first N rows")
    ap.add_argument("--few-shot", action="store_true",
                    help="append the (disjoint) few-shot example block to the prompt")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        sys.exit("ERROR: GEMINI_API_KEY is not set.\n"
                 '  Windows:  setx GEMINI_API_KEY "your-key"   (then reopen the terminal)')

    rows = []
    with open(args.dataset) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    if args.limit:
        rows = rows[:args.limit]
    canonical_ids = {r["id"] for r in rows}

    # Resume support: reload any already-completed rows from a previous
    # (possibly interrupted) run at this --out path, then rewrite the file to
    # contain ONLY those valid rows, in canonical dataset order. This drops
    # stale retry-exhausted placeholders and any corrupt trailing line from a
    # hard kill, so the file has no duplicate ids at any point from here on --
    # everything appended afterwards is for a row that isn't in `done`.
    done = load_resume_state(args.out, canonical_ids)
    with open(args.out, "w") as f:
        for r in rows:
            if r["id"] in done:
                f.write(json.dumps(done[r["id"]]) + "\n")

    remaining = [r for r in rows if r["id"] not in done]

    min_gap = 60.0 / args.rpm  # seconds between request starts
    est_min = len(remaining) * min_gap / 60.0
    mode = "few-shot" if args.few_shot else "zero-shot"
    print(f"Backend D — {args.model}  [{mode}]")
    if done:
        print(f"  resuming: {len(done)}/{len(rows)} rows already completed -> skipping those")
    print(f"  {len(remaining)} utterances remaining, paced at {args.rpm:.0f} RPM "
          f"(~{min_gap:.1f}s apart) -> ~{est_min:.0f} min\n", flush=True)

    last_start = 0.0
    t_start = time.perf_counter()
    out_f = open(args.out, "a")

    for i, r in enumerate(remaining, 1):
        # pace to respect the free-tier RPM cap (this wait is NOT counted as latency)
        wait = min_gap - (time.perf_counter() - last_start)
        if wait > 0:
            time.sleep(wait)
        last_start = time.perf_counter()

        obj, dt, raw = call_gemini(args.model, api_key, r["utterance"],
                                   few_shot=args.few_shot)
        obj = normalize(obj)

        if obj is None or "type" not in obj:
            print(f"  [{i:3d}/{len(remaining)}] MALFORMED {r['utterance'][:40]!r} "
                  f"raw={raw[:70]!r}", flush=True)
            obj = None

        entry = {"id": r["id"], "prediction": obj, "latency_s": round(dt, 4)}
        # Persist as soon as this row completes -- not buffered to end of run --
        # so a kill/quota-wall never loses progress already made.
        out_f.write(json.dumps(entry) + "\n")
        out_f.flush()
        os.fsync(out_f.fileno())

        if i % 10 == 0 or i == len(remaining):
            elapsed = time.perf_counter() - t_start
            eta = (elapsed / i) * (len(remaining) - i)
            print(f"  [{i:3d}/{len(remaining)}]  {elapsed/60:4.1f} min elapsed  "
                  f"ETA {eta/60:4.1f} min", flush=True)

    out_f.close()
    canonicalize_file(args.out, rows)

    malformed, lat = rescore_file(args.out)
    print(f"\n  wrote {len(rows)} predictions total -> {args.out}")
    print(f"  malformed: {malformed}")
    if lat:
        p95 = lat[min(len(lat) - 1, int(round(0.95 * (len(lat) - 1))))]
        print(f"  latency (successful calls only)  mean {sum(lat)/len(lat):.3f}s  "
              f"median {lat[len(lat)//2]:.3f}s  p95 {p95:.3f}s")
    tag = args.model.replace("gemini-", "").replace(".", "").replace("-", "_")
    print(f"\nNow score it:")
    print(f'  py score.py --pred {args.out} --system "D — {args.model}" '
          f"--by-category --json-out results_D_{tag}.json")


if __name__ == "__main__":
    main()
