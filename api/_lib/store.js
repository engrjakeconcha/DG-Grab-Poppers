"use strict";

const { randomUUID, scryptSync, timingSafeEqual } = require("node:crypto");
const { bootstrapDatabase, query, withClient } = require("./db");

function cleanEnv(value, fallback = "") {
  const raw = String(value ?? fallback)
    .trim()
    .replace(/^['"]+|['"]+$/g, "")
    .replace(/\\n/g, "")
    .trim();
  return raw;
}

const STORE_NAME = "Daddy Grab Super App";
const STORE_SLUG = "daddygrab";
const STORE_BASE_URL = cleanEnv(process.env.STOREFRONT_PUBLIC_BASE_URL, "https://store.daddygrab.online");
const TELEGRAM_BOT_TOKEN = cleanEnv(process.env.TELEGRAM_BOT_TOKEN);
const TELEGRAM_ADMIN_GROUP_ID = cleanEnv(process.env.TELEGRAM_ADMIN_GROUP_ID);
const TELEGRAM_ADMIN_IDS = String(process.env.TELEGRAM_ADMIN_IDS || "")
  .split(",")
  .map((value) => cleanEnv(value))
  .filter(Boolean);
const RESEND_API_KEY = cleanEnv(process.env.RESEND_API_KEY);
const RESEND_FROM = cleanEnv(process.env.RESEND_FROM_EMAIL, "noreply@jcit.digital");
const RESEND_TO = cleanEnv(process.env.ORDER_ALERT_EMAIL, RESEND_FROM);

const DEFAULT_PRODUCTS = [
  {
    sku: "DG-POP-TEST",
    category: "poppers",
    name: "Test Poppers Item",
    description: "Temporary test item for Daddy Grab storefront QA.",
    price: 350,
    image_url: "/docs/assets/logo-first-tile.png",
    stock: 10,
  },
  {
    sku: "DG-SUP-TEST",
    category: "supplements",
    name: "Test Supplement Item",
    description: "Temporary test supplement for Daddy Grab storefront QA.",
    price: 490,
    image_url: "/docs/assets/toolkit-book.png",
    stock: 10,
  },
  {
    sku: "DG-TOY-TEST",
    category: "toys",
    name: "Test Toy Item",
    description: "Temporary test toy item for Daddy Grab storefront QA.",
    price: 650,
    image_url: "/docs/assets/toolkit-events.png",
    stock: 10,
  },
  {
    sku: "DG-LUBE-TEST",
    category: "lubricants",
    name: "Test Lubricant Item",
    description: "Temporary test lubricant item for Daddy Grab storefront QA.",
    price: 290,
    image_url: "/docs/assets/toolkit-channels.png",
    stock: 10,
  },
];

const DEFAULT_PROMO = {
  code: "DADDYTEST10",
  discount_type: "fixed",
  discount_value: 10,
  notes: "Temporary QA promo code",
};

const DEFAULT_ADMINS = [
  { username: "Em", passcode: "101010", access_level: "super_admin", created_by: "system" },
  { username: "Admin1", passcode: "010101", access_level: "admin", created_by: "system" },
];

let bootstrapStorePromise;

function passcodeHash(passcode) {
  return scryptSync(String(passcode || ""), "daddy-grab-admin-salt", 64).toString("hex");
}

function verifyPasscode(passcode, hash) {
  const a = Buffer.from(passcodeHash(passcode), "hex");
  const b = Buffer.from(String(hash || ""), "hex");
  return a.length === b.length && timingSafeEqual(a, b);
}

function nowIso() {
  return new Date().toISOString();
}

function normalizeMoney(value) {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric) ? Number(numeric.toFixed(2)) : 0;
}

function validatePhilippineMobileNumber(value) {
  const raw = String(value || "").trim().replace(/\s+/g, "").replace(/-/g, "");
  if (/^09\d{9}$/.test(raw)) {
    return { ok: true, normalized: raw, e164: `+63${raw.slice(1)}` };
  }
  if (/^\+639\d{9}$/.test(raw)) {
    return { ok: true, normalized: `0${raw.slice(3)}`, e164: raw };
  }
  if (/^639\d{9}$/.test(raw)) {
    return { ok: true, normalized: `0${raw.slice(2)}`, e164: `+${raw}` };
  }
  return {
    ok: false,
    message: "Please use a valid Philippine mobile number format like 09XXXXXXXXX or +639XXXXXXXXX.",
  };
}

async function bootstrapStore() {
  if (!bootstrapStorePromise) {
    bootstrapStorePromise = (async () => {
      await bootstrapDatabase();
      for (const product of DEFAULT_PRODUCTS) {
        await query(
          `
            insert into products (sku, category, name, description, price, image_url, active, stock)
            values ($1,$2,$3,$4,$5,$6,true,$7)
            on conflict (sku) do nothing
          `,
          [
            product.sku,
            product.category,
            product.name,
            product.description,
            product.price,
            product.image_url,
            product.stock,
          ]
        );
      }

      await query(
        `
          insert into promos (code, discount_type, discount_value, active, notes)
          values ($1,$2,$3,true,$4)
          on conflict (code) do nothing
        `,
        [DEFAULT_PROMO.code, DEFAULT_PROMO.discount_type, DEFAULT_PROMO.discount_value, DEFAULT_PROMO.notes]
      );

      for (const admin of DEFAULT_ADMINS) {
        await query(
          `
            insert into admin_users (username, passcode_hash, access_level, active, created_by)
            values ($1,$2,$3,true,$4)
            on conflict (username) do nothing
          `,
          [admin.username, passcodeHash(admin.passcode), admin.access_level, admin.created_by]
        );
      }
    })().catch((error) => {
      bootstrapStorePromise = null;
      throw error;
    });
  }
  return bootstrapStorePromise;
}

async function listProducts({ includeInactive = false } = {}) {
  await bootstrapStore();
  const result = await query(
    `
      select sku, category, name, description, price, image_url, active, stock, updated_at
      from products
      ${includeInactive ? "" : "where active = true"}
      order by category asc, name asc
    `
  );
  return result.rows.map((row) => ({
    ...row,
    price: normalizeMoney(row.price),
    active: Boolean(row.active),
    stock: Number(row.stock || 0),
  }));
}

async function listPromos() {
  await bootstrapStore();
  const result = await query(
    `select code, discount_type, discount_value, active, notes, updated_at from promos order by code asc`
  );
  return result.rows.map((row) => ({
    ...row,
    discount_value: normalizeMoney(row.discount_value),
    active: Boolean(row.active),
  }));
}

async function getPromoByCode(code) {
  const normalized = String(code || "").trim().toUpperCase();
  if (!normalized) {
    return null;
  }
  const result = await query(
    `select code, discount_type, discount_value, active, notes from promos where upper(code) = $1 limit 1`,
    [normalized]
  );
  const promo = result.rows[0];
  if (!promo || !promo.active) {
    return null;
  }
  return {
    ...promo,
    discount_value: normalizeMoney(promo.discount_value),
    active: Boolean(promo.active),
  };
}

async function authenticateAdmin(username, passcode) {
  await bootstrapStore();
  const normalized = String(username || "").trim();
  const result = await query(
    `
      select username, passcode_hash, access_level, active, telegram_id, telegram_username
      from admin_users
      where username = $1
      limit 1
    `,
    [normalized]
  );
  const admin = result.rows[0];
  if (!admin || !admin.active || !verifyPasscode(passcode, admin.passcode_hash)) {
    throw new Error("Invalid admin credentials.");
  }
  return {
    username: admin.username,
    access_level: admin.access_level,
    active: Boolean(admin.active),
    telegram_id: admin.telegram_id || "",
    telegram_username: admin.telegram_username || "",
  };
}

function requireAdminRole(session, roles) {
  if (!session || !roles.includes(session.access_level)) {
    throw new Error("You do not have access to this action.");
  }
}

async function upsertProduct(product, actor) {
  await bootstrapStore();
  const payload = {
    sku: String(product.sku || "").trim().toUpperCase(),
    category: String(product.category || "").trim().toLowerCase(),
    name: String(product.name || "").trim(),
    description: String(product.description || "").trim(),
    price: normalizeMoney(product.price),
    image_url: String(product.image_url || "").trim(),
    active: product.active !== false,
    stock: Math.max(0, Number(product.stock || 0)),
  };
  if (!payload.sku || !payload.category || !payload.name) {
    throw new Error("SKU, category, and name are required.");
  }
  await query(
    `
      insert into products (sku, category, name, description, price, image_url, active, stock, updated_at)
      values ($1,$2,$3,$4,$5,$6,$7,$8,now())
      on conflict (sku) do update
      set category = excluded.category,
          name = excluded.name,
          description = excluded.description,
          price = excluded.price,
          image_url = excluded.image_url,
          active = excluded.active,
          stock = excluded.stock,
          updated_at = now()
    `,
    [
      payload.sku,
      payload.category,
      payload.name,
      payload.description,
      payload.price,
      payload.image_url,
      payload.active,
      payload.stock,
    ]
  );
  return { ...payload, updated_by: actor || "" };
}

async function deleteProduct(sku) {
  await bootstrapStore();
  await query(`delete from products where sku = $1`, [String(sku || "").trim().toUpperCase()]);
}

async function upsertPromo(promo) {
  await bootstrapStore();
  const payload = {
    code: String(promo.code || "").trim().toUpperCase(),
    discount_type: String(promo.discount_type || "fixed").trim().toLowerCase(),
    discount_value: normalizeMoney(promo.discount_value),
    active: promo.active !== false,
    notes: String(promo.notes || "").trim(),
  };
  if (!payload.code) {
    throw new Error("Promo code is required.");
  }
  await query(
    `
      insert into promos (code, discount_type, discount_value, active, notes, updated_at)
      values ($1,$2,$3,$4,$5,now())
      on conflict (code) do update
      set discount_type = excluded.discount_type,
          discount_value = excluded.discount_value,
          active = excluded.active,
          notes = excluded.notes,
          updated_at = now()
    `,
    [payload.code, payload.discount_type, payload.discount_value, payload.active, payload.notes]
  );
  return payload;
}

async function upsertAdminUser(input, actor, session) {
  await bootstrapStore();
  requireAdminRole(session, ["super_admin"]);
  const username = String(input.username || "").trim();
  const passcode = String(input.passcode || "").trim();
  const accessLevel = String(input.access_level || "admin").trim();
  if (!username || !passcode) {
    throw new Error("Username and passcode are required.");
  }
  if (!["super_admin", "admin"].includes(accessLevel)) {
    throw new Error("Access level must be super_admin or admin.");
  }
  await query(
    `
      insert into admin_users (
        username, passcode_hash, access_level, active, telegram_id, telegram_username, created_by, updated_at
      )
      values ($1,$2,$3,true,$4,$5,$6,now())
      on conflict (username) do update
      set passcode_hash = excluded.passcode_hash,
          access_level = excluded.access_level,
          telegram_id = excluded.telegram_id,
          telegram_username = excluded.telegram_username,
          active = true,
          updated_at = now()
    `,
    [
      username,
      passcodeHash(passcode),
      accessLevel,
      String(input.telegram_id || "").trim(),
      String(input.telegram_username || "").trim().replace(/^@/, ""),
      actor || "system",
    ]
  );
}

async function listAdminUsers(session) {
  await bootstrapStore();
  requireAdminRole(session, ["super_admin"]);
  const result = await query(
    `
      select username, access_level, active, telegram_id, telegram_username, created_by, updated_at
      from admin_users
      order by access_level desc, username asc
    `
  );
  return result.rows.map((row) => ({ ...row, active: Boolean(row.active) }));
}

function buildOrderId() {
  return `DG-${new Date().toISOString().slice(2, 10).replace(/-/g, "")}-${randomUUID().slice(0, 6).toUpperCase()}`;
}

function buildTicketId() {
  return `TKT-${new Date().toISOString().slice(2, 10).replace(/-/g, "")}-${randomUUID().slice(0, 6).toUpperCase()}`;
}

async function sendTelegramMessage(chatId, text) {
  if (!TELEGRAM_BOT_TOKEN || !chatId) {
    return false;
  }
  const response = await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text }),
  });
  return response.ok;
}

