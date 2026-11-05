
import { fileUrl } from "./api.js";

export const DOC_TYPES = [
  ["ticket", "Ticket"],
  ["boarding_pass", "Boarding pass"],
  ["stamped_ticket", "Stamped ticket"],
  ["other", "Other proof"],
];

const LABELS = {
  just_saved: "Saved",
  sent_to_uni: "Sent",
  pending: "Pending review",
  approved: "Approved",
  rejected: "Rejected",
  need_edits: "Changes requested",
  open: "Open",
  awaiting_response: "Awaiting response",
  no_response_required: "No response required",
  closed: "Closed",
};

export function fmtDuration(min) {
  const h = Math.floor(min / 60);
  const m = min % 60;
  return m ? `${h}h ${m}m` : `${h}h`;
}

export function StatusBadge({ status }) {
  return <span className={`badge ${status}`}>{LABELS[status] || status}</span>;
}
export function fmtWhen(value) {
  return new Date(value).toLocaleString("en-GB", {
    day: "numeric", month: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export function LegLine({ leg }) {
  const arrival = leg.arrival_at ?? new Date(new Date(leg.departure_at).getTime() + leg.duration_min * 60000);
  return (
    <div>
      <strong>{leg.from} → {leg.to}</strong> · {leg.mode} · {leg.provider.name}
      {leg.provider.rating != null && (
        <> ★ {leg.provider.rating} ({leg.provider.review_count} reviews)</>
      )}
      {leg.departure_at && (
        <div>{fmtWhen(leg.departure_at)} → {fmtWhen(arrival)}</div>
      )}
      <div className="muted">
        {fmtDuration(leg.duration_min)} · €{leg.price_eur} · {leg.co2_kg} kg CO₂
      </div>
    </div>
  );
}

export function GradeBadge({ grade }) {
  return <span className={`grade grade-${grade}`} title="Green score">{grade}</span>;
}

export function Docs({ docs, onRemove }) {
  if (!docs?.length) return null;
  return (
    <ul className="docs">
      {docs.map((d) => (
        <li key={d.id} className="doc-row">
          📎 {d.doc_type.replace("_", " ")}: {d.file_name}
          {d.has_file && (
            <a href={fileUrl(d.id)} target="_blank" rel="noreferrer"
              className="icon-btn" title="View file" aria-label="View file">👁</a>
          )}
          {onRemove && (
            <button className="icon-btn" title="Remove file" aria-label="Remove file"
              onClick={() => onRemove(d.id)}>✖</button>
          )}
        </li>
      ))}
    </ul>
  );
}