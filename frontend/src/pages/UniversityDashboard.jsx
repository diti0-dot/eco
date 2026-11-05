import { useCallback, useEffect, useState, useRef} from "react";
import { api, submissionFileUrl,resourceFileUrl } from "../api.js";
import { Docs, fmtDuration, GradeBadge, LegLine, StatusBadge } from "../ui.jsx";

const FILTERS = [
  ["all", "All"],
  ["open", "Open"],
  ["awaiting_response", "Awaiting response"],
  ["no_response_required", "No response required"],
  ["closed", "Closed"],
];

const DECISIONS = [
  ["approved", "Approve"],
  ["rejected", "Reject"],
  ["need_edits", "Request changes"],
];

export default function UniversityDashboard({ user }) {
  const [tickets, setTickets] = useState([]);
  const [resources, setResources] = useState([]);
  const [filter, setFilter] = useState("all");
  const [selectedId, setSelectedId] = useState(null);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState("");

  const refresh = useCallback(() => setVersion((v) => v + 1), []);

  useEffect(() => {
    Promise.all([api.uniTickets(user.id), api.uniResources(user.university_id)])
      .then(([t, r]) => {
        setTickets(t);
        setResources(r);
      })
      .catch((e) => setError(e.message));
  }, [user.id, user.university_id, version]);

  const counts = (status) => tickets.filter((t) => t.status === status).length;
  const visible = filter === "all" ? tickets : tickets.filter((t) => t.status === filter);

  return (
    <main className="container">
      <h2>{user.username}</h2>

      <div className="filters">
        {FILTERS.map(([value, label]) => (
          <button key={value} className={filter === value ? "btn" : "btn-outline"}
            onClick={() => setFilter(value)}>
            {label}{value !== "all" && ` (${counts(value)})`}
          </button>
        ))}
      </div>

      {error && <p className="error">{error}</p>}
      <TicketTable tickets={visible} selectedId={selectedId}
        onSelect={(id) => setSelectedId(id === selectedId ? null : id)} />

      {selectedId && <TicketDetail id={selectedId} version={version} onChange={refresh} />}

      <ResourceManager userId={user.id} resources={resources} onDone={refresh} />
    </main>
  );
}

function TicketTable({ tickets, selectedId, onSelect }) {
  if (tickets.length === 0) return <p className="muted">No tickets here.</p>;
  return (
    <div className="card table-wrap">
      <table className="tickets">
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Student</th>
            <th>Destination</th>
            <th>Journey request</th>
            <th>Report</th>
            <th>Signed documents</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.id} className={t.id === selectedId ? "selected" : ""}>
              <td><strong>{t.ticket_code}</strong></td>
              <td>
                {t.student}
                <div className="muted">{t.email}</div>
              </td>
              <td>{t.destination}</td>
              <td>
                {t.journey ? (
                  <>
                    <StatusBadge status={t.journey.status} />
                    <div className="muted">{t.journey.travel_date}</div>
                    {t.proof_count > 0 && (
                      <div className="muted">📎 {t.proof_count} journey file{t.proof_count > 1 ? "s" : ""}</div>
                    )}
                  </>
                ) : <span className="muted">None</span>}
              </td>
              <td>
                {t.report ? <StatusBadge status={t.report.status} /> : <span className="muted">Not sent</span>}
              </td>
              <td><SignedDocs t={t} /></td>
              <td><StatusBadge status={t.status} /></td>
              <td>
                <button className="btn-outline" onClick={() => onSelect(t.id)}>
                  {t.id === selectedId ? "Close" : "Review"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SignedDocs({ t }) {
  if (t.signed_documents.length === 0) return <span className="muted">None signed yet</span>;
  return (
    <ul className="docs">
      {t.signed_documents.map((d) => (
        <li key={d.resource_id}>
          ✅ {d.title}{" "}
          <a href={submissionFileUrl(t.student_id, d.resource_id)} target="_blank" rel="noreferrer">view</a>
          {" · "}
          <a href={submissionFileUrl(t.student_id, d.resource_id, true)}>download</a>
        </li>
      ))}
    </ul>
  );
}

function TicketDetail({ id, version, onChange }) {
  const [t, setT] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setError("");
    api.ticket(id)
      .then(setT)
      .catch((e) => setError(e.message));
  }, [id, version]);

  if (error) return <p className="error">{error}</p>;
  if (!t) return <p className="muted">Loading…</p>;

  return (
    <section className="card">
      <h3>{t.ticket_code} · {t.student} → {t.destination}</h3>
      {t.journey_request && (
        <ReviewCard key={`j-${t.journey_request.id}-${t.journey_request.status}`}
          r={t.journey_request} stage="journey" onDone={onChange} />
      )}
      {t.grant_report && (
        <ReviewCard key={`g-${t.grant_report.id}-${t.grant_report.status}`}
          r={t.grant_report} stage="grant" onDone={onChange} />
      )}
      {!t.journey_request && !t.grant_report && <p className="muted">Nothing sent yet.</p>}
    </section>
  );
}