async function sendCustomerOrderNotification(order) {
  const targetId = String(order.telegram_user_id || order.telegram_id || "").trim();
  if (!targetId || !TELEGRAM_BOT_TOKEN) {
    return false;
  }
  const firstName = String(order.customer_first_name || order.customer_name || "there").trim().split(/\s+/)[0];
  const lines = [
    `Hi ${firstName}, your Daddy Grab order is in.`,
    "",
    `Order Number: ${order.order_id}`,
    `Status: ${order.order_status}`,
    `Payment: ${order.payment_method}`,
    `Total: PHP ${Number(order.total || 0).toFixed(2)}`,
    "",
    `Track here: ${STORE_BASE_URL}/track?order_id=${encodeURIComponent(order.order_id)}`,
  ];
  return sendTelegramMessage(targetId, lines.join("\n"));
}

function formatSupportTicketNotification(ticket) {
  return [
    `Support Ticket: ${ticket.ticket_id}`,
    `Status: ${ticket.status}`,
    `Source: ${ticket.source}`,
    `Product Type: ${ticket.product_type}`,
    `Issue Type: ${ticket.issue_type}`,
    ticket.customer_name ? `Customer: ${ticket.customer_name}` : "",
    ticket.username ? `Telegram Username: @${ticket.username}` : "",
    ticket.user_id ? `Telegram ID: ${ticket.user_id}` : "",
    ticket.mobile_number ? `Mobile: ${ticket.mobile_number}` : "",
    "",
    "Message:",
    ticket.message,
    "",
    "Admin note: reply to this message in the admin GC to message the customer, or use the admin portal.",
  ]
    .filter(Boolean)
    .join("\n");
}

