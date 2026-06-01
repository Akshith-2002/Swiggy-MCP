const chat = document.getElementById("chat");
const form = document.getElementById("form");
const input = document.getElementById("prompt");
const send = document.getElementById("send");
const splash = document.getElementById("splash");

if (splash) {
  const dismissSplash = () => {
    if (splash.classList.contains("dismissed")) return;
    splash.classList.add("dismissed");
    setTimeout(() => splash.remove(), 600);
  };
  splash.addEventListener("click", dismissSplash);
  // Allow keyboard (Enter / Space) to also dismiss
  window.addEventListener("keydown", function onKey(e) {
    if (e.key === "Enter" || e.key === " ") {
      window.removeEventListener("keydown", onKey);
      dismissSplash();
    }
  });
}

let currentSessionId = null;

// Session-scoped state for picking out which restaurant / products the agent chose
const state = {
  restaurants: new Map(),     // id -> card element
  products: new Map(),        // id -> card element
  pickedRestaurantId: null,
  pickedProductIds: new Set(),
  selectedAddress: null,
  selectedSlot: null,         // {restaurant_name, time, party_size}
  cartItems: [],              // [{name, price}]
  cartSubtotal: 0,
  deliveryFee: 0,
  budget: null,
  pendingItineraryEl: null,
};

const SERVER_FOR_TOOL = {
  get_saved_locations: "dineout",
  search_restaurants_dineout: "dineout",
  get_restaurant_details: "dineout",
  get_available_slots: "dineout",
  create_cart: "dineout",
  book_table: "dineout",
  get_booking_status: "dineout",
  get_addresses: "instamart",
  search_products: "instamart",
  get_product_details: "instamart",
  update_cart: "instamart",
  get_cart: "instamart",
  clear_cart: "instamart",
  your_go_to_items: "instamart",
  fetch_coupons: "instamart",
  apply_coupon: "instamart",
  checkout: "instamart",
  get_orders: "instamart",
  track_order: "instamart",
  search_restaurants: "food",
  get_restaurant_menu: "food",
  get_food_cart: "food",
  place_food_order: "food",
  report_error: "instamart",
};

const PRODUCT_EMOJI = {
  "Bouquet of 12 Red Roses": "🌹",
  "Mixed Seasonal Flower Bouquet": "💐",
  "Sunflower Bouquet (6 stems)": "🌻",
  "Premium White Lilies Bouquet": "🤍",
  "Theobroma Chocolate Truffle Cake 500g": "🍫",
  "Cheesecake Slice 200g (Theobroma)": "🍰",
  "Ferrero Rocher 16-piece Box": "🍬",
  "Belgian Dark Chocolate Brownie Pack (6)": "🍪",
  "Macaron Box 12-piece (assorted)": "🥮",
};

const CATEGORY_EMOJI = {
  Flowers: "💐",
  Dessert: "🍰",
};

document.querySelectorAll(".suggestion").forEach((btn) => {
  btn.addEventListener("click", () => {
    // Strip the leading icon when filling the input
    const text = btn.textContent.replace(/^\s*\S+\s*/, "").trim();
    input.value = text;
    form.requestSubmit();
  });
});

const VIBE_TAG_MAP = {
  "date night": "vibe-date",
  romantic: "vibe-romantic",
  cocktails: "vibe-cocktails",
  vegetarian: "vibe-veg",
  "vegetarian options": "vibe-veg",
  rooftop: "vibe-rooftop",
};

function vibeClass(label) {
  return VIBE_TAG_MAP[label.toLowerCase()] || "";
}

function fireConfetti() {
  const root = document.getElementById("confetti");
  if (!root) return;
  const emojis = ["✦", "✨", "🌹", "💐", "🌟", "🥂", "🍰", "💫"];
  for (let i = 0; i < 32; i++) {
    const span = document.createElement("span");
    span.textContent = emojis[Math.floor(Math.random() * emojis.length)];
    span.style.left = `${Math.random() * 100}%`;
    span.style.animationDelay = `${Math.random() * 0.6}s`;
    span.style.animationDuration = `${2.2 + Math.random() * 1.4}s`;
    span.style.fontSize = `${14 + Math.random() * 14}px`;
    root.appendChild(span);
    setTimeout(() => span.remove(), 4000);
  }
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const prompt = input.value.trim();
  if (!prompt) return;

  // Reset session state on new query
  resetState();
  state.budget = parseBudget(prompt);

  const welcome = document.getElementById("welcome");
  if (welcome) welcome.remove();

  renderUserMessage(prompt);
  input.value = "";
  send.disabled = true;
  input.disabled = true;

  const assistantDiv = createAssistantMessage();
  const thinking = renderThinking(assistantDiv, "Planning your evening…");

  try {
    await streamSSE("/api/plan", { prompt }, assistantDiv, thinking);
  } catch (err) {
    renderError(assistantDiv, err.message);
  } finally {
    send.disabled = false;
    input.disabled = false;
    input.focus();
  }
});

