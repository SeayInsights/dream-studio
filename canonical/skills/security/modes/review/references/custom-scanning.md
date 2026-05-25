---
source: https://github.com/anthropics/claude-code-security-review
extracted: 2026-05-02
purpose: Custom security scanning category templates for organization-specific vulnerabilities
---

# Custom Security Scanning Instructions

This reference provides templates and examples for extending security scans with organization-specific vulnerability categories. Use these patterns to add industry-specific, compliance-focused, or technology-specific security checks.

## Overview

The default security scan covers common vulnerability categories (SQL injection, XSS, auth issues, etc.). However, organizations often have specific security concerns based on:
- Technology stack (GraphQL, gRPC, Power BI, cloud providers)
- Compliance requirements (GDPR, HIPAA, PCI DSS, SOC 2)
- Industry-specific vulnerabilities (retail, financial services, healthcare)
- Custom frameworks and libraries

Custom scanning instructions extend (not replace) the default security categories.

## Template Structure

Each category should:
- Start with a descriptive header in bold (using `**Category Name:**`)
- List specific vulnerabilities or patterns to check for
- Use clear, actionable descriptions

### Example Format

```
**Category Name:**
- Specific vulnerability or pattern to check
- Another specific issue to look for
- Detailed description of what constitutes this vulnerability

**Another Category:**
- More specific checks
- Additional patterns to identify
```

## Generic Examples

### Compliance-Specific Checks

```
**Compliance-Specific Checks:**
- GDPR Article 17 "Right to Erasure" implementation gaps
- HIPAA PHI encryption at rest violations
- PCI DSS credit card data retention beyond allowed periods
- SOC2 audit trail tampering or deletion capabilities
- CCPA data portability API vulnerabilities
```

### Financial Services Security

```
**Financial Services Security:**
- Transaction replay attacks in payment processing
- Double-spending vulnerabilities in ledger systems
- Interest calculation manipulation through timing attacks
- Regulatory reporting data tampering
- Know Your Customer (KYC) bypass mechanisms
```

### E-commerce Specific

```
**E-commerce Specific:**
- Shopping cart manipulation for price changes
- Inventory race conditions allowing overselling
- Coupon/discount stacking exploits
- Affiliate tracking manipulation
- Review system authentication bypass
```

### Technology-Specific Checks

```
**GraphQL Security:**
- Query depth attacks allowing unbounded recursion
- Field-level authorization bypass through aliasing
- Introspection data leakage in production environments
- Mutation batching leading to race conditions
- Subscription DoS through connection exhaustion

**gRPC Security:**
- Missing TLS configuration for production deployments
- Reflection API enabled in production
- Stream message size limits not configured
- Authentication metadata not validated per-request
- Deadlock potential in bidirectional streaming
```

## Industry-Specific Considerations

The patterns below describe which regulatory anchors apply when extending the default scan for specific industry contexts. See [`regulatory-anchors.md`](../../../references/regulatory-anchors.md) for tier definitions and the full catalog.

