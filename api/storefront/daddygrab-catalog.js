"use strict";

const { STORE_NAME, STORE_SLUG, STORE_BASE_URL, bootstrapStore, listProducts, listPromos } = require("../_lib/store");

function sendJson(res, status, body) {
  res.status(status).setHeader("Content-Type", "application/json; charset=utf-8");
  res.end(JSON.stringify(body));
}

module.exports = async function handler(req, res) {
  if (req.method !== "GET") {
    sendJson(res, 405, { ok: false, message: "Method not allowed." });
    return;
  }

  try {
    await bootstrapStore();
    const [products, promos] = await Promise.all([listProducts(), listPromos()]);
    sendJson(res, 200, {
      ok: true,
      data: {
        store: {
          slug: STORE_SLUG,
          title: STORE_NAME,
          description: "Daddy Grab is your one-stop shop for multiple product lines and services.",
          public_base_url: STORE_BASE_URL,
          inactive_integrations: {
            lalamove: { enabled: true, active: false },
            paymongo: { enabled: true, active: false },
          },
        },
        categories: ["poppers", "supplements", "toys", "lubricants"],
        products,
        promos,
      },
    });
  } catch (error) {
    sendJson(res, 500, { ok: false, message: error instanceof Error ? error.message : "Catalog error." });
  }
};
