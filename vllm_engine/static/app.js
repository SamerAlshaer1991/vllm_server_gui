const bootstrap = JSON.parse(document.querySelector("#bootstrap-data").textContent);
const argCards = [...document.querySelectorAll("[data-arg-card]")];
const sectionCards = [...document.querySelectorAll("[data-section]")];
const searchInput = document.querySelector("#search-input");
const preview = document.querySelector("#command-preview");
const activeCount = document.querySelector("#active-count");
const copyButton = document.querySelector("#copy-command");
const runButton = document.querySelector("#run-command");
const stopButton = document.querySelector("#stop-command");
const syncArgsButton = document.querySelector("#sync-args");
const clearLogsButton = document.querySelector("#clear-logs");
const expandAllButton = document.querySelector("[data-expand-all]");
const collapseAllButton = document.querySelector("[data-collapse-all]");
const flashBanner = document.querySelector("#flash-banner");
const profileInput = document.querySelector("#profile-name");
const saveProfileButton = document.querySelector("#save-profile");
const profileList = document.querySelector("#profile-list");
const profileEmpty = document.querySelector("#profile-empty");
const runtimeState = document.querySelector("#runtime-state");
const runtimeCommand = document.querySelector("#runtime-command");
const runtimePid = document.querySelector("#runtime-pid");
const runtimeLog = document.querySelector("#runtime-log");
const runtimeMessage = document.querySelector("#runtime-message");

let profiles = bootstrap.profiles || [];
let runtime = bootstrap.runtime || {};

