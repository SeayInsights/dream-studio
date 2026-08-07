# Regulatory anchors for security review

This document is the canonical reference list of security policies, frameworks, regulations, and standards that may apply to a Dream Studio user's work. The ds-security skill cites this document when surfacing applicable requirements during code review, PRD analysis, and pre-launch checks.

## Tier legend

- 🔴 **Mandatory if in scope** — regulation or law with legal consequences for non-compliance
- 🟠 **De facto mandatory** — can technically be skipped, but skipping costs deals, fails audits, or invites lawsuits
- 🟢 **Should have** — best practice; not strictly required

Apply based on what's in scope for the project at hand: jurisdiction, industry, customer profile, data types handled, deployment target. The ds-security skill walks through scope determination before applying any checks.

## Contents

- [A. Cross-industry trust attestations](#a-cross-industry-trust-attestations-the-audit-layer)
- [B. Payments & financial](#b-payments--financial)
- [C. US federal sector-specific privacy/security](#c-us-federal-sector-specific-privacysecurity)
- [D. US state comprehensive privacy laws](#d-us-state-comprehensive-privacy-laws--20-and-growing)
- [E. US special-purpose state laws](#e-us-special-purpose-state-laws-often-higher-risk-than-the-comprehensive-ones)
- [F. International privacy](#f-international-privacy)
- [G. Cross-border data transfer mechanisms](#g-cross-border-data-transfer-mechanisms)
- [H. Government & defense](#h-government--defense)
- [I. Critical infrastructure & sector](#i-critical-infrastructure--sector)
- [J. Software supply chain & secure SDLC](#j-software-supply-chain--secure-sdlc)
- [K. EU Cyber Resilience Act](#k-eu-cyber-resilience-act-worth-its-own-callout)
- [L. Application security standards](#l-application-security-standards)
- [M. Vulnerability management & disclosure](#m-vulnerability-management--disclosure)
- [N. Identity, access & cryptography](#n-identity-access--cryptography)
- [O. AI-specific](#o-ai-specific)
- [P. Accessibility](#p-accessibility)
- [Q. Marketing/advertising/consumer](#q-marketingadvertisingconsumer)

---

## A. Cross-industry trust attestations (the audit layer)

- 🟠 SOC 1 — financial reporting controls (AICPA)
- 🟠 SOC 2 Type I & II — security, availability, processing integrity, confidentiality, privacy
- 🟢 SOC 3 — public summary version of SOC 2
- 🟠 ISO/IEC 27001 — international ISMS standard
- 🟢 ISO/IEC 27017 — cloud security extension
- 🟢 ISO/IEC 27018 — cloud PII protection
- 🟢 ISO/IEC 27701 — privacy info management extension
- 🟢 ISO/IEC 22301 — business continuity
- 🟢 ISO/IEC 20000 — IT service management
- 🟢 ISO 9001 — quality management
- 🟢 NIST CSF 2.0 — Cybersecurity Framework
- 🟢 NIST SP 800-53 — federal controls catalog
- 🟢 NIST SP 800-171 — controlled unclassified information
- 🟢 CIS Critical Security Controls v8.1
- 🟢 CIS Benchmarks — platform-specific hardening (AWS, Azure, GCP, K8s, Docker, every major OS/DB)
- 🟢 HITRUST CSF — increasingly demanded for healthcare-adjacent
- 🟢 CSA STAR / CCM — Cloud Security Alliance certification
- 🟢 COBIT 2019 — IT governance framework
- 🟢 MITRE ATT&CK / D3FEND — threat modeling reference
- 🟢 Zero Trust Architecture (NIST SP 800-207)

## B. Payments & financial

- 🔴 PCI DSS v4.0.1 — anyone handling card data
- 🔴 PCI PIN, P2PE, 3DS — sub-standards for specific implementations
- 🔴 SOX — public companies, IT general controls over financial reporting
- 🔴 GLBA Safeguards Rule (FTC, updated) — financial services
- 🔴 NYDFS Part 500 — NY financial entities (recently amended)
- 🔴 DORA — EU digital operational resilience (in force Jan 2025)
- 🔴 SEC Cybersecurity Disclosure Rule — 4-business-day material incident disclosure
- 🔴 PSD2 / PSD3 — EU payment services
- 🔴 FFIEC — US banking IT examination handbook

## C. US federal sector-specific privacy/security

- 🔴 HIPAA / HITECH — healthcare
- 🔴 COPPA — under-13 children's data
- 🔴 FERPA — education records
- 🔴 GLBA Privacy Rule — financial
- 🔴 TCPA — calls/SMS
- 🔴 CAN-SPAM — commercial email
- 🔴 ADA Title III — accessibility (courts apply to digital)
- 🔴 Section 508 — federal procurement accessibility
- 🔴 FTC Act §5 — unfair/deceptive practices catch-all
- 🔴 FTC Health Breach Notification Rule
- 🔴 CIPA — Children's Internet Protection Act
- 🔴 VPPA — Video Privacy Protection Act (still alive, lots of pixel-tracking lawsuits)
- 🔴 CFAA — Computer Fraud and Abuse Act
- 🔴 DMCA — copyright (Section 512 safe harbor procedures)

## D. US state comprehensive privacy laws (~20 and growing)

All 🔴 if you have residents in scope:

- California: CCPA / CPRA (enforced by CPPA)
- Virginia: VCDPA
- Colorado: CPA + Colorado AI Act
- Connecticut: CTDPA
- Utah: UCPA
- Texas: TDPSA
- Oregon: OCPA
- Montana: MTCDPA
- Delaware: DPDPA
- Iowa: ICDPA
- Tennessee: TIPA
- Indiana: ICDPA
- New Jersey: NJDPA
- New Hampshire, Kentucky, Maryland, Minnesota, Rhode Island, Nebraska
- (More on the way — track IAPP's tracker)

## E. US special-purpose state laws (often higher risk than the comprehensive ones)

- 🔴 Illinois BIPA — biometrics, private right of action with statutory damages (massive class actions)
- 🔴 Washington My Health My Data Act — broad "consumer health data" + private right of action
- 🔴 Texas CUBI — biometrics
- 🔴 Washington biometric law
- 🔴 NY SHIELD Act — security obligations
- 🔴 California SB-327 — IoT device security
- 🔴 California CalOPPA — privacy policy requirements
- 🔴 California Delete Act
- 🔴 California Age-Appropriate Design Code (AADC)
- 🔴 New York Local Law 144 — automated employment decisions

## F. International privacy

- 🔴 EU GDPR
- 🔴 UK GDPR + Data Protection Act 2018
- 🔴 Swiss FADP
- 🔴 Canada PIPEDA + Quebec Law 25 (strictest in Canada)
- 🔴 Brazil LGPD
- 🔴 China PIPL + DSL + CSL (data triad)
- 🔴 Japan APPI
- 🔴 South Korea PIPA
- 🔴 Singapore PDPA
- 🔴 Thailand PDPA
- 🔴 India DPDP Act 2023
- 🔴 Australia Privacy Act (under reform)
- 🔴 South Africa POPIA
- 🔴 UAE PDPL
- 🔴 Saudi Arabia PDPL
- 🔴 Argentina PDPL, Mexico LFPDPPP

## G. Cross-border data transfer mechanisms

- 🔴 EU-US Data Privacy Framework (post-Schrems II)
- 🔴 Standard Contractual Clauses (SCCs) + Transfer Impact Assessments
- 🟢 Binding Corporate Rules (BCRs)
- 🔴 UK IDTA / UK Addendum
- 🔴 Data localization regimes (China, Russia, India, Vietnam, Indonesia, etc.)

## H. Government & defense

- 🔴 FedRAMP (Low/Moderate/High) — federal cloud
- 🔴 StateRAMP — state cloud
- 🔴 CMMC 2.0 — defense contractors (CUI)
- 🔴 IRS Pub 1075 — federal tax info
- 🔴 CJIS Security Policy — criminal justice
- 🔴 FISMA — federal info systems
- 🔴 ITAR / EAR — export controls
- 🔴 DFARS 252.204-7012 — defense supplier safeguarding

## I. Critical infrastructure & sector

- 🔴 NERC CIP — bulk electric system
- 🔴 TSA Pipeline / Rail directives
- 🔴 NIS2 — EU critical infrastructure (broad scope)
- 🔴 EU CER Directive — physical resilience
- 🔴 UK Cyber Security & Resilience Bill (in progress)
- 🟢 IEC 62443 — industrial control systems
- 🔴 FDA premarket cybersecurity guidance + IEC 62304 — medical devices
- 🔴 DO-178C — avionics software
- 🔴 ISO 26262 — automotive functional safety
- 🟢 IEC 61508 — general functional safety

## J. Software supply chain & secure SDLC

- 🟠 NIST SSDF (SP 800-218) — required for US federal software sellers via self-attestation
- 🟠 SLSA framework (Levels 1–4) — build provenance
- 🟠 SBOM requirements (CycloneDX or SPDX) — mandatory for federal, increasingly for enterprise
- 🟢 Sigstore / in-toto — signing & attestation
- 🟢 OpenSSF Scorecard / Best Practices Badge
- 🟢 CISA Secure by Design pledge
- 🟢 OWASP SAMM — secure development maturity
- 🟢 BSIMM — descriptive benchmark
- 🟢 Microsoft SDL
- 🟢 ISO/IEC 27034 — application security

## K. EU Cyber Resilience Act (worth its own callout)

- 🔴 EU CRA — full application Dec 11, 2027; vuln reporting from Sept 11, 2026. Mandatory security requirements, SBOM, vuln handling, 24-hr exploitation disclosure, CE marking for products with digital elements sold into EU. This is the next GDPR-of-software.

## L. Application security standards

- 🟠 OWASP Top 10 (web)
- 🟠 OWASP API Security Top 10
- 🟠 OWASP ASVS 5.0 — verification standard, Levels 1–3
- 🟠 OWASP MASVS — mobile equivalent
- 🟠 OWASP MASTG — mobile testing guide
- 🟢 OWASP Top 10 for LLM Applications
- 🟢 OWASP ML Security Top 10
- 🟢 OWASP SAMM
- 🟢 CWE / CWE Top 25 — weakness enumeration

## M. Vulnerability management & disclosure

- 🟠 CVE / CVSS — industry baseline
- 🟢 ISO/IEC 29147 (disclosure) and 30111 (handling)
- 🟠 Coordinated Vulnerability Disclosure (CVD) / bug bounty
- 🔴 CISA KEV catalog — federal patch SLAs
- 🟠 VEX (Vulnerability Exploitability eXchange)

## N. Identity, access & cryptography

- 🟠 OAuth 2.0 / 2.1, OIDC, SAML 2.0, SCIM — B2B SaaS table stakes
- 🟢 FIDO2 / WebAuthn / passkeys
- 🟢 FAPI — financial-grade API
- 🟠 NIST SP 800-63-4 — digital identity (IAL/AAL/FAL)
- 🔴 FIPS 140-3 — federal crypto module validation
- 🟠 NIST PQC standards (FIPS 203/204/205) — post-quantum migration
- 🟢 Common Criteria (ISO 15408)

## O. AI-specific

- 🔴 EU AI Act — phased through Aug 2027
- 🟠 NIST AI RMF + Generative AI Profile
- 🟢 ISO/IEC 42001 — AI management system
- 🟢 ISO/IEC 23894 — AI risk management
- 🔴 Colorado AI Act (effective 2026)
- 🔴 NYC LL 144 — automated employment tools
- 🟢 MITRE ATLAS — adversarial ML

## P. Accessibility

- 🔴 WCAG 2.2 (2.1 AA minimum baseline)
- 🔴 ADA Title III
- 🔴 Section 508
- 🔴 EN 301 549 — EU public sector
- 🔴 European Accessibility Act (EAA) — in force June 2025, applies to private sector products/services sold into EU
- 🔴 AODA (Ontario), ACA (Canada federal)

## Q. Marketing/advertising/consumer

- 🔴 CAN-SPAM, CASL (Canada), PECR (UK)
- 🔴 TCPA — calls/SMS
- 🔴 FTC Endorsement Guides — influencer/affiliate disclosure
- 🔴 GDPR ePrivacy / EU Cookie Directive
- 🔴 Global Privacy Control (GPC) signal — must respect under CCPA/CPRA
- 🔴 DSA / DMA — EU platform regulations
- 🔴 UK Online Safety Act
