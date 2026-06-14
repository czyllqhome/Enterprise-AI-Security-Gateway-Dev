(function () {
  const storageKey = "chat_theme";

  function syncThemeButtons() {
    const isNight = document.body.classList.contains("chat-night");
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.textContent = isNight ? "Light" : "Night";
      button.setAttribute("aria-label", isNight ? "Switch to light mode" : "Switch to night mode");
      button.title = isNight ? "Switch to light mode" : "Switch to night mode";
    });
  }

  function applyStoredTheme() {
    const theme = window.localStorage.getItem(storageKey) || "light";
    document.body.classList.toggle("chat-night", theme === "night");
    syncThemeButtons();
  }

  function toggleTheme() {
    const nextTheme = document.body.classList.contains("chat-night") ? "light" : "night";
    window.localStorage.setItem(storageKey, nextTheme);
    document.body.classList.toggle("chat-night", nextTheme === "night");
    syncThemeButtons();
  }

  applyStoredTheme();

  document.addEventListener("DOMContentLoaded", () => {
    applyStoredTheme();
    document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
      button.addEventListener("click", toggleTheme);
    });
  });
})();
