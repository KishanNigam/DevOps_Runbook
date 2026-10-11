const searchInput = document.querySelector("#runbook-search");
const runbookItems = [...document.querySelectorAll(".runbook-item")];
const emptySearchMessage = document.querySelector("#no-search-results");
const searchStatus = document.querySelector("#search-status");
const themeToggle = document.querySelector("#theme-toggle");
const navLinks = [...document.querySelectorAll(".nav-link")];

function filterRunbooks(query) {
  const normalizedQuery = query.trim().toLowerCase();
  let visibleCount = 0;

  for (const item of runbookItems) {
    const matches = item.dataset.search.includes(normalizedQuery);
    item.hidden = !matches;
    visibleCount += Number(matches);
  }

  if (emptySearchMessage) {
    emptySearchMessage.hidden = runbookItems.length === 0 || visibleCount > 0;
  }

  if (searchStatus) {
    searchStatus.textContent = normalizedQuery && visibleCount
      ? `${visibleCount} matching runbook${visibleCount === 1 ? "" : "s"}`
      : "";
  }
}

if (searchInput) {
  searchInput.addEventListener("input", () => filterRunbooks(searchInput.value));
}

for (const shortcut of document.querySelectorAll(".shortcut-chip[data-filter-type]")) {
  shortcut.addEventListener("click", () => {
    const parameter = shortcut.dataset.filterType;
    const value = shortcut.dataset.filterValue;
    window.location.href = `/runbooks?${encodeURIComponent(parameter)}=${encodeURIComponent(value)}`;
  });
}

document.addEventListener("keydown", (event) => {
  const target = event.target;
  const isTyping = target instanceof HTMLElement
    && (target.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName));

  if (event.key === "/" && !isTyping && !event.altKey && !event.ctrlKey && !event.metaKey && searchInput) {
    event.preventDefault();
    searchInput.focus();
  }
});

function updateActiveNavigation() {
  const currentTarget = window.location.hash || "#dashboard";
  const currentPath = window.location.pathname;

  for (const link of navLinks) {
    const destination = new URL(link.href);
    const isRunbookSection = destination.pathname === "/runbooks"
      && currentPath.startsWith("/runbooks");
    const isDashboardSection = destination.pathname === currentPath
      && (currentPath === "/" || destination.hash === currentTarget);
    const isActive = isRunbookSection || isDashboardSection;
    link.classList.toggle("is-active", isActive);

    if (isActive) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  }
}

window.addEventListener("hashchange", updateActiveNavigation);
updateActiveNavigation();

if (themeToggle) {
  const savedTheme = window.localStorage.getItem("runbook-theme");
  const useDarkTheme = savedTheme === "dark";
  document.body.classList.toggle("dark-theme", useDarkTheme);
  themeToggle.setAttribute("aria-pressed", String(useDarkTheme));
  themeToggle.textContent = useDarkTheme ? "Switch to light theme" : "Switch to dark theme";

  themeToggle.addEventListener("click", () => {
    const isDark = document.body.classList.toggle("dark-theme");
    window.localStorage.setItem("runbook-theme", isDark ? "dark" : "light");
    themeToggle.setAttribute("aria-pressed", String(isDark));
    themeToggle.textContent = isDark ? "Switch to light theme" : "Switch to dark theme";
  });
}