function resetState() {
  state.restaurants.clear();
  state.products.clear();
  state.pickedRestaurantId = null;
  state.pickedProductIds.clear();
  state.selectedAddress = null;
  state.selectedSlot = null;
  state.cartItems = [];
  state.cartSubtotal = 0;
  state.deliveryFee = 0;
  state.budget = null;
  state.pendingItineraryEl = null;
}

function parseBudget(prompt) {
  const m = prompt.match(/₹\s?(\d[\d,]*)/);
  return m ? parseInt(m[1].replace(/,/g, ""), 10) : null;
}

async function streamSSE(url, body, assistantDiv, thinking) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop();

    let event = null;
    let data = "";
    for (const raw of lines) {
      const line = raw.replace(/\r$/, "");
      if (line.startsWith("event:")) event = line.slice(6).trim();
      else if (line.startsWith("data:")) data += line.slice(5).trim();
      else if (line === "" && event) {
        try {
          handleEvent(event, JSON.parse(data || "{}"), assistantDiv, thinking);
        } catch (err) {
          console.error("SSE parse error", err, data);
        }
        event = null;
        data = "";
      }
    }
  }

  if (thinking && thinking.parentNode) thinking.remove();
}

function handleEvent(event, payload, assistantDiv, thinking) {
  switch (event) {
    case "session":
      currentSessionId = payload.session_id;
      break;
    case "text":
      if (thinking && thinking.parentNode) thinking.remove();
      renderText(assistantDiv, payload.content);
      break;
    case "tool_call":
      if (thinking) thinking.textContent = `→ ${humanize(payload.name)}…`;
      renderToolCall(assistantDiv, payload);
      break;
    case "tool_result":
      attachToolResult(payload, assistantDiv);
      break;
    case "awaiting_confirmation":
      if (thinking && thinking.parentNode) thinking.remove();
      finalizeItinerary(assistantDiv);
      renderConfirmationBar(assistantDiv);
      break;
    case "cancelled":
      renderInfoText(assistantDiv, "Cancelled — no booking was made.");
      break;
    case "error":
      renderError(assistantDiv, payload.message);
      break;
    case "done":
      if (thinking && thinking.parentNode) thinking.remove();
      break;
  }
  scrollDown();
}

function humanize(name) {
  return name.replace(/_/g, " ");
}

function renderUserMessage(text) {
  const div = document.createElement("div");
  div.className = "message user";
  div.textContent = text;
  chat.appendChild(div);
}

function createAssistantMessage() {
  const div = document.createElement("div");
  div.className = "message assistant";
  chat.appendChild(div);
  return div;
}

function renderThinking(container, label) {
  const el = document.createElement("div");
  el.className = "thinking";
  el.textContent = label;
  container.appendChild(el);
  return el;
}

function renderInfoText(container, text) {
  const div = document.createElement("div");
  div.className = "text markdown";
  div.innerHTML = `<p><em>${escapeHtml(text)}</em></p>`;
  container.appendChild(div);
}

function renderText(container, text) {
  let last = container.querySelector(".text:last-of-type");
  // Only append if last element is a text block (not a tool call / card in between)
  if (last && container.lastElementChild !== last) last = null;

  if (last) {
    last.dataset.raw = (last.dataset.raw || "") + text;
    last.innerHTML = renderMarkdown(last.dataset.raw);
  } else {
    const div = document.createElement("div");
    div.className = "text markdown";
    div.dataset.raw = text;
    div.innerHTML = renderMarkdown(text);
    container.appendChild(div);
  }
}

