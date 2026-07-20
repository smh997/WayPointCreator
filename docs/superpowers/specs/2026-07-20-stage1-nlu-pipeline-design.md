# Stage 1: NLU Pipeline Integration — Design

## Purpose

Prove the free-form voice-command pipeline works end to end inside Unity, on
this development laptop, without a UR10 robot attached. This is **not** a
mapping-accuracy exercise — `eval/backend_b_ollama.py` already scored 88.8%
on 169 labeled utterances, and that result is not re-litigated here. The
unverified surface is entirely on the Unity side:

1. `WaypointManager` has no `offset` operation at all.
2. The UR10-base-frame → Unity-world-frame conversion has only ever been
   built in one direction (Unity → UR, for sending waypoints to the robot).
   The inverse (UR offset → Unity delta) is new and unverified, and the
   codebase has direct evidence of getting this sign convention wrong before
   (a dead, commented-out conversion in `OperationsManager.cs` disagrees with
   the live one on sign).
3. `VoiceCommandRouter` has never dispatched all four schema command types
   (`authoring`, `navigation`, `execution`, `reject`) — only a fixed keyword
   vocabulary for `navigation`/`execution`.

HoloLens dictation is explicitly **out of scope** (Stage 2). Stage 1 uses a
debug text input inside the Unity Editor instead.

## Architecture

### Standalone NLU server (`Server/nlu_server.py`)

A new, separate Python process — **not** a modification to `Server/server.py`.

`Server/server.py`'s connection handler calls `robot = UR.control(robot_ip)`
unconditionally on every accepted connection, before reading any message.
Any in-process addition would block or throw immediately without a live
UR10, making Stage 1 untestable on this laptop. A separate process:

- Needs no robot at all.
- Cannot regress the robot-critical path — zero lines of `server.py` change.
- Can be started/stopped independently while iterating.

