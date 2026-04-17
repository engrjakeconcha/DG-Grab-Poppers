(function () {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;
  const onApexRedirectHost = window.location.hostname === "daddygrab.online";

  if (onApexRedirectHost) {
    const target = new URL(`https://store.daddygrab.online${window.location.pathname}${window.location.search}${window.location.hash}`);
    window.location.replace(target.toString());
    return;
  }

  if (tg) {
    document.body.classList.add("telegram");
    tg.ready();
    tg.expand();
    try {
      tg.setHeaderColor("#153b20");
      tg.setBackgroundColor("#f7faf6");
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
