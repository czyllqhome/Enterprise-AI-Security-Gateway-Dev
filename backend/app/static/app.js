const state = {
  sessions: [],
  selectedSessionId: null,
  pendingPreview: null,
  username: "Guest",
  providers: [],
  scanners: [],
  alertSignature: null,
  dismissedAlertSignature: null,
};

const elements = {
  providerChip: document.getElementById("provider-chip"),
  scannerChip: document.getElementById("scanner-chip"),
  gatewayPipeline: document.getElementById("gateway-pipeline"),
  userGuidanceTitle: document.getElementById("user-guidance-title"),
  userGuidanceText: document.getElementById("user-guidance-text"),
  userGuidanceBadges: document.getElementById("user-guidance-badges"),
  totalScans: document.getElementById("total-scans"),
  passedCount: document.getElementById("passed-count"),
  blockedCount: document.getElementById("blocked-count"),
  piiCount: document.getElementById("pii-count"),
  providerSelect: document.getElementById("provider-select"),
  modelSelect: document.getElementById("model-select"),
  usernameInput: document.getElementById("username-input"),
  selectedProviderStatus: document.getElementById("selected-provider-status"),
  selectedKeyStatus: document.getElementById("selected-key-status"),
  sessionList: document.getElementById("session-list"),
  sessionTitle: document.getElementById("session-title"),
  messageList: document.getElementById("message-list"),
  chatForm: document.getElementById("chat-form"),
  messageInput: document.getElementById("message-input"),
  sendButton: document.getElementById("send-btn"),
  clearButton: document.getElementById("clear-btn"),
  newSessionButton: document.getElementById("new-session-btn"),
  deleteSessionButton: document.getElementById("delete-session-btn"),
  statusText: document.getElementById("status-text"),
  presetGrid: document.getElementById("preset-grid"),
  scannerStatusList: document.getElementById("scanner-status-list"),
  promptPatternList: document.getElementById("prompt-pattern-list"),
  useCaseStrip: document.getElementById("use-case-strip"),
  incidentFeed: document.getElementById("incident-feed"),
  lastScanStatus: document.getElementById("last-scan-status"),
  lastScanProvider: document.getElementById("last-scan-provider"),
  lastScanScanners: document.getElementById("last-scan-scanners"),
  lastScanEntityTypes: document.getElementById("last-scan-entity-types"),
  lastScanReason: document.getElementById("last-scan-reason"),
  lastScanInput: document.getElementById("last-scan-input"),
  lastScanSanitized: document.getElementById("last-scan-sanitized"),
  assistantRawOutput: document.getElementById("assistant-raw-output"),
  assistantDisplayOutput: document.getElementById("assistant-display-output"),
  detailEntityTableBody: document.getElementById("detail-entity-table-body"),
  scannerAlertToast: document.getElementById("scanner-alert-toast"),
  scannerAlertTitle: document.getElementById("scanner-alert-title"),
  scannerAlertMessage: document.getElementById("scanner-alert-message"),
  scannerAlertCount: document.getElementById("scanner-alert-count"),
  scannerAlertClose: document.getElementById("scanner-alert-close"),
  modal: document.getElementById("guardrail-modal"),
  modalEyebrow: document.getElementById("modal-eyebrow"),
  modalTitle: document.getElementById("modal-title"),
  closeModalButton: document.getElementById("close-modal-btn"),
  modalBackButton: document.getElementById("modal-back-btn"),
  modalSendButton: document.getElementById("modal-send-btn"),
  modalOriginalText: document.getElementById("modal-original-text"),
  modalSanitizedText: document.getElementById("modal-sanitized-text"),
  entityTableBody: document.getElementById("entity-table-body"),
  businessSensitivePanel: document.getElementById("business-sensitive-panel"),
  businessSensitiveRisk: document.getElementById("business-sensitive-risk"),
  businessSensitiveSummary: document.getElementById("business-sensitive-summary"),
  businessSensitiveDetails: document.getElementById("business-sensitive-details"),
};

document.addEventListener("DOMContentLoaded", async () => {
  state.username = window.localStorage.getItem("chat_username") || "Guest";
  elements.usernameInput.value = state.username;
  bindEvents();
  await bootstrap();
});

