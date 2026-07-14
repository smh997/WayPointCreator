#!/usr/bin/env python3
"""
AURaPath voice-command evaluation dataset builder.

Emits a labeled JSONL file: one row per utterance, each with an unambiguous
ground-truth structured command. Isolates language->command mapping
(ASR and robot execution are out of scope).

Schema (discriminated union on "type"):
  authoring   : {type, operation, reference, axis, offset}
  navigation  : {type, intent}          # confidence is model-reported, not labeled
  execution   : {type, verb}            # deferred safety verbs; confidence model-reported
  reject      : {type}                  # out-of-scope / ambiguous / unsupported

Frame convention (UR10 base): up=+z, down=-z, forward=+x, back=-x, left=+y, right=-y
Units: SI base. meters for x/y/z, radians for rx/ry/rz.
"""
import json
import math
import hashlib

DEG = math.pi / 180.0

def rad(deg):
    # round to a stable precision so ground truth compares cleanly
    return round(deg * DEG, 6)

def m(cm):
    return round(cm / 100.0, 6)

rows = []

def add(utterance, gt, category, notes=""):
    rows.append({
        "utterance": utterance.strip(),
        "ground_truth": gt,
        "category": category,
        "notes": notes,
    })

# ----------------------------------------------------------------------
# 1. AUTHORING — OFFSET  (varied magnitudes, UR10-base frame)
# ----------------------------------------------------------------------
# Primary axis: up/down (+z / -z) — frame-independent, weighted heavier.
# Horizontal (forward/back/left/right) included but lighter; documented convention.

# up / +z  (heavier: more paraphrases + more magnitudes)
add("raise waypoint two by five centimeters",
    {"type": "authoring", "operation": "offset", "reference": 2, "axis": "z", "offset": m(5)}, "offset_up")
add("move waypoint 3 up by ten centimeters",
    {"type": "authoring", "operation": "offset", "reference": 3, "axis": "z", "offset": m(10)}, "offset_up")
add("lift the second waypoint two centimeters higher",
    {"type": "authoring", "operation": "offset", "reference": 2, "axis": "z", "offset": m(2)}, "offset_up")
add("bump waypoint one up fifteen centimeters",
    {"type": "authoring", "operation": "offset", "reference": 1, "axis": "z", "offset": m(15)}, "offset_up")
add("raise the last waypoint by three centimeters",
    {"type": "authoring", "operation": "offset", "reference": "last", "axis": "z", "offset": m(3)}, "offset_up")
add("push waypoint 4 higher by eight centimeters",
    {"type": "authoring", "operation": "offset", "reference": 4, "axis": "z", "offset": m(8)}, "offset_up")
add("take waypoint two up by twelve centimeters",
    {"type": "authoring", "operation": "offset", "reference": 2, "axis": "z", "offset": m(12)}, "offset_up")

# down / -z
add("lower waypoint two by five centimeters",
    {"type": "authoring", "operation": "offset", "reference": 2, "axis": "z", "offset": -m(5)}, "offset_down")
add("drop waypoint 3 down ten centimeters",
    {"type": "authoring", "operation": "offset", "reference": 3, "axis": "z", "offset": -m(10)}, "offset_down")
add("move the first waypoint down by four centimeters",
    {"type": "authoring", "operation": "offset", "reference": 1, "axis": "z", "offset": -m(4)}, "offset_down")
add("bring waypoint five lower by seven centimeters",
    {"type": "authoring", "operation": "offset", "reference": 5, "axis": "z", "offset": -m(7)}, "offset_down")
add("lower the last waypoint two centimeters",
    {"type": "authoring", "operation": "offset", "reference": "last", "axis": "z", "offset": -m(2)}, "offset_down")
add("sink waypoint two by six centimeters",
    {"type": "authoring", "operation": "offset", "reference": 2, "axis": "z", "offset": -m(6)}, "offset_down")

# forward / +x  (lighter)
add("move waypoint two forward by five centimeters",
    {"type": "authoring", "operation": "offset", "reference": 2, "axis": "x", "offset": m(5)}, "offset_forward")
add("push the third waypoint forward ten centimeters",
    {"type": "authoring", "operation": "offset", "reference": 3, "axis": "x", "offset": m(10)}, "offset_forward")
add("shift waypoint one away from the base by eight centimeters",
    {"type": "authoring", "operation": "offset", "reference": 1, "axis": "x", "offset": m(8)}, "offset_forward")

# back / -x  (lighter)
add("move waypoint two back by five centimeters",
    {"type": "authoring", "operation": "offset", "reference": 2, "axis": "x", "offset": -m(5)}, "offset_back")
add("pull waypoint four backward by twelve centimeters",
    {"type": "authoring", "operation": "offset", "reference": 4, "axis": "x", "offset": -m(12)}, "offset_back")

