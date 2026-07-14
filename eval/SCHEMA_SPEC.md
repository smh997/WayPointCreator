# AURaPath Voice-Command Evaluation — Schema & Dataset Specification

**Version 1.0** · Companion artifact to the MDPI Applied Sciences journal extension of AURaPath (CCECE 2026).

This document defines the structured-output schema, the frame/unit conventions, the dataset composition, and the scoring rules. It is the single source of truth for the evaluation harness and the corresponding paper section.

---

## 1. Scope of the metric

The evaluation isolates **language-to-command mapping**: transcript in, structured command out. Speech recognition (ASR) and physical robot execution are deliberately excluded, so the score reflects only how well each backend maps natural language to the correct structured command. This keeps the ground truth objective and unambiguous.

Three backends are scored on the identical labeled set:

| ID | Backend | Runs on | Cost |
|----|---------|---------|------|
| A  | Keyword baseline (fixed vocabulary, no LLM) | HoloLens (on-device) | none |
| B  | Local LLM (small instruction-tuned model via Ollama) | RTX 5060, Toronto | none (local) |
| D  | Cloud LLM API (Gemini Flash, free tier) | cloud | free tier |

---

## 2. Structured-output schema

Every command maps to exactly one JSON object, discriminated by `type`. Four types:

### 2.1 `authoring`
Targets the 6-DoF waypoint representation `{x, y, z, rx, ry, rz}` from the conference paper (Eq. 1).

```json
{
  "type": "authoring",
  "operation": "create | delete | offset | delete_all",
  "reference": <int> | "last" | null,
  "axis": "x | y | z | rx | ry | rz" | null,
  "offset": <float> | null
}
```

- `reference` — target waypoint. Integer id (1-indexed, as spoken), the literal string `"last"`, or `null` when the operation needs no target (`create`, `delete_all`).
- `axis` / `offset` — populated only for `operation: "offset"`; `null` otherwise.

### 2.2 `navigation`
Mode/menu transitions.

```json
{ "type": "navigation", "intent": "configure | trajectory | preview | run | exit | create_mode | edit_mode | delete_mode" }
```

### 2.3 `execution`
Safety-gated verbs. At runtime these are handled by the **deterministic on-device keyword layer**, never by the LLM. They appear in the dataset so we can score whether the LLM **correctly recognizes and routes them to `type: execution`** (i.e., defers rather than inventing an authoring/nav action).

```json
{ "type": "execution", "verb": "run | confirm | cancel | stop" }
```

### 2.4 `reject`
Out-of-scope, unsupported, or under-specified/ambiguous utterances the LLM layer should refuse rather than guess. Type-only.

```json
{ "type": "reject" }
```

### 2.5 Confidence
For `navigation` and `execution`, the model **reports** a `confidence ∈ [0,1]`. It is **not a labeled target** and is **not scored for correctness**. It is retained only for the confidence-calibration analysis (accuracy vs. reported confidence). Ground-truth rows therefore contain no confidence field.

---

## 3. Frame and unit conventions

### 3.1 Offset frame — UR10 base
Offsets are authored in the **UR10 base frame**, not the Unity scene frame. Rationale: waypoints are ultimately UR10-base 6-DoF poses, and the user reasons about the physical robot in the room, which sidesteps Unity's left-handed handedness (the internal Unity→UR remap `(xu, yu, zu) → (zu, −xu, yu)` is an implementation detail below this layer).

| Spoken direction | UR10 base axis | Sign |
|------------------|----------------|------|
| up / raise / higher / lift | z | + |
| down / lower / drop | z | − |
| forward / away (from base) | x | + |
| back / toward me | x | − |
| left | y | + |
| right | y | − |

**Well-definedness and scope.** All six directions are defined in the **UR10 base frame**: `+z = up`, `+x = forward`, `+y = left` (with negatives for down/back/right). *Up/down* (±z) is frame-independent and unambiguous, and is the primary, most heavily sampled offset axis. *Forward/back* (±x) and *left/right* (±y) are fixed to this base-frame convention, which the operator uses regardless of where they stand around the workspace. Resolving these directions relative to the operator's egocentric stance is **deliberately out of scope for this study**: the research questions target LLM language-to-command mapping accuracy and latency, not frame disambiguation. The operator is expected to use the fixed base-frame convention; egocentric direction resolution is noted as a boundary of the current design (paper §7.1) rather than a research contribution. Horizontal commands are included in the dataset but sampled more lightly than up/down.

