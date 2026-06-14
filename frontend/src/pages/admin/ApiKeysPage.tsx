import { FormEvent, useEffect, useState } from "react";
import { apiFetch } from "../../api/client";
import type { Provider } from "../../api/types";
import { PageTitle } from "./DashboardPage";

export function ApiKeysPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [defaultModel, setDefaultModel] = useState("");
  const [models, setModels] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    loadProviders();
  }, []);

  async function loadProviders() {
    const data = await apiFetch<{ providers: Provider[] }>("/api/providers");
    setProviders(data.providers);
    const first = data.providers[0];
    if (first) {
      hydrate(first);
    }
  }

  function hydrate(provider: Provider) {
    setSelectedProvider(provider.provider);
    setBaseUrl(provider.base_url);
    setDefaultModel(provider.default_model);
    setModels(provider.models.join("\n"));
    setApiKey("");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setStatus("");
    try {
      await apiFetch<Provider>("/api/providers", {
        method: "POST",
        body: JSON.stringify({
          provider: selectedProvider,
          api_key: apiKey,
          base_url: baseUrl,
          default_model: defaultModel,
          models: models.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean),
        }),
      });
      await loadProviders();
      setStatus("Provider 配置已保存。");
    } catch (exc) {
      setStatus(exc instanceof Error ? exc.message : "保存失败。");
    }
  }

  async function deleteProvider(provider: string) {
    await apiFetch<void>(`/api/providers/${provider}`, { method: "DELETE" });
    await loadProviders();
  }

  return (
    <>
      <PageTitle title="API Keys" subtitle="管理 Provider、模型列表和脱敏后的 Key 状态" />
      <section className="two-column">
        <div className="panel provider-list">
          {providers.map((provider) => (
            <button className={provider.provider === selectedProvider ? "active" : ""} key={provider.provider} onClick={() => hydrate(provider)}>
              <strong>{provider.display_name}</strong>
              <span>{provider.requires_api_key ? provider.masked_api_key || "未配置" : "本地模型"}</span>
            </button>
          ))}
        </div>
        <form className="panel form-stack" onSubmit={submit}>
          <label>Provider<input value={selectedProvider} onChange={(event) => setSelectedProvider(event.target.value)} /></label>
          <label>API Key<input value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder="留空则仅更新非 Key 配置" /></label>
          <label>Base URL<input value={baseUrl} onChange={(event) => setBaseUrl(event.target.value)} /></label>
          <label>Default Model<input value={defaultModel} onChange={(event) => setDefaultModel(event.target.value)} /></label>
          <label>Models<textarea value={models} onChange={(event) => setModels(event.target.value)} /></label>
          <div className="button-row">
            <button className="primary-btn">保存</button>
            <button className="secondary-btn danger-text" type="button" onClick={() => deleteProvider(selectedProvider)}>删除</button>
          </div>
        </form>
      </section>
      <div className="status-line">{status}</div>
    </>
  );
}
