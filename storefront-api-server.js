"use strict";

const http = require("node:http");
const { URL } = require("node:url");

const catalogHandler = require("./api/storefront/daddygrab-catalog");
const checkoutHandler = require("./api/storefront/daddygrab-checkout");
const supportHandler = require("./api/storefront/daddygrab-support");
const trackHandler = require("./api/storefront/daddygrab-track");
const adminHandler = require("./api/admin/daddygrab-admin");

const PORT = Number(process.env.STOREFRONT_API_PORT || 3100);
const HOST = process.env.STOREFRONT_API_HOST || "127.0.0.1";

const routes = new Map([
  ["/api/storefront/daddygrab-catalog", catalogHandler],
  ["/api/storefront/daddygrab-checkout", checkoutHandler],
  ["/api/storefront/daddygrab-support", supportHandler],
  ["/api/storefront/daddygrab-track", trackHandler],
  ["/api/admin/daddygrab-admin", adminHandler],
]);

function json(res, status, body) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(body));
}

const server = http.createServer(async (req, res) => {
  res.status = (statusCode) => {
    res.statusCode = statusCode;
    return res;
  };

  const requestUrl = new URL(req.url || "/", `http://${req.headers.host || "localhost"}`);
  if (requestUrl.pathname === "/health") {
    json(res, 200, { ok: true, service: "daddygrab-storefront-api" });
    return;
  }

  const handler = routes.get(requestUrl.pathname);
  if (!handler) {
    json(res, 404, { ok: false, message: "Not found." });
    return;
  }

  try {
    await handler(req, res);
  } catch (error) {
    json(res, 500, {
      ok: false,
      message: error instanceof Error ? error.message : "Server error.",
    });
  }
});

server.listen(PORT, HOST, () => {
  console.log(`Daddy Grab storefront API listening on http://${HOST}:${PORT}`);
});
