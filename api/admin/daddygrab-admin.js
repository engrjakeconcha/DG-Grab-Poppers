"use strict";

const {
  adminDashboard,
  authenticateAdmin,
  bootstrapStore,
  contactCustomer,
  deleteProduct,
  listPromos,
  listProducts,
  listAdminUsers,
  listTickets,
  requireAdminRole,
  replyToTicket,
  upsertAdminUser,
  upsertProduct,
  upsertPromo,
  updateOrder,
} = require("../_lib/store");

function sendJson(res, status, body) {
  res.status(status).setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(body));
}

function parseBody(req) {
  return new Promise((resolve, reject) => {
    let raw = "";
    req.on("data", (chunk) => {
      raw += chunk;
    });
    req.on("end", () => {
      if (!raw.trim()) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(raw));
      } catch (error) {
        reject(error);
      }
    });
    req.on("error", reject);
  });
}

function sessionFromHeaders(req) {
  return {
    username: String(req.headers["x-admin-user"] || "").trim(),
    code: String(req.headers["x-admin-code"] || "").trim(),
    access_level: String(req.headers["x-admin-role"] || "").trim(),
  };
}

async function resolveSession(req) {
  const candidate = sessionFromHeaders(req);
  if (!candidate.username || !candidate.code) {
    throw new Error("Missing admin session.");
  }
  return authenticateAdmin(candidate.username, candidate.code);
}

module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    sendJson(res, 405, { ok: false, message: "Method not allowed." });
    return;
  }

  try {
    const body = await parseBody(req);
    const action = String(body.action || "").trim();

    if (action === "login") {
      const admin = await authenticateAdmin(body.username, body.passcode);
      sendJson(res, 200, { ok: true, session: { username: admin.username, role: admin.access_level, code: body.passcode } });
      return;
    }

    const session = await resolveSession(req);

    if (action === "dashboard") {
      const data = await adminDashboard(session, {
        status: body.status,
        search: body.search,
        limit: body.limit,
      });
      sendJson(res, 200, {
        ok: true,
        summary: data.summary,
        report: data.report,
        orders: data.orders,
        tickets: data.tickets,
        promos: data.promos,
        surveys: data.surveys,
        inventory: data.inventory,
        admin_users: data.admin_users,
      });
      return;
    }

    if (action === "update_order") {
      const order = await updateOrder(body.order_id, {
        status: body.status,
        tracking_number: body.tracking_number,
      });
      sendJson(res, 200, { ok: true, order, customer_notified: false });
      return;
    }

    if (action === "contact_customer") {
      const result = await contactCustomer(body.order_id, body.message);
      sendJson(res, 200, { ok: true, ...result });
      return;
    }

    if (action === "reply_ticket") {
      const ticket = await replyToTicket(body.ticket_id, body.message, session.username);
      sendJson(res, 200, { ok: true, ticket });
      return;
    }

    if (action === "list_tickets") {
      const tickets = await listTickets();
      sendJson(res, 200, { ok: true, tickets });
      return;
    }

    if (action === "save_product") {
      requireAdminRole(session, ["super_admin"]);
      const product = await upsertProduct(body.product || body, session.username);
      sendJson(res, 200, { ok: true, product });
      return;
    }

    if (action === "delete_product") {
      requireAdminRole(session, ["super_admin"]);
      await deleteProduct(body.sku);
      sendJson(res, 200, { ok: true });
      return;
    }

    if (action === "list_products") {
      const inventory = await listProducts({ includeInactive: true });
      sendJson(res, 200, { ok: true, inventory });
      return;
    }

    if (action === "save_promo") {
      requireAdminRole(session, ["super_admin"]);
      const promo = await upsertPromo(body.promo || body);
      sendJson(res, 200, { ok: true, promo });
      return;
    }

    if (action === "list_promos") {
      const promos = await listPromos();
      sendJson(res, 200, { ok: true, promos });
      return;
    }

    if (action === "save_admin_user") {
      await upsertAdminUser(body.admin_user || body, session.username, session);
      const adminUsers = await listAdminUsers(session);
      sendJson(res, 200, { ok: true, admin_users: adminUsers });
      return;
    }

    sendJson(res, 400, { ok: false, message: "Unknown action." });
  } catch (error) {
    sendJson(res, 500, { ok: false, message: error instanceof Error ? error.message : "Admin error." });
  }
};
