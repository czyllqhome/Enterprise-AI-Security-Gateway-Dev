import { useEffect, useState } from "react";
import { apiFetch } from "../../api/client";
import type { Scanner } from "../../api/types";
import { PageTitle } from "./DashboardPage";

const toggleableScanners = new Set(["bancode", "prompt_injection", "ban_topics", "privacy_filter", "business_sensitive", "custom_regex"]);

export function ScannersPage() {
  const [scanners, setScanners] = useState<Scanner[]>([]);
  const [enabled, setEnabled] = useState<string[]>([]);
  const [status, setStatus] = useState("");

  useEffect(() => {
    loadScanners();
  }, []);

  async function loadScanners() {
    const data = await apiFetch<{ scanners: Scanner[]; enabled_scanners: string[] }>("/api/console/scanners");
    setScanners(data.scanners);
    setEnabled(data.enabled_scanners);
  }

  async function setScannerEnabled(scannerId: string, isEnabled: boolean) {
    const nextEnabled = new Set(enabled);
    if (isEnabled) {
      nextEnabled.add(scannerId);
    } else {
      nextEnabled.delete(scannerId);
    }
    const data = await apiFetch<{ scanners: Scanner[]; enabled_scanners: string[] }>("/api/console/scanners", {
      method: "PUT",
      body: JSON.stringify({ enabled_scanners: [...nextEnabled] }),
    });
    setScanners(data.scanners);
    setEnabled(data.enabled_scanners);
    setStatus("Scanner 开关已更新。");
  }

  return (
    <>
      <PageTitle title="Scanners" subtitle="区分 enabled、available、active，并显示模型或检测机制" />
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