function bindEvents() {
  elements.newSessionButton.addEventListener("click", createSession);
  elements.usernameInput.addEventListener("change", persistUsername);
  elements.deleteSessionButton.addEventListener("click", deleteCurrentSession);
  elements.chatForm.addEventListener("submit", handleSend);
  elements.clearButton.addEventListener("click", clearComposer);
  elements.closeModalButton.addEventListener("click", closeModal);
  elements.modalBackButton.addEventListener("click", closeModal);
  elements.modalSendButton.addEventListener("click", confirmSanitizedSend);
  elements.presetGrid.addEventListener("click", handlePresetClick);
  elements.providerSelect.addEventListener("change", handleProviderSelectionChange);
  elements.modelSelect.addEventListener("change", handleModelSelectionChange);
  elements.scannerAlertClose.addEventListener("click", dismissScannerAlert);
  bindSyncedScroll(elements.assistantRawOutput, elements.assistantDisplayOutput);
}

async function bootstrap() {
  await loadProviders();
  await Promise.all([
    loadConsoleSummary(),
    loadScannerStatuses(),
    loadLastScan(),
    loadSessions(),
    loadDashboardSnapshot(),
  ]);
}

function persistUsername() {
  const normalized = elements.usernameInput.value.trim() || "Guest";
  state.username = normalized;
  elements.usernameInput.value = normalized;
  window.localStorage.setItem("chat_username", normalized);
  state.alertSignature = null;
  state.dismissedAlertSignature = null;
  loadConsoleSummary();
}

async function loadProviders() {
  const response = await fetch("/api/providers");
  const data = await response.json();
  state.providers = data.providers || [];
  populateProviderSelect();
}

async function loadConsoleSummary() {
  const query = new URLSearchParams({ username: state.username || "Guest" });
  const response = await fetch(`/api/console/summary?${query.toString()}`);
  const summary = await response.json();
  elements.scannerChip.textContent = summary.active_scanner_count
    ? `${summary.active_scanner_count} Scanners Active`
    : "Scanning disabled";
  updateText(elements.totalScans, summary.total_scans);
  updateText(elements.passedCount, summary.passed_count);
  updateText(elements.blockedCount, summary.blocked_count);
  updateText(elements.piiCount, summary.pii_redaction_count);
  refreshProviderChip(elements.providerSelect.value || summary.provider);
  updateScannerAlert(summary);
  renderGuidance(summary);
}

function updateText(element, value) {
  if (element) {
    element.textContent = value;
  }
}

async function loadDashboardSnapshot() {
  const response = await fetch("/api/console/dashboard");
  const dashboard = await response.json();
  renderPromptPatterns(dashboard);
  renderUseCases(dashboard.use_cases || []);
  renderIncidents(dashboard.incidents || []);
}

async function loadScannerStatuses() {
  const response = await fetch("/api/console/scanners");
  const data = await response.json();
  state.scanners = data.scanners || [];
  elements.scannerStatusList.innerHTML = "";
  state.scanners.filter(shouldDisplayScanner).forEach((scanner) => {
    const isToggleable = isInputScanner(scanner.id);
    const item = document.createElement("label");
    item.className = `scanner-item scanner-toggle-item ${scanner.enabled ? "" : "scanner-toggle-disabled"}`;
    item.setAttribute("title", scanner.detail);
    if (!isToggleable) {
      item.classList.add("scanner-toggle-readonly");
    }
    item.innerHTML = `
      <span class="scanner-toggle-main">
        ${isToggleable ? `<input type="checkbox" data-scanner-id="${escapeHtml(scanner.id)}" ${scanner.enabled ? "checked" : ""} />` : ""}
        <strong class="scanner-name">${escapeHtml(formatScannerDisplayName(scanner))}</strong>
      </span>
      <span class="scanner-badge ${scanner.active ? "scanner-badge-active" : "scanner-badge-inactive"}">
        ${formatScannerState(scanner)}
      </span>
    `;
    item.querySelector("input")?.addEventListener("change", handleScannerToggle);
    elements.scannerStatusList.appendChild(item);
  });
}

async function handleScannerToggle(event) {
  const scannerId = event.target.dataset.scannerId;
  const enabled = event.target.checked;
  const nextEnabled = new Set(
    state.scanners
      .filter((scanner) => isInputScanner(scanner.id) && scanner.enabled)
      .map((scanner) => scanner.id),
  );
  if (enabled) {
    nextEnabled.add(scannerId);
  } else {
    nextEnabled.delete(scannerId);
  }

  elements.statusText.textContent = "Updating scanner selection...";
  const response = await fetch("/api/console/scanners", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled_scanners: [...nextEnabled] }),
  });
  if (!response.ok) {
    const error = await response.json();
    elements.statusText.textContent = error.detail || "Failed to update scanner selection.";
    await loadScannerStatuses();
    return;
  }
  const data = await response.json();
  state.scanners = data.scanners || [];
  await Promise.all([loadScannerStatuses(), loadConsoleSummary(), loadLastScan(), loadDashboardSnapshot()]);
  elements.statusText.textContent = nextEnabled.size ? "Scanner selection updated." : "Scanning disabled.";
}

