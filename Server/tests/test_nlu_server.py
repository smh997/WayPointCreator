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
