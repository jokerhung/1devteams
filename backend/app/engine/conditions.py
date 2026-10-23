"""Small expression language. Never executes workflow-supplied Python."""

import operator
import re
from typing import Any

PATTERN = re.compile(
    r"(last_route\.([\w-]+)|iteration\.([\w-]+)|len\(modified_files\))\s*"
    r'(==|!=|>=|<=|>|<)\s*("[^"\n]*"|\d+)'
)


def evaluate(expression: str, state: dict[str, Any]) -> bool:
    match = PATTERN.fullmatch(expression.strip())
    if not match:
        raise ValueError("Biểu thức condition không hợp lệ")
    left, route, iteration, op, right = match.groups()
    actual = (
        state.get("last_route", {}).get(route, "")
        if route
        else state.get("iteration", {}).get(iteration, 0)
        if iteration
        else len(state.get("modified_files", []))
    )
    expected = right[1:-1] if right.startswith('"') else int(right)
    if type(actual) is not type(expected):
        raise ValueError("Condition sai kiểu dữ liệu")
    return bool(
        {
            "==": operator.eq,
            "!=": operator.ne,
            ">=": operator.ge,
            "<=": operator.le,
            ">": operator.gt,
            "<": operator.lt,
        }[op](actual, expected)
    )
