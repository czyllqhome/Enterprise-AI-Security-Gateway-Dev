const state = {
  providers: [],
  selectedProvider: "openai",
};

const elements = {
  providerSelect: document.getElementById("credential-provider"),
  defaultModelInput: document.getElementById("credential-default-model"),
  baseUrlInput: document.getElementById("credential-base-url"),
  modelsInput: document.getElementById("credential-models"),
  apiKeyInput: document.getElementById("credential-api-key"),
  statusText: document.getElementById("credential-status"),
  credentialForm: document.getElementById("credential-form"),
  credentialList: document.getElementById("credential-list"),
  deleteButton: document.getElementById("delete-credential-btn"),
};

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  await loadProviders();
});

function bindEvents() {
  elements.providerSelect.addEventListener("change", handleProviderChange);
  elements.credentialForm.addEventListener("submit", saveCredential);
  elements.deleteButton.addEventListener("click", deleteCredential);
}

async function loadProviders() {
  const response = await fetch("/api/providers");
  const data = await response.json();
  state.providers = data.providers || [];
  renderProviderOptions();
  renderCredentialList();
  populateForm(state.selectedProvider);
}

function renderProviderOptions() {
  elements.providerSelect.innerHTML = "";
  state.providers.forEach((provider) => {
    const option = document.createElement("option");
    option.value = provider.provider;
    option.textContent = provider.display_name;
    elements.providerSelect.appendChild(option);
  });
  if (![...elements.providerSelect.options].some((option) => option.value === state.selectedProvider)) {
    state.selectedProvider = state.providers[0]?.provider || "openai";
  }
  elements.providerSelect.value = state.selectedProvider;
}

function renderCredentialList() {
  elements.credentialList.innerHTML = "";
  state.providers.forEach((provider) => {
    const item = document.createElement("div");
    item.className = "scanner-item provider-item";
    item.innerHTML = `
      <div class="provider-item-content">
        <strong>${escapeHtml(provider.display_name)}</strong>
        <p class="provider-key-line">${
          provider.requires_api_key === false
            ? "No API key required."
            : provider.configured
              ? `Saved: ${escapeHtml(provider.masked_api_key || "-")}`
              : "No API key saved yet."
        }</p>
        <p>Base URL: ${escapeHtml(provider.base_url)}</p>
        <p>Default Model: ${escapeHtml(provider.default_model)}</p>
      </div>
      <span class="scanner-badge ${provider.configured ? "scanner-badge-active" : "scanner-badge-inactive"}">
        ${provider.configured ? "Configured" : "Missing"}
      </span>
    `;
    elements.credentialList.appendChild(item);
  });
}

function handleProviderChange() {
  state.selectedProvider = elements.providerSelect.value;
  populateForm(state.selectedProvider);
}

function populateForm(providerName) {
  const provider = state.providers.find((item) => item.provider === providerName);
  if (!provider) {
    return;
  }

  elements.providerSelect.value = provider.provider;
  elements.defaultModelInput.value = provider.default_model || "";
  elements.baseUrlInput.value = provider.base_url || "";
  elements.modelsInput.value = (provider.models || []).join("\n");
  elements.apiKeyInput.value = "";
  elements.deleteButton.disabled = !provider.updated_at;
  elements.apiKeyInput.placeholder = provider.requires_api_key === false
    ? "No API key required for Ollama"
    : "Enter API key";
  elements.statusText.textContent = provider.requires_api_key === false
    ? `This provider uses a local Ollama endpoint at ${provider.base_url}.`
    : provider.configured
      ? `Saved key: ${provider.masked_api_key}`
      : "No API key saved for this provider yet.";
}

async function saveCredential(event) {
  event.preventDefault();

  const payload = {
    provider: elements.providerSelect.value,
    api_key: elements.apiKeyInput.value.trim(),
    base_url: elements.baseUrlInput.value.trim(),
    default_model: elements.defaultModelInput.value.trim(),
    models: elements.modelsInput.value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean),
  };

  const selectedProvider = state.providers.find((item) => item.provider === payload.provider);
  if ((selectedProvider?.requires_api_key ?? true) && !payload.api_key) {
    elements.statusText.textContent = "API key is required to save provider credentials.";
    return;
  }

  const response = await fetch("/api/providers", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = response.ok ? await response.json() : await response.json();
  if (!response.ok) {
    elements.statusText.textContent = body.detail || "Failed to save provider credential.";
    return;
  }

  elements.statusText.textContent = `${body.display_name} credential saved.`;
  await loadProviders();
  elements.apiKeyInput.value = "";
}

async function deleteCredential() {
  const provider = elements.providerSelect.value;
  if (!provider) {
    return;
  }
  if (!window.confirm(`Delete the saved API key for ${provider}?`)) {
    return;
  }

  const response = await fetch(`/api/providers/${provider}`, { method: "DELETE" });
  if (!response.ok) {
    const body = await response.json();
    elements.statusText.textContent = body.detail || "Failed to delete provider credential.";
    return;
  }

  elements.statusText.textContent = `Deleted saved key for ${provider}.`;
  await loadProviders();
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
