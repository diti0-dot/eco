import { useEffect, useState } from "react";
import { api } from "../api.js";
import { fmtDuration, GradeBadge } from "../ui.jsx";

export default function Search({ user }) {
  const [origins, setOrigins] = useState([]);
  const [destinations, setDestinations] = useState([]);
  const [originId, setOriginId] = useState("");
  const [destId, setDestId] = useState("");
  const [date, setDate] = useState("2027-01-30");
  const [plans, setPlans] = useState(null);
  const [savedIds, setSavedIds] = useState({}); // plan index -> journey id
  const [sentIds, setSentIds] = useState({});   // plan index -> true once sent
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.cities("origin"), api.cities("destination")])
      .then(([o, d]) => {
        setOrigins(o);
        setDestinations(d);
        setOriginId(o.find((c) => c.name === "Riga")?.id ?? o[0]?.id ?? "");
        setDestId(d.find((c) => c.name === "Madrid")?.id ?? d[0]?.id ?? "");
      })
      .catch((e) => setError(e.message));
  }, []);

  async function search(e) {
    e.preventDefault();
    setError("");
    try {
      const res = await api.search(originId, destId, date);
      setPlans(res.plans);
      setSavedIds({});
      setSentIds({});
    } catch (err) {
      setError(err.message);
    }
  }

  // Creates the journey once, then reuses it for later actions on the same plan.
  async function ensureJourney(i, plan) {
    if (savedIds[i]) return savedIds[i];
    const journey = await api.saveJourney({
      student_id: user.id,
      origin_city_id: Number(originId),
      destination_city_id: Number(destId),
      travel_date: date,
      legs: plan.legs.map((l) => ({ segment_id: l.segment_id })),
    });
    setSavedIds((prev) => ({ ...prev, [i]: journey.id }));
    return journey.id;
  }

  async function save(i, plan) {
    setError("");
    try {
      await ensureJourney(i, plan);
    } catch (err) {
      setError(err.message);
    }
  }

  async function unsave(i) {
    setError("");
    try {
      await api.deleteJourney(savedIds[i]);
      setSavedIds((prev) => {
        const next = { ...prev };
        delete next[i];
        return next;
      });
    } catch (err) {
      setError(err.message);
    }
  }

  async function sendPlan(i, plan) {
    setError("");
    try {
      const id = await ensureJourney(i, plan);
      await api.sendJourney(id);
      setSentIds((prev) => ({ ...prev, [i]: true }));
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="container">
      <h2>Book a green journey</h2>
      <form className="search card" onSubmit={search}>
        <label>From
          <select value={originId} onChange={(e) => setOriginId(e.target.value)}>
            {origins.map((c) => <option key={c.id} value={c.id}>{c.name}, {c.country}</option>)}
          </select>
        </label>
        <label>To
          <select value={destId} onChange={(e) => setDestId(e.target.value)}>
            {destinations.map((c) => <option key={c.id} value={c.id}>{c.name}, {c.country}</option>)}
          </select>
        </label>
        <label>Date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <button className="btn" type="submit">Search</button>
      </form>

      {error && <p className="error">{error}</p>}
      {plans && plans.length === 0 && <p className="muted">No routes found for this pair.</p>}

      {plans?.map((plan, i) => (
        <article className="card" key={i}>
          <div className="row">
            <strong>{plan.legs.length} leg{plan.legs.length > 1 ? "s" : ""}</strong>
            <GradeBadge grade={plan.green_grade} />
          </div>
          <ol className="legs">
            {plan.legs.map((l) => (
              <li key={l.segment_id}>
                <strong>{l.from} → {l.to}</strong> · {l.mode} · {l.provider.name}
                {" "}★ {l.provider.rating} ({l.provider.review_count} reviews)
                <div className="muted">
                  {fmtDuration(l.duration_min)} · €{l.price_eur} · {l.co2_kg} kg CO₂
                </div>
                <a href={l.booking_url} target="_blank" rel="noreferrer">Book on provider site</a>
              </li>
            ))}
          </ol>
          <p className="totals">
            Total: {fmtDuration(plan.total_duration_min)} · €{plan.total_price_eur} · {plan.total_co2_kg} kg CO₂
          </p>

          <div className="actions">
            {sentIds[i] ? (
              <span className="badge pending">Sent for review</span>
            ) : savedIds[i] ? (
              <>
                <span className="btn">Saved</span>
                <button className="btn-outline" onClick={() => unsave(i)}>Remove from saved</button>
              
                <button className="btn" onClick={() => sendPlan(i, plan)}>Send to university</button>
              </>
            ) : (
              <>
                <button className="btn-outline" onClick={() => save(i, plan)}>Save journey</button>
                <button className="btn" onClick={() => sendPlan(i, plan)}>Send to university</button>
              </>
            )}
          </div>
        </article>
      ))}
    </main>
  );
}