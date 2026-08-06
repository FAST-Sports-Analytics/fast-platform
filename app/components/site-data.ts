export const products = [
  {
    slug: "analysis",
    number: "01",
    name: "FAST Analysis",
    label: "Analyse",
    summary: "Code live matches, analyse video and turn key moments into structured, searchable intelligence.",
    description: "A complete desktop workspace for live coding, post-match analysis, event review, clip creation and multi-sport performance workflows.",
    features: ["Live and file-based coding", "Sport-specific coding templates", "Player, event and attribute context", "Clip, data and workbook exports", "Match timeline and live statistics", "Connected publishing to FAST Cloud"],
  },
  {
    slug: "viewer",
    number: "02",
    name: "FAST Viewer",
    label: "Review",
    summary: "Deliver organised match analysis to coaches through a focused review workspace built for fast decisions.",
    description: "A clear review environment for coaches and staff to watch selected clips, build playlists, add comments and communicate decisions.",
    features: ["Automatic match and clip library", "Playlists for meetings and review", "Coach comments and clip context", "Freeze-frame and telestration tools", "Focused half-time workflows", "Secure cloud-delivered content"],
  },
  {
    slug: "cloud",
    number: "03",
    name: "FAST Cloud",
    label: "Connect",
    summary: "Manage organisations, users, licences, matches and secure delivery through one connected platform.",
    description: "The online layer that connects FAST Analysis and FAST Viewer while controlling organisations, access, licences and match delivery.",
    features: ["Organisation and team management", "Role-based user access", "Licence and product entitlements", "Match and clip synchronisation", "Secure media delivery", "Central account administration"],
  },
] as const;

export const sports = [
  { slug: "football", name: "Football", description: "Live coding, formations, substitutions, player context and review workflows built around the rhythm of football.", highlights: ["Formation and squad context", "Live and post-match event coding", "Substitutions and player-linked clips", "Bench delivery through FAST Viewer"] },
  { slug: "rugby", name: "Rugby", description: "Match events, scoring, player status and coding structures suited to rugby analysis.", highlights: ["Rugby-specific scoring context", "Player status and match control", "Structured phase and event review", "Fast delivery to coaches"] },
  { slug: "cricket", name: "Cricket", description: "Formats, innings, overs, batting order, bowling changes and detailed scoring context.", highlights: ["T20, ODI, Test and custom formats", "Innings, overs and ball state", "Batting order and bowling changes", "Score and target context"] },
  { slug: "basketball", name: "Basketball", description: "Fast event coding, player context and possession-based review for a high-tempo game.", highlights: ["High-tempo live coding", "Player and lineup context", "Possession-based review", "Clip playlists for meetings"] },
  { slug: "baseball", name: "Baseball", description: "Diamond-based structure, batting and fielding roles, scoring events and situational review.", highlights: ["Diamond-based match structure", "Batting and fielding roles", "Situational event coding", "Video-linked review"] },
  { slug: "volleyball", name: "Volleyball", description: "Rally-based coding and repeatable review workflows for team and player performance.", highlights: ["Rally-based event structure", "Team and player context", "Repeatable coding workflows", "Focused clip review"] },
  { slug: "tennis", name: "Tennis", description: "Singles and doubles structures with player-specific event and match context.", highlights: ["Singles and doubles support", "Player-specific match context", "Point and event review", "Structured video clips"] },
  { slug: "field-hockey", name: "Field Hockey", description: "Team structures, cards, match actions and video review adapted for field hockey.", highlights: ["Team and formation structure", "Cards and player status", "Match-action coding", "Coach-ready review"] },
  { slug: "ice-hockey", name: "Ice Hockey", description: "A fast review workflow for shifts, key events, player context and match clips.", highlights: ["Shift and player context", "High-speed event coding", "Key-moment clipping", "Connected review delivery"] },
  { slug: "netball", name: "Netball", description: "Position-aware team structure and coding designed around netball's match flow.", highlights: ["Position-aware squad structure", "Match-flow event coding", "Player-linked review", "Cloud-delivered clips"] },
] as const;

export const capabilities = [
  ["Live analysis", "Code meaningful events during the match, maintain match context and publish selected moments while play continues."],
  ["Video review", "Return to every event with structured filters, timelines, player context and precise clip control."],
  ["Cloud delivery", "Move selected analysis securely from the analyst's workspace to the people who need it."],
  ["Multi-sport structure", "Use sport-specific match logic without learning a completely different platform for every team."],
  ["Connected teams", "Control users, roles and product access across analysts, coaches and wider performance staff."],
  ["Actionable output", "Turn coding into clips, playlists, data exports and conversations that support decisions."],
] as const;
