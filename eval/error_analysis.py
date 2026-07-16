#!/usr/bin/env python3
"""Throwaway error dump: prints every row where prediction != ground truth,
grouped by category. Row-wrong definition mirrors score.py exactly (type +
applicable fields, offset tolerance, reject handling).
"""
import argparse
import json
from collections import defaultdict

from score import applicable_fields, field_correct


def row_is_wrong(gt, pred):
    if not isinstance(pred, dict) or "type" not in pred:
        return True
    if gt["type"] == "reject":
        return pred["type"] != "reject"
    if pred["type"] != gt["type"]:
        return True
    for fld in applicable_fields(gt):
        if not field_correct(fld, gt, pred):
            return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset.jsonl")
    ap.add_argument("--pred", required=True)
    args = ap.parse_args()

    data = {}
    with open(args.dataset) as f:
        for line in f:
            r = json.loads(line)
            data[r["id"]] = r

    preds = {}
    with open(args.pred) as f:
        for line in f:
            r = json.loads(line)
            preds[r["id"]] = r

    by_category = defaultdict(list)
    for _id, row in data.items():
        gt = row["ground_truth"]
        pr = preds.get(_id, {})
        pred = pr.get("prediction", None)
        if row_is_wrong(gt, pred):
            by_category[row["category"]].append((row, pred))

    total_wrong = sum(len(v) for v in by_category.values())
    print(f"{total_wrong} mismatched rows out of {len(data)}\n")

    for cat in sorted(by_category):
        rows = by_category[cat]
        print(f"=== {cat} ({len(rows)} errors) ===")
        for row, pred in rows:
            print(f"  id: {row['id']}")
            print(f"  utterance: {row['utterance']}")
            print(f"  ground_truth: {json.dumps(row['ground_truth'])}")
            print(f"  prediction:   {json.dumps(pred)}")
            print()


if __name__ == "__main__":
    main()