async function sendOrderEmail(subject, body) {
  if (!RESEND_API_KEY || !RESEND_TO) {
    return false;
  }
  const response = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from: RESEND_FROM,
      to: [RESEND_TO],
      subject,
      html: `<pre style="font-family:ui-monospace, SFMono-Regular, Menlo, monospace; white-space:pre-wrap;">${body}</pre>`,
    }),
  });
  return response.ok;
}

async function listTickets() {
  await bootstrapStore();
  const result = await query(`select * from tickets order by created_at desc limit 200`);
  return result.rows.map((row) => ({
    ...row,
    created_at: row.created_at ? new Date(row.created_at).toISOString() : "",
    updated_at: row.updated_at ? new Date(row.updated_at).toISOString() : "",
  }));
}

async function createSupportTicket(payload) {
  await bootstrapStore();

  const telegramId = String(payload.telegram_id || payload.user_id || "").trim();
  const telegramUsername = String(payload.telegram_username || payload.username || "").trim().replace(/^@/, "");
  const customerName = String(payload.customer_name || "").trim();
  const mobileCheck = validatePhilippineMobileNumber(payload.mobile_number || "");
  if (!mobileCheck.ok) {
    throw new Error(mobileCheck.message);
  }

  const productType = String(payload.product_type || "").trim().toLowerCase();
  const issueType = String(payload.issue_type || "").trim().toLowerCase();
  const message = String(payload.message || "").trim();
  const source = String(payload.source || (telegramId ? "telegram" : "web")).trim() || "web";
  const allowedProducts = ["grab poppers", "booking", "events"];
  const allowedIssues = ["order follow up", "customer feedback"];

  if (!telegramUsername && !telegramId) {
    throw new Error("Please open this form from Telegram or enter your Telegram username.");
  }
  if (!allowedProducts.includes(productType)) {
    throw new Error("Please choose a valid product type.");
  }
  if (!allowedIssues.includes(issueType)) {
    throw new Error("Please choose a valid issue type.");
  }
  if (message.length < 8) {
    throw new Error("Please share a bit more detail so the support team can help.");
  }

  const ticket = {
    ticket_id: buildTicketId(),
    type: "support",
    user_id: telegramId,
    username: telegramUsername,
    mobile_number: mobileCheck.normalized,
    product_type: productType,
    issue_type: issueType,
    source,
    customer_name: customerName,
    message,
    status: "open",
  };

  await query(
    `
      insert into tickets (
        ticket_id, type, user_id, username, mobile_number, product_type, issue_type, source, customer_name, message, status, created_at, updated_at
      )
      values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,now(),now())
    `,
    [
      ticket.ticket_id,
      ticket.type,
      ticket.user_id,
      ticket.username,
      ticket.mobile_number,
      ticket.product_type,
      ticket.issue_type,
      ticket.source,
      ticket.customer_name,
      ticket.message,
      ticket.status,
    ]
  );

  const notification = formatSupportTicketNotification(ticket);
  if (TELEGRAM_ADMIN_GROUP_ID) {
    await sendTelegramMessage(TELEGRAM_ADMIN_GROUP_ID, notification).catch(() => false);
  } else {
    for (const adminId of TELEGRAM_ADMIN_IDS) {
      await sendTelegramMessage(adminId, notification).catch(() => false);
    }
  }
  await sendOrderEmail(`New CS Ticket- ${ticket.ticket_id}`, notification).catch(() => false);

  if (ticket.user_id) {
    await sendTelegramMessage(
      ticket.user_id,
      [
        `Your support request ${ticket.ticket_id} has been received.`,
        "",
        "The Daddy Grab team has been notified and will reply here or in the admin portal as soon as possible.",
      ].join("\n")
    ).catch(() => false);
  }

  return ticket;
}

