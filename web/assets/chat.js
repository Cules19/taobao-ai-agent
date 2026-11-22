const messages = document.querySelector("#messages");
const composer = document.querySelector("#composer");
const input = document.querySelector("#message");
const send = document.querySelector("#send");
const reset = document.querySelector("#reset");
const status = document.querySelector("#status");
const favoriteCount = document.querySelector("#favorite-count");
const mobileCount = document.querySelector("#mobile-count");
const welcome = document.querySelector("#welcome");
const viewport = document.querySelector("#viewport");
const historyList = document.querySelector("#history");
const idleStatus = "Enter 发送 · Shift + Enter 换行";
let sessionId = null;
let favoriteIds = [];
let busy = false;

async function api(path, settings = {}) {
  const response = await fetch(path, {signal: AbortSignal.timeout(125000), ...settings});
  if (response.status === 204) return null;
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(typeof data.detail === "string" ? data.detail : "请求未完成，请稍后重试。");
    error.statusCode = response.status;
    throw error;
  }
  return data;
}

function scrollLatest() {
  if (window.matchMedia("(max-width:620px)").matches) {
    messages.lastElementChild?.scrollIntoView({block: "nearest"});
  } else {
    viewport.scrollTop = viewport.scrollHeight;
  }
}

async function refreshHistory() {
  try {
    const {items} = await api("/api/conversations", {signal: AbortSignal.timeout(10000)});
    historyList.replaceChildren();
    if (!items.length) {
      const empty = document.createElement("p");
      empty.textContent = "暂时没有历史对话";
      historyList.append(empty);
    }
    for (const entry of items) {
      const row = document.createElement("div");
      row.className = "history-row";
      const open = document.createElement("button");
      open.type = "button";
      open.className = "history-open";
      open.textContent = entry.title;
      open.title = entry.title;
      if (entry.id === sessionId) open.setAttribute("aria-current", "true");
      open.addEventListener("click", () => showConversation(entry.id));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.textContent = "×";
      remove.setAttribute("aria-label", "删除对话：" + entry.title);
      remove.addEventListener("click", async () => {
        if (busy || !window.confirm("删除这段对话及其收藏？")) return;
        busy = true;
        updateControls();
        try {
          await api("/api/conversations/" + entry.id, {method: "DELETE"});
          if (entry.id === sessionId) startConversation();
          await refreshHistory();
        } catch (error) {
          status.textContent = error.message;
        } finally {
          busy = false;
          updateControls();
        }
      });
      row.append(open, remove);
      historyList.append(row);
    }
  } catch {
    const warning = document.createElement("p");
    warning.textContent = "暂时无法读取对话列表";
    historyList.replaceChildren(warning);
  }
  updateControls();
}

async function showConversation(id) {
  if (busy) return;
  busy = true;
  updateControls();
  status.textContent = "正在读取对话…";
  try {
    const data = await api("/api/conversations/" + id);
    sessionId = id;
    favoriteIds = data.favorite_ids;
    welcome.hidden = true;
    messages.replaceChildren();
    for (const turn of data.turns) {
      appendMessage("user", turn.message);
      appendMessage("assistant", turn.reply);
      renderProducts(turn.products);
      renderSources(turn.sources);
    }
    status.textContent = idleStatus;
    await refreshHistory();
    scrollLatest();
  } catch (error) {
    status.textContent = error.message;
    await refreshHistory();
  } finally {
    busy = false;
    updateControls();
  }
}

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
    const price = document.createElement("p");
    price.className = "price";
    price.textContent = `¥${product.price}`;
    const facts = document.createElement("p");
    facts.textContent = `销量 ${product.sales} · 好评 ${product.rating}%`;
    const colors = document.createElement("p");
    colors.className = "muted";
    colors.textContent = `颜色：${product.colors.join("、")}`;
    const like = document.createElement("button");
    like.type = "button";
    like.dataset.favorite = product.id;
    like.addEventListener("click", () => sendMessage(`我喜欢这款，请收藏商品 ${product.id}`));
    const details = document.createElement("button");
    details.type = "button";
    details.className = "product-detail";
    details.textContent = "详情";
    details.addEventListener("click", () => sendMessage(`查看商品 ${product.id} 的详情`));
    if (Object.hasOwn(product, "stock")) colors.textContent += ` · 库存 ${product.stock}`;
    card.append(name, price, facts, colors, like, " ", details);
    grid.append(card);
  }
  messages.append(grid);
}