# left / +y  (lighter)
add("move waypoint three to the left by five centimeters",
    {"type": "authoring", "operation": "offset", "reference": 3, "axis": "y", "offset": m(5)}, "offset_left")
add("shift the second waypoint left by nine centimeters",
    {"type": "authoring", "operation": "offset", "reference": 2, "axis": "y", "offset": m(9)}, "offset_left")

# right / -y  (lighter)
add("move waypoint three to the right by five centimeters",
    {"type": "authoring", "operation": "offset", "reference": 3, "axis": "y", "offset": -m(5)}, "offset_right")
add("nudge waypoint one right by three centimeters",
    {"type": "authoring", "operation": "offset", "reference": 1, "axis": "y", "offset": -m(3)}, "offset_right")

# rotational offsets (rx/ry/rz in radians) — a few, to exercise unit conversion
add("rotate waypoint two around z by fifteen degrees",
    {"type": "authoring", "operation": "offset", "reference": 2, "axis": "rz", "offset": rad(15)}, "offset_rot")
add("turn the last waypoint ten degrees about the z axis",
    {"type": "authoring", "operation": "offset", "reference": "last", "axis": "rz", "offset": rad(10)}, "offset_rot")
add("tilt waypoint three by twenty degrees around x",
    {"type": "authoring", "operation": "offset", "reference": 3, "axis": "rx", "offset": rad(20)}, "offset_rot")
add("roll waypoint one negative five degrees about y",
    {"type": "authoring", "operation": "offset", "reference": 1, "axis": "ry", "offset": rad(-5)}, "offset_rot")

# ----------------------------------------------------------------------
# 2. AUTHORING — CREATE / DELETE / DELETE_ALL
# ----------------------------------------------------------------------
add("create a new waypoint",
    {"type": "authoring", "operation": "create", "reference": None, "axis": None, "offset": None}, "create")
add("add a waypoint here",
    {"type": "authoring", "operation": "create", "reference": None, "axis": None, "offset": None}, "create")
add("place a new point",
    {"type": "authoring", "operation": "create", "reference": None, "axis": None, "offset": None}, "create")
add("drop a waypoint",
    {"type": "authoring", "operation": "create", "reference": None, "axis": None, "offset": None}, "create")
add("make a new waypoint at this spot",
    {"type": "authoring", "operation": "create", "reference": None, "axis": None, "offset": None}, "create")

add("delete waypoint two",
    {"type": "authoring", "operation": "delete", "reference": 2, "axis": None, "offset": None}, "delete")
add("remove the third waypoint",
    {"type": "authoring", "operation": "delete", "reference": 3, "axis": None, "offset": None}, "delete")
add("get rid of waypoint five",
    {"type": "authoring", "operation": "delete", "reference": 5, "axis": None, "offset": None}, "delete")
add("erase the last waypoint",
    {"type": "authoring", "operation": "delete", "reference": "last", "axis": None, "offset": None}, "delete")
add("delete point one",
    {"type": "authoring", "operation": "delete", "reference": 1, "axis": None, "offset": None}, "delete")

add("delete all waypoints",
    {"type": "authoring", "operation": "delete_all", "reference": None, "axis": None, "offset": None}, "delete_all")
add("clear all the waypoints",
    {"type": "authoring", "operation": "delete_all", "reference": None, "axis": None, "offset": None}, "delete_all")
add("remove everything",
    {"type": "authoring", "operation": "delete_all", "reference": None, "axis": None, "offset": None}, "delete_all")
add("wipe the whole path",
    {"type": "authoring", "operation": "delete_all", "reference": None, "axis": None, "offset": None}, "delete_all")
add("start over and clear all points",
    {"type": "authoring", "operation": "delete_all", "reference": None, "axis": None, "offset": None}, "delete_all")

# ----------------------------------------------------------------------
# 3. NAVIGATION / MODE
# ----------------------------------------------------------------------
nav = {
    "configure": ["go to configure", "open the configure menu", "switch to configuration",
                  "take me to setup", "I want to configure the twin", "show configure"],
    "trajectory": ["go to trajectory", "open trajectory mode", "switch to the trajectory canvas",
                   "let me edit waypoints", "open waypoint editing", "show trajectory"],
    "preview": ["preview the motion", "show me the preview", "animate the trajectory",
                "let me see it move", "play the preview", "preview the path"],
    "run": ["go to the run screen", "open preview and run", "take me to the run menu",
            "show the run panel", "open the execute screen"],
    "exit": ["exit", "quit the app", "close this", "go back to the main menu", "leave this screen", "exit please"],
    "create_mode": ["switch to create mode", "enter create mode", "let me add waypoints",
                    "turn on create mode", "go into placement mode"],
    "edit_mode": ["switch to edit mode", "enter edit mode", "let me edit waypoints",
                  "turn on editing", "go into edit mode"],
    "delete_mode": ["switch to delete mode", "enter delete mode", "let me delete waypoints",
                    "turn on delete mode", "go into deletion mode"],
}
for intent, phrases in nav.items():
    for p in phrases:
        add(p, {"type": "navigation", "intent": intent}, f"nav_{intent}")