function isInputScanner(scannerId) {
  return [
    "bancode",
    "prompt_injection",
    "ban_topics",
    "privacy_filter",
    "business_sensitive",
    "custom_regex",
  ].includes(scannerId);
}

function formatScannerState(scanner) {
  if (!scanner.available) {
    return "Unavailable";
  }
  if (!scanner.enabled) {
    return "Disabled";
  }
  return scanner.active ? "Active" : "Inactive";
}

function shouldDisplayScanner(scanner) {
  return scanner.id !== "deanonymize";
}

function formatScannerDisplayName(scanner) {
  const labels = {
    bancode: "Source Code Scanner",
    prompt_injection: "Prompt Injection Scanner",
    ban_topics: "AI Ethical Scanner",
    privacy_filter: "Privacy Information Scanner",
    business_sensitive: "Business Sensitive Scanner",
    custom_regex: "Custom Rule Match",
  };
  return labels[scanner.id] || scanner.name;
}

async function loadLastScan() {
  const response = await fetch("/api/console/last-scan");
  const scan = await response.json();
  elements.lastScanStatus.textContent = scan.status;
  elements.lastScanProvider.textContent = `${scan.provider} / ${scan.model}`;
  elements.lastScanScanners.textContent = scan.scanners.length ? scan.scanners.join(", ") : "-";
  elements.lastScanEntityTypes.textContent = scan.entity_types.length ? scan.entity_types.join(", ") : "-";
  elements.lastScanReason.textContent = scan.blocked_reason || "-";
  elements.lastScanInput.textContent = scan.original_input || "No scans yet.";
  elements.lastScanSanitized.textContent = scan.sanitized_input || "-";
  elements.assistantRawOutput.textContent = scan.assistant_raw_output || "-";
  elements.assistantDisplayOutput.textContent = scan.assistant_display_output || "-";
  renderEntityTable(elements.detailEntityTableBody, scan.detected_entities || []);
}

async function loadSessions() {
  const response = await fetch("/api/sessions");
  state.sessions = await response.json();
  renderSessions();

  if (state.sessions.length > 0) {
    const targetSessionId = state.selectedSessionId || state.sessions[0].id;
    await selectSession(targetSessionId);
  } else {
    setEmptyChatState();
  }
}

function renderSessions() {
  elements.sessionList.innerHTML = "";
  if (!state.sessions.length) {
    elements.sessionList.innerHTML = `<p class="empty-state">No chats yet. Start a new one.</p>`;
    return;
  }

  state.sessions.forEach((session) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `session-item ${session.id === state.selectedSessionId ? "active-session" : ""}`;
    button.innerHTML = `
      <span class="session-item-title">${escapeHtml(session.title)}</span>
      <span class="session-item-meta">by ${escapeHtml(session.created_by || "Guest")}</span>
      <span class="session-item-submeta">${escapeHtml(formatProviderModel(session.provider, session.model))}</span>
      <span class="session-item-submeta">Updated ${escapeHtml(formatRelativeTime(session.updated_at))}</span>
    `;
    button.addEventListener("click", () => selectSession(session.id));
    elements.sessionList.appendChild(button);
  });
}

async function createSession() {
  const provider = elements.providerSelect.value;
  const model = elements.modelSelect.value;
  const response = await fetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: "", username: state.username, provider, model }),
  });
  const session = await response.json();
  state.selectedSessionId = session.id;
  await loadSessions();
}

async function selectSession(sessionId) {
  closeModal();
  state.selectedSessionId = sessionId;
  renderSessions();

  const response = await fetch(`/api/sessions/${sessionId}`);
  const session = await response.json();
  elements.sessionTitle.textContent = session.title;
  elements.providerSelect.value = session.provider;
  populateModelSelect(session.provider, session.model);
  updateCredentialStatus(session.provider);
  elements.sendButton.disabled = false;
  elements.deleteSessionButton.disabled = false;
  renderMessages(session.messages || []);
}

function formatProviderModel(provider, model) {
  const providerLabel = state.providers.find((item) => item.provider === provider)?.display_name || provider;
  return `${providerLabel} / ${model}`;
}

