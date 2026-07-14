#!/usr/bin/env python3
"""
AURaPath voice-command evaluation — scoring harness.

Reads the labeled dataset (dataset.jsonl) and one backend's predictions,
then reports exact-match accuracy, per-field accuracy, reject false-accept/
false-reject rates, and latency percentiles (mean/median/p95).

Scoring follows SCHEMA_SPEC.md §5:
  - type mismatch  -> exact-match fail AND every expected field counted wrong
  - offset         -> correct if |pred - gt| <= tol (default 1e-3), sign must match
  - reference      -> "last" matches "last"; ints match exactly
  - reject row     -> correct iff prediction type == "reject"
  - malformed/unparseable prediction -> exact-match fail, logged

Prediction file format (JSONL), one row per dataset id:
  {"id": "000_139d27aa", "prediction": {...structured object...}, "latency_s": 0.42}
  - `prediction` may be null or a dict; a malformed/missing prediction counts as wrong.
  - `latency_s` optional (used only for B and D latency tables).

Usage:
  python3 score.py --dataset dataset.jsonl --pred preds_D.jsonl --system "D — Cloud LLM API"
  python3 score.py --dataset dataset.jsonl --pred preds_B.jsonl --latency-only
"""
import argparse
import json
import statistics
from collections import defaultdict

OFFSET_TOL = 1e-3  # 1 mm / ~0.057 deg

# Which fields are "applicable" per ground-truth type (SCHEMA_SPEC §5.2)
def applicable_fields(gt):
    t = gt["type"]
    if t == "authoring":
        fields = ["operation"]
        if gt.get("reference") is not None:
            fields.append("reference")
        if gt.get("operation") == "offset":
            fields += ["axis", "offset"]
        return fields
    if t == "navigation":
        return ["intent"]
    if t == "execution":
        return ["verb"]
    if t == "reject":
        return []
    return []


def field_correct(field, gt, pred):
    """Compare a single field. pred is the predicted object (already type-matched)."""
    g = gt.get(field)
    p = pred.get(field)
    if field == "offset":
        if not isinstance(p, (int, float)):
            return False
        # sign must match and magnitude within tol
        if (g < 0) != (p < 0) and g != 0:
            return False
        return abs(p - g) <= OFFSET_TOL
    if field == "reference":
        # "last" must match "last"; ints exact
        return g == p
    return g == p


def score(dataset_path, pred_path):
    # load
    data = {}
    with open(dataset_path) as f:
        for line in f:
            r = json.loads(line)
            data[r["id"]] = r

    preds = {}
    with open(pred_path) as f:
        for line in f:
            r = json.loads(line)
            preds[r["id"]] = r

    n = len(data)
    exact_correct = 0
    type_correct = 0

    # per-field tallies: field -> [correct, total_applicable]
    field_tally = defaultdict(lambda: [0, 0])

    # reject accounting
    reject_rows = 0
    reject_correct = 0
    false_accept = 0   # gt=reject, pred=concrete
    inscope_rows = 0
    false_reject = 0   # gt=in-scope, pred=reject

    latencies = []
    malformed = 0

    per_category = defaultdict(lambda: [0, 0])  # category -> [exact_correct, total]

    for _id, row in data.items():
        gt = row["ground_truth"]
        cat = row["category"]
        per_category[cat][1] += 1

        pr = preds.get(_id, {})
        pred = pr.get("prediction", None)
        lat = pr.get("latency_s", None)
        if isinstance(lat, (int, float)):
            latencies.append(lat)

        # malformed / missing prediction
        if not isinstance(pred, dict) or "type" not in pred:
            malformed += 1
            # counts as exact-match fail; all applicable fields wrong
            for fld in applicable_fields(gt):
                field_tally[fld][1] += 1
            field_tally["type"][1] += 1
            if gt["type"] == "reject":
                reject_rows += 1
            else:
                inscope_rows += 1
            continue

        # type field
        field_tally["type"][1] += 1
        type_match = (pred["type"] == gt["type"])
        if type_match:
            type_correct += 1
            field_tally["type"][0] += 1

        # reject bookkeeping
        if gt["type"] == "reject":
            reject_rows += 1
            if pred["type"] == "reject":
                reject_correct += 1
        else:
            inscope_rows += 1
            if pred["type"] == "reject":
                false_reject += 1
        if gt["type"] != "reject" and pred["type"] == "reject":
            pass  # already counted as false_reject
        if gt["type"] == "reject" and pred["type"] != "reject":
            false_accept += 1

        # per-field accuracy (only over expected-type fields; §5.1/§5.2)
        fields = applicable_fields(gt)
        all_fields_ok = type_match
        for fld in fields:
            field_tally[fld][1] += 1
            ok = type_match and field_correct(fld, gt, pred)
            if ok:
                field_tally[fld][0] += 1
            else:
                all_fields_ok = False

        # exact match: type + every applicable field correct
        # (reject rows: exact == type correct, since no other fields)
        if gt["type"] == "reject":
            row_exact = (pred["type"] == "reject")
        else:
            row_exact = all_fields_ok
        if row_exact:
            exact_correct += 1
            per_category[cat][0] += 1

    def pct(a, b):
        return (100.0 * a / b) if b else float("nan")

    result = {
        "n": n,
        "exact_match": pct(exact_correct, n),
        "type_acc": pct(type_correct, n),
        "fields": {fld: pct(c, t) for fld, (c, t) in field_tally.items()},
        "field_counts": {fld: (c, t) for fld, (c, t) in field_tally.items()},
        "reject": {
            "rows": reject_rows,
            "acc": pct(reject_correct, reject_rows),
            "false_accept": false_accept,
            "false_accept_rate": pct(false_accept, reject_rows),
        },
        "inscope": {
            "rows": inscope_rows,
            "false_reject": false_reject,
            "false_reject_rate": pct(false_reject, inscope_rows),
        },
        "malformed": malformed,
        "per_category": {c: pct(a, b) for c, (a, b) in sorted(per_category.items())},
        "latency": None,
    }
    if latencies:
        srt = sorted(latencies)
        p95 = srt[min(len(srt) - 1, int(round(0.95 * (len(srt) - 1))))]
        result["latency"] = {
            "n": len(latencies),
            "mean": statistics.mean(latencies),
            "median": statistics.median(latencies),
            "p95": p95,
        }
    return result


