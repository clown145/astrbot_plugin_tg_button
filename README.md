
<div align="center">

# astrbot_plugin_tg_button

_✨ 为 AstrBot 在 Telegram 中添加交互式按钮的插件，现已更新 WebUI 以方便管理。 ✨_

[![Version](https://img.shields.io/badge/Version-1.1.0-blue.svg)](https://github.com/clown145/astrbot_plugin_tg_button)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-v4.0%2B-orange.svg)](https://github.com/AstrBotDevs/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-clown145-blue)](https://github.com/clown145)

</div>

## 主要更新 (V1.1.0)

此版本主要引入了一个**可视化 Web 管理界面 (WebUI)**，用于替代旧版的指令式管理，并增加了多项新功能以支持更复杂的交互。

*   **💻 可视化 WebUI**: 在浏览器中通过拖拽方式直观地管理按钮、菜单和布局。
*   **🚀 新增“动作 (Action)”系统**: 让按钮能够调用外部 API、解析数据并动态更新消息。(可能不完善，已测试)
*   **🧩 新增按钮类型**: 支持**子菜单**、**WebApp** 和**返回**等多种新类型。
*   **🌐 WebApp 集成**: 直接在 Telegram 内部无缝打开网页应用。（可能不完善，未测试）
*   **📜 多菜单支持**: 可创建多个相互链接的菜单，构建导航流程。

---

## 📦 插件安装

*   **方式一 (推荐)**: 在 AstrBot 的插件市场搜索 `astrbot_plugin_tg_button`，点击安装即可。

*   **方式二 (手动)**:
    ```bash
    # 进入 AstrBot 插件目录
    cd /path/to/your/AstrBot/data/plugins
    # 克隆仓库
    git clone https://github.com/clown145/astrbot_plugin_tg_button.git
    # 重启 AstrBot
    ```

---

## ⚙️ 插件配置

安装并重启 AstrBot 后，在 WebUI 找到本插件并进入“管理”页面进行配置。

| 配置项 | 说明 | 默认值 |
| :--- | :--- | :--- |
| `menu_command` | 用于调出根菜单的指令名 (无需 `/`)。 | `menu` |
| `menu_header_text` | 调出菜单时，按钮上方显示的默认提示文字。 | `请选择功能` |
| `webui_enabled` | **(核心)** 是否启用插件自带的按钮管理 WebUI。 | `false` |
| `webui_port` | WebUI 服务监听的端口号。 | `17861` |
| `webui_host` | WebUI 服务监听的地址。 `127.0.0.1` 仅本机可访问。 | `127.0.0.1` |
| `webui_exclusive` | 启用 WebUI 时是否独占插件，开启后将暂停指令与回调功能。 | `true` |
| `webui_auth_token` | (可选) 访问 WebUI 时需要携带的认证 Token，若为空则不校验。 | `""` |

---

## 🖥️ 使用 WebUI 进行配置

现在，所有复杂的按钮和菜单管理都推荐通过 WebUI 完成。

1.  在插件配置中，将 `webui_enabled` 设置为 `true` 并保存。
2.  在浏览器中访问 `http://<webui_host>:<webui_port>` (默认为 **`http://127.0.0.1:17861`**)。
3.  界面分为左右两栏：左侧是**菜单列表**，右侧是**未分配的按钮**。

#### 典型使用流程：创建子菜单与返回按钮

以下步骤将演示如何创建一个名为“实用工具”的子菜单，并为其添加一个返回主菜单的按钮。

1.  **创建子菜单**:
    *   在左侧“菜单 (Menus)”区域，点击 **`新增菜单`**。
    *   在新出现的菜单 `menu_xxxx` 中，将其**名称**修改为 `实用工具`。记下它的 ID，例如 `menu_abc123`。

2.  **创建返回按钮**:
    *   在右侧“未分配的按钮”区域，点击 **`创建新按钮`**。
    *   在弹出的窗口中：
        *   **显示文本**: `返回上一级`
        *   **类型**: 选择 `返回 (Back)`
        *   **目标菜单**: 选择 `root` (这是主菜单的 ID)
    *   点击 **`创建按钮`**。

3.  **创建入口按钮**:
    *   再次点击 **`创建新按钮`**。
    *   在弹出的窗口中：
        *   **显示文本**: `实用工具`
        *   **类型**: 选择 `子菜单 (Submenu)`
        *   **目标菜单**: 选择刚刚创建的 `实用工具 (menu_abc123)`
    *   点击 **`创建按钮`**。

4.  **组合布局**:
    *   使用鼠标，将右侧的 `返回上一级` 按钮**拖拽**到左侧 `实用工具` 菜单的布局网格中。
    *   同样，将右侧的 `实用工具` 按钮**拖拽**到 `root` (主菜单) 的布局网格中。

5.  **保存**:
    *   确认布局无误后，点击页面右上角的 **`保存全部`** 按钮。现在，你在 Telegram 中使用 `/menu` 就可以看到效果了。

#### 🌐 对外开放端口

如需从其他设备访问 WebUI，可将 `webui_host` 设置为 `0.0.0.0`。

> **安全提示**: 当对外开放端口时，**强烈建议**在配置中设置一个复杂的 `webui_auth_token`，以防止未授权的访问。

#### 🔒 使用建议

为了安全和节省系统资源，建议在不使用 WebUI 时，将 `webui_enabled` 选项设置回 `false`。

---

## 📖 深入了解高级功能

我们为新功能准备了详细的指南文档，帮助你更好地使用本插件：

*   **[📄 动作 (Action) 按钮使用指南](./md/action_buttons.md)**
*   **[🌐 WebApp 按钮使用指南](./md/webapp_buttons.md)**
*   **[🔗 Telegram `tg://` 协议链接大全](./md/tg_links.md)**
*   **[⚙️ 按钮类型参考指南](./md/button_types.md)**
---

## ⌨️ 关于旧版指令的说明

旧版的 `/bind` 和 `/unbind` 指令在 `1.1.0` 版本中**仍然可用**，但它们的功能有限：
*   仅能创建简单的**指令 (command)** 和**链接 (url)** 类型按钮。
*   无法管理动作、子菜单、WebApp 等高级功能，也无法进行精细的布局调整。
*   所有通过指令创建的按钮都会被添加到 `root` 菜单的末尾。

**结论：对于新功能和布局管理，请使用 WebUI。**

---

## 📝 开发说明

本插件的开发过程得到了 AI 的大量协助，如果代码或功能中存在任何不妥之处，敬请谅解并通过 Issue 提出，感谢您的支持！