It mirrors `server.py`'s conventions: single-threaded synchronous
accept-loop, newline-delimited JSON, a `"type"` field on each request. New
port: **5001** (vs. `server.py`'s 5000), same host.

It imports `get_prompt`, `call_ollama`, `normalize` directly from
`eval/backend_b_ollama.py` (via `sys.path.insert(0, "<repo>/eval")`) — no
reimplementation, so Stage 1 runs the exact prompt that scored 88.8%.

### Model configuration

`NLU_MODEL` env var, default `"qwen2.5:3b"` (fits this laptop's 4GB VRAM
GTX 1050 Ti; `qwen3:8b` spills to CPU here and is impractical for
iteration — 69s/call measured). Read once at server startup, passed to
`call_ollama(model=...)`. Switching models (e.g. to `qwen3:8b` on the lab
machine) is an env var change, no code edit.

Explicitly **not** building a pluggable multi-backend abstraction (Ollama
vs. Groq vs. Gemini) in Stage 1 — that's real work for whichever stage first
needs a cloud backend live. The model-call is isolated to one function so
that swap stays contained later.

## Wire protocol

Request: `{"type":"nlu","utterance":"<text>"}\n`

Success: `{"success":true,"command":{...}}\n`
Failure: `{"success":false,"message":"<error>"}\n`

**The `command` object's fields and semantics are exactly the schema scored
in evaluation (`COMMAND_SCHEMA` in `backend_b_ollama.py`) — nothing about
the schema itself changes.** The only transform applied at the socket
boundary is serialization: `reference` (int / `"last"` / `null` in the
schema) is always encoded on the wire as a JSON string or `null` — e.g.
`"reference": "2"`, `"reference": "last"`, `"reference": null` — never a
bare number. This exists purely because Unity's built-in `JsonUtility`
cannot deserialize a polymorphic field (no Newtonsoft.Json in this project;
confirmed via `Packages/manifest.json`). It is a wire-encoding detail, not a
schema change — the server-side `command` object before serialization is
byte-for-byte what evaluation would have produced.

## Unity: debug input (`NluDebugInput.cs`)

Editor/development-build only (never ships to the HoloLens release build).
Self-bootstraps via `RuntimeInitializeOnLoadMethod` — spawns its own
GameObject at Play-mode start, no manual Canvas/prefab/Inspector wiring.
Finds `VoiceCommandRouter` via `FindObjectOfType` at runtime.

- `OnGUI` immediate-mode text field + Send button for arbitrary utterances.
- Number-key hotkeys (1–5) firing canned utterances covering all four
  command types plus one reject case, for fast one-key smoke testing.
- Sends over a fresh `TcpClient` to `127.0.0.1:5001` per call, using the
  same blocking-coroutine `TcpClient` pattern already used in
  `OperationsManager` (no new async pattern introduced).
- Wraps the connect/send in try/catch (matching the existing
  `SocketException` handling pattern in `OperationsManager`/`TestClient`)
  and, on failure, shows **"NLU server not reachable on 127.0.0.1:5001"**
  in the `OnGUI` status area — not just a `Debug.LogError`. The whole point
  of this debug tool is fast iteration; a raw unhandled socket exception in
  the Console reads as "I broke something" when the actual cause is just
  "forgot to start `nlu_server.py`."

## Unity: dispatch (`VoiceCommandRouter.DispatchStructuredCommand`)

New public method on `VoiceCommandRouter` (not a separate dispatcher class —
it already holds every reference the dispatch needs, and stays the single
entry point for voice per its existing header comment).

- `type: "navigation"` / `"execution"` → map the schema string to the
  existing `VoiceIntent` enum, call the existing `Dispatch()` unchanged.
  **`navigation.intent = "run"` and `execution.verb = "run"` are different
  actions and must not be conflated**: `navigation.intent = "run"` means
  "go to the preview/run screen" (→ `VoiceIntent.PreviewRun`);
  `execution.verb = "run"` means "arm the safety-critical run gate"
  (→ `VoiceIntent.Run`). The mapping code will have an explicit comment
  calling this out, so a future edit matching naively on the string `"run"`
  doesn't collapse the two.
- `type: "authoring", operation: "create"` → `SetMode(WaypointMode.Create,
  "Create mode. Pinch to place a waypoint.")`, reusing the existing private
  `SetMode` helper. Voice cannot supply a 3D point, so arming the gesture
  (rather than inventing a position) is the honest behavior — same
  reject-don't-guess principle the schema itself uses.
- `operation: "delete_all"` → `Waypoints.DeleteAllWaypoints()`.
- `operation: "delete"` → resolve `reference` via
  `WaypointManager.TryGetWaypointByReference`, which distinguishes *why* it
  failed (see below): `Missing` → `Say("Which waypoint? Say delete last, or
  a waypoint number.")`; `OutOfRange` → `Say("There's no waypoint
  {n}.")` (or `"There are no waypoints."` if `reference == "last"` on an
  empty list). Resolved → `Waypoints.RemoveWaypoint(wp)` directly, **without
  switching to Delete mode first** (see mode-gating note below). Never
  guesses a target either way.
- `operation: "offset"` → resolve `reference` the same way, same
  Missing/OutOfRange distinction, then on resolution call
  `WaypointManager.TryApplyOffset`.
- `type: "reject"` → `Say("Sorry, I didn't understand that command.")`,
  no-op.

**Mode-gating decision for voice delete:** `WaypointManager.RemoveWaypoint`
has no internal mode check — the existing `Mode == WaypointMode.Delete`
guard lives only at its two current call sites (`Waypoint.cs`,
`WaypointInteractable.cs`), not inside the method itself. Voice `delete`
calls `RemoveWaypoint` directly, bypassing the mode gate and leaving `Mode`
unchanged. This is deliberate, not a bypass we should later "fix": unlike
`create`, a voice `delete <reference>` fully specifies its target already,
so there's no missing-information reason to force a mode switch (and doing
so would trigger the Delete-mode waypoint recoloring as an unwanted side
effect of a voice command that isn't itself entering that mode).

## `WaypointManager` additions

- `TryGetWaypointByReference(string reference, out Waypoint wp)` — handles
  `"last"` and 1-indexed integers (matches the existing `SetOrder(i+1)`
  convention). Returns an enum result, not a plain bool, because the
  dispatcher needs to distinguish two different failure modes and respond
  differently to each (the evaluation dataset treats out-of-range
  references as a distinct, documented reject case, and `MAX_WAYPOINTS = 5`
  means "waypoint six" is *always* invalid, not just currently invalid):
  - `Resolved` — reference parsed and points at an existing waypoint.
  - `Missing` — `reference` was null/empty (no target given at all).
  - `OutOfRange` — `reference` parsed fine but doesn't point at anything
    (index beyond the current count, or `"last"` with zero waypoints).

  Callers must branch on all three explicitly rather than collapsing to a
  single "unresolved" case.
- `TryApplyOffset(Waypoint wp, string axis, float value, Transform
  robotBase)` — inverts the **canonical** Unity→UR conversion, i.e. the one
  in `CalculateWaypointsData()` (the function actually used for live
  Preview/Run traffic — confirmed as the live path; a second,
  commented-out/dead conversion earlier in `OperationsManager.cs` uses
  different signs and is disregarded). Canonical forward mapping:
  `UR.x = Unity.z`, `UR.y = -Unity.x`, `UR.z = Unity.y` (robot-base-local).
  Inverse for a single-axis offset:
  - axis `x`, offset `d` → local Unity `z += d` (should move **forward**,
    away from the robot base)
  - axis `y`, offset `d` → local Unity `x += -d` (should move to the
    **operator's left**)
  - axis `z`, offset `d` → local Unity `y += d` (should move **up**)
  - axis `rx`/`ry`/`rz` → **returns a distinct "not yet supported" result.**
    Composing an axis-angle offset in UR frame back onto the waypoint's
    quaternion is materially more complex than translation, and is deferred
    past Stage 1. The dispatcher surfaces this honestly ("rotation offsets
    aren't wired up yet") rather than silently no-op'ing or misapplying.
    **Tracked follow-up, required before the demo video** — not Stage 1,
    but not indefinitely deferred either.

## Verification plan

1. Start `nlu_server.py` standalone — confirm it runs with no robot and no
   `Server/server.py` involved at all. **This must happen before entering
   Unity Play mode** — the debug input has no auto-launch/retry of the
   server, so testing order matters. Also deliberately test the inverse:
   enter Play mode *without* starting the server first, send a command, and
   confirm the "NLU server not reachable" message appears in the debug
   input's status area rather than an unhandled exception.
2. A handful (3–4) of raw utterances via a quick script, confirming the wire
   round-trip and the `reference`-as-string encoding. This is a protocol
   sanity check, not a re-run of evaluation.
3. In Unity Play mode, via the debug input:
   - **All three translation axes, with signs** — not just `z`. Confirm
     visually in the Scene view: `+x` → forward (away from robot base),
     `+y` → operator's left, `+z` → up. This is the one place the codebase
     has already been wrong before (the dead conversion's differing signs),
     so all three get checked individually, not just the one the schema
     example happened to use.
   - `delete <ref>` on a valid reference, `delete_all`.
   - `delete` with an out-of-range reference (e.g. "delete waypoint six"
     with fewer than six present) → confirm the `"There's no waypoint
     six."`-style message appears, distinct from the `Missing`-reference
     message, and nothing is deleted.
   - `create` → mode switches, "Create mode, pinch to place" message
     appears, then manual pinch-place still works afterward.
   - **`MAX_WAYPOINTS = 5` interaction**: offsetting an existing waypoint
     must not trip the create-path gating (`AddWaypoint`'s mode/count
     checks) since offset mutates an existing waypoint's transform rather
     than creating a new one. Also check `delete_all` followed by a voice
     `create` behaves sanely (mode switches cleanly, count resets, no stale
     state from the deleted waypoints).
   - One `navigation` command, one `execution` command, one `reject`.
   - Unity Console watched for exceptions throughout all of the above.

## Explicitly deferred (not Stage 1)

- HoloLens dictation (Stage 2).
- Rotation-axis (`rx`/`ry`/`rz`) offsets — required before the demo video,
  tracked as follow-up work, not silently dropped.
- Multi-backend (cloud) NLU abstraction.