function formatRelativeTime(value) {
  if (!value) {
    return "just now";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "recently";
  }

  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.max(0, Math.round(diffMs / 60000));
  if (diffMinutes < 1) {
    return "just now";
  }
  if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  }

  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}h ago`;
  }

  const diffDays = Math.round(diffHours / 24);
  if (diffDays < 7) {
    return `${diffDays}d ago`;
  }

  return date.toLocaleDateString();
}

function renderMessages(messages) {
  elements.messageList.innerHTML = "";
  if (!messages.length) {
    elements.messageList.innerHTML = `<p class="empty-state">Messages will appear here.</p>`;
    return;
  }

  messages.forEach((message) => {
    const div = document.createElement("div");
    div.className = `message ${message.role === "user" ? "message-user" : "message-assistant"}`;
    const content = message.role === "assistant"
      ? (message.sanitized_content || message.original_content || message.used_content || "")
      : (message.used_content || message.sanitized_content || message.original_content || "");
    div.textContent = content;
    elements.messageList.appendChild(div);
  });
  elements.messageList.scrollTop = elements.messageList.scrollHeight;
}

function setEmptyChatState() {
  closeModal();
  state.selectedSessionId = null;
  elements.sessionTitle.textContent = "Select or create a chat";
  elements.messageList.innerHTML = `<p class="empty-state">Create a session to start chatting.</p>`;
  elements.messageInput.value = "";
  elements.sendButton.disabled = true;
  elements.deleteSessionButton.disabled = true;
}

async function deleteCurrentSession() {
  if (!state.selectedSessionId) {
    return;
  }
  if (!window.confirm("Delete this chat session?")) {
    return;
  }

  await fetch(`/api/sessions/${state.selectedSessionId}`, { method: "DELETE" });
  state.selectedSessionId = null;
  await loadSessions();
}

function handlePresetClick(event) {
  const button = event.target.closest(".preset-btn");
  if (!button) {
    return;
  }
  elements.messageInput.value = button.dataset.preset || "";
}

function clearComposer() {
  elements.messageInput.value = "";
  elements.statusText.textContent = "Composer cleared.";
}

function updateScannerAlert(summary) {
  const isActive = Boolean(summary.alert_active);
  const signature = `${summary.monitored_username || "Guest"}:${summary.total_trigger_count || 0}`;
  if (!isActive) {
    state.alertSignature = null;
    hideScannerAlert();
    return;
  }

  state.alertSignature = signature;
  elements.scannerAlertTitle.textContent = "Scanner Warning";
  elements.scannerAlertMessage.textContent =
    summary.alert_message ||
    `User ${summary.monitored_username || "Guest"} has triggered security scanners repeatedly.`;
  elements.scannerAlertCount.textContent = `${summary.total_trigger_count} total triggers`;

  if (state.dismissedAlertSignature === signature) {
    return;
  }
  showScannerAlert();
}

function renderGuidance(summary) {
  if (!elements.userGuidanceTitle || !elements.userGuidanceText || !elements.userGuidanceBadges) {
    return;
  }
  const hasAlert = Boolean(summary.alert_active);
  const blocked = Number(summary.blocked_count || 0);
  const pii = Number(summary.pii_redaction_count || 0);

  if (hasAlert) {
    elements.userGuidanceTitle.textContent = "High-risk usage pattern detected";
    elements.userGuidanceText.textContent =
      summary.alert_message ||
      "This user has triggered multiple guardrails and should be reviewed by an administrator.";
  } else if (blocked > 0) {
    elements.userGuidanceTitle.textContent = "Review before AI content leaves the company";
    elements.userGuidanceText.textContent =
      "Blocked prompts usually involve source code, prompt injection attempts, restricted topics, or business-sensitive material that should stay internal.";
  } else if (pii > 0) {
    elements.userGuidanceTitle.textContent = "PII masking is active";
    elements.userGuidanceText.textContent =
      "When names, IDs, phone numbers, cards, or secrets are detected, the system shows the sanitized version and asks the user to confirm.";
  } else {
    elements.userGuidanceTitle.textContent = "Safe by default";
    elements.userGuidanceText.textContent =
      "Prompts containing personal data, secrets, or contract terms will be masked, reviewed, or blocked before reaching the model.";
  }

  elements.userGuidanceBadges.innerHTML = [
    `<span class="status-chip ${pii ? "status-chip-active" : ""}">PII detections: ${escapeHtml(summary.pii_redaction_count)}</span>`,
    `<span class="status-chip ${blocked ? "status-chip-active" : ""}">Blocked prompts: ${escapeHtml(summary.blocked_count)}</span>`,
    `<span class="status-chip">Audit enabled</span>`,
  ].join("");
}

function showScannerAlert() {
  elements.scannerAlertToast.classList.remove("hidden");
  elements.scannerAlertToast.classList.add("alert-toast-visible");
}

function hideScannerAlert() {
  elements.scannerAlertToast.classList.add("hidden");
  elements.scannerAlertToast.classList.remove("alert-toast-visible");
}

function dismissScannerAlert() {
  state.dismissedAlertSignature = state.alertSignature;
  hideScannerAlert();
}

async function handleProviderSelectionChange() {
  const provider = elements.providerSelect.value;
  populateModelSelect(provider);
  updateCredentialStatus(provider);
  renderGatewayPipeline(provider);
  await syncSessionSettings();
}

async function handleModelSelectionChange() {
  await syncSessionSettings();
}

async function syncSessionSettings() {
  if (!state.selectedSessionId) {
    return;
  }

  const response = await fetch(`/api/sessions/${state.selectedSessionId}/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider: elements.providerSelect.value,
      model: elements.modelSelect.value,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    elements.statusText.textContent = error.detail || "Failed to update session settings.";
    return;
  }

  const session = await response.json();
  const current = state.sessions.find((item) => item.id === session.id);
  if (current) {
    current.provider = session.provider;
    current.model = session.model;
  }
  updateCredentialStatus(session.provider);
}

