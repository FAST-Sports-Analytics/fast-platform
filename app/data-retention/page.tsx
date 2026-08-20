import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "../components/PageShell";

export const metadata: Metadata = {
  title: "Data Retention & Deletion Policy",
  description: "How FAST Sports Analytics retains, recovers and deletes customer and service data."
};

export default function DataRetention() {
  return <PageShell>
    <section className="page-hero legal-hero">
      <p className="eyebrow">Legal</p>
      <h1>Data Retention &amp; Deletion Policy</h1>
      <p className="lead">How long FAST keeps different categories of information and what happens when an organisation or subscription ends.</p>
    </section>

    <section className="content-section legal-copy">
      <p><strong>Last updated: 20 August 2026</strong></p>

      <h2>1. Purpose</h2>
      <p>This policy explains the retention and deletion approach used by FAST SPORTS ANALYTICS LTD ("FAST", "we", "us" or "our"). We aim to keep personal information and Customer Content only for as long as reasonably necessary for the purpose for which it is held, while meeting contractual, security, accounting, tax and legal obligations.</p>
      <p>This policy should be read with our <Link href="/privacy">Privacy Notice</Link>, <Link href="/dpa">Data Processing Agreement</Link> and <Link href="/terms">Terms of Service</Link>.</p>

      <h2>2. Customer Content</h2>
      <p>Customer Content can include match footage, video, audio or images contained in footage, clips, teams, squads, player information, event/tagging data, annotations, analysis information and other content submitted to or created through FAST by or for a customer organisation.</p>
      <p>While the relevant FAST service remains active, Customer Content is retained as necessary to provide that service and subject to any deletion controls made available to the customer.</p>

      <h2>3. The 31-day recovery period</h2>
      <p>When the relevant organisation or service terminates or is deleted, Customer Content and recoverable operational organisation data will ordinarily enter a recovery period of up to <strong>31 days</strong>.</p>
      <p>The purpose of this period is to allow recovery from accidental deletion, administrative mistakes or a customer's decision to reactivate an eligible service. The 31-day period begins when the relevant service or organisation actually terminates or is deleted, not merely when a subscription cancellation is requested or an individual payment attempt fails.</p>
      <p>Where a customer cancels but has already paid for access through a future date, ordinary service access continues until the applicable paid service period ends. The post-termination recovery period then begins when that service access ends.</p>

      <h2>4. Permanent deletion after recovery</h2>
      <p>After the 31-day recovery period expires, FAST will initiate permanent deletion of Customer Content and operational organisation data from active systems, except for information that FAST must or is permitted to retain separately for a legitimate legal, accounting, tax, security, fraud-prevention or dispute purpose.</p>
      <p>Customers should export information they need to retain before their service and recovery period expire. Once permanent deletion has progressed beyond the recoverable state, FAST may be unable to restore the information.</p>

      <h2>5. Backups</h2>
      <p>Secure backups may operate on a separate lifecycle from active production systems. Information deleted from active systems may therefore remain in protected backups until the applicable backup expires or is overwritten.</p>
      <p>Backup information awaiting expiry is not intended to be restored to ordinary operational use. If restoration is necessary for legitimate disaster recovery, FAST will take reasonable steps to ensure that previously deleted information is not reintroduced into ordinary service use except where technically necessary during recovery and is subsequently returned to the appropriate deletion state.</p>

      <h2>6. Retention schedule</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Data category</th><th>Normal retention approach</th><th>Reason</th></tr></thead>
          <tbody>
            <tr>
              <td><strong>Customer Content</strong></td>
              <td>During active service, then up to 31 days after the relevant service/organisation terminates or is deleted before permanent deletion is initiated.</td>
              <td>Service delivery and limited recovery/reactivation.</td>
            </tr>
            <tr>
              <td><strong>Recoverable organisation/account operational data</strong></td>
              <td>During active service, then ordinarily up to 31 days following termination/deletion, unless a separate retention purpose applies.</td>
              <td>Account operation, recovery and orderly termination.</td>
            </tr>
            <tr>
              <td><strong>Authentication/reset/invitation data</strong></td>
              <td>For the validity period needed for the relevant authentication, verification, reset or invitation function, plus limited records where required for security/audit purposes.</td>
              <td>Authentication and account security.</td>
            </tr>
            <tr>
              <td><strong>Billing, transaction, tax and accounting records</strong></td>
              <td>Retained for the period required by applicable accounting, company and tax law and for legitimate financial/dispute purposes. These records are not subject to the 31-day Customer Content deletion rule.</td>
              <td>Legal, tax, accounting, payment and dispute obligations.</td>
            </tr>
            <tr>
              <td><strong>Security and audit records</strong></td>
              <td>Normally up to 12 months, unless a longer period is reasonably required for an active security incident, fraud investigation, dispute or legal obligation.</td>
              <td>Security monitoring, investigation, abuse prevention and accountability.</td>
            </tr>
            <tr>
              <td><strong>Crash and diagnostic information</strong></td>
              <td>Normally up to 90 days. Relevant information may be retained longer where attached to an unresolved engineering, security or support incident.</td>
              <td>Fault diagnosis, reliability and security.</td>
            </tr>
            <tr>
              <td><strong>Support and business correspondence</strong></td>
              <td>Normally up to 24 months after the matter is resolved, unless longer retention is reasonably required for an ongoing customer relationship, dispute or legal obligation.</td>
              <td>Customer support, business records and dispute handling.</td>
            </tr>
            <tr>
              <td><strong>Secure backups</strong></td>
              <td>Until expiry/overwrite under the applicable backup lifecycle after deletion from active systems.</td>
              <td>Resilience and disaster recovery.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2>7. Payment failure and grace periods</h2>
      <p>A failed payment does not automatically start Customer Content deletion. FAST may retry payment and may provide a billing grace or recovery process. The 31-day post-service recovery period begins only when the relevant service actually terminates or the organisation is deleted.</p>

      <h2>8. Reactivation</h2>
      <p>Where technically supported and the recovery period has not expired, FAST may restore access to retained Customer Content following an eligible reactivation. Reactivation is not guaranteed once deletion has begun or where information has already become irrecoverable.</p>

      <h2>9. User deletion versus organisation deletion</h2>
      <p>Removing an individual user from an organisation does not necessarily delete Customer Content belonging to that organisation. Match footage, analysis and other organisation content may remain available to the organisation in accordance with its subscription and retention period.</p>
      <p>Personal information relating only to a removed user will be deleted, anonymised or retained according to the purpose for which it is held and any applicable security, audit, legal or contractual requirement.</p>

      <h2>10. Legal holds and disputes</h2>
      <p>FAST may temporarily preserve information beyond its normal deletion date where reasonably necessary to comply with law, a court or regulatory requirement, investigate fraud or security incidents, establish or defend legal claims, or preserve evidence relating to an active dispute. Access will be restricted to the extent appropriate to that purpose.</p>

      <h2>11. Customer instructions when FAST is processor</h2>
      <p>Where FAST acts as processor of Customer Personal Data, deletion and return are also governed by the <Link href="/dpa">Data Processing Agreement</Link> and the customer's lawful documented instructions. FAST will not retain Customer Personal Data for its own unrelated purposes merely because the customer has terminated the service.</p>

      <h2>12. Data minimisation and anonymisation</h2>
      <p>Where FAST no longer needs information in identifiable form but aggregate or non-identifying information remains useful for legitimate statistical, reliability or business purposes, FAST may anonymise the information so that it is no longer personal data. We will not describe information as anonymous where individuals remain reasonably identifiable.</p>

      <h2>13. Changes to this policy</h2>
      <p>We may update this policy as FAST's systems, backup arrangements, legal requirements or retention needs develop. Material changes affecting active customers will be communicated where required by law or contract.</p>

      <h2>14. Contact</h2>
      <p>Questions about retention, deletion or recovery can be sent to <a href="mailto:contact@fastsportsanalytics.com">contact@fastsportsanalytics.com</a>.</p>
    </section>
  </PageShell>;
}
