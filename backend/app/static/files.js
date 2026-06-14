const state = {
  files: [],
  selectedFileId: null,
};

const elements = {
  storageForm: document.getElementById("storage-form"),
  storagePathInput: document.getElementById("storage-path-input"),
  storageStatus: document.getElementById("storage-status"),
  uploadForm: document.getElementById("upload-form"),
  uploadFileInput: document.getElementById("upload-file-input"),
  uploadUsernameInput: document.getElementById("upload-username-input"),
  uploadStatus: document.getElementById("upload-status"),
  fileList: document.getElementById("file-list"),
  fileDetailTitle: document.getElementById("file-detail-title"),
  detailStatus: document.getElementById("detail-status"),
  detailRisk: document.getElementById("detail-risk"),
  detailCategories: document.getElementById("detail-categories"),
  detailSummary: document.getElementById("detail-summary"),
  detailPath: document.getElementById("detail-path"),
  detailSize: document.getElementById("detail-size"),
  detailUser: document.getElementById("detail-user"),
  detailError: document.getElementById("detail-error"),
  detailExtractionSummary: document.getElementById("detail-extraction-summary"),
  detailExtractedText: document.getElementById("detail-extracted-text"),
  fileHitTableBody: document.getElementById("file-hit-table-body"),
};

document.addEventListener("DOMContentLoaded", async () => {
  elements.uploadUsernameInput.value = window.localStorage.getItem("chat_username") || "Guest";
  bindEvents();
  await bootstrap();
});

function bindEvents() {
  elements.storageForm.addEventListener("submit", saveStoragePath);
  elements.uploadForm.addEventListener("submit", uploadFile);
}

async function bootstrap() {
  await Promise.all([loadSettings(), loadFiles()]);
}

async function loadSettings() {
  const response = await fetch("/api/file-review/settings");
  const settings = await response.json();
  elements.storagePathInput.value = settings.default_storage_path;
  elements.storageStatus.textContent = `Current default path loaded. Upload limit: ${settings.max_upload_mb}MB.`;
}

async function saveStoragePath(event) {
  event.preventDefault();
  elements.storageStatus.textContent = "Saving storage path...";
  const response = await fetch("/api/file-review/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ default_storage_path: elements.storagePathInput.value.trim() }),
  });
  const body = await response.json();
  if (!response.ok) {
    elements.storageStatus.textContent = body.detail || "Failed to update storage path.";
    return;
  }
  elements.storagePathInput.value = body.default_storage_path;
  elements.storageStatus.textContent = "Storage path updated.";
}

async function loadFiles() {
  const response = await fetch("/api/file-review/files");
  const body = await parseResponseBody(response);
  if (!response.ok) {
    state.files = [];
    const message = body.detail || "File list failed to load.";
    elements.fileList.innerHTML = `<p class="empty-state">${escapeHtml(message)}</p>`;
    elements.uploadStatus.textContent = message;
    renderEmptyDetail();
    return;
  }
  state.files = body.files || [];
  renderFileList();
  if (state.files.length) {
    const targetId = state.selectedFileId || state.files[0].id;
    renderFileDetail(state.files.find((item) => item.id === targetId) || state.files[0]);
  } else {
    renderEmptyDetail();
  }
}

function renderFileList() {
  elements.fileList.innerHTML = "";
  if (!state.files.length) {
    elements.fileList.innerHTML = `<p class="empty-state">No uploaded files yet.</p>`;
    return;
  }

  state.files.forEach((file) => {
    const summary = file.review_result?.summary || file.error_message || "Waiting for result";
    const button = document.createElement("button");
    button.type = "button";
    button.className = `session-item file-list-item ${file.id === state.selectedFileId ? "active-session" : ""}`;
    button.title = `${file.original_filename}\n${summary}`;
    button.innerHTML = `
      <span class="session-item-title">${escapeHtml(file.original_filename)}</span>
      <span class="session-item-meta">${escapeHtml(file.file_type)} / ${escapeHtml(file.status)}</span>
      <span class="session-item-submeta">${escapeHtml(formatRisk(file.review_result?.risk_level || "low"))}</span>
      <span class="session-item-submeta file-list-summary">${escapeHtml(summary)}</span>
    `;
    button.addEventListener("click", () => renderFileDetail(file));
    elements.fileList.appendChild(button);
  });
}

