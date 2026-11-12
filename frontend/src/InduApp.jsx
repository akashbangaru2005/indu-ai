
import React, { useEffect, useRef, useState } from "react";
import "./App.css";
import DesktopDashboard from "./components/DesktopDashboard.jsx";
import {api, apiBase, requireBackend} from "./api.js";
import { acquireMicrophone, connectVoiceSocket, isExitCommand, isWakePhrase, voiceUrl } from "./voice-session.js";

const WS_URL = voiceUrl(apiBase);
const OUTPUT_SAMPLE_RATE = 24000;

// Keep false unless you want to mute the microphone while Indu speaks.
const HALF_DUPLEX = false;

function App() {
  // ----------------------------------------------------------
  // UI STATE
  // ----------------------------------------------------------

  const [status, setStatus] = useState("sleeping");
  const [transcript, setTranscript] = useState("");
  const [induText, setInduText] = useState("");
  const [error, setError] = useState("");
  const [pendingAction, setPendingAction] = useState(null);
  const [voiceHistory, setVoiceHistory] = useState([]);
  const [audioDevices, setAudioDevices] = useState(() => {
    try {return JSON.parse(localStorage.getItem("indu-audio-devices")) || {input:"", output:""};}
    catch {return {input:"", output:""};}
  });
  const audioDevicesRef = useRef(audioDevices);
  const changeAudioDevices = next => {
    audioDevicesRef.current = next; setAudioDevices(next);
    try {localStorage.setItem("indu-audio-devices", JSON.stringify(next));} catch {}
  };
  const [wakeText, setWakeText] = useState(
    'Listening for "Hey Indu"...'
  );

  // ----------------------------------------------------------
  // SESSION
  // ----------------------------------------------------------

  const socketRef = useRef(null);
  const sessionActiveRef = useRef(false);
  const conversationWantedRef = useRef(false);
  const mutedOutputRef = useRef(false);
  const backendReadyRef = useRef(false);
  const sessionIdRef = useRef(0);
  const statusRef = useRef("sleeping");

  // ----------------------------------------------------------
  // MICROPHONE / AUDIO WORKLET
  // ----------------------------------------------------------

  const audioContextRef = useRef(null);
  const micStreamRef = useRef(null);
  const micSourceRef = useRef(null);
  const workletRef = useRef(null);
  const silentGainRef = useRef(null);

  // ----------------------------------------------------------
  // AUDIO PLAYBACK
  // ----------------------------------------------------------

  const activeSourcesRef = useRef(new Set());
  const nextPlayTimeRef = useRef(0);

  const turnCompleteRef = useRef(false);
  const speakingRef = useRef(false);

  // ----------------------------------------------------------
  // TRANSCRIPT
  // ----------------------------------------------------------

  const newTurnRef = useRef(true);
  const userTextRef = useRef("");
  const assistantTextRef = useRef("");

  // ----------------------------------------------------------
  // WAKE WORD
  // ----------------------------------------------------------

  const wakeRecognitionRef = useRef(null);
  const wakeActiveRef = useRef(false);
  const wakeWantedRef = useRef(true);
  const wakeRestartTimerRef = useRef(null);

  // ----------------------------------------------------------
  // STATUS
  // ----------------------------------------------------------

  const updateStatus = (next) => {
    statusRef.current = next;
    setStatus(next);
  };

  // ============================================================
  // PLAYBACK
  // ============================================================

  const flushPlayback = () => {
    activeSourcesRef.current.forEach((source) => {
      try {
        source.onended = null;
        source.stop();
        source.disconnect();
      } catch {}
    });

    activeSourcesRef.current.clear();
    nextPlayTimeRef.current = 0;
    speakingRef.current = false;
  };

  const beginTurn = () => {
    if (!newTurnRef.current) return;
    const previous = {id: crypto.randomUUID(), user: userTextRef.current, assistant: assistantTextRef.current};
    if (previous.user || previous.assistant) {
      setVoiceHistory(history => [...history, previous].slice(-100));
    }
    newTurnRef.current = false;
    userTextRef.current = "";
    assistantTextRef.current = "";
    mutedOutputRef.current = false;
    turnCompleteRef.current = false;
    setTranscript("");
    setInduText("");
  };

  const finishResponse = () => {
    if (!sessionActiveRef.current || !turnCompleteRef.current || activeSourcesRef.current.size) return;
    turnCompleteRef.current = false;
    speakingRef.current = false;
    updateStatus("listening");
    setWakeText("Conversation is active. Ask your next question.");
  };

  const playChunk = (arrayBuffer) => {
    const ctx = audioContextRef.current;

    if (!ctx || !sessionActiveRef.current || mutedOutputRef.current) {
      return;
    }

    const usable =
      arrayBuffer.byteLength -
      (arrayBuffer.byteLength % 2);

    if (usable <= 0) {
      return;
    }

    const pcm16 = new Int16Array(
      arrayBuffer.slice(0, usable)
    );

    const float32 = new Float32Array(pcm16.length);

    for (let i = 0; i < pcm16.length; i++) {
      float32[i] = pcm16[i] / 32768;
    }

    const buffer = ctx.createBuffer(
      1,
      float32.length,
      OUTPUT_SAMPLE_RATE
    );

    buffer.getChannelData(0).set(float32);

    const source = ctx.createBufferSource();

    source.buffer = buffer;
    source.connect(ctx.destination);

    const now = ctx.currentTime;

    if (nextPlayTimeRef.current < now + 0.02) {
      nextPlayTimeRef.current = now + 0.06;
    }

    const startAt = nextPlayTimeRef.current;

    nextPlayTimeRef.current =
      startAt + buffer.duration;

    activeSourcesRef.current.add(source);

    source.onended = () => {
      activeSourcesRef.current.delete(source);

      try { source.disconnect(); } catch {}
      finishResponse();
    };

    source.start(startAt);

    if (!speakingRef.current) {
      speakingRef.current = true;
      updateStatus("speaking");

      console.log("🔊 Indu is speaking...");
    }
  };

  // ============================================================
  // BACKEND MESSAGES
  // ============================================================

  const handleBackendMessage = (data) => {
    switch (data.type) {
      case "user_turn_started":
        newTurnRef.current = true;
        beginTurn();
        break;
      case "user_transcript":
        beginTurn();
        userTextRef.current += data.text || "";
        setTranscript(userTextRef.current);
        if (!speakingRef.current) updateStatus("listening");
        break;
      case "input_complete":
        if (isExitCommand(userTextRef.current)) { exitIndu(); return; }
        if (!speakingRef.current) updateStatus("thinking");
        break;
      case "indu_transcript":
        assistantTextRef.current += data.text || "";
        setInduText(assistantTextRef.current);
        break;
      case "interrupted":
        flushPlayback();
        mutedOutputRef.current = false;
        turnCompleteRef.current = false;
        updateStatus("listening");
        setWakeText("Conversation is active. I am listening.");
        break;
      case "command_started":
        flushPlayback();
        mutedOutputRef.current = true;
        turnCompleteRef.current = false;
        assistantTextRef.current = "";
        setInduText("");
        updateStatus("executing");
        setWakeText("Working on your request...");
        break;
      case "command_result":
        assistantTextRef.current = [assistantTextRef.current, data.response].filter(Boolean).join("\n");
        setInduText(assistantTextRef.current);
        if (data.confirmation) setPendingAction(data.confirmation);
        break;
      case "command_acknowledgement":
        mutedOutputRef.current = false;
        turnCompleteRef.current = false;
        break;
      case "turn_complete":
        turnCompleteRef.current = true;
        newTurnRef.current = true;
        finishResponse();
        break;
      case "error":
        failSession(data.message || "Live voice failed. Retry voice to reconnect.");
        break;
      default:
        break;
    }
  };

  // ============================================================
  // WEBSOCKET
  // ============================================================

  const connectWebSocket = (sessionId) => connectVoiceSocket(WS_URL, {
    isCurrent: () => sessionId === sessionIdRef.current && sessionActiveRef.current,
    onCreate: (socket) => { socketRef.current = socket; },
    onMessage: (data) => {
      if (data instanceof ArrayBuffer) playChunk(data);
      else handleBackendMessage(data);
    },
    onClose: () => {
      failSession("Voice connection closed. Retry voice to reconnect, or choose Exit Indu.");
    },
  }).then((socket) => {
    if (sessionId === sessionIdRef.current) backendReadyRef.current = true;
    return socket;
  });

  // ============================================================
  // MICROPHONE — AUDIO WORKLET
  // ============================================================

  const setupAudio = async (sessionId) => {
    console.log(
      "🎙️ Requesting microphone permission..."
    );

    const isCurrent = () => sessionId === sessionIdRef.current && sessionActiveRef.current;
    const stream = await acquireMicrophone(isCurrent, navigator.mediaDevices, audioDevicesRef.current.input);
    if (!stream) return;

    micStreamRef.current = stream;
    stream.getAudioTracks().forEach(track => track.addEventListener("ended", () => {
      if (isCurrent()) failSession("The microphone disconnected. Check the device and choose Retry voice.");
    }, {once:true}));

    const ctx = new AudioContext({
      latencyHint: "interactive",
    });

    audioContextRef.current = ctx;

    if (audioDevicesRef.current.output) {
      if (!ctx.setSinkId) throw new Error("This browser cannot select a speaker. Choose the system default in Settings.");
      await ctx.setSinkId(audioDevicesRef.current.output);
      if (!isCurrent()) return;
    }

    await ctx.resume();
    if (!isCurrent()) return;
    ctx.onstatechange = () => {
      if (isCurrent() && ["closed", "suspended"].includes(ctx.state)) {
        failSession("Audio was interrupted by the device or browser. Choose Retry voice to continue.");
      }
    };

    /*
     * This loads:
     *
     * frontend/public/mic-processor.js
     *
     * Vite serves public/ files from "/".
     */
    await ctx.audioWorklet.addModule(
      "/mic-processor.js"
    );
    if (!isCurrent()) return;

    const source =
      ctx.createMediaStreamSource(stream);

    micSourceRef.current = source;

    const worklet =
      new AudioWorkletNode(
        ctx,
        "mic-processor"
      );

    workletRef.current = worklet;
    worklet.onprocessorerror = () => {
      if (isCurrent()) failSession("Microphone processing failed. Choose Retry voice to continue.");
    };

    worklet.port.onmessage = (event) => {
      const socket =
        socketRef.current;

      if (
        !sessionActiveRef.current ||
        !backendReadyRef.current ||
        !socket ||
        socket.readyState !== WebSocket.OPEN ||
        socket.bufferedAmount > 65536
      ) {
        return;
      }

      /*
       * Optional half-duplex mode.
       *
       * false = allow microphone while Indu speaks.
       */
      if (
        HALF_DUPLEX &&
        speakingRef.current
      ) {
        return;
      }

      try {
        socket.send(event.data);
      } catch (error) {
        console.error(
          "❌ Failed to send microphone audio:",
          error
        );
      }
    };

    source.connect(worklet);

    /*
     * Keep AudioWorklet processing alive
     * without sending audible microphone audio
     * to the speakers.
     */
    const silent =
      ctx.createGain();

    silent.gain.value = 0;

    silentGainRef.current = silent;

    worklet.connect(silent);

    silent.connect(ctx.destination);

    console.log(
      "🎙️ Microphone AudioWorklet ready."
    );
  };

  // ============================================================
  // AUDIO CLEANUP
  // ============================================================

  const teardownAudio = () => {
    flushPlayback();

    if (workletRef.current) {
      try {
        workletRef.current.port.onmessage =
          null;

        workletRef.current.port.close();
        workletRef.current.disconnect();
      } catch {}

      workletRef.current = null;
    }

    if (silentGainRef.current) {
      try {
        silentGainRef.current.disconnect();
      } catch {}

      silentGainRef.current = null;
    }

    if (micSourceRef.current) {
      try {
        micSourceRef.current.disconnect();
      } catch {}

      micSourceRef.current = null;
    }

    if (micStreamRef.current) {
      micStreamRef.current
        .getTracks()
        .forEach((track) => {
          try {
            track.stop();
          } catch {}
        });

      micStreamRef.current = null;
    }

    if (audioContextRef.current) {
      try {
        audioContextRef.current.close().catch(() => {});
      } catch {}

      audioContextRef.current = null;
    }

    console.log(
      "🧹 Audio resources cleaned."
    );
  };

  // ============================================================
  // WAKE WORD
  // ============================================================

  const stopWakeListener = () => {
    clearTimeout(
      wakeRestartTimerRef.current
    );

    const recognition =
      wakeRecognitionRef.current;

    wakeRecognitionRef.current = null;
    wakeActiveRef.current = false;

    if (recognition) {
      try {
        recognition.onend = null;
        recognition.onresult = null;
        recognition.onerror = null;

        recognition.abort();
      } catch {}
    }
  };

  const startWakeListener = () => {
    if (
      !wakeWantedRef.current ||
      conversationWantedRef.current ||
      wakeActiveRef.current ||
      wakeRecognitionRef.current
    ) {
      return;
    }

    const SpeechRecognition =
      window.SpeechRecognition ||
      window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setWakeText(
        'Speech recognition unsupported. Click "Hey Indu".'
      );

      return;
    }

    try {
      const recognition =
        new SpeechRecognition();

      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "en-IN";
      recognition.maxAlternatives = 3;

      wakeRecognitionRef.current =
        recognition;

      recognition.onstart = () => {
        wakeActiveRef.current = true;

        setWakeText(
          'Listening for "Hey Indu"...'
        );

        console.log(
          '👂 Wake listener active. Say "Hey Indu".'
        );
      };

      recognition.onresult = (event) => {
        let detected = false;
        for (let i = event.resultIndex; i < event.results.length; i++) {
          for (let a = 0; a < event.results[i].length; a++) {
            if (isWakePhrase(event.results[i][a].transcript)) detected = true;
          }
        }
        if (detected) {
          stopWakeListener();

          startIndu();
        }
      };

      recognition.onerror = (event) => {
        console.warn(
          "⚠️ Wake recognition:",
          event.error
        );

        if (
          event.error === "not-allowed" ||
          event.error ===
            "service-not-allowed"
        ) {
          wakeWantedRef.current = false;

          setWakeText(
            'Mic blocked. Click "Hey Indu" to start.'
          );
        }
      };

      recognition.onend = () => {
        wakeActiveRef.current = false;
        wakeRecognitionRef.current = null;

        if (
          wakeWantedRef.current &&
          !conversationWantedRef.current
        ) {
          clearTimeout(
            wakeRestartTimerRef.current
          );

          wakeRestartTimerRef.current =
            setTimeout(
              startWakeListener,
              250
            );
        }
      };

      recognition.start();
    } catch (error) {
      wakeActiveRef.current = false;
      wakeRecognitionRef.current = null;

      console.error(
        "❌ Could not start wake listener:",
        error
      );
    }
  };

  // ============================================================
  // SESSION LIFECYCLE
  // ============================================================

  const stopTransport = (notifyBackend = false) => {
    sessionIdRef.current += 1;
    sessionActiveRef.current = false;
    backendReadyRef.current = false;
    turnCompleteRef.current = false;
    speakingRef.current = false;
    wakeWantedRef.current = false;
    stopWakeListener();
    const socket = socketRef.current;
    socketRef.current = null;
    if (socket) {
      try {
        if (notifyBackend && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type:"stop"}));
        socket.close(1000, "Conversation stopped");
      } catch {}
    }
    teardownAudio();
  };

  const failSession = (message) => {
    stopTransport(false);
    setError(message);
    updateStatus("error");
    setWakeText("Voice is paused. Retry voice to reconnect, or choose Exit Indu.");
  };

  const stopSpeaking = () => {
    if (!conversationWantedRef.current) return;
    flushPlayback();
    mutedOutputRef.current = true;
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({type:"stop_speaking"}));
    if (sessionActiveRef.current && backendReadyRef.current) {
      updateStatus("listening");
      setWakeText("Speech stopped. You can continue talking.");
    }
  };

  // ============================================================
  // START INDU
  // ============================================================

  const startIndu = async () => {
    if (sessionActiveRef.current) return;
    const retrying = conversationWantedRef.current;
    const sessionId = sessionIdRef.current + 1;
    sessionIdRef.current = sessionId;
    conversationWantedRef.current = true;
    sessionActiveRef.current = true;
    backendReadyRef.current = false;
    mutedOutputRef.current = false;
    wakeWantedRef.current = false;
    stopWakeListener();
    newTurnRef.current = true;
    turnCompleteRef.current = false;
    speakingRef.current = false;
    setWakeText("Connecting your continuous conversation...");
    setError("");
    updateStatus(retrying ? "reconnecting" : "connecting");
    try {
      await requireBackend();
      if (sessionId !== sessionIdRef.current || !sessionActiveRef.current) return;
      await Promise.all([connectWebSocket(sessionId), setupAudio(sessionId)]);
      if (sessionId !== sessionIdRef.current || !sessionActiveRef.current) return;
      updateStatus("listening");
      setWakeText("Conversation is active. Ask your first question.");
    } catch (failure) {
      if (sessionId === sessionIdRef.current) failSession(failure.message || "Could not start voice.");
    }
  };

  const exitIndu = () => {
    conversationWantedRef.current = false;
    stopTransport(true);
    setError("");
    updateStatus("sleeping");
    setWakeText("Indu is sleeping. Click Hey Indu to start a new conversation.");
  };

  const handleButton = () => {
    if (conversationWantedRef.current) exitIndu();
    else void startIndu();
  };

  // ============================================================
  // MOUNT / UNMOUNT
  // ============================================================

  useEffect(() => {
    wakeWantedRef.current = true;

    const timer =
      setTimeout(
        startWakeListener,
        500
      );

    return () => {
      clearTimeout(timer);

      wakeWantedRef.current = false;

      stopWakeListener();

      conversationWantedRef.current = false;
      stopTransport(true);
    };

    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return <DesktopDashboard status={status} transcript={transcript} induText={induText}
    error={error} wakeText={wakeText} onVoiceToggle={handleButton}
    pendingAction={pendingAction} clearPendingAction={() => setPendingAction(null)}
    voiceHistory={voiceHistory} onStopSpeaking={stopSpeaking} onRetryVoice={startIndu}
    audioDevices={audioDevices} onAudioChange={changeAudioDevices}
    onAppExit={async () => {exitIndu(); try {await api("/api/app/exit", {method:"POST"}); setWakeText("Indu is closed. You can close this tab.");} catch (failure) {setError(failure.message);}}}
    voiceActive={conversationWantedRef.current} voiceConnected={sessionActiveRef.current && backendReadyRef.current}/>;

}

export default App;
