import asyncio
import json
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def _generate_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@dataclass
class LayoutConfig:
    """按钮在网格布局中的位置和尺寸信息。"""
    row: int = 0
    col: int = 0
    rowspan: int = 1
    colspan: int = 1

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "LayoutConfig":
        if not data:
            return cls()
        return cls(
            row=int(data.get("row", 0)),
            col=int(data.get("col", 0)),
            rowspan=max(1, int(data.get("rowspan", 1))),
            colspan=max(1, int(data.get("colspan", 1))),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WebAppDefinition:
    """定义一个可在按钮中使用的 WebApp。"""
    id: str
    name: str
    kind: str = "external"  # 类型: external(外部) | internal(内部)
    url: str = ""
    source: str = ""  # 当 kind 为 'internal' 时使用
    description: str = ""
    options: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        name: str,
        *,
        kind: str = "external",
        url: str = "",
        source: str = "",
        description: str = "",
        options: Optional[Dict[str, Any]] = None,
        webapp_id: Optional[str] = None,
    ) -> "WebAppDefinition":
        return cls(
            id=webapp_id or _generate_id("webapp"),
            name=name,
            kind=kind,
            url=url,
            source=source,
            description=description,
            options=options or {},
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WebAppDefinition":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            kind=data.get("kind", "external"),
            url=data.get("url", ""),
            source=data.get("source", ""),
            description=data.get("description", ""),
            options=data.get("options", {}) or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "url": self.url,
            "source": self.source,
            "description": self.description,
            "options": self.options,
        }


