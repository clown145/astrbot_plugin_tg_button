
# 动作 (Action) 按钮使用指南

欢迎来到插件最的功能之一：**动作按钮**。（目前似乎不够完善，有建议欢迎提出）

与只能执行预设指令或打开链接的普通按钮不同，动作按钮赋予了你的机器人与外部世界进行动态交互的能力。你可以用它来：

*   调用任何公开的 API (例如：天气、新闻、汇率)。
*   从你的网站或服务获取数据并展示给用户。
*   根据用户的点击，动态更新消息内容和按钮布局。
*   实现简单的逻辑，例如查询数据库、触发 Webhook 等。

简而言之，**动作按钮是连接你的 Telegram 机器人和互联网的桥梁**。

## 核心概念

一个“动作”主要由三部分构成：**请求 (Request)**、**解析 (Parse)** 和 **渲染 (Render)**。这三部分都定义在动作的 `config` JSON 中。



1.  **请求 (Request)**: 当用户点击按钮时，机器人会根据你的配置，向一个指定的 URL 发起一个 HTTP 请求。你可以自定义请求的方法 (GET, POST)、请求头 (Headers) 和请求体 (Body)。

2.  **解析 (Parse)**: 机器人收到 API 的响应后（通常是 JSON 格式），会根据你的配置，从中提取出需要的数据。例如，从一堆天气数据中只提取出“温度”和“天气状况”。提取出的数据可以存为临时**变量 (variables)**，供下一步使用。

3.  **渲染 (Render)**: 最后，机器人会使用上一步解析出的数据，通过一个**模板 (template)** 来生成一条新的消息，并用它来更新用户点击时所在的消息。

## 模板与变量 (Jinja2)

“动作”功能的核心是 **Jinja2 模板引擎**。它允许你在配置的各个部分（如 URL、请求体、返回消息模板等）中嵌入变量和简单的逻辑。

模板变量使用双花括号 `{{ }}` 包裹。例如 `{{ user.name }}`。

在一个动作的执行流程中，你可以随时使用以下核心变量：

| 变量名 | 类型 | 描述 |
| :--- | :--- | :--- |
| `runtime` | 对象 | **最常用**。包含触发该动作的运行时信息，如：<br>- `runtime.chat_id`: 聊天 ID<br>- `runtime.user_id`: 用户 ID<br>- `runtime.username`: 用户名<br>- `runtime.full_name`: 用户全名 |
| `button` | 对象 | 当前被点击的按钮的完整定义。 |
| `menu` | 对象 | 当前按钮所在的菜单的完整定义。 |
| `response` | 对象 | **API 响应对象**。在“解析”和“渲染”阶段可用。<br>- `response.status_code`: HTTP 状态码 (如 200)<br>- `response.json`: **最常用**，API 返回的 JSON 数据<br>- `response.text`: API 返回的原始文本 |
| `extracted` | 任意 | 通过 `parse.extractor` 提取出的主数据。 |
| `variables` | 对象 | 你在 `parse.variables` 中定义的所有自定义变量的集合。 |

## Step-by-Step 实例：创建一个天气查询按钮

接下来，我们将通过一个完整的例子，带你创建一个可以查询实时天气的按钮。我们将使用一个免费的、无需注册的天气 API：`wttr.in`。

### 第 1 步：在 WebUI 中创建新动作

1.  进入插件的 WebUI，切换到 **"动作 (Actions)"** 标签页。
2.  点击 **"新增动作"** 按钮。一个新的动作编辑框会出现。
3.  为你的动作命名，例如 `获取天气`，描述可以填写 `调用 wttr.in API 获取天气`。
4.  将下方 **配置 (JSON)** 文本框的内容替换为以下代码：

```json
{
  "request": {
    "method": "GET",
    "url": "https://wttr.in/beijing?format=j1"
  },
  "parse": {
    "variables": [
      {
        "name": "city",
        "type": "template",
        "template": "{{ response.json.nearest_area[0].areaName[0].value }}"
      },
      {
        "name": "temp",
        "type": "template",
        "template": "{{ response.json.current_condition[0].temp_C }}"
      },
      {
        "name": "weather_desc",
        "type": "template",
        "template": "{{ response.json.current_condition[0].weatherDesc[0].value }}"
      }
    ]
  },
  "render": {
    "template": "🏙️ 城市: {{ variables.city }}\n🌡️ 当前温度: {{ variables.temp }}°C\n☁️ 天气状况: {{ variables.weather_desc }}\n\n更新于: {{ response.json.current_condition[0].localObsDateTime }}"
  }
}
```

5.  暂时**不要**点击“保存全部”，我们先来理解一下这段 JSON 的含义。

    *   `request`: 我们向 `https://wttr.in/beijing?format=j1` 这个 URL 发送一个 GET 请求。`?format=j1` 参数会告诉服务器返回 JSON 格式的数据。
    *   `parse`: 我们定义了三个变量 `city`, `temp`, `weather_desc`。
        *   它们都使用 `template` 类型，意味着它们的值是通过 Jinja2 模板从 `response.json` (API 返回的 JSON) 中获取的。
        *   例如 `{{ response.json.current_condition[0].temp_C }}` 就是在多层级的 JSON 数据中，取出当前气温的值。
    *   `render`:
        *   `template` 定义了最终要显示给用户的消息格式。
        *   我们使用了 `{{ variables.city }}`、`{{ variables.temp }}` 等来引用刚刚在 `parse` 步骤中定义的变量，将它们嵌入到一句话中。
        *   我们也可以直接使用 `response` 变量，如 `{{ response.json.current_condition[0].localObsDateTime }}` 来获取观测时间。

### 第 2 步：创建按钮并链接动作

1.  切换到 **"菜单与布局"** 标签页。
2.  在右侧的 **"未分配的按钮"** 区域，点击 **"创建新按钮"**。
3.  在弹出的编辑窗口中：
    *   **显示文本**: 填写 `查询天气`。
    *   **类型**: 选择 `动作 (action)`。
    *   **动作**: 在下拉菜单中选择我们刚刚创建的 `获取天气` 动作。
4.  点击 **"创建按钮"**。

### 第 3 步：将按钮添加到菜单并保存

1.  你会看到 "查询天气" 按钮出现在了 "未分配的按钮" 区域。
2.  用鼠标 **长按并拖拽** 这个按钮到左侧 `root` 菜单下的任意一个虚线框（行）中。
3.  一切就绪！点击页面右上角的 **"保存全部"** 按钮。

### 第 4 步：在 Telegram 中测试

现在，回到你的 Telegram 聊天，发送 `/menu` 指令。你会看到你刚刚添加的 "查询天气" 按钮。

点击它，消息应该会立刻被更新为北京的实时天气情况！

---

恭喜！你已经成功创建并使用了一个动作按钮。这只是一个开始，你可以尝试修改 URL 中的城市，或者寻找其他有趣的 API 来进行对接。动作按钮的潜力只受限于你的想象力。