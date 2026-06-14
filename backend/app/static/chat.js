const chatState = {
  providers: [],
  sessions: [],
  sessionId: null,
  pendingPreview: null,
  attachment: null,
  username: "Guest",
  scanners: [],
};

const DEFAULT_CHAT_PROVIDER = "qwen";
const DEFAULT_CHAT_MODEL = "deepseek-v4-pro";

const chatElements = {
  sessionTitle: document.getElementById("session-title"),
  sessionLabel: document.getElementById("session-label"),
  sessionList: document.getElementById("session-list"),
  providerSelect: document.getElementById("provider-select"),
  modelSelect: document.getElementById("model-select"),
  routePreviewText: document.getElementById("route-preview-text"),
  routeStatusPill: document.getElementById("route-status-pill"),
  usernameInput: document.getElementById("username-input"),
  newChatButton: document.getElementById("new-chat-btn"),
  refreshSessionsButton: document.getElementById("refresh-sessions-btn"),
  deleteChatButton: document.getElementById("delete-chat-btn"),
  themeToggleButton: document.getElementById("theme-toggle-btn"),
  messageList: document.getElementById("message-list"),
  chatForm: document.getElementById("chat-form"),
  sampleSelect: document.getElementById("sample-select"),
  attachmentInput: document.getElementById("attachment-input"),
  attachButton: document.getElementById("attach-btn"),
  attachmentTray: document.getElementById("attachment-tray"),
  messageInput: document.getElementById("message-input"),
  sendButton: document.getElementById("send-btn"),
  statusText: document.getElementById("status-text"),
  scannerStack: document.getElementById("scanner-stack"),
  reviewPanel: document.getElementById("review-panel"),
  reviewCard: document.querySelector(".review-card"),
  reviewHeader: document.querySelector(".review-header"),
  reviewKicker: document.getElementById("review-kicker"),
  reviewTitle: document.getElementById("review-title"),
  reviewFileAssessment: document.getElementById("review-file-assessment"),
  reviewMessageGrid: document.getElementById("review-message-grid"),
  reviewOriginal: document.getElementById("review-original"),
  reviewSanitized: document.getElementById("review-sanitized"),
  reviewOutputGrid: document.getElementById("review-output-grid"),
  reviewAssistantRawOutput: document.getElementById("review-assistant-raw-output"),
  reviewAssistantDisplayOutput: document.getElementById("review-assistant-display-output"),
  reviewDetails: document.getElementById("review-details"),
  reviewActions: document.getElementById("review-actions"),
  reviewCloseButton: document.getElementById("review-close-btn"),
  reviewBackButton: document.getElementById("review-back-btn"),
  reviewSendButton: document.getElementById("review-send-btn"),
};

document.addEventListener("DOMContentLoaded", async () => {
  applyStoredChatTheme();
  chatState.username = window.localStorage.getItem("chat_username") || "Guest";
  chatElements.usernameInput.value = chatState.username;
  bindChatEvents();
  await bootstrapChat();
});

function bindChatEvents() {
  chatElements.chatForm.addEventListener("submit", handleChatSubmit);
  chatElements.newChatButton.addEventListener("click", createStandaloneSession);
  chatElements.refreshSessionsButton.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    loadStandaloneSessions();
  });
  chatElements.deleteChatButton.addEventListener("click", deleteCurrentSession);
  chatElements.themeToggleButton.addEventListener("click", toggleChatTheme);
  chatElements.sampleSelect.addEventListener("change", fillSamplePrompt);
  chatElements.attachButton.addEventListener("click", () => chatElements.attachmentInput.click());
  chatElements.attachmentInput.addEventListener("change", handleAttachmentSelection);
  chatElements.providerSelect.addEventListener("change", handleProviderChange);
  chatElements.modelSelect.addEventListener("change", () => {
    updateRoutePreview();
    syncStandaloneSessionSettings();
  });
  chatElements.usernameInput.addEventListener("change", persistStandaloneUsername);
  chatElements.reviewCloseButton.addEventListener("click", closeReviewPanel);
  chatElements.reviewBackButton.addEventListener("click", closeReviewPanel);
  chatElements.reviewSendButton.addEventListener("click", confirmReviewedSend);
  bindDraggableReviewPanel();
  chatElements.messageInput.addEventListener("input", resizeComposer);
  chatElements.messageInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      chatElements.chatForm.requestSubmit();
    }
  });
}

function applyStoredChatTheme() {
  const theme = window.localStorage.getItem("chat_theme") || "light";
  document.body.classList.toggle("chat-night", theme === "night");
  updateThemeToggleLabel();
}

function toggleChatTheme() {
  const nextTheme = document.body.classList.contains("chat-night") ? "light" : "night";
  window.localStorage.setItem("chat_theme", nextTheme);
  document.body.classList.toggle("chat-night", nextTheme === "night");
  updateThemeToggleLabel();
}

function updateThemeToggleLabel() {
  if (!chatElements.themeToggleButton) {
    return;
  }
  const isNight = document.body.classList.contains("chat-night");
  chatElements.themeToggleButton.textContent = isNight ? "Light" : "Night";
  chatElements.themeToggleButton.setAttribute("aria-label", isNight ? "Switch to light mode" : "Switch to night mode");
  chatElements.themeToggleButton.title = isNight ? "Switch to light mode" : "Switch to night mode";
}

async function bootstrapChat() {
  setChatStatus("Loading chat...");
  await Promise.all([loadStandaloneProviders(), loadChatScannerStatuses()]);
  await loadOrCreateSession();
}

async function loadStandaloneProviders() {
  const response = await fetch("/api/providers");
  const data = await response.json();
  chatState.providers = data.providers || [];
  populateStandaloneProviders();
}

async function loadOrCreateSession() {
  const sessions = await loadStandaloneSessions();
  const preferredId = Number(window.localStorage.getItem("standalone_chat_session_id"));
  const session = sessions.find((item) => item.id === preferredId) || sessions[0];
  if (session) {
    await selectStandaloneSession(session.id);
    return;
  }
  await createStandaloneSession();
}

