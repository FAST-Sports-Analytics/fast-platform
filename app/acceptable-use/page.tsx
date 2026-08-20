import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "../components/PageShell";

export const metadata: Metadata = {
  title: "Acceptable Use Policy",
  description: "Rules for safe, lawful and authorised use of FAST Sports Analytics."
};

export default function AcceptableUse() {
  return <PageShell>
    <section className="page-hero legal-hero">
      <p className="eyebrow">Legal</p>
      <h1>Acceptable Use Policy</h1>
      <p className="lead">Rules designed to protect FAST, our customers, authorised users, athletes and the integrity of the service.</p>
    </section>

    <section className="content-section legal-copy">
      <p><strong>Last updated: 20 August 2026</strong></p>

      <h2>1. About this policy</h2>
      <p>This Acceptable Use Policy ("AUP") applies to use of FAST Sports Analytics websites, desktop applications, cloud services, downloads, APIs and related services ("FAST"). It forms part of the FAST <Link href="/terms">Terms of Service</Link>.</p>
      <p>The customer organisation is responsible for ensuring that its administrators and authorised users comply with this policy.</p>

      <h2>2. Lawful and authorised use</h2>
      <p>You may use FAST only for lawful, authorised sports-analysis and related organisational purposes. You must comply with applicable laws, regulations, competition or governing-body requirements, contractual restrictions and the rights of other people and organisations.</p>

      <h2>3. Match footage and Customer Content</h2>
      <p>You must not upload, process, distribute or make available footage, images, audio, player information, analysis, statistics or other material unless your organisation has the rights, permissions or other lawful authority necessary to do so.</p>
      <p>You must not use FAST to infringe copyright, database rights, trade marks, privacy, confidentiality, publicity rights or other intellectual-property or legal rights.</p>
      <p>Where Customer Content contains personal information, including information concerning players, staff, officials, spectators or children, your organisation is responsible for complying with applicable data-protection, privacy and safeguarding requirements. FAST's processing of Customer Personal Data on behalf of customers is addressed in the <Link href="/dpa">Data Processing Agreement</Link>.</p>

      <h2>4. Accounts and access</h2>
      <p>You must not:</p>
      <ul>
        <li>share personal login credentials with an unauthorised person;</li>
        <li>access another user's account without authority;</li>
        <li>misrepresent your identity, organisation, role or authority;</li>
        <li>invite users who are not authorised by the organisation to access its FAST environment;</li>
        <li>use another organisation's licence, subscription, device allocation or Customer Content without permission; or</li>
        <li>attempt to obtain access to FAST functionality for which your organisation is not licensed.</li>
      </ul>

      <h2>5. Licensing, seats and devices</h2>
      <p>You must not bypass, disable, manipulate or circumvent FAST licensing, subscription, sport, product, seat, role, device or feature restrictions. You must not falsify device or entitlement information or otherwise attempt to obtain paid functionality without the appropriate licence or subscription.</p>

      <h2>6. Security and service integrity</h2>
      <p>You must not:</p>
      <ul>
        <li>introduce malware, ransomware, malicious code or other harmful material;</li>
        <li>probe, scan or test FAST systems for vulnerabilities without FAST's prior written authorisation;</li>
        <li>attempt to defeat authentication, access controls, rate limits or other security measures;</li>
        <li>intercept data or communications that you are not authorised to access;</li>
        <li>perform denial-of-service activity or deliberately overload, disrupt or degrade FAST infrastructure;</li>
        <li>use automated activity in a way that materially interferes with FAST or other customers;</li>
        <li>attempt to access FAST administrative systems, source code, secrets, credentials or another customer's environment without authority; or</li>
        <li>use FAST to facilitate phishing, fraud, impersonation or other deceptive or unlawful activity.</li>
      </ul>

      <h2>7. Reverse engineering and copying</h2>
      <p>Except where applicable law expressly permits an activity despite this restriction, you must not reverse engineer, decompile, disassemble or otherwise attempt to derive FAST source code or protected implementation details; remove proprietary notices; clone substantial protected elements of FAST; or reproduce or distribute FAST software outside the licence granted by the Terms of Service.</p>
      <p>This section does not prevent legitimate use of documented interoperability or integration functionality that FAST makes available.</p>

      <h2>8. Scraping, automation and APIs</h2>
      <p>You must not scrape, harvest, crawl or systematically extract FAST data, customer information or service content except through functionality or APIs that FAST expressly makes available for that purpose. Automated access must comply with any documentation, credentials, rate limits and usage restrictions FAST provides.</p>

      <h2>9. Harmful and unlawful content</h2>
      <p>You must not knowingly use FAST to store, transmit or distribute content that is unlawful; materially infringes another person's rights; contains malicious software; facilitates criminal activity; or is used to threaten, harass or exploit another person.</p>
      <p>Normal sporting footage showing lawful competitive play, contact, injuries or disciplinary incidents is not prohibited merely because it depicts those events. Customers remain responsible for handling such footage appropriately.</p>

      <h2>10. Young people and safeguarding</h2>
      <p>Organisation administrators responsible for the commercial FAST account must be at least 18. Organisations may authorise younger staff users where appropriate, but must manage their access and supervision responsibly.</p>
      <p>Customers processing footage or information relating to children or young athletes must apply appropriate privacy and safeguarding standards and must not use FAST in a way that exploits, endangers or unlawfully profiles a child.</p>

      <h2>11. FAST AI and automated functionality</h2>
      <p>Where FAST provides artificial-intelligence, machine-learning, automated tagging, tracking, prediction or generated-analysis functionality, users must treat outputs as analytical assistance rather than guaranteed facts or professional decisions.</p>
      <p>You must not deliberately use FAST AI functionality to make unlawful discriminatory decisions, generate deceptive evidence, impersonate individuals, circumvent safeguarding obligations or process data that you are not entitled to provide to FAST. Additional AI-specific terms or notices may apply as those features are released.</p>

      <h2>12. Competitive and resale use</h2>
      <p>You may use FAST in providing legitimate analysis services for your organisation or clients where your subscription permits that use. You must not resell, sublicense, white-label or make FAST itself available as a competing hosted software service unless FAST has expressly authorised this in writing.</p>

      <h2>13. Confidential and sensitive information</h2>
      <p>Do not submit passwords, payment-card numbers, authentication secrets or other credentials as Customer Content. Customers should use FAST's designated account, billing and security functionality for such information.</p>
      <p>Before uploading confidential sporting or commercial material, the Customer is responsible for confirming that its use of FAST is consistent with any confidentiality obligations it owes to leagues, governing bodies, clubs, athletes, employers or other parties.</p>

      <h2>14. Reporting security or abuse</h2>
      <p>If you discover suspected unauthorised access, a security vulnerability, unlawful content or misuse of FAST, report it promptly to <a href="mailto:contact@fastsportsanalytics.com">contact@fastsportsanalytics.com</a>. Do not exploit a suspected vulnerability or access data beyond what is reasonably necessary to identify and report the issue.</p>

      <h2>15. Enforcement</h2>
      <p>Where FAST reasonably believes this policy has been breached, we may investigate and take proportionate action. Depending on the seriousness and urgency of the issue, this may include warning the Customer, requesting removal of content, restricting a user or device, suspending affected functionality, preserving relevant evidence, or suspending or terminating access in accordance with the Terms of Service.</p>
      <p>FAST may take immediate action where reasonably necessary to protect people, customer data, FAST infrastructure or third parties, or to comply with law. Where appropriate and legally permitted, we will seek to notify the affected Customer.</p>

      <h2>16. Changes to this policy</h2>
      <p>FAST may update this policy as the service, security environment or applicable law develops. Material changes affecting active customers will be handled in accordance with the change provisions in the Terms of Service.</p>

      <h2>17. Contact</h2>
      <p>Questions about acceptable use can be sent to <a href="mailto:contact@fastsportsanalytics.com">contact@fastsportsanalytics.com</a>.</p>
    </section>
  </PageShell>;
}