# ----------------------------------------------------------------------
# 4. EXECUTION — deferred safety verbs (LLM should route to type=execution)
# ----------------------------------------------------------------------
execs = {
    "run": ["run it", "execute the path", "send it to the robot", "go ahead and run",
            "run the trajectory", "start the robot"],
    "confirm": ["confirm", "yes confirm", "acknowledge the path", "yes go ahead", "confirmed", "affirmative"],
    "cancel": ["cancel", "never mind", "cancel that", "stop the confirmation", "abort this", "cancel the run"],
    "stop": ["stop", "halt", "stop now", "emergency stop", "freeze", "stop the robot"],
}
for verb, phrases in execs.items():
    for p in phrases:
        add(p, {"type": "execution", "verb": verb}, f"exec_{verb}")

# ----------------------------------------------------------------------
# 5. REJECT — out-of-scope / ambiguous / unsupported
# ----------------------------------------------------------------------
rejects = [
    ("what's the weather today", "out_of_domain"),
    ("tell me a joke", "out_of_domain"),
    ("how heavy is the ur10 arm", "out_of_domain_qa"),
    ("make the robot dance", "unsupported_op"),
    ("pick up that box over there", "unsupported_op"),
    ("weld along the seam", "unsupported_op"),
    ("move the waypoint", "ambiguous_missing_ref_axis"),
    ("raise it", "ambiguous_missing_ref_amount"),
    ("shift by five centimeters", "ambiguous_missing_ref_axis"),
    ("move waypoint two", "ambiguous_missing_axis_amount"),
    ("do the thing", "ambiguous_vacuous"),
    ("change something", "ambiguous_vacuous"),
    ("set the speed to fifty percent", "unsupported_param"),
    ("increase the force limit", "unsupported_param"),
    ("undo that", "unsupported_op"),
    ("redo the last move", "unsupported_op"),
    ("save this program as test one", "unsupported_op"),
    ("load the previous path", "unsupported_op"),
    ("rotate the robot base", "unsupported_op"),
    ("go faster", "unsupported_param"),
    ("mirror the path", "unsupported_op"),
    ("waypoint", "ambiguous_vacuous"),
    ("delete", "ambiguous_missing_ref"),
    ("move waypoint fifty up by five centimeters", "out_of_range_ref"),
]
for utt, note in rejects:
    add(utt, {"type": "reject"}, "reject", note)

# ----------------------------------------------------------------------
# 6. PHRASING-STRESS variants (harder wording of in-scope commands)
# ----------------------------------------------------------------------
add("could you nudge the second waypoint upward a couple centimeters",
    {"type": "authoring", "operation": "offset", "reference": 2, "axis": "z", "offset": m(2)}, "stress_offset")
add("I'd like waypoint three raised by about seven centimeters",
    {"type": "authoring", "operation": "offset", "reference": 3, "axis": "z", "offset": m(7)}, "stress_offset")
add("scoot the last one down four centimeters please",
    {"type": "authoring", "operation": "offset", "reference": "last", "axis": "z", "offset": -m(4)}, "stress_offset")
add("can we drop point number two by nine centimeters",
    {"type": "authoring", "operation": "offset", "reference": 2, "axis": "z", "offset": -m(9)}, "stress_offset")
add("go ahead and remove the second one",
    {"type": "authoring", "operation": "delete", "reference": 2, "axis": None, "offset": None}, "stress_delete")
add("let's just clear everything and restart",
    {"type": "authoring", "operation": "delete_all", "reference": None, "axis": None, "offset": None}, "stress_delete_all")
add("mind adding a fresh waypoint for me",
    {"type": "authoring", "operation": "create", "reference": None, "axis": None, "offset": None}, "stress_create")
add("take us over to the trajectory editor",
    {"type": "navigation", "intent": "trajectory"}, "stress_nav")
add("alright let's run this on the arm",
    {"type": "execution", "verb": "run"}, "stress_exec")
add("yeah that's good confirm it",
    {"type": "execution", "verb": "confirm"}, "stress_exec")
add("hold on stop everything",
    {"type": "execution", "verb": "stop"}, "stress_exec")
add("shift waypoint four to the right by six centimeters",
    {"type": "authoring", "operation": "offset", "reference": 4, "axis": "y", "offset": -m(6)}, "stress_offset")
add("bring the first waypoint forward eleven centimeters",
    {"type": "authoring", "operation": "offset", "reference": 1, "axis": "x", "offset": m(11)}, "stress_offset")
