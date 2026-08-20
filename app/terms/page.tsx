import type { Metadata } from "next";
import Link from "next/link";
import { PageShell } from "../components/PageShell";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "Commercial terms governing access to and use of FAST Sports Analytics."
};

export default function Terms() {
  return <PageShell>
    <section className="page-hero legal-hero">
      <p className="eyebrow">Legal</p>
      <h1>Terms of Service</h1>
      <p className="lead">The terms governing organisations' purchase of and access to FAST Sports Analytics products and services.</p>
    </section>

    <section className="content-section legal-copy">
      <p><strong>Last updated: 20 August 2026</strong></p>

      <h2>1. About these Terms</h2>
      <p>These Terms of Service ("Terms") govern access to and use of the FAST Sports Analytics website, desktop applications, cloud services, downloads, updates and related services (together, "FAST"). FAST is provided by FAST SPORTS ANALYTICS LTD ("FAST", "we", "us" or "our").</p>
      <p>By creating an organisation account, purchasing a subscription, accepting these Terms on behalf of an organisation, or using FAST after being authorised by an organisation, you agree to these Terms. If you accept them for an organisation, you confirm that you have authority to bind that organisation.</p>

      <h2>2. Business service and account eligibility</h2>
      <p>FAST is primarily a business-to-business sports-analysis service intended for clubs, teams, analysts, coaches, sporting organisations and other professional or organisational users. The organisation administrator who creates, purchases or manages the commercial FAST account must be at least 18 years old.</p>
      <p>An organisation may invite other authorised users, including younger staff members such as 16- or 17-year-olds where appropriate. The organisation is responsible for deciding who should have access, ensuring it has authority to provide that access, assigning suitable roles and permissions, supervising its users, and ensuring their use complies with these Terms and applicable law.</p>

      <h2>3. Accounts and security</h2>
      <p>You must provide accurate account and organisation information and keep it reasonably current. Account credentials are personal to the authorised user and must not be shared except through FAST functionality expressly designed for organisational access.</p>
      <p>The Customer is responsible for activity carried out through its organisation and authorised accounts except to the extent caused by FAST's breach of its obligations. You must promptly notify FAST if you reasonably suspect unauthorised access, compromised credentials or another security incident affecting your FAST account.</p>

      <h2>4. Subscriptions and plans</h2>
      <p>Access to paid FAST functionality is determined by the subscription, products, sports, seats, devices, features and other entitlements associated with the Customer's plan. Current plan descriptions and prices are displayed during purchase or on the FAST website.</p>
      <p>Plans may include Starter, Professional, Enterprise or other offerings introduced by FAST. Different plans may provide different products, numbers of sports, users/seats, devices, support levels and service features. Enterprise or custom arrangements may be subject to an order form or additional written terms.</p>

      <h2>5. Fees, billing and taxes</h2>
      <p>The Customer must pay the fees shown at checkout or otherwise agreed with FAST. Unless stated otherwise at purchase, subscriptions are billed in advance for the selected monthly or annual billing period and payment is processed through FAST's payment provider.</p>
      <p>Prices, tax treatment and currency information will be displayed as applicable to the transaction. Where a price is stated as including an applicable tax, that tax forms part of the displayed total. Where law requires tax to be charged in addition, FAST may add the applicable amount.</p>
      <p>FAST may change subscription prices for future billing periods by giving reasonable advance notice where required by the agreement or applicable law. A price change does not retrospectively alter a billing period already paid for.</p>

      <h2>6. Automatic renewal</h2>
      <p>Unless the purchase flow or applicable order states otherwise, paid subscriptions renew automatically for successive billing periods until cancelled. The Customer authorises FAST and its payment provider to charge the payment method associated with the subscription for renewal fees and applicable taxes.</p>

      <h2>7. Cancellation</h2>
      <p>The Customer may cancel a self-service subscription using the billing-management functionality made available by FAST. Unless FAST expressly states otherwise, cancellation takes effect at the end of the billing period already paid for and the Customer retains its paid service entitlement until that date.</p>
      <p>Cancellation stops future renewal; it does not ordinarily produce a refund for an already-paid billing period except where required by applicable law or expressly agreed by FAST.</p>

      <h2>8. Upgrades and downgrades</h2>
      <p>Upgrades may take effect immediately or as described during the upgrade process and may result in an immediate or prorated charge through the payment provider. A downgrade may be scheduled for a future renewal date where applying it immediately would conflict with existing paid access, seats, devices, sports, products or other entitlements.</p>
      <p>The Customer is responsible for reducing usage to the limits of a downgraded plan before the downgrade takes effect where FAST asks it to do so.</p>

      <h2>9. Failed payments</h2>
      <p>If payment fails or a subscription becomes overdue, FAST may retry payment, provide a grace or recovery period, restrict functionality, suspend access or ultimately terminate the affected subscription. FAST will not treat a temporary payment-processing issue as an instruction to immediately delete Customer Content.</p>
      <p>The 31-day recovery/deletion period described below begins when the relevant service or organisation actually terminates or is deleted, not merely when an individual payment attempt fails.</p>

      <h2>10. Seats, devices, sports and product entitlements</h2>
      <p>The Customer may use FAST only within the limits attached to its subscription or licence. These limits may include authorised users/seats, registered devices, licensed sports, FAST products and particular features.</p>
      <p>The Customer must not deliberately circumvent licence, seat, device, product or sport restrictions. FAST may enforce these limits technically through its cloud licensing and account systems.</p>

      <h2>11. FAST software licence</h2>
      <p>Subject to these Terms and payment of applicable fees, FAST grants the Customer and its authorised users a limited, non-exclusive, non-transferable and revocable right during the applicable subscription period to install, access and use the licensed FAST products for the Customer's internal sports-analysis and related business purposes.</p>
      <p>This is a licence to use FAST, not a sale or transfer of ownership of the FAST software or intellectual property.</p>

      <h2>12. Customer Content</h2>
      <p>"Customer Content" means footage, video, audio, images, clips, teams, squads, player information, event/tagging data, annotations, analysis, templates and other information or material submitted to or created through FAST by or for the Customer.</p>
      <p>As between FAST and the Customer, the Customer retains its ownership and other rights in Customer Content. Using FAST does not transfer ownership of the Customer's match footage or analysis to FAST.</p>
      <p>The Customer grants FAST a non-exclusive right to host, copy, transmit, display, process, convert and otherwise handle Customer Content only to the extent reasonably necessary to provide, secure, support and maintain the FAST services, comply with the Customer's instructions, or meet applicable legal obligations.</p>

      <h2>13. Customer responsibilities for footage and player data</h2>
      <p>The Customer is responsible for ensuring that it has all rights, permissions, notices, lawful bases and other authority required to collect, record, upload, share and analyse Customer Content. This includes responsibility for footage and information concerning players, opposition teams, staff, officials, spectators, children or other identifiable individuals.</p>
      <p>FAST does not grant the Customer rights to footage, league data, club branding, player information or other material owned by third parties.</p>

      <h2>14. Data protection</h2>
      <p>FAST's processing of personal information for its own account, subscription, licensing, security and business purposes is described in the <Link href="/privacy">Privacy Notice</Link>.</p>
      <p>Where FAST processes Customer Personal Data on behalf of the Customer, the <Link href="/dpa">Data Processing Agreement</Link> forms part of these Terms and governs that processing.</p>

      <h2>15. Customer Content after termination or deletion</h2>
      <p>When the relevant FAST service or organisation terminates or is deleted, Customer Content will ordinarily enter a recovery period of up to <strong>31 days</strong>. During this period FAST may retain the content so that the organisation/service can be recovered or reactivated where supported.</p>
      <p>After the recovery period expires, FAST will initiate permanent deletion of Customer Content from active systems in accordance with its deletion procedures. Secure backups may follow a separate deletion cycle and may remain beyond ordinary operational use until they expire.</p>
      <p>The Customer should export any Customer Content it wishes to retain before its access and recovery period expire. FAST may retain limited billing, accounting, tax, fraud-prevention, security, legal or dispute records for longer where required or reasonably necessary.</p>

      <h2>16. Acceptable use</h2>
      <p>The Customer and its users must use FAST lawfully and responsibly. They must not use FAST to infringe intellectual-property, privacy or other rights; upload unlawful material; gain unauthorised access to systems or data; distribute malware; interfere with the operation or security of FAST; circumvent access controls or licensing; or use FAST in a manner that creates material security, legal or operational risk.</p>
      <p>FAST may publish a separate Acceptable Use Policy containing additional operational rules. Where published and incorporated into these Terms, that policy forms part of the agreement.</p>

      <h2>17. Restrictions</h2>
      <p>Except to the extent a restriction is prohibited by applicable law, the Customer must not copy or redistribute FAST software outside authorised use; sell, sublicense or make FAST available as a competing hosted service; remove proprietary notices; attempt to bypass licensing or security controls; or reverse engineer, decompile or disassemble FAST except where applicable law expressly permits that activity despite this restriction.</p>

      <h2>18. FAST intellectual property</h2>
      <p>FAST and its licensors retain all rights, title and interest in the FAST software, services, source code, object code, interfaces, designs, documentation, branding, logos, technology and other FAST intellectual property, together with improvements and updates to them. No rights are granted except those expressly stated in these Terms.</p>
      <p>Customer Content remains subject to section 12 and is not transferred to FAST merely because it is processed through the service.</p>

      <h2>19. Feedback</h2>
      <p>If the Customer voluntarily provides product suggestions or feedback, FAST may use that feedback to develop and improve its products without restriction or payment, provided this does not give FAST ownership of the Customer's confidential information or Customer Content.</p>

      <h2>20. Updates and changes to FAST</h2>
      <p>FAST may issue software updates, security fixes, feature changes and new versions. The Customer may need to install or permit updates to continue using supported versions safely and correctly.</p>
      <p>FAST may change or discontinue features where reasonably necessary for product development, security, legal compliance or service operation. We will seek to give reasonable notice where a change materially reduces paid functionality and advance notice is reasonably practicable.</p>

      <h2>21. Availability, maintenance and beta features</h2>
      <p>FAST aims to provide a reliable service but does not guarantee uninterrupted or error-free availability. Access may be affected by maintenance, updates, internet connectivity, third-party infrastructure, device configuration, security incidents or events outside FAST's reasonable control.</p>
      <p>Features expressly labelled beta, preview, experimental, coming soon or similar may be incomplete, changed or withdrawn and should not be relied upon as production commitments unless FAST expressly agrees otherwise in writing.</p>

      <h2>22. Suspension</h2>
      <p>FAST may suspend an account, user, device or service where reasonably necessary to address non-payment, a security threat, suspected unauthorised use, material breach of these Terms, legal requirements, or risk to FAST, its customers or third parties. Where appropriate and legally permitted, FAST will seek to notify the Customer and allow a reasonable opportunity to resolve the issue.</p>

      <h2>23. Termination</h2>
      <p>Either party may terminate where the other commits a material breach that is incapable of remedy or is not remedied within a reasonable period after notice. FAST may also terminate or suspend immediately where required by law or where continued service would create a serious security, fraud or legal risk.</p>
      <p>Termination does not affect rights or liabilities accrued before termination. Provisions which by their nature should continue, including intellectual-property, payment, confidentiality, liability, dispute and applicable data-retention provisions, survive termination.</p>

      <h2>24. Confidentiality</h2>
      <p>Each party must protect confidential information received from the other and use it only for purposes connected with the FAST relationship, except where disclosure is authorised, required by law, or made to professional advisers or service providers who are subject to appropriate confidentiality obligations.</p>

      <h2>25. Warranties</h2>
      <p>FAST will provide the service with reasonable care and skill. Except as expressly stated in these Terms and to the maximum extent permitted by law, FAST does not warrant that every feature will be uninterrupted, error-free or suitable for every sporting, tactical, employment, medical, safeguarding, scouting or commercial decision.</p>
      <p>FAST analytics and outputs are tools to support professional judgement. The Customer remains responsible for decisions made using FAST and for verifying information where accuracy is critical.</p>

      <h2>26. Liability</h2>
      <p>Nothing in these Terms excludes or limits liability where it would be unlawful to do so, including liability for death or personal injury caused by negligence, fraud or fraudulent misrepresentation, or any other liability that cannot lawfully be excluded or limited.</p>
      <p>Subject to the previous paragraph, neither party will be liable to the other for indirect or consequential loss, or for loss of profits, revenue, anticipated savings, goodwill or business opportunity, except to the extent such exclusion is prohibited by law.</p>
      <p>Subject to liabilities that cannot lawfully be limited and unless an applicable order form expressly states a different cap, each party's aggregate liability arising out of or in connection with FAST during any 12-month period will not exceed the fees paid or payable by the Customer to FAST for the affected services during the 12 months preceding the event giving rise to the claim.</p>
      <p>The liability provisions in this section are intended for business customers and should be read subject to any mandatory rights that applicable law does not permit the parties to exclude.</p>

      <h2>27. Third-party services</h2>
      <p>FAST relies on third-party infrastructure and services for functions such as hosting, networking, email and payment processing. FAST is responsible for its contractual obligations to the Customer but is not responsible for a third party's independent products, websites or services that the Customer chooses to use outside FAST.</p>

      <h2>28. Changes to these Terms</h2>
      <p>FAST may update these Terms to reflect changes in the service, law, security requirements or business operations. For material changes affecting an active paid subscription, FAST will provide reasonable advance notice where required by law or reasonably practicable. Continued use after an updated version takes effect constitutes acceptance where legally effective; where additional express agreement is required, FAST will request it.</p>

      <h2>29. Notices</h2>
      <p>FAST may provide service and contractual notices through the FAST service, the Customer's registered email address or the website where appropriate. The Customer is responsible for maintaining a working email address for its organisation administrator.</p>

      <h2>30. Assignment</h2>
      <p>The Customer may not assign or transfer its agreement with FAST without FAST's prior written consent, not to be unreasonably withheld where appropriate. FAST may assign the agreement as part of a reorganisation, merger, acquisition, financing or sale of all or substantially all of the relevant business, subject to applicable law.</p>

      <h2>31. Entire agreement and severability</h2>
      <p>These Terms, the applicable order or checkout information, the DPA and any policies expressly incorporated into them form the agreement concerning the Customer's use of FAST and supersede earlier discussions on the same subject. If a provision is held invalid or unenforceable, the remaining provisions continue in effect to the extent permitted by law.</p>

      <h2>32. Governing law and courts</h2>
      <p>Unless mandatory law requires otherwise or a separate written enterprise agreement states differently, these Terms and any non-contractual obligations arising from them are governed by the laws of England and Wales. The courts of England and Wales will have exclusive jurisdiction over disputes arising from or connected with these Terms.</p>

      <h2>33. Contact</h2>
      <p>Questions about these Terms can be sent to <a href="mailto:contact@fastsportsanalytics.com">contact@fastsportsanalytics.com</a>.</p>
    </section>
  </PageShell>;
}
