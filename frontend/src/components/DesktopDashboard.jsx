import React, {useEffect, useRef, useState} from "react";
import {api, BackendCompatibilityError, requireBackend} from "../api.js";
import AssistantScene from "./AssistantScene.jsx";
import Icon from "./Icon.jsx";
import WhatsAppPanel from "./WhatsAppPanel.jsx";
import MessagePreview from "./MessagePreview.jsx";
import SettingsPanel from "./SettingsPanel.jsx";
import RemindersPanel from "./RemindersPanel.jsx";

const stateNames = {idle: "Indu is sleeping", sleeping: "Indu is sleeping", connecting: "Connecting to Indu...", reconnecting: "Reconnecting...", listening: "Listening...", thinking: "Thinking...", speaking: "Indu is speaking...", executing: "Executing command...", error: "Voice connection error", confirmation: "Waiting for confirmation"};

export default function DesktopDashboard({status, transcript, induText, error, wakeText, onVoiceToggle, voiceActive, voiceConnected, voiceHistory = [], onStopSpeaking, onRetryVoice, pendingAction, clearPendingAction, audioDevices, onAudioChange, onAppExit}) {
  const [health, setHealth] = useState(null);
  const [backend, setBackend] = useState("checking");
  const [apiReady, setApiReady] = useState(false);
  const [backendError, setBackendError] = useState("");
  const [connection, setConnection] = useState({state:"disconnected"});
  const [contacts, setContacts] = useState([]);
  const [messages, setMessages] = useState([]);
  const [panelOpen, setPanelOpen] = useState(false);
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState([]);
  const [typing, setTyping] = useState(false);
  const [textError, setTextError] = useState("");
  const [clock, setClock] = useState(new Date());
  const [clearing, setClearing] = useState(false);
  const [preview, setPreview] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [welcome, setWelcome] = useState(false);
  const [remindersOpen, setRemindersOpen] = useState(false);
  const [reminders, setReminders] = useState([]);
  const [desktop, setDesktop] = useState(false);
  useEffect(() => {if (health?.features?.includes("secure_setup")) void api("/api/app/status").then(result => setDesktop(result.desktop)).catch(() => {});}, [health?.features?.includes("secure_setup")]);
  const notified = useRef(new Set());
  const refreshReminders = async () => {
    const data = await api("/api/reminders"); setReminders(data.reminders);
    for (const row of data.reminders.filter(row => row.status === "due")) {
      if (!notified.current.has(row.id) && "Notification" in window && Notification.permission === "granted") {
        new Notification("Indu reminder", {body:row.title, tag:row.id});
        notified.current.add(row.id);
      }
    }
  };
  useEffect(() => {
    if (!health?.features?.includes("reminders")) return;
    void refreshReminders().catch(() => {});
    const timer = setInterval(() => {void refreshReminders().catch(() => {});}, 2000);
    return () => clearInterval(timer);
  }, [health?.features?.includes("reminders")]);
  const setupChecked = useRef(false);
  useEffect(() => {
    if (health?.features?.includes("secure_setup") && !setupChecked.current) {
      setupChecked.current = true;
      if (!health.gemini?.configured) {setWelcome(true); setSettingsOpen(true);}
    }
  }, [health]);
  const timeline = useRef(null);
  const submitting = useRef(false);
  useEffect(() => {if (pendingAction) setPreview(pendingAction);}, [pendingAction]);

  const refreshWhatsApp = async () => {
    if (!apiReady) return;
    const [state, people, outbox] = await Promise.all([api("/api/whatsapp/status"), api("/api/contacts"), api("/api/whatsapp/messages")]);
    setConnection(state); setContacts(people.contacts); setMessages(outbox.messages);
  };
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const refreshHealth = async () => {
      try {
        await requireBackend({signal:controller.signal});
        const data = await api("/health", {signal:controller.signal});
        if (active) {setHealth(data); setBackend("online"); setApiReady(true); setBackendError("");}
      } catch (failure) {
        if (active) {
          setApiReady(false); setHealth(null);
          setBackend(failure instanceof BackendCompatibilityError ? "outdated" : "offline");
          setBackendError(failure instanceof BackendCompatibilityError ? failure.message : "Cannot reach the Indu backend. Start it in the backend terminal, then refresh this page.");
        }
      }
    };
    void refreshHealth();
    const interval = setInterval(refreshHealth, 20000);
    const timeInterval = setInterval(() => setClock(new Date()), 30000);
    return () => {active = false; controller.abort(); clearInterval(interval); clearInterval(timeInterval);};
  }, []);
  useEffect(() => {
    if (!apiReady) return;
    let active = true;
    const refresh = async () => {
      try {
        const [state, people, outbox] = await Promise.all([api("/api/whatsapp/status"), api("/api/contacts"), api("/api/whatsapp/messages")]);
        if (active) {setConnection(state); setContacts(people.contacts); setMessages(outbox.messages);}
      } catch (failure) {
        if (active && failure.status === 404) {
          setApiReady(false); setBackend("outdated");
          setBackendError("The running backend is missing the contacts or WhatsApp routes. Restart the backend to load the updated code.");
        }
      }
    };
    void refresh();
    const interval = setInterval(refresh, panelOpen ? 2000 : 10000);
    return () => {active = false; clearInterval(interval);};
  }, [panelOpen, apiReady]);
  useEffect(() => {
    if (timeline.current) timeline.current.scrollTop = timeline.current.scrollHeight;
  }, [transcript, induText, turns, typing, voiceHistory]);

  const submitText = async (text) => {
    if (!text.trim() || submitting.current || !apiReady) return;
    submitting.current = true;
    setTyping(true); setTextError(""); setInput("");
    setTurns(previous => [...previous, {role:"user", text:text.trim()}].slice(-40));
    try {
      const result = await api("/api/chat", {method:"POST", body:{message:text.trim(), request_id:crypto.randomUUID()}});
      setTurns(previous => [...previous, {role:"assistant", text:result.response, failed:!result.success}].slice(-40));
      if (result.confirmation) setPreview(result.confirmation);
      void refreshWhatsApp().catch(() => {});
    } catch (failure) {setTextError(failure.message);}
    finally {setTyping(false); submitting.current = false;}
  };
  const clearConversation = async () => {
    setClearing(true); setTextError("");
    try {await api("/api/memory/clear", {method:"POST"}); setTurns([]);}
    catch (failure) {setTextError(failure.message);}
    finally {setClearing(false);}
  };
  const activeStatus = status === "error" ? "error" : ["idle", "sleeping"].includes(status)
    ? typing ? "thinking" : "sleeping" : preview ? "confirmation" : status;
  const timeText = clock.toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"});
  const lastSend = messages[0];

  return <div className="app dashboard-app">
    <aside className="sidebar" aria-label="Main navigation"><a className="brand-mark" href="#" aria-label="Indu home">i<span/></a><div className="sidebar-links"><button className="nav-button active" aria-label="Assistant dashboard" onClick={() => setPanelOpen(false)}><Icon name="grid"/></button><button className="nav-button" aria-label="WhatsApp and contacts" disabled={!apiReady} onClick={() => setPanelOpen(true)}><Icon name="whatsapp"/></button><button className="nav-button" aria-label="Focus conversation" onClick={() => document.getElementById("command-input")?.focus()}><Icon name="message"/></button></div><div className="sidebar-bottom"><span className={`backend-dot ${backend}`} title={`Backend ${backend}`}/><span className="profile-avatar" title="Personal workspace">A</span></div></aside>
    <main className="workspace">
      <header className="topbar"><div className="wordmark">INDU<span>PERSONAL AI</span></div><div className="topbar-right"><button className="subtle-button" onClick={() => setRemindersOpen(true)} disabled={!health?.features?.includes("reminders")}>Reminders{reminders.some(row => row.status === "due") ? " •" : ""}</button><button className="subtle-button" onClick={() => {setWelcome(false); setSettingsOpen(true);}} disabled={!health?.features?.includes("secure_setup")}>Settings</button><span className="local-badge"><span/>Your personal workspace</span><span className="topbar-time">{timeText}</span><span className="topbar-avatar">A</span></div></header>
      <div className="workspace-body">
        <div className="page-heading"><div><p className="eyebrow">A LITTLE MORE POSSIBLE</p><h1>Your day. <span>With Indu.</span></h1><p>A place to think, connect, and get things done.</p></div><span className={`system-status ${backend}`}><span/>{backend === "online" ? "System online" : backend === "checking" ? "Checking connection" : backend === "outdated" ? "Restart backend" : "Backend offline"}</span></div>
        {backendError && <p className="backend-notice" role="alert">{backendError}</p>}
        {reminders.some(row => row.status === "due") && <button className="backend-notice reminder-alert" onClick={() => setRemindersOpen(true)}>Reminder due: {reminders.filter(row => row.status === "due").map(row => row.title).join(" · ")}</button>}
        <div className="main-grid">
          <section className="indu-container core-panel" aria-label="3D assistant">
            <div className="core-panel-top"><span className="panel-label"><span/>INDU CORE</span><span className="dimension-tag">3D / INTERACTIVE</span></div>
            <div className="core-stage"><div className="scene-grid"/><AssistantScene status={activeStatus}/><span className="scene-coordinate coordinate-left">01 / INDU</span><span className="scene-coordinate coordinate-right">MOVE TO EXPLORE <span>↗</span></span></div>
            <div className={`core-caption state-${activeStatus}`}>
              <span className="state-pill"><span/>{stateNames[activeStatus] || "Ready"}</span>
              <h2>{["idle", "sleeping"].includes(activeStatus) ? "Here for whatever's next." : activeStatus === "listening" ? "Go ahead. I'm listening." : activeStatus === "thinking" ? "A moment of thought." : activeStatus === "speaking" ? "A little clarity, coming up." : activeStatus === "executing" ? "Working on your request." : activeStatus === "confirmation" ? "A quick review before continuing." : activeStatus === "error" ? "Let's get your voice connected again." : "Let's get connected."}</h2>
              <p className="wake-status">{wakeText || "Ask a question, open an app, or send a message."}</p>
              <div className="voice-controls">
                <button className={`indu-button primary-button voice-button ${voiceActive ? "is-active" : ""}`} onClick={onVoiceToggle} disabled={!apiReady && !voiceActive}>
                  <Icon name={voiceActive ? "power" : "mic"} size={19}/>{voiceActive ? "Exit Indu" : "Hey Indu"}
                </button>
                {voiceActive && <button className="stop-speaking-button" onClick={onStopSpeaking} disabled={!voiceConnected || status !== "speaking"}><Icon name="stop" size={15}/>Stop speaking</button>}
                {status === "error" && voiceActive && <button className="stop-speaking-button" onClick={onRetryVoice} disabled={!apiReady}>Retry voice</button>}
              </div>
              <span className="voice-caption">{voiceConnected ? "Microphone on / continuous conversation" : voiceActive ? "Microphone off / conversation paused" : "Click to talk, or use your wake phrase"}</span>
            </div>
            <div className="core-panel-footer"><span><Icon name="volume" size={13}/>Natural voice</span><span className="footer-divider"/><span>English · తెలుగు · हिन्दी</span><span className="core-version">INDU 0.8</span></div>
          </section>
          <section className="conversation-panel" aria-label="Conversation"><div className="conversation-heading"><div><Icon name="message" size={19}/><h2>Conversation</h2></div><button className="icon-button" aria-label="Clear text conversation" title="Clear conversation" onClick={clearConversation} disabled={clearing || typing}><Icon name="plus" size={18}/></button></div>
            <div className="conversation-timeline" ref={timeline} aria-live="polite" aria-relevant="additions text">
              {!turns.length && !voiceHistory.length && !transcript && !induText && <div className="conversation-empty"><span className="empty-symbol"><Icon name="spark" size={25}/></span><h3>A good place to begin.</h3><p>Big questions. Small tasks.<br/>Whatever’s on your mind.</p><div className="example-prompt"><Icon name="mic" size={15}/><span>“Hey Indu, what can you do?”</span></div></div>}
              {turns.map((turn, index) => <div className={`message ${turn.role === "user" ? "user-message" : "indu-message"} ${turn.failed ? "message-failed" : ""}`} key={index}><strong>{turn.role === "user" ? "You" : "Indu"}</strong><span>{turn.text}</span></div>)}
              {voiceHistory.map(turn => <React.Fragment key={turn.id}>{turn.user && <div className="message user-message"><strong>You <small>VOICE</small></strong><span>{turn.user}</span></div>}{turn.assistant && <div className="message indu-message"><strong>Indu <small>VOICE</small></strong><span>{turn.assistant}</span></div>}</React.Fragment>)}
              {transcript && <div className="message user-message"><strong>You <small>VOICE</small></strong><span>{transcript}</span></div>}
              {induText && <div className="message indu-message"><strong>Indu <small>VOICE</small></strong><span>{induText}</span></div>}
              {preview && <MessagePreview key={preview.id} preview={preview} onComplete={(result) => {setPreview(null); clearPendingAction(); setTurns(previous => [...previous, {role:"assistant", text:result.response}]); void refreshWhatsApp().catch(() => {});}} onCancel={() => {setPreview(null); clearPendingAction();}}/>}
              {typing && <div className="typing-indicator" aria-label="Indu is thinking"><span/><span/><span/></div>}
            </div>
            {(error || textError) && <p className="conversation-error" role="alert">{error || textError}</p>}
            <form className="command-composer" onSubmit={(event) => {event.preventDefault(); void submitText(input);}}><label className="sr-only" htmlFor="command-input">Message Indu</label><input id="command-input" value={input} onChange={event => setInput(event.target.value)} maxLength={10000} placeholder="Ask Indu anything…" autoComplete="off" disabled={typing || !apiReady}/><button aria-label="Send message to Indu" disabled={typing || !apiReady || !input.trim()}><Icon name="arrow" size={19}/></button></form><p className="composer-caption">A thought away. A task closer.</p>
          </section>
        </div>
        <div className="integrations-heading"><h2>Your everyday, connected.</h2><span>Made to work together</span></div>
        <section className="integration-grid" aria-label="Connections"><button className="integration-card whatsapp-card" disabled={!apiReady} onClick={() => setPanelOpen(true)}><span className="app-icon whatsapp-icon"><Icon name="whatsapp" size={25}/></span><div><div className="integration-title"><h3>WhatsApp</h3><span className={connection.state === "connected" ? "mini-badge connected" : "mini-badge"}>{connection.state === "connected" ? "Connected" : "Connect"}</span></div><p>{connection.state === "connected" ? `${contacts.length} saved contacts · Send with your voice` : "Your people. Just a few words away."}</p></div><Icon name="arrow" size={17}/></button>
          <div className="integration-card"><span className="app-icon brain-icon"><Icon name="cpu" size={24}/></span><div><div className="integration-title"><h3>Gemini AI</h3><span className={`mini-badge ${health?.gemini?.configured ? "connected" : ""}`}>{!apiReady ? "Awaiting backend" : health?.gemini?.configured ? "Configured" : "Set API key"}</span></div><p>{health?.gemini?.model || "Gemini"} · Text conversations</p></div></div>
          <div className="integration-card"><span className="app-icon voice-icon"><Icon name="mic" size={24}/></span><div><div className="integration-title"><h3>Natural conversation</h3><span className={`mini-badge ${health?.gemini_live ? "connected" : ""}`}>{!apiReady ? "Awaiting backend" : health?.gemini_live ? "Configured" : "Set API key"}</span></div><p>Speak your mind, in your language.</p></div></div>
        </section>
        <section className="quick-actions" aria-label="Quick actions"><span>TRY A LITTLE SOMETHING</span><button onClick={() => void submitText("open youtube")} disabled={typing || !apiReady}><Icon name="globe" size={15}/>Open YouTube<Icon name="arrow" size={13}/></button><button disabled={!apiReady} onClick={() => setPanelOpen(true)}><Icon name="whatsapp" size={15}/>Message someone<Icon name="arrow" size={13}/></button><button onClick={() => {setInput("Explain something I've always wondered about: "); document.getElementById("command-input")?.focus();}}><Icon name="spark" size={15}/>Explore a thought<Icon name="arrow" size={13}/></button></section>
        {lastSend && <div className="last-send"><Icon name="whatsapp" size={15}/><span>Last WhatsApp message to <strong>{lastSend.contact}</strong></span><span className={`delivery-state delivery-${lastSend.status}`}>{lastSend.status}</span></div>}
        <footer className="workspace-footer"><span><span className="tiny-spark">✳</span> A little intelligence. A lot of possibility.</span>{desktop && <button className="subtle-button" onClick={onAppExit}>Close Indu app</button>}<span>CRAFTED BY AKASH BANGARU</span></footer>
      </div>
    </main>
    <WhatsAppPanel open={panelOpen} onClose={() => setPanelOpen(false)} connection={connection} contacts={contacts} refresh={refreshWhatsApp}/>
    <SettingsPanel open={settingsOpen} welcome={welcome} onClose={() => setSettingsOpen(false)} onConfigured={() => {void api("/health").then(setHealth).catch(() => {});}} audio={audioDevices} onAudioChange={onAudioChange} voiceActive={voiceActive}/>
    <RemindersPanel open={remindersOpen} onClose={() => setRemindersOpen(false)} reminders={reminders} refresh={refreshReminders}/>
  </div>;
}
