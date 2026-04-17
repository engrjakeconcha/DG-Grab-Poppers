"use strict";

const { createHmac, timingSafeEqual } = require("node:crypto");
const { createSupportTicket } = require("../_lib/store");

const CAPTCHA_SECRET = String(process.env.SUPPORT_CAPTCHA_SECRET || process.env.TELEGRAM_BOT_TOKEN || "daddygrab-support-captcha").trim();

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

function signCaptcha(payload) {
  return createHmac("sha256", CAPTCHA_SECRET).update(payload).digest("hex");
}

function issueCaptcha() {
  const left = Math.floor(Math.random() * 8) + 1;
  const right = Math.floor(Math.random() * 8) + 1;
  const answer = left + right;
  const issuedAt = Date.now();
  const payload = `${left}:${right}:${answer}:${issuedAt}`;
  const signature = signCaptcha(payload);
  return {
    question: `${left} + ${right}`,
    token: Buffer.from(`${payload}:${signature}`, "utf8").toString("base64url"),
  };
}

function verifyCaptcha(token, answer) {
  const raw = Buffer.from(String(token || ""), "base64url").toString("utf8");
  const parts = raw.split(":");
  if (parts.length !== 5) {
    throw new Error("Captcha validation failed.");
  }
  const [left, right, expectedAnswer, issuedAt, signature] = parts;
  const payload = `${left}:${right}:${expectedAnswer}:${issuedAt}`;
  const expectedSignature = signCaptcha(payload);
  const a = Buffer.from(signature, "utf8");
  const b = Buffer.from(expectedSignature, "utf8");
  if (a.length !== b.length || !timingSafeEqual(a, b)) {
    throw new Error("Captcha validation failed.");
  }
  if (Date.now() - Number(issuedAt || 0) > 15 * 60 * 1000) {
    throw new Error("Captcha expired. Please refresh and try again.");
  }
  if (String(answer || "").trim() !== String(expectedAnswer).trim()) {
    throw new Error("Captcha answer is incorrect.");
  }
}

module.exports = async function handler(req, res) {
  try {
    if (req.method === "GET") {
      sendJson(res, 200, { ok: true, data: issueCaptcha() });
      return;
    }

    if (req.method === "POST") {
      const body = await parseBody(req);
      verifyCaptcha(body.captcha_token, body.captcha_answer);
      const ticket = await createSupportTicket(body);
      sendJson(res, 200, { ok: true, data: ticket });
      return;
    }

    sendJson(res, 405, { ok: false, message: "Method not allowed." });
  } catch (error) {
    sendJson(res, 500, { ok: false, message: error instanceof Error ? error.message : "Support request error." });
  }
};
