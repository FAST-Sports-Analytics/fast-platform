import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "../components/PageShell";

export const metadata: Metadata = {
  title: "Subprocessors",
  description: "Service providers used by FAST Sports Analytics to provide and support the FAST service."
};

export default function Subprocessors() {
  return <PageShell>
    <section className="page-hero legal-hero">
      <p className="eyebrow">Legal</p>
      <h1>Subprocessors & Service Providers</h1>
      <p className="lead">Providers used to operate, secure, support and administer FAST Sports Analytics.</p>
    </section>

    <section className="content-section legal-copy">
      <p><strong>Last updated: 20 August 2026</strong></p>

      <h2>1. About this list</h2>
      <p>FAST SPORTS ANALYTICS LTD ("FAST", "we", "us" or "our") uses third-party providers to operate and support FAST. This page identifies key providers and explains their role.</p>
      <p>A provider is a <strong>subprocessor</strong> only to the extent it processes Customer Personal Data on FAST's behalf when FAST is acting as a processor for a customer. Some providers may instead act as an independent controller for particular activities, or may be used for development/business functions without being intended to receive Customer Personal Data.</p>
      <p>This page should be read with our <Link href="/dpa">Data Processing Agreement</Link> and <Link href="/privacy">Privacy Notice</Link>.</p>

      <h2>2. Current providers</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Provider</th><th>FAST use</th><th>Information / processing</th><th>Classification</th></tr></thead>
          <tbody>
            <tr>
              <td><strong>Railway</strong></td>
              <td>FAST Cloud application, API and associated production infrastructure.</td>
              <td>May host/process FAST account, organisation, licensing, device, service and Customer Personal Data handled through FAST Cloud, depending on the deployed service.</td>
              <td>Subprocessor where it hosts Customer Personal Data for FAST.</td>
            </tr>
            <tr>
              <td><strong>Vercel</strong></td>
              <td>FAST public website deployment and hosting.</td>
              <td>Website requests and associated technical/network information; account-related information only to the extent a deployed FAST web function processes it through Vercel infrastructure.</td>
              <td>Service provider; subprocessor to the extent it processes Customer Personal Data on FAST's behalf.</td>
            </tr>
            <tr>
              <td><strong>Cloudflare</strong></td>
              <td>Domain/DNS and web/network delivery, protection and security infrastructure.</td>
              <td>May process IP addresses, request/network metadata and security information when traffic passes through Cloudflare services.</td>
              <td>Service provider; subprocessor where processing Customer Personal Data on FAST's behalf.</td>
            </tr>
            <tr>
              <td><strong>Google / Gmail</strong></td>
              <td>FAST business email and customer correspondence.</td>
              <td>Names, email addresses, correspondence, support information and other information a person chooses to include in email communications.</td>
              <td>Service provider; may be a processor/subprocessor for relevant business-email processing, subject to the applicable Google service terms.</td>
            </tr>
            <tr>
              <td><strong>Stripe</strong></td>
              <td>Payments, subscription billing and billing-management services.</td>
              <td>Customer/contact information, payment and billing information, subscription/payment status and transaction-related information.</td>
              <td>Payment service provider. Stripe may act as an independent controller for some processing and as a processor/service provider for other processing under its applicable terms.</td>
            </tr>
            <tr>
              <td><strong>GitHub</strong></td>
              <td>FAST source-code repositories and software/deployment workflows.</td>
              <td>Development/source-code information and deployment-related information. GitHub is not intended to be used to store customer match footage or ordinary Customer Personal Data.</td>
              <td>Development service provider; not listed as a Customer Personal Data subprocessor unless a FAST workflow actually causes it to process such data on FAST's behalf.</td>
            </tr>
          </tbody>
        </table>
      </div>

      <h2>3. Customer Personal Data</h2>
      <p>For purposes of this page, "Customer Personal Data" has the meaning used in the FAST Data Processing Agreement and can include personal information contained in customer-provided footage, clips, player/team information, event/tagging data, annotations and other Customer Content.</p>

      <h2>4. International processing</h2>
      <p>Providers may operate infrastructure or support functions in multiple countries. Where FAST makes a restricted transfer of Customer Personal Data subject to UK data-protection law, FAST will use an applicable lawful transfer mechanism as described in the Data Processing Agreement.</p>

      <h2>5. Changes to providers</h2>
      <p>FAST may add, replace or remove providers as its infrastructure develops. Where applicable data-protection law or the Data Processing Agreement requires notice of a new subprocessor, FAST will provide reasonable notice and an opportunity for the Customer to raise a reasonable data-protection objection.</p>

      <h2>6. Provider locations</h2>
      <p>We do not state a single fixed processing country for a provider unless FAST has verified and contractually established that location for the relevant service. Provider infrastructure and support locations can change, and FAST will maintain appropriate international-transfer safeguards where required.</p>

      <h2>7. Contact</h2>
      <p>Questions about FAST's providers or subprocessor arrangements can be sent to <a href="mailto:contact@fastsportsanalytics.com">contact@fastsportsanalytics.com</a>.</p>
    </section>
  </PageShell>;
}
