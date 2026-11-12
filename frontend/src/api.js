export const apiBase = import.meta.env?.VITE_API_URL || (globalThis.location && !["5173", "4173"].includes(globalThis.location.port)
  ? globalThis.location.origin : `http://${globalThis.location?.hostname || "127.0.0.1"}:8000`);
const base = apiBase;

export class BackendCompatibilityError extends Error {}

export function backendCompatibility(info) {
  const required = ["contacts", "whatsapp_previews", "gemini_text", "continuous_voice", "secure_setup", "reminders", "live_information"];
  const compatible = info?.name === "Indu" && info.api_contract >= 1
    && required.every(feature => info.features?.includes(feature));
  return {compatible, message: compatible ? "" :
    `The running backend${info?.version ? ` (${info.version})` : ""} needs restarting to match this interface. Stop it with Ctrl+C in its terminal, then restart it from this project's folder.`};
}

export async function requireBackend(options) {
  const info = await api("/", options);
  const status = backendCompatibility(info);
  if (!status.compatible) throw new BackendCompatibilityError(status.message);
  return info;
}

export async function api(path, {signal, ...options} = {}) {
  const response = await fetch(new URL(path, base), {
    ...options, signal,
    headers: {"Content-Type": "application/json", ...options.headers},
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });
  let data;
  try { data = await response.json(); } catch { throw new Error("The backend returned an unreadable response."); }
  if (!response.ok) {
    const error = new Error(typeof data.detail === "string" ? data.detail : "The request could not be completed.");
    error.status = response.status;
    throw error;
  }
  return data;
}
