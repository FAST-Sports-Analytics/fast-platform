import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { ResetPasswordForm } from "./ResetPasswordForm";

export const metadata: Metadata = {
  title: "Reset password",
  description: "Reset your FAST Sports Analytics account password.",
  robots: { index: false, follow: false },
};

export default function ResetPasswordPage() {
  return <main className="reset-page">
    <div className="reset-page-glow" aria-hidden="true" />
    <Link href="/" className="reset-brand" aria-label="FAST Sports Analytics home">
      <Image src="/branding/fast-logo.png" alt="FAST Sports Analytics" width={500} height={170} priority />
    </Link>
    <ResetPasswordForm />
    <p className="reset-footer">FAST Sports Analytics · Secure account recovery</p>
  </main>;
}
