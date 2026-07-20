# Stage 1 NLU Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the evaluated Ollama NLU pipeline (`eval/backend_b_ollama.py`) into Unity end-to-end — a standalone NLU server, a `WaypointManager.offset` operation with a verified UR↔Unity frame conversion, and full four-command-type dispatch through `VoiceCommandRouter` — driven by an Editor-only debug text input, with no robot hardware and no HoloLens dictation required.

**Architecture:** A new standalone Python socket server (`Server/nlu_server.py`, port 5001) wraps `backend_b_ollama.py`'s already-scored prompt and imports, independent of the robot-dependent `Server/server.py`. Unity gets a self-bootstrapping debug input component that talks to it, new `WaypointManager` methods for reference resolution and frame-converted offsets, and a new `VoiceCommandRouter.DispatchStructuredCommand` that routes all four schema types into real (mostly pre-existing) methods.

**Tech Stack:** Python 3.14 (stdlib only — `socket`, `json`, `urllib`), pytest 9.0.3 for the server; C# / Unity 2022.3.62f3, `JsonUtility` (no Newtonsoft.Json in this project).

## Global Constraints

- NLU server: separate process from `Server/server.py`, host `0.0.0.0`, port **5001** (robot server stays on 5000).
- Model config: env var `NLU_MODEL`, default `"qwen2.5:3b"`.
- Wire protocol: request `{"type":"nlu","utterance":"<text>"}\n`; response `{"success":true,"command":{...}}\n` or `{"success":false,"message":"<error>"}\n`.
- Wire-encoding rules (serialization only — the `command` object's semantics before encoding are exactly `COMMAND_SCHEMA` from `backend_b_ollama.py`, unchanged): `reference` → always a JSON string or `null`, never a bare number. `offset` and `confidence` → default to `0.0` when the schema value is `null`/absent. This exists solely because `JsonUtility` cannot deserialize a polymorphic or null-for-value-type field (confirmed: no Newtonsoft.Json in `Packages/manifest.json`).
- Canonical Unity↔UR frame conversion (from the live path, `OperationsManager.CalculateWaypointsData`): `UR.x = Unity.z`, `UR.y = -Unity.x`, `UR.z = Unity.y` (robot-base-local). A second, dead/commented conversion earlier in `OperationsManager.cs` uses different signs and must not be used.
- Offset inverse (UR-frame axis+value → Unity-local delta): axis `x` → `Unity.z += d` (forward, away from robot base); axis `y` → `Unity.x += -d` (operator's left); axis `z` → `Unity.y += d` (up). Axes `rx`/`ry`/`rz` are **not implemented** — must return a distinct "unsupported" result, never silently no-op or misapply. Tracked as required before the demo video, not Stage 1.
- `MAX_WAYPOINTS = 5` (existing constant in `WaypointManager.cs`) — offset must not trip `AddWaypoint`'s create-path gating.
- Voice `delete` bypasses the `WaypointMode.Delete` gate deliberately (`WaypointManager.RemoveWaypoint` has no internal mode check today) and does not change `Mode` as a side effect.
- `navigation.intent = "run"` → `VoiceIntent.PreviewRun` (go to preview/run screen). `execution.verb = "run"` → `VoiceIntent.Run` (arm the safety-critical run gate). These must never be conflated — mapping code carries an explicit comment saying so.
- `create` operation → `SetMode(WaypointMode.Create, "Create mode. Pinch to place a waypoint.")`. Never invents a position.
- Reference resolution has three outcomes, not two: `Resolved`, `Missing` (no reference given → `"Which waypoint? Say delete last, or a waypoint number."`), `OutOfRange` (parses but doesn't exist → `"There's no waypoint {n}."`, or `"There are no waypoints."` for `"last"` on an empty list).
- `reject` → `Say("Sorry, I didn't understand that command.")`, no-op.
- `NluDebugInput` is Editor/development-build only (`#if UNITY_EDITOR || DEVELOPMENT_BUILD`), self-bootstraps via `RuntimeInitializeOnLoadMethod` (no manual scene/prefab wiring), targets `127.0.0.1:5001`, and shows `"NLU server not reachable on 127.0.0.1:5001"` in its own status label (not just `Debug.LogError`) on connection failure.
- **Testing approach note:** this Unity project has no assembly definition files under `Assets/` (all scripts compile into the implicit `Assembly-CSharp`). Introducing Unity Test Framework EditMode tests would require restructuring `Assets/Scripts` into its own `.asmdef` so a test assembly can reference it — a real, project-wide risk (MRTK/reflection-based systems, third-party plugins) far outside Stage 1's scope. Instead: the Python server gets full pytest TDD (Tasks 1–3), and every C# task is verified by a Unity batchmode compile check (Tasks 5–8, catches type/signature errors immediately) plus the manual Play-mode verification pass in Task 9, which is where the frame-conversion signs and dispatch behavior are actually exercised.
- **Batchmode/Editor collision:** Unity holds a project lock file (`Temp/UnityLockfile`) while open, and a second `-batchmode` invocation against the same `-projectPath` will fail immediately (not a compile error — a lock/instance conflict) if the Editor GUI is already open on this project. Since the Editor was opened manually earlier this session, **close it before running any batchmode compile-check step**, and reopen it (or just re-enter Play mode) for Task 9's manual verification. If a compile-check step errors out immediately rather than producing normal Unity startup log lines, this is the first thing to check.

---

### Task 1: NLU server — wire-shaping of the command object

**Files:**
- Create: `Server/nlu_server.py`
- Create: `Server/tests/conftest.py`
- Create: `Server/tests/test_nlu_server.py`

**Interfaces:**
- Produces: `shape_command_for_wire(cmd: dict | None) -> dict | None` in `nlu_server.py`, used by Task 2's request handler.

- [ ] **Step 1: Create the tests directory and conftest**

`Server/tests/conftest.py`:
```python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
```

- [ ] **Step 2: Write the failing tests**

`Server/tests/test_nlu_server.py`:
```python
from nlu_server import shape_command_for_wire


def test_none_passthrough():
    assert shape_command_for_wire(None) is None


def test_reference_int_becomes_string():
    cmd = {"type": "authoring", "operation": "offset", "reference": 2,
           "axis": "z", "offset": 0.05}
    out = shape_command_for_wire(cmd)
    assert out["reference"] == "2"
    assert isinstance(out["reference"], str)


def test_reference_last_stays_string():
    cmd = {"type": "authoring", "operation": "delete", "reference": "last"}
    out = shape_command_for_wire(cmd)
    assert out["reference"] == "last"


def test_reference_none_stays_none():
    cmd = {"type": "authoring", "operation": "create", "reference": None}
    out = shape_command_for_wire(cmd)
    assert out["reference"] is None


def test_reference_absent_becomes_none():
    cmd = {"type": "authoring", "operation": "delete_all"}
    out = shape_command_for_wire(cmd)
    assert out["reference"] is None


def test_offset_none_defaults_to_zero():
    cmd = {"type": "authoring", "operation": "create", "reference": None,
           "offset": None}
    out = shape_command_for_wire(cmd)
    assert out["offset"] == 0.0


def test_offset_absent_defaults_to_zero():
    cmd = {"type": "navigation", "intent": "configure"}
    out = shape_command_for_wire(cmd)
    assert out["offset"] == 0.0


def test_offset_value_passthrough():
    cmd = {"type": "authoring", "operation": "offset", "reference": 1,
           "axis": "x", "offset": -0.02}
    out = shape_command_for_wire(cmd)
    assert out["offset"] == -0.02


def test_confidence_none_defaults_to_zero():
    cmd = {"type": "navigation", "intent": "exit", "confidence": None}
    out = shape_command_for_wire(cmd)
    assert out["confidence"] == 0.0


def test_confidence_value_passthrough():
    cmd = {"type": "execution", "verb": "run", "confidence": 0.92}
    out = shape_command_for_wire(cmd)
    assert out["confidence"] == 0.92


def test_other_fields_pass_through_unchanged():
    cmd = {"type": "authoring", "operation": "offset", "reference": 3,
           "axis": "y", "offset": 0.1}
    out = shape_command_for_wire(cmd)
    assert out["type"] == "authoring"
    assert out["operation"] == "offset"
    assert out["axis"] == "y"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `py -m pytest Server/tests/test_nlu_server.py -v` (from repo root `D:\GitHub\WayPointCreator`)
Expected: FAIL/ERROR — `ModuleNotFoundError: No module named 'nlu_server'` (file doesn't exist yet).

- [ ] **Step 4: Create `nlu_server.py` with the wire-shaping function**

`Server/nlu_server.py`:
```python
#!/usr/bin/env python3
"""
AURaPath Stage 1 — standalone NLU server.

Wraps eval/backend_b_ollama.py's already-evaluated prompt (88.8% on 169
labeled utterances) behind a small socket server, independent of
Server/server.py (which requires a live UR10 connection per accepted
connection and would make Stage 1 untestable without robot hardware).

Wire protocol (newline-delimited JSON, one request/response per connection):
  request:  {"type":"nlu","utterance":"<text>"}
  response: {"success":true,"command":{...}}
        or: {"success":false,"message":"<error>"}

The `command` object's fields and semantics are exactly COMMAND_SCHEMA from
backend_b_ollama.py -- nothing about the schema changes here. The only
transform is wire encoding: `reference` is always a JSON string or null
(never a bare number), and `offset`/`confidence` default to 0.0 when null,
because Unity's JsonUtility cannot deserialize a polymorphic field or a
null value for a C# value type (no Newtonsoft.Json in this project).
"""
import json
import os
import socket
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "eval"))
from backend_b_ollama import call_ollama, normalize  # noqa: E402

MODEL = os.environ.get("NLU_MODEL", "qwen2.5:3b")


def shape_command_for_wire(cmd):
    """Re-encode a normalize()'d command dict for JsonUtility compatibility.
    See module docstring -- this does not change schema semantics."""
    if cmd is None:
        return None
    out = dict(cmd)
    ref = out.get("reference")
    out["reference"] = str(ref) if ref is not None else None
    out["offset"] = out.get("offset") if out.get("offset") is not None else 0.0
    out["confidence"] = out.get("confidence") if out.get("confidence") is not None else 0.0
    return out


if __name__ == "__main__":
    pass  # server wiring added in Task 3
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -m pytest Server/tests/test_nlu_server.py -v`
Expected: PASS — 11 passed.

- [ ] **Step 6: Commit**

```bash
git add Server/nlu_server.py Server/tests/conftest.py Server/tests/test_nlu_server.py
git commit -m "Add NLU server wire-shaping for JsonUtility-safe command encoding"
```

---

### Task 2: NLU server — request handler

**Files:**
- Modify: `Server/nlu_server.py`
- Modify: `Server/tests/test_nlu_server.py`

**Interfaces:**
- Consumes: `shape_command_for_wire` (Task 1); `call_ollama(model, utterance, timeout=120, few_shot=False, json_mode=False) -> (dict|None, float, str)` and `normalize(dict|None) -> dict|None` from `eval/backend_b_ollama.py`.
- Produces: `handle_nlu_request(msg_obj: dict, model: str) -> dict` in `nlu_server.py`, used by Task 3's socket wiring.

- [ ] **Step 1: Write the failing tests**

Append to `Server/tests/test_nlu_server.py`:
```python
from unittest.mock import patch

import nlu_server
from nlu_server import handle_nlu_request


def test_missing_utterance_returns_failure():
    result = handle_nlu_request({}, "qwen2.5:3b")
    assert result["success"] is False
    assert "utterance" in result["message"]


def test_successful_command_round_trip():
    fake_obj = {"type": "authoring", "operation": "offset", "reference": 2,
                "axis": "z", "offset": 0.05}
    with patch.object(nlu_server, "call_ollama",
                       return_value=(fake_obj, 0.1, '{"type":"authoring",...}')):
        result = handle_nlu_request({"utterance": "move waypoint two up 5cm"},
                                     "qwen2.5:3b")
    assert result["success"] is True
    assert result["command"]["type"] == "authoring"
    assert result["command"]["reference"] == "2"  # wire-shaped, not int 2


def test_malformed_model_output_returns_failure():
    with patch.object(nlu_server, "call_ollama",
                       return_value=(None, 0.1, "not json")):
        result = handle_nlu_request({"utterance": "gibberish"}, "qwen2.5:3b")
    assert result["success"] is False
    assert "message" in result


def test_model_output_missing_type_field_returns_failure():
    with patch.object(nlu_server, "call_ollama",
                       return_value=({"operation": "create"}, 0.1, "{}")):
        result = handle_nlu_request({"utterance": "add one"}, "qwen2.5:3b")
    assert result["success"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest Server/tests/test_nlu_server.py -v -k handle_nlu_request or successful_command or malformed_model or missing_type or missing_utterance`
Expected: FAIL — `ImportError: cannot import name 'handle_nlu_request' from 'nlu_server'`.

- [ ] **Step 3: Implement `handle_nlu_request`**

In `Server/nlu_server.py`, insert after `shape_command_for_wire` and before the `if __name__ == "__main__":` block:
```python
def handle_nlu_request(msg_obj, model):
    """msg_obj: the parsed request dict (must have 'utterance'). Returns a
    response dict ready for json.dumps -- never raises for model/parse
    failures, only for programmer errors."""
    utterance = msg_obj.get("utterance", "")
    if not utterance:
        return {"success": False, "message": "Missing 'utterance'."}

    obj, _dt, raw = call_ollama(model, utterance)
    obj = normalize(obj)
    if obj is None or "type" not in obj:
        return {"success": False,
                "message": f"Malformed model output: {raw[:200]!r}"}

    return {"success": True, "command": shape_command_for_wire(obj)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest Server/tests/test_nlu_server.py -v`
Expected: PASS — 15 passed.

- [ ] **Step 5: Commit**

```bash
git add Server/nlu_server.py Server/tests/test_nlu_server.py
git commit -m "Add NLU server request handler with mocked-model test coverage"
```

---

### Task 3: NLU server — socket wiring and config

**Files:**
- Modify: `Server/nlu_server.py`
- Modify: `Server/tests/test_nlu_server.py`

**Interfaces:**
- Consumes: `handle_nlu_request` (Task 2).
- Produces: `start_server(host="0.0.0.0", port=5001)` in `nlu_server.py` — the entry point run by `if __name__ == "__main__":` and by Task 9's manual verification.

- [ ] **Step 1: Write the failing integration test**

Append to `Server/tests/test_nlu_server.py`:
```python
import json as json_module
import socket as socket_module
import threading
import time


def test_server_round_trip_over_socket():
    fake_obj = {"type": "navigation", "intent": "configure"}
    test_port = 15001

    with patch.object(nlu_server, "call_ollama",
                       return_value=(fake_obj, 0.1, "{}")):
        thread = threading.Thread(
            target=nlu_server.start_server,
            kwargs={"host": "127.0.0.1", "port": test_port},
            daemon=True,
        )
        thread.start()
        time.sleep(0.3)  # let the accept loop bind before we connect

        with socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM) as client:
            client.connect(("127.0.0.1", test_port))
            request = json_module.dumps({"type": "nlu", "utterance": "configure"}) + "\n"
            client.sendall(request.encode("utf-8"))
            response = json_module.loads(client.recv(4096).decode("utf-8").strip())

    assert response["success"] is True
    assert response["command"]["intent"] == "configure"


def test_server_rejects_non_nlu_request_type():
    test_port = 15002
    thread = threading.Thread(
        target=nlu_server.start_server,
        kwargs={"host": "127.0.0.1", "port": test_port},
        daemon=True,
    )
    thread.start()
    time.sleep(0.3)

    with socket_module.socket(socket_module.AF_INET, socket_module.SOCK_STREAM) as client:
        client.connect(("127.0.0.1", test_port))
        request = json_module.dumps({"type": "preview"}) + "\n"
        client.sendall(request.encode("utf-8"))
        response = json_module.loads(client.recv(4096).decode("utf-8").strip())

    assert response["success"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -m pytest Server/tests/test_nlu_server.py -v -k socket`
Expected: FAIL — `AttributeError: module 'nlu_server' has no attribute 'start_server'`.

- [ ] **Step 3: Implement `start_server`**

Replace the `if __name__ == "__main__":` block at the bottom of `Server/nlu_server.py` with:
```python
def start_server(host="0.0.0.0", port=5001):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((host, port))
        server_socket.listen(1)
        print(f"NLU server listening on {host}:{port}  (model={MODEL})", flush=True)

        while True:
            conn, addr = server_socket.accept()
            with conn:
                data = b""
                while True:
                    chunk = conn.recv(1024)
                    if not chunk or chunk.endswith(b"\n"):
                        data += chunk
                        break
                    data += chunk

                if not data:
                    continue

                try:
                    msg_obj = json.loads(data.decode("utf-8").strip())
                except json.JSONDecodeError:
                    response = {"success": False, "message": "Invalid JSON format."}
                else:
                    if msg_obj.get("type", "").lower() != "nlu":
                        response = {"success": False, "message": "Unknown request type."}
                    else:
                        response = handle_nlu_request(msg_obj, MODEL)

                conn.sendall((json.dumps(response) + "\n").encode("utf-8"))


if __name__ == "__main__":
    start_server()
```

Note: unlike `Server/server.py`, this handles exactly one request per accepted connection then loops back to `accept()` — matching the fresh-`TcpClient`-per-call pattern both `OperationsManager` and the new `NluDebugInput` (Task 8) use, rather than `server.py`'s keep-reading-until-disconnect loop.

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -m pytest Server/tests/test_nlu_server.py -v`
Expected: PASS — 17 passed.

- [ ] **Step 5: Commit**

```bash
git add Server/nlu_server.py Server/tests/test_nlu_server.py
git commit -m "Add NLU server socket wiring with threaded integration tests"
```

---

### Task 4: NLU server — manual smoke test against real Ollama

**Files:** none (verification only).

**Interfaces:**
- Consumes: `start_server` (Task 3), the live `qwen2.5:3b` Ollama model (already pulled and confirmed working in prior session).

- [ ] **Step 1: Start the server**

Run (from repo root, foreground terminal kept open):
```bash
py Server/nlu_server.py
```
Expected output: `NLU server listening on 0.0.0.0:5001  (model=qwen2.5:3b)`

- [ ] **Step 2: Send 3–4 raw utterances from a second terminal**

```bash
py -c "
import json, socket
tests = [
    'move waypoint two up five centimeters',
    'delete the last waypoint',
    'go to configure',
    'what is the weather today',
]
for u in tests:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(('127.0.0.1', 5001))
        s.sendall((json.dumps({'type': 'nlu', 'utterance': u}) + '\n').encode())
        print(u, '->', s.recv(4096).decode().strip())
"
```

Expected: each line prints `{"success": true, "command": {...}}` with `reference` (if present) as a string or `null`, never a bare number — e.g. the first utterance should show `"reference": "2", "axis": "z", "offset": 0.05` (or similarly close; exact wording-to-slot mapping is the already-evaluated model's job, not something this task re-verifies). This is a protocol sanity check, **not** a re-run of evaluation — 3–4 utterances is sufficient.

- [ ] **Step 3: Confirm no exceptions in the server terminal**, then leave the server running for Task 9 (or stop with Ctrl+C — it will be restarted before Task 9).

No commit — this task produces no file changes.

---

### Task 5: `WaypointManager` — reference resolution

**Files:**
- Modify: `Assets/Scripts/WaypointManager.cs`

**Interfaces:**
- Produces: `enum ReferenceResolution { Resolved, Missing, OutOfRange }` and `ReferenceResolution TryGetWaypointByReference(string reference, out Waypoint wp)` on `WaypointManager`, used by Task 7 (`VoiceCommandRouter`).

- [ ] **Step 1: Add the enum and method**

In `Assets/Scripts/WaypointManager.cs`, add the enum above the class declaration (after the existing `WaypointMode` enum, before `public class WaypointManager`):
```csharp
public enum ReferenceResolution
{
    Resolved,
    Missing,
    OutOfRange
}
```

Add the method inside `WaypointManager`, directly after `GetWaypoints()`:
```csharp
    /// <summary>
    /// Resolves an authoring command's `reference` field ("last", a 1-indexed
    /// integer as a string, or null/empty) to a Waypoint. Distinguishes
    /// "no reference given" from "that waypoint doesn't exist" so callers can
    /// give different feedback for each -- see ReferenceResolution.
    /// </summary>
    public ReferenceResolution TryGetWaypointByReference(string reference, out Waypoint wp)
    {
        wp = null;

        if (string.IsNullOrEmpty(reference))
            return ReferenceResolution.Missing;

        if (reference == "last")
        {
            if (waypoints.Count == 0)
                return ReferenceResolution.OutOfRange;
            wp = waypoints[waypoints.Count - 1];
            return ReferenceResolution.Resolved;
        }

        if (int.TryParse(reference, out int index) && index >= 1 && index <= waypoints.Count)
        {
            wp = waypoints[index - 1];
            return ReferenceResolution.Resolved;
        }

        return ReferenceResolution.OutOfRange;
    }
```

- [ ] **Step 2: Verify it compiles**

Run (from repo root; this forces Unity to reimport and compile in batch mode, writing a log):
```bash
"/c/Program Files/Unity/Hub/Editor/2022.3.62f3/Editor/Unity.exe" -batchmode -quit -projectPath "D:\GitHub\WayPointCreator" -logFile "C:\Users\smh10\AppData\Local\Temp\claude\d--GitHub-WayPointCreator\3e101a25-6d0a-46d5-8dc4-0277acde0ef1\scratchpad\unity_compile_task5.log"
```
Then check for compile errors:
```bash
grep -i "error CS" "C:\Users\smh10\AppData\Local\Temp\claude\d--GitHub-WayPointCreator\3e101a25-6d0a-46d5-8dc4-0277acde0ef1\scratchpad\unity_compile_task5.log"
```
Expected: no output (no matches). If there is output, fix the reported error before proceeding.

- [ ] **Step 3: Commit**

```bash
git add Assets/Scripts/WaypointManager.cs
git commit -m "Add WaypointManager.TryGetWaypointByReference with Missing/OutOfRange distinction"
```

---

### Task 6: `WaypointManager` — offset application

**Files:**
- Modify: `Assets/Scripts/WaypointManager.cs`

**Interfaces:**
- Consumes: nothing new (uses `UnityEngine.Vector3`/`Transform`, already available).
- Produces: `enum OffsetResult { Applied, UnsupportedAxis }` and `OffsetResult TryApplyOffset(Waypoint wp, string axis, float value, Transform robotBase)` on `WaypointManager`, used by Task 7.

- [ ] **Step 1: Add the enum and method**

In `Assets/Scripts/WaypointManager.cs`, add the enum next to `ReferenceResolution`:
```csharp
public enum OffsetResult
{
    Applied,
    UnsupportedAxis
}
```

Add the method directly after `TryGetWaypointByReference`:
```csharp
    /// <summary>
    /// Applies a UR10-base-frame offset (SI units: meters for x/y/z) to a
    /// waypoint, converting into Unity's local space relative to robotBase.
    /// This is the INVERSE of the conversion in
    /// OperationsManager.CalculateWaypointsData() -- that is the canonical,
    /// live Unity->UR conversion (UR.x=Unity.z, UR.y=-Unity.x, UR.z=Unity.y);
    /// a second, dead/commented conversion elsewhere in OperationsManager.cs
    /// uses different signs and must NOT be used as a reference here.
    ///
    /// Rotation axes (rx/ry/rz) are not implemented -- composing an
    /// axis-angle offset in UR frame back onto the waypoint's quaternion is
    /// materially more complex than translation and is deferred past Stage 1
    /// (tracked as required before the demo video). Returns UnsupportedAxis
    /// rather than silently no-op'ing or misapplying.
    /// </summary>
    public OffsetResult TryApplyOffset(Waypoint wp, string axis, float value, Transform robotBase)
    {
        Vector3 localDelta;
        switch (axis)
        {
            case "x": localDelta = new Vector3(0f, 0f, value); break;   // UR x -> Unity local z (forward)
            case "y": localDelta = new Vector3(-value, 0f, 0f); break;  // UR y -> Unity local -x (operator's left)
            case "z": localDelta = new Vector3(0f, value, 0f); break;   // UR z -> Unity local y (up)
            case "rx":
            case "ry":
            case "rz":
                return OffsetResult.UnsupportedAxis;
            default:
                return OffsetResult.UnsupportedAxis;
        }

        Vector3 localPos = robotBase.InverseTransformPoint(wp.transform.position);
        wp.transform.position = robotBase.TransformPoint(localPos + localDelta);
        return OffsetResult.Applied;
    }
```

- [ ] **Step 2: Verify it compiles**

Run:
```bash
"/c/Program Files/Unity/Hub/Editor/2022.3.62f3/Editor/Unity.exe" -batchmode -quit -projectPath "D:\GitHub\WayPointCreator" -logFile "C:\Users\smh10\AppData\Local\Temp\claude\d--GitHub-WayPointCreator\3e101a25-6d0a-46d5-8dc4-0277acde0ef1\scratchpad\unity_compile_task6.log"
```
```bash
grep -i "error CS" "C:\Users\smh10\AppData\Local\Temp\claude\d--GitHub-WayPointCreator\3e101a25-6d0a-46d5-8dc4-0277acde0ef1\scratchpad\unity_compile_task6.log"
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add Assets/Scripts/WaypointManager.cs
git commit -m "Add WaypointManager.TryApplyOffset with UR->Unity frame inverse, rotation axes stubbed"
```

---

### Task 7: `VoiceCommandRouter` — structured command dispatch

**Files:**
- Modify: `Assets/Scripts/Voice/VoiceCommandRouter.cs`

**Interfaces:**
- Consumes: `WaypointManager.ReferenceResolution`, `TryGetWaypointByReference` (Task 5); `WaypointManager.OffsetResult`, `TryApplyOffset` (Task 6); existing `Dispatch(VoiceIntent, float, string)`, `SetMode(WaypointMode, string)`, `Say(string)`, `Waypoints` property, `operationsManager.robotBase` (all pre-existing in this file/`OperationsManager.cs`).
- Produces: `class NluCommand` (serializable) and `void DispatchStructuredCommand(NluCommand cmd)` on `VoiceCommandRouter`, used by Task 8 (`NluDebugInput`).

- [ ] **Step 1: Add the `NluCommand` class**

In `Assets/Scripts/Voice/VoiceCommandRouter.cs`, add above the `VoiceCommandRouter` class declaration:
```csharp
/// <summary>
/// Deserialization target for the NLU server's `command` object
/// (Server/nlu_server.py). Field types match what JsonUtility can handle --
/// `reference` is always a string (or null) on the wire, never a bare int,
/// because JsonUtility can't deserialize a polymorphic field. See
/// Server/nlu_server.py's shape_command_for_wire for the encoding.
/// </summary>
[System.Serializable]
public class NluCommand
{
    public string type;       // "authoring" | "navigation" | "execution" | "reject"
    public string operation;  // authoring: "create" | "delete" | "offset" | "delete_all"
    public string reference;  // authoring: "last", a 1-indexed integer as a string, or null
    public string axis;       // authoring offset: "x" | "y" | "z" | "rx" | "ry" | "rz"
    public float offset;      // authoring offset: meters (x/y/z) or radians (rx/ry/rz)
    public string intent;     // navigation: "configure" | "trajectory" | "preview" | "run" | "exit" | "create_mode" | "edit_mode" | "delete_mode"
    public string verb;       // execution: "run" | "confirm" | "cancel" | "stop"
    public float confidence;
}
```

- [ ] **Step 2: Add `DispatchStructuredCommand` and its private helpers**

Inside `VoiceCommandRouter`, add after the existing public `Dispatch(...)` method:
```csharp
    /// <summary>Entry point for parsed NLU server commands (all four schema types).</summary>
    public void DispatchStructuredCommand(NluCommand cmd)
    {
        if (cmd == null)
        {
            Say("No command received.");
            return;
        }

        switch (cmd.type)
        {
            case "navigation":
                DispatchNavigationIntent(cmd.intent);
                break;
            case "execution":
                DispatchExecutionVerb(cmd.verb);
                break;
            case "authoring":
                DispatchAuthoring(cmd);
                break;
            case "reject":
                Say("Sorry, I didn't understand that command.");
                break;
            default:
                Debug.LogWarning($"[Voice] Unknown structured command type: {cmd.type}");
                break;
        }
    }

    // navigation.intent == "run" means "go to the preview/run screen"
    // (VoiceIntent.PreviewRun). This is a DIFFERENT action from
    // execution.verb == "run", which arms the safety-critical run gate
    // (VoiceIntent.Run). They come from different schema fields (intent vs
    // verb) -- do not collapse them by matching on the string "run" alone.
    private void DispatchNavigationIntent(string intent)
    {
        switch (intent)
        {
            case "configure":   Dispatch(VoiceIntent.Configure); break;
            case "trajectory":  Dispatch(VoiceIntent.Trajectory); break;
            case "preview":     Dispatch(VoiceIntent.Preview); break;
            case "run":         Dispatch(VoiceIntent.PreviewRun); break; // preview/run SCREEN, not the robot gate
            case "exit":        Dispatch(VoiceIntent.Exit); break;
            case "create_mode": Dispatch(VoiceIntent.CreateMode); break;
            case "edit_mode":   Dispatch(VoiceIntent.EditMode); break;
            case "delete_mode": Dispatch(VoiceIntent.DeleteMode); break;
            default:
                Debug.LogWarning($"[Voice] Unknown navigation intent: {intent}");
                break;
        }
    }

    private void DispatchExecutionVerb(string verb)
    {
        switch (verb)
        {
            case "run":     Dispatch(VoiceIntent.Run); break;     // arms the safety-critical run gate
            case "confirm": Dispatch(VoiceIntent.Confirm); break;
            case "cancel":  Dispatch(VoiceIntent.Cancel); break;
            case "stop":    Dispatch(VoiceIntent.Stop); break;
            default:
                Debug.LogWarning($"[Voice] Unknown execution verb: {verb}");
                break;
        }
    }

    private void DispatchAuthoring(NluCommand cmd)
    {
        switch (cmd.operation)
        {
            case "create":
                // Voice cannot supply a 3D point -- arm the gesture, don't invent a position.
                SetMode(WaypointMode.Create, "Create mode. Pinch to place a waypoint.");
                break;

            case "delete_all":
                if (Waypoints != null) Waypoints.DeleteAllWaypoints();
                Say("All waypoints deleted.");
                break;

            case "delete":
                HandleVoiceDelete(cmd.reference);
                break;

            case "offset":
                HandleVoiceOffset(cmd.reference, cmd.axis, cmd.offset);
                break;

            default:
                Debug.LogWarning($"[Voice] Unknown authoring operation: {cmd.operation}");
                break;
        }
    }

    // Deliberately bypasses the WaypointMode.Delete gate: RemoveWaypoint has
    // no internal mode check (the gate lives only at its two existing UI call
    // sites), and a voice `delete <reference>` already fully specifies its
    // target, so there's no missing-information reason to force a mode
    // switch first (and doing so would trigger the Delete-mode waypoint
    // recoloring as an unwanted side effect).
    private void HandleVoiceDelete(string reference)
    {
        if (Waypoints == null)
        {
            Say("No waypoints to delete.");
            return;
        }

        var result = Waypoints.TryGetWaypointByReference(reference, out Waypoint wp);
        switch (result)
        {
            case WaypointManager.ReferenceResolution.Resolved:
                Waypoints.RemoveWaypoint(wp);
                break;
            case WaypointManager.ReferenceResolution.Missing:
                Say("Which waypoint? Say delete last, or a waypoint number.");
                break;
            case WaypointManager.ReferenceResolution.OutOfRange:
                Say(reference == "last" ? "There are no waypoints." : $"There's no waypoint {reference}.");
                break;
        }
    }

    private void HandleVoiceOffset(string reference, string axis, float value)
    {
        if (Waypoints == null || operationsManager == null || operationsManager.robotBase == null)
        {
            Say("Can't apply offset right now.");
            return;
        }

        var result = Waypoints.TryGetWaypointByReference(reference, out Waypoint wp);
        if (result == WaypointManager.ReferenceResolution.Missing)
        {
            Say("Which waypoint? Say offset last, or a waypoint number.");
            return;
        }
        if (result == WaypointManager.ReferenceResolution.OutOfRange)
        {
            Say(reference == "last" ? "There are no waypoints." : $"There's no waypoint {reference}.");
            return;
        }

        var offsetResult = Waypoints.TryApplyOffset(wp, axis, value, operationsManager.robotBase);
        Say(offsetResult == WaypointManager.OffsetResult.UnsupportedAxis
            ? "Rotation offsets aren't wired up yet."
            : "Offset applied.");
    }
```

- [ ] **Step 3: Verify it compiles**

Run:
```bash
"/c/Program Files/Unity/Hub/Editor/2022.3.62f3/Editor/Unity.exe" -batchmode -quit -projectPath "D:\GitHub\WayPointCreator" -logFile "C:\Users\smh10\AppData\Local\Temp\claude\d--GitHub-WayPointCreator\3e101a25-6d0a-46d5-8dc4-0277acde0ef1\scratchpad\unity_compile_task7.log"
```
```bash
grep -i "error CS" "C:\Users\smh10\AppData\Local\Temp\claude\d--GitHub-WayPointCreator\3e101a25-6d0a-46d5-8dc4-0277acde0ef1\scratchpad\unity_compile_task7.log"
```
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git add Assets/Scripts/Voice/VoiceCommandRouter.cs
git commit -m "Add VoiceCommandRouter.DispatchStructuredCommand for all four NLU schema types"
```

---

### Task 8: `NluDebugInput` — Editor debug input

**Files:**
- Create: `Assets/Scripts/Voice/NluDebugInput.cs`

**Interfaces:**
- Consumes: `VoiceCommandRouter.DispatchStructuredCommand(NluCommand)`, `NluCommand` (Task 7).
- Produces: nothing consumed by later tasks — this is the top of the chain, exercised directly in Task 9.

- [ ] **Step 1: Create the debug input component**

`Assets/Scripts/Voice/NluDebugInput.cs`:
```csharp
using System.Net.Sockets;
using System.Text;
using UnityEngine;

/// <summary>
/// Editor-only debug input for Stage 1 NLU pipeline testing (no HoloLens
/// dictation -- that's Stage 2). Sends an utterance to the standalone NLU
/// server (Server/nlu_server.py, 127.0.0.1:5001) and dispatches the parsed
/// command through VoiceCommandRouter.
///
/// Self-bootstraps at Play-mode start -- no scene/prefab/Inspector wiring
/// required. Never compiled into the HoloLens release build.
/// </summary>
public class NluDebugInput : MonoBehaviour
{
#if UNITY_EDITOR || DEVELOPMENT_BUILD
    private const string ServerIP = "127.0.0.1";
    private const int ServerPort = 5001;

    // Covers all four schema types plus one reject case, for one-key smoke testing.
    private static readonly string[] CannedUtterances =
    {
        "move waypoint two up five centimeters", // authoring / offset
        "delete the last waypoint",               // authoring / delete
        "go to configure",                        // navigation
        "run it",                                 // execution
        "what's the weather today",                // reject
    };

    private string inputText = "";
    private string statusText = "";
    private VoiceCommandRouter router;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    private static void Bootstrap()
    {
        var go = new GameObject("[NluDebugInput]");
        go.AddComponent<NluDebugInput>();
        DontDestroyOnLoad(go);
    }

    private void Start()
    {
        router = FindObjectOfType<VoiceCommandRouter>();
        if (router == null)
            Debug.LogWarning("[NluDebugInput] No VoiceCommandRouter found in scene -- " +
                              "responses will be logged but not dispatched.");
    }

    private void Update()
    {
        for (int i = 0; i < CannedUtterances.Length; i++)
        {
            if (Input.GetKeyDown(KeyCode.Alpha1 + i))
                SendUtterance(CannedUtterances[i]);
        }
    }

    private void OnGUI()
    {
        GUILayout.BeginArea(new Rect(10, 10, 420, 130));
        GUILayout.Label("NLU Debug Input  (keys 1-5 = canned utterances)");
        inputText = GUILayout.TextField(inputText);

        bool enterPressed = Event.current.type == EventType.KeyDown &&
                             Event.current.keyCode == KeyCode.Return;
        if (GUILayout.Button("Send") || enterPressed)
            SendUtterance(inputText);

        GUILayout.Label(statusText);
        GUILayout.EndArea();
    }

    private void SendUtterance(string utterance)
    {
        if (string.IsNullOrEmpty(utterance)) return;
        statusText = $"Sending: \"{utterance}\"...";

        try
        {
            using (TcpClient client = new TcpClient(ServerIP, ServerPort))
            using (NetworkStream stream = client.GetStream())
            {
                string json = "{\"type\":\"nlu\",\"utterance\":\"" + EscapeJson(utterance) + "\"}\n";
                byte[] data = Encoding.UTF8.GetBytes(json);
                stream.Write(data, 0, data.Length);

                byte[] buffer = new byte[4096];
                int bytesRead = stream.Read(buffer, 0, buffer.Length);
                string response = Encoding.UTF8.GetString(buffer, 0, bytesRead).Trim();
                statusText = response;
                Debug.Log("[NluDebugInput] Response: " + response);

                var parsed = JsonUtility.FromJson<NluServerResponse>(response);
                if (parsed != null && parsed.success && router != null)
                    router.DispatchStructuredCommand(parsed.command);
            }
        }
        catch (SocketException e)
        {
            statusText = $"NLU server not reachable on {ServerIP}:{ServerPort}";
            Debug.LogWarning("[NluDebugInput] " + statusText + " (" + e.Message + ")");
        }
    }

    private static string EscapeJson(string s) => s.Replace("\\", "\\\\").Replace("\"", "\\\"");
#endif
}

[System.Serializable]
public class NluServerResponse
{
    public bool success;
    public string message;
    public NluCommand command;
}
```

- [ ] **Step 2: Verify it compiles**

Run:
```bash
"/c/Program Files/Unity/Hub/Editor/2022.3.62f3/Editor/Unity.exe" -batchmode -quit -projectPath "D:\GitHub\WayPointCreator" -logFile "C:\Users\smh10\AppData\Local\Temp\claude\d--GitHub-WayPointCreator\3e101a25-6d0a-46d5-8dc4-0277acde0ef1\scratchpad\unity_compile_task8.log"
```
```bash
grep -i "error CS" "C:\Users\smh10\AppData\Local\Temp\claude\d--GitHub-WayPointCreator\3e101a25-6d0a-46d5-8dc4-0277acde0ef1\scratchpad\unity_compile_task8.log"
```
Expected: no output.

- [ ] **Step 3: Commit**

```bash
git add Assets/Scripts/Voice/NluDebugInput.cs
git commit -m "Add self-bootstrapping Editor-only NLU debug input"
```

---

### Task 9: Full Stage 1 manual verification pass

**Files:** none (verification only — this is where the frame-conversion signs and dispatch behavior actually get exercised, per the testing-approach note in Global Constraints).

**Interfaces:**
- Consumes: everything from Tasks 1–8.

- [ ] **Step 1: Start the NLU server** (must happen before Play mode — the debug input has no auto-launch/retry)

```bash
py Server/nlu_server.py
```
Expected: `NLU server listening on 0.0.0.0:5001  (model=qwen2.5:3b)`

- [ ] **Step 2: Test the connection-failure path first**

Stop the server (Ctrl+C). In the Unity Editor, enter Play mode and use the debug input (key `4` or type "run it" and hit Send). Confirm the on-screen status shows `"NLU server not reachable on 127.0.0.1:5001"` — not an unhandled exception in the Console. Exit Play mode.

- [ ] **Step 3: Restart the server**, then re-enter Play mode.

```bash
py Server/nlu_server.py
```

- [ ] **Step 4: Verify all three translation axes, with signs**

Place at least one waypoint by hand (pinch, per existing interaction) or via the `create` canned utterance (key `3`... note: canned utterances are indices 1-5 for the array in Task 8; "create" isn't in the canned list, so type it directly): type `create a waypoint`, confirm Create-mode message appears, then pinch-place one waypoint in the Scene view.

Then, for each axis, type an utterance and visually confirm the waypoint moves in the Scene view exactly as follows relative to `robotBase`:
- `move waypoint one forward 5 centimeters` → **+x** → should move **forward, away from the robot base**.
- `move waypoint one left 5 centimeters` → **+y** → should move to the **operator's left**.
- `move waypoint one up 5 centimeters` → **+z** → should move **up**.

This is the one place the codebase has direct evidence of getting signs wrong before (the dead conversion in `OperationsManager.cs`), so check all three individually — do not stop at the first one that looks right.

- [ ] **Step 5: Verify delete on a valid reference, and `delete_all`**

`delete waypoint one` → waypoint removed, no exception. Add 2+ waypoints again (pinch-place), then `delete all waypoints` → all removed.

- [ ] **Step 6: Verify out-of-range delete gives distinct feedback**

With fewer than six waypoints present, say `delete waypoint six`. Confirm the on-screen/status message reads `"There's no waypoint 6."` (distinct from the "Which waypoint?" missing-reference message), and confirm nothing was deleted.

- [ ] **Step 7: Verify `create` behavior and feedback legibility**

`add a waypoint` → confirm the mode switches to Create (check `WaypointManager`'s status text or the mode-toggle UI) and the message `"Create mode. Pinch to place a waypoint."` is visible — not silent. Then pinch-place by hand and confirm it still works exactly as before this change.

- [ ] **Step 8: Verify `MAX_WAYPOINTS = 5` interaction**

Place 5 waypoints (the existing max). Apply a voice offset to one of them (`move waypoint one up 5 centimeters`) and confirm it succeeds without tripping `AddWaypoint`'s count/mode gating (i.e., no "Maximum of 5 waypoints reached" message appears — offset mutates an existing waypoint, it doesn't create one). Then `delete all waypoints`, followed immediately by `add a waypoint` — confirm Create mode switches cleanly, the waypoint count is genuinely zero (not stale), and a subsequent pinch-place creates waypoint **1**, not waypoint 6.

- [ ] **Step 9: Verify one navigation command, one execution command, one reject**

- `go to configure` → confirm `MenuManager.OnConfigurePressed()` fires (Configure screen opens) — this is `navigation.intent`, exercised via `VoiceIntent.Configure`.
- `run it` → confirm the run gate arms (existing `ArmRun()` behavior — run-confirm popup appears), **not** a screen navigation. This exercises `execution.verb = "run"` → `VoiceIntent.Run`, as distinct from `navigation.intent = "run"` → `VoiceIntent.PreviewRun` (can additionally test `go to run` to see the distinct screen-navigation behavior, confirming the two don't collapse).
- `what's the weather today` → confirm `"Sorry, I didn't understand that command."` and no state change.

- [ ] **Step 10: Check the Unity Console** for exceptions or errors across all of the above. None expected.

- [ ] **Step 11: Report results**

No commit for this task (verification only) — report back with a pass/fail for each of Steps 2, 4 (all three axes individually), 6, 7, 8, 9 so any failures can be triaged before Stage 1 is considered done.
