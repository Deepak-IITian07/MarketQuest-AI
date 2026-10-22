import StatusBadge from "../components/StatusBadge";

const features = [
  { title: "Explore", text: "Browse Indian stock data on a game-style dashboard." },
  { title: "Ask the Agent", text: "Get an AI-guided analysis with honest uncertainty." },
  { title: "Trade Virtually", text: "Start with ₹100,000 of virtual money. No real trades." },
];

export default function Landing() {
  return (
    <main className="page">
      <header className="hero">
        <p className="eyebrow">Hackathon build · Part 1 scaffold</p>
        <h1>MarketQuest AI</h1>
        <p className="tagline">Run the market. Risk nothing. Learn everything.</p>
        <StatusBadge />
      </header>
      <section className="cards">
        {features.map((f) => (
          <article key={f.title} className="card">
            <h2>{f.title}</h2>
            <p>{f.text}</p>
          </article>
        ))}
      </section>
      <footer className="note">Features above are planned. Only this page and the backend health check work today.</footer>
    </main>
  );
}
