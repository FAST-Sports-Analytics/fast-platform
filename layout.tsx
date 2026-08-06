import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://www.fastsportsanalytics.com"),
  title: { default: "FAST Sports Analytics", template: "%s | FAST Sports Analytics" },
  description: "Connected multi-sport analysis software for live coding, post-match review, cloud delivery and collaborative coaching workflows.",
  keywords: ["sports analysis", "football analysis software", "video analysis", "live match analysis", "performance analysis", "FAST Sports Analytics"],
  openGraph: { title: "FAST Sports Analytics", description: "One connected platform for live analysis, post-match intelligence and cloud-based review.", url: "https://www.fastsportsanalytics.com", siteName: "FAST Sports Analytics", type: "website" },
  robots: { index: true, follow: true },
};

export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body>{children}</body></html>}
