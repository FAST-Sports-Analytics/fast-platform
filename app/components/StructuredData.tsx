const BASE_URL = "https://www.fastsportsanalytics.com";

const organisation = {
  "@type": "Organization",
  "@id": `${BASE_URL}/#organization`,
  name: "FAST Sports Analytics Ltd",
  alternateName: "FAST Sports Analytics",
  url: BASE_URL,
  logo: `${BASE_URL}/branding/fast-logo.png`,
  description:
    "Developer of FAST, a connected multi-sport performance analysis platform for analysts, coaches and sports organisations.",
};

const software = {
  "@type": "SoftwareApplication",
  "@id": `${BASE_URL}/#software`,
  name: "FAST Sports Analytics",
  alternateName: "FAST",
  applicationCategory: "SportsApplication",
  applicationSubCategory: "Sports performance analysis software",
  operatingSystem: "Windows",
  url: BASE_URL,
  publisher: { "@id": `${BASE_URL}/#organization` },
  description:
    "Multi-sport performance analysis software for live coding, post-match video analysis, player-linked clips, coach review, cloud delivery and organisation management.",
  keywords: [
    "Football analysis",
    "Futsal analysis",
    "Rugby Union analysis",
    "Rugby League analysis",
    "American Football analysis",
    "Cricket analysis",
    "Basketball analysis",
    "Handball analysis",
    "Baseball analysis",
    "Volleyball analysis",
    "Tennis analysis",
    "Field Hockey analysis",
    "Ice Hockey analysis",
    "Netball analysis",
  ],
  featureList: [
    "Live sports analysis and event coding",
    "Post-match video analysis",
    "Player-linked clip review",
    "Coach-facing video review and playlists",
    "Cloud clip delivery",
    "Organisation, role and licence management",
    "Multi-sport workflows",
  ],
};

const website = {
  "@type": "WebSite",
  "@id": `${BASE_URL}/#website`,
  url: BASE_URL,
  name: "FAST Sports Analytics",
  publisher: { "@id": `${BASE_URL}/#organization` },
};

export function StructuredData() {
  const graph = {
    "@context": "https://schema.org",
    "@graph": [organisation, software, website],
  };

  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(graph) }}
    />
  );
}