function renderSources(sources = []) {
  if (!sources.length) return;
  const wrapper = document.createElement("section");
  wrapper.className = "source-panel";
  wrapper.setAttribute("aria-label", "已检索资料");
  const label = document.createElement("h3");
  label.textContent = `已检索资料 · ${sources.length} 条`;
  wrapper.append(label);
  for (const source of sources) {
    const card = document.createElement("details");
    const title = document.createElement("summary");
    title.textContent = source.title;
    const text = document.createElement("p");
    text.textContent = source.snippet;
    const metadata = document.createElement("small");
    metadata.textContent = `${source.label} · ${source.chunk_id} · v${source.version}`;
    card.append(title, text, metadata);
    card.addEventListener("toggle", () => {
      if (card.open && window.matchMedia("(max-width:620px)").matches) {
        card.scrollIntoView({block: "nearest"});
      }
    });
    wrapper.append(card);
  }
  messages.append(wrapper);
}

async function refreshKnowledgeStatus() {
  const target = document.querySelector("#knowledge-status");
  try {
    const data = await api("/api/knowledge/status", {signal: AbortSignal.timeout(5000)});
    target.textContent = data.status === "indexed"
      ? `${data.documents} 篇资料已索引，回答可查看片段。`
      : "资料索引尚不可用；商品、优惠和订单查询仍可用。";
  } catch {
    target.textContent = "暂时无法读取资料状态。";
  }
}

function updateControls() {
  send.disabled = reset.disabled = busy;
  for (const button of document.querySelectorAll("[data-prompt], #history button, .product-detail")) {
    button.disabled = busy;
  }
  favoriteCount.textContent = favoriteIds.length;
  mobileCount.textContent = favoriteIds.length;
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
  welcome.hidden = true;
  appendMessage("user", message);
  status.textContent = "正在查询商品或资料，请稍候…";
  updateControls();
  scrollLatest();
  try {
    const result = await api("/chat", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({message, session_id: sessionId}),
    });
    if (!result.turn_status || result.turn_status === "completed") sessionId = result.session_id;
    favoriteIds = result.favorite_ids;
    appendMessage("assistant", result.reply);
    renderProducts(result.products);
    renderSources(result.sources);
    await refreshHistory();
  } catch (error) {
    const recovered = error.statusCode === 404 && sessionId;
    if (recovered) startConversation();
    if (recovered) welcome.hidden = true;
    appendMessage("error", recovered ? "原对话已过期。再次发送会开始新对话。" : error.message);
    if (!input.value) input.value = message;
  } finally {
    busy = false;
    status.textContent = idleStatus;
    updateControls();
    scrollLatest();
  }
}

function startConversation() {
  sessionId = null;
  favoriteIds = [];
  input.value = "";
  messages.replaceChildren();
  welcome.hidden = false;
  status.textContent = idleStatus;
  viewport.scrollTop = 0;
  for (const button of historyList.querySelectorAll("[aria-current]")) button.removeAttribute("aria-current");
  updateControls();
}

composer.addEventListener("submit", (event) => {
  event.preventDefault();
  sendMessage(input.value);
});
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing && event.keyCode !== 229) {
    event.preventDefault();
    composer.requestSubmit();
  }
});
reset.addEventListener("click", () => {
  startConversation();
  input.focus();
});
for (const button of document.querySelectorAll("[data-prompt]")) {
  button.addEventListener("click", () => sendMessage(button.dataset.prompt));
}
startConversation();
refreshHistory();
refreshKnowledgeStatus();