async function replyToTicket(ticketId, message, actor = "") {
  await bootstrapStore();
  const normalizedTicketId = String(ticketId || "").trim();
  const outbound = String(message || "").trim();
  if (!normalizedTicketId) {
    throw new Error("Ticket ID is required.");
  }
  if (!outbound) {
    throw new Error("Reply message is required.");
  }

  const result = await query(`select * from tickets where ticket_id = $1 limit 1`, [normalizedTicketId]);
  const ticket = result.rows[0];
  if (!ticket) {
    throw new Error("Ticket not found.");
  }
  if (!ticket.user_id) {
    throw new Error("This ticket is not linked to a Telegram user ID.");
  }

  const sent = await sendTelegramMessage(
    ticket.user_id,
    [`Support update for ticket ${ticket.ticket_id}:`, outbound].join("\n\n")
  );
  if (!sent) {
    throw new Error("Unable to send Telegram reply for this ticket.");
  }

  await query(
    `
      update tickets
      set status = 'responded',
          updated_at = now()
      where ticket_id = $1
    `,
    [normalizedTicketId]
  );

  if (TELEGRAM_ADMIN_GROUP_ID) {
    await sendTelegramMessage(
      TELEGRAM_ADMIN_GROUP_ID,
      [`Admin reply sent for ticket ${ticket.ticket_id}.`, actor ? `By: ${actor}` : "", outbound].filter(Boolean).join("\n")
    ).catch(() => false);
  }

  return {
    ...ticket,
    status: "responded",
    updated_at: nowIso(),
  };
}

