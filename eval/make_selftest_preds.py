#!/usr/bin/env python3
"""
Self-test for score.py.

Builds a synthetic predictions file from the real dataset with a KNOWN set of
injected errors, then we run score.py against it and check the reported numbers
match what the injection implies. This proves the scorer catches each error class:

  - correct passthrough           (most rows: prediction == ground truth)
  - offset within tolerance       (should still count correct)
  - offset out of tolerance       (should fail offset + exact)
  - offset wrong sign             (should fail offset + exact)
  - wrong reference               (fail reference + exact)
  - wrong axis                    (fail axis + exact)
  - type mismatch                 (fail exact; expected fields all wrong)
  - false-accept (reject -> cmd)  (unsafe)
  - false-reject (cmd -> reject)  (coverage loss)
  - malformed / null prediction   (counted wrong, logged)

Run:  python3 make_selftest_preds.py  &&  python3 score.py --pred selftest_preds.jsonl --system "SELF-TEST"
"""
import json

rows = []
with open("dataset.jsonl") as f:
    for line in f:
        rows.append(json.loads(line))

# index helpers
def find(pred_filter):
    for r in rows:
        if pred_filter(r):
            return r
    return None

preds = []
injected = {
    "offset_out_of_tol": 0,
    "offset_wrong_sign": 0,
    "wrong_reference": 0,
    "wrong_axis": 0,
    "type_mismatch": 0,
    "false_accept": 0,
    "false_reject": 0,
    "malformed": 0,
    "offset_within_tol": 0,
}

# We'll walk rows and mutate a controlled handful; everything else = perfect copy.
used = set()

def take(cat_prefix, gt_pred, n=1):
    """Grab n unused rows whose category starts with cat_prefix."""
    got = []
    for r in rows:
        if r["id"] in used:
            continue
        if r["category"].startswith(cat_prefix) and gt_pred(r):
            got.append(r)
            used.add(r["id"])
            if len(got) == n:
                break
    return got

# 1 offset within tolerance (0.5 mm off) -> should still be correct
for r in take("offset_", lambda r: r["ground_truth"].get("operation") == "offset"):
    gt = dict(r["ground_truth"])
    gt["offset"] = gt["offset"] + 0.0005  # within 1e-3
    preds.append({"id": r["id"], "prediction": gt, "latency_s": 0.10})
    injected["offset_within_tol"] += 1

# 2 offset out of tolerance (5 mm off) -> fail
for r in take("offset_", lambda r: r["ground_truth"].get("operation") == "offset"):
    gt = dict(r["ground_truth"])
    gt["offset"] = gt["offset"] + 0.005
    preds.append({"id": r["id"], "prediction": gt, "latency_s": 0.10})
    injected["offset_out_of_tol"] += 1

# 3 offset wrong sign -> fail
for r in take("offset_", lambda r: r["ground_truth"].get("operation") == "offset"):
    gt = dict(r["ground_truth"])
    gt["offset"] = -gt["offset"]
    preds.append({"id": r["id"], "prediction": gt, "latency_s": 0.10})
    injected["offset_wrong_sign"] += 1

# 4 wrong reference -> fail
for r in take("offset_", lambda r: isinstance(r["ground_truth"].get("reference"), int)):
    gt = dict(r["ground_truth"])
    gt["reference"] = gt["reference"] + 1
    preds.append({"id": r["id"], "prediction": gt, "latency_s": 0.10})
    injected["wrong_reference"] += 1

# 5 wrong axis -> fail
for r in take("offset_", lambda r: r["ground_truth"].get("axis") == "z"):
    gt = dict(r["ground_truth"])
    gt["axis"] = "x"
    preds.append({"id": r["id"], "prediction": gt, "latency_s": 0.10})
    injected["wrong_axis"] += 1

# 6 type mismatch: authoring predicted as navigation -> fail
for r in take("create", lambda r: r["ground_truth"]["type"] == "authoring"):
    preds.append({"id": r["id"],
                  "prediction": {"type": "navigation", "intent": "configure"},
                  "latency_s": 0.10})
    injected["type_mismatch"] += 1

# 7 false accept: reject row predicted as a concrete command -> unsafe
for r in take("reject", lambda r: True):
    preds.append({"id": r["id"],
                  "prediction": {"type": "authoring", "operation": "create",
                                 "reference": None, "axis": None, "offset": None},
                  "latency_s": 0.10})
    injected["false_accept"] += 1

# 8 false reject: in-scope nav predicted as reject -> coverage loss
for r in take("nav_", lambda r: r["ground_truth"]["type"] == "navigation"):
    preds.append({"id": r["id"], "prediction": {"type": "reject"}, "latency_s": 0.10})
    injected["false_reject"] += 1

# 9 malformed / null prediction
for r in take("exec_", lambda r: True):
    preds.append({"id": r["id"], "prediction": None, "latency_s": 0.10})
    injected["malformed"] += 1

# Everything else -> perfect passthrough
for r in rows:
    if r["id"] in used:
        continue
    preds.append({"id": r["id"], "prediction": dict(r["ground_truth"]), "latency_s": 0.10})

with open("selftest_preds.jsonl", "w") as f:
    for p in preds:
        f.write(json.dumps(p) + "\n")

# Compute what exact-match SHOULD be: total minus every injected error row.
n = len(rows)
errors = (injected["offset_out_of_tol"] + injected["offset_wrong_sign"]
          + injected["wrong_reference"] + injected["wrong_axis"]
          + injected["type_mismatch"] + injected["false_accept"]
          + injected["false_reject"] + injected["malformed"])
expected_exact = n - errors  # offset_within_tol rows are still correct

print("Injected errors:")
for k, v in injected.items():
    print(f"  {k:20s} {v}")
print(f"\nTotal rows           : {n}")
print(f"Rows that should fail : {errors}")
print(f"Expected exact-match  : {expected_exact}/{n} = {100*expected_exact/n:.1f}%")
print(f"Expected false-accept : {injected['false_accept']}")
print(f"Expected false-reject : {injected['false_reject']}")
print(f"Expected malformed    : {injected['malformed']}")
print("\nWrote selftest_preds.jsonl")
