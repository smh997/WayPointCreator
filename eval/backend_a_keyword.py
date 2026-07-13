#!/usr/bin/env python3
"""
Backend A — Keyword baseline (deployed MRTK vocabulary, no LLM).

METHODOLOGICAL NOTE (matters for the paper):
This baseline is defined by the vocabulary the DEPLOYED HoloLens keyword layer
actually recognizes, extracted verbatim from the running system:

    Assets/Scripts/Voice/MrtkKeywordVoiceInput.cs   (keywordMap)
    Assets/MixedRealityToolkit.Generated/CustomProfiles/
        WaypointCreatorMixedRealitySpeechCommandsProfile.asset  (same phrases)

It is NOT tuned against the evaluation dataset. No synonyms, paraphrases, or
regex generalizations have been added. A baseline authored while looking at the
test set would be contaminated and would make RQ3 unanswerable.

Matching mirrors MrtkKeywordVoiceInput.cs:73 -- `.ToLowerInvariant().Trim()` on the
recognized phrase, looked up in the keyword dictionary. MRTK fires on the recognized
phrase as a whole; it does not substring-search within a sentence. We therefore
require an exact match (after lowercase / trim / trailing-punctuation strip).
An unrecognized phrase fires nothing ("Unmapped keyword heard") -> {"type": "reject"}.

STRUCTURAL LIMITATION -- this is the finding, not a defect:
The deployed vocabulary contains NO parameterized authoring commands. There is no
keyword for create, delete-single, or offset. A fixed keyword grammar cannot carry
parameters (which waypoint / which axis / how far) without enumerating every
combination (~20 waypoints x 6 directions x N magnitudes, and it still fails on an
unlisted magnitude). Backend A therefore rejects authoring utterances. That
categorical inability is precisely the gap the LLM tier exists to fill.

Usage:
  py backend_a_keyword.py --dataset dataset.jsonl --out preds_A.jsonl
"""
import argparse
import json
import time

# ----------------------------------------------------------------------
# The deployed vocabulary -- literal phrases, verbatim from keywordMap.
# Grouped exactly as the source comments group them.
# ----------------------------------------------------------------------
KEYWORD_MAP = {
    # --- run gate ---
    "run":            {"type": "execution", "verb": "run"},
    "run it":         {"type": "execution", "verb": "run"},
    "send to robot":  {"type": "execution", "verb": "run"},
    "confirm":        {"type": "execution", "verb": "confirm"},
    "confirm run":    {"type": "execution", "verb": "confirm"},
    "cancel":         {"type": "execution", "verb": "cancel"},
    "abort":          {"type": "execution", "verb": "cancel"},

    # --- emergency ---
    "stop":           {"type": "execution", "verb": "stop"},
    "halt":           {"type": "execution", "verb": "stop"},
    "stop the robot": {"type": "execution", "verb": "stop"},
    "emergency stop": {"type": "execution", "verb": "stop"},

    # --- navigation / mode ---
    "configure":      {"type": "navigation", "intent": "configure"},
    "trajectory":     {"type": "navigation", "intent": "trajectory"},
    "preview run":    {"type": "navigation", "intent": "run"},
    "preview":        {"type": "navigation", "intent": "preview"},
    "create mode":    {"type": "navigation", "intent": "create_mode"},
    "edit mode":      {"type": "navigation", "intent": "edit_mode"},
    "delete mode":    {"type": "navigation", "intent": "delete_mode"},
    "exit":           {"type": "navigation", "intent": "exit"},
    "go back":        {"type": "navigation", "intent": "exit"},

    # --- the ONLY authoring keyword that exists in the deployed layer ---
    "delete all":     {"type": "authoring", "operation": "delete_all",
                       "reference": None, "axis": None, "offset": None},
}

# The extraction reported 20 phrases in keywordMap (incl. "delete all").
assert len(KEYWORD_MAP) == 21, f"expected 21 phrases, got {len(KEYWORD_MAP)}"


def normalize(utterance):
    """Mirror MrtkKeywordVoiceInput.cs: ToLowerInvariant().Trim(), and strip trailing
    punctuation (which a speech recognizer would not include in the matched phrase)."""
    return utterance.lower().strip().rstrip(".!?,")


def map_utterance(utterance):
    """Exact-phrase lookup, as MRTK does. No match -> nothing fires -> reject."""
    hit = KEYWORD_MAP.get(normalize(utterance))
    if hit is None:
        return {"type": "reject"}
    return dict(hit)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset.jsonl")
    ap.add_argument("--out", default="preds_A.jsonl")
    args = ap.parse_args()

    rows = []
    with open(args.dataset) as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))

    out, n_hit = [], 0
    for r in rows:
        t0 = time.perf_counter()
        pred = map_utterance(r["utterance"])
        dt = time.perf_counter() - t0
        if pred["type"] != "reject":
            n_hit += 1
        out.append({"id": r["id"], "prediction": pred, "latency_s": round(dt, 6)})

    with open(args.out, "w") as f:
        for o in out:
            f.write(json.dumps(o) + "\n")

    print(f"Backend A - deployed MRTK vocabulary ({len(KEYWORD_MAP)} literal phrases)")
    print(f"  wrote {len(out)} predictions -> {args.out}")
    print(f"  utterances matching a registered keyword: {n_hit}/{len(rows)}")
    print(f"  all others fire no action -> reject")


if __name__ == "__main__":
    main()
