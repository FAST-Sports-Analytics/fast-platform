import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { AcceptInviteForm } from "./AcceptInviteForm";

export const metadata: Metadata = {
  title: "Accept invitation",
  description: "Activate your FAST Sports Analytics account.",
  robots: { index: false, follow: false },
};

export default function AcceptInvitePage() {
  return <main className="reset-page">
    <div className="reset-page-glow" aria-hidden="true" />
    <Link href="/" className="reset-brand" aria-label="FAST Sports Analytics home">
      <Image src="/branding/fast-logo.png" alt="FAST Sports Analytics" width={500} height={170} priority />
    </Link>
    <AcceptInviteForm />
    <p className="reset-footer">FAST Sports Analytics · Secure account onboarding</p>
  </main>;
}
