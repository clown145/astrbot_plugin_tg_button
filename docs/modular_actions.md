# 如何创建模块化动作 (Modular Action)

模块化动作是 1.2.0 版本引入的一种强大的、用于扩展插件功能的标准化方式。它允许您通过在指定的文件夹中添加简单的 Python 文件，来创建新的、可以在 WebUI 中被工作流使用的动作，而无需修改任何插件的核心代码。

本教程将指导您完成创建一个完整模块化动作的全过程。

## 1. 模块化动作是什么？

一个模块化动作本质上就是一个遵循特定规范的 Python (`.py`) 文件。插件在启动或重载时会自动扫描 `data/plugin_data/astrbot_plugin_tg_button/modular_actions/` 目录，并加载所有符合规范的动作文件。

每个动作文件都必须包含两个核心部分：

1.  `ACTION_METADATA`: 一个 Python 字典，用于描述动作的元信息，如 ID、名称、以及它需要哪些输入和会产生哪些输出。
2.  `execute`: 一个异步的 Python 函数 (`async def`)，用于实现动作的具体逻辑。

## 2. 创建与管理模块动作

您可以通过两种主要方式来创建和管理模块动作：

### 方法 A：通过 WebUI (高风险)

> [!CAUTION]
> **高风险功能警告**
> 通过 WebUI 上传 `.py` 文件直接等同于在服务器上执行任意代码，这是一个极度危险的权限。此功能**默认关闭且强烈不推荐开启**。
>
> 如果您完全理解相关风险并决定启用，**必须**在插件配置中为上传 (`webui_upload_auth_token`) 和删除 (`webui_delete_auth_token`) 设置独立的、长而复杂的密码。请参考 `README.md` 中的安全警告部分获取更多信息。

尽管存在风险，对于高级用户来说，通过 WebUI 管理模块动作可能仍然是比较方便的方式。

1.  **导航到模块动作页面**：登录插件 WebUI，在侧边栏找到“模块动作” (Modular Actions) 页面。
2.  **查看与下载**：在此页面，您可以看到所有当前已加载的模块动作。您可以点击“下载”按钮，将现有动作的 `.py` 文件保存到本地，这是一个很好的学习和修改的起点。
3.  **上传新动作**：如果已按安全要求开启上传功能，点击“上传动作”按钮，选择您在本地创建或修改好的 `.py` 文件。文件将被上传到服务器正确的 `modular_actions` 目录中。
4.  **重载插件**：
    > [!IMPORTANT]
    > **上传新动作或修改现有动作后，必须重载插件才能生效！**
    > 请在 AstrBot 的主 WebUI 中找到“插件管理”，然后点击本插件旁边的“重载”按钮。重载后，您的新动作就会出现在 WebUI 的动作列表和工作流编辑器中。

### 方法 B：手动创建文件

如果您熟悉服务器文件系统操作，也可以直接在服务器上创建和编辑动作文件。这种方法的好处是修改后只需重载插件即可，无需上传步骤。

#### 步骤 1: 创建 Python 文件

在您的 AstrBot 数据目录中，找到并进入 `data/plugins/astrbot_plugin_tg_button/modular_actions/` 文件夹。如果该文件夹不存在，您可以手动创建它。

在该文件夹中，创建一个新的 `.py` 文件，例如 `my_action.py`。文件名可以任意，但建议有意义且不以 `_` 开头。

#### 步骤 2: 定义 `ACTION_METADATA`

打开您创建的 `my_action.py` 文件，在文件顶部定义一个名为 `ACTION_METADATA` 的字典。这个字典是动作的“说明书”，告诉插件和 WebUI 如何理解和使用它。

```python
# my_action.py

ACTION_METADATA = {
    # (必填) 动作的唯一标识符，只能包含字母、数字、下划线。这是在工作流中引用此动作的 ID。
    "id": "get_current_time",

    # (选填) 在 WebUI 中显示的可读名称。如果未提供，则使用 ID。
    "name": "获取当前时间",

    # (选填) 在 WebUI 中显示的详细描述。
    "description": "获取服务器的当前时间，并以指定格式返回。",

    # (选填) 定义动作的输入参数列表。
    "inputs": [
        {
            "name": "format_str",          # 参数名
            "type": "string",             # 参数类型 (主要用于 UI 显示)
            "description": "时间的格式化字符串，例如 %Y-%m-%d %H:%M:%S",
            "default": "%Y-%m-%d %H:%M:%S",  # (选填) 参数的默认值
            "placeholder": "%Y-%m-%d %H:%M:%S"  # (选填) 在表单中的提示文字
        },
        {
            "name": "parse_mode",
            "type": "string",
            "description": "选择 Telegram 文本解析模式。",
            "default": "html",
            "enum": ["html", "markdown", "markdownv2", "plain"],  # (选填) 枚举值 -> 渲染为下拉菜单
            "enum_labels": {  # (选填) 下拉菜单中显示的中文标签
                "html": "HTML（默认）",
                "markdown": "Markdown",
                "markdownv2": "MarkdownV2",
                "plain": "纯文本"
            }
        }
    ],

    # (选填) 定义动作的输出变量列表。
    "outputs": [
        {
            "name": "formatted_time",      # 输出变量名
            "type": "string",             # 输出变量类型
            "description": "格式化后的当前时间字符串"
        },
        {
            "name": "timestamp",           # 另一个输出变量名
            "type": "integer",            # 输出变量类型
            "description": "当前的 Unix 时间戳"
        }
    ]
}
```

