"use strict";

const { bootstrapStore, getOrderTracking, updateOrder } = require("../_lib/store");

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

module.exports = async function handler(req, res) {
  try {
    await bootstrapStore();
    if (req.method === "POST") {
      const body = await parseBody(req);
      if (body.action === "mark_completed" && body.order_id) {
        const order = await updateOrder(body.order_id, { status: "Completed" });
        sendJson(res, 200, { ok: true, data: order });
        return;
      }
      const order = await getOrderTracking({
        orderId: body.order_id,
        phone: body.phone,
        telegramUsername: body.telegram_username,
      });
      sendJson(res, 200, { ok: true, data: order });
      return;
    }
    sendJson(res, 405, { ok: false, message: "Method not allowed." });
  } catch (error) {
    sendJson(res, 500, { ok: false, message: error instanceof Error ? error.message : "Tracking error." });
  }
};
