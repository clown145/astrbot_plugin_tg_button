import asyncio
from typing import Any, Dict

# --- 动作元数据 ---
ACTION_METADATA = {
    "id": "delay",
    "name": "延迟/路由 (Delay/Router)",
    "description": "用于在工作流中插入一个时间延迟，或创建一个纯粹的执行顺序依赖，而不会污染数据流。",
    "inputs": [
        {
            "name": "delay_ms",
            "type": "integer",
            "required": False,
            "default": 0,
            "description": "需要延迟的毫秒数。",
        },
        {
            "name": "control_input",
            "type": "any",
            "required": False,
            "description": "【控制流输入】连接上一个节点到此，仅用于确立执行顺序。此接口收到的数据将被忽略。",
        },
        {
            "name": "passthrough_input",
            "type": "any",
            "required": False,
            "description": "【数据流输入】需要延迟后，再向下游传递的数据。",
        },
    ],
    "outputs": [
        {
            "name": "passthrough_output",
            "type": "any",
            "description": "【数据流输出】将从 passthrough_input 收到的数据原样输出。",
        }
    ],
}


# --- 动作执行逻辑 ---
async def execute(
    delay_ms: int = 0, control_input: Any = None, passthrough_input: Any = None
) -> Dict[str, Any]:
    """
    执行延迟，并透传数据。
    `control_input` 被有意地接收但从不使用，以实现“吞掉”上游数据的效果。
    """
    # 1. 执行延迟
    delay_duration_ms = 0
    try:
        delay_duration_ms = int(delay_ms)
    except (ValueError, TypeError):
        pass  # 如果转换失败，则保持为0

    if delay_duration_ms > 0:
        await asyncio.sleep(delay_duration_ms / 1000)

    # 2. 返回结果
    # 只将 passthrough_input 的值传递给 passthrough_output
    return {"passthrough_output": passthrough_input}
