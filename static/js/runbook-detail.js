const apiUrl = document.body.dataset.apiUrl;
const returnTo = document.body.dataset.returnTo || "/runbooks";
const detailFeedback = document.querySelector("#detail-feedback");
detailFeedback.textContent = document.body.dataset.notice || "";

document.querySelector("#delete-runbook").addEventListener("click", async () => {
  const title = document.querySelector(".detail-heading h1").textContent;
  if (!window.confirm(`Delete "${title}"? This cannot be undone.`)) return;

  detailFeedback.textContent = "Deleting runbook…";
  try {
    const response = await fetch(apiUrl, {
      method: "DELETE",
      headers: { Accept: "application/json" },
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Runbook could not be deleted.");
    window.location.assign(returnTo);
  } catch (error) {
    detailFeedback.textContent = error.message || "Runbook could not be deleted.";
  }
});

for (const button of document.querySelectorAll(".copy-command")) {
  button.addEventListener("click", async () => {
    const command = button.closest(".command-block").querySelector("code").textContent;
    const feedback = button.parentElement.querySelector(".copy-feedback");
    feedback.textContent = "";

    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard access is not available in this browser.");
      }
      await navigator.clipboard.writeText(command);
      feedback.textContent = "Copied.";
    } catch {
      feedback.textContent = "Copy failed. Select and copy the command manually.";
    }
  });
}
