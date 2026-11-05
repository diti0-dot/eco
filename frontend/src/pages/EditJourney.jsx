import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api.js";
import { LegLine } from "../ui.jsx";

// Converts a leg (from the saved journey or a new one) into the body the API expects.
function toBody(l) {
  return {
    segment_id: l.segment_id ?? null,
    from_city_id: l.from_city_id,
    to_city_id: l.to_city_id,
    mode: l.mode,
    provider_id: l.provider_id ?? null,
    provider_name: l.provider?.name ?? null,
    duration_min: l.duration_min,
    price_eur: l.price_eur,
    co2_kg: l.co2_kg,
    distance_km: l.distance_km ?? 0,
    departure_at: l.departure_at,
    note: l.note ?? null,
  };
}

export default function EditJourney({ user }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const [journey, setJourney] = useState(null);
  const [cities, setCities] = useState([]);
  const [legs, setLegs] = useState([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    Promise.all([api.journey(id), api.allCities()])
      .then(([j, c]) => {
        setJourney(j);
        setLegs(j.legs);
        setCities(c);
      })
      .catch((e) => setError(e.message));
  }, [id]);

  function move(i, dir) {
    const next = [...legs];
    const target = i + dir;
    if (target < 0 || target >= next.length) return;
    [next[i], next[target]] = [next[target], next[i]];
    setLegs(next);
  }

  function remove(i) {
    setLegs(legs.filter((_, k) => k !== i));
  }

  async function saveAndSend() {
    setSaving(true);
    setError("");
    try {
      await api.updateJourney(id, {
        student_id: user.id,
        origin_city_id: journey.origin_city_id,
        destination_city_id: journey.destination_city_id,
        travel_date: journey.travel_date,
        notes: journey.notes,
        legs: legs.map(toBody),
      });
      await api.sendJourney(id);
      navigate("/student");
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  if (!journey) return <main className="container">{error || "Loading…"}</main>;

  return (
    <main className="container">
      <h2>Edit journey: {journey.origin} → {journey.destination}</h2>
      <p className="muted">Travel date {journey.travel_date}</p>

      {legs.map((leg, i) => (
        <article className="card" key={i}>
          <LegLine leg={leg} />
          <div className="actions">
            <button className="btn-outline" onClick={() => move(i, -1)} disabled={i === 0}>↑ Up</button>
            <button className="btn-outline" onClick={() => move(i, 1)} disabled={i === legs.length - 1}>↓ Down</button>
            <button className="btn-outline" onClick={() => remove(i)}>Delete</button>
          </div>
        </article>
      ))}

      <AddLegForm cities={cities} onAdd={(leg) => setLegs([...legs, leg])} />

      {error && <p className="error">{error}</p>}
      <button className="btn" disabled={saving || legs.length === 0} onClick={saveAndSend}>
        Save and send to university
      </button>
    </main>
  );
}

function AddLegForm({ cities, onAdd }) {
  const blank = {
    from_city_id: "", to_city_id: "", mode: "train", provider_id: "",
    departure_at: "", duration_min: "", price_eur: "", co2_kg: "",
  };
  const [f, setF] = useState(blank);
  const [providers, setProviders] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    api.providers(f.mode)
      .then(setProviders)
      .catch((e) => setError(e.message));
  }, [f.mode]);

  const set = (key) => (e) => setF({ ...f, [key]: e.target.value });

  function changeMode(e) {
    setF({ ...f, mode: e.target.value, provider_id: "" }); // providers depend on the mode
  }

  function add() {
    if (Object.values(f).some((v) => v === "")) return setError("Fill in every field");
    if (f.from_city_id === f.to_city_id) return setError("Origin and destination must differ");
    const from = cities.find((c) => c.id === Number(f.from_city_id));
    const to = cities.find((c) => c.id === Number(f.to_city_id));
    const provider = providers.find((p) => p.id === Number(f.provider_id));
    onAdd({
      segment_id: null,
      from_city_id: Number(f.from_city_id),
      to_city_id: Number(f.to_city_id),
      mode: f.mode,
      provider_id: Number(f.provider_id),
      departure_at: f.departure_at,
      duration_min: Number(f.duration_min),
      price_eur: Number(f.price_eur),
      co2_kg: Number(f.co2_kg),
      distance_km: 0,
      note: null,
      // Display fields, so the new leg looks like the others
      from: from.name,
      to: to.name,
      provider: { name: provider.name, rating: provider.rating, review_count: provider.review_count },
    });
    setF(blank);
    setError("");
  }

  return (
    <section className="card">
      <h3>Add a leg</h3>
      <div className="row">
        <select value={f.from_city_id} onChange={set("from_city_id")}>
          <option value="">From</option>
          {cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select value={f.to_city_id} onChange={set("to_city_id")}>
          <option value="">To</option>
          {cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
        <select value={f.mode} onChange={changeMode}>
          <option value="train">Train</option>
          <option value="bus">Bus</option>
        </select>
        <select value={f.provider_id} onChange={set("provider_id")}>
          <option value="">Provider</option>
          {providers.map((p) => <option key={p.id} value={p.id}>{p.name} ★ {p.rating}</option>)}
        </select>
      </div>
      <div className="row">
        <label>Departure
          <input type="datetime-local" value={f.departure_at} onChange={set("departure_at")} />
        </label>
        <label>Duration (min)
          <input type="number" min="1" value={f.duration_min} onChange={set("duration_min")} />
        </label>
        <label>Price (€)
          <input type="number" min="0" step="0.01" value={f.price_eur} onChange={set("price_eur")} />
        </label>
        <label>CO₂ (kg)
          <input type="number" min="0" step="0.1" value={f.co2_kg} onChange={set("co2_kg")} />
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      <button className="btn-outline" onClick={add}>Add leg</button>
    </section>
  );
}