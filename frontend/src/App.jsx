import { useState } from "react";
import { Routes, Route, Link, Navigate, useNavigate } from "react-router-dom";
import Home from "./pages/Home.jsx";
import Login from "./pages/Login.jsx";
import Search from "./pages/Search.jsx";
import StudentDashboard from "./pages/StudentDashboard.jsx";
import EditJourney from "./pages/EditJourney.jsx";
import UniversityDashboard from "./pages/UniversityDashboard.jsx";

export default function App() {
  const [user, setUser] = useState(() =>
    JSON.parse(localStorage.getItem("ecorasmus_user") || "null"));
  const navigate = useNavigate();

  function handleLogin(u) {
    localStorage.setItem("ecorasmus_user", JSON.stringify(u));
    setUser(u);
    navigate(u.role === "student" ? "/student" : "/university");
  }

  function logout() {
    localStorage.removeItem("ecorasmus_user");
    setUser(null);
    navigate("/");
  }

  return (
    <>
      <nav className="topbar">
        <Link to="/" className="brand">Ecorasmus</Link>
        <div>
          {user?.role === "student" && (
            <>
              <Link to="/student">My to-do</Link>
              <Link to="/search">Book journey</Link>
            </>
          )}
          {user?.role === "university" && <Link to="/university">Dashboard</Link>}
          {user ? (
            <button onClick={logout}>Log out</button>
          ) : (
            <Link to="/login" className="btn-light">Log in</Link>
          )}
        </div>
      </nav>

      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login onLogin={handleLogin} />} />
        <Route path="/search"
          element={user?.role === "student" ? <Search user={user} /> : <Navigate to="/login" />} />
        <Route path="/student"
          element={user?.role === "student" ? <StudentDashboard user={user} /> : <Navigate to="/login" />} />
        <Route path="/university"
          element={user?.role === "university" ? <UniversityDashboard user={user} /> : <Navigate to="/login" />} />
        <Route path="*" element={<Navigate to="/" />} />
        <Route path="/journeys/:id/edit"
          element={user?.role === "student" ? <EditJourney user={user} /> : <Navigate to="/login" />} />
      </Routes>
    </>
  );
}