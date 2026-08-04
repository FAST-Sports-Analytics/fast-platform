import Image from "next/image";

const products = [
  {
    number: "01",
    name: "FAST Analysis",
    label: "Analyse",
    description:
      "Code live matches, analyse video and turn every key moment into structured, searchable intelligence.",
    points: ["Live and file-based coding", "Multi-sport templates", "Clip and data exports"],
  },
  {
    number: "02",
    name: "FAST Viewer",
    label: "Review",
    description:
      "Deliver organised match analysis to coaches through a focused review workspace built for fast decisions.",
    points: ["Automatic match library", "Clip playlists and comments", "Telestration and review tools"],
  },
  {
    number: "03",
    name: "FAST Hub",
    label: "Connect",
    description:
      "Manage organisations, users, licences, matches and cloud delivery through one secure online portal.",
    points: ["Organisation management", "Cloud synchronisation", "Role-based access"],
  },
];

const sports = [
  "Football",
  "Rugby",
  "Cricket",
  "Basketball",
  "Baseball",
  "Volleyball",
  "Tennis",
  "Field Hockey",
  "Ice Hockey",
  "Netball",
];

const capabilities = [
  {
    title: "One connected workflow",
    text: "Move from coding to review without rebuilding projects, transferring folders or changing platforms.",
  },
  {
    title: "Built for matchday",
    text: "Capture meaningful moments live, publish rolling clips and keep the bench focused on what matters.",
  },
  {
    title: "Structured intelligence",
    text: "Combine events, players, attributes, clips and match context in a reusable analysis model.",
  },
  {
    title: "Designed to scale",
    text: "Start with one analyst and grow into a connected organisation with controlled users and licences.",
  },
];