async function handleSend(event) {
  event.preventDefault();
  const message = elements.messageInput.value.trim();
  if (!message || !state.selectedSessionId) {
    return;
  }

  elements.sendButton.disabled = true;
  elements.statusText.textContent = "Scanning prompt...";

  const previewResponse = await fetch("/api/chat/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: state.selectedSessionId,
      message,
      username: state.username,
    }),
  });
  const preview = await previewResponse.json();
  await Promise.all([loadConsoleSummary(), loadLastScan(), loadDashboardSnapshot()]);

  if (preview.status === "blocked") {
    elements.sendButton.disabled = false;
    elements.statusText.textContent = preview.blocked_reason || "Prompt blocked by policy.";
    return;
  }

  if (preview.status === "needs_confirmation") {
    state.pendingPreview = preview;
    openModal(preview);
    elements.sendButton.disabled = false;
    elements.statusText.textContent = buildPreviewStatusText(preview);
    return;
  }

  await sendConfirmed(preview);
}

function openModal(preview) {
  configureModalForPreview(preview);
  elements.modalOriginalText.textContent = preview.original_message;
  elements.modalSanitizedText.textContent = preview.sanitized_message;
  renderEntityTable(elements.entityTableBody, preview.detected_entities);
  elements.modal.classList.remove("hidden");
  elements.modal.setAttribute("aria-hidden", "false");
}

function closeModal() {
  state.pendingPreview = null;
  elements.modal.classList.add("hidden");
  elements.modal.setAttribute("aria-hidden", "true");
}

function configureModalForPreview(preview) {
  const businessResult = preview.business_sensitive_result || {};
  const hasBusinessSensitive = Boolean(businessResult.contains_business_sensitive);
  const riskLevel = (businessResult.risk_level || "low").toLowerCase();
  const hasSensitiveEntities = Boolean(preview.has_sensitive_data);

  if (hasBusinessSensitive) {
    elements.modalEyebrow.textContent = "Business Sensitive Review";
    elements.modalTitle.textContent = "Review business-sensitive content before sending";
  } else {
    elements.modalEyebrow.textContent = "Sensitive Data Detected";
    elements.modalTitle.textContent = "Review before sending";
  }

  elements.modalSendButton.textContent = hasSensitiveEntities ? "Send sanitized version" : "Send anyway";
  renderBusinessSensitivePanel(businessResult, hasBusinessSensitive, riskLevel);
  renderPreviewGuidance(preview, hasBusinessSensitive, hasSensitiveEntities);
}

function renderPreviewGuidance(preview, hasBusinessSensitive, hasSensitiveEntities) {
  if (preview.status === "blocked") {
    elements.statusText.textContent = preview.blocked_reason || "Prompt blocked by policy.";
    return;
  }
  if (hasBusinessSensitive) {
    elements.statusText.textContent =
      `Detected business-sensitive content. Risk level: ${formatRiskLevel(preview.business_sensitive_result?.risk_level || "low")}.`;
    return;
  }
  if (hasSensitiveEntities) {
    elements.statusText.textContent = "Detected personal data or secrets. Review the masked version before sending.";
    return;
  }
  elements.statusText.textContent = "Prompt is ready to send.";
}

