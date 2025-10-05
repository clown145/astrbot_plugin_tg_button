const TG_HOST = "api.telegram.org";

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request))
})

async function handleRequest(request) {
  // 1. 复制原始请求的 URL
  const url = new URL(request.url);

  // 2. 将 URL 的主机名（hostname）更改为 Telegram API 的主机名
  url.hostname = TG_HOST;

  // 3. 创建一个新的请求，除了主机名被修改外，
  //    其他所有内容（如路径、方法、请求头、请求体）都与原始请求完全相同。
  const modifiedRequest = new Request(url, request);

  // 4. 将修改后的请求发送到 Telegram API，并直接返回它的响应
  return fetch(modifiedRequest);
}
