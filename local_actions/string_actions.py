ACTION_METADATA = {
    "id": "concat_strings",
    "name": "拼接字符串",
    "description": "将两个字符串拼接在一起。",
    "inputs": [
        {"name": "string_a", "type": "string", "description": "第一个字符串。"},
        {"name": "string_b", "type": "string", "description": "第二个字符串。"},
    ],
    "outputs": [{"name": "result", "type": "string", "description": "拼接后的结果。"}],
}


async def execute(string_a: str, string_b: str) -> dict:
    """拼接两个字符串并返回结果。"""
    concatenated_string = f"{string_a}{string_b}"

    # 返回值必须是字典，其键和 outputs 中的 name 匹配
    # 还可以包含一个特殊的 new_text 键，用于在 Telegram 中直接显示最终结果
    return {"result": concatenated_string}