async function loadStandaloneSessions() {
  const response = await fetch("/api/sessions");
  chatState.sessions = await response.json();
  renderSessionList();
  return chatState.sessions;
}

function renderSessionList() {
  chatElements.sessionList.innerHTML = "";
  if (!chatState.sessions.length) {
    chatElements.sessionList.innerHTML = `<p class="empty-state">No conversations yet.</p>`;
    return;
  }

  chatState.sessions.forEach((session) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `session-item ${session.id === chatState.sessionId ? "active-session" : ""}`;
    button.innerHTML = `
      <span class="session-name">${escapeHtml(session.title)}</span>
      <span class="session-meta">${escapeHtml(session.created_by || "Guest")} - ${escapeHtml(formatProviderModel(session.provider, session.model))}</span>
      <span class="session-submeta">${escapeHtml(formatRelativeTime(session.updated_at))}</span>
    `;
    button.addEventListener("click", () => selectStandaloneSession(session.id));
    chatElements.sessionList.appendChild(button);
  });
}

async function createStandaloneSession() {
  closeReviewPanel();
  setChatStatus("Starting a new chat...");
  const response = await fetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: "",
      username: chatState.username,
      provider: chatElements.providerSelect.value,
      model: chatElements.modelSelect.value,
    }),
  });
  const session = await response.json();
  upsertSessionSummary(session);
  renderSessionList();
  await selectStandaloneSession(session.id);
}

async function selectStandaloneSession(sessionId) {
  closeReviewPanel();
  chatState.sessionId = sessionId;
  window.localStorage.setItem("standalone_chat_session_id", String(sessionId));
  const response = await fetch(`/api/sessions/${sessionId}`);
  const session = await response.json();
  chatElements.sessionTitle.textContent = session.title;
  chatElements.sessionLabel.textContent = formatProviderModel(session.provider, session.model);
  chatElements.providerSelect.value = session.provider;
  populateStandaloneModels(session.provider, session.model);
  updateRoutePreview();
  renderStandaloneMessages(session.messages || []);
  upsertSessionSummary(session);
  renderSessionList();
  chatElements.sendButton.disabled = false;
  chatElements.deleteChatButton.disabled = false;
  setChatStatus("Ready.");
}

function renderStandaloneMessages(messages) {
  chatElements.messageList.innerHTML = "";
  if (!messages.length) {
    chatElements.messageList.innerHTML = `
      <div class="welcome-state">
        <h2>
          <span>我可以帮你做什么？</span>
          <span>What can I help with?</span>
        </h2>
        <p>
          <span>你的提示词会在发送到模型前进行安全检查。敏感数据可能会被脱敏并要求确认，不安全请求会被拦截并显示原因。</span>
          <span>Before sending, each prompt is checked for sensitive data and policy risks. Sensitive details may be masked for review, while unsafe requests are blocked with a clear reason.</span>
        </p>
      </div>
    `;
    return;
  }

  messages.forEach((message) => {
    const content = message.role === "assistant"
      ? (message.sanitized_content || message.original_content || message.used_content || "")
      : (message.used_content || message.sanitized_content || message.original_content || "");
    appendMessage(message.role, content);
  });
}

async function handleChatSubmit(event) {
  event.preventDefault();
  const message = chatElements.messageInput.value.trim();
  if (!message || !chatState.sessionId) {
    return;
  }
  if (chatState.attachment?.status === "uploading" || chatState.attachment?.status === "processing") {
    setChatStatus("Attachment review is still running...");
    return;
  }
  if (isHighRiskAttachment(chatState.attachment?.record)) {
    openAttachmentReviewPanel(chatState.attachment.record);
    setChatStatus("Attachment blocked because it was classified as high-risk business-sensitive content.");
    return;
  }

  chatElements.sendButton.disabled = true;
  setChatStatus("Scanning prompt...");
  const displayMessage = buildDisplayMessageWithAttachment(message);
  const outboundMessage = buildOutboundMessageWithAttachment(message);
  appendMessage("user", displayMessage);

  const previewResponse = await fetch("/api/chat/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: chatState.sessionId,
      message: outboundMessage,
      username: chatState.username,
    }),
  });
  const preview = await previewResponse.json();

  if (preview.status === "blocked") {
    openBlockedReviewPanel(preview);
    clearComposerInput();
    setChatStatus("Blocked.");
    chatElements.sendButton.disabled = false;
    await loadStandaloneSessions();
    return;
  }

  if (preview.status === "needs_confirmation") {
    chatState.pendingPreview = preview;
    openReviewPanel(preview);
    setChatStatus(buildReviewStatus(preview));
    chatElements.sendButton.disabled = false;
    await loadStandaloneSessions();
    return;
  }

  await sendStandaloneConfirmed(preview);
}

async function sendStandaloneConfirmed(preview) {
  closeReviewPanel();
  setChatStatus("Waiting for model reply...");
  const response = await fetch("/api/chat/confirm", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: chatState.sessionId,
      original_message: preview.original_message,
      sanitized_message: preview.sanitized_message,
      username: chatState.username,
      scan_event_id: preview.scan_event_id || null,
      enabled_scanners: preview.enabled_scanners || null,
    }),
  });

  if (!response.ok) {
    const error = await response.json();
    appendMessage("blocked", error.detail || "Request failed.");
    setChatStatus("Request failed.");
    chatElements.sendButton.disabled = false;
    await loadStandaloneSessions();
    return;
  }

  const data = await response.json();
  const assistant = data.assistant_message || {};
  appendMessage("assistant", assistant.sanitized_content || assistant.original_content || assistant.used_content || "");
  if (hasDeanonymizedAssistantOutput(assistant)) {
    openReviewPanel(preview, { assistant, mode: "assistant_output" });
  }
  clearComposerInput();
  clearAttachment();
  chatElements.sessionTitle.textContent = data.session_title || chatElements.sessionTitle.textContent;
  await loadStandaloneSessions();
  setChatStatus("Ready.");
  chatElements.sendButton.disabled = false;
  if (!hasDeanonymizedAssistantOutput(assistant)) {
    chatElements.messageInput.focus();
  }
}