function formatOrderNotification(order, items) {
  return [
    `New Order - ${order.order_id}`,
    `Name: ${order.customer_name}`,
    `Phone: ${order.phone_number}`,
    order.telegram_username ? `Telegram: @${order.telegram_username}` : "",
    order.telegram_id ? `Telegram ID: ${order.telegram_id}` : "",
    `Payment: ${order.payment_method}`,
    `Delivery: ${order.delivery_method}`,
    `Address: ${order.delivery_address}`,
    `Area: ${order.delivery_area}`,
    `Promo: ${order.promo_code || "none"}`,
    `Referral: ${order.referral_code || "none"}`,
    `Status: ${order.order_status}`,
    `Total: PHP ${order.total.toFixed(2)}`,
    "",
    "Items:",
    ...items.map((item) => `- ${item.name} x${item.quantity} = PHP ${Number(item.line_total || 0).toFixed(2)}`),
  ]
    .filter(Boolean)
    .join("\n");
}

async function createOrder(payload) {
  await bootstrapStore();

  const customer = payload?.customer || {};
  const items = Array.isArray(payload?.items) ? payload.items : [];
  if (!items.length) {
    throw new Error("Your cart is empty.");
  }

  const phoneCheck = validatePhilippineMobileNumber(customer.phone_number || customer.delivery_contact);
  if (!phoneCheck.ok) {
    throw new Error(phoneCheck.message);
  }

  const customerName = String(customer.customer_name || customer.delivery_name || "").trim();
  if (!customerName) {
    throw new Error("Customer name is required.");
  }

  const address = String(customer.delivery_address || "").trim();
  if (!address) {
    throw new Error("Delivery address is required.");
  }

  const paymentMethod = String(payload.payment_method || "").trim();
  if (!paymentMethod) {
    throw new Error("Payment method is required.");
  }

  const deliveryMethod = String(payload.delivery_method || "Standard").trim() || "Standard";
  const promo = await getPromoByCode(payload.promo_code);
  const subtotal = normalizeMoney(
    items.reduce((sum, item) => sum + normalizeMoney(item.unit_price || item.price) * Number(item.quantity || item.qty || 0), 0)
  );
  const promoDiscount = promo ? normalizeMoney(promo.discount_value) : 0;
  const total = Math.max(0, normalizeMoney(subtotal - promoDiscount));
  const orderId = buildOrderId();
  const now = nowIso();
  const source = String(payload.source || (customer.telegram_id || customer.telegram_user_id ? "telegram" : "web")).trim();
  const orderRow = {
    order_id: orderId,
    source,
    customer_name: customerName,
    customer_first_name: String(customer.first_name || customer.customer_first_name || customerName.split(/\s+/)[0] || "").trim(),
    phone_number: phoneCheck.normalized,
    telegram_id: String(customer.telegram_id || "").trim(),
    telegram_user_id: String(customer.telegram_user_id || "").trim(),
    telegram_username: String(customer.telegram_username || customer.username || "").trim().replace(/^@/, ""),
    telegram_init_data: String(customer.telegram_init_data || "").trim(),
    delivery_area: String(customer.delivery_area || "Metro Manila").trim() || "Metro Manila",
    delivery_address: address,
    address_verified: Boolean(payload.address_verified),
    address_verification_notes: String(payload.address_verification_notes || "").trim(),
    payment_method: paymentMethod,
    payment_status: paymentMethod === "Cash on Delivery" ? "pay_on_delivery" : "awaiting_payment",
    order_status: "Pending Confirmation",
    delivery_method: deliveryMethod,
    tracking_number: "",
    promo_code: promo ? promo.code : "",
    promo_discount: promoDiscount,
    referral_code: String(payload.referral_code || "").trim().toUpperCase(),
    referral_discount: 0,
    repeat_discount: 0,
    subtotal,
    shipping_fee: 0,
    total,
    notes: String(payload.notes || "").trim(),
    payment_proof_url: String(payload.payment_proof_url || "").trim(),
    lalamove_enabled: true,
    lalamove_active: false,
    lalamove_status: "inactive",
    paymongo_enabled: true,
    paymongo_active: false,
    created_at: now,
    updated_at: now,
  };

  const normalizedItems = items.map((item) => {
    const quantity = Math.max(1, Number(item.quantity || item.qty || 1));
    const unitPrice = normalizeMoney(item.unit_price || item.price);
    return {
      sku: String(item.sku || "").trim().toUpperCase(),
      name: String(item.name || "").trim(),
      category: String(item.category || "general").trim().toLowerCase(),
      quantity,
      unit_price: unitPrice,
      line_total: normalizeMoney(unitPrice * quantity),
    };
  });

  await withClient(async (client) => {
    await client.query("begin");
    try {
      await client.query(
        `
          insert into orders (
            order_id, source, customer_name, customer_first_name, phone_number, telegram_id, telegram_user_id,
            telegram_username, telegram_init_data, delivery_area, delivery_address, address_verified,
            address_verification_notes, payment_method, payment_status, order_status, delivery_method,
            tracking_number, promo_code, promo_discount, referral_code, referral_discount, repeat_discount,
            subtotal, shipping_fee, total, notes, payment_proof_url, lalamove_enabled, lalamove_active,
            lalamove_status, paymongo_enabled, paymongo_active, created_at, updated_at
          ) values (
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22,$23,$24,$25,$26,$27,$28,$29,$30,$31,$32,$33,$34,$35
          )
        `,
        [
          orderRow.order_id,
          orderRow.source,
          orderRow.customer_name,
          orderRow.customer_first_name,
          orderRow.phone_number,
          orderRow.telegram_id,
          orderRow.telegram_user_id,
          orderRow.telegram_username,
          orderRow.telegram_init_data,
          orderRow.delivery_area,
          orderRow.delivery_address,
          orderRow.address_verified,
          orderRow.address_verification_notes,
          orderRow.payment_method,
          orderRow.payment_status,
          orderRow.order_status,
          orderRow.delivery_method,
          orderRow.tracking_number,
          orderRow.promo_code,
          orderRow.promo_discount,
          orderRow.referral_code,
          orderRow.referral_discount,
          orderRow.repeat_discount,
          orderRow.subtotal,
          orderRow.shipping_fee,
          orderRow.total,
          orderRow.notes,
          orderRow.payment_proof_url,
          orderRow.lalamove_enabled,
          orderRow.lalamove_active,
          orderRow.lalamove_status,
          orderRow.paymongo_enabled,
          orderRow.paymongo_active,
          orderRow.created_at,
          orderRow.updated_at,
        ]
      );

      for (const item of normalizedItems) {
        await client.query(
          `
            insert into order_items (order_id, sku, name, category, quantity, unit_price, line_total)
            values ($1,$2,$3,$4,$5,$6,$7)
          `,
          [orderId, item.sku, item.name, item.category, item.quantity, item.unit_price, item.line_total]
        );
      }

      await client.query("commit");
    } catch (error) {
      await client.query("rollback");
      throw error;
    }
  });

  const notification = formatOrderNotification(orderRow, normalizedItems);
  if (TELEGRAM_ADMIN_GROUP_ID) {
    await sendTelegramMessage(TELEGRAM_ADMIN_GROUP_ID, notification).catch(() => false);
  } else {
    for (const adminId of TELEGRAM_ADMIN_IDS) {
      await sendTelegramMessage(adminId, notification).catch(() => false);
    }
  }
  await sendOrderEmail(`New Order - ${orderId}`, notification).catch(() => false);
  await sendCustomerOrderNotification(orderRow).catch(() => false);

  return {
    order: {
      ...orderRow,
      items: normalizedItems,
      tracking_link: `${STORE_BASE_URL}/track?order_id=${encodeURIComponent(orderId)}`,
      rewards: { balance_after: 0, referral_discount_active: false, repeat_discount_active: false },
    },
    promo_auto_applied: false,
    promo_code: promo ? promo.code : "",
    total,
  };
}

