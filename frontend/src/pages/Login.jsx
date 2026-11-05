import { useState } from "react";
import { api } from "../api.js";

const DEMO_EMAILS = {
  student: "dn24002@edu.lu.lv",
  university: "erasmus_lu@ecorasmus.eu",
};

export default function Login({ onLogin }) {
  const [role, setRole] = useState("student");
  const [email, setEmail] = useState(DEMO_EMAILS.student);
  const [error, setError] = useState("");

  function switchRole(next) {
    setRole(next);
    setEmail(DEMO_EMAILS[next]);
    setError("");
  }

  async function submit(e) {
    e.preventDefault();
    try {
      const user = await api.login(email.trim());
      if (user.role !== role) {
        setError(`That is a ${user.role} account. Switch roles to continue.`);
        return;
      }
      onLogin(user);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <main className="container narrow">
      <h2>Log in</h2>
      <div className="tabs">
        <button type="button" className={role === "student" ? "btn" : "btn-outline"}
          onClick={() => switchRole("student")}>Student</button>
        <button type="button" className={role === "university" ? "btn" : "btn-outline"}
          onClick={() => switchRole("university")}>University admin</button>
      </div>
      <form onSubmit={submit} className="card">
        <label>
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn" type="submit">Log in</button>
        <p className="muted">Demo emails are filled in. Students use their university .edu email.</p>
      </form>
    </main>
  );
}