async function loadChatScannerStatuses() {
  const response = await fetch("/api/console/scanners");
  const data = await response.json();
  chatState.scanners = data.scanners || [];
  renderChatScannerStack();
}

function renderChatScannerStack() {
  if (!chatElements.scannerStack) {
    return;
  }
  chatElements.scannerStack.innerHTML = "";
  chatState.scanners
    .filter((scanner) => isInputScanner(scanner.id))
    .forEach((scanner) => {
      const label = document.createElement("label");
      label.className = `scanner-toggle ${scanner.enabled ? "" : "scanner-toggle-disabled"}`;
      label.title = scanner.detail || "";
      label.innerHTML = `
        <span class="scanner-toggle-main">
          <input type="checkbox" data-scanner-id="${escapeHtml(scanner.id)}" ${scanner.enabled ? "checked" : ""} />
          <span>${escapeHtml(formatScannerDisplayName(scanner))}</span>
        </span>
        <em>${escapeHtml(formatScannerState(scanner))}</em>
      `;
      label.querySelector("input")?.addEventListener("change", handleChatScannerToggle);
      chatElements.scannerStack.appendChild(label);
    });
  updateChatScannerStatus();
}

async function handleChatScannerToggle(event) {
  const scannerId = event.target.dataset.scannerId;
  const enabled = event.target.checked;
  const nextEnabled = new Set(
    chatState.scanners
      .filter((scanner) => isInputScanner(scanner.id) && scanner.enabled)
      .map((scanner) => scanner.id),
  );
  if (enabled) {
    nextEnabled.add(scannerId);
  } else {
    nextEnabled.delete(scannerId);
  }

  setChatStatus("Updating scanner selection...");
  const response = await fetch("/api/console/scanners", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled_scanners: [...nextEnabled] }),
  });
  if (!response.ok) {
    const error = await response.json();
    setChatStatus(error.detail || "Failed to update scanner selection.");
    await loadChatScannerStatuses();
    return;
  }
  const data = await response.json();
  chatState.scanners = data.scanners || [];
  renderChatScannerStack();
  setChatStatus(nextEnabled.size ? "Scanner selection updated." : "Scanning disabled.");
}

