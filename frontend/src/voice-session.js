export const normalizeText = (text = "") => text.toLowerCase()
  .replace(/[^\p{L}\p{N}\s]/gu, " ").replace(/\s+/g, " ").trim();

const WAKE_PHRASES = ["hey indu", "hey hindu", "hey indoo", "hey endu", "hey andu", "hey induu", "hi indu", "a indu"];
const EXIT_WORDS = ["exit indu", "bye indu", "goodbye indu", "stop indu", "quit indu"];
export const isExitCommand = (text) => EXIT_WORDS.includes(normalizeText(text));
export const isWakePhrase = (text) => {
  const normalized = normalizeText(text);
  return WAKE_PHRASES.some((phrase) => normalized === phrase || normalized.startsWith(`${phrase} `));
};

export function voiceUrl(apiUrl, location = globalThis.location) {
  const url = new URL(apiUrl || `${location.protocol}//${location.hostname}:8000`);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws/voice";
  return url.toString();
}

// Resolve only after Gemini is ready, rather than the initial HTTP upgrade.
export function connectVoiceSocket(url, {
  isCurrent, onCreate, onMessage, onClose,
  WebSocketClass = globalThis.WebSocket, timeoutMs = 15000,
}) {
  return new Promise((resolve, reject) => {
    const socket = new WebSocketClass(url);
    socket.binaryType = "arraybuffer";
    let ready = false;
    let settled = false;
    const fail = (error) => {
      clearTimeout(timer);
      if (!settled) {
        settled = true;
        reject(error);
      }
      socket.close();
    };
    const timer = setTimeout(() => fail(new Error("Voice connection timed out.")), timeoutMs);
    socket.onopen = () => {
      if (!isCurrent()) fail(new Error("Voice session was cancelled."));
    };
    socket.onerror = () => fail(new Error("Could not connect to the Indu backend."));
    socket.onclose = () => {
      clearTimeout(timer);
      if (!settled) {
        settled = true;
        reject(new Error("Voice connection closed before it was ready."));
      }
      if (isCurrent()) onClose();
    };
    socket.onmessage = (event) => {
      if (!isCurrent()) return;
      let data = event.data;
      if (typeof data === "string") {
        try { data = JSON.parse(data); } catch { return; }
        if (!data || typeof data !== "object") return;
        if (data.type === "error") {
          const error = new Error(data.message || "Live voice failed.");
          fail(error);
          onMessage(data);
          return;
        }
        if (data.type === "ready") {
          if (settled) return;
          ready = settled = true;
          clearTimeout(timer);
          resolve(socket);
          return;
        }
      }
      if (ready) onMessage(data);
    };
    // Register immediately so cancellation can close a CONNECTING socket.
    onCreate(socket);
  });
}

export async function acquireMicrophone(isCurrent, mediaDevices = globalThis.navigator.mediaDevices, deviceId = "") {
  const stream = await mediaDevices.getUserMedia({audio: {
    channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true,
    ...(deviceId ? {deviceId:{exact:deviceId}} : {}),
  }});
  if (!isCurrent()) {
    stream.getTracks().forEach((track) => track.stop());
    return null;
  }
  return stream;
}
