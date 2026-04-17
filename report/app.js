"use strict";

const SUPPORT_API_URL = "/api/storefront/daddygrab-support";
const tele = window.Telegram?.WebApp || null;

const state = {
  captchaToken: "",
};

if (tele) {
  tele.ready();
  tele.expand();
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

function getTelegramMiniAppUser() {
  const user = tele?.initDataUnsafe?.user;
  if (!user) return null;
  return {
    id: String(user.id || "").trim(),
    username: String(user.username || "").trim().replace(/^@/, ""),
    firstName: String(user.first_name || "").trim(),
  };
}

function setFeedback(message, tone = "") {
  const node = document.getElementById("support-feedback");
  if (!node) return;
  node.textContent = message || "";
  node.className = `checkout-feedback${tone ? ` is-${tone}` : ""}`;
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

async function loadCaptcha() {
  const result = await apiJson(SUPPORT_API_URL);
  state.captchaToken = String(result.data?.token || "");
  const label = document.getElementById("captcha-label");
  if (label) {
    label.textContent = `What is ${result.data?.question || "?"}?`;
  }
}

function hydrateTelegramFields() {
  const form = document.getElementById("support-form");
  if (!(form instanceof HTMLFormElement)) return;
  const tgUser = getTelegramMiniAppUser();
  if (!tgUser) return;

  if (form.elements.telegram_id) {
    form.elements.telegram_id.value = tgUser.id;
  }
  if (form.elements.telegram_username && tgUser.username) {
    form.elements.telegram_username.value = `@${tgUser.username}`;
  }
}

function bindEvents() {
  const form = document.getElementById("support-form");
  if (!(form instanceof HTMLFormElement)) return;

  document.getElementById("refresh-captcha")?.addEventListener("click", async () => {
    try {
      setFeedback("");
      await loadCaptcha();
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "Unable to refresh captcha.", "error");
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const mobileCheck = validatePhilippineMobileNumber(form.elements.mobile_number?.value || "");
      if (!mobileCheck.ok) {
        throw new Error(mobileCheck.message);
      }

      setFeedback("Creating your support ticket...");
      const payload = {
        telegram_id: String(form.elements.telegram_id?.value || "").trim(),
        telegram_username: String(form.elements.telegram_username?.value || "").trim(),
        mobile_number: mobileCheck.normalized,
        product_type: String(form.elements.product_type?.value || "").trim(),
        issue_type: String(form.elements.issue_type?.value || "").trim(),
        message: String(form.elements.message?.value || "").trim(),
        captcha_answer: String(form.elements.captcha_answer?.value || "").trim(),
        captcha_token: state.captchaToken,
        source: getTelegramMiniAppUser() ? "telegram" : "web",
      };

      const result = await apiJson(SUPPORT_API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      setFeedback(`Ticket ${result.data?.ticket_id || ""} created. Our team has been notified.`, "success");
      form.reset();
      hydrateTelegramFields();
      await loadCaptcha();
      if (tele) {
        try {
          tele.HapticFeedback.notificationOccurred("success");
        } catch (_) {
          // Ignore haptic failures.
        }
      }
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "Failed to send support request.", "error");
    }
  });
}

async function init() {
  hydrateTelegramFields();
  bindEvents();
  try {
    await loadCaptcha();
  } catch (error) {
    setFeedback(error instanceof Error ? error.message : "Unable to load captcha.", "error");
  }
}

window.addEventListener("DOMContentLoaded", init);
