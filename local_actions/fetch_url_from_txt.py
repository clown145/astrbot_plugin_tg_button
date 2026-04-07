import httpx
from typing import Dict, Any

# --- 动作元数据 ---
ACTION_METADATA = {
    "id": "fetch_url_from_txt",
    "name": "从 TXT 获取目标 URL",
    "description": "访问一个 TXT 文件链接，读取其文本内容并作为 URL 变量输出。",
    "inputs": [
        {
            "name": "txt_file_url",
            "type": "string",
            "required": True,
            "description": "存放目标 URL 的 TXT 文件链接。",
        }
    ],
    "outputs": [
        {
            "name": "extracted_url",
            "type": "string",
            "description": "从 TXT 文件中读取到的 URL 字符串。",
        }
    ],
}

# --- 动作执行逻辑 ---
async def execute(**kwargs) -> Dict[str, Any]:
    """
    读取远程 TXT 文件内容并返回。
    """
    txt_file_url = kwargs.get("txt_file_url")
    if not txt_file_url:
        raise ValueError("输入参数 'txt_file_url' 不能为空。")

    async with httpx.AsyncClient() as client:
        try:
            # 仿照 cache_from_url.py 的下载逻辑
            response = await client.get(txt_file_url, follow_redirects=True, timeout=10)
            response.raise_for_status()
            
            # 获取文本内容并去除首尾空格/换行
            extracted_url = response.text.strip()
            
            if not extracted_url:
                raise ValueError("TXT 文件内容为空。")

        except httpx.RequestError as exc:
            raise RuntimeError(f"访问 TXT 文件时发生网络错误: {exc}")
        except Exception as exc:
            raise RuntimeError(f"处理 TXT 内容时发生错误: {exc}")

    # 返回结果，extracted_url 将作为变量供后续节点使用
    return {
        "extracted_url": extracted_url
    }