async function quoteOrder(payload) {
  await bootstrapStore();
  const items = Array.isArray(payload?.items) ? payload.items : [];
  const promo = await getPromoByCode(payload?.promo_code);
  const subtotal = normalizeMoney(
    items.reduce((sum, item) => sum + normalizeMoney(item.unit_price || item.price) * Number(item.quantity || item.qty || 0), 0)
  );
  const promoDiscount = promo ? normalizeMoney(promo.discount_value) : 0;
  const total = Math.max(0, normalizeMoney(subtotal - promoDiscount));
  return {
    subtotal,
    shipping: 0,
    discount: promoDiscount,
    total,
    promo_code: promo ? promo.code : "",
    promo_auto_applied: false,
    referral_discount_active: false,
    repeat_discount_active: false,
  };
}

async function getOrderTracking({ orderId, phone, telegramUsername }) {
  await bootstrapStore();
  const params = [];
  const conditions = [];
  if (orderId) {
    params.push(String(orderId).trim());
    conditions.push(`order_id = $${params.length}`);
  }
  const phoneCheck = phone ? validatePhilippineMobileNumber(phone) : null;
  if (phoneCheck?.ok) {
    params.push(phoneCheck.normalized);
    conditions.push(`phone_number = $${params.length}`);
  }
  if (telegramUsername) {
    params.push(String(telegramUsername).trim().replace(/^@/, ""));
    conditions.push(`telegram_username = $${params.length}`);
  }
  if (!conditions.length) {
    throw new Error("Provide an order number, phone number, or Telegram username.");
  }
  const result = await query(
    `
      select *
      from orders
      where ${conditions.join(" or ")}
      order by created_at desc
      limit 1
    `,
    params
  );
  const order = result.rows[0];
  if (!order) {
    throw new Error("No matching order was found.");
  }
  const itemsResult = await query(
    `select sku, name, category, quantity, unit_price, line_total from order_items where order_id = $1 order by name asc`,
    [order.order_id]
  );
  return {
    ...order,
    items: itemsResult.rows,
    tracking_link: `${STORE_BASE_URL}/track?order_id=${encodeURIComponent(order.order_id)}`,
    lalamove: {
      enabled: Boolean(order.lalamove_enabled),
      active: Boolean(order.lalamove_active),
      status_label: order.lalamove_status || "inactive",
      tracking_link: "",
    },
  };
}