function renderFileDetail(file) {
  if (!file) {
    renderEmptyDetail();
    return;
  }
  state.selectedFileId = file.id;
  renderFileList();

  const review = file.review_result || {};
  elements.fileDetailTitle.textContent = file.original_filename;
  elements.detailStatus.textContent = file.status;
  elements.detailRisk.textContent = formatRisk(review.risk_level || "low");
  elements.detailCategories.textContent = (review.categories || []).join(", ") || "-";
  elements.detailSummary.textContent = review.summary || "-";
  elements.detailPath.textContent = file.storage_path || "-";
  elements.detailSize.textContent = formatBytes(file.size_bytes);
  elements.detailUser.textContent = file.uploaded_by || "Guest";
  elements.detailError.textContent = file.error_message || "-";
  elements.detailExtractionSummary.textContent = file.extraction_summary || "-";
  elements.detailExtractedText.textContent = file.extracted_text || "-";
  renderHits(review.hits || []);
}

function renderHits(hits) {
  elements.fileHitTableBody.innerHTML = "";
  if (!hits.length) {
    elements.fileHitTableBody.innerHTML = `<tr><td class="empty-cell" colspan="5">No matched business-sensitive hits.</td></tr>`;
    return;
  }
  hits.forEach((hit) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(hit.category)}</td>
      <td>${escapeHtml(formatRisk(hit.risk_level))}</td>
      <td>${escapeHtml(hit.location || "-")}</td>
      <td>${escapeHtml(hit.matched_text || "-")}</td>
      <td>${escapeHtml(hit.reason || "-")}</td>
    `;
    elements.fileHitTableBody.appendChild(row);
  });
}

function renderEmptyDetail() {
  elements.fileDetailTitle.textContent = "Select a reviewed file";
  elements.detailStatus.textContent = "-";
  elements.detailRisk.textContent = "-";
  elements.detailCategories.textContent = "-";
  elements.detailSummary.textContent = "-";
  elements.detailPath.textContent = "-";
  elements.detailSize.textContent = "-";
  elements.detailUser.textContent = "-";
  elements.detailError.textContent = "-";
  elements.detailExtractionSummary.textContent = "-";
  elements.detailExtractedText.textContent = "-";
  renderHits([]);
}

async function uploadFile(event) {
  event.preventDefault();
  const file = elements.uploadFileInput.files?.[0];
  if (!file) {
    elements.uploadStatus.textContent = "Select a file first.";
    return;
  }

  elements.uploadStatus.textContent = "Uploading and reviewing file...";
  const formData = new FormData();
  formData.append("file", file);
  formData.append("username", elements.uploadUsernameInput.value.trim() || "Guest");

  const response = await fetch("/api/file-review/files/upload", {
    method: "POST",
    body: formData,
  });
  const body = await response.json();
  if (!response.ok) {
    elements.uploadStatus.textContent = body.detail || "Upload failed.";
    return;
  }

  elements.uploadStatus.textContent = "Upload accepted. Review is running in the background...";
  elements.uploadForm.reset();
  elements.uploadUsernameInput.value = window.localStorage.getItem("chat_username") || "Guest";
  await loadFiles();
  renderFileDetail(body);
  await pollFileUntilFinished(body.id);
}

async function pollFileUntilFinished(fileId) {
  const maxAttempts = 120;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    const response = await fetch(`/api/file-review/files/${fileId}`);
    const file = await response.json();
    renderFileDetail(file);
    await loadFiles();
    if (file.status === "completed") {
      elements.uploadStatus.textContent = "Review completed.";
      return;
    }
    if (file.status === "failed") {
      elements.uploadStatus.textContent = file.error_message || "Review failed.";
      return;
    }
    elements.uploadStatus.textContent = "Review in progress...";
    await wait(2000);
  }
  elements.uploadStatus.textContent = "Review is still running. Refresh later to see the final result.";
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

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function wait(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function parseResponseBody(response) {
  const text = await response.text();
  if (!text) {
    return {};
  }
  try {
    return JSON.parse(text);
  } catch (_error) {
    return { detail: text };
  }
}
