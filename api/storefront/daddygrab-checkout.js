"use strict";

const { bootstrapStore, createOrder, quoteOrder } = require("../_lib/store");

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
      if (body.mode === "quote") {
        const quote = await quoteOrder(body);
        sendJson(res, 200, { ok: true, data: quote });
        return;
      }
      const result = await createOrder(body);
      sendJson(res, 200, { ok: true, data: result });
      return;
    }

    sendJson(res, 405, { ok: false, message: "Method not allowed." });
  } catch (error) {
    sendJson(res, 500, { ok: false, message: error instanceof Error ? error.message : "Checkout error." });
  }
};
