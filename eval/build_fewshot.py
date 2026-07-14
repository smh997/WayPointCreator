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
    offset  +z / -z          up / down
    offset  +y / -y          left / right   <- all four horizontal signs, not just one
    offset  +x / -x          forward / back
    offset  rz (degrees)     degrees -> radians conversion
    reference "last"         the non-integer reference form
    create / delete / delete_all   the null-reference and populated-reference forms
    navigation x2            intent mapping
    execution x1             the deferred safety verb form
    reject x2                out-of-scope AND under-specified — the two reject reasons

  REVISION HISTORY:
    v1 (13 examples) demonstrated only up, down, and right. The ablation revealed
    that the models MEMORISE demonstrated cases rather than generalising the rule:
    `offset_right` improved to zero errors while `offset_left` was COMPLETELY
    unchanged (all three still sign-flipped), and forward/back still confused x
    with z. The models did not infer "if right is -y then left is +y" even though
    the prose direction table states exactly that.

    Since the stated rule is "cover each structural feature once", and there are
    SIX direction/sign mappings rather than three, v1 under-covered. v2 demonstrates
    all six. This is the pool's only revision: it restores the original design rule
    rather than tuning toward the test set. Enforced by assert_direction_coverage().

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
    # --- offset: the SIX direction/sign mappings, one example each ---
    #
    # REVISION NOTE (v2): v1 demonstrated only up, down, and right. The ablation
    # showed the models memorised the demonstrated cases rather than generalising
    # the rule: `offset_right` went to zero errors while `offset_left` was
    # COMPLETELY unchanged (all three still sign-flipped), and forward/back still
    # confused x with z. The models did not infer "if right is -y then left is +y",
    # even though the prose direction table states it.
    #
    # That asymmetry was a defect in this pool, not a property of the task: the
    # stated design rule is "cover each structural feature once", and there are SIX
    # direction/sign mappings, not three. v2 restores that rule by demonstrating all
    # six. This is the pool's one and only revision.

    ("move waypoint 3 up by 10 centimeters",
     {"type": "authoring", "operation": "offset", "reference": 3,
      "axis": "z", "offset": m(10)},
     "up -> +z"),

    ("move waypoint 1 down by 6 centimeters",
     {"type": "authoring", "operation": "offset", "reference": 1,
      "axis": "z", "offset": -m(6)},
     "down -> -z"),

    ("move waypoint 4 to the right by 8 centimeters",
     {"type": "authoring", "operation": "offset", "reference": 4,
      "axis": "y", "offset": -m(8)},
     "right -> -y"),

    ("move waypoint 2 to the left by 7 centimeters",
     {"type": "authoring", "operation": "offset", "reference": 2,
      "axis": "y", "offset": m(7)},
     "left -> +y"),

    ("move waypoint 5 forward by 12 centimeters",
     {"type": "authoring", "operation": "offset", "reference": 5,
      "axis": "x", "offset": m(12)},
     "forward -> +x"),

    ("move waypoint 6 backward by 9 centimeters",
     {"type": "authoring", "operation": "offset", "reference": 6,
      "axis": "x", "offset": -m(9)},
     "back -> -x"),

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


def assert_direction_coverage():
    """All six direction/sign mappings must be demonstrated.

    This exists because v1 of the pool silently under-covered: it demonstrated
    `right -> -y` but not `left -> +y`, and the models then got `right` correct
    while leaving `left` entirely unfixed -- they memorised the shown case rather
    than inferring the opposite sign. An unbalanced pool produces an unbalanced
    result that is easy to mistake for a model limitation. Fail loudly instead.
    """
    want = {("z", +1), ("z", -1), ("y", +1), ("y", -1), ("x", +1), ("x", -1)}
    have = set()
    for _utt, obj, _note in EXAMPLES:
        if obj.get("operation") == "offset":
            ax, off = obj.get("axis"), obj.get("offset")
            if ax in ("x", "y", "z") and off is not None:
                have.add((ax, 1 if off > 0 else -1))
    missing = want - have
    if missing:
        raise SystemExit(
            "UNBALANCED POOL: these direction/sign mappings are not demonstrated: "
            f"{sorted(missing)}\nEvery axis must show BOTH signs, or the models will "
            "memorise the demonstrated case and leave its opposite unfixed."
        )
    return sorted(have)


if __name__ == "__main__":
    # ---- CONTRACT 1: every direction/sign pair is demonstrated ----
    covered = assert_direction_coverage()

    # ---- CONTRACT 2: no overlap with the test set ----
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

    print(f"Few-shot pool v2: {len(EXAMPLES)} examples -> fewshot_pool.jsonl")
    print(f"  by type: {dict(by_type)}")
    print(f"  overlap with dataset.jsonl ({len(test)} test rows): 0  OK")
    print(f"  direction/sign coverage: all 6 demonstrated  OK")
    print(f"    {covered}")
    print()
    print("Demonstrates:")
    for _, _, note in EXAMPLES:
        print(f"  - {note}")
