import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "../components/PageShell";

export const metadata: Metadata = {
  title: "Data Processing Agreement",
  description: "FAST Sports Analytics Data Processing Agreement for customer-controlled personal data."
};

export default function DPA() {
  return <PageShell>
    <section className="page-hero legal-hero">
      <p className="eyebrow">Legal</p>
      <h1>Data Processing Agreement</h1>
      <p className="lead">The data-processing terms that apply when FAST processes personal data on behalf of a customer organisation.</p>
    </section>
    <section className="content-section legal-copy">
      <p><strong>Last updated: 20 August 2026</strong></p>
      <p>This Data Processing Agreement ("DPA") forms part of the agreement between FAST SPORTS ANALYTICS LTD ("FAST", "Processor") and the customer organisation using FAST ("Customer", "Controller") where FAST processes Customer Personal Data on the Customer's behalf. Capitalised terms not defined here have the meaning given in the applicable FAST Terms.</p>

      <h2>1. Roles and scope</h2>
      <p>The Customer determines the purposes and means of processing Customer Personal Data submitted to FAST and acts as controller. FAST acts as processor to the extent it processes that data to provide the contracted FAST services on the Customer's documented instructions.</p>
      <p>This DPA does not govern processing for which FAST independently determines the purposes and means, such as FAST's own account administration, billing, licensing, security, fraud prevention, legal compliance and business records. Those activities are described in the <Link href="/privacy">Privacy Notice</Link>.</p>

      <h2>2. Processing instructions</h2>
      <p>FAST will process Customer Personal Data only on documented instructions from the Customer, including instructions contained in the agreement, this DPA, the Customer's configuration and authorised use of FAST, unless FAST is required to process the data by applicable law. Where legally permitted, FAST will inform the Customer before processing required by law.</p>
      <p>If FAST considers that an instruction infringes applicable data-protection law, FAST will inform the Customer without undue delay and may suspend the affected processing while the parties address the issue.</p>

      <h2>3. Confidentiality</h2>
      <p>FAST will ensure that persons authorised to process Customer Personal Data are subject to an appropriate duty of confidentiality and receive access only where required for their responsibilities.</p>

      <h2>4. Security</h2>
      <p>Taking account of the nature of the processing, available technology, implementation costs and the risks to individuals, FAST will maintain appropriate technical and organisational measures designed to protect Customer Personal Data against accidental or unlawful destruction, loss, alteration, unauthorised disclosure or access.</p>
      <p>Measures may include, as appropriate to the relevant FAST service, authentication and access controls, restricted administrative access, password hashing, audit/security logging, infrastructure protections, software-update controls, resilience and recovery measures, and procedures for identifying and responding to security incidents.</p>

      <h2>5. Subprocessors</h2>
      <p>The Customer gives FAST general authorisation to engage subprocessors necessary to provide and support the FAST services. FAST will impose data-protection obligations on subprocessors that are no less protective, in substance, than the obligations applicable to FAST under this DPA where required by law, and FAST remains responsible for the performance of its subprocessor obligations as required by applicable data-protection law.</p>
      <p>FAST's infrastructure may involve providers including Railway, Vercel and Cloudflare where they process Customer Personal Data on FAST's behalf. Other suppliers, such as Stripe, Google/Gmail and GitHub, are used for particular business or technical functions and are included as subprocessors only to the extent they actually process Customer Personal Data on FAST's behalf.</p>
      <p>FAST may update its subprocessors as the service develops. Where applicable law requires prior notice of a new subprocessor, FAST will provide reasonable notice and an opportunity for the Customer to raise a reasonable data-protection objection.</p>

      <h2>6. Data-subject requests</h2>
      <p>Taking into account the nature of the processing, FAST will provide reasonable assistance through appropriate technical and organisational measures to help the Customer respond to requests by individuals exercising their data-protection rights. If FAST receives a request concerning Customer Personal Data for which the Customer is controller, FAST will not independently respond on the merits except as required by law and may direct the requester to the Customer.</p>

      <h2>7. Assistance and compliance</h2>
      <p>Taking into account the nature of processing and information available to FAST, FAST will provide reasonable assistance to the Customer with applicable obligations concerning security of processing, personal-data-breach notifications, data-protection impact assessments and prior consultation with a supervisory authority.</p>

      <h2>8. Personal-data breaches</h2>
      <p>FAST will notify the Customer without undue delay after becoming aware of a personal-data breach affecting Customer Personal Data and will provide information reasonably available to FAST that the Customer requires to meet applicable notification obligations. FAST's notification of an incident is not an admission of fault or liability.</p>

      <h2>9. International transfers</h2>
      <p>FAST may use infrastructure and subprocessors located in, or capable of accessing information from, multiple countries. FAST will not make a restricted transfer of Customer Personal Data where UK data-protection law applies unless an applicable transfer mechanism is in place.</p>
      <p>Where required, this may include UK adequacy regulations, the UK International Data Transfer Agreement, the UK Addendum to approved EU Standard Contractual Clauses, or another lawful safeguard. The parties will provide information and cooperate with transfer-risk/data-protection assessments where required by applicable law.</p>

      <h2>10. Return, recovery and deletion</h2>
      <p>At the end of the service, Customer Personal Data will ordinarily enter a <strong>31-day recovery period</strong>. During that period the data may remain available for account/service recovery or reactivation. Subject to the Customer's lawful instructions and any functionality made available by FAST, the Customer should export information it requires before the recovery period expires.</p>
      <p>After the recovery period FAST will initiate permanent deletion of Customer Personal Data from active systems unless applicable law requires continued storage. Data contained in secure backups may remain until the applicable backup deletion cycle, provided it is protected and not returned to ordinary operational use except where necessary for legitimate disaster recovery.</p>
      <p>Where applicable law gives the Customer a choice between return and deletion at the end of processing, FAST will honour a valid documented choice to the extent technically and legally applicable.</p>

      <h2>11. Information, audits and inspections</h2>
      <p>FAST will make available information reasonably necessary to demonstrate compliance with the processor obligations applicable under this DPA. The Customer may conduct, or appoint an independent auditor to conduct, a reasonable audit where required by applicable data-protection law.</p>
      <p>Audits must be proportionate, protect the security and confidentiality of FAST and other customers, avoid unreasonable disruption, and ordinarily use existing compliance information or remote review before requiring an on-site inspection. Nothing in this section limits a supervisory authority's lawful powers.</p>

      <h2>12. Customer responsibilities</h2>
      <p>The Customer is responsible for the lawfulness, accuracy and quality of Customer Personal Data and its instructions to FAST. This includes establishing an appropriate lawful basis; providing required privacy information; obtaining permissions or consents where required; managing authorised users and access; and ensuring it is entitled to upload and analyse match footage, player information and other Customer Content.</p>
      <p>The Customer must take particular care where Customer Content concerns children or other vulnerable people and must comply with applicable safeguarding, privacy and sports-governance obligations.</p>

      <h2>13. Processing details</h2>
      <p><strong>Subject matter:</strong> hosting, transmitting, storing, displaying and processing Customer Personal Data as necessary to provide FAST sports-analysis, review and related cloud services.</p>
      <p><strong>Duration:</strong> for the period FAST provides the relevant service, followed by the applicable 31-day recovery period and any limited secure backup lifecycle or legally required retention.</p>
      <p><strong>Nature and purpose:</strong> enabling authorised users to upload, create, organise, analyse, review, transmit, download and otherwise use sports-analysis content and associated service functionality.</p>
      <p><strong>Categories of data subjects:</strong> Customer staff and authorised users; analysts, coaches and other sports personnel; athletes/players; opposition participants; officials; and other identifiable people appearing in or associated with Customer Content.</p>
      <p><strong>Types of personal data:</strong> names and identifiers; team/squad and sporting information; match/event data; video, images and audio where present in Customer Content; player tags; clips; annotations; analysis information; and other personal information the Customer chooses to submit through supported FAST functionality.</p>
      <p><strong>Special-category data:</strong> FAST does not require customers to submit special-category personal data as a standard part of the service. If Customer Content nevertheless contains such data, the Customer is responsible for ensuring that its processing is lawful and appropriately instructed and protected.</p>

      <h2>14. Priority and changes</h2>
      <p>If this DPA conflicts with another FAST contractual term specifically concerning FAST's processing of Customer Personal Data as processor, this DPA prevails to the extent of that conflict. FAST may update this DPA where reasonably necessary to reflect changes in law or the service, subject to applicable contractual and legal requirements.</p>

      <h2>15. Contact</h2>
      <p>Data-protection enquiries concerning this DPA can be sent to <a href="mailto:contact@fastsportsanalytics.com">contact@fastsportsanalytics.com</a>.</p>
    </section>
  </PageShell>;
}