function renderToolCall(container, payload) {
  const div = document.createElement("div");
  div.className = "tool-call";
  div.id = `tool-${payload.id}`;
  const server = SERVER_FOR_TOOL[payload.name] || payload.server || "mcp";
  div.dataset.server = server;
  div.innerHTML = `
    <div class="header">
      <span class="icon">⚡</span>
      <span class="name">${payload.name}</span>
      <span class="server-tag">${server}</span>
      <span class="status-dot"></span>
      <span class="caret">▸</span>
    </div>
    <div class="body">
      <div class="label">Input</div>
      <pre class="input">${escapeHtml(JSON.stringify(payload.input, null, 2))}</pre>
      <div class="label">Result</div>
      <pre class="result">⏳ awaiting…</pre>
    </div>
  `;
  div.querySelector(".header").addEventListener("click", () => {
    div.classList.toggle("expanded");
  });
  container.appendChild(div);
}

function attachToolResult(payload, assistantDiv) {
  const div = document.getElementById(`tool-${payload.id}`);
  if (div) {
    div.classList.add("done");
    const resultPre = div.querySelector(".result");
    let text = payload.result || "";
    try { text = JSON.stringify(JSON.parse(text), null, 2); } catch (_) {}
    resultPre.textContent = text;
  }

  // Domain-specific rich renderings
  let parsed = null;
  try { parsed = JSON.parse(payload.result); } catch (_) {}
  if (!parsed) return;

  if (payload.name === "search_restaurants_dineout" && parsed.success && Array.isArray(parsed.results)) {
    renderRestaurantStrip(assistantDiv, parsed.results);
  } else if (payload.name === "search_products" && parsed.success && Array.isArray(parsed.results)) {
    renderProductStrip(assistantDiv, parsed.results);
  } else if (payload.name === "create_cart" && parsed.success && parsed.cart) {
    state.pickedRestaurantId = parsed.cart.restaurant_id;
    state.selectedSlot = {
      restaurant_name: parsed.cart.restaurant_name,
      slot_id: parsed.cart.slot_id,
      party_size: parsed.cart.party_size,
    };
    markRestaurantPicked(parsed.cart.restaurant_id);
  } else if (payload.name === "get_addresses" && parsed.success && parsed.addresses) {
    const home = parsed.addresses.find((a) => a.is_default) || parsed.addresses[0];
    state.selectedAddress = home;
  } else if (payload.name === "update_cart" && parsed.success && parsed.cart) {
    state.cartItems = parsed.cart.items || [];
    state.cartSubtotal = parsed.cart.subtotal || 0;
    state.deliveryFee = parsed.cart.delivery_fee || 0;
    for (const item of state.cartItems) {
      state.pickedProductIds.add(item.product_id);
      markProductPicked(item.product_id);
    }
  } else if (payload.name === "get_cart" && parsed.success && parsed.cart) {
    state.cartItems = parsed.cart.items || [];
    state.cartSubtotal = parsed.cart.subtotal || 0;
    state.deliveryFee = parsed.cart.delivery_fee || 0;
  } else if (payload.name === "book_table" && parsed.success && parsed.booking) {
    renderBookingSuccess(assistantDiv, parsed.booking);
    fireConfetti();
  } else if (payload.name === "checkout" && parsed.success && parsed.order) {
    renderOrderSuccess(assistantDiv, parsed.order);
  }
}

function renderRestaurantStrip(container, restaurants) {
  if (state.restaurants.size > 0) return; // only render once per session
  const strip = document.createElement("div");
  strip.className = "restaurant-strip";
  const top = restaurants.slice(0, 4);
  for (const r of top) {
    const card = document.createElement("div");
    card.className = "restaurant-card";
    card.id = `rest-${r.id}`;
    card.innerHTML = `
      <div class="ribbon">Picked</div>
      <div class="image">
        <div class="image-inner" style="background-image:url('${r.image || ''}');"></div>
        ${r.is_pure_veg ? '<div class="veg-badge"></div>' : ""}
        <div class="rating"><span class="star">★</span>${r.rating}</div>
      </div>
      <div class="body">
        <div class="name">${escapeHtml(r.name)}</div>
        <div class="cuisine">${escapeHtml((r.cuisine || []).slice(0, 2).join(" · "))} · ${escapeHtml(r.area || "")}</div>
        <div class="meta-row">
          <span>₹${r.price_for_two} for two</span>
        </div>
        <div class="tags">
          ${(r.amenities || [])
            .slice(0, 3)
            .map((a) => `<span class="tag ${vibeClass(a)}">${escapeHtml(a)}</span>`)
            .join("")}
        </div>
      </div>
    `;
    strip.appendChild(card);
    state.restaurants.set(r.id, card);
  }
  container.appendChild(strip);
}

