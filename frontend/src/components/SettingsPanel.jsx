import React, {useEffect, useRef, useState} from "react";
import {api} from "../api.js";

export default function SettingsPanel({open, welcome, onClose, onConfigured, audio, onAudioChange, voiceActive}) {
  const dialog = useRef(null);
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [settings, setSettings] = useState(null);
  const [devices, setDevices] = useState([]);
  const [canChooseOutput, setCanChooseOutput] = useState(false);
  useEffect(() => {
    if (open) {
      if (!dialog.current.open) dialog.current.showModal();
      setError(""); setNotice("");
      void api("/api/settings/gemini").then(setSettings).catch(failure => setError(failure.message));
      setCanChooseOutput(typeof AudioContext !== "undefined" && "setSinkId" in AudioContext.prototype);
      void navigator.mediaDevices?.enumerateDevices().then(setDevices).catch(() => {});
    } else {dialog.current.close(); setKey(""); setShow(false);}
  }, [open]);
  const act = async (operation) => {
    if (busy) return;
    setBusy(true); setError(""); setNotice("");
    try {setSettings(await operation()); setKey(""); setShow(false); onConfigured();}
    catch (failure) {setError(failure.message);}
    finally {setBusy(false);}
  };
  return <dialog ref={dialog} className="whatsapp-dialog settings-dialog" aria-labelledby="settings-title" onCancel={event => {event.preventDefault(); if (!busy) onClose();}}>
    <div className="dialog-heading"><div><h2 id="settings-title">{welcome ? "Welcome to Indu." : "Your Indu settings."}</h2><p>Gemini connection and your audio devices.</p></div><button className="icon-button close-dialog" onClick={onClose} disabled={busy} aria-label="Close settings">×</button></div>
    {error && <p className="form-notice is-error" role="alert">{error}</p>}
    {notice && <p className="form-notice" role="status">{notice}</p>}
    <div className="panel-content">
      <p className="section-intro">Connect your own Google Gemini key for voice and text. Get one in <a href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">Google AI Studio</a>.</p>
      <p role="status">{settings?.configured ? settings.verified ? "Gemini connection validated" : "Gemini configured" : "Gemini is not connected"}</p>
      {settings?.credential_management === "environment" ? <p className="field-hint">Gemini credentials are managed in the cloud server's environment settings. Browser microphone streaming remains available when Gemini is configured.</p> : <form className="contact-form" onSubmit={event => {event.preventDefault(); void act(() => api("/api/settings/gemini", {method:"PUT", body:{api_key:key}}));}}>
        <label>Gemini API key<input type={show ? "text" : "password"} value={key} onChange={event => setKey(event.target.value)} required minLength={20} maxLength={512} autoComplete="off" spellCheck={false} disabled={busy || voiceActive}/></label>
        <div className="form-actions"><button className="subtle-button" type="button" onClick={() => setShow(!show)}>{show ? "Hide key" : "Show key"}</button><button className="primary-button" disabled={busy || voiceActive || !key.trim()}>{busy ? "Validating…" : "Validate and save"}</button></div>
        <p className="field-hint">Saved in your operating system's credential store. Validation sends a small test request to Gemini. Text and audio you submit are sent to Google.</p>
        {settings?.configured && <button className="subtle-button" type="button" disabled={busy || voiceActive} onClick={() => void act(() => api("/api/settings/gemini", {method:"DELETE"}))}>Disconnect Gemini</button>}
      </form>}
      {voiceActive && <p className="field-hint">Exit the voice conversation before changing the key or audio devices.</p>}
      <div className="contact-form">
        <h3>Audio devices</h3>
        <label>Microphone<select aria-label="Microphone" value={audio?.input || ""} disabled={voiceActive} onChange={event => onAudioChange({...audio, input:event.target.value})}><option value="">System default microphone</option>{devices.filter(device => device.kind === "audioinput" && device.deviceId && device.deviceId !== "default").map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Microphone ${index + 1}`}</option>)}</select></label>
        <label>Speaker<select aria-label="Speaker" value={audio?.output || ""} disabled={voiceActive || !canChooseOutput} onChange={event => onAudioChange({...audio, output:event.target.value})}><option value="">System default speaker</option>{devices.filter(device => device.kind === "audiooutput" && device.deviceId && device.deviceId !== "default").map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Speaker ${index + 1}`}</option>)}</select></label>
        <p className="field-hint">Device names appear after microphone permission. {canChooseOutput ? "Changes apply to your next conversation." : "This browser uses the system speaker; change it in Windows sound settings."}</p>
      </div>
      {welcome && <button className="subtle-button" onClick={onClose} disabled={busy}>Continue without Gemini</button>}
    </div>
  </dialog>;
}
