import json
import math
import pathlib
import subprocess

import pytest

from src.decision_cost import calculate_decision


def test_move_case():
    result = calculate_decision(0.6, 80, 1000, 100)
    assert result["state"] == "move"
    assert result["expected_without"] == pytest.approx(600)
    assert result["expected_move"] == pytest.approx(140)
    assert result["benefit"] == pytest.approx(460)
    assert result["break_even_probability"] == pytest.approx(80 / 900)


def test_keep_case():
    result = calculate_decision(0.6, 600, 1000, 100)
    assert result["state"] == "keep"
    assert result["expected_without"] == pytest.approx(600)
    assert result["expected_move"] == pytest.approx(660)
    assert result["benefit"] == pytest.approx(-60)


@pytest.mark.parametrize(
    ("probability", "move_cost", "loss_without", "loss_after"),
    [
        (0, 0, 100, 0),
        (1, 0, 100, 0),
        (0.5, 0, 100, 100),
        (0.5, 10, 100, 100),
        (0.5, 10, 100, 120),
        (1, 100, 100, 0),
    ],
)
def test_boundaries_and_cost_assumptions(probability, move_cost, loss_without, loss_after):
    result = calculate_decision(probability, move_cost, loss_without, loss_after)
    assert all(
        value is None or isinstance(value, (int, float)) and math.isfinite(value)
        for key, value in result.items()
        if key != "state"
    )
    if loss_without <= loss_after:
        assert result["break_even_probability"] is None


def test_tie_and_tolerance():
    exact = calculate_decision(0.5, 50, 100, 0)
    near = calculate_decision(0.5, 50 + 1e-9, 100, 0)
    outside = calculate_decision(0.5, 50 + 2e-8, 100, 0)
    assert exact["state"] == "tie"
    assert near["state"] == "tie"
    assert outside["state"] == "keep"


def test_break_even_can_exceed_one():
    result = calculate_decision(0.2, 200, 100, 0)
    assert result["break_even_probability"] == pytest.approx(2)
    assert result["state"] == "keep"


def test_extreme_positive_difference_keeps_break_even_finite():
    result = calculate_decision(1, 1_000_000_000, 5e-324, 0)
    assert result["break_even_probability"] == pytest.approx(float("1.7976931348623157e308"))
    assert math.isfinite(result["break_even_probability"])


@pytest.mark.parametrize(
    "args",
    [
        (True, 1, 1, 0),
        (0.5, False, 1, 0),
        (0.5, 1, "100", 0),
        (0.5, 1, None, 0),
        (float("nan"), 1, 1, 0),
        (0.5, float("inf"), 1, 0),
        (-0.01, 1, 1, 0),
        (1.01, 1, 1, 0),
        (0.5, -1, 1, 0),
        (0.5, 1_000_000_001, 1, 0),
        (0.5, 1, 1_000_000_001, 0),
        (0.5, 1, 1, 1_000_000_001),
    ],
)
def test_invalid_inputs_raise_clear_value_error(args):
    with pytest.raises(ValueError, match="参数"):
        calculate_decision(*args)


def test_missing_argument_is_clear_and_json_serializable():
    with pytest.raises(ValueError, match="不能为空"):
        calculate_decision(0.5, 1, 1)
    result = calculate_decision(0.6, 80, 1000, 100)
    assert json.loads(json.dumps(result, allow_nan=False)) == result


def test_python_and_javascript_match_on_same_real_case():
    project_dir = pathlib.Path(__file__).resolve().parents[1]
    node = pathlib.Path(r"C:\Users\kongbai\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe")
    script = (
        "const r=require('./templates/decision_cost.js').calculate({"
        "probability:0.6,move_cost:80,loss_without:1000,loss_after:100});"
        "process.stdout.write(JSON.stringify(r));"
    )
    completed = subprocess.run(
        [str(node), "-e", script],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    javascript_result = json.loads(completed.stdout)
    assert javascript_result == calculate_decision(0.6, 80, 1000, 100)