async function listOrders({ status = "", search = "", limit = 40, dateFrom = "", dateTo = "" } = {}) {
  await bootstrapStore();
  const params = [];
  const conditions = [];
  if (status && status !== "all") {
    const normalizedStatus = String(status).trim().toLowerCase();
    if (normalizedStatus === "pending") {
      conditions.push(`order_status ilike 'Pending%'`);
    } else if (normalizedStatus === "awaiting_payment") {
      conditions.push(`payment_status = 'awaiting_payment'`);
    } else {
      params.push(status);
      conditions.push(`order_status = $${params.length}`);
    }
  }
  if (search) {
    params.push(`%${String(search).trim()}%`);
    conditions.push(
      `(order_id ilike $${params.length} or customer_name ilike $${params.length} or telegram_username ilike $${params.length} or phone_number ilike $${params.length})`
    );
  }
  if (dateFrom) {
    params.push(String(dateFrom).trim());
    conditions.push(`created_at::date >= $${params.length}::date`);
  }
  if (dateTo) {
    params.push(String(dateTo).trim());
    conditions.push(`created_at::date <= $${params.length}::date`);
  }
  params.push(Math.max(1, Math.min(200, Number(limit || 40))));
  const sql = `
    select *
    from orders
    ${conditions.length ? `where ${conditions.join(" and ")}` : ""}
    order by created_at desc
    limit $${params.length}
  `;
  const result = await query(sql, params);
  const orders = [];
  for (const row of result.rows) {
    const itemsResult = await query(
      `select sku, name, category, quantity as qty, unit_price as price, line_total from order_items where order_id = $1 order by name asc`,
      [row.order_id]
    );
    orders.push({
      ...row,
      items: itemsResult.rows,
      tracking_link: `${STORE_BASE_URL}/track?order_id=${encodeURIComponent(row.order_id)}`,
      telegram_contact_available: Boolean(row.telegram_id || row.telegram_user_id),
      active_promo_code: row.promo_code || "",
      total: normalizeMoney(row.total),
    });
  }
  return orders;
}

