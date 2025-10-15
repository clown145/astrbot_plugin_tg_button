# local_actions/cache_from_url.py

import os
import uuid
from typing import TYPE_CHECKING, Dict, Any
from urllib.parse import urlparse

import httpx
import aiofiles

from astrbot.api.star import StarTools

if TYPE_CHECKING:
    from ..main import DynamicButtonFrameworkPlugin


# --- 动作元数据 ---
ACTION_METADATA = {
    "id": "cache_from_url",
    "name": "从 URL 缓存文件",
    "description": "下载一个文件并将其临时存储，返回本地文件路径以供工作流中的其他节点使用。",
    "inputs": [
        {
            "name": "url",
            "type": "string",
            "required": True,
            "description": "要下载的文件的 URL。",
        },
        {
            "name": "filename",
            "type": "string",
            "required": False,
            "description": "可选的文件名。如果留空，将自动生成一个。",
        },
    ],
    "outputs": [
        {
            "name": "file_path",
            "type": "string",
            "description": "文件在服务器上的绝对路径。",
        },
    ],
}


# --- 动作执行逻辑 ---
async def execute(**kwargs) -> Dict[str, Any]:
    """
    下载文件并返回其本地路径。
    """
    url = kwargs.get("url")
    if not url:
        raise ValueError("输入参数 'url' 不能为空。")

    # 1. 确定并创建临时目录
    plugin_data_dir = StarTools.get_data_dir("astrbot_plugin_tg_button")
    temp_dir = os.path.join(plugin_data_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    # 2. 确定文件名
    filename = kwargs.get("filename")
    if not filename:
        try:
            # 尝试从 URL 路径中提取
            parsed_path = urlparse(url).path
            filename = os.path.basename(parsed_path)
            if not filename:  # 如果路径为空或以 '/' 结尾
                raise ValueError
        except Exception:
            # 失败则生成 UUID
            filename = str(uuid.uuid4())

    file_path = os.path.join(temp_dir, filename)

    # 3. 下载文件
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, follow_redirects=True, timeout=30)
            response.raise_for_status()  # 确保请求成功

            # 4. 异步写入文件
            async with aiofiles.open(file_path, "wb") as f:
                await f.write(response.content)

        except httpx.RequestError as exc:
            raise RuntimeError(f"下载文件时发生网络错误: {exc}")
        except Exception as exc:
            raise RuntimeError(f"处理文件时发生未知错误: {exc}")

    # 5. 返回结果，包括文件路径和需要清理的标记
    return {
        "file_path": file_path,  # 这是动作的输出
        "temp_files_to_clean": [file_path],  # 这是给 ActionExecutor 的指令
    }