function renderBusinessSensitivePanel(result, hasBusinessSensitive, riskLevel) {
  if (!hasBusinessSensitive) {
    elements.businessSensitivePanel.classList.add("hidden");
    elements.businessSensitiveRisk.textContent = "Risk: low";
    elements.businessSensitiveRisk.className = "risk-pill";
    elements.businessSensitiveSummary.textContent = "";
    elements.businessSensitiveDetails.innerHTML = "";
    return;
  }

  elements.businessSensitivePanel.classList.remove("hidden");
  elements.businessSensitiveRisk.textContent = `Risk: ${formatRiskLevel(riskLevel)}`;
  elements.businessSensitiveRisk.className = `risk-pill risk-pill-${riskLevel}`;
  elements.businessSensitiveSummary.textContent =
    result.summary || "Potential business-sensitive content was detected.";

  if (riskLevel !== "medium") {
    elements.businessSensitiveDetails.innerHTML = "";
    return;
  }

  const categories = Array.isArray(result.categories) ? result.categories : [];
  if (!categories.length) {
    elements.businessSensitiveDetails.innerHTML =
      `<div class="business-sensitive-item">The model identified potentially business-sensitive content, but no finer-grained categories were returned.</div>`;
    return;
  }

  elements.businessSensitiveDetails.innerHTML = categories.map((category) => {
    const reason = category.reason
      ? escapeHtml(category.reason)
      : "The model identified potentially business-sensitive information.";
    const matchedText = category.matched_text
      ? `<div class="business-sensitive-item-text">Matched text: ${escapeHtml(category.matched_text)}</div>`
      : "";
    return `
      <div class="business-sensitive-item">
        <strong>${escapeHtml(formatBusinessCategoryName(category.name || "business-sensitive"))}</strong>
        <div>${reason}</div>
        ${matchedText}
      </div>
    `;
  }).join("");
}

function buildPreviewStatusText(preview) {
  const businessResult = preview.business_sensitive_result || {};
  if (businessResult.contains_business_sensitive) {
    return `Detected business-sensitive content. Risk level: ${formatRiskLevel(businessResult.risk_level || "low")}.`;
  }
  return "Sensitive data detected. Please review the sanitized version before sending.";
}

function renderPromptPatterns(dashboard) {
  if (!elements.promptPatternList) {
    return;
  }
  const prompts = [
    {
      title: "Mild reminder before send",
      text: "We found personal data in this prompt. We masked it automatically. Please review the sanitized version before sending.",
    },
    {
      title: "Business-sensitive approval prompt",
      text: "This content appears to contain contract terms, pricing, product specifications, or customer information. Please confirm this is allowed for AI processing.",
    },
    {
      title: "Hard block message",
      text: "This request was blocked because it may expose source code, secrets, restricted content, or an attempt to bypass system policies.",
    },
    {
      title: "Audit notice after exception",
      text: `Sensitive sends confirmed by users are logged for audit. Current confirmed sends: ${dashboard.confirmed_sensitive_sends || 0}.`,
    },
  ];

  elements.promptPatternList.innerHTML = prompts.map((item) => `
    <article class="notice-card">
      <strong>${escapeHtml(item.title)}</strong>
      <p>${escapeHtml(item.text)}</p>
    </article>
  `).join("");
}

function renderUseCases(useCases) {
  if (!elements.useCaseStrip) {
    return;
  }
  elements.useCaseStrip.innerHTML = useCases.slice(0, 4).map((item) => `
    <article class="scenario-card">
      <div class="scenario-card-head">
        <strong>${escapeHtml(item.title)}</strong>
        <span class="scanner-badge ${item.blocked ? "scanner-badge-active" : ""}">${escapeHtml(item.total)} events</span>
      </div>
      <p>${escapeHtml(item.description)}</p>
      <div class="scenario-metrics">
        <span>Blocked ${escapeHtml(item.blocked)}</span>
        <span>Review ${escapeHtml(item.review_needed)}</span>
      </div>
    </article>
  `).join("");
}

