import React, {useState, useRef} from "react";
import {api} from "../api.js";
import Icon from "./Icon.jsx";

export default function MessagePreview({preview, onComplete, onCancel}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const processing = useRef(false);
  const act = async (confirmed) => {
    if (processing.current) return;
    processing.current = true; setBusy(true); setError("");
    try {
      const result = await api(`/api/whatsapp/preview/${preview.id}/${confirmed ? "confirm" : "cancel"}`, {method:"POST"});
      if (confirmed) onComplete(result); else onCancel();
    } catch (failure) {setError(failure.message);}
    finally {processing.current = false; setBusy(false);}
  };
  return <section className="message-preview" aria-label="Confirm WhatsApp message">
    <div className="preview-heading"><Icon name="whatsapp" size={18}/><strong>Review your message</strong></div>
    <p className="preview-recipient"><span>TO</span><strong>{preview.recipient}</strong><span>+{preview.phone}</span></p>
    <blockquote>{preview.message}</blockquote>
    <p className="preview-note">Confirm to open a prepared WhatsApp draft. You’ll review it and press Send in WhatsApp.</p>
    {error && <p className="field-hint" role="alert">{error}</p>}
    <div className="preview-actions"><button className="subtle-button" disabled={busy} onClick={() => act(false)}>Cancel</button><button className="primary-button" disabled={busy} onClick={() => act(true)}><Icon name="arrow" size={15}/>{busy ? "Opening…" : "Confirm and open WhatsApp"}</button></div>
  </section>;
}
