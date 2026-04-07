# jump_to_webpage.py
from typing import Dict, Any

# --- 动作元数据 ---
ACTION_METADATA = {
    # 动作的唯一标识符，已改为 jump_to_webpage
    "id": "jump_to_webpage",
    
    # 在 WebUI 中显示的名称
    "name": "跳转至网页",
    
    "description": "将当前的按钮转换为一个跳转链接，点击后直接在浏览器中打开目标 URL。",
    
    # 定义输入参数
    "inputs": [
        {
            "name": "url",
            "type": "string",
            "required": True,
            "description": "要跳转到的完整 URL 地址。",
        },
        {
            "name": "display_text",
            "type": "string",
            "default": "立即访问",
            "description": "跳转按钮上显示的文字内容。",
        }
    ],
    
    # 此动作直接操作 UI，无需定义输出变量
    "outputs": [], 
}

# --- 动作执行逻辑 ---
async def execute(**kwargs) -> Dict[str, Any]:
    """
    执行逻辑：通过返回特殊的 UI 控制键来修改 Telegram 按钮属性
    """
    url = kwargs.get("url")
    display_text = kwargs.get("display_text", "立即访问")

    if not url:
        raise ValueError("输入参数 'url' 不能为空。")

    # 逻辑核心：返回 button_overrides 字典列表
    # target: "self" 表示锁定当前被点击的这个按钮
    return {
        "new_text": "链接已就绪，请点击下方按钮访问：",
        "button_overrides": [
            {
                "target": "self",
                "text": display_text,
                "type": "url",  # 将按钮类型动态改为 URL 跳转型
                "url": url
            }
        ]
    }