@dataclass
class ButtonDefinition:
    """定义一个具体的按钮，包括其文本、类型、负载和布局。"""
    id: str
    text: str
    type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    layout: LayoutConfig = field(default_factory=LayoutConfig)

    @classmethod
    def create(
        cls,
        text: str,
        btn_type: str,
        payload: Dict[str, Any],
        *,
        description: str = "",
        layout: Optional[Dict[str, Any]] = None,
        button_id: Optional[str] = None,
    ) -> "ButtonDefinition":
        return cls(
            id=button_id or _generate_id("btn"),
            text=text,
            type=btn_type,
            payload=payload,
            description=description,
            layout=LayoutConfig.from_dict(layout),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ButtonDefinition":
        return cls(
            id=data["id"],
            text=data.get("text", ""),
            type=data.get("type", "command"),
            payload=data.get("payload", {}) or {},
            description=data.get("description", ""),
            layout=LayoutConfig.from_dict(data.get("layout")),
        )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["layout"] = self.layout.to_dict()
        return data


@dataclass
class MenuDefinition:
    """定义一个菜单，它包含一组按钮项和可选的标题。"""
    id: str
    name: str
    header: str = ""
    items: List[str] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        name: str,
        *,
        header: str = "",
        menu_id: Optional[str] = None,
        items: Optional[List[str]] = None,
    ) -> "MenuDefinition":
        return cls(
            id=menu_id or _generate_id("menu"),
            name=name,
            header=header,
            items=list(items or []),
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MenuDefinition":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            header=data.get("header", ""),
            items=list(data.get("items", [])),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ActionDefinition:
    """定义一个可执行的动作，如 HTTP 请求或本地函数调用。"""
    id: str
    name: str
    kind: str
    config: Dict[str, Any] = field(default_factory=dict)
    description: str = ""

    @classmethod
    def create(
        cls,
        name: str,
        kind: str,
        *,
        config: Optional[Dict[str, Any]] = None,
        description: str = "",
        action_id: Optional[str] = None,
    ) -> "ActionDefinition":
        return cls(
            id=action_id or _generate_id("action"),
            name=name,
            kind=kind,
            config=config or {},
            description=description,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionDefinition":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            kind=data.get("kind", "http"),
            config=data.get("config", {}) or {},
            description=data.get("description", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowNodePosition:
    """工作流中节点的可视化位置。"""
    x: float = 0.0
    y: float = 0.0

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowNodePosition":
        return cls(x=data.get("x", 0.0), y=data.get("y", 0.0))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowNode:
    """工作流中的一个节点，代表一个要执行的动作。"""
    id: str
    action_id: str
    position: WorkflowNodePosition
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowNode":
        return cls(
            id=data["id"],
            action_id=data.get("action_id", ""),
            position=WorkflowNodePosition.from_dict(data.get("position", {})),
            data=data.get("data", {}),
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["position"] = self.position.to_dict()
        return d


@dataclass
class WorkflowEdge:
    """工作流中的一条边，连接两个节点的输入和输出。"""
    id: str
    source_node: str
    source_output: str
    target_node: str
    target_input: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowEdge":
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowDefinition:
    """定义一个完整的工作流，包含节点（动作）和边（数据流）。"""
    id: str
    name: str
    description: str = ""
    nodes: Dict[str, WorkflowNode] = field(default_factory=dict)
    edges: List[WorkflowEdge] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkflowDefinition":
        return cls(
            id=data["id"],
            name=data.get("name", data["id"]),
            description=data.get("description", ""),
            nodes={
                node_id: WorkflowNode.from_dict(node_data)
                for node_id, node_data in (data.get("nodes", {}) or {}).items()
            },
            edges=[WorkflowEdge.from_dict(edge_data) for edge_data in data.get("edges", [])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "edges": [edge.to_dict() for edge in self.edges],
        }


@dataclass
class ButtonsModel:
    """插件所有持久化数据的顶层容器。"""
    version: int = 2
    menus: Dict[str, MenuDefinition] = field(default_factory=dict)
    buttons: Dict[str, ButtonDefinition] = field(default_factory=dict)
    actions: Dict[str, ActionDefinition] = field(default_factory=dict)
    web_apps: Dict[str, WebAppDefinition] = field(default_factory=dict)
    workflows: Dict[str, WorkflowDefinition] = field(default_factory=dict)

    def ensure_menu(self, menu: MenuDefinition) -> None:
        if menu.id not in self.menus:
            self.menus[menu.id] = menu

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "menus": {menu_id: menu.to_dict() for menu_id, menu in self.menus.items()},
            "buttons": {btn_id: btn.to_dict() for btn_id, btn in self.buttons.items()},
            "actions": {act_id: act.to_dict() for act_id, act in self.actions.items()},
            "web_apps": {webapp_id: webapp.to_dict() for webapp_id, webapp in self.web_apps.items()},
            "workflows": {workflow_id: workflow.to_dict() for workflow_id, workflow in self.workflows.items()},
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ButtonsModel":
        version = data.get("version", 2)
        menus_source: Dict[str, Any] = data.get("menus", {}) or {}
        buttons_source: Dict[str, Any] = data.get("buttons", {}) or {}
        actions_source: Dict[str, Any] = data.get("actions", {}) or {}
        web_apps_source: Dict[str, Any] = data.get("web_apps", {}) or {}
        workflows_source: Dict[str, Any] = data.get("workflows", {}) or {}
        menus = {menu_id: MenuDefinition.from_dict(menu_dict) for menu_id, menu_dict in menus_source.items()}
        buttons = {btn_id: ButtonDefinition.from_dict(btn_dict) for btn_id, btn_dict in buttons_source.items()}
        actions = {act_id: ActionDefinition.from_dict(act_dict) for act_id, act_dict in actions_source.items()}
        web_apps = {webapp_id: WebAppDefinition.from_dict(webapp_dict) for webapp_id, webapp_dict in web_apps_source.items()}
        workflows = {
            workflow_id: WorkflowDefinition.from_dict(workflow_dict)
            for workflow_id, workflow_dict in workflows_source.items()
        }
        return cls(
            version=version,
            menus=menus,
            buttons=buttons,
            actions=actions,
            web_apps=web_apps,
            workflows=workflows,
        )

    def clone(self) -> "ButtonsModel":
        return ButtonsModel.from_dict(self.to_dict())


class ButtonStore:
    """负责管理插件数据的持久化，处理文件的加载、保存和迁移。"""
    def __init__(self, data_dir: Path, *, logger, default_header: str = "请选择功能"):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logger
        self._default_header = default_header
        self._file_path = self.data_dir / "buttons_v2.json"
        self._legacy_path = self.data_dir / "buttons.json"
        self._lock = asyncio.Lock()
        self._model = self._load()
        self._ensure_defaults()
        self._save()  # 确保启动时文件存在

    @property
    def model(self) -> ButtonsModel:
        return self._model

    def _load(self) -> ButtonsModel:
        if self._file_path.exists():
            try:
                with open(self._file_path, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                return ButtonsModel.from_dict(data)
            except Exception as exc:  # 防御性日志记录
                self._logger.error(f"加载 {self._file_path} 失败，将重新初始化: {exc}")
        legacy_model = self._load_legacy()
        if legacy_model:
            return legacy_model
        return ButtonsModel(
            menus={
                "root": MenuDefinition.create("root", header=self._default_header, menu_id="root"),
            },
            buttons={},
            actions={},
            web_apps={},
        )

    def _load_legacy(self) -> Optional[ButtonsModel]:
        if not self._legacy_path.exists():
            return None
        try:
            with open(self._legacy_path, "r", encoding="utf-8-sig") as fp:
                data = json.load(fp)
        except Exception as exc:
            self._logger.error(f"迁移旧按钮配置失败: {exc}")
            return None
        if not isinstance(data, list):
            self._logger.warning("旧按钮配置不是列表，跳过迁移。")
            return None
        menus: Dict[str, MenuDefinition] = {
            "root": MenuDefinition.create("root", header=self._default_header, menu_id="root"),
        }
        buttons: Dict[str, ButtonDefinition] = {}
        order_row = 0
        for item in data:
            text = item.get("text")
            btn_type = item.get("type")
            value = item.get("value")
            if not text or not btn_type or not value:
                continue
            payload: Dict[str, Any]
            if btn_type == "command":
                payload = {"command": value}
            elif btn_type == "url":
                payload = {"url": value}
            else:
                payload = {"raw": value}
            button = ButtonDefinition.create(
                text=text,
                btn_type=btn_type,
                payload=payload,
                layout={"row": order_row, "col": 0},
            )
            buttons[button.id] = button
            menus["root"].items.append(button.id)
            order_row += 1
        return ButtonsModel(menus=menus, buttons=buttons, actions={}, web_apps={})

    def _ensure_defaults(self) -> None:
        if "root" not in self._model.menus:
            self._model.menus["root"] = MenuDefinition.create("root", header=self._default_header, menu_id="root")
        for menu in self._model.menus.values():
            menu.items = [btn_id for btn_id in menu.items if btn_id in self._model.buttons]
        if not isinstance(self._model.web_apps, dict):
            self._model.web_apps = {}

    def _save(self) -> None:
        try:
            with open(self._file_path, "w", encoding="utf-8") as fp:
                json.dump(self._model.to_dict(), fp, ensure_ascii=False, indent=2)
        except Exception as exc:  # 防御性日志记录
            self._logger.error(f"保存按钮配置失败: {exc}")

    async def get_snapshot(self) -> ButtonsModel:
        async with self._lock:
            return self._model.clone()

    async def modify(self, mutator: Callable[[ButtonsModel], None]) -> ButtonsModel:
        async with self._lock:
            mutator(self._model)
            self._ensure_defaults()
            self._save()
            return self._model.clone()

    async def replace_with(self, new_data: Dict[str, Any]) -> ButtonsModel:
        async with self._lock:
            self._model = ButtonsModel.from_dict(new_data)
            self._ensure_defaults()
            self._save()
            return self._model.clone()

    async def upsert_simple_button(self, text: str, btn_type: str, payload_value: str) -> ButtonDefinition:
        btn_type = btn_type.lower()
        payload: Dict[str, Any]
        if btn_type == "command":
            payload = {"command": payload_value}
        elif btn_type in {"url", "web_app"}:
            payload = {"url": payload_value}
        else:
            payload = {"value": payload_value}

        def mutator(model: ButtonsModel) -> None:
            existing = next((btn for btn in model.buttons.values() if btn.text == text), None)
            target_menu = model.menus.get("root")
            if not target_menu:
                model.menus["root"] = MenuDefinition.create("root", header=self._default_header, menu_id="root")
                target_menu = model.menus["root"]
            if existing:
                existing.type = btn_type
                existing.payload = payload
                if existing.id not in target_menu.items:
                    target_menu.items.append(existing.id)
            else:
                new_button = ButtonDefinition.create(text=text, btn_type=btn_type, payload=payload)
                model.buttons[new_button.id] = new_button
                target_menu.items.append(new_button.id)

        snapshot = await self.modify(mutator)
        for button in snapshot.buttons.values():
            if button.text == text:
                return button
        raise RuntimeError("未能写入按钮配置")

    async def remove_button_by_text(self, text: str) -> bool:
        removed_ids: List[str] = []

        def mutator(model: ButtonsModel) -> None:
            targets = [btn_id for btn_id, btn in model.buttons.items() if btn.text == text]
            if not targets:
                return
            for btn_id in targets:
                removed_ids.append(btn_id)
                model.buttons.pop(btn_id, None)
            for menu in model.menus.values():
                menu.items = [btn_id for btn_id in menu.items if btn_id not in removed_ids]

        await self.modify(mutator)
        return bool(removed_ids)

    def generate_id(self, entity_type: str) -> str:
        prefix_map = {"button": "btn", "menu": "menu", "action": "action", "webapp": "webapp"}
        prefix = prefix_map.get(entity_type, entity_type)
        return _generate_id(prefix)