### 3.2 Units — SI base
Ground-truth `offset` values are stored in SI base units: **meters** for translational axes (x/y/z), **radians** for rotational axes (rx/ry/rz). Spoken units are normalized: `5 cm → 0.05`, `10° → 0.174533`. Scoring compares canonical floats with a small numeric tolerance (§5).

### 3.3 Offset magnitudes
Varied across the dataset (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15 cm; 5–30°) to genuinely exercise numeric parsing rather than letting a backend memorize a single constant.

---

## 4. Dataset composition

169 utterances. Each in-scope command is phrased several natural ways; each row has exactly one unambiguous ground-truth object.

| Type | Rows | Notes |
|------|------|-------|
| authoring | 61 | offset (up/down/fwd/back/left/right/rot), create, delete, delete_all |
| navigation | 51 | 8 intents |
| execution | 28 | 4 deferred safety verbs |
| reject | 29 | out-of-domain, unsupported ops/params, under-specified/ambiguous |

The **reject** bucket (≈17%) is deliberately substantial: it demonstrates the LLM layer is a *constrained mapper*, not an open-ended planner, and that it fails safe on ambiguous or unsupported input. Reject sub-reasons (recorded in `notes`) include: missing reference/axis/amount, vacuous/deictic phrasing, out-of-domain Q&A, unsupported operations (pick/weld/undo/home/calibrate), unsupported parameters (speed/force), and out-of-range references.

A **phrasing-stress** slice (polite, hedged, colloquial wordings — "scoot the last one down four centimeters please") is mixed in to test robustness beyond canonical templates; this directly supports RQ3 (natural-language vs. fixed-keyword baseline).

---

## 5. Scoring rules

For each row, each backend produces one predicted object. Metrics:

### 5.1 Exact-match accuracy
All applicable fields correct. A **type mismatch is an automatic exact-match failure**, and additionally every field of the *expected* type is counted incorrect in per-field accuracy (so a wrong-type prediction cannot silently inflate per-field numbers).

### 5.2 Per-field accuracy
Computed per field over rows where that field applies in ground truth:
- **operation** (authoring rows)
- **reference** (authoring rows where reference ≠ null) — `"last"` must match `"last"`; integers must match exactly
- **axis** (offset rows)
- **offset** (offset rows) — correct if `|pred − gt| ≤ tol`. Default `tol = 1e-3` (1 mm / ~0.057°). Sign must match.
- **intent** (navigation rows)
- **verb** (execution rows)
- **type** (all rows)

### 5.3 Reject handling
A `reject` row is correct iff the prediction is `type: reject`. Predicting a concrete command on a reject row is a false-accept (safety-relevant; report separately). Predicting reject on an in-scope row is a false-reject (coverage loss).

### 5.4 Latency
Per mapping call, for B and D: mean, median, p95. Measured end-to-end for the mapping call under deterministic decoding (temperature 0 where supported), with a fixed number of repeats per item. Malformed/unparseable output is counted as an exact-match failure and logged.

### 5.5 Confidence calibration
For navigation/execution predictions, bin by reported confidence and plot empirical accuracy per bin (reliability curve). Not part of accuracy scoring.

---

## 6. Dataset row format (JSONL)

```json
{
  "id": "000_ab12cd34",
  "utterance": "raise waypoint two by five centimeters",
  "ground_truth": {"type": "authoring", "operation": "offset", "reference": 2, "axis": "z", "offset": 0.05},
  "category": "offset_up",
  "notes": ""
}
```

- `id` — stable index + short content hash.
- `category` — fine-grained bucket (for stratified error analysis).
- `notes` — reject sub-reason or provenance annotation.

---

## 7. Reproducibility

- The dataset is generated deterministically by `build_dataset.py` (no randomness); re-running reproduces byte-identical output.
- Unit conversions (cm→m, deg→rad) are applied in the generator so labels are always canonical SI.
- Schema integrity assertions run at build time (every row's field set matches its type).
