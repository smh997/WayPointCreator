#!/usr/bin/env python3
"""
Few-shot example pool for the LLM backends.

METHODOLOGICAL CONTRACT — read before editing:

  These examples are NOT part of the evaluation set. They exist solely to be
  embedded in the system prompt as demonstrations. `dataset.jsonl` remains a
  pure test set: nothing here is ever scored, and the build ASSERTS zero overlap
  with the test utterances. If an example ever collides with a test row, this
  script fails loudly rather than silently contaminating the benchmark.

  Two rules govern what goes in here:

  1. Demonstrate the SCHEMA, not the TEST PHRASINGS. Examples use plain,
     canonical wordings ("move waypoint 3 down by 10 centimeters"). They must NOT
     use the colloquial/hedged style of the dataset's phrasing-stress slice
     ("scoot the last one down four centimeters please"). Teaching the model the
     test's flavour would make RQ3 (robustness to phrasing variation) unmeasurable —
     we would be testing memorisation, not generalisation.

  2. Cover each structural feature ONCE. The job of these examples is to pin the
     conventions the schema description states in prose: sign convention, unit
     conversion, the "last" reference, null-vs-populated fields, and — most
     importantly — that declining is a legitimate answer.

  Coverage (12 examples):
    offset  +z / -z          sign convention on the primary axis
    offset  -y               sign convention on a horizontal axis
    offset  rz (degrees)     degrees -> radians conversion
    reference "last"         the non-integer reference form
    create / delete / delete_all   the null-reference and populated-reference forms
    navigation x2            intent mapping
    execution x1             the deferred safety verb form
    reject x2                out-of-scope AND under-specified — the two reject reasons

Usage:
  py build_fewshot.py          # writes fewshot_pool.jsonl, asserts no test overlap
"""
import json
import math

DEG = math.pi / 180.0

def rad(d):  return round(d * DEG, 6)
def m(cm):   return round(cm / 100.0, 6)

# ----------------------------------------------------------------------
# The pool. Plain canonical phrasings only.
# ----------------------------------------------------------------------
EXAMPLES = [
    # --- offset: sign convention on the primary (vertical) axis ---
    ("move waypoint 3 up by 10 centimeters",
     {"type": "authoring", "operation": "offset", "reference": 3,
      "axis": "z", "offset": m(10)},
     "up -> +z"),

    ("move waypoint 1 down by 6 centimeters",
     {"type": "authoring", "operation": "offset", "reference": 1,
      "axis": "z", "offset": -m(6)},
     "down -> -z"),

    # --- offset: sign convention on a horizontal axis (the hard case) ---
    ("move waypoint 4 to the right by 8 centimeters",
     {"type": "authoring", "operation": "offset", "reference": 4,
      "axis": "y", "offset": -m(8)},
     "right -> -y (UR10 base frame)"),

    # --- offset: unit conversion, degrees -> radians ---
    ("rotate waypoint 2 by 45 degrees around z",
     {"type": "authoring", "operation": "offset", "reference": 2,
      "axis": "rz", "offset": rad(45)},
     "degrees -> radians"),

    # --- reference: the "last" form ---
    ("move the last waypoint up by 3 centimeters",
     {"type": "authoring", "operation": "offset", "reference": "last",
      "axis": "z", "offset": m(3)},
     'reference "last"'),

    # --- authoring: create (null reference) ---
    ("create a waypoint",
     {"type": "authoring", "operation": "create", "reference": None,
      "axis": None, "offset": None},
     "create -> null reference"),

    # --- authoring: delete (populated reference) ---
    ("delete waypoint 5",
     {"type": "authoring", "operation": "delete", "reference": 5,
      "axis": None, "offset": None},
     "delete -> reference set, axis/offset null"),

    # --- authoring: delete_all ---
    ("delete all the waypoints",
     {"type": "authoring", "operation": "delete_all", "reference": None,
      "axis": None, "offset": None},
     "delete_all -> null reference"),

    # --- navigation ---
    ("bring up the configuration panel",
     {"type": "navigation", "intent": "configure"},
     "menu transition"),

    ("put me in edit mode",
     {"type": "navigation", "intent": "edit_mode"},
     "mode switch"),

    # --- execution: the deferred safety verb ---
    ("execute the trajectory",
     {"type": "execution", "verb": "run"},
     "safety verb -> type execution"),

    # --- reject: out of scope ---
    ("what time is it",
     {"type": "reject"},
     "out of scope -> decline"),

    # --- reject: under-specified (missing the amount) ---
    ("move waypoint 2 up",
     {"type": "reject"},
     "under-specified (no amount) -> decline, do not guess"),
]


def build_prompt_block():
    """Render the examples as a prompt section."""
    lines = ["", "EXAMPLES", ""]
    for utt, obj, _note in EXAMPLES:
        lines.append(f'Command: "{utt}"')
        lines.append(json.dumps(obj, separators=(", ", ": ")))
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    # ---- HARD CONTRACT: no overlap with the test set ----
    test = set()
    with open("dataset.jsonl") as f:
        for line in f:
            if line.strip():
                test.add(json.loads(line)["utterance"].strip().lower())

    pool = [u.strip().lower() for u, _, _ in EXAMPLES]

    overlap = sorted(set(pool) & test)
    if overlap:
        raise SystemExit(
            "CONTAMINATION: few-shot examples appear in the test set:\n  "
            + "\n  ".join(overlap)
            + "\n\nThe few-shot pool must be disjoint from dataset.jsonl."
        )

    dupes = [u for u in set(pool) if pool.count(u) > 1]
    assert not dupes, f"duplicate examples in pool: {dupes}"

    with open("fewshot_pool.jsonl", "w") as f:
        for utt, obj, note in EXAMPLES:
            f.write(json.dumps({"utterance": utt, "ground_truth": obj,
                                "demonstrates": note}) + "\n")

    from collections import Counter
    by_type = Counter(o["type"] for _, o, _ in EXAMPLES)

    print(f"Few-shot pool: {len(EXAMPLES)} examples -> fewshot_pool.jsonl")
    print(f"  by type: {dict(by_type)}")
    print(f"  overlap with dataset.jsonl ({len(test)} test rows): 0  OK")
    print()
    print("Demonstrates:")
    for _, _, note in EXAMPLES:
        print(f"  - {note}")
