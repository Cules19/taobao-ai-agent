const messages = document.querySelector("#messages");
const composer = document.querySelector("#composer");
const input = document.querySelector("#message");
const send = document.querySelector("#send");
const reset = document.querySelector("#reset");
const status = document.querySelector("#status");
const favoriteCount = document.querySelector("#favorite-count");
let sessionId = null;
let favoriteIds = [];
let busy = false;

function appendMessage(kind, text) {
  const item = document.createElement("div");
  item.className = `message ${kind}`;
  const label = document.createElement("span");
  label.className = "message-label";
  label.textContent = kind === "user" ? "你" : "选物助手";
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  item.append(label, bubble);
  messages.append(item);
}

function renderProducts(products) {
  if (!products.length) return;
  const grid = document.createElement("div");
  grid.className = "product-grid";
  for (const product of products) {
    const card = document.createElement("article");
    card.className = "product";
    const name = document.createElement("strong");
    name.textContent = `${product.name} · ${product.id}`;
    const facts = document.createElement("p");
    facts.textContent = `¥${product.price} · 销量 ${product.sales} · 好评 ${product.rating}%`;
    const colors = document.createElement("p");
    colors.className = "muted";
    colors.textContent = `颜色：${product.colors.join("、")}`;
    const like = document.createElement("button");
    like.type = "button";
    like.dataset.favorite = product.id;
    like.addEventListener("click", () => sendMessage(`我喜欢这款，请收藏商品 ${product.id}`));
    card.append(name, facts, colors, like);
    grid.append(card);
  }
  messages.append(grid);
}

function updateControls() {
  send.disabled = reset.disabled = busy;
  for (const button of document.querySelectorAll("[data-prompt]")) {
    button.disabled = busy;
  }
  favoriteCount.textContent = favoriteIds.length;
  for (const button of document.querySelectorAll("[data-favorite]")) {
    const saved = favoriteIds.includes(button.dataset.favorite);
    button.textContent = saved ? "已收藏" : "♡ 喜欢";
    button.disabled = busy || saved;
  }
}

async function sendMessage(text) {
  const message = text.trim();
  if (!message || busy) return;
  busy = true;
  input.value = "";
  appendMessage("user", message);
  status.textContent = "正在处理请求，请稍候…";
  updateControls();
  messages.scrollTop = messages.scrollHeight;
  try {
    const response = await fetch("/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message, session_id: sessionId}),
    });
    const result = await response.json();
    if (!response.ok) {
      const detail = typeof result.detail === "string" ? result.detail : "请检查输入后重试。";
      throw new Error(detail);
    }
    sessionId = result.session_id;
    favoriteIds = result.favorite_ids;
    appendMessage("assistant", result.reply);
    renderProducts(result.products);
  } catch (error) {
    appendMessage("error", error.message || "请求失败，请稍后重试。");
    if (!input.value) input.value = message;
  } finally {
    busy = false;
    status.textContent = "准备就绪";
    updateControls();
    messages.scrollTop = messages.scrollHeight;
    input.focus();
  }
}

function startConversation() {
  sessionId = null;
  favoriteIds = [];
  input.value = "";
  messages.replaceChildren();
  appendMessage("assistant", "你好！告诉我想买的商品、预算或使用场景，我来帮你找。这里的商品、优惠和订单都是模拟数据。");
  updateControls();
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});
reset.addEventListener("click", () => {
  startConversation();
  input.focus();
});
for (const button of document.querySelectorAll("[data-prompt]")) {
  button.addEventListener("click", () => sendMessage(button.dataset.prompt));
}
startConversation();
