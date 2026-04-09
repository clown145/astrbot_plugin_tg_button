
<div align="center">

# astrbot_plugin_tg_button

_✨ 为 AstrBot 在 Telegram 中添加交互式按钮的插件，现已更新 WebUI 以方便管理。 ✨_

[![Version](https://img.shields.io/badge/Version-1.3.4-blue.svg)](https://github.com/clown145/astrbot_plugin_tg_button)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-v4.0%2B-orange.svg)](https://github.com/AstrBotDevs/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-clown145-blue)](https://github.com/clown145)
![Stone Badge](https://stone.professorlee.work/api/stone/clown145/astrbot_plugin_tg_button)

</div>

## 📜 更新日志

欲查看详细的项目更新记录，请访问：**[CHANGELOG.md](./CHANGELOG.md)**

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
        *   **类型**: 选择 `子菜单 (Submenu)`
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

#### 🔒 安全警告：保护您的 WebUI 与模块化动作

WebUI 拥有强大的功能，可以配置能够执行服务器端逻辑的“动作 (Action)”按钮，甚至上传自定义代码（模块化动作）。因此，保护对 WebUI 的访问至关重要。

> [!WARNING]
> **强烈建议不要常态化开启 WebUI！**
> 为了安全和节省系统资源，建议仅在需要配置按钮时开启 WebUI，完成后立即在插件配置中将 `webui_enabled` 设置回 `false`。

> [!CAUTION]
> **关于模块化动作上传功能的额外警告**
> 1.  **高风险功能**：通过 WebUI 上传 `.py` 文件作为模块化动作的功能，相当于允许通过网页直接在您的服务器上部署和执行代码。这是一个非常危险的权限。
> 2.  **默认关闭且不推荐开启**：出于安全考虑，此功能默认是禁用的。我们强烈不推荐普通用户开启此功能。
> 3.  **强制密码保护**：如果您确切地知道风险并决定启用它，**您必须在插件配置中为上传 (`webui_upload_auth_token`) 和删除 (`webui_delete_auth_token`) 操作设置一个长而复杂的、不同于主 WebUI 密钥的密码**。否则，任何能够访问您 WebUI 的人都有可能上传恶意代码并控制您的服务器。

> [!IMPORTANT]
> **务必为 WebUI 设置访问密钥！**
> 如果您需要开启 WebUI（即使是临时），特别是当您将端口暴露给公网（`webui_host` 设置为 `0.0.0.0`）时，**必须**在插件配置中设置一个长而复杂的 `webui_auth_token`。

---

## 📖 深入了解高级功能

我们为新功能准备了详细的指南文档，帮助你更好地使用本插件：

*   **[✨ (新) 工作流 (Workflow) 功能详解](./docs/workflows.md)**
*   **[🧩 (新) 如何创建模块化动作](./docs/modular_actions.md)**
*   **[📄 动作 (Action) 按钮使用指南](./docs/action_buttons.md)**
*   **[🌐 WebApp 按钮使用指南](./docs/webapp_buttons.md)**
*   **[🔗 Telegram `tg://` 协议链接大全](./docs/tg_links.md)**
*   **[⚙️ 按钮类型参考指南](./docs/button_types.md)**
---

## ⌨️ 关于旧版指令的说明

旧版的 `/bind` 和 `/unbind` 指令已在 `1.2.0` 版本中被**完全移除**，以鼓励用户转向功能更强大、更安全的 WebUI。

所有按钮和菜单的管理现在都应通过 **WebUI** 完成。

---

## 📝 开发说明

本插件的开发过程得到了 AI 的大量协助，如果代码或功能中存在任何不妥之处，敬请谅解并通过 Issue 提出，感谢您的支持！


