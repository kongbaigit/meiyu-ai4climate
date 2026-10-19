"""纯成本决策计算。

本模块只计算调用方提供的假设账单，不读取天气数据，也不替用户确认是否执行搬运。
"""

from __future__ import annotations

import json
import math
from numbers import Number
from typing import Any


_MISSING = object()
_PROBABILITY_MIN = 0.0
_PROBABILITY_MAX = 1.0
_MONEY_MIN = 0.0
_MONEY_MAX = 1_000_000_000.0
_BENEFIT_TOLERANCE = 1e-8
_MAX_FINITE = float("1.7976931348623157e308")


def _finite_real(value: Any, name: str) -> float:
    """验证并规范化一个有限实数，错误信息保持面向调用方的中文。"""

    if value is _MISSING:
        raise ValueError(f"参数{name}不能为空，必须提供有限实数")
    # bool 是 int 的子类，但在账单计算中不接受 True/False 作为数字。
    if isinstance(value, bool) or not isinstance(value, Number):
        raise ValueError(f"参数{name}必须是有限实数，不能是布尔值、字符串或空值")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise ValueError(f"参数{name}必须是有限实数") from exc
    if not math.isfinite(number):
        raise ValueError(f"参数{name}必须是有限实数，不能是NaN或无穷大")
    return number


def _bounded(value: Any, name: str, lower: float, upper: float) -> float:
    number = _finite_real(value, name)
    if number < lower or number > upper:
        raise ValueError(f"参数{name}必须在[{lower:g}, {upper:g}]范围内")
    return number


def calculate_decision(
    probability: Any = _MISSING,
    move_cost: Any = _MISSING,
    loss_without: Any = _MISSING,
    loss_after: Any = _MISSING,
) -> dict[str, float | str | None]:
    """按期望成本评估是否值得搬运。

    ``probability`` 是用户提供的事件概率；本函数不会将其重新解释为货损概率，
    也不会检查天气新鲜度或用户确认状态。
    """

    p = _bounded(probability, "probability", _PROBABILITY_MIN, _PROBABILITY_MAX)
    cost = _bounded(move_cost, "move_cost", _MONEY_MIN, _MONEY_MAX)
    without = _bounded(loss_without, "loss_without", _MONEY_MIN, _MONEY_MAX)
    after = _bounded(loss_after, "loss_after", _MONEY_MIN, _MONEY_MAX)

    expected_without = p * without
    expected_move = cost + p * after
    benefit = p * (without - after) - cost

    if abs(benefit) <= _BENEFIT_TOLERANCE:
        state = "tie"
    elif benefit > 0.0:
        state = "move"
    else:
        state = "keep"

    loss_difference = without - after
    if loss_difference > 0.0:
        break_even_probability = cost / loss_difference
        # 极小的正差值可能让阈值超出双精度范围；JSON 结果仍须保持有限。
        if not math.isfinite(break_even_probability):
            break_even_probability = _MAX_FINITE
    else:
        break_even_probability = None

    result: dict[str, float | str | None] = {
        "state": state,
        "probability": p,
        "move_cost": cost,
        "loss_without": without,
        "loss_after": after,
        "expected_without": expected_without,
        "expected_move": expected_move,
        "benefit": benefit,
        "break_even_probability": break_even_probability,
    }

    # 显式检查可避免未来修改引入不可 JSON 化的值。
    json.dumps(result, allow_nan=False)
    return result


__all__ = ["calculate_decision"]