function renderIncidents(incidents) {
  if (!incidents.length) {
    elements.incidentFeed.innerHTML = `<p class="empty-state">No recent incidents.</p>`;
    return;
  }

  elements.incidentFeed.innerHTML = incidents.slice(0, 5).map((incident) => `
    <article class="incident-item incident-${escapeHtml(incident.severity || "medium")}">
      <div class="incident-head">
        <strong>${escapeHtml(incident.title)}</strong>
        <span class="status-chip">${escapeHtml(incident.channel)} / ${escapeHtml(incident.status)}</span>
      </div>
      <p>${escapeHtml(incident.summary)}</p>
      <div class="incident-meta">
        <span>${escapeHtml(incident.actor)}</span>
        <span>${escapeHtml(formatDateTime(incident.created_at))}</span>
      </div>
    </article>
  `).join("");
}

function formatBusinessCategoryName(value) {
  const labels = {
    contract_terms: "Contract Terms",
    pricing: "Pricing",
    product_spec: "Product Specification",
    commercial_plan: "Commercial Plan",
    customer_data: "Customer Data",
    insurance_policy_terms: "Insurance Policy Terms",
    insurance_coverage: "Insurance Coverage",
    insurance_premium: "Insurance Premium",
    insurance_claims: "Insurance Claims",
    insurance_underwriting: "Insurance Underwriting",
    insurance_party_data: "Insurance Party Data",
    "business-sensitive": "Business Sensitive",
  };
  return labels[String(value || "")] || String(value || "");
}

function formatRiskLevel(value) {
  const labels = {
    low: "low",
    medium: "medium",
    high: "high",
  };
  return labels[String(value || "").toLowerCase()] || String(value || "");
}

async function confirmSanitizedSend() {
  if (!state.pendingPreview) {
    return;
  }
  const preview = state.pendingPreview;
  closeModal();
  await sendConfirmed(preview);
}

async function sendConfirmed(preview) {
  elements.statusText.textContent = "Waiting for model reply...";
  const response = await fetch("/api/chat/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: state.selectedSessionId,
      original_message: preview.original_message,
      sanitized_message: preview.sanitized_message,
      username: state.username,
      scan_event_id: preview.scan_event_id || null,
      enabled_scanners: preview.enabled_scanners || null,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    elements.statusText.textContent = error.detail || "Request failed.";
    elements.sendButton.disabled = false;
    await Promise.all([loadConsoleSummary(), loadLastScan(), loadDashboardSnapshot()]);
    return;
  }

  elements.messageInput.value = "";
  elements.statusText.textContent = "Message sent.";
  elements.sendButton.disabled = false;
  await Promise.all([loadSessions(), loadConsoleSummary(), loadLastScan(), loadDashboardSnapshot()]);
}

function renderEntityTable(target, entities) {
  target.innerHTML = "";
  if (!entities || !entities.length) {
    target.innerHTML = `<tr><td class="empty-cell" colspan="4">No entities detected.</td></tr>`;
    return;
  }

  entities.forEach((entity) => {
    const row = document.createElement("tr");
    const sources = formatEntitySources(entity.sources && entity.sources.length ? entity.sources : [entity.source]);
    row.innerHTML = `
      <td>${escapeHtml(entity.type)}</td>
      <td title="${escapeHtml(entity.original)}">${escapeHtml(entity.masked)}</td>
      <td>${escapeHtml(entity.replacement)}</td>
      <td>${escapeHtml(sources)}</td>
    `;
    target.appendChild(row);
  });
}

function formatEntitySources(sources) {
  const labels = {
    custom_regex: "Custom Regex",
    privacy_filter: "Privacy Filter",
    llm_guard: "LLM Guard",
    llm_guard_secrets: "LLM Guard Secrets",
  };
  return (sources || []).filter(Boolean).map((source) => labels[source] || source).join(", ");
}

function populateProviderSelect() {
  const currentProvider = elements.providerSelect.value || state.providers[0]?.provider || "openai";
  elements.providerSelect.innerHTML = "";
  state.providers.forEach((provider) => {
    const option = document.createElement("option");
    option.value = provider.provider;
    option.textContent = provider.display_name;
    elements.providerSelect.appendChild(option);
  });

  const nextProvider = state.providers.some((item) => item.provider === currentProvider)
    ? currentProvider
    : state.providers[0]?.provider;

  if (nextProvider) {
    elements.providerSelect.value = nextProvider;
    populateModelSelect(nextProvider);
    updateCredentialStatus(nextProvider);
    refreshProviderChip(nextProvider);
    renderGatewayPipeline(nextProvider);
  }
}