function ReviewCard({ r, stage, onDone }) {
  const [decision, setDecision] = useState("approved");
  const [notes, setNotes] = useState("");
  const [extraDays, setExtraDays] = useState(0);
  const [amount, setAmount] = useState("");
  const [deadline, setDeadline] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    const body = { decision, notes: notes.trim() || null };
    if (stage === "journey" && decision === "approved") {
      body.extra_travel_days = Number(extraDays) || 0;
    }
    if (stage === "grant" && decision === "rejected") {
      body.repayment_amount_eur = amount ? Number(amount) : null;
      body.repayment_deadline = deadline || null;
    }
    setBusy(true);
    setError("");
    try {
      await api.review(r.id, body);
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const j = r.journey;
  const pending = r.status === "pending";
  const totalDays = Math.max(1, Math.ceil(j.total_duration_min / 1440));

  return (
    <article className="request">
      <div className="row">
        <strong>{stage === "journey" ? "Journey request" : "Grant report"}</strong>
        <span>{j.origin} → {j.destination} · {j.travel_date}</span>
        <GradeBadge grade={j.green_grade} />
        <StatusBadge status={r.status} />
      </div>

      {r.student_summary && <p className="note">Student summary: {r.student_summary}</p>}

      {r.changes?.has_changes && (
        <p className="muted">
          Changes since last send: {r.changes.added_docs} added, {r.changes.removed_docs} removed
          {r.changes.summary_changed ? ", summary edited" : ""}.
        </p>
      )}

      <ol className="legs">
        {j.legs.map((leg) => (
          <li key={leg.leg_id}>
            <LegLine leg={leg} />
            <Docs docs={leg.documents} />
          </li>
        ))}
      </ol>

      <p className="totals">
        Total: €{j.total_price_eur} · {totalDays} day{totalDays > 1 ? "s" : ""} of travel
        ({fmtDuration(j.total_duration_min)} on the road)
        {r.extra_travel_days != null && r.status === "approved" && (
          <> · {r.extra_travel_days} extra day{r.extra_travel_days === 1 ? "" : "s"} approved</>
        )}
      </p>

      {r.extra_documents?.length > 0 && (
        <>
          <p className="muted">Extra documents</p>
          <Docs docs={r.extra_documents} />
        </>
      )}

      {pending ? (
        <>
          <div className="actions">
            {DECISIONS.map(([v, l]) => (
              <button key={v} className={decision === v ? "btn" : "btn-outline"}
                onClick={() => setDecision(v)}>{l}</button>
            ))}
          </div>

          {stage === "journey" && decision === "approved" && (
            <label>
              Extra travel days approved
              <input type="number" min="0" value={extraDays}
                onChange={(e) => setExtraDays(e.target.value)} />
            </label>
          )}

          {stage === "grant" && decision === "rejected" && (
            <div className="row">
              <input placeholder="Repayment €" value={amount}
                onChange={(e) => setAmount(e.target.value)} />
              <input type="date" value={deadline} onChange={(e) => setDeadline(e.target.value)} />
            </div>
          )}

          <textarea rows={2} placeholder="Note to student" value={notes}
            onChange={(e) => setNotes(e.target.value)} />
          {error && <p className="error">{error}</p>}
          <button className="btn" disabled={busy} onClick={submit}>Send decision</button>
        </>
      ) : (
        <>
          {r.university_notes && <p className="note">Your note: {r.university_notes}</p>}
          {stage === "grant" && r.status === "rejected" && (
            <p className="error">Repayment €{r.repayment_amount_eur} by {r.repayment_deadline}.</p>
          )}
        </>
      )}
    </article>
  );
}

function ResourceManager({ userId, resources, onDone }) {
  const [title, setTitle] = useState("");
  const [type, setType] = useState("agreement");
  const [file, setFile] = useState(null);
  const [required, setRequired] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const inputRef = useRef(null);

  async function add() {
    if (!title.trim()) return setError("Enter a title");
    if (!file) return setError("Choose a file");
    setBusy(true);
    setError("");
    try {
      await api.uploadResourceFile(userId, { title: title.trim(), type, required, file });
      setTitle("");
      setFile(null);
      setRequired(true);
      if (inputRef.current) inputRef.current.value = "";
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card">
      <h3>Resources for students</h3>
      <p className="muted">
        Shown in "Sign required documents" for students whose home university is this one.
        Deleting a document that students have signed archives it instead. Replacing a document
        means students who signed the old version must sign the new one.
      </p>

      {resources.length === 0 && <p className="muted">No resources yet.</p>}
      <ul className="docs">
        {resources.map((r) => (
          <ResourceRow key={r.id} r={r} userId={userId} onDone={onDone} />
        ))}
      </ul>

      <h4>Add a resource</h4>
      <div className="row">
        <input placeholder="Title, e.g. Green Travel Grant Agreement" value={title}
          onChange={(e) => setTitle(e.target.value)} />
        <select value={type} onChange={(e) => setType(e.target.value)}>
          <option value="agreement">Agreement</option>
          <option value="requirements">Requirements</option>
          <option value="other">Other</option>
        </select>
        <label className="check">
          <input type="checkbox" checked={required} onChange={(e) => setRequired(e.target.checked)} />
          Required
        </label>
      </div>
      <div className="row">
        <input ref={inputRef} type="file" accept=".pdf,.doc,.docx"
          onChange={(e) => setFile(e.target.files[0] ?? null)} />
        <button className="btn" disabled={!file || !title.trim() || busy} onClick={add}>
          {busy ? "Uploading…" : "Upload resource"}
        </button>
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

function ResourceRow({ r, userId, onDone }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function replace(e) {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;
    if (!window.confirm(`Replace "${r.title}"? Students who signed it will need to sign the new version.`)) return;
    setBusy(true);
    setError("");
    try {
      await api.replaceResource(userId, r.id, file);
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!window.confirm(`Delete "${r.title}"?`)) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.deleteResource(userId, r.id);
      if (res.result === "archived") window.alert(res.message);
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="request">
      <div className="doc-row">
        <strong>{r.title}</strong> ({r.type}){r.required ? " · required" : ""}
        {r.has_file && (
          <a href={resourceFileUrl(r.id)} target="_blank" rel="noreferrer"
            className="icon-btn" title="View file" aria-label="View file">👁</a>
        )}
        <label className="icon-btn" title="Replace file">
          ↻ Replace
          <input type="file" hidden accept=".pdf,.doc,.docx" onChange={replace} disabled={busy} />
        </label>
        <button className="icon-btn" title="Delete" aria-label="Delete" disabled={busy} onClick={remove}>✖</button>
      </div>
      {error && <p className="error">{error}</p>}
    </li>
  );
}