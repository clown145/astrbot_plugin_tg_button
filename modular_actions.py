import asyncio
import importlib.util
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ModularAction:
    """代表一个从文件中加载并经过验证的模块化动作。"""
    id: str
    name: str
    description: str
    inputs: List[Dict[str, Any]]
    outputs: List[Dict[str, Any]]
    execute: Callable[..., Any] # 异步的 execute 函数
    source_file: Path


class ModularActionRegistry:
    """扫描、加载并管理文件中的模块化动作。"""

    def __init__(self, logger, actions_dir: Path):
        self._logger = logger
        self._actions_dir = actions_dir
        self._actions: Dict[str, ModularAction] = {}

    def get(self, action_id: str) -> Optional[ModularAction]:
        """根据 ID 获取已加载的模块化动作。"""
        return self._actions.get(action_id)

    def get_all(self) -> List[ModularAction]:
        """获取所有已加载的模块化动作。"""
        return list(self._actions.values())

    async def scan_and_load_actions(self):
        """扫描配置的目录中的 .py 文件，并将它们作为模块化动作加载。"""
        actions_dir = self._actions_dir
        self._actions.clear()

        # 确保目录存在，如果不存在则创建。
        if not actions_dir.is_dir():
            self._logger.info(f"模块化动作目录 {actions_dir} 不存在，将自动创建。")
            try:
                actions_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                self._logger.error(f"创建模块化动作目录失败: {e}")
                return

        self._logger.info(f"开始扫描模块化动作目录: {actions_dir}")
        for file_path in actions_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue  # 跳过 __init__.py 和其他私有文件

            try:
                # 从文件路径动态加载模块
                spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
                if not spec or not spec.loader:
                    raise ImportError(f"无法为 {file_path} 创建模块规范。")

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # 验证加载的模块
                metadata = getattr(module, "ACTION_METADATA", None)
                execute_func = getattr(module, "execute", None)

                if not isinstance(metadata, dict):
                    raise ValueError("未找到或 ACTION_METADATA 不是一个字典。")
                if not callable(execute_func) or not inspect.iscoroutinefunction(execute_func):
                    raise ValueError("未找到或 execute 不是一个 async 函数。")

                action_id = metadata.get("id")
                if not action_id or not isinstance(action_id, str):
                     raise ValueError("ACTION_METADATA 中缺少 'id' 或 'id' 类型不正确。")

                if action_id in self._actions:
                    self._logger.warning(f"动作 ID '{action_id}' 冲突。文件 '{file_path}' 将覆盖来自 '{self._actions[action_id].source_file}' 的动作。")

                loaded_action = ModularAction(
                    id=action_id,
                    name=metadata.get("name", action_id),
                    description=metadata.get("description", ""),
                    inputs=metadata.get("inputs", []),
                    outputs=metadata.get("outputs", []),
                    execute=execute_func,
                    source_file=file_path,
                )
                self._actions[action_id] = loaded_action
                self._logger.info(f"成功加载模块化动作 '{action_id}' 从 {file_path.name}")

            except Exception as e:
                self._logger.error(f"加载模块化动作文件 {file_path.name} 失败: {e}", exc_info=True)

        self._logger.info(f"模块化动作扫描完成。共加载 {len(self._actions)} 个动作。")
