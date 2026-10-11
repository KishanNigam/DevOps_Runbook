(() => {
const apiUrl = document.body.dataset.apiUrl;
const searchForm = document.querySelector("#runbook-search-form");
const searchInput = document.querySelector("#runbook-search");
const resultsContainer = document.querySelector("#runbook-results");
const resultCount = document.querySelector("#result-count");
const emptyPanel = document.querySelector("#listing-empty");
const errorPanel = document.querySelector("#listing-error");
const resultsRegion = document.querySelector("#runbook-results");
const filterIds = ["technology", "category", "environment", "severity"];
const filterLabels = {
  technology: "technologies",
  category: "categories",
  environment: "environments",
  severity: "severities",
};
const filterElements = Object.fromEntries(
  filterIds.map((name) => [name, document.querySelector(`#filter-${name}`)]),
);
const sortElement = document.querySelector("#sort-runbooks");
let requestNumber = 0;
let debounceTimer;

function getParameters() {
  const params = new URLSearchParams(window.location.search);
  return {
    q: params.get("q") || "",
    technology: params.get("technology") || "",
    category: params.get("category") || "",
    environment: params.get("environment") || "",
    severity: params.get("severity") || "",
    sort: params.get("sort") || "updated",
  };
}

function updateUrl(parameters) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(parameters)) {
    if (value && !(key === "sort" && value === "updated")) params.set(key, value);
  }
  const query = params.toString();
  window.history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}`);
}

function setOptions(select, values, allLabel, selected) {
  const fragment = document.createDocumentFragment();
  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = allLabel;
  fragment.append(allOption);

  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    fragment.append(option);
  }

  select.replaceChildren(fragment);
  select.value = values.includes(selected) ? selected : "";
}

function addTag(container, text, className = "runbook-tag") {
  const tag = document.createElement("span");
  tag.className = className;
  tag.textContent = text;
  container.append(tag);
}

function createRunbookCard(runbook) {
  const link = document.createElement("a");
  link.className = "runbook-card";
  const detailUrl = new URL(
    `/runbooks/${encodeURIComponent(runbook.id)}`,
    window.location.origin,
  );
  detailUrl.searchParams.set(
    "return_to",
    `${window.location.pathname}${window.location.search}`,
  );
  link.href = `${detailUrl.pathname}${detailUrl.search}`;
  link.setAttribute("aria-label", `Open runbook: ${runbook.title}`);

  const content = document.createElement("div");
  content.className = "runbook-card-content";

  const headingRow = document.createElement("div");
  headingRow.className = "runbook-card-heading";
  const title = document.createElement("h3");
  title.textContent = runbook.title;
  const severity = document.createElement("span");
  severity.className = `severity-badge severity-${runbook.severity}`;
  severity.textContent = runbook.severity;
  headingRow.append(title, severity);
  content.append(headingRow);

  const metadata = document.createElement("div");
  metadata.className = "runbook-card-meta";
  addTag(metadata, runbook.category, "category-tag");
  for (const technology of runbook.technologies) addTag(metadata, technology);
  content.append(metadata);

  const summary = document.createElement("p");
  summary.className = "runbook-card-summary";
  summary.textContent = runbook.summary || runbook.symptoms.join(" ");
  content.append(summary);

  const footer = document.createElement("div");
  footer.className = "runbook-card-footer";
  const tags = document.createElement("div");
  tags.className = "runbook-card-tags";
  for (const tag of runbook.tags) addTag(tags, `#${tag}`, "runbook-hashtag");
  const updated = document.createElement("time");
  updated.dateTime = runbook.updated_at;
  updated.textContent = `Updated ${runbook.updated_at.slice(0, 10)}`;
  footer.append(tags, updated);
  content.append(footer);
  link.append(content);
  return link;
}

function renderResults(data) {
  const fragment = document.createDocumentFragment();
  for (const runbook of data.runbooks) fragment.append(createRunbookCard(runbook));
  resultsContainer.replaceChildren(fragment);

  resultCount.textContent = data.count === data.total
    ? `${data.count} runbook${data.count === 1 ? "" : "s"}`
    : `${data.count} of ${data.total} runbook${data.total === 1 ? "" : "s"}`;
  emptyPanel.hidden = data.count !== 0;
  errorPanel.hidden = true;
  resultsContainer.hidden = data.count === 0;
  if (data.count === 0) {
    const noRecords = data.total === 0;
    document.querySelector("#empty-title").textContent = noRecords
      ? "No runbooks yet"
      : "No matching runbooks";
    document.querySelector("#empty-description").textContent = noRecords
      ? "Runbooks added to your library will appear here."
      : "Try a different keyword or clear some filters.";
  }
}

async function loadRunbooks() {
  const currentRequest = ++requestNumber;
  const parameters = getParameters();
  resultsRegion.setAttribute("aria-busy", "true");
  resultCount.textContent = "Loading runbooks…";
  emptyPanel.hidden = true;
  errorPanel.hidden = true;

  const query = new URLSearchParams(parameters);
  try {
    const response = await fetch(`${apiUrl}?${query.toString()}`, {
      headers: { Accept: "application/json" },
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Runbooks could not be loaded.");
    if (currentRequest !== requestNumber) return;

    for (const name of filterIds) {
      const label = `All ${filterLabels[name]}`;
      setOptions(filterElements[name], data.filters[name], label, parameters[name]);
    }
    searchInput.value = parameters.q;
    sortElement.value = parameters.sort;
    renderResults(data);
  } catch (error) {
    if (currentRequest !== requestNumber) return;
    resultsContainer.replaceChildren();
    resultsContainer.hidden = true;
    emptyPanel.hidden = true;
    errorPanel.hidden = false;
    resultCount.textContent = "Runbooks unavailable";
    document.querySelector("#error-description").textContent = error.message;
  } finally {
    if (currentRequest === requestNumber) resultsRegion.setAttribute("aria-busy", "false");
  }
}

function applyControlsToUrl() {
  const parameters = {
    q: searchInput.value.trim(),
    technology: filterElements.technology.value,
    category: filterElements.category.value,
    environment: filterElements.environment.value,
    severity: filterElements.severity.value,
    sort: sortElement.value,
  };
  updateUrl(parameters);
  loadRunbooks();
}

searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  applyControlsToUrl();
});

searchInput.addEventListener("input", () => {
  window.clearTimeout(debounceTimer);
  debounceTimer = window.setTimeout(applyControlsToUrl, 180);
});

for (const select of [...Object.values(filterElements), sortElement]) {
  select.addEventListener("change", applyControlsToUrl);
}

function clearFilters() {
  searchInput.value = "";
  for (const select of Object.values(filterElements)) select.value = "";
  sortElement.value = "updated";
  updateUrl({});
  loadRunbooks();
}

document.querySelector("#clear-filters").addEventListener("click", clearFilters);
document.querySelector("[data-clear-filters]").addEventListener("click", clearFilters);
document.querySelector("#retry-listing").addEventListener("click", loadRunbooks);
window.addEventListener("popstate", loadRunbooks);

const initialParameters = getParameters();
searchInput.value = initialParameters.q;
for (const name of filterIds) filterElements[name].value = initialParameters[name];
sortElement.value = initialParameters.sort;
loadRunbooks();
})();
