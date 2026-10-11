(() => {
  const form = document.querySelector("#runbook-form");
  const mode = document.body.dataset.formMode;
  const collectionApiUrl = document.body.dataset.apiUrl;
  const resultsUrl = document.body.dataset.resultsUrl || "/runbooks";
  const initialRunbookElement = document.querySelector("#initial-runbook");
  const initialRunbook = initialRunbookElement
    ? JSON.parse(initialRunbookElement.textContent)
    : null;
  const feedback = document.querySelector("#form-feedback");
  const previewDialog = document.querySelector("#runbook-preview");
  const previewContent = document.querySelector("#preview-content");
  const previewFeedback = document.querySelector("#preview-feedback");
  const saveButton = document.querySelector("#save-runbook");
  let dirty = false;
  let previewedPayload = null;
  let generatedId = initialRunbook?.id || null;
  const createdAt = initialRunbook?.created_at || new Date().toISOString();

  function splitList(value) {
    return value
      .split(/[\n,]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function makeField(row, key, labelText, tagName = "textarea") {
    const wrapper = document.createElement("div");
    wrapper.className = "form-field step-field";
    const inputId = `step-${row.dataset.stepList}-${row.dataset.stepIndex}-${key}`;
    const label = document.createElement("label");
    label.htmlFor = inputId;
    label.textContent = labelText;
    const input = document.createElement(tagName);
    input.id = inputId;
    input.name = inputId;
    input.dataset.stepField = key;
    if (tagName === "textarea") input.rows = key === "description" ? 2 : 2;
    wrapper.append(label, input);
    return wrapper;
  }

  function updateStepButtons(list) {
    const rows = [...list.querySelectorAll("[data-step-row]")];
    rows.forEach((row, index) => {
      row.dataset.stepIndex = String(index + 1);
      row.querySelector(".step-position").textContent = `Step ${index + 1}`;
      for (const field of row.querySelectorAll("[data-step-field]")) {
        const inputId = `step-${list.dataset.stepList}-${index + 1}-${field.dataset.stepField}`;
        field.id = inputId;
        field.name = inputId;
        field.labels[0].htmlFor = inputId;
      }
      row.querySelector('[data-step-action="up"]').disabled = index === 0;
      row.querySelector('[data-step-action="down"]').disabled = index === rows.length - 1;
    });
  }

  function addStep(list, data = {}) {
    const row = document.createElement("fieldset");
    row.className = "step-row";
    row.dataset.stepRow = "";
    row.dataset.stepList = list.dataset.stepList;
    row.dataset.stepIndex = String(list.querySelectorAll("[data-step-row]").length + 1);

    const header = document.createElement("div");
    header.className = "step-row-header";
    const position = document.createElement("span");
    position.className = "step-position";
    const controls = document.createElement("div");
    controls.className = "step-controls";

    for (const [action, text, label] of [
      ["up", "Move up", "Move step up"],
      ["down", "Move down", "Move step down"],
      ["remove", "Remove", "Remove step"],
    ]) {
      const button = document.createElement("button");
      button.className = "button button-secondary step-action";
      button.type = "button";
      button.dataset.stepAction = action;
      button.textContent = text;
      button.setAttribute("aria-label", label);
      controls.append(button);
    }
    header.append(position, controls);

    const fields = document.createElement("div");
    fields.className = "form-grid step-field-grid";
    const description = makeField(row, "description", "Description");
    const command = makeField(row, "command", "Command (displayed only)");
    const expected = makeField(row, "expected_result", "Expected result");
    const notes = makeField(row, "notes", "Notes");
    description.classList.add("form-field-wide");
    command.classList.add("form-field-wide");
    for (const field of [description, command, expected, notes]) fields.append(field);
    row.append(header, fields);

    for (const input of row.querySelectorAll("[data-step-field]")) {
      input.value = data[input.dataset.stepField] || "";
    }
    list.append(row);
    updateStepButtons(list);
  }

  function stepRows(fieldName) {
    return [...document.querySelector(`[data-step-list="${fieldName}"]`).querySelectorAll("[data-step-row]")]
      .map((row, index) => {
        const step = {};
        for (const input of row.querySelectorAll("[data-step-field]")) {
          step[input.dataset.stepField] = input.value.trim();
        }
        const hasContent = Object.values(step).some(Boolean);
        if (!hasContent) return null;
        if (!step.description) {
          return { index, error: `Step ${index + 1} needs a description.` };
        }
        for (const key of ["command", "expected_result", "notes"]) {
          if (!step[key]) delete step[key];
        }
        return step;
      });
  }

  function makeId(title) {
    const slug = title
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 26) || "runbook";
    const bytes = new Uint8Array(16);
    if (window.crypto?.getRandomValues) {
      window.crypto.getRandomValues(bytes);
    } else {
      bytes.forEach((_, index) => { bytes[index] = Math.floor(Math.random() * 256); });
    }
    const suffix = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    return `${slug}-${suffix}`;
  }

  function fieldValue(id) {
    return document.querySelector(`#${id}`).value.trim();
  }

  function composeRunbook() {
    const investigation = stepRows("investigation_steps");
    const resolution = stepRows("resolution_steps");
    const invalidStep = [...investigation, ...resolution].find(
      (step) => step && step.error,
    );
    if (invalidStep) {
      return { error: invalidStep.error };
    }

    const title = fieldValue("title");
    if (!title) {
      document.querySelector("#title").focus();
      return { error: "Enter a title." };
    }
    if (!generatedId) generatedId = makeId(title);

    const timestamp = createdAt;
    const runbook = {
      ...(initialRunbook || {}),
      id: generatedId,
      title,
      category: fieldValue("category"),
      technologies: splitList(fieldValue("technologies")),
      environment: fieldValue("environment"),
      severity: fieldValue("severity"),
      symptoms: splitList(fieldValue("symptoms")),
      error_messages: splitList(fieldValue("error-messages")),
      root_cause: {
        status: fieldValue("root-cause-status"),
        details: fieldValue("root-cause-details"),
      },
      prerequisites: splitList(fieldValue("prerequisites")),
      investigation_steps: investigation.filter(Boolean),
      commands: splitList(fieldValue("commands")),
      resolution_steps: resolution.filter(Boolean),
      verification_steps: splitList(fieldValue("verification-steps")),
      rollback_steps: splitList(fieldValue("rollback-steps")),
      prevention: splitList(fieldValue("prevention")),
      tags: splitList(fieldValue("tags")),
      created_at: timestamp,
      updated_at: mode === "create"
        ? timestamp
        : (initialRunbook?.updated_at || timestamp),
    };
    const summary = fieldValue("summary");
    if (summary || Object.hasOwn(runbook, "summary")) runbook.summary = summary;
    return { runbook };
  }

  function loadRunbook(runbook) {
    for (const field of ["title", "category", "environment", "severity"]) {
      const element = document.querySelector(`#${field}`);
      element.value = runbook[field] || "";
    }
    document.querySelector("#technologies").value = (runbook.technologies || []).join("\n");
    document.querySelector("#summary").value = runbook.summary || "";
    document.querySelector("#symptoms").value = (runbook.symptoms || []).join("\n");
    document.querySelector("#error-messages").value = (runbook.error_messages || []).join("\n");
    document.querySelector("#root-cause-status").value = runbook.root_cause?.status || "unknown";
    document.querySelector("#root-cause-details").value = runbook.root_cause?.details || "";
    document.querySelector("#prerequisites").value = (runbook.prerequisites || []).join("\n");
    document.querySelector("#commands").value = (runbook.commands || []).join("\n");
    document.querySelector("#verification-steps").value = (runbook.verification_steps || []).join("\n");
    document.querySelector("#rollback-steps").value = (runbook.rollback_steps || []).join("\n");
    document.querySelector("#prevention").value = (runbook.prevention || []).join("\n");
    document.querySelector("#tags").value = (runbook.tags || []).join("\n");

    for (const fieldName of ["investigation_steps", "resolution_steps"]) {
      const list = document.querySelector(`[data-step-list="${fieldName}"]`);
      const steps = runbook[fieldName] || [];
      if (steps.length) {
        for (const step of steps) {
          addStep(list, typeof step === "string" ? { description: step } : step);
        }
      } else {
        addStep(list);
      }
    }
  }

  function invalidatePreview() {
    dirty = true;
    previewedPayload = null;
    feedback.textContent = "";
    previewFeedback.textContent = "";
    if (previewDialog.open) previewDialog.close();
  }

  function openPreview() {
    if (!form.reportValidity()) return;
    const result = composeRunbook();
    if (!result.runbook) {
      feedback.textContent = result.error;
      return;
    }
    feedback.textContent = "";
    previewFeedback.textContent = "";
    previewedPayload = JSON.stringify(result.runbook);
    previewContent.textContent = JSON.stringify(result.runbook, null, 2);
    previewDialog.showModal();
    document.querySelector("#close-preview").focus();
  }

  async function saveRunbook() {
    if (!form.reportValidity()) {
      previewDialog.close();
      return;
    }
    const result = composeRunbook();
    if (!result.runbook) {
      feedback.textContent = result.error;
      previewDialog.close();
      return;
    }
    if (previewedPayload !== JSON.stringify(result.runbook)) {
      feedback.textContent = "Review the latest changes in the preview before saving.";
      previewDialog.close();
      return;
    }

    saveButton.disabled = true;
    saveButton.textContent = "Saving…";
    previewFeedback.textContent = "";
    try {
      const isEdit = mode === "edit";
      const endpoint = isEdit
        ? `${collectionApiUrl}/${encodeURIComponent(result.runbook.id)}`
        : collectionApiUrl;
      const response = await fetch(endpoint, {
        method: isEdit ? "PUT" : "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify(result.runbook),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Runbook could not be saved.");

      dirty = false;
      const detailUrl = new URL(
        `/runbooks/${encodeURIComponent(result.runbook.id)}`,
        window.location.origin,
      );
      detailUrl.searchParams.set("return_to", resultsUrl);
      detailUrl.searchParams.set("saved", isEdit ? "updated" : "created");
      window.location.assign(`${detailUrl.pathname}${detailUrl.search}`);
    } catch (error) {
      previewFeedback.textContent = error.message || "Runbook could not be saved.";
      saveButton.disabled = false;
      saveButton.textContent = "Save runbook";
    }
  }

  document.querySelectorAll("[data-add-step]").forEach((button) => {
    button.addEventListener("click", () => {
      addStep(document.querySelector(`[data-step-list="${button.dataset.addStep}"]`));
      invalidatePreview();
    });
  });

  document.querySelectorAll("[data-step-list]").forEach((list) => {
    list.addEventListener("click", (event) => {
      const button = event.target.closest("[data-step-action]");
      if (!button) return;
      const row = button.closest("[data-step-row]");
      const action = button.dataset.stepAction;
      if (action === "remove") {
        row.remove();
      } else if (action === "up" && row.previousElementSibling) {
        list.insertBefore(row, row.previousElementSibling);
      } else if (action === "down" && row.nextElementSibling) {
        list.insertBefore(row.nextElementSibling, row);
      }
      updateStepButtons(list);
      invalidatePreview();
    });
  });

  form.addEventListener("input", invalidatePreview);
  form.addEventListener("change", invalidatePreview);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    saveRunbook();
  });
  document.querySelector("#preview-button").addEventListener("click", openPreview);
  document.querySelector("#close-preview").addEventListener("click", () => previewDialog.close());
  document.querySelector("#preview-cancel").addEventListener("click", () => previewDialog.close());
  saveButton.addEventListener("click", () => form.requestSubmit());
  document.querySelector("#cancel-button").addEventListener("click", (event) => {
    if (dirty && !window.confirm("Discard unsaved runbook changes?")) event.preventDefault();
  });
  window.addEventListener("beforeunload", (event) => {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });

  if (initialRunbook) loadRunbook(initialRunbook);
  else {
    for (const list of document.querySelectorAll("[data-step-list]")) addStep(list);
  }
})();
