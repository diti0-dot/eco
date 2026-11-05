import { Link } from "react-router-dom";

export default function Home() {
  return (
    <header className="banner">
      <h1>Ecorasmus</h1>
      <p>
        Ecorasmus helps Erasmus students plan greener trips across Europe by train and bus,
        get approval and funding from their university, upload travel proof, and share
        their experiences.
      </p>
      <Link to="/login" className="btn-light">Book a green journey</Link>
    </header>
  );
}