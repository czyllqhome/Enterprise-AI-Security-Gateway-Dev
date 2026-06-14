const logTableBody = document.getElementById("log-table-body");

document.addEventListener("DOMContentLoaded", async () => {
  await loadLogs();
});

async function loadLogs() {
  const response = await fetch("/api/logs");
  const logs = await response.json();

  logTableBody.innerHTML = "";
  if (!logs.length) {
    logTableBody.innerHTML = `<tr><td class="empty-cell" colspan="5">No sensitive prompt logs yet.</td></tr>`;
    return;
  }

  logs.forEach((log) => {
    const sensitiveContent = log.original_sensitive_content || "";
    const entityTypes = (log.detected_entity_types || []).join(", ");
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${escapeHtml(log.id)}</td>
      <td>${escapeHtml(log.username)}</td>
      <td>
        <span class="log-content-preview" title="${escapeHtml(sensitiveContent)}">${escapeHtml(sensitiveContent)}</span>
      </td>
      <td>
        <span class="log-entity-preview" title="${escapeHtml(entityTypes)}">${escapeHtml(entityTypes)}</span>
      </td>
      <td>${escapeHtml(log.created_at)}</td>
    `;
    logTableBody.appendChild(row);
  });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
