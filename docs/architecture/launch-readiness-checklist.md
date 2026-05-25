# Launch readiness checklist

Canonical reference list of requirements a Dream Studio user should address before a product launch. The future ds-launch / product-readiness skill (Phase 18.4.2) will cite this document when surfacing launch-blockers.

## Tier legend

- 🔴 **Mandatory if in scope** — regulation or law with legal consequences for non-compliance
- 🟠 **De facto mandatory** — can technically be skipped, but skipping costs deals, fails audits, or invites lawsuits
- 🟢 **Should have** — best practice; not strictly required

## Contents

- [1. Legal/foundational docs](#1-legalfoundational-docs-live-on-the-site)
- [2. Privacy & consent mechanics](#2-privacy--consent-mechanics)
- [3. Security baseline](#3-security-baseline-the-engineering-layer)
- [4. Infrastructure & platform](#4-infrastructure--platform)
- [5. App & UX requirements](#5-app--ux-requirements)
- [6. Marketing/growth compliance](#6-marketinggrowth-compliance)
- [7. Payments](#7-payments)
- [8. App store-specific](#8-app-store-specific-if-mobile)
- [9. AI features](#9-ai-features-if-applicable)
- [10. Operational/business readiness](#10-operationalbusiness-readiness)
- [11. Analytics & observability](#11-analytics--observability)
- [12. Pre-launch testing](#12-pre-launch-testing)

---

## 1. Legal/foundational docs (live on the site)

- 🔴 Privacy Policy (jurisdiction-appropriate, covers all data processing, retention, rights)
- 🔴 Terms of Service / Terms of Use
- 🔴 Cookie Policy
- 🔴 Cookie consent banner (region-aware: GDPR opt-in, CCPA opt-out, GPC honored)
- 🟠 Acceptable Use Policy
- 🟠 EULA (for installed software)
- 🔴 DPA template for B2B customers (if you process their data)
- 🔴 Sub-processor list (publicly maintained)
- 🟠 SLA (for paid products)
- 🔴 Refund/return policy (e-commerce)
- 🔴 Shipping policy (physical goods)
- 🔴 Accessibility statement
- 🟠 Security overview / trust page
- 🔴 DMCA notice + designated agent registered with US Copyright Office
- 🔴 Imprint / business identification (required in Germany, others — Impressum)
- 🔴 Contact info that meets jurisdiction requirements
- 🟠 Vulnerability disclosure / security.txt
- 🟢 Responsible AI / AI use disclosure (if AI is in the product)

## 2. Privacy & consent mechanics

- 🔴 Lawful basis for every data flow documented (GDPR Art. 6)
- 🔴 Consent capture, storage, withdrawal mechanism (timestamped, auditable)
- 🔴 Granular cookie/tracker consent (no pre-checked boxes)
- 🔴 "Do Not Sell or Share My Personal Information" link (CCPA)
- 🔴 GPC signal handling
- 🔴 Age gating where required (under-13 = COPPA, under-16 = GDPR-K)
- 🔴 DSAR/DSR handling process (access, deletion, correction, portability, opt-out)
- 🔴 Data retention schedule per data class, enforced at storage layer
- 🔴 Privacy by Design / Default documented
- 🔴 ROPA (Record of Processing Activities) — GDPR Art. 30
- 🔴 DPIA for high-risk processing
- 🔴 EU representative (if non-EU but processing EU residents)
- 🔴 UK representative (same)
- 🔴 Appointed DPO if required
- 🔴 Cross-border transfer mechanism in place (SCCs, DPF, BCRs)

## 3. Security baseline (the engineering layer)

- 🔴 HTTPS everywhere, HSTS, modern TLS (1.2+ / 1.3 preferred)
- 🔴 Valid TLS cert with auto-renewal (Let's Encrypt / cloud provider)
- 🔴 Secure cookie flags (Secure, HttpOnly, SameSite)
- 🔴 Security headers: CSP, X-Frame-Options/frame-ancestors, X-Content-Type-Options, Referrer-Policy, Permissions-Policy
- 🔴 Subresource Integrity for third-party scripts
- 🔴 Input validation & output encoding (XSS prevention)
- 🔴 Parameterized queries (SQLi prevention)
- 🔴 CSRF protection on state-changing endpoints
- 🔴 SSRF protection on outbound requests
- 🔴 Rate limiting + brute-force protection
- 🔴 Bot mitigation / WAF
- 🔴 Secrets in a vault — never in repo, never in env files in repo
- 🔴 Password storage: argon2/bcrypt/scrypt; never plaintext, never reversible
- 🔴 MFA available (TOTP at minimum, WebAuthn/passkeys preferred)
- 🔴 Session management (secure rotation, expiry, logout invalidation)
- 🔴 Authorization checks on every endpoint (not just authentication)
- 🔴 Encryption at rest (database, backups, object storage)
- 🔴 Encryption in transit between internal services
- 🔴 Key management (KMS, rotation)
- 🟠 PII tokenization / field-level encryption for sensitive fields
- 🟠 SSO support for B2B (SAML/OIDC) — major enterprise blocker if missing
- 🟢 SCIM provisioning
- 🔴 Audit logging — who did what, when, immutable, retained
- 🔴 Centralized log aggregation
- 🔴 Monitoring + alerting on auth failures, privilege changes, exfil patterns
- 🟠 Intrusion detection
- 🔴 Backup strategy with tested restores
- 🔴 Disaster recovery plan with RTO/RPO
- 🔴 Incident response plan + runbooks
- 🟠 Tabletop exercises
- 🟠 Penetration test (annual minimum, before major releases)
- 🔴 Vulnerability scanning (SAST, DAST, SCA, container scanning)
- 🟠 Dependency update process (Dependabot/Renovate)
- 🔴 SBOM generation
- 🟠 Signed artifacts / provenance
- 🔴 Patch management process
- 🟠 Bug bounty / vuln disclosure program
- 🟠 DDoS protection
- 🔴 Least-privilege IAM everywhere
- 🔴 No shared accounts; named users + MFA on all admin access
- 🔴 Production access controlled, logged, time-bounded
- 🔴 Separation of dev/staging/prod
- 🔴 No production data in non-prod environments (use synthetic/masked)

## 4. Infrastructure & platform

- 🔴 CIS Benchmark applied to your cloud provider, OS, containers, K8s
- 🔴 Network segmentation
- 🔴 Default-deny firewall/security groups
- 🔴 Bastion / VPN for admin access (not exposed admin panels)
- 🔴 DNS + domain locking, registrar 2FA
- 🟠 DNSSEC
- 🔴 SPF, DKIM, DMARC for email (anti-spoofing)
- 🟢 BIMI for brand
- 🟠 CAA records for cert issuance control
- 🟢 CDN with edge caching
- 🔴 Database backups encrypted, off-site, lifecycle-managed
- 🟠 Multi-region or multi-AZ for production
- 🟠 Infrastructure as code (reviewed, versioned)
- 🟠 Change management process (PR reviews, approvals)

## 5. App & UX requirements

- 🔴 Mobile-responsive
- 🔴 WCAG 2.1 AA minimum (2.2 better)
- 🔴 Keyboard navigable
- 🔴 Color contrast ratios pass
- 🔴 Alt text on all images
- 🔴 Form labels, ARIA where needed
- 🔴 Reduced motion respected (prefers-reduced-motion)
- 🔴 Lighthouse / Core Web Vitals targets
- 🟠 Performance budget (LCP < 2.5s, INP < 200ms, CLS < 0.1)
- 🔴 Cross-browser tested (Chrome, Safari, Firefox, Edge)
- 🔴 Cross-device tested (iOS, Android, desktop)
- 🟠 Internationalization-ready if you'll ever go global
- 🟠 Offline/degraded states handled
- 🔴 404, 500, and error states designed and helpful
- 🔴 Loading and empty states
- 🔴 Favicon, OG tags, Twitter cards
- 🔴 Robots.txt + sitemap.xml
- 🔴 Canonical URLs

## 6. Marketing/growth compliance

- 🔴 Opt-in (not pre-checked) for email/SMS marketing
- 🔴 Visible unsubscribe in every marketing email
- 🔴 Physical mailing address in commercial emails (CAN-SPAM)
- 🔴 Sender identity not deceptive
- 🔴 FTC disclosure on testimonials, endorsements, affiliate links
- 🔴 No dark patterns in subscriptions (FTC Click-to-Cancel rule)
- 🔴 Suppression list respected across all channels
- 🔴 Geographic suppression / opt-out flags propagated through CDP
- 🔴 Cookie/pixel inventory documented (every Meta, Google, TikTok pixel = data sharing)
- 🟠 Server-side tagging where possible
- 🔴 Honor DNT/GPC where required
- 🟠 Marketing claims substantiated (FTC ad substantiation)
- 🔴 Sweepstakes/contest rules legally compliant if running them
- 🔴 Pricing transparency, no hidden fees (FTC "junk fees" rule)

## 7. Payments

- 🔴 PCI DSS scope minimized (use Stripe/Braintree-hosted; don't touch card data directly)
- 🔴 Strong Customer Authentication (SCA) for EU
- 🔴 Sales tax handling (US: economic nexus; EU: VAT OSS)
- 🔴 Subscription disclosures, auto-renew clarity
- 🔴 Receipts, invoices comply with local requirements
- 🟠 Fraud detection
- 🔴 Chargeback handling process

## 8. App store-specific (if mobile)

- 🔴 Apple Privacy Nutrition Labels accurate
- 🔴 App Tracking Transparency prompt where required
- 🔴 Google Play Data Safety section accurate
- 🔴 Comply with platform payment rules (no third-party payments for digital goods)
- 🔴 Age rating accurate
- 🔴 Permissions justified (no requesting what you don't need)
- 🔴 Push notification consent
- 🔴 No private APIs
- 🔴 Crash-free launch (both stores reject crashy apps)

## 9. AI features (if applicable)

- 🔴 Disclosure that AI is being used (EU AI Act, FTC)
- 🔴 No prohibited uses (social scoring, manipulative AI, etc.)
- 🔴 Human oversight where required
- 🔴 Data minimization for training
- 🔴 No training on user data without explicit consent (or contractual right)
- 🔴 Outputs not deceptive (deepfake disclosure)
- 🟠 Bias evaluation documented
- 🟠 Red-team testing
- 🟠 LLM guardrails (prompt injection, PII leakage, jailbreaks)
- 🔴 Logging of AI decisions affecting users
- 🔴 Appeal mechanism for automated decisions (GDPR Art. 22, Colorado AI Act)

## 10. Operational/business readiness

- 🔴 Business entity registered, EIN/equivalent
- 🔴 Liability insurance + cyber insurance
- 🟠 Errors & Omissions / professional liability
- 🔴 Trademark check on name, logo
- 🟠 Trademark filed
- 🔴 Open-source licenses audited (no GPL contamination if you're proprietary)
- 🟠 Patent freedom-to-operate (if relevant)
- 🔴 Vendor DPAs in place (Google, AWS, Stripe, every SaaS that touches PII)
- 🔴 Employee/contractor IP assignment + NDA
- 🔴 Code of conduct / acceptable use enforcement plan
- 🟠 Status page (uptime communication)
- 🟠 Support process (email, helpdesk, SLA)
- 🔴 Breach notification process tested (72-hr GDPR, varying US state windows)
- 🔴 Contact for law enforcement requests
- 🔴 Records retention schedule
- 🟠 Background checks on staff with prod access

## 11. Analytics & observability

- 🟠 Product analytics (with consent-gated PII)
- 🟠 Error tracking (Sentry, etc.)
- 🟠 Performance monitoring (APM)
- 🟠 Uptime monitoring
- 🟠 Real user monitoring
- 🟠 Business metrics dashboard

## 12. Pre-launch testing

- 🔴 Security review / threat model
- 🔴 Penetration test before launch (for any serious B2B)
- 🔴 Load/stress testing
- 🔴 End-to-end test coverage on critical flows
- 🔴 Accessibility audit (axe, Lighthouse, manual screen reader test)
- 🔴 Legal review of all customer-facing copy
- 🟠 Red team / chaos engineering for mature products