**Retail and consumer-facing platforms** should extend the default scan to cover customer data flows, loyalty program handling, and pricing integrity. Applicable anchors include [D. US state privacy laws](../../../references/regulatory-anchors.md#d-us-state-privacy-laws) (CCPA/CPRA, Virginia, Colorado) for data portability and deletion rights, and [C. US federal sector-specific privacy/security](../../../references/regulatory-anchors.md#c-us-federal-sector-specific-privacysecurity) for pharmacy or health-adjacent data (HIPAA). Check for customer PII (loyalty records, patient identifiers, or transaction data) exposure in aggregated reports, price manipulation through cart or discount calculation flaws, and row-level security bypass in BI dashboards (Power BI, Tableau, Looker, Metabase).

**Healthcare platforms** must add PHI-specific checks beyond the default data exposure category. The primary anchor is [C. US federal sector-specific privacy/security](../../../references/regulatory-anchors.md#c-us-federal-sector-specific-privacysecurity): HIPAA/HITECH requires access controls, audit logging, and encryption for all protected health information. Scan for PHI leakage in error messages and logs, missing encryption at rest for health records, audit trail gaps in data modification flows, and role-based access misconfigurations that allow non-treating staff to access patient data.

**Financial services platforms** extend the default scan with transaction integrity and regulatory compliance checks. Key anchors: [B. Payment card industry (PCI DSS)](../../../references/regulatory-anchors.md#b-payment-card-industry-pci-dss--pci-3ds) for cardholder data environment boundary enforcement and cryptographic controls, and [C. US federal sector-specific privacy/security](../../../references/regulatory-anchors.md#c-us-federal-sector-specific-privacysecurity) for GLBA safeguards over non-public personal financial information. Check for transaction replay vulnerabilities, double-spending in ledger systems, cardholder data retention beyond PCI-allowed periods, and regulatory reporting data tampering.

**SaaS platforms** built to SOC 2 Type II requirements should add tenant isolation and audit trail checks to the default scan. Relevant anchors: [A. Cross-industry trust attestations](../../../references/regulatory-anchors.md#a-cross-industry-trust-attestations-the-audit-layer) (SOC 2 CC6.1/CC6.6 logical access and CC7.1/CC7.2 monitoring controls) and [L. Application security standards](../../../references/regulatory-anchors.md#l-application-security-standards) (OWASP ASVS 5.0 Level 2 access control requirements). Scan for cross-tenant data leakage in multi-tenant APIs, insufficient audit logging for security-relevant events, missing authentication on administrative endpoints, and privilege escalation paths in RBAC implementations.

## Power Platform Security

```
**Power Apps Security:**
- Connector permissions granting excessive SharePoint/Dataverse access
- Environment security groups misconfigured allowing external sharing
- Data loss prevention (DLP) policies bypassed through custom connectors
- Formula injection in text input controls executing arbitrary code
- Canvas apps embedded in Teams exposing data to wrong audience
- Service principal usage lacking secret rotation or least privilege
- Gallery controls loading full datasets instead of delegated queries
- Collection variables caching sensitive data in browser memory

**Power Automate Security:**
- Flow run history exposing PII in action inputs/outputs
- HTTP actions calling internal APIs without authentication
- Parse JSON actions vulnerable to injection in dynamic schemas
- Approval workflows lacking multi-factor authentication requirements
- Child flows running with elevated permissions without justification
- Trigger conditions bypassable through direct API calls
- Connections shared across environments without access review
- Desktop flow credentials stored in plain text or weak encryption
```

## Best Practices

1. **Be Specific**: Provide clear descriptions of what constitutes each vulnerability
2. **Include Context**: Explain why something is a vulnerability in your environment
3. **Provide Examples**: Where possible, describe specific attack scenarios
4. **Avoid Duplicates**: Check default categories (Input Validation, Auth, Crypto, Injection, Data Exposure) to avoid redundancy
5. **Keep It Focused**: Only add categories relevant to your codebase
6. **Update Regularly**: Review and update as technology stack and compliance needs evolve

## Default Categories Reference

The default scan already includes:
- **Input Validation**: SQL injection, command injection, XXE, path traversal, SSRF
- **Authentication & Authorization**: Weak passwords, privilege escalation, session management
- **Crypto & Secrets Management**: Weak algorithms, hardcoded secrets, key management
- **Injection & Code Execution**: Code injection, eval usage, deserialization
- **Data Exposure**: Sensitive data in logs, error messages, debug endpoints

Your custom categories should **complement** these, not duplicate them.

## Writing Effective Categories

### Industry-Specific Template

```
**[Industry] Security:**
- [Business process] manipulation attack
- [Sensitive data type] exposure through [mechanism]
- [Regulatory requirement] compliance gap
- [Domain-specific] race condition or timing issue
- [Industry-standard] bypass or circumvention
```

### Technology-Specific Template

```
**[Technology] Security:**
- [Feature] misconfiguration leading to [vulnerability type]
- [API/Component] lacking [security control]
- [Data flow] exposing [sensitive information]
- [Authentication mechanism] bypass through [attack vector]
- [Performance feature] enabling DoS via [mechanism]
```

### Compliance-Focused Template

```
**[Regulation] Compliance:**
- [Regulation Article/Section] implementation gap in [system]
- [Data type] [handling requirement] violation
- [Audit requirement] not enforced in [process]
- [User right] not implemented or bypassable
- [Data transfer restriction] violated in [integration]
```

## Usage in dream-studio

To use custom scanning instructions:

1. Create a `.dream/security/custom-categories.txt` file in your project
2. Use templates above and customize for your environment
3. Reference it when invoking security review mode
4. Start with industry/compliance categories most relevant to your work
5. Add technology-specific checks as you adopt new tools

## Integration with False Positive Filtering

Custom scanning and false positive filtering work together:
- **Custom scanning** adds new vulnerability categories to check
- **False positive filtering** excludes irrelevant findings from results

Example workflow:
1. Add custom retail security categories to catch industry-specific issues
2. Add false positive filtering to exclude findings handled by infrastructure
3. Review results focusing on real vulnerabilities in your context

## References

- [Anthropic Security Review Documentation](https://github.com/anthropics/claude-code-security-review)
- [OWASP Application Security Verification Standard (ASVS)](https://owasp.org/www-project-application-security-verification-standard/)
- [CIS Controls](https://www.cisecurity.org/controls)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [Retail Industry Cybersecurity Resources](https://www.nrf.com/topics/loss-prevention-safety)
