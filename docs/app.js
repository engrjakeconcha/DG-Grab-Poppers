(function () {
  const tg = window.Telegram && window.Telegram.WebApp ? window.Telegram.WebApp : null;

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
    link.addEventListener("click", function (event) {
      if (!tg) return;
      try {
        tg.HapticFeedback.selectionChanged();
      } catch (error) {
        console.debug("Telegram haptic skipped", error);
      }

      if (link.dataset.miniappRoute === "true") {
        const href = link.getAttribute("href");
        if (!href) return;
        event.preventDefault();
        window.location.assign(href);
      }
    });
  });
})();
