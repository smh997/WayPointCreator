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