add("spin waypoint two thirty degrees around the z axis",
    {"type": "authoring", "operation": "offset", "reference": 2, "axis": "rz", "offset": rad(30)}, "stress_offset")
add("get me into delete mode",
    {"type": "navigation", "intent": "delete_mode"}, "stress_nav")
add("open up the preview so I can watch it",
    {"type": "navigation", "intent": "preview"}, "stress_nav")
add("scrap waypoint six",
    {"type": "authoring", "operation": "delete", "reference": 6, "axis": None, "offset": None}, "stress_delete")
add("kill it now",
    {"type": "execution", "verb": "stop"}, "stress_exec")

# ----------------------------------------------------------------------
# 7. FILL — extra paraphrases for thinner in-scope categories
# ----------------------------------------------------------------------
# create
add("insert a waypoint", {"type": "authoring", "operation": "create", "reference": None, "axis": None, "offset": None}, "create")
# delete
add("take out waypoint four", {"type": "authoring", "operation": "delete", "reference": 4, "axis": None, "offset": None}, "delete")
# delete_all
add("delete the entire trajectory", {"type": "authoring", "operation": "delete_all", "reference": None, "axis": None, "offset": None}, "delete_all")
# horizontal offsets (bring these up a bit)
add("push waypoint two away by seven centimeters", {"type": "authoring", "operation": "offset", "reference": 2, "axis": "x", "offset": m(7)}, "offset_forward")
add("draw waypoint three toward me by four centimeters", {"type": "authoring", "operation": "offset", "reference": 3, "axis": "x", "offset": -m(4)}, "offset_back")
add("move the last waypoint left by six centimeters", {"type": "authoring", "operation": "offset", "reference": "last", "axis": "y", "offset": m(6)}, "offset_left")
add("slide waypoint five to the right by two centimeters", {"type": "authoring", "operation": "offset", "reference": 5, "axis": "y", "offset": -m(2)}, "offset_right")
# rotational
add("yaw the last waypoint by twenty five degrees around z", {"type": "authoring", "operation": "offset", "reference": "last", "axis": "rz", "offset": rad(25)}, "offset_rot")
add("pitch waypoint two eight degrees about y", {"type": "authoring", "operation": "offset", "reference": 2, "axis": "ry", "offset": rad(8)}, "offset_rot")
# nav thin ones (create_mode, edit_mode, delete_mode, nav_run each had 5)
add("start placing waypoints", {"type": "navigation", "intent": "create_mode"}, "nav_create_mode")
add("let me modify the points", {"type": "navigation", "intent": "edit_mode"}, "nav_edit_mode")
add("switch over to removing waypoints", {"type": "navigation", "intent": "delete_mode"}, "nav_delete_mode")
add("bring up the execute panel", {"type": "navigation", "intent": "run"}, "nav_run")
# reject — a few more ambiguity/unsupported to keep the safety bucket strong
add("move it over there", {"type": "reject"}, "reject", "ambiguous_deictic")
add("bend the arm a little", {"type": "reject"}, "reject", "unsupported_op")
add("what can you do", {"type": "reject"}, "reject", "out_of_domain_qa")
add("home the robot", {"type": "reject"}, "reject", "unsupported_op")
add("calibrate the gripper", {"type": "reject"}, "reject", "unsupported_op")

# ----------------------------------------------------------------------
# Assign stable ids and write out
# ----------------------------------------------------------------------
for i, r in enumerate(rows):
    h = hashlib.sha1(r["utterance"].encode()).hexdigest()[:8]
    r_id = f"{i:03d}_{h}"
    # reorder keys: id first
    rows[i] = {"id": r_id, **r}

with open("dataset.jsonl", "w") as f:
    for r in rows:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")

# ---- summary ----
from collections import Counter
by_type = Counter(r["ground_truth"]["type"] for r in rows)
by_cat = Counter(r["category"] for r in rows)
print(f"TOTAL rows: {len(rows)}")
print("\nBy type:")
for k, v in sorted(by_type.items()):
    print(f"  {k:12s} {v}")
print("\nBy category:")
for k, v in sorted(by_cat.items()):
    print(f"  {k:28s} {v}")

# integrity checks
assert all("reject" != r["ground_truth"]["type"] or set(r["ground_truth"]) == {"type"} for r in rows), "reject must be type-only"
for r in rows:
    gt = r["ground_truth"]
    if gt["type"] == "authoring":
        assert set(gt) == {"type", "operation", "reference", "axis", "offset"}, r["id"]
    if gt["type"] == "navigation":
        assert set(gt) == {"type", "intent"}, r["id"]
    if gt["type"] == "execution":
        assert set(gt) == {"type", "verb"}, r["id"]
print("\nAll schema integrity checks passed.")
