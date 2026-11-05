import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, resourceFileUrl, submissionFileUrl, uploadReportFile } from "../api.js";
import { DOC_TYPES, Docs, fmtDuration, GradeBadge, StatusBadge,LegLine } from "../ui.jsx";

export default function StudentDashboard({ user }) {
  const [todo, setTodo] = useState([]);
  const [saved, setSaved] = useState([]);
  const [sent, setSent] = useState([]);
  const [resources, setResources] = useState([]);
  const [error, setError] = useState("");
  
  const load = useCallback(async () => {
    try {
      const [t, j, s, r] = await Promise.all([
        api.todo(user.id),
        api.studentJourneys(user.id),
        api.studentSent(user.id),
        api.studentResources(user.id),
      ]);
      setTodo(t);
      setSaved(j.filter((x) => x.status === "just_saved"));
      setSent(s);
      setResources(r);
    } catch (e) {
      setError(e.message);
    }
  }, [user.id]);

  useEffect(() => { load(); }, [load]);

  async function sendSaved(id) {
    setError("");
    try {
      await api.sendJourney(id);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  async function removeSaved(id) {
    setError("");
    try {
      await api.deleteJourney(id);
      load();
    } catch (e) {
      setError(e.message);
    }
  }

  const journeyRequests = sent.filter((s) => s.stage === "journey");
  const grantReports = sent.filter((s) => s.stage === "grant");
  const approved = journeyRequests.find((s) => s.status === "approved");
  const latestGrant = grantReports[0];
  const canReport = approved && !latestGrant;

  return (
    <main className="container">
      <h2>Hi, {user.username}</h2>
      {error && <p className="error">{error}</p>}

      <section className="card">
        <h3>To-do</h3>
        <ul className="todo">
          {todo.map((t) => (
            <li key={t.key} className={t.done ? "done" : t.locked ? "locked" : ""}>
              {t.done ? "✅" : t.locked ? "🔒" : "⬜"} {t.label}
            </li>
          ))}
        </ul>
      </section>

       <section className="card">
        <h3>Saved journeys</h3>
        {saved.length === 0 && (
          <p className="muted">No saved journeys. <Link to="/search">Search for one</Link>.</p>
        )}
        {saved.map((j) => (
          <div className="row" key={j.id}>
            <span>
              {j.origin} → {j.destination} · {j.travel_date} · €{j.total_price_eur} · {j.total_co2_kg} kg CO₂ · {fmtDuration(j.total_duration_min)}
            </span>
            
            <button className="btn" onClick={() => sendSaved(j.id)}>Send to university</button>
            <button className="btn-outline" onClick={() => removeSaved(j.id)}>Remove</button>

          </div>
        ))}
      </section>

      <section className="card">
        <h3>Journey requests</h3>
        {journeyRequests.length === 0 && <p className="muted">Nothing sent yet.</p>}
        {journeyRequests.map((s) => (
          <JourneyRequest key={s.id} sj={s} onChange={load} />
        ))}
      </section>

      <section className="card">
        <h3>Sign required documents</h3>
        {resources.length === 0 && <p className="muted">Nothing to sign yet.</p>}
        {resources.map((r) => (
          <SignRow key={r.id} r={r} userId={user.id} onDone={load} />
        ))}
      </section>

      {canReport && <FinalReport sj={approved} onDone={load} />}

      {grantReports.length > 0 && (
        <section className="card">
          <h3>Grant reports</h3>
          {grantReports.map((g) => <GrantReport key={g.id} g={g} onChange={load} />)}
        </section>
      )}
    </main>
  );
}

function SignRow({ r, userId, onDone }) {
  const [name, setName] = useState("");
  const [agree, setAgree] = useState(false);
  const [error, setError] = useState("");

  async function sign() {
    if (!r.submission) return setError("Upload the signed document first");
    if (!name.trim()) return setError("Type your full name");
    if (!agree) return setError("Tick “I agree” first");
    setError("");
    try {
      await api.sign(userId, r.id, name.trim());
      onDone();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="request">
      <div className="row">
        <strong>{r.title}</strong>
        <span className="muted">{r.file_name}{r.required ? " · required" : ""}</span>
        {r.has_file && (
          <>
            <a href={resourceFileUrl(r.id)} target="_blank" rel="noreferrer"
              className="icon-btn" title="View document" aria-label="View document">👁 View</a>
            <a href={resourceFileUrl(r.id, true)} className="icon-btn"
              title="Download document" aria-label="Download document">⬇ Download</a>
          </>
        )}
      </div>

      <p className="muted"><strong>Step 1:</strong> Upload the filled and signed copy.</p>
      <SubmissionRow r={r} userId={userId} onDone={onDone} />

      <p className="muted"><strong>Step 2:</strong> Type your name, tick “I agree,” and sign to send it to your university.</p>
      {r.signed_at ? (
        <p className="ok">✅ Signed and sent to the university {new Date(r.signed_at).toLocaleDateString()}</p>
      ) : (
        <div className="row">
          <input placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />
          <label className="check">
            <input type="checkbox" checked={agree} onChange={(e) => setAgree(e.target.checked)} />
            I agree
          </label>
          <button className="btn" disabled={!r.submission} onClick={sign}>Sign and send</button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function SubmissionRow({ r, userId, onDone }) {
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);
  const locked = Boolean(r.signed_at);

  async function upload() {
    if (!file) return setError("Choose a file first");
    setBusy(true);
    setError("");
    try {
      await api.uploadSubmission(userId, r.id, file);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="submission">
      {r.submission && (
        <div className="doc-row">
          📎 {r.submission.file_name} · uploaded {new Date(r.submission.uploaded_at).toLocaleDateString()}
          <a href={submissionFileUrl(userId, r.id)} target="_blank" rel="noreferrer"
            className="icon-btn" title="View file" aria-label="View file">👁</a>
        </div>
      )}

      {!locked && (
        <div className="row">
          <input ref={inputRef} type="file" accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
            onChange={(e) => setFile(e.target.files[0] ?? null)} />
          <button className="btn-outline" disabled={!file || busy} onClick={upload}>
            {busy ? "Uploading…" : r.submission ? "Replace file" : "Upload"}
          </button>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}


function JourneyRequest({ sj, onChange }) {
  const [error, setError] = useState("");

  async function resend() {
    setError("");
    try {
      await api.sendJourney(sj.journey_id);
      onChange();
    } catch (e) {
      setError(e.message);
    }
  }

  async function removeDoc(docId) {
    if (!window.confirm("Remove this file?")) return;
    setError("");
    try {
      await api.deleteDocument(docId);
      onChange();
    } catch (e) {
      setError(e.message);
    }
  }

  const j = sj.journey;
  return (
    <div className="request">
      <div className="row">
        <strong>{j.origin} → {j.destination}</strong>
        <span className="muted">{j.travel_date}</span>
        <GradeBadge grade={j.green_grade} />
        <StatusBadge status={sj.status} />
      </div>

      {sj.university_notes && <p className="note">University note: {sj.university_notes}</p>}
      {sj.status === "approved" && (
        <p className="ok">Approved. Extra travel days: {sj.extra_travel_days}</p>
      )}
      {sj.status === "rejected" && (
        <p className="error">
          Not approved. <Link to="/search">Search for another route</Link>.
        </p>
      )}
      {sj.status === "need_edits" && (
        <div className="actions">
          <Link className="btn" to={`/journeys/${sj.journey_id}/edit`}>Edit plan</Link>
          <Link className="btn-outline" to="/search">Search for another route</Link>
        </div>
        
      )}
      {error && <p className="error">{error}</p>}

      <ol className="legs">
        {j.legs.map((leg) => (
          <li key={leg.leg_id}>
            <LegLine leg={leg} />
            {/* <strong>{leg.from} → {leg.to}</strong> · {leg.mode} · {leg.provider.name}
            <div className="muted">
              {fmtDuration(leg.duration_min)} · €{leg.price_eur} · {leg.co2_kg} kg CO₂
            </div> */}
            {sj.status === "approved" && (
              <>
                <a href={leg.booking_url} target="_blank" rel="noreferrer">Book on provider site</a>
                <Docs docs={leg.documents} onRemove={removeDoc} />
                <LegUpload legId={leg.leg_id} onUploaded={onChange} />
              </>
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

function LegUpload({ legId, onUploaded }) {
  const [docType, setDocType] = useState("ticket");
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef(null);

  async function upload() {
    if (!file) return setError("Choose a file first");
    setBusy(true);
    setError("");
    try {
      await api.uploadFile(legId, docType, file);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onUploaded();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="row">
      <select value={docType} onChange={(e) => setDocType(e.target.value)}>
        {DOC_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.jpg,.jpeg,.png"
        onChange={(e) => setFile(e.target.files[0] ?? null)}
      />
      <button className="btn-outline" disabled={!file || busy} onClick={upload}>
        {busy ? "Uploading…" : "Upload"}
      </button>
      {error && <span className="error">{error}</span>}
    </div>
  );
}

function FinalReport({ sj, onDone }) {
  const [summary, setSummary] = useState("");
  const [extraName, setExtraName] = useState("");
  const [extraType, setExtraType] = useState("other");
  const [error, setError] = useState("");

  async function submit() {
    if (!summary.trim()) return setError("Write a short summary");
    try {
      await api.submitReport(sj.id, {
        summary: summary.trim(),
        extra_docs: extraName.trim()
          ? [{ doc_type: extraType, file_name: extraName.trim() }]
          : [],
      });
      onDone();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <section className="card">
      <h3>Final report</h3>
      <p className="muted">
        Includes every leg, the tickets and proof you uploaded, and any extra document below.
      </p>
      <label>
        Summary
        <textarea rows={4} value={summary} onChange={(e) => setSummary(e.target.value)} />
      </label>
      <div className="row">
        <input placeholder="Extra document file name" value={extraName}
          onChange={(e) => setExtraName(e.target.value)} />
        <select value={extraType} onChange={(e) => setExtraType(e.target.value)}>
          {DOC_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
      </div>
      {error && <p className="error">{error}</p>}
      <button className="btn" onClick={submit}>Submit final report</button>
    </section>
  );
}

function GrantReport({ g, onChange }) {
  const [summary, setSummary] = useState(g.student_summary ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const editable = g.status === "need_edits";
  const dirty = summary.trim() !== (g.student_summary ?? "").trim();
  const canSend = editable && (g.changes?.has_changes || dirty) && !busy;

  async function resend() {
    setBusy(true);
    setError("");
    try {
      await api.resubmitReport(g.id, summary.trim());
      onChange();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function removeDoc(docId) {
    if (!window.confirm("Remove this file?")) return;
    setError("");
    try {
      await api.deleteDocument(docId);
      onChange();
    } catch (e) {
      setError(e.message);
    }
  }

  return (
    <div className="request">
      <div className="row">
        <strong>Report from {new Date(g.created_at).toLocaleDateString()}</strong>
        <StatusBadge status={g.status} />
      </div>
      {g.university_notes && <p className="note">University note: {g.university_notes}</p>}
      {g.status === "approved" && <p className="ok">Approved. You keep the green travel grant.</p>}
      {g.status === "rejected" && (
        <p className="error">Repay €{g.repayment_amount_eur} by {g.repayment_deadline}.</p>
      )}
      {g.status === "pending" && <p className="muted">Sent. Waiting for the university.</p>}

      {editable && (
        <>
          <label>
            Summary
            <textarea rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />
          </label>

          <p className="muted"><strong>Journey documents</strong> (add these per segment above)</p>
          {g.journey.legs.map((leg) => (
            <div key={leg.leg_id}>
              <p className="muted">{leg.from} → {leg.to}</p>
              <Docs docs={leg.documents} onRemove={removeDoc} />
            </div>
          ))}

          <p className="muted"><strong>Report documents</strong></p>
          <Docs docs={g.extra_documents} onRemove={removeDoc} />
          <ReportUpload sjId={g.id} onUploaded={onChange} />

          <p className="muted">
            {g.changes?.has_changes
              ? `Changes since last send: ${g.changes.added_docs} added, ${g.changes.removed_docs} removed${g.changes.summary_changed ? ", summary edited" : ""}.`
              : "No changes since the last send yet."}
          </p>
          <button className="btn" disabled={!canSend} onClick={resend}>
            {busy ? "Sending…" : "Send again"}
          </button>
        </>
      )}
      {error && <p className="error">{error}</p>}
    </div>
  );
}

function ReportUpload({ sjId, onUploaded }) {
  const [docType, setDocType] = useState("other");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  async function upload() {
    if (!file) return setError("Choose a file first");
    setBusy(true);
    setError("");
    try {
      await uploadReportFile(sjId, docType, file);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onUploaded();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="row">
      <select value={docType} onChange={(e) => setDocType(e.target.value)}>
        {DOC_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
      <input ref={inputRef} type="file" accept=".pdf,.jpg,.jpeg,.png"
        onChange={(e) => setFile(e.target.files[0] ?? null)} />
      <button className="btn-outline" disabled={!file || busy} onClick={upload}>
        {busy ? "Uploading…" : "Add document"}
      </button>
      {error && <span className="error">{error}</span>}
    </div>
  );
}