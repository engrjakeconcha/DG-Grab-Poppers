"use strict";

const ADMIN_SESSION_KEY = "daddygrab_admin_session";
const ADMIN_API_URL = "/api/admin/daddygrab-admin";
const ORDER_STATUSES = [
  "Awaiting Payment Confirmation",
  "Payment Confirmed",
  "Preparing",
  "For Delivery",
  "Out for Delivery",
  "Delivered",
];
const PAYMENT_METHOD_OPTIONS = ["Maya", "GCash", "Bank Transfer", "Cash on Delivery"];
const INVENTORY_CATEGORIES = ["poppers", "supplements", "toys", "lubricants"];

const state = {
  session: null,
  dashboard: null,
  activeTab: "orders",
  orderFilter: "pending",
  orderSearch: "",
  inventoryFilter: "all",
  reportDateFrom: "",
  reportDateTo: "",
  tickets: [],
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

function titleize(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function normalizeOrderStatus(value) {
  const raw = String(value || "").trim().toLowerCase();
  if (!raw) return "Awaiting Payment Confirmation";
  if (raw === "pending confirmation" || raw === "pending" || raw === "awaiting payment" || raw === "awaiting_payment") {
    return "Awaiting Payment Confirmation";
  }
  if (raw === "confirmed" || raw === "payment confirmed" || raw === "paid") {
    return "Payment Confirmed";
  }
  if (raw === "preparing") return "Preparing";
  if (raw === "for delivery") return "For Delivery";
  if (raw === "out for delivery") return "Out for Delivery";
  if (raw === "delivered" || raw === "completed") return "Delivered";
  return titleize(value);
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
    // ignore storage failures
  }
}

function isSuperAdmin() {
  return state.session?.role === "super_admin";
}

function setFeedback(targetId, message, tone = "") {
  const node = document.getElementById(targetId);
  if (!node) return;
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

function clearLists() {
  [
    "admin-orders",
    "admin-tickets",
    "admin-inventory",
    "admin-promos",
    "admin-users",
    "reporting-summary",
  ].forEach((id) => {
    const node = document.getElementById(id);
    if (node) node.innerHTML = "";
  });
  [
    "admin-orders-empty",
    "admin-tickets-empty",
    "admin-inventory-empty",
    "admin-promos-empty",
    "admin-users-empty",
  ].forEach((id) => {
    const node = document.getElementById(id);
    if (node) node.hidden = true;
  });
}

function resetAdminState() {
  state.dashboard = null;
  state.tickets = [];
  state.inventory = [];
  state.promos = [];
  state.adminUsers = [];
  clearLists();
  applyOverview();
  closeAdminModal();
}

function renderAuthState() {
  const auth = document.getElementById("admin-auth");
  const dashboard = document.getElementById("admin-dashboard");
  const welcome = document.getElementById("admin-welcome");
  const roleLabel = document.getElementById("admin-role-label");
  const loggedIn = Boolean(state.session?.username);

  if (auth) auth.hidden = loggedIn;
  if (dashboard) dashboard.hidden = !loggedIn;
  if (welcome) welcome.textContent = loggedIn ? `Welcome, ${state.session.username}` : "Welcome";
  if (roleLabel) {
    roleLabel.textContent = !loggedIn
      ? ""
      : state.session.role === "super_admin"
        ? "Super Admin access is active. Rotate seeded passwords before production."
        : "Admin access is active. Order updates only, with view-only access for finance and promos.";
  }

  document.querySelectorAll("[data-admin-panel='admins']").forEach((panel) => {
    panel.hidden = !loggedIn || !isSuperAdmin() || state.activeTab !== "admins";
  });

  const viewSelect = document.getElementById("admin-view-select");
  if (viewSelect) {
    const adminOption = viewSelect.querySelector("option[value='admins']");
    if (adminOption) adminOption.hidden = !isSuperAdmin();
  }

  ["inventory-create", "promo-create", "admin-user-create"].forEach((id) => {
    const button = document.getElementById(id);
    if (button) {
      button.hidden = !loggedIn || (id === "admin-user-create" ? !isSuperAdmin() : !isSuperAdmin());
    }
  });
}

function setActiveTab(tabName) {
  const resolvedTab = tabName === "admins" && !isSuperAdmin() ? "orders" : tabName;
  state.activeTab = resolvedTab;
  document.querySelectorAll("[data-admin-tab]").forEach((button) => {
    const active = button.dataset.adminTab === resolvedTab;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", active ? "true" : "false");
  });
  document.querySelectorAll("[data-admin-panel]").forEach((panel) => {
    const panelName = panel.dataset.adminPanel;
    const isAdminsPanel = panelName === "admins";
    panel.hidden = panelName !== resolvedTab || (isAdminsPanel && !isSuperAdmin());
  });
  const viewSelect = document.getElementById("admin-view-select");
  if (viewSelect) {
    viewSelect.value = resolvedTab;
  }
}

function applyOverview() {
  const summary = state.dashboard?.summary || {};
  const report = state.dashboard?.report || {};
  const set = (id, value) => {
    const node = document.getElementById(id);
    if (node) node.textContent = value;
  };
  set("metric-pending", String(summary.pending_orders ?? 0));
  set("metric-awaiting", String(summary.awaiting_payment ?? 0));
  set("metric-sales", peso(report.gross_sales || 0));
  set("metric-aov", peso(report.average_order_value || 0));
  set("metric-sales-copy", `${report.order_count || 0} orders in report snapshot.`);
  set("metric-aov-copy", "Track totals, queue health, and fulfillment progress here.");
}

function createListRow({ title, meta = "", badge = "", buttonLabel = "Details", onClick }) {
  const row = document.createElement("article");
  row.className = "admin-list-row";
  row.innerHTML = `
    <div class="admin-list-row__copy">
      <strong class="admin-list-row__title"></strong>
      <p class="admin-list-row__meta"></p>
    </div>
    <div class="admin-list-row__actions">
      <span class="pill admin-list-row__badge"></span>
      <button class="cta cta--secondary admin-list-row__button" type="button">${buttonLabel}</button>
    </div>
  `;
  row.querySelector(".admin-list-row__title").textContent = title;
  row.querySelector(".admin-list-row__meta").textContent = meta;
  const badgeNode = row.querySelector(".admin-list-row__badge");
  if (badge) {
    badgeNode.textContent = badge;
  } else {
    badgeNode.hidden = true;
  }
  row.querySelector(".admin-list-row__button").addEventListener("click", onClick);
  return row;
}

function createTableRow({ primary, secondary, badge = "", buttonLabel = "Details", onClick }) {
  const row = document.createElement("article");
  row.className = "admin-table";
  row.innerHTML = `
    <div class="admin-table__cell admin-table__cell--primary"></div>
    <div class="admin-table__cell admin-table__cell--secondary"></div>
    <div class="admin-table__cell admin-table__cell--action">
      <span class="pill admin-table__badge"></span>
      <button class="cta cta--secondary admin-list-row__button" type="button">${buttonLabel}</button>
    </div>
  `;
  row.querySelector(".admin-table__cell--primary").textContent = primary;
  row.querySelector(".admin-table__cell--secondary").textContent = secondary;
  const badgeNode = row.querySelector(".admin-table__badge");
  if (badge) {
    badgeNode.textContent = badge;
  } else {
    badgeNode.hidden = true;
  }
  row.querySelector("button").addEventListener("click", onClick);
  return row;
}

function openAdminModal({ kicker = "Details", title = "Details", body }) {
  const wrap = document.getElementById("admin-modal");
  const kickerNode = document.getElementById("admin-modal-kicker");
  const titleNode = document.getElementById("admin-modal-title");
  const bodyNode = document.getElementById("admin-modal-body");
  if (!wrap || !bodyNode) return;
  kickerNode.textContent = kicker;
  titleNode.textContent = title;
  bodyNode.innerHTML = "";
  if (typeof body === "string") {
    bodyNode.innerHTML = body;
  } else if (body instanceof Node) {
    bodyNode.appendChild(body);
  }
  wrap.hidden = false;
}

function closeAdminModal() {
  const wrap = document.getElementById("admin-modal");
  const bodyNode = document.getElementById("admin-modal-body");
  if (bodyNode) bodyNode.innerHTML = "";
  if (wrap) wrap.hidden = true;
}

function renderOrders() {
  const list = document.getElementById("admin-orders");
  const empty = document.getElementById("admin-orders-empty");
  if (!list) return;
  list.innerHTML = "";
  const orders = Array.isArray(state.dashboard?.orders) ? state.dashboard.orders : [];
  const filtered = orders.filter((order) => {
    const normalizedStatus = normalizeOrderStatus(order.order_status);
    if (state.orderFilter === "pending" && normalizedStatus !== "Awaiting Payment Confirmation") return false;
    if (state.orderFilter === "payment_confirmed" && normalizedStatus !== "Payment Confirmed") return false;
    if (state.orderFilter === "preparing" && normalizedStatus !== "Preparing") return false;
    if (state.orderFilter === "for_delivery" && normalizedStatus !== "For Delivery") return false;
    if (state.orderFilter === "out_for_delivery" && normalizedStatus !== "Out for Delivery") return false;
    if (state.orderFilter === "delivered" && normalizedStatus !== "Delivered") return false;
    if (state.orderFilter === "awaiting_payment" && String(order.payment_status || "").toLowerCase() !== "awaiting_payment")
      return false;
    if (!state.orderSearch) return true;
    const haystack = [order.order_id, order.customer_name, order.phone_number, order.telegram_username]
      .join(" ")
      .toLowerCase();
    return haystack.includes(state.orderSearch.toLowerCase());
  });
  if (empty) empty.hidden = filtered.length > 0;
  filtered.forEach((order) => {
    list.appendChild(
      createTableRow({
        primary: order.order_id || "-",
        secondary: order.customer_name || "-",
        badge: normalizeOrderStatus(order.order_status),
        onClick: () => openOrderModal(order),
      })
    );
  });
}

function renderOrderItemEditor(items) {
  const wrap = document.createElement("div");
  wrap.className = "admin-modal-stack";
  const rows = document.createElement("div");
  rows.className = "admin-modal-stack";

  const addRow = (item = null) => {
    const row = document.createElement("div");
    row.className = "admin-line-editor";
    row.innerHTML = `
      <label class="field">
        <span>Product</span>
        <select class="admin-order-item-sku"></select>
      </label>
      <label class="field">
        <span>Qty</span>
        <input class="admin-order-item-qty" type="number" min="1" step="1" value="1" />
      </label>
      <button class="cta cta--secondary admin-line-editor__remove" type="button">Remove</button>
    `;
    const select = row.querySelector(".admin-order-item-sku");
    state.inventory.forEach((product) => {
      const option = document.createElement("option");
      option.value = product.sku;
      option.textContent = `${product.name} (${peso(product.price)})`;
      if (product.sku === String(item?.sku || "").toUpperCase()) option.selected = true;
      select.appendChild(option);
    });
    row.querySelector(".admin-order-item-qty").value = item?.quantity || item?.qty || 1;
    row.querySelector(".admin-line-editor__remove").addEventListener("click", () => {
      row.remove();
      if (!rows.children.length) addRow();
    });
    rows.appendChild(row);
  };

  (items || []).forEach((item) => addRow(item));
  if (!rows.children.length) addRow();

  const addButton = document.createElement("button");
  addButton.type = "button";
  addButton.className = "cta cta--secondary";
  addButton.textContent = "Add Item";
  addButton.addEventListener("click", () => addRow());
  wrap.append(rows, addButton);
  wrap.collectItems = () =>
    Array.from(rows.querySelectorAll(".admin-line-editor")).map((row) => ({
      sku: row.querySelector(".admin-order-item-sku").value,
      quantity: Number(row.querySelector(".admin-order-item-qty").value || 1),
    }));
  return wrap;
}

function buildOrderModal(order) {
  const superAdmin = isSuperAdmin();
  const itemEditor = superAdmin ? renderOrderItemEditor(order.items || []) : null;
  const wrap = document.createElement("div");
  wrap.className = "admin-modal-stack";
  wrap.innerHTML = `
    <div class="admin-modal-block">
      <div class="form-grid">
        <label class="field">
          <span>Name of Recipient</span>
          <input id="modal-order-customer" type="text" />
        </label>
        <label class="field">
          <span>Phone Number</span>
          <input id="modal-order-phone" type="text" />
        </label>
      </div>
      <div class="form-grid">
        <label class="field">
          <span>Delivery Area</span>
          <input id="modal-order-area" type="text" />
        </label>
        <label class="field">
          <span>Payment Method</span>
          <select id="modal-order-payment-method"></select>
        </label>
      </div>
      <label class="field">
        <span>Delivery Address</span>
        <textarea id="modal-order-address" rows="3"></textarea>
      </label>
      <label class="field">
        <span>Order Notes</span>
        <textarea id="modal-order-notes" rows="2" placeholder="Internal or order notes"></textarea>
      </label>
      <p class="admin-note"><strong>Telegram</strong><br>${order.telegram_username ? `@${order.telegram_username}<br>` : ""}${order.telegram_id || order.telegram_user_id || "No Telegram ID linked."}</p>
      <p class="admin-note"><strong>Total</strong><br>${peso(order.total)}</p>
    </div>
    <div class="form-grid">
      <label class="field">
        <span>Status</span>
        <select id="modal-order-status"></select>
      </label>
      <label class="field">
        <span>Tracking Number</span>
        <input id="modal-order-tracking" type="text" placeholder="Optional tracking number" />
      </label>
    </div>
    <label class="field">
      <span>Upload Order Photo</span>
      <input id="modal-order-photo" type="file" accept="image/*" />
      <small class="field-hint">Upload hook stays available here for the next phase.</small>
    </label>
    <div class="admin-modal-block" id="modal-order-items-block">
      <p class="admin-note"><strong>Order Items</strong></p>
    </div>
    <label class="field">
      <span>Message Customer</span>
      <textarea id="modal-order-message" rows="3" placeholder="Type a delivery update or support note."></textarea>
    </label>
    <div class="admin-toolbar__actions">
      <button id="modal-order-save" class="cta cta--primary" type="button">Save Update</button>
      <button id="modal-order-message-send" class="cta cta--secondary" type="button">Send Message</button>
      <a class="cta cta--secondary" href="${order.tracking_link || `/track?order_id=${encodeURIComponent(order.order_id || "")}`}" target="_blank" rel="noreferrer">Track Page</a>
    </div>
    <div id="modal-order-feedback" class="checkout-feedback" aria-live="polite"></div>
  `;
  const statusSelect = wrap.querySelector("#modal-order-status");
  ORDER_STATUSES.forEach((status) => {
    const option = document.createElement("option");
    option.value = status;
    option.textContent = status;
    if (status === normalizeOrderStatus(order.order_status)) option.selected = true;
    statusSelect.appendChild(option);
  });
  const paymentMethodSelect = wrap.querySelector("#modal-order-payment-method");
  PAYMENT_METHOD_OPTIONS.forEach((method) => {
    const option = document.createElement("option");
    option.value = method;
    option.textContent = method;
    if (method === (order.payment_method || "")) option.selected = true;
    paymentMethodSelect.appendChild(option);
  });
  wrap.querySelector("#modal-order-customer").value = order.customer_name || "";
  wrap.querySelector("#modal-order-phone").value = order.phone_number || "";
  wrap.querySelector("#modal-order-area").value = order.delivery_area || "Metro Manila";
  wrap.querySelector("#modal-order-address").value = order.delivery_address || "";
  wrap.querySelector("#modal-order-notes").value = order.notes || "";
  wrap.querySelector("#modal-order-tracking").value = order.tracking_number || "";
  const itemsBlock = wrap.querySelector("#modal-order-items-block");
  if (superAdmin && itemEditor) {
    itemsBlock.appendChild(itemEditor);
  } else {
    const note = document.createElement("p");
    note.className = "admin-note";
    note.innerHTML =
      (order.items || []).map((item) => `${item.name} x${item.quantity || item.qty}`).join("<br>") ||
      "No items attached.";
    itemsBlock.appendChild(note);
  }
  if (!superAdmin) {
    [
      "#modal-order-customer",
      "#modal-order-phone",
      "#modal-order-area",
      "#modal-order-address",
      "#modal-order-payment-method",
      "#modal-order-notes",
      "#modal-order-photo",
    ].forEach((selector) => {
      const node = wrap.querySelector(selector);
      if (node) node.disabled = true;
    });
  }
  wrap.querySelector("#modal-order-save").addEventListener("click", async () => {
    try {
      setFeedback("modal-order-feedback", "Saving update...");
      await adminRequest("update_order", {
        order_id: order.order_id,
        status: wrap.querySelector("#modal-order-status").value,
        tracking_number: wrap.querySelector("#modal-order-tracking").value,
        customer_name: wrap.querySelector("#modal-order-customer").value,
        phone_number: wrap.querySelector("#modal-order-phone").value,
        delivery_area: wrap.querySelector("#modal-order-area").value,
        delivery_address: wrap.querySelector("#modal-order-address").value,
        payment_method: wrap.querySelector("#modal-order-payment-method").value,
        notes: wrap.querySelector("#modal-order-notes").value,
        items: superAdmin && itemEditor ? itemEditor.collectItems() : undefined,
      });
      setFeedback("modal-order-feedback", "Order updated.", "success");
      await refreshDashboard();
    } catch (error) {
      setFeedback("modal-order-feedback", error instanceof Error ? error.message : "Failed to update order.", "error");
    }
  });
  wrap.querySelector("#modal-order-message-send").addEventListener("click", async () => {
    try {
      setFeedback("modal-order-feedback", "Sending message...");
      await adminRequest("contact_customer", {
        order_id: order.order_id,
        message: wrap.querySelector("#modal-order-message").value,
      });
      setFeedback("modal-order-feedback", "Customer message sent.", "success");
    } catch (error) {
      setFeedback("modal-order-feedback", error instanceof Error ? error.message : "Failed to contact customer.", "error");
    }
  });
  return wrap;
}

function openOrderModal(order) {
  openAdminModal({
    kicker: "Order Details",
    title: order.order_id || "Order",
    body: buildOrderModal(order),
  });
}

function renderTickets() {
  const list = document.getElementById("admin-tickets");
  const empty = document.getElementById("admin-tickets-empty");
  if (!list) return;
  list.innerHTML = "";
  const tickets = Array.isArray(state.tickets) ? state.tickets : [];
  if (empty) empty.hidden = tickets.length > 0;
  tickets.forEach((ticket) => {
    list.appendChild(
      createListRow({
        title: ticket.ticket_id || "-",
        meta: [ticket.customer_name || "-", ticket.mobile_number || "-", ticket.issue_type || "-"].join(" - "),
        badge: (ticket.status || "open").replace(/_/g, " "),
        onClick: () => openTicketModal(ticket),
      })
    );
  });
}

function buildTicketModal(ticket) {
  const wrap = document.createElement("div");
  wrap.className = "admin-modal-stack";
  wrap.innerHTML = `
    <div class="admin-modal-block">
      <p class="admin-note"><strong>Customer</strong><br>${ticket.customer_name || "-"}${ticket.username ? `<br>@${ticket.username}` : ""}${ticket.mobile_number ? `<br>${ticket.mobile_number}` : ""}</p>
      <p class="admin-note"><strong>Summary</strong><br>Product: ${ticket.product_type || "-"}<br>Issue: ${ticket.issue_type || "-"}<br>Source: ${ticket.source || "-"}</p>
      <p class="admin-note"><strong>Message</strong><br>${ticket.message || "-"}</p>
    </div>
    <label class="field">
      <span>Reply to Customer</span>
      <textarea id="modal-ticket-reply" rows="4" placeholder="Type a support reply for Telegram."></textarea>
    </label>
    <div class="admin-toolbar__actions">
      <button id="modal-ticket-send" class="cta cta--primary" type="button">Send Reply</button>
    </div>
    <div id="modal-ticket-feedback" class="checkout-feedback" aria-live="polite"></div>
  `;
  wrap.querySelector("#modal-ticket-send").addEventListener("click", async () => {
    try {
      setFeedback("modal-ticket-feedback", "Sending reply...");
      await adminRequest("reply_ticket", {
        ticket_id: ticket.ticket_id,
        message: wrap.querySelector("#modal-ticket-reply").value,
      });
      setFeedback("modal-ticket-feedback", "Reply sent.", "success");
      await refreshDashboard();
    } catch (error) {
      setFeedback("modal-ticket-feedback", error instanceof Error ? error.message : "Failed to send reply.", "error");
    }
  });
  return wrap;
}

function openTicketModal(ticket) {
  openAdminModal({
    kicker: "Ticket Details",
    title: ticket.ticket_id || "Ticket",
    body: buildTicketModal(ticket),
  });
}

function renderInventory() {
  const list = document.getElementById("admin-inventory");
  const empty = document.getElementById("admin-inventory-empty");
  if (!list) return;
  list.innerHTML = "";
  const inventory = state.inventory.filter((product) => {
    if (state.inventoryFilter === "all") return true;
    return String(product.category || "").toLowerCase() === state.inventoryFilter;
  });
  if (empty) empty.hidden = inventory.length > 0;
  inventory.forEach((product) => {
    list.appendChild(
      createTableRow({
        primary: product.name || "-",
        secondary: peso(product.price || 0),
        badge: titleize(product.category || "-"),
        onClick: () => openInventoryModal(product),
      })
    );
  });
}

function buildInventoryModal(product = null) {
  const isNew = !product;
  const wrap = document.createElement("div");
  wrap.className = "admin-modal-stack";
  wrap.innerHTML = `
    <div class="form-grid">
      <label class="field"><span>SKU</span><input id="modal-product-sku" type="text" required /></label>
      <label class="field"><span>Category</span>
        <select id="modal-product-category">
          <option value="poppers">Poppers</option>
          <option value="supplements">Supplements</option>
          <option value="toys">Toys</option>
          <option value="lubricants">Lubricants</option>
        </select>
      </label>
    </div>
    <div class="form-grid">
      <label class="field"><span>Name</span><input id="modal-product-name" type="text" required /></label>
      <label class="field"><span>Price</span><input id="modal-product-price" type="number" min="0" step="0.01" /></label>
    </div>
    <div class="form-grid">
      <label class="field"><span>Stock</span><input id="modal-product-stock" type="number" min="0" step="1" /></label>
      <label class="field"><span>Status</span>
        <select id="modal-product-active">
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
      </label>
    </div>
    <label class="field"><span>Description</span><textarea id="modal-product-description" rows="3"></textarea></label>
    <label class="field"><span>Image URL</span><input id="modal-product-image-url" type="url" placeholder="https://..." /></label>
    <label class="field"><span>Or Upload Image</span><input id="modal-product-image-file" type="file" accept="image/*" /></label>
    <div class="admin-toolbar__actions">
      <button id="modal-product-save" class="cta cta--primary" type="button">Save Product</button>
      <button id="modal-product-delete" class="cta cta--secondary" type="button">Delete</button>
    </div>
    <div id="modal-product-feedback" class="checkout-feedback" aria-live="polite"></div>
  `;
  wrap.querySelector("#modal-product-sku").value = product?.sku || "";
  wrap.querySelector("#modal-product-category").value = product?.category || "poppers";
  wrap.querySelector("#modal-product-name").value = product?.name || "";
  wrap.querySelector("#modal-product-price").value = product?.price || "";
  wrap.querySelector("#modal-product-stock").value = product?.stock || 0;
  wrap.querySelector("#modal-product-active").value = String(product?.active !== false);
  wrap.querySelector("#modal-product-description").value = product?.description || "";
  wrap.querySelector("#modal-product-image-url").value = product?.image_url || "";
  const deleteButton = wrap.querySelector("#modal-product-delete");
  deleteButton.hidden = isNew || !isSuperAdmin();
  if (!isSuperAdmin()) {
    wrap.querySelectorAll("input, select, textarea, button").forEach((node) => {
      if (node.id !== "modal-product-delete") node.disabled = true;
    });
  }
  wrap.querySelector("#modal-product-save").addEventListener("click", async () => {
    if (!isSuperAdmin()) return;
    try {
      setFeedback("modal-product-feedback", "Saving product...");
      let imageUrl = wrap.querySelector("#modal-product-image-url").value.trim();
      const file = wrap.querySelector("#modal-product-image-file").files?.[0];
      if (!imageUrl && file) {
        imageUrl = await fileToDataUrl(file);
      }
      await adminRequest("save_product", {
        product: {
          sku: wrap.querySelector("#modal-product-sku").value.trim(),
          category: wrap.querySelector("#modal-product-category").value.trim(),
          name: wrap.querySelector("#modal-product-name").value.trim(),
          price: Number(wrap.querySelector("#modal-product-price").value || 0),
          stock: Number(wrap.querySelector("#modal-product-stock").value || 0),
          description: wrap.querySelector("#modal-product-description").value.trim(),
          image_url: imageUrl,
          active: wrap.querySelector("#modal-product-active").value === "true",
        },
      });
      setFeedback("inventory-feedback", "Product saved.", "success");
      setFeedback("modal-product-feedback", "Product saved.", "success");
      await refreshDashboard();
    } catch (error) {
      setFeedback("modal-product-feedback", error instanceof Error ? error.message : "Save failed.", "error");
    }
  });
  deleteButton.addEventListener("click", async () => {
    try {
      setFeedback("modal-product-feedback", "Deleting product...");
      await adminRequest("delete_product", { sku: product.sku });
      setFeedback("inventory-feedback", "Product deleted.", "success");
      closeAdminModal();
      await refreshDashboard();
    } catch (error) {
      setFeedback("modal-product-feedback", error instanceof Error ? error.message : "Delete failed.", "error");
    }
  });
  return wrap;
}

function openInventoryModal(product) {
  openAdminModal({
    kicker: "Inventory Details",
    title: product?.name || "New Product",
    body: buildInventoryModal(product),
  });
}

function renderPromos() {
  const list = document.getElementById("admin-promos");
  const empty = document.getElementById("admin-promos-empty");
  if (!list) return;
  list.innerHTML = "";
  if (empty) empty.hidden = state.promos.length > 0;
  state.promos.forEach((promo) => {
    list.appendChild(
      createListRow({
        title: promo.code || "-",
        meta:
          promo.discount_type === "percent"
            ? `${promo.discount_value}% off`
            : `${peso(promo.discount_value || 0)} off`,
        badge: promo.active ? "Active" : "Inactive",
        onClick: () => openPromoModal(promo),
      })
    );
  });
}

function buildPromoModal(promo = null) {
  const wrap = document.createElement("div");
  wrap.className = "admin-modal-stack";
  wrap.innerHTML = `
    <div class="form-grid">
      <label class="field"><span>Code</span><input id="modal-promo-code" type="text" required /></label>
      <label class="field"><span>Discount Type</span>
        <select id="modal-promo-type">
          <option value="fixed">Fixed</option>
          <option value="percent">Percent</option>
        </select>
      </label>
    </div>
    <div class="form-grid">
      <label class="field"><span>Discount Value</span><input id="modal-promo-value" type="number" min="0" step="0.01" /></label>
      <label class="field"><span>Status</span>
        <select id="modal-promo-active">
          <option value="true">Active</option>
          <option value="false">Inactive</option>
        </select>
      </label>
    </div>
    <label class="field"><span>Notes</span><textarea id="modal-promo-notes" rows="3"></textarea></label>
    <div class="admin-toolbar__actions">
      <button id="modal-promo-save" class="cta cta--primary" type="button">Save Promo</button>
    </div>
    <div id="modal-promo-feedback" class="checkout-feedback" aria-live="polite"></div>
  `;
  wrap.querySelector("#modal-promo-code").value = promo?.code || "";
  wrap.querySelector("#modal-promo-type").value = promo?.discount_type || "fixed";
  wrap.querySelector("#modal-promo-value").value = promo?.discount_value || "";
  wrap.querySelector("#modal-promo-active").value = String(promo?.active !== false);
  wrap.querySelector("#modal-promo-notes").value = promo?.notes || "";
  if (!isSuperAdmin()) {
    wrap.querySelectorAll("input, select, textarea, button").forEach((node) => (node.disabled = true));
  }
  wrap.querySelector("#modal-promo-save").addEventListener("click", async () => {
    if (!isSuperAdmin()) return;
    try {
      setFeedback("modal-promo-feedback", "Saving promo...");
      await adminRequest("save_promo", {
        promo: {
          code: wrap.querySelector("#modal-promo-code").value.trim(),
          discount_type: wrap.querySelector("#modal-promo-type").value.trim(),
          discount_value: Number(wrap.querySelector("#modal-promo-value").value || 0),
          active: wrap.querySelector("#modal-promo-active").value === "true",
          notes: wrap.querySelector("#modal-promo-notes").value.trim(),
        },
      });
      setFeedback("promo-feedback", "Promo saved.", "success");
      setFeedback("modal-promo-feedback", "Promo saved.", "success");
      await refreshDashboard();
    } catch (error) {
      setFeedback("modal-promo-feedback", error instanceof Error ? error.message : "Promo save failed.", "error");
    }
  });
  return wrap;
}

function openPromoModal(promo) {
  openAdminModal({
    kicker: "Promo Details",
    title: promo?.code || "New Promo",
    body: buildPromoModal(promo),
  });
}

function renderAdminUsers() {
  const list = document.getElementById("admin-users");
  const empty = document.getElementById("admin-users-empty");
  const panel = document.querySelector("[data-admin-panel='admins']");
  if (!list) return;
  list.innerHTML = "";
  if (!isSuperAdmin()) {
    if (panel instanceof HTMLElement) panel.hidden = true;
    return;
  }
  if (empty) empty.hidden = state.adminUsers.length > 0;
  state.adminUsers.forEach((admin) => {
    list.appendChild(
      createListRow({
        title: admin.username || "-",
        meta: [admin.telegram_username ? `@${admin.telegram_username}` : "", admin.telegram_id || ""].filter(Boolean).join(" - ") || "No Telegram link saved.",
        badge: admin.access_level === "super_admin" ? "Super Admin" : "Admin",
        onClick: () => openAdminUserModal(admin),
      })
    );
  });
}

function buildAdminUserModal(admin = null) {
  const wrap = document.createElement("div");
  wrap.className = "admin-modal-stack";
  wrap.innerHTML = `
    <div class="form-grid">
      <label class="field"><span>Username</span><input id="modal-admin-username" type="text" required /></label>
      <label class="field"><span>Passcode</span><input id="modal-admin-passcode" type="password" required /></label>
    </div>
    <div class="form-grid">
      <label class="field"><span>Access Level</span>
        <select id="modal-admin-role">
          <option value="admin">Admin</option>
          <option value="super_admin">Super Admin</option>
        </select>
      </label>
      <label class="field"><span>Telegram ID</span><input id="modal-admin-telegram-id" type="text" /></label>
    </div>
    <label class="field"><span>Telegram Username</span><input id="modal-admin-telegram-username" type="text" placeholder="@username" /></label>
    <div class="admin-toolbar__actions">
      <button id="modal-admin-save" class="cta cta--primary" type="button">Save Admin User</button>
    </div>
    <div id="modal-admin-feedback" class="checkout-feedback" aria-live="polite"></div>
  `;
  wrap.querySelector("#modal-admin-username").value = admin?.username || "";
  wrap.querySelector("#modal-admin-passcode").value = "";
  wrap.querySelector("#modal-admin-role").value = admin?.access_level || "admin";
  wrap.querySelector("#modal-admin-telegram-id").value = admin?.telegram_id || "";
  wrap.querySelector("#modal-admin-telegram-username").value = admin?.telegram_username || "";
  wrap.querySelector("#modal-admin-save").addEventListener("click", async () => {
    try {
      setFeedback("modal-admin-feedback", "Saving admin user...");
      await adminRequest("save_admin_user", {
        admin_user: {
          username: wrap.querySelector("#modal-admin-username").value.trim(),
          passcode: wrap.querySelector("#modal-admin-passcode").value.trim(),
          access_level: wrap.querySelector("#modal-admin-role").value.trim(),
          telegram_id: wrap.querySelector("#modal-admin-telegram-id").value.trim(),
          telegram_username: wrap.querySelector("#modal-admin-telegram-username").value.trim(),
        },
      });
      setFeedback("admin-user-feedback", "Admin user saved.", "success");
      setFeedback("modal-admin-feedback", "Admin user saved.", "success");
      await refreshDashboard();
    } catch (error) {
      setFeedback("modal-admin-feedback", error instanceof Error ? error.message : "Admin save failed.", "error");
    }
  });
  return wrap;
}

function openAdminUserModal(admin) {
  openAdminModal({
    kicker: "Admin Details",
    title: admin?.username || "New Admin",
    body: buildAdminUserModal(admin),
  });
}

function renderReports() {
  const summary = document.getElementById("reporting-summary");
  if (!summary) return;
  const report = state.dashboard?.report || {};
  summary.innerHTML = "";
  [
    `Delivered Sales - ${peso(report.gross_sales || 0)}`,
    `Delivered Orders - ${report.order_count || 0}`,
    `Average Delivered Order - ${peso(report.average_order_value || 0)}`,
    `Statuses - ${Object.entries(report.by_status || {}).map(([key, value]) => `${key}: ${value}`).join(" • ") || "No data"}`,
  ].forEach((line) => {
    const row = document.createElement("article");
    row.className = "admin-list-row admin-list-row--report";
    row.innerHTML = `<div class="admin-list-row__copy"><strong class="admin-list-row__title">${line.split(" - ")[0]}</strong><p class="admin-list-row__meta">${line.split(" - ").slice(1).join(" - ")}</p></div>`;
    summary.appendChild(row);
  });
}

function downloadCsv(filename, rows) {
  const csv = rows
    .map((row) =>
      row
        .map((value) => `"${String(value ?? "").replace(/"/g, '""')}"`)
        .join(",")
    )
    .join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

function exportSalesReport() {
  const orders = (Array.isArray(state.dashboard?.orders) ? state.dashboard.orders : []).filter(
    (order) => normalizeOrderStatus(order.order_status) === "Delivered"
  );
  const rows = [
    ["order_number", "customer_name", "phone_number", "status", "payment_method", "total", "created_at"],
    ...orders.map((order) => [
      order.order_id,
      order.customer_name,
      order.phone_number,
      order.order_status,
      order.payment_method,
      Number(order.total || 0).toFixed(2),
      order.created_at || "",
    ]),
  ];
  downloadCsv("daddygrab-sales-report.csv", rows);
}

function exportInventoryReport() {
  const rows = [
    ["sku", "category", "name", "price", "stock", "active"],
    ...state.inventory.map((product) => [
      product.sku,
      product.category,
      product.name,
      Number(product.price || 0).toFixed(2),
      product.stock,
      product.active ? "true" : "false",
    ]),
  ];
  downloadCsv("daddygrab-inventory-report.csv", rows);
}

async function refreshDashboard() {
  const result = await adminRequest("dashboard", {
    status: state.orderFilter,
    search: state.orderSearch,
    limit: 100,
    date_from: state.reportDateFrom,
    date_to: state.reportDateTo,
  });
  state.dashboard = result;
  state.tickets = result.tickets || [];
  state.inventory = result.inventory || [];
  state.promos = result.promos || [];
  state.adminUsers = result.admin_users || [];
  applyOverview();
  renderOrders();
  renderTickets();
  renderInventory();
  renderPromos();
  renderAdminUsers();
  renderReports();
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
    resetAdminState();
    setActiveTab("orders");
    renderAuthState();
  });

  document.querySelectorAll("[data-admin-tab]").forEach((button) => {
    button.addEventListener("click", () => {
      setActiveTab(button.dataset.adminTab || "orders");
      closeAdminModal();
    });
  });

  document.getElementById("admin-view-select")?.addEventListener("change", (event) => {
    setActiveTab(event.target.value || "orders");
    closeAdminModal();
  });

  document.querySelectorAll("[data-admin-modal-close]").forEach((button) => {
    button.addEventListener("click", closeAdminModal);
  });

  document.getElementById("order-filter")?.addEventListener("change", async (event) => {
    state.orderFilter = event.target.value;
    await refreshDashboard();
  });

  document.getElementById("order-search")?.addEventListener("input", () => {
    state.orderSearch = document.getElementById("order-search").value.trim();
    renderOrders();
  });

  document.getElementById("inventory-filter")?.addEventListener("change", (event) => {
    state.inventoryFilter = event.target.value || "all";
    renderInventory();
  });

  document.getElementById("inventory-create")?.addEventListener("click", () => openInventoryModal(null));
  document.getElementById("promo-create")?.addEventListener("click", () => openPromoModal(null));
  document.getElementById("admin-user-create")?.addEventListener("click", () => openAdminUserModal(null));

  document.getElementById("report-apply")?.addEventListener("click", async () => {
    state.reportDateFrom = document.getElementById("report-date-from").value;
    state.reportDateTo = document.getElementById("report-date-to").value;
    try {
      setFeedback("reporting-feedback", "Refreshing report...");
      await refreshDashboard();
      setFeedback("reporting-feedback", "Report updated.", "success");
    } catch (error) {
      setFeedback("reporting-feedback", error instanceof Error ? error.message : "Report refresh failed.", "error");
    }
  });

  document.getElementById("export-sales-report")?.addEventListener("click", exportSalesReport);
  document.getElementById("export-inventory-report")?.addEventListener("click", exportInventoryReport);
}

async function init() {
  state.session = readSession();
  bindEvents();
  renderAuthState();
  setActiveTab(state.activeTab);
  if (!state.session?.username) return;
  try {
    await refreshDashboard();
  } catch (error) {
    writeSession(null);
    state.session = null;
    resetAdminState();
    renderAuthState();
    setFeedback("admin-login-feedback", error instanceof Error ? error.message : "Admin session expired.", "error");
  }
}

window.addEventListener("DOMContentLoaded", init);