function markRestaurantPicked(id) {
  state.restaurants.forEach((card, cardId) => {
    card.classList.toggle("picked", cardId === id);
  });
}

function renderProductStrip(container, products) {
  const strip = document.createElement("div");
  strip.className = "product-strip";
  const top = products.slice(0, 5);
  for (const p of top) {
    const card = document.createElement("div");
    card.className = "product-card";
    if (!p.in_stock) card.classList.add("oos");
    card.id = `prod-${p.id}`;
    const emoji = PRODUCT_EMOJI[p.name] || CATEGORY_EMOJI[p.category] || "🛒";
    card.innerHTML = `
      <div class="picked-badge">✓</div>
      <div class="emoji">${emoji}</div>
      <div class="name">${escapeHtml(p.name)}</div>
      <div class="price">₹${p.price}</div>
      <div class="eta">${p.delivery_minutes || 25} min</div>
    `;
    strip.appendChild(card);
    state.products.set(p.id, card);
  }
  container.appendChild(strip);
}

function markProductPicked(id) {
  const card = state.products.get(id);
  if (card) card.classList.add("picked");
}

function finalizeItinerary(container) {
  // Render the polished itinerary card from accumulated state
  if (!state.selectedSlot && state.cartItems.length === 0) return;

  const restaurant = state.pickedRestaurantId
    ? Array.from(state.restaurants.entries()).find(([id]) => id === state.pickedRestaurantId)
    : null;

  const rEl = restaurant ? restaurant[1] : null;
  const rName = state.selectedSlot?.restaurant_name || "Reservation";

  const slotTime = state.selectedSlot?.slot_id
    ? formatSlotTime(state.selectedSlot.slot_id)
    : "8:00 PM";

  const subtotal = state.cartSubtotal || 0;
  const delivery = state.deliveryFee || 0;
  const total = subtotal + delivery;

  const itinerary = document.createElement("div");
  itinerary.className = "itinerary";
  itinerary.innerHTML = `
    <div class="itinerary-top-bar"></div>
    <div class="itinerary-header">
      <span class="icon">🌙</span>
      <h3>Tonight's <em>plan</em></h3>
    </div>

    <div class="itinerary-section">
      <div class="label">Dinner reservation</div>
      <div class="primary">${escapeHtml(rName)}</div>
      <div class="meta">${slotTime} · Party of ${state.selectedSlot?.party_size || 2} · Free booking</div>
    </div>

    ${state.cartItems.length > 0 ? `
      <div class="itinerary-section">
        <div class="label">Home delivery — 10:30 PM</div>
        ${state.cartItems.map((i) => `
          <div class="itinerary-item">
            <span>${escapeHtml(i.name)} ${i.quantity > 1 ? `× ${i.quantity}` : ""}</span>
            <span class="price">₹${i.price * (i.quantity || 1)}</span>
          </div>
        `).join("")}
      </div>
    ` : ""}

    <div class="itinerary-totals">
      ${subtotal ? `<div class="row"><span>Instamart subtotal</span><span class="price">₹${subtotal}</span></div>` : ""}
      ${delivery ? `<div class="row"><span>Delivery</span><span class="price">₹${delivery}</span></div>` : ""}
      <div class="row"><span>Dineout reservation</span><span class="price">Free</span></div>
      <div class="row total">
        <span>Total tonight</span>
        <span class="price">₹${total}</span>
      </div>
      ${state.budget ? `
        <div class="budget-bar"><div class="budget-fill" style="width:${Math.min(100, Math.round((total / state.budget) * 100))}%"></div></div>
        <div class="budget-label">${total} / ${state.budget} budget · ${Math.round(((state.budget - total) / state.budget) * 100)}% headroom</div>
      ` : ""}
    </div>
  `;

  // Insert before any trailing text block from the agent
  container.appendChild(itinerary);
  state.pendingItineraryEl = itinerary;

  // Hide the now-redundant markdown table the agent produced
  const tables = container.querySelectorAll("table");
  tables.forEach((t) => (t.style.display = "none"));
}

