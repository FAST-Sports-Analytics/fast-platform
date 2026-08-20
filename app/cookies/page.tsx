import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "../components/PageShell";

export const metadata: Metadata = {
  title: "Cookie Notice",
  description: "How FAST Sports Analytics uses cookies, browser storage and similar technologies."
};

export default function Cookies() {
  return <PageShell>
    <section className="page-hero legal-hero">
      <p className="eyebrow">Legal</p>
      <h1>Cookie Notice</h1>
      <p className="lead">How FAST Sports Analytics uses cookies, browser storage and similar technologies on our website and web account services.</p>
    </section>

    <section className="content-section legal-copy">
      <p><strong>Last updated: 20 August 2026</strong></p>

      <h2>1. About this notice</h2>
      <p>This notice explains how FAST SPORTS ANALYTICS LTD ("FAST", "we", "us" or "our") uses cookies, web storage and similar storage or access technologies on fastsportsanalytics.com and associated FAST web-account functionality.</p>
      <p>It should be read together with our <Link href="/privacy">Privacy Notice</Link>.</p>

      <h2>2. What these technologies are</h2>
      <p>Cookies are small pieces of information that a website can store on a user's device. Similar technologies include browser web storage, such as session storage, and other mechanisms that store information on or access information from a browser or device.</p>

      <h2>3. Our current use</h2>
      <p>The current FAST website does <strong>not intentionally use advertising, behavioural-tracking or third-party analytics cookies</strong>. We do not currently use FAST website storage to build advertising profiles or track visitors across unrelated websites.</p>
      <p>Authenticated FAST web-account pages use browser <strong>session storage</strong> for information necessary to operate the signed-in session. This currently includes the FAST access token, refresh token and a limited cached representation of the signed-in user. Session storage is scoped to the browser tab/session and is cleared by FAST when the user signs out; browsers also ordinarily clear session storage when the relevant browsing session ends.</p>

      <h2>4. Strictly necessary storage</h2>
      <p>The session storage described above is used to authenticate the user, maintain access to requested account functionality and support the security and operation of the signed-in FAST service. Because this storage is used for functionality requested by the user and is necessary to provide that functionality, FAST treats it as strictly necessary storage.</p>
      <p>Strictly necessary technologies do not require an optional-cookie consent choice, but we still provide information about them through this notice.</p>

      <h2>5. Current storage summary</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>Technology</th><th>Purpose</th><th>Typical duration</th><th>Consent</th></tr>
          </thead>
          <tbody>
            <tr><td>FAST access token (session storage)</td><td>Authenticates the signed-in FAST web session and authorises requested account actions.</td><td>Browser session / until logout, subject to the token's own expiry.</td><td>Strictly necessary</td></tr>
            <tr><td>FAST refresh token (session storage)</td><td>Supports authorised session continuity where FAST web functionality uses refresh-token handling.</td><td>Browser session / until logout, subject to the token's own expiry.</td><td>Strictly necessary</td></tr>
            <tr><td>FAST user cache (session storage)</td><td>Stores limited signed-in user/profile information required to present and operate account pages.</td><td>Browser session / until logout.</td><td>Strictly necessary</td></tr>
          </tbody>
        </table>
      </div>

      <h2>6. Infrastructure providers</h2>
      <p>Our website and network infrastructure uses providers including Vercel and Cloudflare. Those providers may process technical request, network and security information when delivering or protecting the website. If an infrastructure configuration places or accesses information on a user's device, we will assess that use under applicable storage/access rules and update this notice where necessary.</p>

      <h2>7. Analytics, advertising and optional technologies</h2>
      <p>FAST does not currently intentionally deploy non-essential analytics, advertising or cross-site tracking technologies on the public website. If we introduce optional analytics, advertising, tracking or other non-essential storage/access technologies in the future, we will update this notice and implement an appropriate consent mechanism before using technologies that require consent.</p>
      <p>Where consent is required, declining optional technologies will not prevent access to core FAST website functionality unless the technology is genuinely necessary for a feature the user specifically requests.</p>

      <h2>8. Browser controls</h2>
      <p>Most browsers allow users to inspect, block or remove cookies and website storage. Blocking storage that is strictly necessary for authentication may prevent signed-in FAST account functionality from working correctly.</p>

      <h2>9. Changes to this notice</h2>
      <p>We will review our use of cookies and similar technologies as the FAST website and account services develop. We may update this notice when technologies, providers, purposes or legal requirements change.</p>

      <h2>10. Contact</h2>
      <p>Questions about FAST's use of cookies or similar technologies can be sent to <a href="mailto:contact@fastsportsanalytics.com">contact@fastsportsanalytics.com</a>.</p>
    </section>
  </PageShell>;
}