function updateChatScannerStatus() {
  const activeCount = chatState.scanners.filter((scanner) => isInputScanner(scanner.id) && scanner.active).length;
  if (!activeCount) {
    chatElements.scannerStack?.classList.add("scanner-stack-disabled");
    return;
  }
  chatElements.scannerStack?.classList.remove("scanner-stack-disabled");
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

function openReviewPanel(preview, options = {}) {
  resetReviewPanelPosition();
  const businessResult = preview.business_sensitive_result || {};
  const hasBusinessSensitive = Boolean(businessResult.contains_business_sensitive);
  const isAssistantOutputReview = options.mode === "assistant_output";
  chatElements.reviewKicker.textContent = isAssistantOutputReview
    ? "PII Deanonymized Output"
    : hasBusinessSensitive
      ? "Business Sensitive Review"
      : "Sensitive Data Detected";
  chatElements.reviewTitle.textContent = isAssistantOutputReview
    ? "Assistant output review"
    : hasBusinessSensitive
      ? "Review business-sensitive content"
      : "Review before sending";
  chatElements.reviewCloseButton.textContent = isAssistantOutputReview ? "Close" : "Back to edit";
  chatElements.reviewSendButton.textContent = preview.has_sensitive_data ? "Send sanitized version" : "Send anyway";
  chatElements.reviewMessageGrid.classList.remove("hidden");
  chatElements.reviewFileAssessment.classList.add("hidden");
  chatElements.reviewFileAssessment.innerHTML = "";
  chatElements.reviewOriginal.textContent = preview.original_message;
  chatElements.reviewSanitized.textContent = preview.sanitized_message;
  renderAssistantOutputReview(options.assistant);
  renderReviewDetails(preview);
  chatElements.reviewActions.classList.toggle("hidden", isAssistantOutputReview);
  chatElements.reviewPanel.classList.remove("hidden");
  chatElements.reviewPanel.setAttribute("aria-hidden", "false");
}

function openBlockedReviewPanel(preview) {
  resetReviewPanelPosition();
  const businessResult = preview.business_sensitive_result || {};
  const hasBusinessSensitive = Boolean(businessResult.contains_business_sensitive);
  chatElements.reviewKicker.textContent = hasBusinessSensitive ? "Business Sensitive" : "Blocked";
  chatElements.reviewTitle.textContent = hasBusinessSensitive
    ? "Review business-sensitive content before sending"
    : "Prompt blocked before sending";
  chatElements.reviewCloseButton.textContent = "Close";
  chatElements.reviewMessageGrid.classList.add("hidden");
  chatElements.reviewOutputGrid.classList.add("hidden");
  chatElements.reviewActions.classList.add("hidden");
  chatElements.reviewDetails.innerHTML = "";
  chatElements.reviewFileAssessment.classList.remove("hidden");
  chatElements.reviewFileAssessment.innerHTML = hasBusinessSensitive
    ? renderPromptBusinessSensitiveAssessment(preview)
    : renderGenericBlockedAssessment(preview);
  chatElements.reviewPanel.classList.remove("hidden");
  chatElements.reviewPanel.setAttribute("aria-hidden", "false");
}

function closeReviewPanel() {
  chatState.pendingPreview = null;
  chatElements.reviewPanel.classList.add("hidden");
  chatElements.reviewPanel.setAttribute("aria-hidden", "true");
}

function bindDraggableReviewPanel() {
  let dragging = false;
  let startX = 0;
  let startY = 0;
  let originX = 0;
  let originY = 0;

  chatElements.reviewHeader.addEventListener("pointerdown", (event) => {
    if (event.target.closest("button")) {
      return;
    }
    dragging = true;
    startX = event.clientX;
    startY = event.clientY;
    originX = Number(chatElements.reviewCard.dataset.dragX || 0);
    originY = Number(chatElements.reviewCard.dataset.dragY || 0);
    chatElements.reviewCard.classList.add("review-card-dragging");
    chatElements.reviewHeader.setPointerCapture(event.pointerId);
  });

  chatElements.reviewHeader.addEventListener("pointermove", (event) => {
    if (!dragging) {
      return;
    }
    const nextX = originX + event.clientX - startX;
    const nextY = originY + event.clientY - startY;
    setReviewPanelPosition(nextX, nextY);
  });

  chatElements.reviewHeader.addEventListener("pointerup", (event) => {
    if (!dragging) {
      return;
    }
    dragging = false;
    chatElements.reviewCard.classList.remove("review-card-dragging");
    chatElements.reviewHeader.releasePointerCapture(event.pointerId);
  });
}

function setReviewPanelPosition(x, y) {
  chatElements.reviewCard.dataset.dragX = String(x);
  chatElements.reviewCard.dataset.dragY = String(y);
  chatElements.reviewCard.style.setProperty("--review-drag-x", `${x}px`);
  chatElements.reviewCard.style.setProperty("--review-drag-y", `${y}px`);
}

function resetReviewPanelPosition() {
  setReviewPanelPosition(0, 0);
}

function renderAssistantOutputReview(assistant) {
  const hasOutput = Boolean(assistant);
  chatElements.reviewOutputGrid.classList.toggle("hidden", !hasOutput);
  chatElements.reviewAssistantRawOutput.textContent = hasOutput
    ? (assistant.original_content || assistant.used_content || "-")
    : "-";
  chatElements.reviewAssistantDisplayOutput.textContent = hasOutput
    ? (assistant.sanitized_content || assistant.original_content || assistant.used_content || "-")
    : "-";
}

function hasDeanonymizedAssistantOutput(assistant) {
  const rawOutput = (assistant?.original_content || assistant?.used_content || "").trim();
  const displayOutput = (assistant?.sanitized_content || "").trim();
  return Boolean(rawOutput && displayOutput && rawOutput !== displayOutput);
}

async function confirmReviewedSend() {
  if (!chatState.pendingPreview) {
    return;
  }
  const preview = chatState.pendingPreview;
  await sendStandaloneConfirmed(preview);
}

function renderReviewDetails(preview) {
  const businessResult = preview.business_sensitive_result || {};
  if (businessResult.contains_business_sensitive) {
    chatElements.reviewDetails.innerHTML = renderBusinessSensitiveReviewDetails(businessResult);
    return;
  }

  const entities = preview.detected_entities || [];
  chatElements.reviewDetails.innerHTML = entities.length
    ? renderPrivacyEntityTable(entities)
    : "No personal identifiers were returned, but this prompt still needs review.";
}

function renderBusinessSensitiveReviewDetails(businessResult) {
  const summary = businessResult.summary
    ? `<p class="review-detail-summary">${escapeHtml(businessResult.summary)}</p>`
    : "";
  return `
    <div class="review-detail-risk">Risk: ${escapeHtml(businessResult.risk_level || "unknown")}</div>
    ${summary}
  `;
}

function renderPrivacyEntityTable(entities) {
  const rows = entities.map((entity) => {
    const sources = formatEntitySources(entity.sources && entity.sources.length ? entity.sources : [entity.source]);
    return `
      <tr>
        <td>${escapeHtml(entity.type)}</td>
        <td title="${escapeHtml(entity.original || "")}">${escapeHtml(entity.masked || "")}</td>
        <td>${escapeHtml(entity.replacement || "")}</td>
        <td>${escapeHtml(sources || "-")}</td>
      </tr>
    `;
  }).join("");

  return `
    <div class="review-entity-table-wrap">
      <strong class="review-entity-title">Detected Entities</strong>
      <table class="review-entity-table">
        <thead>
          <tr>
            <th>TYPE</th>
            <th>MASKED VALUE</th>
            <th>REPLACEMENT</th>
            <th>SOURCES</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
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

async function handleAttachmentSelection() {
  const file = chatElements.attachmentInput.files?.[0];
  chatElements.attachmentInput.value = "";
  if (!file) {
    return;
  }

  chatState.attachment = {
    file,
    status: "uploading",
    name: file.name,
    size: file.size,
    record: null,
    announced: false,
  };
  renderAttachmentTray();
  setChatStatus("Uploading attachment for review...");
  chatElements.sendButton.disabled = true;

  const formData = new FormData();
  formData.append("file", file);
  formData.append("username", chatState.username || "Guest");

  const response = await fetch("/api/file-review/files/upload", {
    method: "POST",
    body: formData,
  });
  const body = await response.json();
  if (!response.ok) {
    chatState.attachment.status = "failed";
    chatState.attachment.error = body.detail || "Upload failed.";
    renderAttachmentTray();
    setChatStatus(chatState.attachment.error);
    chatElements.sendButton.disabled = false;
    return;
  }

  chatState.attachment.record = body;
  chatState.attachment.status = body.status || "processing";
  renderAttachmentTray();
  await pollAttachmentUntilFinished(body.id);
}

async function pollAttachmentUntilFinished(fileId) {
  const maxAttempts = 120;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const response = await fetch(`/api/file-review/files/${fileId}`);
    const file = await response.json();
    if (!chatState.attachment || chatState.attachment.record?.id !== fileId) {
      return;
    }
    chatState.attachment.record = file;
    chatState.attachment.status = file.status;
    renderAttachmentTray();

    if (file.status === "completed") {
      const isHighRisk = isHighRiskAttachment(file);
      setChatStatus(isHighRisk
        ? "Attachment blocked because it was classified as high-risk business-sensitive content."
        : "Attachment review completed.");
      openAttachmentReviewPanel(file);
      chatElements.sendButton.disabled = isHighRisk;
      return;
    }
    if (file.status === "failed") {
      chatState.attachment.error = file.error_message || "Attachment review failed.";
      setChatStatus(chatState.attachment.error);
      chatElements.sendButton.disabled = false;
      return;
    }
    setChatStatus("Attachment review in progress...");
    await wait(2000);
  }
  setChatStatus("Attachment review is still running. You can remove it or wait a little longer.");
  chatElements.sendButton.disabled = false;
}

function renderAttachmentTray() {
  const attachment = chatState.attachment;
  if (!attachment) {
    chatElements.attachmentTray.classList.add("hidden");
    chatElements.attachmentTray.innerHTML = "";
    return;
  }

  const record = attachment.record || {};
  const review = record.review_result || {};
  const status = attachment.error
    ? attachment.error
    : `${formatAttachmentStatus(attachment.status)}${review.risk_level ? ` / Risk: ${formatRisk(review.risk_level)}` : ""}`;
  chatElements.attachmentTray.classList.remove("hidden");
  chatElements.attachmentTray.innerHTML = `
    <div class="attachment-card">
      <div class="attachment-main">
        <span class="attachment-name">${escapeHtml(attachment.name || record.original_filename || "Attachment")}</span>
        <span class="attachment-meta">${escapeHtml(formatBytes(attachment.size || record.size_bytes || 0))} - ${escapeHtml(status)}</span>
      </div>
      <button class="attachment-remove" type="button">Remove</button>
    </div>
  `;
  chatElements.attachmentTray.querySelector(".attachment-remove")?.addEventListener("click", clearAttachment);
}

function openAttachmentReviewPanel(file) {
  const review = file.review_result || {};
  const isHighRisk = isHighRiskAttachment(file);
  chatElements.reviewKicker.textContent = "Business Sensitive";
  chatElements.reviewTitle.textContent = isHighRisk
    ? "Review business-sensitive content before sending"
    : "Business-sensitive file assessment";
  chatElements.reviewCloseButton.textContent = "Close";
  chatElements.reviewMessageGrid.classList.add("hidden");
  chatElements.reviewOutputGrid.classList.add("hidden");
  chatElements.reviewActions.classList.add("hidden");
  chatElements.reviewDetails.innerHTML = "";
  chatElements.reviewFileAssessment.classList.remove("hidden");
  chatElements.reviewFileAssessment.innerHTML = renderAttachmentAssessment(file, isHighRisk);
  chatElements.reviewPanel.classList.remove("hidden");
  chatElements.reviewPanel.setAttribute("aria-hidden", "false");
}

function renderAttachmentAssessment(file, isHighRisk) {
  const review = file.review_result || {};
  const hits = review.hits || [];
  const categories = review.categories || [];
  const fileSummary = buildAttachmentSummary(file);
  const reasonItems = buildAttachmentReasonItems(file, hits, categories);
  const hitMarkup = reasonItems.length
    ? reasonItems.map((item) => `
      <article class="file-assessment-hit">
        <strong>${escapeHtml(item.title)}</strong>
        <p>${escapeHtml(item.reason)}</p>
        ${item.location ? `<span>Location: ${escapeHtml(item.location)}</span>` : ""}
      </article>
    `).join("")
    : `<p class="file-assessment-muted">No high-risk business-sensitive evidence was returned for this file.</p>`;
  const categoryMarkup = categories.length
    ? `<div class="file-assessment-tags">${categories.map((item) => `<span>${escapeHtml(formatCategoryName(item))}</span>`).join("")}</div>`
    : "";
  const blockReason = isHighRisk
    ? "Blocked reason: this attachment contains high-risk business-sensitive content and cannot be sent to the model as chat context."
    : "Result: this attachment was reviewed and can be used as chat context according to policy.";
  return `
    <section class="file-assessment-card">
      <div class="file-assessment-head">
        <div>
          <strong>Business Sensitive Assessment</strong>
          <span>File: ${escapeHtml(file.original_filename || "Attachment")}</span>
          <span>${escapeHtml(String(file.file_type || "file").toUpperCase())} / ${escapeHtml(String(file.status || "completed").toUpperCase())}</span>
        </div>
        <span class="file-risk-pill file-risk-${escapeHtml(String(review.risk_level || "low").toLowerCase())}">
          Risk: ${escapeHtml(formatRisk(review.risk_level || "low"))}
        </span>
      </div>
      <p class="file-assessment-muted">${escapeHtml(fileSummary)}</p>
      ${categoryMarkup}
      <div class="file-block-reason ${isHighRisk ? "file-block-reason-high" : ""}">${escapeHtml(blockReason)}</div>
      <div class="file-assessment-hits">${hitMarkup}</div>
    </section>
  `;
}

function buildAttachmentReasonItems(file, hits, categories) {
  const items = [];
  const seen = new Set();
  (hits || []).forEach((hit) => {
    const category = hit.category || "business_sensitive";
    const key = `${category}:${hit.location || ""}:${hit.reason || ""}`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    items.push({
      title: formatCategoryName(category),
      reason: formatSensitiveReason(category, hit.reason),
      location: hit.location || "",
    });
  });
  (categories || []).forEach((category) => {
    const key = `${category}:category`;
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    items.push({
      title: formatCategoryName(category),
      reason: formatSensitiveReason(category, ""),
      location: "",
    });
  });
  return items;
}

function buildAttachmentSummary(file) {
  const review = file?.review_result || {};
  const summary = String(review.summary || "").trim();
  if (summary && summary !== "No business-sensitive content detected.") {
    return summary;
  }
  const categories = review.categories || [];
  if (categories.length) {
    const labels = categories.map((item) => formatCategoryName(item)).join(", ");
    return `This file contains information related to ${labels}.`;
  }
  const fileType = String(file?.file_type || "file").toUpperCase();
  const extraction = String(file?.extraction_summary || "").trim();
  const scope = extraction ? ` The scanner reviewed ${extraction}.` : "";
  return `This ${fileType} file was reviewed by the local business-sensitive scanner. No high-risk business-sensitive content was detected.${scope}`;
}

function inferAttachmentReasonItems(file) {
  const review = file?.review_result || {};
  const haystack = [
    file?.original_filename,
    file?.extracted_text,
    file?.extraction_summary,
    review.summary,
  ].filter(Boolean).join("\n");
  const checks = [
    {
      category: "insurance_policy_terms",
      pattern: /(保单|保险单|电子保单|合同编号|合同号|保单号|policy|contract|C\d{6,18})/i,
      location: "filename / extracted text",
    },
    {
      category: "insurance_party_data",
      pattern: /(投保人|被保险人|参保人|受益人|姓名|身份证|证件号|年龄|出生日期|联系电话|phone|id number|name|age)/i,
      location: "extracted text",
    },
    {
      category: "insurance_premium",
      pattern: /(保险金额|保额|保费|保险费|费率|缴费|赔付金额|金额|premium|sum insured|insured amount)/i,
      location: "extracted text",
    },
    {
      category: "insurance_coverage",
      pattern: /(保险责任|保障范围|责任限额|免赔额|赔付比例|保险期间|承保区域|coverage|liability limit)/i,
      location: "extracted text",
    },
    {
      category: "insurance_claims",
      pattern: /(理赔|出险|赔案|赔付|拒赔|claim)/i,
      location: "extracted text",
    },
    {
      category: "insurance_underwriting",
      pattern: /(核保|承保|风险评级|除外责任|加费|underwriting)/i,
      location: "extracted text",
    },
  ];
  return checks.filter((item) => item.pattern.test(haystack));
}

function formatSensitiveReason(category, fallbackReason) {
  if (fallbackReason) {
    return fallbackReason;
  }
  const labels = {
    insurance_policy_terms: "涉及合同编号、保单号、特别约定、责任免除或续保/退保等保险合同条款。",
    insurance_coverage: "涉及保障范围、保险责任、保额、免赔额、赔付比例或保险期间。",
    insurance_premium: "涉及保险金额、保费、费率、折扣、缴费方式或佣金/手续费。",
    insurance_claims: "涉及理赔条件、出险信息、赔案号、赔付金额、拒赔原因或赔付记录。",
    insurance_underwriting: "涉及核保结论、风险评级、承保限制、加费或除外责任。",
    insurance_party_data: "涉及个人信息或保险合同相关方信息，如参保人/被保险人姓名、身份证号、年龄、受益人或联系人。",
    contract_terms: "涉及合同条款、付款条件、违约责任或交付条件。",
    pricing: "涉及价格、报价、折扣、成本、预算或金额信息。",
    product_spec: "涉及内部产品编号、规格、未公开参数或技术配置。",
    commercial_plan: "涉及投标方案、销售策略、客户拓展计划或内部商务决策。",
    customer_data: "涉及客户名单、商务联系人、采购意向或企业客户信息。",
  };
  const key = String(category || "").toLowerCase();
  return labels[key] || fallbackReason || "涉及商务敏感类型，需拦截后人工确认。";
}

function formatSensitiveReason(category, fallbackReason) {
  if (fallbackReason) {
    return fallbackReason;
  }
  const labels = {
    insurance_policy_terms: "涉及合同编号、保单号、特别约定、责任免除或续保/退保等保险合同条款。",
    insurance_coverage: "涉及保障范围、保险责任、保额、免赔额、赔付比例或保险期间。",
    insurance_premium: "涉及保险金额、保费、费率、折扣、缴费方式或佣金/手续费。",
    insurance_claims: "涉及理赔条件、出险信息、赔案号、赔付金额、拒赔原因或赔付记录。",
    insurance_underwriting: "涉及核保结论、风险评级、承保限制、加费或除外责任。",
    insurance_party_data: "涉及个人信息或保险合同相关方信息，如参保人/被保险人姓名、身份证号、年龄、受益人或联系人。",
    contract_terms: "涉及合同条款、付款条件、违约责任或交付条件。",
    pricing: "涉及价格、报价、折扣、成本、预算或金额信息。",
    product_spec: "涉及内部产品编号、规格、未公开参数或技术配置。",
    commercial_plan: "涉及投标方案、销售策略、客户拓展计划或内部商务决策。",
    customer_data: "涉及客户名单、商务联系人、采购意向或企业客户信息。",
  };
  const key = String(category || "").toLowerCase();
  return labels[key] || fallbackReason || "涉及商务敏感类型，需拦截后人工确认。";
}

function renderPromptBusinessSensitiveAssessment(preview) {
  const businessResult = preview.business_sensitive_result || {};
  const categories = businessResult.categories || [];
  const riskLevel = businessResult.risk_level || "high";
  const summary = businessResult.summary || "文本中包含可能的商务敏感信息。";
  const categoryMarkup = categories.length
    ? `<div class="file-assessment-tags">${categories.map((item) => `<span>${escapeHtml(formatCategoryName(item.name))}</span>`).join("")}</div>`
    : "";
  const hitMarkup = categories.length
    ? categories.map((category) => `
      <article class="file-assessment-hit">
        <strong>${escapeHtml(formatCategoryName(category.name || "Business Sensitive"))}</strong>
        <p>${escapeHtml(formatSensitiveReason(category.name, category.reason))}</p>
      </article>
    `).join("")
    : `<p class="file-assessment-muted">未返回具体分类命中，但该内容已被归类为商务敏感。 / No detailed category hits were returned, but this content was classified as business-sensitive.</p>`;
  const blockReason = String(riskLevel).toLowerCase() === "high"
    ? "拦截理由：该内容被归类为 High 高风险商务敏感内容，因此不能发送给模型。 / Blocked reason: this prompt was classified as High-risk business-sensitive content, so it cannot be sent to the model."
    : (preview.blocked_reason || "该内容已被安全策略拦截。 / This prompt was blocked by policy.");
  return `
    <section class="file-assessment-card">
      <div class="file-assessment-head">
        <div>
          <strong>Business Sensitive Assessment</strong>
          <span>检测对象 / Target: Prompt</span>
        </div>
        <span class="file-risk-pill file-risk-${escapeHtml(String(riskLevel).toLowerCase())}">
          风险 / Risk: ${escapeHtml(formatRisk(riskLevel))}
        </span>
      </div>
      <p>${escapeHtml(summary)}</p>
      ${categoryMarkup}
      <div class="file-block-reason file-block-reason-high">${escapeHtml(blockReason)}</div>
      <div class="file-assessment-hits">${hitMarkup}</div>
    </section>
  `;
}

function renderGenericBlockedAssessment(preview) {
  const reason = preview.blocked_reason || "Prompt blocked by policy.";
  const scannerTitle = formatBlockedScannerAssessmentTitle(preview.scanners);
  return `
    <section class="file-assessment-card">
      <div class="file-assessment-head">
        <div>
          <strong>${escapeHtml(scannerTitle)}</strong>
          <span>检测对象 / Target: Prompt</span>
        </div>
        <span class="file-risk-pill file-risk-high">Blocked</span>
      </div>
      <div class="file-block-reason file-block-reason-high">${escapeHtml(reason)}</div>
    </section>
  `;
}

function formatBlockedScannerAssessmentTitle(scanners = []) {
  const labels = {
    BanCode: "BanCode Scanner",
    PromptInjection: "Prompt Injection Scanner",
    BanTopics: "Ban Topics Scanner",
    "Business Sensitive": "Business Sensitive Scanner",
    "Privacy Filter": "Privacy Information Scanner",
    "Custom Regex": "Custom Rule Scanner",
  };
  const scannerNames = (Array.isArray(scanners) ? scanners : [])
    .filter(Boolean)
    .map((scanner) => labels[scanner] || `${scanner} Scanner`);
  return scannerNames.length ? scannerNames.join(", ") : "Blocked Scanner";
}

function isHighRiskAttachment(file) {
  return String(file?.review_result?.risk_level || "").toLowerCase() === "high";
}

function formatCategoryName(value) {
  const labels = {
    contract_terms: "合同条款 / Contract Terms",
    pricing: "价格信息 / Pricing",
    product_spec: "产品规格 / Product Specification",
    product_specification: "产品规格 / Product Specification",
    commercial_plan: "商业计划 / Commercial Plan",
    customer_data: "客户数据 / Customer Data",
    business_plan: "商业计划 / Business Plan",
    strategy: "战略规划 / Strategy",
    procurement: "采购信息 / Procurement",
    insurance_policy_terms: "Insurance Policy Terms",
    insurance_coverage: "Insurance Coverage",
    insurance_premium: "Insurance Premium",
    insurance_claims: "Insurance Claims",
    insurance_underwriting: "Insurance Underwriting",
    insurance_party_data: "Insurance Party Data",
  };
  const key = String(value || "").toLowerCase();
  return labels[key] || String(value || "")
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function clearAttachment() {
  chatState.attachment = null;
  renderAttachmentTray();
  if (chatState.sessionId) {
    chatElements.sendButton.disabled = false;
  }
}

function buildDisplayMessageWithAttachment(message) {
  const attachment = chatState.attachment;
  if (!attachment?.record || attachment.status !== "completed") {
    return message;
  }
  if (isHighRiskAttachment(attachment.record)) {
    return message;
  }
  return `${message}\n\n[Attachment: ${attachment.record.original_filename}]`;
}

function buildOutboundMessageWithAttachment(message) {
  const attachment = chatState.attachment;
  if (!attachment?.record || attachment.status !== "completed") {
    return message;
  }
  if (isHighRiskAttachment(attachment.record)) {
    openAttachmentReviewPanel(attachment.record);
    setChatStatus("Attachment blocked because it was classified as high-risk business-sensitive content.");
    return message;
  }
  const extractedText = (attachment.record.extracted_text || "").trim();
  const summary = (attachment.record.extraction_summary || "").trim();
  const reviewSummary = (attachment.record.review_result?.summary || "").trim();
  const contextParts = [
    `Attached file: ${attachment.record.original_filename}`,
    summary ? `Extraction summary: ${summary}` : "",
    reviewSummary ? `File review summary: ${reviewSummary}` : "",
    extractedText ? `Extracted text:\n${truncateText(extractedText, 8000)}` : "",
  ].filter(Boolean);
  return `${message}\n\n[Attachment context]\n${contextParts.join("\n\n")}`;
}

function appendMessage(role, text) {
  const welcome = chatElements.messageList.querySelector(".welcome-state");
  if (welcome) {
    chatElements.messageList.innerHTML = "";
  }
  const row = document.createElement("div");
  row.className = role === "blocked"
    ? "message-row message-row-system message-row-blocked"
    : `message-row message-row-${role}`;
  const bubble = document.createElement("div");
  bubble.className = "message-bubble";
  bubble.textContent = text;
  row.appendChild(bubble);
  chatElements.messageList.appendChild(row);
  chatElements.messageList.scrollTop = chatElements.messageList.scrollHeight;
}

function populateStandaloneProviders() {
  const currentProvider = chatElements.providerSelect.value || DEFAULT_CHAT_PROVIDER;
  chatElements.providerSelect.innerHTML = "";
  chatState.providers.forEach((provider) => {
    const option = document.createElement("option");
    option.value = provider.provider;
    option.textContent = provider.display_name || provider.provider;
    chatElements.providerSelect.appendChild(option);
  });
  const nextProvider = chatState.providers.some((item) => item.provider === currentProvider)
    ? currentProvider
    : chatState.providers[0]?.provider;
  if (nextProvider) {
    chatElements.providerSelect.value = nextProvider;
    populateStandaloneModels(nextProvider);
    updateRoutePreview();
  }
}

function populateStandaloneModels(providerName, preferredModel = null) {
  const provider = chatState.providers.find((item) => item.provider === providerName);
  const models = provider?.models?.length ? provider.models : [provider?.default_model || ""];
  chatElements.modelSelect.innerHTML = "";
  models.forEach((model) => {
    const option = document.createElement("option");
    option.value = model;
    option.textContent = model || "No model configured";
    chatElements.modelSelect.appendChild(option);
  });
  const target = preferredModel && models.includes(preferredModel)
    ? preferredModel
    : (providerName === DEFAULT_CHAT_PROVIDER && models.includes(DEFAULT_CHAT_MODEL))
    ? DEFAULT_CHAT_MODEL
    : (provider?.default_model || models[0] || "");
  chatElements.modelSelect.value = target;
  updateRoutePreview();
}

async function handleProviderChange() {
  populateStandaloneModels(chatElements.providerSelect.value);
  updateRoutePreview();
  await syncStandaloneSessionSettings();
}

async function syncStandaloneSessionSettings() {
  if (!chatState.sessionId) {
    return;
  }
  const response = await fetch(`/api/sessions/${chatState.sessionId}/settings`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      provider: chatElements.providerSelect.value,
      model: chatElements.modelSelect.value,
    }),
  });
  if (!response.ok) {
    const error = await response.json();
    setChatStatus(error.detail || "Failed to update settings.");
    return;
  }
  const session = await response.json();
  upsertSessionSummary(session);
  renderSessionList();
  chatElements.sessionLabel.textContent = formatProviderModel(session.provider, session.model);
  setChatStatus("Settings updated.");
  updateRoutePreview();
}

function persistStandaloneUsername() {
  const normalized = chatElements.usernameInput.value.trim() || "Guest";
  chatState.username = normalized;
  chatElements.usernameInput.value = normalized;
  window.localStorage.setItem("chat_username", normalized);
  setChatStatus(`User set to ${normalized}.`);
}

function fillSamplePrompt(event) {
  const select = event.target;
  const selectedOption = select.selectedOptions?.[0];
  if (!select.value) {
    return;
  }
  chatElements.messageInput.value = select.value;
  resizeComposer();
  chatElements.messageInput.focus();
  setChatStatus(`${selectedOption?.textContent?.trim() || "Demo"} sample loaded.`);
  select.value = "";
}

function clearComposerInput() {
  chatElements.messageInput.value = "";
  resizeComposer();
}

async function deleteCurrentSession() {
  if (!chatState.sessionId) {
    return;
  }
  const current = chatState.sessions.find((session) => session.id === chatState.sessionId);
  if (!window.confirm(`Delete "${current?.title || "this chat"}"?`)) {
    return;
  }

  await fetch(`/api/sessions/${chatState.sessionId}`, { method: "DELETE" });
  window.localStorage.removeItem("standalone_chat_session_id");
  chatState.sessionId = null;
  chatElements.sendButton.disabled = true;
  chatElements.deleteChatButton.disabled = true;

  const sessions = await loadStandaloneSessions();
  if (sessions.length) {
    await selectStandaloneSession(sessions[0].id);
    return;
  }

  chatElements.sessionTitle.textContent = "AI Chat";
  chatElements.sessionLabel.textContent = "No conversation selected";
  renderStandaloneMessages([]);
  setChatStatus("Create a new chat to continue.");
}

function upsertSessionSummary(session) {
  const summary = {
    id: session.id,
    title: session.title,
    created_by: session.created_by,
    provider: session.provider,
    model: session.model,
    created_at: session.created_at,
    updated_at: session.updated_at,
  };
  chatState.sessions = [
    summary,
    ...chatState.sessions.filter((item) => item.id !== session.id),
  ].sort((left, right) => new Date(right.updated_at || 0) - new Date(left.updated_at || 0));
}

function buildReviewStatus(preview) {
  const businessResult = preview.business_sensitive_result || {};
  if (businessResult.contains_business_sensitive) {
    return `Review required. Risk: ${businessResult.risk_level || "unknown"}.`;
  }
  return "Review required. Sensitive values were masked.";
}

function formatProviderModel(provider, model) {
  const label = chatState.providers.find((item) => item.provider === provider)?.display_name || provider;
  return `${label} / ${model}`;
}

function updateRoutePreview() {
  const providerName = chatElements.providerSelect.value;
  const modelName = chatElements.modelSelect.value;
  const provider = chatState.providers.find((item) => item.provider === providerName);
  const providerLabel = provider?.display_name || providerName || "Provider";
  chatElements.routePreviewText.textContent = `${providerLabel} -> ${modelName || "No model selected"}`;
  chatElements.routeStatusPill.textContent = provider?.configured === false && provider?.requires_api_key !== false
    ? "Needs key"
    : "Active";
}

function formatRelativeTime(value) {
  if (!value) {
    return "just now";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "recently";
  }

  const diffMinutes = Math.max(0, Math.round((Date.now() - date.getTime()) / 60000));
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

function formatAttachmentStatus(value) {
  const labels = {
    uploading: "Uploading",
    processing: "Reviewing",
    completed: "Reviewed",
    failed: "Failed",
  };
  return labels[String(value || "").toLowerCase()] || "Attached";
}

function formatRisk(value) {
  const labels = {
    low: "Low",
    medium: "Medium",
    high: "High",
  };
  return labels[String(value || "").toLowerCase()] || String(value || "-");
}

function formatBytes(value) {
  const bytes = Number(value || 0);
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function truncateText(value, maxLength) {
  const text = String(value || "");
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}\n[Attachment text truncated for chat context.]`;
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function setChatStatus(text) {
  chatElements.statusText.textContent = text;
}

function resizeComposer() {
  const input = chatElements.messageInput;
  input.style.height = "auto";
  input.style.height = `${Math.min(input.scrollHeight, 180)}px`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
