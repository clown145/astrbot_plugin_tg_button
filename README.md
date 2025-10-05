
<div align="center">

# astrbot_plugin_tg_button

_✨ 为你的 AstrBot 在 Telegram 中添加交互式指令按钮 ✨_  

[![License](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-v3.4%2B-orange.svg)](https://github.com/AstrBotDevs/AstrBot)
[![GitHub](https://img.shields.io/badge/作者-clown145-blue)](https://github.com/clown145)

</div>

## 📖 功能简介

本插件是为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 设计的一款 Telegram 平台专属的增强工具。它允许管理员通过简单的指令，动态地创建和管理一个可视化的内联按钮菜单。用户只需点击按钮，即可轻松触发预设的指令或打开链接，极大地提升了机器人的交互体验和易用性。

- **动态按钮管理**：无需重启或修改代码，通过指令即可实时添加、修改或删除菜单按钮。
- **两种按钮类型**：
    1.  **指令按钮**：点击后，在后台替用户执行一条预设的 AstrBot 指令。
    2.  **网址按钮**：点击后，引导用户打开一个指定的 URL 链接。
- **权限控制**：可以配置只有管理员才能管理按钮，确保菜单的安全性。
- **平台专属**：深度集成 `python-telegram-bot` 库，专为 Telegram 平台优化。
- **配置灵活**：调出菜单的指令名称、管理按钮的权限级别均可在 WebUI 中自定义。

---

## ⚠️ 重要前置：平台与依赖

1.  **Telegram 平台限定**：本插件的功能**仅在 Telegram 平台**下生效。在其他平台（如 QQ、Discord 等）调用相关指令不会产生任何效果。

2.  **依赖库安装**：插件需要 `python-telegram-bot` 库来创建和处理按钮。通常 AstrBot 的 Telegram 适配器会自带此依赖。如果您的环境缺失，请在 AstrBot 环境中执行以下命令安装：
    ```bash
    pip install python-telegram-bot
    ```

---

## 📦 插件安装

- **方式一 (推荐)**: 在 AstrBot 的插件市场搜索 `astrbot_plugin_tg_button`，点击安装，等待完成即可。

- **方式二 (手动)**: 若安装失败，可尝试克隆源码。
  ```bash
  # 进入 AstrBot 插件目录
  cd /path/to/your/AstrBot/data/plugins

  # 克隆仓库 (请替换为您的仓库地址)
  git clone https://github.com/clown145/astrbot_plugin_tg_button.git

  # 重启 AstrBot
  ```

---

## ⚙️ 插件配置

安装后，在 AstrBot 的 WebUI 找到本插件并进入配置页面。配置项非常简单：

| 配置项 | 说明 | 默认值 |
| :--- | :--- | :--- |
| **菜单指令名** | 用于调出按钮菜单的指令，**无需填写斜杠 `/`**。 | `menu` |
| **绑定权限** | 能够使用 `/bind` 和 `/unbind` 指令的最低权限。可选值为 `admin` (管理员) 或 `user` (所有用户)。 | `admin` |

---

## ⌨️ 使用说明

### 命令表

#### 按钮管理 (需要相应权限)

| 命令格式 | 别名 | 说明 |
| :--- | :--- | :--- |
| `/bind <按钮文字> <类型> <值>` | `/绑定` | 创建或更新一个按钮。<br>- **按钮文字**: 显示在按钮上的文本，例如 `查看帮助`。<br>- **类型**: `指令` (或 `command`) / `网址` (或 `url`)。<br>- **值**: 若类型为`指令`，则为要执行的指令名(不带`/`)；若为`网址`，则为完整的URL。 |
| `/unbind <按钮文字>` | `/解绑` | 删除一个按钮。<br>- **按钮文字** 必须与要删除的按钮完全一致。 |

#### 用户功能

| 命令 | 说明 |
| :--- | :--- |
| `/<您配置的菜单指令>` | 在聊天中显示所有已创建的按钮菜单。默认是 `/menu`。|

### 💡 典型使用流程

假设您是管理员，并且保持默认配置 (`menu_command` 为 `menu`, `bind_permission` 为 `admin`)。

1.  **安装与配置**：完成插件安装，并根据需要调整配置后保存。

2.  **创建第一个按钮 (指令类型)**：
    您希望创建一个名为“获取帮助”的按钮，点击后触发 `/help` 指令。
    -   **发送指令**：
        ```
        /bind 获取帮助 指令 help
        ```
    -   机器人会回复 `✅ 按钮 '获取帮助' 已成功绑定！`

3.  **创建第二个按钮 (网址类型)**：
    您希望创建一个名为“访问官网”的按钮，点击后打开 AstrBot 的 GitHub 页面。
    -   **发送指令**：
        ```
        /bind 访问官网 网址 https://github.com/AstrBotDevs/AstrBot
        ```
    -   机器人会回复 `✅ 按钮 '访问官网' 已成功绑定！`

4.  **调出并使用菜单**：
    现在，任何用户（包括您自己）都可以在聊天中调出这个菜单。
    -   **发送指令**：
        ```
        /menu
        ```
    -   机器人会发送一条消息，下方附带两个内联按钮：`[ 获取帮助 ]` 和 `[ 访问官网 ]`。
    -   点击 **[ 获取帮助 ]**，机器人会像收到 `/help` 指令一样进行回复。
    -   点击 **[ 访问官网 ]**，Telegram 会提示您是否要打开 `https://github.com/AstrBotDevs/AstrBot` 这个链接。

5.  **修改按钮**：
    您发现“获取帮助”按钮触发的指令应该是 `plugin_help` 而不是 `help`。只需使用 `/bind` 命令覆盖即可。
    -   **发送指令**：
        ```
        /bind 获取帮助 指令 plugin_help
        ```
    -   机器人会回复绑定成功，现在点击该按钮将触发 `/plugin_help`。

6.  **删除按钮**：
    您决定不再需要“访问官网”这个按钮了。
    -   **发送指令**：
        ```
        /unbind 访问官网
        ```
    -   机器人会回复 `🗑️ 按钮 '访问官网' 已成功解绑！`
    -   再次使用 `/menu`，将只看到“获取帮助”按钮。

## 📝 开发说明
本插件的开发过程得到了 AI 的大量协助，如果代码或功能中存在任何不妥之处，敬请谅解并通过 Issue 提出，感谢您的支持！