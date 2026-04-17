"use strict";

const STORE = {
  slug: "daddygrab",
  title: "Daddy Grab Super App",
  badge: "Discreet. Fast. Ready Anytime.",
  description: "Poppers 24 Hours. Order Now!",
  baseUrl: "https://store.daddygrab.online",
  logoUrl: "/Assets/dglogotransparent.png",
  fallbackImage: "/Assets/logo.png",
};

const STORAGE_KEYS = {
  cart: "daddygrab_store_cart",
  checkout: "daddygrab_checkout_draft",
  address: "daddygrab_address_draft",
  referral: "daddygrab_referral_code",
};

const tele = window.Telegram?.WebApp || null;
if (tele) {
  tele.ready();
  tele.expand();
}

const state = {
  products: [],
  categories: [],
  activeCategory: "All",
  search: "",
  cart: readJson(STORAGE_KEYS.cart, { cart_session_id: makeCartSessionId(), items: [] }),
  lastQuote: null,
};

function currentPage() {
  return document.body?.dataset.page || "catalog";
}

function readJson(key, fallback) {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch (_) {
    return fallback;
  }
}

function writeJson(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (_) {
    // Ignore storage failures.
  }
}

function makeCartSessionId() {
  if (window.crypto?.randomUUID) {
    return `${STORE.slug}-${window.crypto.randomUUID()}`;
  }
  return `${STORE.slug}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getTelegramMiniAppUser() {
  const user = tele?.initDataUnsafe?.user;
  if (!user) return null;
  const firstName = String(user.first_name || "").trim();
  const lastName = String(user.last_name || "").trim();
  return {
    id: String(user.id || "").trim(),
    username: String(user.username || "").trim().replace(/^@/, ""),
    firstName,
    fullName: [firstName, lastName].filter(Boolean).join(" ").trim(),
    initData: String(tele?.initData || "").trim(),
  };
}

function greetingName() {
  const tgUser = getTelegramMiniAppUser();
  if (tgUser?.firstName) return tgUser.firstName;
  const params = new URLSearchParams(window.location.search);
  return String(params.get("first_name") || params.get("name") || "").trim();
}

function apiJson(url, options = {}) {
  return fetch(url, options).then(async (response) => {
    const payload = await response.json().catch(() => ({}));
    if (!response.ok || payload.ok === false) {
      throw new Error(payload.message || "Request failed.");
    }
    return payload;
  });
}

function peso(value) {
  return new Intl.NumberFormat("en-PH", {
    style: "currency",
    currency: "PHP",
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function validatePhilippineMobileNumber(value) {
  const raw = String(value || "").trim().replace(/\s+/g, "").replace(/-/g, "");
  if (/^09\d{9}$/.test(raw)) {
    return { ok: true, normalized: raw };
  }
  if (/^\+639\d{9}$/.test(raw)) {
    return { ok: true, normalized: `0${raw.slice(3)}` };
  }
  if (/^639\d{9}$/.test(raw)) {
    return { ok: true, normalized: `0${raw.slice(2)}` };
  }
  return {
    ok: false,
    message: "Please use a valid Philippine mobile number like 09XXXXXXXXX or +639XXXXXXXXX.",
  };
}

function cartItemsDetailed() {
  const productMap = new Map(state.products.map((product) => [product.sku, product]));
  return (state.cart.items || [])
    .map((item) => {
      const product = productMap.get(item.sku);
      if (!product) return null;
      const quantity = Number(item.qty || 0);
      return {
        sku: product.sku,
        name: product.name,
        category: product.category,
        quantity,
        price: Number(product.price || 0),
        unit_price: Number(product.price || 0),
        line_total: Number(product.price || 0) * quantity,
      };
    })
    .filter(Boolean);
}

function persistCart() {
  writeJson(STORAGE_KEYS.cart, state.cart);
}

function renderHero() {
  const title = document.getElementById("store-title");
  const badge = document.getElementById("store-badge");
  const description = document.getElementById("store-description");
  const logo = document.querySelector(".hero__logo");
  const greeting = document.getElementById("store-greeting");
  if (title) title.textContent = STORE.title;
  if (badge) badge.textContent = currentPage() === "catalog" ? STORE.badge : badge.textContent;
  if (description && currentPage() === "catalog") description.textContent = STORE.description;
  if (logo) {
    logo.src = STORE.logoUrl;
    logo.alt = `${STORE.title} logo`;
  }
  if (greeting) {
    const name = greetingName();
    greeting.textContent = name ? `Welcome back, ${name}.` : "";
    greeting.hidden = !name;
  }
}

function renderFilters() {
  const wrap = document.getElementById("filters");
  if (!wrap) return;
  wrap.innerHTML = "";
  ["All", ...state.categories].forEach((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `filter-button${category === state.activeCategory ? " is-active" : ""}`;
    button.textContent = category;
    button.addEventListener("click", () => {
      state.activeCategory = category;
      renderFilters();
      renderProducts();
    });
    wrap.appendChild(button);
  });
}

function filteredProducts() {
  return state.products.filter((product) => {
    const matchesCategory = state.activeCategory === "All" || product.category === state.activeCategory;
    const haystack = [product.name, product.description, product.sku, product.category].join(" ").toLowerCase();
    const matchesSearch = haystack.includes(state.search.toLowerCase());
    return matchesCategory && matchesSearch;
  });
}

function renderProducts() {
  const grid = document.getElementById("product-grid");
  const template = document.getElementById("product-card-template");
  if (!grid || !template) return;
  grid.innerHTML = "";
  const products = filteredProducts();
  if (!products.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "No products match this filter yet.";
    grid.appendChild(empty);
    return;
  }
  products.forEach((product) => {
    const node = template.content.firstElementChild.cloneNode(true);
    const image = node.querySelector(".product-card__image");
    const category = node.querySelector(".product-card__category");
    const stock = node.querySelector(".product-card__stock");
    const title = node.querySelector(".product-card__title");
    const description = node.querySelector(".product-card__description");
    const price = node.querySelector(".product-card__price");
    const button = node.querySelector(".product-card__button");
    if (image) {
      image.src = product.image_url || STORE.fallbackImage;
      image.alt = product.name;
    }
    if (category) category.textContent = product.category;
    if (stock) stock.textContent = `${product.stock} in stock`;
    if (title) title.textContent = product.name;
    if (description) description.textContent = product.description;
    if (price) price.textContent = peso(product.price);
    if (button) {
      button.addEventListener("click", () => addToCart(product));
    }
    grid.appendChild(node);
  });
}

function renderCartBadge() {
  const countNode = document.getElementById("cart-count");
  const qty = (state.cart.items || []).reduce((sum, item) => sum + Number(item.qty || 0), 0);
  if (countNode) countNode.textContent = String(qty);
}

function addToCart(product) {
  const existing = state.cart.items.find((item) => item.sku === product.sku);
  if (existing) {
    existing.qty += 1;
  } else {
    state.cart.items.push({ sku: product.sku, qty: 1 });
  }
  persistCart();
  renderCartBadge();
  renderCheckout();
}

function changeQty(sku, delta) {
  const item = state.cart.items.find((entry) => entry.sku === sku);
  if (!item) return;
  item.qty += delta;
  if (item.qty <= 0) {
    state.cart.items = state.cart.items.filter((entry) => entry.sku !== sku);
  }
  persistCart();
  state.lastQuote = null;
  renderCartBadge();
  renderCheckout();
}

function setCheckoutFeedback(message, tone = "") {
  const node = document.getElementById("checkout-feedback");
  if (!node) return;
  node.textContent = message || "";
  node.className = `checkout-feedback${tone ? ` is-${tone}` : ""}`;
}

function setAddressFeedback(message, tone = "") {
  const node = document.getElementById("delivery-address-feedback") || document.getElementById("address-page-feedback");
  if (!node) return;
  node.textContent = message || "";
  node.className = `field-hint${tone ? ` is-${tone}` : ""}`;
}

function populateCheckoutDraft(form) {
  const draft = readJson(STORAGE_KEYS.checkout, {});
  const tgUser = getTelegramMiniAppUser();
  const setValue = (name, value, force = false) => {
    const field = form.elements[name];
    if (!field) return;
    if (!force && String(field.value || "").trim()) return;
    if (value != null && value !== "") field.value = value;
  };
  setValue("delivery_name", tgUser?.fullName || draft.delivery_name);
  setValue("telegram_id", tgUser?.username ? `@${tgUser.username}` : tgUser?.id || draft.telegram_id, true);
  setValue("delivery_area", draft.delivery_area);
  setValue("delivery_contact", draft.delivery_contact);
  setValue("delivery_address", draft.delivery_address);
  setValue("promo_code", draft.promo_code);
  setValue("referral_code", draft.referral_code || readJson(STORAGE_KEYS.referral, ""));
  setValue("payment_method", draft.payment_method || "GCash");
  setValue("delivery_method", draft.delivery_method || "Standard");

  const telegramField = form.elements.telegram_id;
  if (telegramField && tgUser) {
    telegramField.readOnly = true;
  }
}

function persistCheckoutDraft(form) {
  if (!form) return;
  writeJson(STORAGE_KEYS.checkout, {
    delivery_name: String(form.elements.delivery_name?.value || "").trim(),
    telegram_id: String(form.elements.telegram_id?.value || "").trim(),
    delivery_area: String(form.elements.delivery_area?.value || "").trim(),
    delivery_contact: String(form.elements.delivery_contact?.value || "").trim(),
    delivery_address: String(form.elements.delivery_address?.value || "").trim(),
    promo_code: String(form.elements.promo_code?.value || "").trim(),
    referral_code: String(form.elements.referral_code?.value || "").trim().toUpperCase(),
    payment_method: String(form.elements.payment_method?.value || "").trim(),
    delivery_method: String(form.elements.delivery_method?.value || "").trim(),
  });
}

function renderCheckout() {
  const list = document.getElementById("cart-list");
  const empty = document.getElementById("cart-empty");
  const totals = document.getElementById("cart-totals");
  if (!list || !empty || !totals) {
    renderCartBadge();
    return;
  }
  const items = cartItemsDetailed();
  list.innerHTML = "";
  if (!items.length) {
    empty.hidden = false;
    totals.hidden = true;
    return;
  }
  empty.hidden = true;
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "cart-row";
    row.innerHTML = `
      <div class="cart-row__copy">
        <strong>${item.name}</strong>
        <span>${item.category}</span>
        <span>${peso(item.price)}</span>
      </div>
      <div class="cart-row__controls">
        <button type="button" data-minus="${item.sku}">-</button>
        <span>${item.quantity}</span>
        <button type="button" data-plus="${item.sku}">+</button>
      </div>
    `;
    list.appendChild(row);
  });
  list.querySelectorAll("[data-minus]").forEach((button) => {
    button.addEventListener("click", () => changeQty(button.dataset.minus, -1));
  });
  list.querySelectorAll("[data-plus]").forEach((button) => {
    button.addEventListener("click", () => changeQty(button.dataset.plus, 1));
  });
  const subtotal = items.reduce((sum, item) => sum + item.line_total, 0);
  totals.hidden = false;
  totals.innerHTML = `
    <div class="cart-total-line"><span>Subtotal</span><strong>${peso(subtotal)}</strong></div>
    <div class="cart-total-line"><span>Discount</span><strong>${peso(state.lastQuote?.discount || 0)}</strong></div>
    <div class="cart-total-line cart-total-line--grand"><span>Total</span><strong>${peso(state.lastQuote?.total || subtotal)}</strong></div>
  `;
}

async function loadCatalog() {
  const response = await apiJson("/api/storefront/daddygrab-catalog");
  const data = response.data || {};
  state.products = Array.isArray(data.products) ? data.products : [];
  state.categories = Array.from(new Set(state.products.map((product) => product.category))).sort();
  renderFilters();
  renderProducts();
  renderCartBadge();
}

async function refreshQuote() {
  const form = document.getElementById("checkout-form");
  if (!form) return;
  const phoneCheck = validatePhilippineMobileNumber(form.elements.delivery_contact?.value || "");
  if (!phoneCheck.ok) {
    setCheckoutFeedback(phoneCheck.message, "error");
    return;
  }
  persistCheckoutDraft(form);
  const items = cartItemsDetailed();
  if (!items.length) {
    setCheckoutFeedback("Your cart is empty.", "error");
    return;
  }
  const response = await apiJson("/api/storefront/daddygrab-checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode: "quote",
      promo_code: String(form.elements.promo_code?.value || "").trim(),
      items,
    }),
  });
  state.lastQuote = response.data;
  renderCheckout();
  setCheckoutFeedback(`Quote updated. Total is ${peso(response.data.total)}.`, "success");
}

async function submitOrder(event) {
  event.preventDefault();
  const form = document.getElementById("checkout-form");
  const items = cartItemsDetailed();
  if (!items.length) {
    setCheckoutFeedback("Your cart is empty.", "error");
    return;
  }
  const phoneCheck = validatePhilippineMobileNumber(form.elements.delivery_contact?.value || "");
  if (!phoneCheck.ok) {
    setCheckoutFeedback(phoneCheck.message, "error");
    return;
  }
  const address = String(form.elements.delivery_address?.value || "").trim();
  if (!address) {
    setCheckoutFeedback("Delivery address is required.", "error");
    return;
  }
  const tgUser = getTelegramMiniAppUser();
  persistCheckoutDraft(form);
  setCheckoutFeedback("Placing your order...");
  const payload = {
    source: tgUser ? "telegram" : "web",
    customer: {
      customer_name: String(form.elements.delivery_name?.value || "").trim(),
      first_name: tgUser?.firstName || "",
      telegram_id: tgUser?.id || "",
      telegram_user_id: tgUser?.id || "",
      telegram_username: tgUser?.username || String(form.elements.telegram_id?.value || "").trim().replace(/^@/, ""),
      telegram_init_data: tgUser?.initData || "",
      phone_number: phoneCheck.normalized,
      delivery_area: String(form.elements.delivery_area?.value || "").trim(),
      delivery_address: address,
    },
    payment_method: String(form.elements.payment_method?.value || "").trim(),
    delivery_method: String(form.elements.delivery_method?.value || "").trim() || "Standard",
    promo_code: String(form.elements.promo_code?.value || "").trim(),
    referral_code: String(form.elements.referral_code?.value || "").trim().toUpperCase(),
    address_verified: false,
    address_verification_notes: "Manual review allowed; verification not required for submission.",
    items,
  };
  try {
    const response = await apiJson("/api/storefront/daddygrab-checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    state.cart = { cart_session_id: makeCartSessionId(), items: [] };
    state.lastQuote = null;
    persistCart();
    writeJson(STORAGE_KEYS.checkout, {});
    writeJson(STORAGE_KEYS.address, {});
    renderCartBadge();
    renderCheckout();
    form.reset();
    populateCheckoutDraft(form);
    showOrderSuccessPopup(response.data.order);
    setCheckoutFeedback(`Order ${response.data.order.order_id} created successfully.`, "success");
  } catch (error) {
    setCheckoutFeedback(error.message || "Could not place the order.", "error");
  }
}

function ownReferralCode() {
  const tgUser = getTelegramMiniAppUser();
  if (tgUser?.username) {
    return `DADDY-${tgUser.username.replace(/[^a-z0-9]/gi, "").toUpperCase().slice(0, 8)}`;
  }
  if (tgUser?.id) {
    return `DADDY-${tgUser.id.slice(-6)}`;
  }
  return `DADDY-${state.cart.cart_session_id.slice(-6).toUpperCase()}`;
}

function showOrderSuccessPopup(order) {
  const wrap = document.getElementById("order-success");
  if (!wrap) return;
  const number = document.getElementById("order-success-number");
  const link = document.getElementById("order-success-track-link");
  const code = document.getElementById("own-referral-code");
  if (number) number.textContent = order.order_id || "-";
  if (link) link.href = `/track?order_id=${encodeURIComponent(order.order_id || "")}`;
  if (code) code.textContent = ownReferralCode();
  wrap.hidden = false;
  wrap.querySelectorAll("[data-order-success-close]").forEach((node) => {
    node.addEventListener("click", () => {
      wrap.hidden = true;
    }, { once: true });
  });
  const copyButton = document.getElementById("copy-referral");
  if (copyButton) {
    copyButton.onclick = async () => {
      try {
        await navigator.clipboard.writeText(code?.textContent || "");
      } catch (_) {
        // Ignore clipboard failures.
      }
    };
  }
}

async function loadTracking() {
  const form = document.getElementById("tracking-form");
  const statusNode = document.getElementById("tracking-status");
  if (!form || !statusNode) return;
  const params = new URLSearchParams(window.location.search);
  const tgUser = getTelegramMiniAppUser();
  if (!String(form.elements.telegram_username?.value || "").trim() && tgUser?.username) {
    form.elements.telegram_username.value = `@${tgUser.username}`;
  }
  if (params.get("order_id")) {
    form.elements.order_id.value = params.get("order_id");
  }
  if (params.get("phone")) {
    form.elements.phone.value = params.get("phone");
  }

  const lookup = async (event) => {
    if (event) event.preventDefault();
    statusNode.textContent = "Checking order status...";
    try {
      const response = await apiJson("/api/storefront/daddygrab-track", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          order_id: String(form.elements.order_id?.value || "").trim(),
          phone: String(form.elements.phone?.value || "").trim(),
          telegram_username: String(form.elements.telegram_username?.value || "").trim().replace(/^@/, ""),
        }),
      });
      const order = response.data;
      statusNode.innerHTML = `
        <p><strong>Order Number:</strong> ${order.order_id}</p>
        <p><strong>Status:</strong> ${order.order_status}</p>
        <p><strong>Payment:</strong> ${order.payment_method}</p>
        <p><strong>Total:</strong> ${peso(order.total)}</p>
        <p><strong>Phone:</strong> ${order.phone_number}</p>
        <p><strong>Address:</strong> ${order.delivery_address}</p>
      `;
    } catch (error) {
      statusNode.textContent = error.message || "Could not load tracking right now.";
    }
  };

  form.addEventListener("submit", lookup);
  if (params.get("order_id")) {
    lookup();
  }
}

function loadAddressPage() {
  const form = document.getElementById("address-form");
  const backButton = document.getElementById("back-to-checkout");
  const verifyButton = document.getElementById("verify-address");
  if (!form) return;
  const draft = readJson(STORAGE_KEYS.checkout, {});
  if (draft.delivery_area) form.elements.delivery_area.value = draft.delivery_area;
  if (draft.delivery_method) form.elements.delivery_method.value = draft.delivery_method;
  if (draft.delivery_address) form.elements.delivery_address.value = draft.delivery_address;

  verifyButton?.addEventListener("click", () => {
    writeJson(STORAGE_KEYS.address, {
      delivery_area: String(form.elements.delivery_area.value || "").trim(),
      delivery_method: String(form.elements.delivery_method.value || "").trim(),
      delivery_address: String(form.elements.delivery_address.value || "").trim(),
    });
    setAddressFeedback("Verification is not required right now. We saved this address for manual review.", "success");
  });

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const merged = {
      ...readJson(STORAGE_KEYS.checkout, {}),
      delivery_area: String(form.elements.delivery_area.value || "").trim(),
      delivery_method: String(form.elements.delivery_method.value || "").trim(),
      delivery_address: String(form.elements.delivery_address.value || "").trim(),
    };
    writeJson(STORAGE_KEYS.address, merged);
    writeJson(STORAGE_KEYS.checkout, merged);
    window.location.href = "/checkout";
  });

  backButton?.addEventListener("click", () => {
    window.location.href = "/checkout";
  });
}

function bindNavigation() {
  document.getElementById("copy-link")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(STORE.baseUrl);
    } catch (_) {
      // Ignore clipboard failures.
    }
  });
  document.getElementById("go-track")?.addEventListener("click", () => {
    window.location.href = "/track";
  });
  document.getElementById("go-admin")?.addEventListener("click", () => {
    window.location.href = "/admin";
  });
  document.getElementById("go-checkout")?.addEventListener("click", () => {
    window.location.href = "/checkout";
  });
  document.querySelectorAll("[data-go-checkout]").forEach((button) => {
    button.addEventListener("click", () => {
      window.location.href = "/checkout";
    });
  });
  document.getElementById("back-to-catalog")?.addEventListener("click", () => {
    window.location.href = "/";
  });
  document.getElementById("open-address-page")?.addEventListener("click", () => {
    const form = document.getElementById("checkout-form");
    persistCheckoutDraft(form);
    window.location.href = "/address";
  });
}

async function initCheckoutPage() {
  const form = document.getElementById("checkout-form");
  if (!form) return;
  populateCheckoutDraft(form);
  renderCheckout();
  form.addEventListener("submit", submitOrder);
  document.getElementById("refresh-quote")?.addEventListener("click", refreshQuote);
  document.getElementById("apply-promo")?.addEventListener("click", refreshQuote);
  ["delivery_name", "telegram_id", "delivery_area", "delivery_contact", "delivery_address", "promo_code", "referral_code", "payment_method", "delivery_method"].forEach((name) => {
    const field = form.elements[name];
    field?.addEventListener("input", () => persistCheckoutDraft(form));
    field?.addEventListener("change", () => persistCheckoutDraft(form));
  });
}

async function initCatalogPage() {
  await loadCatalog();
  const search = document.getElementById("search");
  if (search) {
    search.addEventListener("input", (event) => {
      state.search = String(event.target.value || "");
      renderProducts();
    });
  }
}

async function init() {
  renderHero();
  bindNavigation();
  if (currentPage() === "catalog") {
    await initCatalogPage();
  }
  if (currentPage() === "checkout") {
    await loadCatalog();
    await initCheckoutPage();
  }
  if (currentPage() === "track") {
    await loadTracking();
  }
  if (currentPage() === "address") {
    loadAddressPage();
  }
}

window.addEventListener("DOMContentLoaded", init);
