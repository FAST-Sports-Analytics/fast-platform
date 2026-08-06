import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://www.fastsportsanalytics.com"),
  title: { default: "FAST Sports Analytics", template: "%s | FAST Sports Analytics" },
  description: "Connected multi-sport analysis software for live coding, post-match review, cloud delivery, scouting and collaborative coaching workflows.",
  applicationName: "FAST Sports Analytics",
  keywords: ["sports analysis", "football analysis software", "video analysis", "live match analysis", "performance analysis", "FAST Sports Analytics"],
  openGraph: { title: "FAST Sports Analytics", description: "One connected platform for analysis, review, cloud delivery and scouting workflows.", url: "https://www.fastsportsanalytics.com", siteName: "FAST Sports Analytics", type: "website" },
  twitter: { card: "summary_large_image", title: "FAST Sports Analytics", description: "Connected sports analysis software for modern performance teams." },
  robots: { index: true, follow: true },
};
export const viewport: Viewport = { themeColor: "#1E2227", colorScheme: "dark" };
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
