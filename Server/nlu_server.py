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


if __name__ == "__main__":
    pass  # server wiring added in Task 3
