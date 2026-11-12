import React, {useEffect, useRef, useState} from "react";
import {api} from "../api.js";

export default function RemindersPanel({open, onClose, reminders, refresh}) {
  const dialog = useRef(null);
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notification, setNotification] = useState("");
  useEffect(() => {if (open && !dialog.current.open) dialog.current.showModal(); else if (!open) dialog.current.close();}, [open]);
  const act = async operation => {
    if (busy) return;
    setBusy(true); setError("");
    try {await operation(); await refresh();}
    catch (failure) {setError(failure.message);}
    finally {setBusy(false);}
  };
  return <dialog ref={dialog} className="whatsapp-dialog" aria-labelledby="reminders-title" onCancel={event => {event.preventDefault(); onClose();}}>
    <div className="dialog-heading"><div><h2 id="reminders-title">A little reminder.</h2><p>Timers, alarms, and things to remember.</p></div><button className="icon-button close-dialog" onClick={onClose} aria-label="Close reminders">×</button></div>
    {error && <p role="alert" className="form-notice is-error">{error}</p>}
    <div className="panel-content">
      <form className="contact-form" onSubmit={event => {event.preventDefault(); void act(async () => {await api("/api/reminders", {method:"POST", body:{title, due_at:new Date(due).toISOString()}}); setTitle(""); setDue("");});}}>
        <label>Reminder<input value={title} onChange={event => setTitle(event.target.value)} maxLength={250} required placeholder="Call Deva"/></label>
        <label>When<input type="datetime-local" value={due} onChange={event => setDue(event.target.value)} required/></label>
        <button className="primary-button" disabled={busy}>Save reminder</button>
      </form>
      <p className="field-hint">Keep Indu running to receive reminders on time. After sleep or shutdown, missed reminders appear on the next launch. Times use your computer's clock.</p>
      <button className="subtle-button" onClick={async () => {if (!("Notification" in window)) {setNotification("This browser does not support desktop notifications."); return;} setNotification(`Desktop notifications: ${await Notification.requestPermission()}`);}}>Enable desktop notifications</button>
      {notification && <p role="status">{notification}</p>}
      <div className="contact-list">{reminders.filter(row => ["scheduled", "due"].includes(row.status)).map(row => <div className="contact-row" key={row.id}><div><strong>{row.title}</strong><span>{new Date(row.due_at).toLocaleString()} · {row.status === "due" ? "Due now" : "Scheduled"}</span></div><button className="subtle-button" disabled={busy} onClick={() => void act(() => api(`/api/reminders/${row.id}/${row.status === "due" ? "dismiss" : "cancel"}`, {method:"POST"}))}>{row.status === "due" ? "Dismiss" : "Cancel"}</button></div>)}</div>
      {!reminders.some(row => ["scheduled", "due"].includes(row.status)) && <p className="section-intro">No active reminders. Try saying “Set a timer for ten minutes” using a number, such as 10.</p>}
    </div>
  </dialog>;
}
