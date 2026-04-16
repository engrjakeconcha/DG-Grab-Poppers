"use strict";

const ADMIN_SESSION_KEY = "daddygrab_admin_session";
const ADMIN_API_URL = "/api/admin/daddygrab-admin";

const state = {
  session: null,
  dashboard: null,
  activeTab: "orders",
  orderFilter: "pending",
  orderSearch: "",
  inventory: [],
  promos: [],
  adminUsers: [],
};

function peso(value) {
  return new Intl.NumberFormat("en-PH", {
    style: "currency",
    currency: "PHP",
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

function readSession() {
  try {
    const raw = window.sessionStorage.getItem(ADMIN_SESSION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    return null;
  }
}

function writeSession(session) {
  try {
    if (!session) {
      window.sessionStorage.removeItem(ADMIN_SESSION_KEY);
      return;
    }
    window.sessionStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(session));
  } catch (_) {
    // Ignore storage failures.
  }
}

function isSuperAdmin() {
  return state.session?.role === "super_admin";
}

function setFeedback(targetId, message, tone = "") {
  const node = document.getElementById(targetId);
  if (!node) {
    return;
  }
  node.textContent = message || "";
  node.className = `checkout-feedback${tone ? ` is-${tone}` : ""}`;
}

function withAuthHeaders() {
  return {
    "Content-Type": "application/json",
    "x-admin-user": state.session?.username || "",
    "x-admin-code": state.session?.code || "",
    "x-admin-role": state.session?.role || "",
  };
}

async function adminRequest(action, payload = {}, { auth = true } = {}) {
  const response = await fetch(ADMIN_API_URL, {
    method: "POST",
    headers: auth ? withAuthHeaders() : { "Content-Type": "application/json" },
    body: JSON.stringify({ action, ...payload }),
  });
  const result = await response.json();
  if (!response.ok || !result.ok) {
    throw new Error(result.message || "Admin request failed.");
  }
  return result;
}

function renderAuthState() {
  const auth = document.getElementById("admin-auth");
  const dashboard = document.getElementById("admin-dashboard");
  const welcome = document.getElementById("admin-welcome");
  const roleLabel = document.getElementById("admin-role-label");
  const loggedIn = Boolean(state.session?.username);

  if (auth) {
    auth.hidden = loggedIn;
  }
  if (dashboard) {
    dashboard.hidden = !loggedIn;
  }
  if (welcome && loggedIn) {
    welcome.textContent = `Welcome, ${state.session.username}`;
  }
  if (roleLabel && loggedIn) {
    roleLabel.textContent =
      state.session.role === "super_admin"
        ? "Super Admin access is active. Rotate seeded passwords before production."
        : "Admin access is active. Order updates only, with view-only access for finance and promos.";
  }

  const adminPanel = document.querySelector("[data-admin-panel='admins']");
  if (adminPanel instanceof HTMLElement) {
    adminPanel.hidden = !loggedIn || !isSuperAdmin() || state.activeTab !== "admins";
  }

  document.querySelectorAll("#promo-form, #inventory-form, #admin-user-form").forEach((node) => {
    if (!(node instanceof HTMLFormElement)) {
      return;
    }
    const disabled = !loggedIn || !isSuperAdmin();
    node.querySelectorAll("input, select, textarea, button").forEach((control) => {
      control.disabled = disabled;
    });
  });
}

function setActiveTab(tabName) {
  state.activeTab = tabName;
  document.querySelectorAll("[data-admin-tab]").forEach((button) => {
    const active = button.dataset.adminTab === tabName;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll("[data-admin-panel]").forEach((panel) => {
    if (panel.dataset.adminPanel === "admins" && !isSuperAdmin()) {
      panel.hidden = true;
      return;
    }
    panel.hidden = panel.dataset.adminPanel !== tabName;
  });
}

function applyOverview() {
  const summary = state.dashboard?.summary || {};
  const report = state.dashboard?.report || {};
  const set = (id, value) => {
    const node = document.getElementById(id);
    if (node) {
      node.textContent = value;
    }
  };
  set("metric-pending", String(summary.pending_orders ?? 0));
  set("metric-awaiting", String(summary.awaiting_payment ?? 0));
  set("metric-sales", peso(report.gross_sales || 0));
  set("metric-aov", peso(report.average_order_value || 0));
  set("metric-sales-copy", `${report.order_count || 0} orders in report snapshot.`);
  set("metric-aov-copy", "Track totals, queue health, and fulfillment progress here.");
}

function renderOrders() {
  const list = document.getElementById("admin-orders");
  const empty = document.getElementById("admin-orders-empty");
  const template = document.getElementById("admin-order-template");
  if (!list || !(template instanceof HTMLTemplateElement)) {
    return;
  }
  list.innerHTML = "";

  const orders = Array.isArray(state.dashboard?.orders) ? state.dashboard.orders : [];
  const filtered = orders.filter((order) => {
    if (state.orderFilter === "pending" && order.order_status !== "Pending Confirmation") {
      return false;
    }
    if (state.orderFilter === "awaiting_payment" && order.payment_status !== "awaiting_payment") {
      return false;
    }
    if (!state.orderSearch) {
      return true;
    }
    const haystack = [
      order.order_id,
      order.customer_name,
      order.phone_number,
      order.telegram_username,
      order.delivery_address,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(state.orderSearch.toLowerCase());
  });

  if (empty) {
    empty.hidden = filtered.length > 0;
  }

  filtered.forEach((entry) => {
    const fragment = template.content.cloneNode(true);
    const node = fragment.querySelector(".admin-order-card");
    if (!node) {
      return;
    }

    const set = (selector, value) => {
      const target = node.querySelector(selector);
      if (target) {
        target.textContent = value;
      }
    };
    const setValue = (selector, value) => {
      const target = node.querySelector(selector);
      if (target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement) {
        target.value = value;
      }
    };

    set(".admin-order-card__title", entry.order_id || "-");
    set(".admin-order-card__status", entry.order_status || "Pending Confirmation");
    set(
      ".admin-order-card__meta",
      [entry.customer_name, entry.phone_number, entry.telegram_username ? `@${entry.telegram_username}` : ""].filter(Boolean).join(" • ")
    );
    set(".admin-order-card__address", `${entry.delivery_area || "Metro Manila"}\n${entry.delivery_address || "-"}`);
    set(
      ".admin-order-card__items",
      (entry.items || []).length
        ? entry.items.map((item) => `${item.name} x${item.quantity}`).join(" • ")
        : "No items attached."
    );
    set(
      ".admin-order-card__totals",
      `Total ${peso(entry.total)} • Payment ${entry.payment_method || "-"} • Delivery ${entry.delivery_method || "-"}`
    );
    setValue(".admin-order-card__status-input", entry.order_status || "Pending Confirmation");
    setValue(".admin-order-card__tracking-input", entry.tracking_number || "");
    const trackLink = node.querySelector(".admin-order-card__track-page");
    if (trackLink instanceof HTMLAnchorElement) {
      trackLink.href = entry.tracking_link || `/track?order_id=${encodeURIComponent(entry.order_id || "")}`;
    }

    const feedback = node.querySelector(".admin-order-card__feedback");
    const statusInput = node.querySelector(".admin-order-card__status-input");
    const trackingInput = node.querySelector(".admin-order-card__tracking-input");
    const messageInput = node.querySelector(".admin-order-card__message");
    const saveButton = node.querySelector(".admin-order-card__save");
    const contactButton = node.querySelector(".admin-order-card__contact");

    const setCardFeedback = (message, tone = "") => {
      if (!(feedback instanceof HTMLElement)) {
        return;
      }
      feedback.textContent = message || "";
      feedback.className = `checkout-feedback admin-order-card__feedback${tone ? ` is-${tone}` : ""}`;
    };

    saveButton?.addEventListener("click", async () => {
      try {
        setCardFeedback("Saving update...");
        const result = await adminRequest("update_order", {
          order_id: entry.order_id,
          status: statusInput?.value || "",
          tracking_number: trackingInput?.value || "",
        });
        setCardFeedback("Order updated.", "success");
        entry.order_status = result.order?.order_status || statusInput?.value || entry.order_status;
        entry.tracking_number = result.order?.tracking_number || trackingInput?.value || entry.tracking_number;
        await refreshDashboard();
      } catch (error) {
        setCardFeedback(error instanceof Error ? error.message : "Failed to update order.", "error");
      }
    });

    contactButton?.addEventListener("click", async () => {
      try {
        setCardFeedback("Sending message...");
        await adminRequest("contact_customer", {
          order_id: entry.order_id,
          message: messageInput?.value || "",
        });
        setCardFeedback("Customer message queued.", "success");
        if (messageInput instanceof HTMLTextAreaElement) {
          messageInput.value = "";
        }
      } catch (error) {
        setCardFeedback(error instanceof Error ? error.message : "Failed to message customer.", "error");
      }
    });

    list.appendChild(fragment);
  });
}

function fillInventoryForm(product) {
  const form = document.getElementById("inventory-form");
  if (!(form instanceof HTMLFormElement) || !product) {
    return;
  }
  form.sku.value = product.sku || "";
  form.category.value = product.category || "poppers";
  form.name.value = product.name || "";
  form.price.value = product.price || "";
  form.stock.value = product.stock || 0;
  form.description.value = product.description || "";
  form.image_url.value = product.image_url || "";
  form.active.value = String(product.active !== false);
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderInventory() {
  const list = document.getElementById("admin-inventory");
  const template = document.getElementById("admin-inventory-template");
  if (!list || !(template instanceof HTMLTemplateElement)) {
    return;
  }
  list.innerHTML = "";
  state.inventory.forEach((product) => {
    const fragment = template.content.cloneNode(true);
    const node = fragment.querySelector(".admin-mini-card");
    if (!node) {
      return;
    }
    const set = (selector, value) => {
      const target = node.querySelector(selector);
      if (target) {
        target.textContent = value;
      }
    };
    set(".admin-inventory__title", product.name || "-");
    set(".admin-inventory__sku", product.sku || "-");
    set(".admin-inventory__meta", `${product.category || "-"} • ${peso(product.price || 0)} • Stock ${product.stock || 0}`);
    set(".admin-inventory__description", product.description || "No description yet.");

    const feedback = node.querySelector(".admin-inventory__feedback");
    const setCardFeedback = (message, tone = "") => {
      if (!(feedback instanceof HTMLElement)) {
        return;
      }
      feedback.textContent = message || "";
      feedback.className = `checkout-feedback admin-inventory__feedback${tone ? ` is-${tone}` : ""}`;
    };

    node.querySelector(".admin-inventory__edit")?.addEventListener("click", () => {
      fillInventoryForm(product);
      setCardFeedback("Loaded into editor.", "success");
    });

    const deleteButton = node.querySelector(".admin-inventory__delete");
    if (!isSuperAdmin()) {
      deleteButton?.setAttribute("disabled", "disabled");
    }
    deleteButton?.addEventListener("click", async () => {
      if (!isSuperAdmin()) {
        setCardFeedback("Only super admins can delete products.", "error");
        return;
      }
      try {
        setCardFeedback("Deleting product...");
        await adminRequest("delete_product", { sku: product.sku });
        setCardFeedback("Product deleted.", "success");
        await refreshDashboard();
      } catch (error) {
        setCardFeedback(error instanceof Error ? error.message : "Delete failed.", "error");
      }
    });

    list.appendChild(fragment);
  });
}

function renderPromos() {
  const list = document.getElementById("admin-promos");
  const template = document.getElementById("admin-promo-template");
  if (!list || !(template instanceof HTMLTemplateElement)) {
    return;
  }
  list.innerHTML = "";
  state.promos.forEach((promo) => {
    const fragment = template.content.cloneNode(true);
    const node = fragment.querySelector(".admin-mini-card");
    if (!node) {
      return;
    }
    const set = (selector, value) => {
      const target = node.querySelector(selector);
      if (target) {
        target.textContent = value;
      }
    };
    set(".admin-promo__code", promo.code || "-");
    set(".admin-promo__state", promo.active ? "Active" : "Inactive");
    set(
      ".admin-promo__discount",
      promo.discount_type === "percent"
        ? `${promo.discount_value}% off`
        : `${peso(promo.discount_value || 0)} off`
    );
    set(".admin-promo__notes", promo.notes || "No notes.");
    list.appendChild(fragment);
  });
}

function renderAdminUsers() {
  const list = document.getElementById("admin-users");
  const template = document.getElementById("admin-user-template");
  const panel = document.querySelector("[data-admin-panel='admins']");
  if (!list || !(template instanceof HTMLTemplateElement)) {
    return;
  }
  if (!isSuperAdmin()) {
    if (panel instanceof HTMLElement) {
      panel.hidden = true;
    }
    return;
  }
  list.innerHTML = "";
  state.adminUsers.forEach((admin) => {
    const fragment = template.content.cloneNode(true);
    const node = fragment.querySelector(".admin-mini-card");
    if (!node) {
      return;
    }
    const set = (selector, value) => {
      const target = node.querySelector(selector);
      if (target) {
        target.textContent = value;
      }
    };
    set(".admin-user__title", admin.username || "-");
    set(".admin-user__state", admin.access_level === "super_admin" ? "Super Admin" : "Admin");
    set(
      ".admin-user__meta",
      [admin.telegram_username ? `@${admin.telegram_username}` : "", admin.telegram_id || "", admin.created_by ? `Created by ${admin.created_by}` : ""]
        .filter(Boolean)
        .join(" • ") || "No Telegram link saved."
    );
    list.appendChild(fragment);
  });
}

async function refreshDashboard() {
  const result = await adminRequest("dashboard", {
    status: state.orderFilter,
    search: state.orderSearch,
    limit: 100,
  });
  state.dashboard = result;
  state.inventory = result.inventory || [];
  state.promos = result.promos || [];
  state.adminUsers = result.admin_users || [];
  applyOverview();
  renderOrders();
  renderInventory();
  renderPromos();
  renderAdminUsers();
  renderAuthState();
}

async function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(reader.error || new Error("Failed to read file."));
    reader.readAsDataURL(file);
  });
}

function bindEvents() {
  const loginForm = document.getElementById("admin-login-form");
  if (loginForm instanceof HTMLFormElement) {
    loginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        setFeedback("admin-login-feedback", "Signing in...");
        const form = new FormData(loginForm);
        const result = await adminRequest(
          "login",
          {
            username: String(form.get("username") || "").trim(),
            passcode: String(form.get("passcode") || "").trim(),
          },
          { auth: false }
        );
        state.session = result.session;
        writeSession(state.session);
        renderAuthState();
        await refreshDashboard();
        setFeedback("admin-login-feedback", "");
      } catch (error) {
        setFeedback("admin-login-feedback", error instanceof Error ? error.message : "Login failed.", "error");
      }
    });
  }

  document.getElementById("admin-refresh")?.addEventListener("click", async () => {
    setFeedback("admin-dashboard-feedback", "Refreshing dashboard...");
    try {
      await refreshDashboard();
      setFeedback("admin-dashboard-feedback", "Dashboard refreshed.", "success");
    } catch (error) {
      setFeedback("admin-dashboard-feedback", error instanceof Error ? error.message : "Refresh failed.", "error");
    }
  });

  document.getElementById("admin-logout")?.addEventListener("click", () => {
    state.session = null;
    writeSession(null);
    renderAuthState();
  });

  document.querySelectorAll("[data-admin-tab]").forEach((button) => {
    button.addEventListener("click", () => setActiveTab(button.dataset.adminTab || "orders"));
  });

  document.getElementById("order-filter")?.addEventListener("change", async (event) => {
    state.orderFilter = event.target.value;
    await refreshDashboard();
  });

  document.getElementById("order-search")?.addEventListener("input", async (event) => {
    state.orderSearch = event.target.value.trim();
    renderOrders();
  });

  const inventoryForm = document.getElementById("inventory-form");
  if (inventoryForm instanceof HTMLFormElement) {
    inventoryForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!isSuperAdmin()) {
        setFeedback("inventory-feedback", "Only super admins can save products.", "error");
        return;
      }
      try {
        setFeedback("inventory-feedback", "Saving product...");
        const form = new FormData(inventoryForm);
        let imageUrl = String(form.get("image_url") || "").trim();
        const fileInput = document.getElementById("inventory-image-file");
        if (!imageUrl && fileInput instanceof HTMLInputElement && fileInput.files?.[0]) {
          imageUrl = await fileToDataUrl(fileInput.files[0]);
        }
        await adminRequest("save_product", {
          product: {
            sku: String(form.get("sku") || "").trim(),
            category: String(form.get("category") || "").trim(),
            name: String(form.get("name") || "").trim(),
            price: Number(form.get("price") || 0),
            stock: Number(form.get("stock") || 0),
            description: String(form.get("description") || "").trim(),
            image_url: imageUrl,
            active: String(form.get("active") || "true") === "true",
          },
        });
        inventoryForm.reset();
        if (fileInput instanceof HTMLInputElement) {
          fileInput.value = "";
        }
        setFeedback("inventory-feedback", "Product saved.", "success");
        await refreshDashboard();
      } catch (error) {
        setFeedback("inventory-feedback", error instanceof Error ? error.message : "Save failed.", "error");
      }
    });
  }

  const promoForm = document.getElementById("promo-form");
  if (promoForm instanceof HTMLFormElement) {
    promoForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!isSuperAdmin()) {
        setFeedback("promo-feedback", "Only super admins can save promos.", "error");
        return;
      }
      try {
        setFeedback("promo-feedback", "Saving promo...");
        const form = new FormData(promoForm);
        await adminRequest("save_promo", {
          promo: {
            code: String(form.get("code") || "").trim(),
            discount_type: String(form.get("discount_type") || "fixed").trim(),
            discount_value: Number(form.get("discount_value") || 0),
            active: String(form.get("active") || "true") === "true",
            notes: String(form.get("notes") || "").trim(),
          },
        });
        promoForm.reset();
        setFeedback("promo-feedback", "Promo saved.", "success");
        await refreshDashboard();
      } catch (error) {
        setFeedback("promo-feedback", error instanceof Error ? error.message : "Promo save failed.", "error");
      }
    });
  }

  const adminUserForm = document.getElementById("admin-user-form");
  if (adminUserForm instanceof HTMLFormElement) {
    adminUserForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!isSuperAdmin()) {
        setFeedback("admin-user-feedback", "Only super admins can manage admin users.", "error");
        return;
      }
      try {
        setFeedback("admin-user-feedback", "Saving admin user...");
        const form = new FormData(adminUserForm);
        await adminRequest("save_admin_user", {
          admin_user: {
            username: String(form.get("username") || "").trim(),
            passcode: String(form.get("passcode") || "").trim(),
            access_level: String(form.get("access_level") || "admin").trim(),
            telegram_id: String(form.get("telegram_id") || "").trim(),
            telegram_username: String(form.get("telegram_username") || "").trim(),
          },
        });
        adminUserForm.reset();
        setFeedback("admin-user-feedback", "Admin user saved.", "success");
        await refreshDashboard();
      } catch (error) {
        setFeedback("admin-user-feedback", error instanceof Error ? error.message : "Admin save failed.", "error");
      }
    });
  }
}

async function init() {
  state.session = readSession();
  bindEvents();
  renderAuthState();
  setActiveTab(state.activeTab);
  if (!state.session?.username) {
    return;
  }
  try {
    await refreshDashboard();
  } catch (error) {
    writeSession(null);
    state.session = null;
    renderAuthState();
    setFeedback("admin-login-feedback", error instanceof Error ? error.message : "Admin session expired.", "error");
  }
}

window.addEventListener("DOMContentLoaded", init);
