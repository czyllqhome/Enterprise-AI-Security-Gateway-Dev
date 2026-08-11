import { useEffect, useState } from "react";
import { apiFetch } from "../../api/client";
import type { BusinessSensitiveScannerConfig, ConsoleScannersResponse, Scanner } from "../../api/types";
import { PageTitle } from "./DashboardPage";

const toggleableScanners = new Set(["bancode", "prompt_injection", "ban_topics", "privacy_filter", "business_sensitive", "custom_regex"]);
type BusinessSensitiveProvider = "ollama" | "qwen" | "bedrock";

export function ScannersPage() {
  const [scanners, setScanners] = useState<Scanner[]>([]);
  const [enabled, setEnabled] = useState<string[]>([]);
  const [businessConfig, setBusinessConfig] = useState<BusinessSensitiveScannerConfig | null>(null);
  const [selectedProvider, setSelectedProvider] = useState<BusinessSensitiveProvider>("ollama");
  const [selectedModel, setSelectedModel] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    loadScanners();
  }, []);

  async function loadScanners() {
    hydrateScanners(await apiFetch<ConsoleScannersResponse>("/api/console/scanners"));
  }

  function hydrateScanners(data: ConsoleScannersResponse) {
    setScanners(data.scanners);
    setEnabled(data.enabled_scanners);
    if (data.business_sensitive_config) {
      setBusinessConfig(data.business_sensitive_config);
      setSelectedProvider(data.business_sensitive_config.provider);
      setSelectedModel(data.business_sensitive_config.model);
    }
  }

  async function setScannerEnabled(scannerId: string, isEnabled: boolean) {
    const nextEnabled = new Set(enabled);
    if (isEnabled) {
      nextEnabled.add(scannerId);
    } else {
      nextEnabled.delete(scannerId);
    }
    const data = await apiFetch<ConsoleScannersResponse>("/api/console/scanners", {
      method: "PUT",
      body: JSON.stringify({ enabled_scanners: [...nextEnabled] }),
    });
    hydrateScanners(data);
    setStatus("Scanner switch updated.");
  }

  async function saveBusinessSensitiveConfig() {
    const data = await apiFetch<ConsoleScannersResponse>("/api/console/scanners/business-sensitive", {
      method: "PUT",
      body: JSON.stringify({ provider: selectedProvider, model: selectedModel }),
    });
    hydrateScanners(data);
    setStatus("Business Sensitive runtime updated.");
  }

  function setBusinessProvider(provider: BusinessSensitiveProvider) {
    setSelectedProvider(provider);
    const option = businessConfig?.options.find((item) => item.provider === provider);
    if (option) {
      setSelectedModel(option.model);
    }
  }

  const businessOptions = businessConfig?.options ?? [];
  const businessModelOptions = businessOptions.filter((option) => option.provider === selectedProvider);

  return (
    <>
      <PageTitle title="Scanners" subtitle="Manage enabled, available, and active scanner runtimes." />
      {businessConfig ? (
        <section className="panel scanner-runtime-panel">
          <div>
            <h2>Business Sensitive Runtime</h2>
            <p>{businessConfig.detail}</p>
          </div>
          <div className="scanner-runtime-controls">
            <label>
              Provider
              <select value={selectedProvider} onChange={(event) => setBusinessProvider(event.target.value as BusinessSensitiveProvider)}>
                {businessOptions.map((option) => (
                  <option key={option.provider} value={option.provider}>{option.label}</option>
                ))}
              </select>
            </label>
            <label>
              Model
              <select value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)}>
                {businessModelOptions.map((option) => (
                  <option key={`${option.provider}:${option.model}`} value={option.model}>{option.model}</option>
                ))}
              </select>
            </label>
            <button className="primary-btn" type="button" onClick={saveBusinessSensitiveConfig}>Save</button>
          </div>
          <div className="entity-strip">
            <span className={businessConfig.configured ? "ok" : "warn"}>runtime configured: {String(businessConfig.configured)}</span>
            <span>selected: {businessConfig.provider}/{businessConfig.model}</span>
          </div>
        </section>
      ) : null}
      <section className="scanner-grid">
        {scanners.map((scanner) => (
          <article className="scanner-card" key={scanner.id}>
            <div className="scanner-card-head">
              <div>
                <strong>{scanner.name}</strong>
                <span>{scanner.id}</span>
              </div>
              {toggleableScanners.has(scanner.id) ? (
                <label className="switch">
                  <input checked={scanner.enabled} type="checkbox" onChange={(event) => setScannerEnabled(scanner.id, event.target.checked)} />
                  <span />
                </label>
              ) : null}
            </div>
            <p>{scanner.detail}</p>
            <div className="entity-strip">
              <span className={scanner.enabled ? "ok" : "warn"}>enabled: {String(scanner.enabled)}</span>
              <span className={scanner.available ? "ok" : "warn"}>available: {String(scanner.available)}</span>
              <span className={scanner.active ? "ok" : "warn"}>active: {String(scanner.active)}</span>
            </div>
          </article>
        ))}
      </section>
      <div className="status-line">{status}</div>
    </>
  );
}