export default function Home() {
  return (
    <main>
      <header className="site-header">
        <a className="brand" href="#top" aria-label="FAST Sports Analytics home">
          <Image
            src="/branding/fast-logo.png"
            alt="FAST Sports Analytics"
            width={500}
            height={170}
            priority
          />
        </a>
        <nav aria-label="Primary navigation">
          <a href="#platform">Platform</a>
          <a href="#capabilities">Capabilities</a>
          <a href="#sports">Sports</a>
          <a href="#about">About</a>
        </nav>
        <a className="button button-small button-outline" href="#contact">
          Request a demo
        </a>
      </header>

      <section className="hero" id="top">
        <div className="hero-glow hero-glow-one" />
        <div className="hero-glow hero-glow-two" />
        <div className="hero-content">
          <p className="eyebrow">The connected sports analysis platform</p>
          <h1>
            Analyse the game.
            <span>Deliver the insight.</span>
          </h1>
          <p className="hero-copy">
            FAST brings live coding, post-match review and cloud delivery into one
            focused multi-sport workflow.
          </p>
          <div className="hero-actions">
            <a className="button button-primary" href="#contact">
              Request a demo
              <span aria-hidden="true">↗</span>
            </a>
            <a className="button button-quiet" href="#platform">
              Explore the platform
              <span aria-hidden="true">↓</span>
            </a>
          </div>
          <div className="hero-proof">
            <div>
              <strong>10</strong>
              <span>sports supported</span>
            </div>
            <div>
              <strong>3</strong>
              <span>connected products</span>
            </div>
            <div>
              <strong>1</strong>
              <span>unified workflow</span>
            </div>
          </div>
        </div>

        <div className="hero-product" aria-label="FAST platform overview">
          <div className="window-bar">
            <span />
            <span />
            <span />
            <p>FAST Sports Analytics</p>
          </div>
          <div className="product-screen">
            <aside>
              <Image
                src="/branding/fast-logo.png"
                alt=""
                width={210}
                height={72}
              />
              <div className="side-nav">
                <span className="active">Overview</span>
                <span>Matches</span>
                <span>Analysis</span>
                <span>Viewer</span>
                <span>Organisation</span>
              </div>
            </aside>
            <div className="dashboard">
              <div className="dashboard-heading">
                <div>
                  <small>Match workspace</small>
                  <h2>Performance overview</h2>
                </div>
                <span className="live-pill">Live</span>
              </div>
              <div className="metric-grid">
                <article>
                  <small>Possession</small>
                  <strong>58%</strong>
                  <i style={{ width: "58%" }} />
                </article>
                <article>
                  <small>Final third entries</small>
                  <strong>31</strong>
                  <i style={{ width: "72%" }} />
                </article>
                <article>
                  <small>Shots</small>
                  <strong>14</strong>
                  <i style={{ width: "64%" }} />
                </article>
              </div>
              <div className="timeline-card">
                <div className="timeline-header">
                  <span>Match timeline</span>
                  <small>Second half</small>
                </div>
                <div className="timeline">
                  <span className="event e1" />
                  <span className="event e2" />
                  <span className="event e3" />
                  <span className="event e4" />
                  <span className="event e5" />
                </div>
                <div className="clip-list">
                  <span><b>62:14</b> High regain</span>
                  <span><b>68:40</b> Final-third entry</span>
                  <span><b>74:09</b> Shot on target</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="trust-strip" aria-label="Platform positioning">
        <span>LIVE ANALYSIS</span>
        <i />
        <span>POST-MATCH REVIEW</span>
        <i />
        <span>CLOUD DELIVERY</span>
        <i />
        <span>MULTI-SPORT</span>
      </section>

      <section className="section platform" id="platform">
        <div className="section-heading">
          <p className="eyebrow">One platform. Every stage.</p>
          <h2>From the first tag to the final conversation.</h2>
          <p>
            Each FAST product has a clear purpose. Together they create a single,
            connected analysis environment.
          </p>
        </div>

        <div className="product-list">
          {products.map((product) => (
            <article className="product-card" key={product.name}>
              <div className="product-card-top">
                <span>{product.number}</span>
                <small>{product.label}</small>
              </div>
              <h3>{product.name}</h3>
              <p>{product.description}</p>
              <ul>
                {product.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
              <div className="card-arrow">↗</div>
            </article>
          ))}
        </div>
      </section>

      <section className="section capabilities" id="capabilities">
        <div className="capability-intro">
          <p className="eyebrow">Built around real analysis</p>
          <h2>Less friction. More useful insight.</h2>
          <p>
            FAST is designed around the realities of matchday, video review and
            communication—not a generic data dashboard.
          </p>
        </div>
        <div className="capability-grid">
          {capabilities.map((capability, index) => (
            <article key={capability.title}>
              <span>0{index + 1}</span>
              <h3>{capability.title}</h3>
              <p>{capability.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="section sports" id="sports">
        <div className="sports-copy">
          <p className="eyebrow">Multi-sport by design</p>
          <h2>One platform. Your sport.</h2>
          <p>
            Sport-specific match structures and coding workflows sit on top of a
            shared platform, keeping the experience consistent without forcing
            every sport into the same model.
          </p>
        </div>
        <div className="sports-grid">
          {sports.map((sport, index) => (
            <div key={sport}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <strong>{sport}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="section about" id="about">
        <div className="about-mark">
          <Image
            src="/branding/fast-logo.png"
            alt="FAST Sports Analytics"
            width={620}
            height={210}
          />
        </div>
        <div className="about-copy">
          <p className="eyebrow">Built for analysts. Built to connect teams.</p>
          <h2>Analysis software should support the conversation—not slow it down.</h2>
          <p>
            FAST Sports Analytics is being developed as a modern alternative to
            fragmented tagging, review and delivery workflows. The objective is
            straightforward: help analysts work efficiently and help coaches
            reach decisions sooner.
          </p>
          <p>
            The platform is currently in active development with live analysis,
            multi-sport support, match review and connected delivery at its core.
          </p>
        </div>
      </section>

      <section className="contact-section" id="contact">
        <div>
          <p className="eyebrow">Early access</p>
          <h2>See how FAST could fit your analysis workflow.</h2>
          <p>
            Request an early demonstration for your club, academy, university or
            performance department.
          </p>
        </div>
        <a
          className="button button-light"
          href="mailto:contact@fastsportsanalytics.com?subject=FAST Sports Analytics demo request"
        >
          Request a demo
          <span aria-hidden="true">↗</span>
        </a>
      </section>

      <footer>
        <Image
          src="/branding/fast-logo.png"
          alt="FAST Sports Analytics"
          width={300}
          height={102}
        />
        <div>
          <a href="#platform">Platform</a>
          <a href="#sports">Sports</a>
          <a href="#about">About</a>
          <a href="mailto:contact@fastsportsanalytics.com">Contact</a>
        </div>
        <p>© 2026 FAST Sports Analytics. All rights reserved.</p>
      </footer>
    </main>
  );
}