def print_report(res, system, latency_only=False):
    print(f"\n===== {system} =====")
    print(f"rows scored: {res['n']}")
    if not latency_only:
        print(f"\nExact-match accuracy : {res['exact_match']:.1f}%")
        print(f"Type accuracy        : {res['type_acc']:.1f}%")
        print("\nPer-field accuracy (over applicable rows):")
        order = ["type", "operation", "reference", "axis", "offset", "intent", "verb"]
        for fld in order:
            if fld in res["fields"]:
                c, t = res["field_counts"][fld]
                print(f"  {fld:10s} {res['fields'][fld]:6.1f}%   ({c}/{t})")
        rj = res["reject"]
        isc = res["inscope"]
        print("\nReject / safety:")
        print(f"  reject accuracy        : {rj['acc']:.1f}%  ({rj['rows']} rows)")
        print(f"  false-accepts (unsafe) : {rj['false_accept']}  ({rj['false_accept_rate']:.1f}% of reject rows)")
        print(f"  false-rejects (coverage): {isc['false_reject']}  ({isc['false_reject_rate']:.1f}% of in-scope rows)")
        print(f"  malformed outputs      : {res['malformed']}")
    if res["latency"]:
        L = res["latency"]
        print("\nLatency (s):")
        print(f"  mean {L['mean']:.3f}   median {L['median']:.3f}   p95 {L['p95']:.3f}   (n={L['n']})")
    print()


def latex_rows(res, system):
    """Emit Table 1 (accuracy) and Table 2 (latency) LaTeX rows for this backend.
    Column order matches the skeleton: Exact, Operation, Reference, Offset, Axis."""
    def c(key):
        v = res["fields"].get(key)
        return "--" if v is None else f"{v:.1f}"
    exact = f"{res['exact_match']:.1f}"
    acc = (f"{system} & {exact} & {c('operation')} & {c('reference')} "
           f"& {c('offset')} & {c('axis')} \\\\")
    lat = None
    if res["latency"]:
        L = res["latency"]
        lat = f"{system} & {L['mean']:.2f} & {L['median']:.2f} & {L['p95']:.2f} \\\\"
    return acc, lat


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset.jsonl")
    ap.add_argument("--pred", required=True)
    ap.add_argument("--system", default="(unnamed system)")
    ap.add_argument("--latency-only", action="store_true")
    ap.add_argument("--latex", action="store_true", help="print LaTeX table rows")
    ap.add_argument("--by-category", action="store_true", help="print per-category exact match")
    ap.add_argument("--json-out", default=None, help="write full result dict to this path")
    args = ap.parse_args()

    res = score(args.dataset, args.pred)
    print_report(res, args.system, latency_only=args.latency_only)

    if args.by_category:
        print("Per-category exact match:")
        for cat, v in res["per_category"].items():
            print(f"  {cat:24s} {v:6.1f}%")
        print()

    if args.latex:
        acc, lat = latex_rows(res, args.system)
        print("LaTeX — Table 1 (accuracy) row:")
        print("  " + acc)
        if lat:
            print("LaTeX — Table 2 (latency) row:")
            print("  " + lat)
        print()

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump({"system": args.system, **res}, f, indent=2)
        print(f"(full result written to {args.json_out})")
