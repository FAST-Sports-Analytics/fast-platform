import Link from "next/link";

export default function BetaTermsPage() {
  return <main className="legal-page">
    <div className="legal-shell">
      <p className="eyebrow">FAST Beta Programme</p>
      <h1>FAST Beta Terms</h1>
      <p><strong>Version 22 August 2026</strong></p>
      <p>These Beta Terms apply when FAST Sports Analytics Ltd gives an organisation temporary access to pre-release FAST software through a Beta invitation.</p>
      <h2>Pre-release software</h2>
      <p>Beta software is provided for evaluation and testing. Features may be incomplete, changed, suspended or removed before general release, and Beta builds may contain defects.</p>
      <h2>Permitted use</h2>
      <p>Beta access is limited to the organisation, products, sports, users, devices, release channel and access period attached to the invitation. Beta invitations must not be sold, transferred or shared outside the authorised organisation.</p>
      <h2>Feedback</h2>
      <p>FAST may invite participants to report bugs, usability issues and product feedback. Providing feedback does not transfer ownership of the participant's match footage, analysis data or other customer content to FAST.</p>
      <h2>Customer content and privacy</h2>
      <p>Customer match footage and analysis data remain subject to the FAST Terms of Service, Data Processing Agreement and Privacy Notice. Participation in the Beta Programme does not by itself grant FAST permission to use customer footage for machine-learning training.</p>
      <h2>Availability and support</h2>
      <p>Beta functionality may be unavailable or interrupted and is not subject to the same availability expectations as generally released FAST services. Participants should retain appropriate copies of important source footage and data.</p>
      <h2>Expiry and revocation</h2>
      <p>Beta access ends automatically on the expiry date attached to the invitation and may be revoked earlier if the invitation is misused or the Beta programme ends. Expiry of Beta access does not automatically delete the organisation's account or customer data.</p>
      <h2>Other FAST terms</h2>
      <p>These Beta Terms supplement the <Link href="/terms">FAST Terms of Service</Link>, <Link href="/dpa">Data Processing Agreement</Link> and <Link href="/privacy">Privacy Notice</Link>. If there is a conflict, the applicable signed or accepted customer agreement takes precedence.</p>
      <p><Link className="button button-primary" href="/account">Return to your account</Link></p>
    </div>
  </main>;
}