**`inputs` 详解**：
`inputs` 是一个字典列表，每个字典定义一个输入参数。当在 WebUI 的工作流编辑器中点击此动作节点时，这里定义的输入参数会以表单的形式显示出来，方便用户填写。

-   `name`: 参数的内部名称，在 `execute` 函数中会用到。
-   `type`: 目前主要用于 UI 的展示（文本、数字等标签），不会限制输入类型。
-   `required`: 设为 `True` 时，工作流保存前会提示用户补全该参数。
-   `default`: 如果设置了默认值，在工作流中未提供此参数时，将自动使用该默认值。
-   `placeholder`: 在表单输入框中的浅色提示文字，适合给出格式示例。
-   `enum`: 列出允许的取值数组时，WebUI 会自动将此输入渲染为下拉菜单。
-   `enum_labels`:（可选）为 `enum` 中的每个值提供一个更友好的显示名称。

> 💡 **关于下拉菜单**：只要在参数字典中提供 `enum` 数组即可获得下拉选择器；若想让选项显示中文或解释性文字，可额外提供 `enum_labels` 映射。上述 `parse_mode` 示例就演示了如何在自定义动作中复用当前 WebUI 的“文本解析模式”下拉选择。

**`outputs` 详解**：
`outputs` 也是一个字典列表，它主要用于在 WebUI 中清晰地展示这个动作会产生哪些可供下游节点使用的数据。它就像一份“返回说明”，帮助用户构建工作流。

#### 步骤 3: 实现 `execute` 函数

在 `ACTION_METADATA` 下方，定义一个名为 `execute` 的异步函数。这个函数是动作的核心逻辑所在。

```python
# my_action.py

import time
from datetime import datetime

# ... ACTION_METADATA 定义 ...

async def execute(**kwargs):
    """
    动作的执行逻辑。
    kwargs 会接收所有在 inputs 中定义的、并且在工作流中被传入的参数。
    """
    # 从 kwargs 获取输入参数，如果参数不存在或用户未提供，则使用默认值
    format_str = kwargs.get("format_str", "%Y-%m-%d %H:%M:%S")

    # 执行核心逻辑
    now = datetime.now()
    formatted_time = now.strftime(format_str)
    current_timestamp = int(time.time())

    # 返回一个结果字典
    return {
        # 特殊键: new_text 会在执行后更新 Telegram 消息
        "new_text": f"服务器当前时间是: {formatted_time}",

        # 自定义输出变量: 这里的键名对应 outputs 中定义的 name
        "formatted_time": formatted_time,
        "timestamp": current_timestamp
    }

```

**`execute` 函数要点**：
-   必须是 `async def` 定义的异步函数。
-   它通过 `**kwargs` 接收所有输入参数。您可以使用 `kwargs.get("参数名")` 来安全地获取它们。
-   **必须返回一个字典**。

#### 步骤 4: 理解 `execute` 的返回值

`execute` 函数返回的字典非常关键。它可以包含两种类型的键：

1.  **特殊 UI 控制键**：这些键有特殊含义，用于控制执行后的 Telegram 界面行为。
    -   `new_text: str`: 如果提供，将用此文本更新当前菜单的标题文本。
    -   `next_menu_id: str`: 如果提供，执行后会自动跳转到指定 ID 的菜单。
    -   `notification: dict`: 显示一个短暂的顶部通知。例如 `{"text": "操作成功！"}`。
    -   `button_overrides: list`: 动态修改当前菜单上的按钮。这是一个高级功能。

2.  **自定义输出变量**：字典中任何**不属于**上述特殊键的键值对，都会被视为此动作的输出变量。这些变量可以在工作流中被后续的节点作为输入使用。
    -   在我们的例子中，`"formatted_time": ...` 和 `"timestamp": ...` 就是输出变量。在 WebUI 中，您可以从这个节点的输出端口将它们连接到其他节点的输入端口。

## 3. 加载并使用动作

无论您是通过 WebUI 上传还是手动创建文件，最后一步都是让插件加载它。

保存好您的 `.py` 文件后，**重启 AstrBot 或在 AstrBot 的 WebUI 中重载动态按钮插件**。插件会自动发现并加载您的新动作。

之后，您就可以在动态按钮插件的 WebUI 中，创建一个新的工作流，并在动作列表中找到您刚刚创建的动作，将它拖拽到画布上并开始使用了。
