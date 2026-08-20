import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "../components/PageShell";

export const metadata: Metadata = {
  title: "Privacy Notice",
  description: "How FAST Sports Analytics Ltd collects, uses, shares and protects personal information."
};

export default function Privacy() {
  return <PageShell>
    <section className="page-hero legal-hero">
      <p className="eyebrow">Legal</p>
      <h1>Privacy Notice</h1>
      <p className="lead">How FAST SPORTS ANALYTICS LTD handles personal information across the FAST website, accounts, subscriptions and services.</p>
    </section>
    <section className="content-section legal-copy">
      <p><strong>Last updated: 20 August 2026</strong></p>

      <h2>1. Who we are</h2>
      <p>FAST SPORTS ANALYTICS LTD ("FAST", "we", "us" or "our") provides sports-analysis software and cloud services. We are responsible for personal information that we determine how and why to use, including information used to operate customer accounts, subscriptions, licensing, security and our business relationship with customers.</p>
      <p>Privacy questions and requests can be sent to <a href="mailto:contact@fastsportsanalytics.com">contact@fastsportsanalytics.com</a>.</p>

      <h2>2. When this notice applies</h2>
      <p>This notice applies when you visit our website, create or use a FAST account, administer or participate in a customer organisation, purchase or manage a subscription, activate a device, contact us, or otherwise interact with FAST.</p>
      <p>Customers may also submit match footage, clips, player or team information, event data, annotations and other sports-analysis content. Where a customer determines the purposes and means of processing personal information contained in that content, the customer is normally the controller and FAST acts as its processor. That processing is governed by our <Link href="/dpa">Data Processing Agreement</Link> and the customer's instructions.</p>

      <h2>3. Information we collect</h2>
      <p>Depending on how FAST is used, we may process:</p>
      <ul>
        <li><strong>Account information:</strong> name, work email address, organisation, country, account status and authentication information. Passwords are stored using password hashes rather than as readable passwords.</li>
        <li><strong>Organisation and access information:</strong> organisation details, membership, roles, invitations, permissions, assigned sports/products and seat information.</li>
        <li><strong>Subscription and billing information:</strong> plan, billing interval, subscription state, Stripe customer/subscription references, payment status and related billing records. Payment-card processing is handled by Stripe; FAST does not need to store full card details in its application database.</li>
        <li><strong>Licence and device information:</strong> licences, products, sports, entitlement limits, device identifiers/names, activations, installed component versions, update status and service telemetry.</li>
        <li><strong>Security and diagnostic information:</strong> authentication events, administrative actions, audit records, error/crash information, component/version information and diagnostic context used to secure and support the service.</li>
        <li><strong>Communications:</strong> information contained in enquiries, support requests and other correspondence with FAST.</li>
        <li><strong>Website and network information:</strong> technical information generated when accessing our website and services, such as IP/network and request information where processed by our infrastructure and security providers.</li>
      </ul>

      <h2>4. Why we use personal information</h2>
      <p>We use personal information to provide and administer FAST; create and secure accounts; verify identity and email addresses; manage organisations, permissions, licences and devices; provide subscriptions and billing administration; deliver updates and support; prevent abuse and protect our systems; diagnose faults; communicate with customers; maintain appropriate business and accounting records; and establish, exercise or defend legal rights.</p>

      <h2>5. Our lawful bases</h2>
      <p>Where UK data-protection law applies, our lawful bases depend on the processing. We primarily rely on processing necessary to perform or take steps relating to our contract with a customer or user; our legitimate interests in operating, securing, supporting and improving FAST and administering our business; and compliance with legal obligations, including applicable accounting, tax and regulatory requirements. Where consent is legally required for a particular activity, we will request it separately.</p>
      <p>When FAST acts only as a processor of Customer Personal Data, the customer is responsible for determining its applicable lawful basis and providing any required privacy information to the people concerned.</p>

      <h2>6. Customer sports content</h2>
      <p>FAST can process customer-provided sports content including match footage, images or audio contained in footage, clips, teams, player identifiers, event/tagging information, annotations and analysis data. Customers are responsible for ensuring that they are entitled to collect, upload and instruct FAST to process that content, including where it contains information about players, staff, opponents, spectators or other individuals.</p>

      <h2>7. Young users</h2>
      <p>The organisation administrator who creates or manages the commercial FAST account must be at least 18 years old. An organisation may invite younger authorised staff users, including 16- or 17-year-olds, where appropriate. The organisation is responsible for ensuring it has authority to provide those users with access, assigning appropriate permissions and supervising their use of FAST.</p>

      <h2>8. Who receives information</h2>
      <p>We use service providers to operate FAST. Depending on the service and configuration, these include Railway for FAST Cloud infrastructure, Vercel for website deployment/hosting, Cloudflare for domain, DNS, network and security infrastructure, Stripe for payments and subscription billing, Google/Gmail for business email, and GitHub for source-code and deployment workflows. GitHub is not intended to be used as a repository for customer match or account data.</p>
      <p>Some providers, including payment providers, may act as independent controllers for parts of their processing. We may also disclose information where required by law, to protect legal rights or security, or in connection with a lawful corporate transaction.</p>

      <h2>9. International processing</h2>
      <p>FAST is offered internationally and our service providers may process information in more than one country. Where UK data-protection law applies and a transfer is a restricted transfer, we use an applicable lawful transfer mechanism, such as adequacy regulations or appropriate contractual safeguards, and carry out any assessment required by law.</p>

      <h2>10. Retention and deletion</h2>
      <p>Customer content and operational organisation data are retained for a recovery period of up to <strong>31 days after the relevant organisation/service terminates or is deleted</strong>. After that recovery period FAST will initiate permanent deletion from active systems in accordance with its deletion procedures.</p>
      <p>Backups may follow a separate secure deletion cycle and may be placed beyond ordinary use before final expiry. We may retain limited information for longer where necessary for legal, tax, accounting, fraud-prevention, security, dispute or regulatory purposes. Such information is not retained merely to continue providing the terminated service.</p>

      <h2>11. Your rights</h2>
      <p>Depending on the law that applies to you, you may have rights relating to your personal information, including rights of access, correction, erasure, restriction, objection and data portability, and rights relating to consent or automated decision-making where applicable. To exercise a right relating to information FAST controls, contact us at <a href="mailto:contact@fastsportsanalytics.com">contact@fastsportsanalytics.com</a>.</p>
      <p>If your request concerns personal information submitted to FAST by your employer, club or another customer, that organisation may be the controller. We may refer the request to, or assist, that customer as required.</p>

      <h2>12. Complaints</h2>
      <p>Please contact us first if you have a privacy concern so we can investigate it. Where UK data-protection law applies, you also have the right to complain to the UK Information Commissioner's Office (ICO). Individuals elsewhere may have the right to complain to their local data-protection or privacy authority.</p>

      <h2>13. Security</h2>
      <p>We use technical and organisational measures designed to protect personal information, including access controls, authentication controls, restricted administrative access and security/audit records. No internet or software service can guarantee absolute security.</p>

      <h2>14. Changes to this notice</h2>
      <p>We may update this notice as FAST, our suppliers or applicable laws change. We will publish the current version here and, where required, bring material changes to affected users' attention before the new processing begins.</p>

      <h2>15. Contact</h2>
      <p>FAST SPORTS ANALYTICS LTD<br/>Email: <a href="mailto:contact@fastsportsanalytics.com">contact@fastsportsanalytics.com</a></p>
    </section>
  </PageShell>;
}
