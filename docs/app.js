(function () {
  const greetingEl = document.getElementById("greeting");
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

  function getQueryParam(name) {
    const params = new URLSearchParams(window.location.search);
    return params.get(name);
  }

  function resolveFirstName() {
    const fromQuery = getQueryParam("name") || getQueryParam("first_name");
    if (fromQuery) return fromQuery.trim();

    if (tg && tg.initDataUnsafe && tg.initDataUnsafe.user && tg.initDataUnsafe.user.first_name) {
      return String(tg.initDataUnsafe.user.first_name).trim();
    }

    return "";
  }

  const firstName = resolveFirstName();
  if (firstName && greetingEl) {
    greetingEl.textContent = `Hi ${firstName}, where do you want to go today?`;
  }

  if (tg) {
    document.body.classList.add("telegram");
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("#f4fbf3");
      tg.setBackgroundColor("#f4fbf3");
    } catch (error) {
      console.debug("Telegram theme update skipped", error);
    }
  }

  document.querySelectorAll("[data-telegram='true']").forEach((link) => {
    link.addEventListener("click", function () {
      if (!tg) return;
      try {
        tg.HapticFeedback.selectionChanged();
      } catch (error) {
        console.debug("Telegram haptic skipped", error);
      }
    });
  });
})();