async function updateOrder(orderId, patch) {
  await bootstrapStore();
  const currentResult = await query(`select * from orders where order_id = $1 limit 1`, [orderId]);
  const current = currentResult.rows[0];
  if (!current) {
    throw new Error("Order not found.");
  }
  const next = {
    status: String(patch.status || current.order_status).trim(),
    tracking_number: String(patch.tracking_number || current.tracking_number || "").trim(),
  };
  const result = await query(
    `
      update orders
      set order_status = $2,
          tracking_number = $3,
          updated_at = now()
      where order_id = $1
      returning *
    `,
    [orderId, next.status, next.tracking_number]
  );
  return result.rows[0];
}

async function adminDashboard(session, filters = {}) {
  await bootstrapStore();
  const orders = await listOrders({
    status: filters.status || "all",
    search: filters.search || "",
    limit: filters.limit || 40,
    dateFrom: filters.date_from || "",
    dateTo: filters.date_to || "",
  });
  const promos = await listPromos();
  const inventory = await listProducts({ includeInactive: true });
  const tickets = await listTickets();
  const surveysResult = await query(`select * from surveys order by created_at desc limit 100`);
  const summary = {
    pending_orders: orders.filter((order) => /pending/i.test(order.order_status || "")).length,
    awaiting_payment: orders.filter((order) => /payment/i.test(order.payment_status || "")).length,
  };
  const grossSales = orders.reduce((sum, order) => sum + normalizeMoney(order.total), 0);
  const orderCount = orders.length;
  const report = {
    gross_sales: grossSales,
    order_count: orderCount,
    average_order_value: orderCount ? grossSales / orderCount : 0,
    by_status: orders.reduce((acc, order) => {
      acc[order.order_status || "Unknown"] = (acc[order.order_status || "Unknown"] || 0) + 1;
      return acc;
    }, {}),
  };
  const adminUsers = session?.access_level === "super_admin" ? await listAdminUsers(session) : [];
  return {
    orders,
    summary,
    report,
    tickets,
    promos,
    surveys: surveysResult.rows,
    inventory,
    admin_users: adminUsers,
  };
}

async function contactCustomer(orderId, message) {
  const order = await getOrderTracking({ orderId });
  const targetId = order.telegram_id || order.telegram_user_id;
  if (!targetId) {
    return { customer_notified: false };
  }
  await sendTelegramMessage(targetId, String(message || "").trim());
  return { customer_notified: true };
}

module.exports = {
  STORE_BASE_URL,
  STORE_NAME,
  STORE_SLUG,
  adminDashboard,
  authenticateAdmin,
  bootstrapStore,
  createSupportTicket,
  contactCustomer,
  createOrder,
  deleteProduct,
  getOrderTracking,
  listAdminUsers,
  listTickets,
  listProducts,
  listPromos,
  listOrders,
  passcodeHash,
  quoteOrder,
  requireAdminRole,
  replyToTicket,
  upsertAdminUser,
  upsertProduct,
  upsertPromo,
  updateOrder,
  validatePhilippineMobileNumber,
};
