
import React, { useEffect, useRef, useState } from "react";
import "./App.css";

const WS_URL = "ws://127.0.0.1:8000/ws/voice";
const INPUT_SAMPLE_RATE = 16000;
const OUTPUT_SAMPLE_RATE = 24000;

function App() {
  const [status, setStatus] = useState("idle");
  const [transcript, setTranscript] = useState("");
  const [induText, setInduText] = useState("");

  const socketRef = useRef(null);

  const audioContextRef = useRef(null);
  const microphoneStreamRef = useRef(null);
  const microphoneSourceRef = useRef(null);
  const processorRef = useRef(null);

  const audioQueueRef = useRef([]);
  const playingAudioRef = useRef(false);

  // ============================================================
  // CONNECT WEBSOCKET
  // ============================================================

  const connectWebSocket = () => {
    return new Promise((resolve, reject) => {
      const socket = new WebSocket(WS_URL);

      socket.binaryType = "arraybuffer";

      socket.onopen = () => {
        console.log("🌐 Connected to Indu backend.");
        socketRef.current = socket;
        resolve(socket);
      };

      socket.onerror = (error) => {
        console.error("❌ WebSocket error:", error);
        reject(error);
      };

      socket.onclose = () => {
        console.log("🔌 WebSocket disconnected.");
        socketRef.current = null;
      };

      socket.onmessage = (event) => {
        // ========================================================
        // TEXT MESSAGE FROM BACKEND
        // ========================================================

        if (typeof event.data === "string") {
          try {
            const data = JSON.parse(event.data);

            console.log("📩 Backend:", data);

            if (data.type === "user_transcript") {
              setTranscript((previous) => {
                const text = `${previous} ${data.text || ""}`.trim();
                return text;
              });

              setStatus("thinking");
            }

            if (data.type === "indu_transcript") {
              setInduText((previous) => {
                const text = `${previous} ${data.text || ""}`.trim();
                return text;
              });

              setStatus("speaking");
            }

            if (data.type === "error") {
              console.error(
                "❌ Indu backend error:",
                data.message
              );

              setStatus("idle");
            }

            return;
          } catch (error) {
            console.error(
              "❌ Could not parse backend message:",
              error
            );

            return;
          }
        }

        // ========================================================
        // AUDIO MESSAGE FROM GEMINI
        // ========================================================

        if (event.data instanceof ArrayBuffer) {
          console.log(
            "🔊 Received audio:",
            event.data.byteLength,
            "bytes"
          );

          audioQueueRef.current.push(event.data);

          playNextAudio();
        }
      };
    });
  };

  // ============================================================
  // PLAY GEMINI AUDIO
  // ============================================================

  const playNextAudio = () => {
    if (playingAudioRef.current) {
      return;
    }

    if (audioQueueRef.current.length === 0) {
      return;
    }

    const audioContext = audioContextRef.current;

    if (!audioContext) {
      audioQueueRef.current = [];
      return;
    }

    const audioData = audioQueueRef.current.shift();

    if (!audioData) {
      return;
    }

    playingAudioRef.current = true;

    try {
      const pcm16 = new Int16Array(audioData);

      const float32 = new Float32Array(pcm16.length);

      for (let i = 0; i < pcm16.length; i++) {
        float32[i] = pcm16[i] / 32768;
      }

      const audioBuffer = audioContext.createBuffer(
        1,
        float32.length,
        OUTPUT_SAMPLE_RATE
      );

      audioBuffer
        .getChannelData(0)
        .set(float32);

      const source =
        audioContext.createBufferSource();

      source.buffer = audioBuffer;

      source.connect(audioContext.destination);

      source.onended = () => {
        playingAudioRef.current = false;

        playNextAudio();
      };

      source.start(0);
    } catch (error) {
      console.error(
        "❌ Audio playback error:",
        error
      );

      playingAudioRef.current = false;

      playNextAudio();
    }
  };

  // ============================================================
  // CONVERT FLOAT32 → PCM16
  // ============================================================

  const float32ToPCM16 = (input) => {
    const output = new Int16Array(input.length);

    for (let i = 0; i < input.length; i++) {
      const sample = Math.max(
        -1,
        Math.min(1, input[i])
      );

      output[i] =
        sample < 0
          ? sample * 32768
          : sample * 32767;
    }

    return output;
  };

  // ============================================================
  // START MICROPHONE
  // ============================================================

  const startMicrophone = async (socket) => {
    console.log("🎙️ Requesting microphone...");

    const stream =
      await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

    microphoneStreamRef.current = stream;

    console.log("✅ Microphone permission granted.");

    const audioContext =
      new AudioContext({
        sampleRate: INPUT_SAMPLE_RATE,
      });

    audioContextRef.current = audioContext;

    await audioContext.resume();

    console.log(
      "🎧 AudioContext sample rate:",
      audioContext.sampleRate
    );

    const source =
      audioContext.createMediaStreamSource(
        stream
      );

    microphoneSourceRef.current = source;

    const processor =
      audioContext.createScriptProcessor(
        4096,
        1,
        1
      );

    processorRef.current = processor;

    processor.onaudioprocess = (event) => {
      if (
        socket.readyState !==
        WebSocket.OPEN
      ) {
        return;
      }

      const input =
        event.inputBuffer.getChannelData(0);

      const pcm16 =
        float32ToPCM16(input);

      try {
        socket.send(pcm16.buffer);
      } catch (error) {
        console.error(
          "❌ Failed to send microphone audio:",
          error
        );
      }
    };

    source.connect(processor);

    /*
      Connecting the processor to destination keeps
      ScriptProcessorNode active in browsers.

      We use a silent gain node so the microphone
      is not played back directly to the speakers.
    */

    const silentGain =
      audioContext.createGain();

    silentGain.gain.value = 0;

    processor.connect(silentGain);

    silentGain.connect(
      audioContext.destination
    );

    setStatus("listening");

    console.log("🎙️ Indu is listening.");
  };

  // ============================================================
  // STOP MICROPHONE
  // ============================================================

  const stopMicrophone = () => {
    console.log("🛑 Stopping microphone...");

    if (processorRef.current) {
      try {
        processorRef.current.disconnect();
      } catch {
        // Ignore disconnect errors.
      }

      processorRef.current = null;
    }

    if (microphoneSourceRef.current) {
      try {
        microphoneSourceRef.current.disconnect();
      } catch {
        // Ignore disconnect errors.
      }

      microphoneSourceRef.current = null;
    }

    if (microphoneStreamRef.current) {
      microphoneStreamRef.current
        .getTracks()
        .forEach((track) => {
          track.stop();
        });

      microphoneStreamRef.current = null;
    }

    if (audioContextRef.current) {
      try {
        audioContextRef.current.close();
      } catch {
        // Ignore close errors.
      }

      audioContextRef.current = null;
    }
  };

  // ============================================================
  // START INDU
  // ============================================================

  const startIndu = async () => {
    try {
      console.log("🌙 Starting Indu...");

      setTranscript("");
      setInduText("");

      audioQueueRef.current = [];
      playingAudioRef.current = false;

      setStatus("connecting");

      const socket =
        await connectWebSocket();

      await startMicrophone(socket);

      console.log(
        "✅ INDU IS READY"
      );
    } catch (error) {
      console.error(
        "❌ Could not start Indu:",
        error
      );

      stopMicrophone();

      if (socketRef.current) {
        try {
          socketRef.current.close();
        } catch {
          // Ignore close errors.
        }
      }

      socketRef.current = null;

      setStatus("idle");
    }
  };

  // ============================================================
  // STOP INDU
  // ============================================================

  const stopIndu = () => {
    console.log("🛑 Stopping Indu...");

    stopMicrophone();

    if (
      socketRef.current &&
      socketRef.current.readyState ===
        WebSocket.OPEN
    ) {
      try {
        socketRef.current.send(
          JSON.stringify({
            type: "stop",
          })
        );
      } catch {
        // Ignore send errors.
      }

      try {
        socketRef.current.close();
      } catch {
        // Ignore close errors.
      }
    }

    socketRef.current = null;

    audioQueueRef.current = [];

    playingAudioRef.current = false;

    setStatus("idle");
  };

  // ============================================================
  // CLEANUP
  // ============================================================

  useEffect(() => {
    return () => {
      stopMicrophone();

      if (socketRef.current) {
        try {
          socketRef.current.close();
        } catch {
          // Ignore close errors.
        }
      }

      socketRef.current = null;
    };
  }, []);

  // ============================================================
  // STATUS TEXT
  // ============================================================

  const getStatusText = () => {
    switch (status) {
      case "connecting":
        return "Connecting to Indu...";

      case "listening":
        return "Listening...";

      case "thinking":
        return "Thinking...";

      case "speaking":
        return "Indu is speaking...";

      default:
        return "Ready";
    }
  };

  // ============================================================
  // UI
  // ============================================================

  return (
    <div className="app">
      <div className="indu-container">

        <div
          className={`indu-orb ${status}`}
        >
          <div className="orb-core">
            INDU
          </div>
        </div>

        <h1>Indu</h1>

        <p className="status">
          {getStatusText()}
        </p>

        <button
          className="indu-button"
          onClick={
            status === "idle"
              ? startIndu
              : stopIndu
          }
        >
          {status === "idle"
            ? "Hey Indu"
            : "Stop Indu"}
        </button>

        {transcript && (
          <div className="message user-message">
            <strong>You:</strong>
            <span>{transcript}</span>
          </div>
        )}

        {induText && (
          <div className="message indu-message">
            <strong>Indu:</strong>
            <span>{induText}</span>
          </div>
        )}

      </div>
    </div>
  );
}

export default App;
