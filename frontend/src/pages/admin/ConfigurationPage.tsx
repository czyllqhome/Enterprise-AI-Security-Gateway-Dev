import { FormEvent, useEffect, useMemo, useState } from "react";
import { FolderCog, Save } from "lucide-react";
import { apiFetch } from "../../api/client";
import type { FileStorageSettings } from "../../api/types";
import { PageTitle } from "./DashboardPage";

type StorageProfile = FileStorageSettings["active_storage_profile"];

export function ConfigurationPage() {
  const [settings, setSettings] = useState<FileStorageSettings | null>(null);
  const [activeProfile, setActiveProfile] = useState<StorageProfile>("windows");
  const [windowsPath, setWindowsPath] = useState("");
  const [linuxPath, setLinuxPath] = useState("");
  const [perUserSubdirectories, setPerUserSubdirectories] = useState(true);
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  async function loadSettings() {
    const data = await apiFetch<FileStorageSettings>("/api/file-review/settings");
    hydrate(data);
  }

  function hydrate(data: FileStorageSettings) {
    setSettings(data);
    setActiveProfile(data.active_storage_profile);
    setWindowsPath(data.windows_storage_path);
    setLinuxPath(data.linux_storage_path);
    setPerUserSubdirectories(data.per_user_subdirectories);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setStatus("");
    try {
      const data = await apiFetch<FileStorageSettings>("/api/file-review/settings", {
        method: "PUT",
        body: JSON.stringify({
          active_storage_profile: activeProfile,
          windows_storage_path: windowsPath,
          linux_storage_path: linuxPath,
          per_user_subdirectories: perUserSubdirectories,
        }),
      });
      hydrate(data);
      setStatus("Configuration saved.");
    } catch (exc) {
      setStatus(exc instanceof Error ? exc.message : "Save failed.");
    } finally {
      setSaving(false);
    }
  }

  const effectivePath = useMemo(() => {
    return activeProfile === "windows" ? windowsPath : linuxPath;
  }, [activeProfile, linuxPath, windowsPath]);

  return (
    <>
      <PageTitle title="Configuration" subtitle="Manage file upload storage paths for local and cloud runtimes." />
      <form className="panel form-stack configuration-form" onSubmit={submit}>
        <div className="configuration-head">
          <FolderCog size={20} />
          <div>
            <h2>Attachment Storage</h2>
            <p>Active profile: {activeProfile}</p>
          </div>
        </div>

        <div className="configuration-grid">
          <label>
            Active Path Profile
            <select value={activeProfile} onChange={(event) => setActiveProfile(event.target.value as StorageProfile)}>
              <option value="windows">Windows</option>
              <option value="linux">Linux</option>
            </select>
          </label>
          <label>
            Max Upload
            <input value={`${settings?.max_upload_mb ?? "-"} MB`} readOnly />
          </label>
        </div>

        <label>
          Windows Storage Path
          <input value={windowsPath} onChange={(event) => setWindowsPath(event.target.value)} />
        </label>
        <label>
          Linux Storage Path
          <input value={linuxPath} onChange={(event) => setLinuxPath(event.target.value)} />
        </label>

        <label className="inline-toggle">
          <input
            type="checkbox"
            checked={perUserSubdirectories}
            onChange={(event) => setPerUserSubdirectories(event.target.checked)}
          />
          Store uploads in username subdirectories
        </label>

        <div className="configuration-current">
          <span>Effective storage path</span>
          <code>{effectivePath || "-"}</code>
          <small>{perUserSubdirectories ? "Files are written under <username>." : "Files are written directly under the storage path."}</small>
        </div>

        <button className="primary-btn configuration-save" disabled={saving}>
          <Save size={17} />
          Save
        </button>
      </form>
      <div className="status-line">{status}</div>
    </>
  );
}
