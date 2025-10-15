"""工作流条件判断预设模块。"""

import re
from typing import Any, Dict, Iterable, Tuple


OPERATOR_OPTIONS: Tuple[Tuple[str, str], ...] = (
    ("equals", "等于 (==)"),
    ("not_equals", "不等于 (!=)"),
    ("greater", "大于 (>)"),
    ("greater_or_equal", "大于等于 (>=)"),
    ("less", "小于 (<)"),
    ("less_or_equal", "小于等于 (<=)"),
    ("contains", "包含"),
    ("not_contains", "不包含"),
    ("in", "属于集合"),
    ("not_in", "不属于集合"),
    ("starts_with", "以……开头"),
    ("ends_with", "以……结尾"),
    ("matches", "正则匹配"),
    ("is_truthy", "判定为真"),
    ("is_falsy", "判定为假"),
)

OPERATOR_CANONICAL_MAP = {
    "equals": "equals",
    "==": "equals",
    "等于": "equals",
    "等于 (==)": "equals",
    "not_equals": "not_equals",
    "!=": "not_equals",
    "<>": "not_equals",
    "不等于": "not_equals",
    "greater": "greater",
    ">": "greater",
    "大于": "greater",
    "greater_or_equal": "greater_or_equal",
    ">=": "greater_or_equal",
    "大于等于": "greater_or_equal",
    "less": "less",
    "<": "less",
    "小于": "less",
    "less_or_equal": "less_or_equal",
    "<=": "less_or_equal",
    "小于等于": "less_or_equal",
    "contains": "contains",
    "包含": "contains",
    "not_contains": "not_contains",
    "不包含": "not_contains",
    "in": "in",
    "属于集合": "in",
    "not_in": "not_in",
    "不属于集合": "not_in",
    "starts_with": "starts_with",
    "以……开头": "starts_with",
    "ends_with": "ends_with",
    "以……结尾": "ends_with",
    "matches": "matches",
    "正则匹配": "matches",
    "is_truthy": "is_truthy",
    "判定为真": "is_truthy",
    "is_falsy": "is_falsy",
    "判定为假": "is_falsy",
}


ACTION_METADATA = {
    "id": "branch_condition",
    "name": "条件判断 (Condition Check)",
    "description": (
        "接收上游数据并计算布尔结果，可用于驱动工作流分支。"
        "支持常见的比较、包含、正则匹配等运算，并允许将结果保存为自定义变量名。"
    ),
    "inputs": [
        {
            "name": "left",
            "type": "any",
            "description": "需要参与判断的左值，可以来自上游节点或静态填写。",
        },
        {
            "name": "operator",
            "type": "string",
            "description": "选择要使用的运算符，不同运算符会对右侧输入有不同要求。",
            "default": "equals",
            "choices": [
                {"value": value, "label": label}
                for value, label in OPERATOR_OPTIONS
            ],
        },
        {
            "name": "right",
            "type": "any",
            "description": "需要参与判断的右值，对部分运算符可以留空。",
        },
        {
            "name": "case_insensitive",
            "type": "boolean",
            "description": "在字符串比较时忽略大小写。",
            "default": False,
        },
        {
            "name": "interpret_numbers",
            "type": "boolean",
            "description": "尝试将字符串转换为数字再比较（适用于大小比较）。",
            "default": True,
        },
        {
            "name": "result_variable",
            "type": "string",
            "description": "额外保存布尔结果所用的自定义变量名，可选。",
        },
    ],
    "outputs": [
        {
            "name": "result",
            "type": "boolean",
            "description": "最终的布尔判断结果。",
        },
        {
            "name": "negated_result",
            "type": "boolean",
            "description": "布尔结果取反后的值，便于直接驱动反向分支。",
        },
        {
            "name": "result_as_text",
            "type": "string",
            "description": '布尔结果的字符串形式（"true" 或 "false"）。',
        },
    ],
}


def _coerce_iterable(value: Any) -> Iterable[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return value
    if isinstance(value, str):
        return [item.strip() for item in value.split(",")]
    return [value]


def _maybe_to_number(value: Any) -> Tuple[bool, float]:
    if isinstance(value, (int, float)):
        return True, float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return False, 0.0
        try:
            return True, float(stripped)
        except ValueError:
            return False, 0.0
    return False, 0.0


def _normalize_case(value: Any, case_insensitive: bool) -> Any:
    if not case_insensitive:
        return value
    if isinstance(value, str):
        return value.lower()
    if isinstance(value, (list, tuple, set)):
        return type(value)(_normalize_case(item, True) for item in value)
    return value


def _normalize_operator(operator: str) -> str:
    key = (operator or "equals").strip().lower()
    return OPERATOR_CANONICAL_MAP.get(key, key)


def _compare(
    left: Any,
    operator: str,
    right: Any,
    *,
    case_insensitive: bool,
    interpret_numbers: bool,
) -> bool:
    op = _normalize_operator(operator)
    left_value = _normalize_case(left, case_insensitive)
    right_value = _normalize_case(right, case_insensitive)

    if interpret_numbers and op in {
        "equals",
        "not_equals",
        "greater",
        "greater_or_equal",
        "less",
        "less_or_equal",
    }:
        left_is_num, left_num = _maybe_to_number(left_value)
        right_is_num, right_num = _maybe_to_number(right_value)
        if left_is_num and right_is_num:
            left_value = left_num
            right_value = right_num

    if op in {"equals", "=="}:
        return left_value == right_value
    if op in {"not_equals", "!=", "<>"}:
        return left_value != right_value
    if op in {"greater", ">"}:
        return left_value > right_value
    if op in {"greater_or_equal", ">="}:
        return left_value >= right_value
    if op in {"less", "<"}:
        return left_value < right_value
    if op in {"less_or_equal", "<="}:
        return left_value <= right_value

    if op == "contains":
        if isinstance(left_value, str) and right_value is not None:
            return str(right_value) in left_value
        return right_value in _coerce_iterable(left_value)
    if op == "not_contains":
        if isinstance(left_value, str) and right_value is not None:
            return str(right_value) not in left_value
        return right_value not in _coerce_iterable(left_value)

    if op == "in":
        return left_value in _coerce_iterable(right_value)
    if op == "not_in":
        return left_value not in _coerce_iterable(right_value)

    if op == "starts_with":
        return isinstance(left_value, str) and isinstance(right_value, str) and left_value.startswith(right_value)
    if op == "ends_with":
        return isinstance(left_value, str) and isinstance(right_value, str) and left_value.endswith(right_value)

    if op == "matches":
        if not isinstance(right_value, str):
            return False
        pattern = right_value
        try:
            return bool(re.search(pattern, str(left)))
        except re.error:
            return False

    if op == "is_truthy":
        return bool(left)
    if op == "is_falsy":
        return not bool(left)

    # 回退到等于判断
    return left_value == right_value


async def execute(
    left: Any = None,
    operator: str = "equals",
    right: Any = None,
    *,
    case_insensitive: bool = False,
    interpret_numbers: bool = True,
    result_variable: str = "",
) -> Dict[str, Any]:
    result = _compare(
        left,
        operator,
        right,
        case_insensitive=case_insensitive,
        interpret_numbers=interpret_numbers,
    )
    payload: Dict[str, Any] = {
        "result": result,
        "negated_result": not result,
        "result_as_text": "true" if result else "false",
    }
    if result_variable:
        key = str(result_variable).strip()
        if key:
            payload[key] = result
    return payload
