
# 教程：使用 Cloudflare Worker 反代 Telegram API

本教程将指导您如何使用 Cloudflare Workers 免费创建一个 Telegram API 的反向代理，解决因服务器网络问题导致机器人无法连接到 Telegram 的问题。

## 🎯 解决什么问题？

- 服务器在某些地区（如中国大陆）无法直接访问 `api.telegram.org`。
- 不想在服务器上配置和维护复杂的全局网络代理。

## 🔧 准备工作

1.  一个 Cloudflare 账户。
2.  (强烈推荐) 一个您自己的域名，并已将其 NS (域名服务器) 托管到 Cloudflare。

---

## 🚀 操作步骤

### 第 1 步：创建 Cloudflare Worker

1.  登录到您的 Cloudflare 仪表板。
2.  在左侧菜单中，转到 **Workers & Pages**。
3.  点击 **Create Application** (创建应用程序)，然后选择 **Create Worker** (创建 Worker)。
4.  为您的 Worker 指定一个名称 (例如 `tg-proxy`)，然后点击 **Deploy** (部署)。

### 第 2 步：部署反代代码

1.  进入您刚刚创建的 Worker，点击 **Quick Edit** (快速编辑)。
2.  删除编辑器中所有默认代码，然后将 `worker.js` 文件中的代码完整地复制粘贴进去。
3.  点击 **Save and Deploy** (保存并部署)。

### 第 3 步：绑定自定义域名 (关键步骤)

Cloudflare 提供的默认 `workers.dev` 域名在国内通常无法访问，因此**强烈建议**绑定您自己的域名。

1.  在您的 Worker 管理页面，切换到 **Triggers** (触发器) 选项卡。
2.  在 **Custom Domains** (自定义域) 部分，点击 **Add Custom Domain** (添加自定义域)。
3.  输入一个您想使用的子域名 (例如 `tg-api.yourdomain.com`)，然后点击 **Add Domain**。Cloudflare 会自动为您处理 DNS 解析记录。

### 第 4 步：修改 AstrBot 插件配置

现在，您需要告诉 AstrBot 使用您的反代地址而不是官方地址。

1.  进入 AstrBot 的 WebUI。
2.  在“平台适配器”中找到并打开 **Telegram 平台** 的配置。
3.  修改以下两个 API 地址，将其中的域名替换为您刚刚绑定的**自定义域名**：

    -   **`API_URL`**:
        -   **原始值**: `https://api.telegram.org/bot`
        -   **修改为**: `https://tg-api.yourdomain.com/bot`  (请替换成您自己的域名)

    -   **`FILE_API_URL`**:
        -   **原始值**: `https://api.telegram.org/file/bot`
        -   **修改为**: `https://tg-api.yourdomain.com/file/bot` (请替换成您自己的域名)

4.  保存配置并重启 AstrBot。

至此，您的机器人所有与 Telegram API 的通信都将通过您自己的 Cloudflare 反代服务器进行，解决了网络访问问题。
