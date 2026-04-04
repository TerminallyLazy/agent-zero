import { useEffect, useState } from "preact/hooks";

import { normalizeBaseUrl } from "../lib/api";
import { sendRuntimeMessage } from "../lib/extension";
import type { BackgroundState, ExtensionConfig } from "../lib/types";
import { DEFAULT_CONFIG } from "../lib/types";

export function App() {
  const [config, setConfig] = useState<ExtensionConfig>(DEFAULT_CONFIG);
  const [status, setStatus] = useState("Loading…");
  const [runtimeState, setRuntimeState] = useState<BackgroundState | null>(null);
  const [apiKeyVisible, setApiKeyVisible] = useState(false);
  const [busyAction, setBusyAction] = useState<"" | "save" | "refresh">("");

  useEffect(() => {
    void sendRuntimeMessage<{ ok: boolean; state: BackgroundState }>({ type: "get_state" }).then(async (result) => {
      if (!result.ok) {
        return;
      }

      const nextConfig = result.state.config;
      setConfig(nextConfig);
      setRuntimeState(result.state);
      setStatus(result.state.connectionError || result.state.lastStatus);

      if (nextConfig.baseUrl.trim() && nextConfig.apiKey.trim()) {
        await refreshStatus();
      }
    });
  }, []);

  const save = async () => {
    setBusyAction("save");
    try {
      const sanitizedConfig: ExtensionConfig = {
        ...config,
        baseUrl: normalizeBaseUrl(config.baseUrl),
        apiKey: config.apiKey.trim(),
        defaultProject: config.defaultProject.trim(),
      };

      setConfig(sanitizedConfig);
      const result = await sendRuntimeMessage<{ ok: boolean; state: BackgroundState }>({
        type: "save_config",
        config: sanitizedConfig,
      });
      if (result.ok) {
        setRuntimeState(result.state);
        setStatus(result.state.connectionError || "Saved. Connection refreshed.");
      }
    } finally {
      setBusyAction("");
    }
  };

  const refreshStatus = async () => {
    setBusyAction("refresh");
    try {
      const result = await sendRuntimeMessage<{ ok: boolean; state: BackgroundState }>({ type: "refresh" });
      if (result.ok) {
        setRuntimeState(result.state);
        setStatus(result.state.connectionError || result.state.lastStatus);
      }
    } finally {
      setBusyAction("");
    }
  };

  const hasBaseUrl = Boolean(config.baseUrl.trim());
  const hasApiKey = Boolean(config.apiKey.trim());
  const connectionHealthy = Boolean(hasBaseUrl && hasApiKey && runtimeState && !runtimeState.connectionError);

  return (
    <div className="options-shell">
      <section className="hero">
        <div>
          <div className="eyebrow">Agent Zero Chrome Bridge</div>
          <h1>Quick setup</h1>
          <p>Connect the extension to your Agent Zero app once, then the side panel will be ready whenever you open Chrome.</p>
        </div>
        <button className="secondary-button" onClick={() => setConfig((current) => ({ ...current, baseUrl: DEFAULT_CONFIG.baseUrl }))}>
          Use localhost default
        </button>
      </section>

      <section className="status-grid">
        <article className={`status-card ${hasBaseUrl ? "ok" : ""}`}>
          <span>1</span>
          <div>
            <strong>App address</strong>
            <p>{hasBaseUrl ? normalizeBaseUrl(config.baseUrl) : "Add the address of your Agent Zero app."}</p>
          </div>
        </article>

        <article className={`status-card ${hasApiKey ? "ok" : ""}`}>
          <span>2</span>
          <div>
            <strong>API token</strong>
            <p>{hasApiKey ? "Token added" : "Paste the same token your Agent Zero browser bridge expects."}</p>
          </div>
        </article>

        <article className={`status-card ${connectionHealthy ? "ok" : ""}`}>
          <span>3</span>
          <div>
            <strong>Connection</strong>
            <p>{connectionHealthy ? "Looks good" : "Save or test the connection after filling in the basics."}</p>
          </div>
        </article>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <div className="section-label">Basics</div>
            <h2>Only three things matter</h2>
          </div>
        </div>

        <label className="field">
          <span>Agent Zero address</span>
          <input
            placeholder="http://localhost:50001"
            value={config.baseUrl}
            onInput={(event) => setConfig({ ...config, baseUrl: (event.currentTarget as HTMLInputElement).value })}
          />
          <small>Most local installs use `http://localhost:50001`.</small>
        </label>

        <label className="field">
          <span>API token</span>
          <div className="input-with-action">
            <input
              type={apiKeyVisible ? "text" : "password"}
              placeholder="Paste your Agent Zero API token"
              value={config.apiKey}
              onInput={(event) => setConfig({ ...config, apiKey: (event.currentTarget as HTMLInputElement).value })}
            />
            <button className="secondary-button" onClick={() => setApiKeyVisible((current) => !current)}>
              {apiKeyVisible ? "Hide" : "Show"}
            </button>
          </div>
          <small>This is the same token the extension sends as `X-API-KEY`.</small>
        </label>

        <label className="field">
          <span>Default project</span>
          {runtimeState?.projects.length ? (
            <select
              value={config.defaultProject}
              onChange={(event) => setConfig({ ...config, defaultProject: (event.currentTarget as HTMLSelectElement).value })}
            >
              <option value="">Use no default project</option>
              {runtimeState.projects.map((project) => (
                <option key={project.name} value={project.name}>
                  {project.title || project.name}
                </option>
              ))}
            </select>
          ) : (
            <input
              placeholder="Optional project name"
              value={config.defaultProject}
              onInput={(event) => setConfig({ ...config, defaultProject: (event.currentTarget as HTMLInputElement).value })}
            />
          )}
          <small>Optional. If you leave this blank, the side panel starts without a project selected.</small>
        </label>

        <div className="actions">
          <button className="primary-button" disabled={busyAction === "save"} onClick={() => void save()}>
            {busyAction === "save" ? "Saving…" : "Save settings"}
          </button>
          <button className="secondary-button" disabled={busyAction === "refresh"} onClick={() => void refreshStatus()}>
            {busyAction === "refresh" ? "Checking…" : "Test connection"}
          </button>
        </div>

        <div className={`status-banner ${connectionHealthy ? "ok" : ""}`}>{status}</div>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <div className="section-label">Advanced</div>
            <h2>Timing controls</h2>
          </div>
        </div>

        <details className="advanced-panel">
          <summary>Show polling settings</summary>
          <div className="grid">
            <label className="field">
              <span>Chat poll (ms)</span>
              <input
                type="number"
                min="500"
                step="100"
                value={config.chatPollMs}
                onInput={(event) => setConfig({ ...config, chatPollMs: Number((event.currentTarget as HTMLInputElement).value) })}
              />
            </label>

            <label className="field">
              <span>Command poll (ms)</span>
              <input
                type="number"
                min="500"
                step="100"
                value={config.commandPollMs}
                onInput={(event) =>
                  setConfig({ ...config, commandPollMs: Number((event.currentTarget as HTMLInputElement).value) })
                }
              />
            </label>

            <label className="field">
              <span>Session poll (ms)</span>
              <input
                type="number"
                min="500"
                step="100"
                value={config.sessionPollMs}
                onInput={(event) =>
                  setConfig({ ...config, sessionPollMs: Number((event.currentTarget as HTMLInputElement).value) })
                }
              />
            </label>
          </div>
        </details>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <div className="section-label">Diagnostics</div>
            <h2>Current extension state</h2>
          </div>
        </div>
        <details className="advanced-panel">
          <summary>Show runtime snapshot</summary>
          <pre>{JSON.stringify(runtimeState, null, 2)}</pre>
        </details>
      </section>
    </div>
  );
}