function formatSlotTime(slotId) {
  // SLOT_20260522_2000 → 8:00 PM
  const m = slotId.match(/(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/);
  if (!m) return slotId;
  let h = parseInt(m[4], 10);
  const min = m[5];
  const ampm = h >= 12 ? "PM" : "AM";
  h = ((h + 11) % 12) + 1;
  return `${h}:${min} ${ampm}`;
}

function renderConfirmationBar(container) {
  const bar = document.createElement("div");
  bar.className = "confirm-bar";
  bar.innerHTML = `
    <button class="secondary" id="cancel-btn">Cancel</button>
    <button class="primary" id="confirm-btn">Confirm &amp; book</button>
  `;
  container.appendChild(bar);

  document.getElementById("confirm-btn").addEventListener("click", () =>
    onConfirm(true, bar)
  );
  document.getElementById("cancel-btn").addEventListener("click", () =>
    onConfirm(false, bar)
  );
}

async function onConfirm(confirmed, bar) {
  bar.querySelectorAll("button").forEach((b) => (b.disabled = true));
  const newAssistant = createAssistantMessage();
  const thinking = renderThinking(
    newAssistant,
    confirmed ? "Executing your plan…" : "Cancelling…"
  );
  await streamSSE(
    "/api/confirm",
    { session_id: currentSessionId, confirmed },
    newAssistant,
    thinking
  );
}

function renderBookingSuccess(container, booking) {
  let card = container.querySelector(".success-card");
  if (!card) {
    card = document.createElement("div");
    card.className = "success-card";
    card.innerHTML = `
      <div class="header">
        <div class="check">✓</div>
        <h3>Tonight is locked in</h3>
      </div>
      <div class="success-rows"></div>
    `;
    container.appendChild(card);
  }
  const rows = card.querySelector(".success-rows");
  const row = document.createElement("div");
  row.className = "success-row";
  row.innerHTML = `
    <span>🍽</span>
    <span>${escapeHtml(booking.cart?.restaurant_name || "Reservation")} · table for ${booking.cart?.party_size || 2}</span>
    <span class="conf">${booking.confirmation_code}</span>
  `;
  rows.appendChild(row);
}

function renderOrderSuccess(container, order) {
  let card = container.querySelector(".success-card");
  if (!card) {
    card = document.createElement("div");
    card.className = "success-card";
    card.innerHTML = `
      <div class="header">
        <div class="check">✓</div>
        <h3>Tonight is locked in</h3>
      </div>
      <div class="success-rows"></div>
    `;
    container.appendChild(card);
  }
  const rows = card.querySelector(".success-rows");
  const row = document.createElement("div");
  row.className = "success-row";
  const itemSummary = (order.items || [])
    .map((i) => i.name.replace(/\s*\(.*?\)/, ""))
    .join(" + ");
  row.innerHTML = `
    <span>💐</span>
    <span>Delivery — ${escapeHtml(itemSummary || "Instamart order")} · ₹${order.total}</span>
    <span class="conf">${order.confirmation_code}</span>
  `;
  rows.appendChild(row);
}

function renderError(container, message) {
  const div = document.createElement("div");
  div.className = "error-banner";
  div.textContent = `Error: ${message}`;
  container.appendChild(div);
}

function renderMarkdown(text) {
  let html = escapeHtml(text);
  html = html.replace(/((?:^\|.*\|\s*\n)+)/gm, (block) => {
    const rows = block
      .trim()
      .split("\n")
      .filter((r) => !/^\|\s*-+/.test(r) && !/^\|\s*$/.test(r));
    const cells = rows
      .map(
        (r) =>
          "<tr>" +
          r
            .replace(/^\||\|$/g, "")
            .split("|")
            .map((c) => `<td>${c.trim()}</td>`)
            .join("") +
          "</tr>"
      )
      .join("");
    return `<table>${cells}</table>`;
  });
  html = html.replace(/^---$/gm, "<hr>");
  html = html.replace(/^### (.*)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.*)$/gm, "<h2>$1</h2>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/(^|[^*])\*([^*]+?)\*([^*]|$)/g, "$1<em>$2</em>$3");
  html = html.replace(/((?:^- .*(?:\n|$))+)/gm, (block) => {
    const items = block
      .trim()
      .split("\n")
      .map((l) => l.replace(/^- /, ""))
      .map((l) => `<li>${l}</li>`)
      .join("");
    return `<ul>${items}</ul>`;
  });
  return html
    .split(/\n{2,}/)
    .map((para) => {
      if (/^<(h2|h3|ul|table|hr)/.test(para.trim())) return para;
      return `<p>${para.replace(/\n/g, "<br>")}</p>`;
    })
    .join("");
}

function escapeHtml(s) {
  if (typeof s !== "string") s = String(s);
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function scrollDown() {
  chat.scrollTop = chat.scrollHeight;
}
