import type { Metadata, Viewport } from "next";
import "./globals.css";
import { StructuredData } from "./components/StructuredData";

export const metadata: Metadata = {
  metadataBase: new URL("https://www.fastsportsanalytics.com"),
  title: {
    default: "FAST Sports Analytics | Multi-Sport Performance Analysis Software",
    template: "%s | FAST Sports Analytics",
  },
  description:
    "FAST is connected multi-sport performance analysis software for live coding, post-match video analysis, player-linked clips, coach review, cloud delivery and organisation management.",
  applicationName: "FAST Sports Analytics",
  keywords: [
    "multi-sport analysis software",
    "sports performance analysis software",
    "sports video analysis software",
    "live sports analysis",
    "match analysis software",
    "coach video review",
    "player clip analysis",
    "football analysis software",
    "rugby union analysis software",
    "rugby league analysis software",
    "american football analysis software",
    "futsal analysis software",
    "handball analysis software",
    "cricket analysis software",
    "basketball analysis software",
    "FAST Sports Analytics",
  ],
  alternates: { canonical: "/" },
  openGraph: {
    title: "FAST Sports Analytics | Multi-Sport Performance Analysis Software",
    description:
      "One connected multi-sport platform for live analysis, video review, player clips, coach delivery and cloud workflows.",
    url: "https://www.fastsportsanalytics.com",
    siteName: "FAST Sports Analytics",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "FAST Sports Analytics | Multi-Sport Performance Analysis Software",
    description:
      "Connected multi-sport analysis software for analysts, coaches and performance teams.",
  },
  robots: { index: true, follow: true },
};
export const viewport: Viewport = { themeColor: "#1E2227", colorScheme: "dark" };
export default function RootLayout({children}:{children:React.ReactNode}){return <html lang="en"><body><StructuredData />{children}</body></html>}
