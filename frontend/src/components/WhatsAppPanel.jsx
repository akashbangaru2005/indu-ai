import React, {useEffect, useRef, useState} from "react";
import {api} from "../api.js";
import Icon from "./Icon.jsx";
import MessagePreview from "./MessagePreview.jsx";

const labels = {connected: "Connected", web_opened: "WhatsApp Web opened · login unverified", connecting: "Connecting", qr: "Scan to connect", disconnected: "Open WhatsApp Web to link", error: "Connection needs attention"};

export default function WhatsAppPanel({open, onClose, connection, contacts, refresh}) {
  const dialog = useRef(null);
  const [tab, setTab] = useState("connection");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [editing, setEditing] = useState(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [aliases, setAliases] = useState("");
  const [recipient, setRecipient] = useState("");
  const [message, setMessage] = useState("");
  const [preview, setPreview] = useState(null);
  const sendId = useRef(null);
  const actionBusy = useRef(false);

  useEffect(() => {
    if (open && !dialog.current.open) dialog.current.showModal();
    else if (!open && dialog.current.open) dialog.current.close();
  }, [open]);

  const act = async (operation) => {
    if (actionBusy.current) return;
    actionBusy.current = true;
    setBusy(true); setError(""); setNotice("");
    try { await operation(); await refresh(); }
    catch (failure) { setError(failure.message || "Could not reach the backend."); }
    finally { setBusy(false); actionBusy.current = false; }
  };
  const resetContact = () => { setEditing(null); setName(""); setPhone(""); setAliases(""); };

  return <dialog ref={dialog} className="whatsapp-dialog" aria-labelledby="whatsapp-title" onCancel={(event) => {event.preventDefault(); onClose();}}>
    <div className="dialog-heading"><span className="app-icon whatsapp-icon"><Icon name="whatsapp" size={24}/></span><div><h2 id="whatsapp-title">Your WhatsApp workspace.</h2><p>Contacts, message previews, and WhatsApp Web.</p></div><button className="icon-button close-dialog" onClick={onClose} aria-label="Close WhatsApp"><Icon name="close"/></button></div>
    <div className="panel-tabs" role="tablist" aria-label="WhatsApp settings">
      {[['connection', 'Connection'], ['contacts', 'Contacts'], ['send', 'Send a message']].map(([key, label]) => <button key={key} role="tab" id={`wa-tab-${key}`} aria-controls={`wa-panel-${key}`} aria-selected={tab === key} onClick={() => {setTab(key); setError(""); setNotice("");}}>{label}{key === "contacts" && <span>{contacts.length}</span>}</button>)}
    </div>
    {error && <p className="form-notice is-error" role="alert">{error}</p>}
    {notice && <p className="form-notice" role="status">{notice}</p>}
    <div className="panel-content" role="tabpanel" id={`wa-panel-${tab}`} aria-labelledby={`wa-tab-${tab}`}>
      {tab === "connection" && <>
        <div className={`connection-banner ${connection.state === "connected" ? "is-connected" : ""}`}><span className="connection-light"/><strong>{labels[connection.state] || "Not connected"}</strong>{connection.account && <span>{connection.account}</span>}</div>
        {connection.qr ? <div className="qr-area"><img src={connection.qr} alt="WhatsApp linking QR code" width="250" height="250"/><p>Open WhatsApp on your phone → Linked devices → Link a device.</p></div> : <div className="connect-illustration"><div className="connect-rings"><Icon name={connection.state === "connected" ? "check" : "whatsapp"} size={38}/></div><h3>{connection.state === "connected" ? "Ready when you are." : "One scan. Your own WhatsApp."}</h3><p>{connection.detail || "Link your phone to send messages by voice or text."}</p></div>}
        <div className="connection-actions"><button className="primary-button" disabled={busy} onClick={() => act(async () => {await api("/api/whatsapp/connect", {method:"POST"});})}><Icon name="whatsapp" size={18}/>Open WhatsApp Web to link</button></div>
        <p className="privacy-note"><Icon name="check" size={14}/>WhatsApp manages account linking in your browser. Direct sending is not enabled.</p>
      </>}
      {tab === "contacts" && <>
        <p className="section-intro">Save a name and number so Indu knows exactly who you mean.</p>
        <form className="contact-form" onSubmit={(event) => {event.preventDefault(); act(async () => {
          await api(editing ? `/api/contacts/${editing}` : "/api/contacts", {method: editing ? "PUT" : "POST", body: {name, phone, aliases: aliases.split(",").map(value => value.trim()).filter(Boolean)}});
          resetContact(); setNotice("Contact saved. You can now use their name in a voice command.");
        });}}>
          <div className="field-row"><label>Name<input required maxLength={80} value={name} onChange={event => setName(event.target.value)} placeholder="e.g. Deva" autoComplete="off"/></label><label>WhatsApp number<input required value={phone} onChange={event => setPhone(event.target.value)} placeholder="+91 98765 43210" type="tel" autoComplete="off"/></label></div>
          <label>Other names <span className="optional">optional</span><input value={aliases} onChange={event => setAliases(event.target.value)} placeholder="e.g. Deva Kumar, brother"/></label>
          <div className="form-actions"><button className="primary-button" disabled={busy}><Icon name="plus" size={16}/>{editing ? "Save changes" : "Add contact"}</button>{editing && <button type="button" className="subtle-button" onClick={resetContact}>Cancel edit</button>}</div>
        </form>
        <div className="contact-list">{contacts.length ? contacts.map(contact => <div className="contact-row" key={contact.id}><span className="contact-avatar">{contact.name.slice(0, 1).toUpperCase()}</span><div><strong>{contact.name}</strong><span>+{contact.phone}</span>{contact.aliases.length > 0 && <small>{contact.aliases.join(" · ")}</small>}</div><button className="text-button" onClick={() => {setEditing(contact.id); setName(contact.name); setPhone("+" + contact.phone); setAliases(contact.aliases.join(", "));}}>Edit</button><button className="icon-button" aria-label={`Delete ${contact.name}`} disabled={busy} onClick={() => act(async () => {await api(`/api/contacts/${contact.id}`, {method:"DELETE"}); if (editing === contact.id) resetContact();})}><Icon name="trash" size={16}/></button></div>) : <div className="small-empty"><Icon name="users" size={28}/><p>Your contacts will appear here.</p></div>}</div>
      </>}
      {tab === "send" && <>
        <p className="section-intro">Write a message here, or say “Send a WhatsApp message to Deva saying I’ll be there at six.”</p>
        <form className="send-form" onSubmit={(event) => {event.preventDefault(); act(async () => {
          const key = JSON.stringify([recipient, message]);
          if (!sendId.current || sendId.current.key !== key) sendId.current = {key, id: crypto.randomUUID()};
          const result = await api("/api/whatsapp/send", {method:"POST", body:{recipient, message, request_id:sendId.current.id}});
          setNotice(result.response);
          if (result.confirmation) setPreview(result.confirmation);
          if (result.success) {setMessage(""); sendId.current = null;}
        });}}>
          <label>To<select aria-label="WhatsApp recipient" required value={recipient} onChange={event => setRecipient(event.target.value)}><option value="">Choose a saved contact</option>{contacts.map(contact => <option key={contact.id} value={contact.name}>{contact.name} · +{contact.phone}</option>)}</select></label>
          <label>Message<textarea required maxLength={4000} value={message} onChange={event => setMessage(event.target.value)} placeholder="What would you like to say?" rows={4}/></label>
          <div className="form-actions"><span className="character-count">{message.length}/4000</span><button className="primary-button" disabled={busy}><Icon name="send" size={16}/>{busy ? "Preparing…" : "Preview WhatsApp message"}</button></div>
          <p className="field-hint">Messages require your confirmation. Final sending takes place in WhatsApp.</p>
        </form>
        {preview && <MessagePreview key={preview.id} preview={preview} onComplete={result => {setNotice(result.response); setPreview(null); if (result.success) {setMessage(""); sendId.current = null;} void refresh().catch(() => {});}} onCancel={() => {setPreview(null); setNotice("Message preview cancelled. No message was sent."); sendId.current = null;}}/>}
      </>}
    </div>
  </dialog>;
}