function splitListValue(raw) {
  return String(raw || "")
    .split(/[\n,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function shellQuote(value) {
  if (!value) {
    return "''";
  }
  if (/^[A-Za-z0-9_./:=,@%+-]+$/.test(value)) {
    return value;
  }
  return `'${value.replace(/'/g, `'\"'\"'`)}'`;
}

function formatCommand(parts) {
  return parts.map(shellQuote).join(" ");
}

function notify(message, kind = "info") {
  flashBanner.textContent = message;
  flashBanner.hidden = false;
  flashBanner.classList.toggle("is-error", kind === "error");
}

function syncControlState(card) {
  const enabled = card.querySelector("[data-enable]").checked;
  const control = card.querySelector("[data-value-control]");
  if (control) {
    control.disabled = !enabled;
  }
  card.classList.toggle("is-enabled", enabled);
}

function getCardState(card) {
  const valueControl = card.querySelector("[data-value-control]");
  return {
    enabled: card.querySelector("[data-enable]").checked,
    value: valueControl ? valueControl.value : "",
  };
}

function serializeState() {
  const state = {};
  argCards.forEach((card) => {
    const key = card.dataset.key;
    const current = getCardState(card);
    if (current.enabled || String(current.value || "").trim()) {
      state[key] = current;
    }
  });
  return state;
}

function resetControl(control) {
  if (!control) {
    return;
  }
  control.value = control.dataset.initialValue || "";
}

function clearState() {
  argCards.forEach((card) => {
    card.querySelector("[data-enable]").checked = false;
    resetControl(card.querySelector("[data-value-control]"));
    syncControlState(card);
  });
}

function applyState(state) {
  clearState();
  Object.entries(state || {}).forEach(([key, value]) => {
    const card = document.querySelector(`[data-key="${key}"]`);
    if (!card) {
      return;
    }
    card.querySelector("[data-enable]").checked = Boolean(value.enabled);
    const control = card.querySelector("[data-value-control]");
    if (control && value.value !== undefined) {
      control.value = value.value;
    }
    syncControlState(card);
  });
  buildCommandPreview();
}

function buildCommandPreview() {
  const command = [...(bootstrap.command_parts || ["vllm"])];
  let enabledArgs = 0;

  argCards.forEach((card) => {
    if (!card.querySelector("[data-enable]").checked) {
      return;
    }

    enabledArgs += 1;
    const controlType = card.dataset.control;
    const valueControl = card.querySelector("[data-value-control]");

    if (controlType === "boolean") {
      const value = valueControl.value;
      if (value === "true" && card.dataset.trueFlag) {
        command.push(card.dataset.trueFlag);
      } else if (value === "false" && card.dataset.falseFlag) {
        command.push(card.dataset.falseFlag);
      }
      return;
    }

    const value = String(valueControl.value || "").trim();
    if (!value) {
      return;
    }

    if (card.dataset.positional === "true") {
      command.push(value);
      return;
    }

    if (card.dataset.repeatable === "true") {
      splitListValue(value).forEach((item) => {
        command.push(card.dataset.primaryFlag, item);
      });
      return;
    }

    if (card.dataset.multi === "true") {
      const values = splitListValue(value);
      if (values.length > 0) {
        command.push(card.dataset.primaryFlag, ...values);
      }
      return;
    }

    if (value) {
      command.push(card.dataset.primaryFlag, value);
    }
  });

  preview.textContent = formatCommand(command);
  activeCount.textContent = String(enabledArgs);
  return { commandPreview: preview.textContent, selectedCount: enabledArgs };
}

function filterCards() {
  if (!searchInput) {
    return;
  }
  const query = searchInput.value.trim().toLowerCase();
  sectionCards.forEach((section) => {
    const cards = [...section.querySelectorAll("[data-arg-card]")];
    const visibleCount = cards.reduce((count, card) => {
      const matches = !query || card.dataset.search.includes(query);
      card.hidden = !matches;
      return matches ? count + 1 : count;
    }, 0);
    section.hidden = visibleCount === 0;
    if (query && visibleCount > 0) {
      section.open = true;
    }
  });
}

function setSectionSelection(section, enabled) {
  section.querySelectorAll("[data-arg-card]").forEach((card) => {
    if (card.hidden) {
      return;
    }
    card.querySelector("[data-enable]").checked = enabled;
    syncControlState(card);
  });
  buildCommandPreview();
}

function renderProfiles() {
  profileList.innerHTML = "";
  profileEmpty.hidden = profiles.length > 0;
  profiles.forEach((profile) => {
    const element = document.createElement("article");
    element.className = "profile-item";
    element.innerHTML = `
      <strong>${profile.name}</strong>
      <div class="profile-meta">
        <span>${profile.selected_count} enabled args</span>
        <span>${profile.saved_at}</span>
      </div>
      <code>${profile.command_preview}</code>
      <div class="profile-actions">
        <button type="button" class="ghost-button" data-load-profile="${profile.name}">Load</button>
        <button type="button" class="ghost-button" data-delete-profile="${profile.name}">Delete</button>
      </div>
    `;
    profileList.appendChild(element);
  });
}

function updateRuntime(nextRuntime) {
  runtime = nextRuntime || runtime;
  runtimeState.textContent = runtime.state || "idle";
  runtimeCommand.textContent = runtime.command_display || "n/a";
  runtimePid.textContent = runtime.pid || "n/a";
  runtimeLog.textContent = runtime.log_path || "No log file yet.";
  runtimeMessage.textContent = runtime.message || "No vLLM process is running.";
  runButton.disabled = Boolean(runtime.running);
  stopButton.disabled = !runtime.running;
}

async function postJSON(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.message || "The request failed.");
  }
  return data;
}

async function refreshRuntime() {
  const response = await fetch("/api/runtime");
  const data = await response.json();
  if (data.ok) {
    updateRuntime(data.runtime);
  }
}

async function saveProfile() {
  const name = profileInput.value.trim();
  if (!name) {
    notify("Enter a profile name before saving.", "error");
    return;
  }
  const summary = buildCommandPreview();
  const data = await postJSON("/api/profiles/save", {
    name,
    state: serializeState(),
    command_preview: summary.commandPreview,
    selected_count: summary.selectedCount,
  });
  profiles = data.profiles || profiles;
  renderProfiles();
  notify(data.message);
}

async function loadProfile(name) {
  const data = await postJSON("/api/profiles/load", {
    name,
  });
  applyState(data.profile.state || {});
  profileInput.value = data.profile.name || "";
  notify(data.message);
}

async function deleteProfile(name) {
  const data = await postJSON("/api/profiles/delete", {
    name,
  });
  profiles = data.profiles || [];
  renderProfiles();
  notify(data.message);
}

async function runCommand() {
  const data = await postJSON("/api/runtime/run", {
    state: serializeState(),
  });
  updateRuntime(data.runtime);
  notify(data.message);
}

async function stopCommand() {
  const data = await postJSON("/api/runtime/stop", {});
  updateRuntime(data.runtime);
  notify(data.message);
}

async function syncArguments() {
  if (syncArgsButton) {
    syncArgsButton.disabled = true;
  }
  try {
    const data = await postJSON("/api/schema/sync", {});
    notify(`${data.message} Reloading the page...`);
    window.setTimeout(() => {
      window.location.reload();
    }, 700);
  } finally {
    if (syncArgsButton) {
      syncArgsButton.disabled = false;
    }
  }
}

async function clearLogs() {
  if (!window.confirm("Delete all log files in the logs folder?")) {
    return;
  }
  if (clearLogsButton) {
    clearLogsButton.disabled = true;
  }
  try {
    const data = await postJSON("/api/logs/clear", {});
    notify(data.message);
    await refreshRuntime();
  } finally {
    if (clearLogsButton) {
      clearLogsButton.disabled = false;
    }
  }
}

argCards.forEach((card) => {
  const toggle = card.querySelector("[data-enable]");
  const control = card.querySelector("[data-value-control]");
  syncControlState(card);
  toggle.addEventListener("change", () => {
    syncControlState(card);
    buildCommandPreview();
  });
  if (control) {
    control.addEventListener("input", buildCommandPreview);
    control.addEventListener("change", buildCommandPreview);
  }
});

sectionCards.forEach((section) => {
  const selectButton = section.querySelector("[data-select-section]");
  const clearButton = section.querySelector("[data-clear-section]");
  selectButton.addEventListener("click", () => setSectionSelection(section, true));
  clearButton.addEventListener("click", () => setSectionSelection(section, false));
});

profileList.addEventListener("click", async (event) => {
  const loadTarget = event.target.closest("[data-load-profile]");
  const deleteTarget = event.target.closest("[data-delete-profile]");
  try {
    if (loadTarget) {
      await loadProfile(loadTarget.dataset.loadProfile);
    }
    if (deleteTarget) {
      await deleteProfile(deleteTarget.dataset.deleteProfile);
    }
  } catch (error) {
    notify(error.message, "error");
  }
});

if (searchInput) {
  searchInput.addEventListener("input", filterCards);
}
if (expandAllButton) {
  expandAllButton.addEventListener("click", () => {
    sectionCards.forEach((section) => {
      if (!section.hidden) {
        section.open = true;
      }
    });
  });
}
if (collapseAllButton) {
  collapseAllButton.addEventListener("click", () => {
    sectionCards.forEach((section) => {
      section.open = false;
    });
  });
}

copyButton.addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText(preview.textContent);
    notify("Copied the current command preview.");
  } catch {
    notify("Clipboard access failed in this browser context.", "error");
  }
});

saveProfileButton.addEventListener("click", async () => {
  try {
    await saveProfile();
  } catch (error) {
    notify(error.message, "error");
  }
});

runButton.addEventListener("click", async () => {
  try {
    await runCommand();
  } catch (error) {
    notify(error.message, "error");
  }
});

stopButton.addEventListener("click", async () => {
  try {
    await stopCommand();
  } catch (error) {
    notify(error.message, "error");
  }
});

if (syncArgsButton) {
  syncArgsButton.addEventListener("click", async () => {
    try {
      await syncArguments();
    } catch (error) {
      notify(error.message, "error");
    }
  });
}

if (clearLogsButton) {
  clearLogsButton.addEventListener("click", async () => {
    try {
      await clearLogs();
    } catch (error) {
      notify(error.message, "error");
    }
  });
}

renderProfiles();
filterCards();
buildCommandPreview();
updateRuntime(runtime);
window.setInterval(() => {
  refreshRuntime().catch(() => {});
}, 5000);