function populateModelSelect(providerName, preferredModel = null) {
  const provider = state.providers.find((item) => item.provider === providerName);
  const models = provider?.models?.length ? provider.models : [];
  elements.modelSelect.innerHTML = "";

  models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model;
    elements.modelSelect.appendChild(option);
  });

  if (!models.length) {
    const option = document.createElement("option");
    option.value = provider?.default_model || "";
    option.textContent = provider?.default_model || "No model configured";
    elements.modelSelect.appendChild(option);
  }

  const targetModel =
    preferredModel && [...elements.modelSelect.options].some((option) => option.value === preferredModel)
      ? preferredModel
      : (provider?.default_model || elements.modelSelect.options[0]?.value || "");
  elements.modelSelect.value = targetModel;
}

function updateCredentialStatus(providerName) {
  const provider = state.providers.find((item) => item.provider === providerName);
  elements.selectedProviderStatus.textContent = provider?.display_name || providerName;
  elements.selectedKeyStatus.textContent = provider?.requires_api_key === false
    ? `Local\n${provider.base_url || "http://localhost:11434"}`
    : provider?.configured
      ? `Configured\n${provider.masked_api_key}`
      : "Not configured";
  refreshProviderChip(providerName);
  renderGatewayPipeline(providerName);
  if (provider?.configured === false && provider?.requires_api_key !== false) {
    elements.statusText.textContent = `No saved API key for ${provider.display_name}. Open Manage Keys to configure it.`;
  }
}

function refreshProviderChip(providerName) {
  const provider = state.providers.find((item) => item.provider === providerName);
  const label = provider?.display_name || providerName || "openai";
  elements.providerChip.textContent = `Provider: ${label}`;
}

function renderGatewayPipeline(providerName = elements.providerSelect?.value) {
  if (!elements.gatewayPipeline) {
    return;
  }

  const provider = state.providers.find((item) => item.provider === providerName);
  const providerInfo = getProviderLogoInfo(provider?.provider || providerName, provider?.display_name);
  const stages = [
    { step: "1", label: "USER INPUT", title: "User Input", iconType: "user", meta: "Prompt" },
    { step: "2", label: "INPUT SCANNERS", title: "Input Scanners", iconType: "shield", meta: "PII / Code / Policy" },
    { step: "3", label: "AI PROVIDER", title: providerInfo.title, iconType: providerInfo.iconType, meta: providerInfo.meta, providerInfo },
    { step: "4", label: "OUTPUT SCANNERS", title: "Output Scanners", iconType: "search", meta: "Response Review" },
    { step: "5", label: "RESPONSE FILTERING", title: "Response Filtering", iconType: "filter", meta: "Policy Gate" },
    { step: "6", label: "RESPONSE", title: "Return User", iconType: "check", meta: "Allowed Output" },
  ];

  elements.gatewayPipeline.innerHTML = `
    <div class="gateway-pipeline-title">AI Data Security Gateway - Scanning Pipeline</div>
    <div class="gateway-pipeline-flow">
      ${stages.map((stage) => renderGatewayStage(stage)).join("")}
    </div>
  `;
}

function renderGatewayStage(stage) {
  return `
    <article class="gateway-stage">
      <div class="gateway-stage-copy">
        <span>${escapeHtml(stage.label)}</span>
        <strong>${escapeHtml(stage.title)}</strong>
        <em>${escapeHtml(stage.meta)}</em>
      </div>
    </article>
  `;
}

function getProviderLogoInfo(providerName, displayName) {
  const key = String(providerName || "").toLowerCase();
  const display = displayName || providerName || "OpenAI";
  if (key.includes("ollama")) {
    return { title: "Ollama", meta: "Local model", iconType: "ollama", className: "gateway-provider-ollama" };
  }
  if (key.includes("qwen") || key.includes("aliyun") || key.includes("dashscope")) {
    return { title: "阿里云百炼", meta: display, iconType: "aliyun", className: "gateway-provider-aliyun" };
  }
  return { title: "OpenAI", meta: display, iconType: "openai", className: "gateway-provider-openai" };
}

function bindSyncedScroll(left, right) {
  let syncing = false;

  const sync = (source, target) => {
    if (syncing) {
      return;
    }
    const maxSource = source.scrollHeight - source.clientHeight;
    const maxTarget = target.scrollHeight - target.clientHeight;
    if (maxSource <= 0 || maxTarget <= 0) {
      return;
    }
    syncing = true;
    target.scrollTop = (source.scrollTop / maxSource) * maxTarget;
    syncing = false;
  };

  left.addEventListener("scroll", () => sync(left, right));
  right.addEventListener("scroll", () => sync(right, left));
}

function formatDateTime(value) {
  if (!value) {
    return "recently";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "recently";
  }
  return date.toLocaleString();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
