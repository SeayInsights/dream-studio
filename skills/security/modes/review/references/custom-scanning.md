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

## PLMarketing/Kroger-Specific Examples

### Retail Analytics Security

```
**Retail Data Security:**
- Competitive pricing data exposure in reports or exports
- Vendor agreement terms leaked through aggregated metrics
- Store-level PII in aggregated dashboards (employee schedules, performance)
- Category management insights accessible to unauthorized roles
- Planogram data exported without vendor permission controls
- Sales forecast data exposed before official release
- Supplier cost data visible outside procurement team
- Store comparison reports revealing strategic expansion plans

**Power BI Security:**
- Row-level security (RLS) bypass through DAX injection in measures
- Sensitive columns exported via "Analyze in Excel" without masking
- Workspace permissions granting broader access than intended
- Embedded report tokens not expiring or lacking scope restrictions
- DirectQuery connections exposing database schema to end users
- Custom visuals loading untrusted external scripts
- Dataset refresh credentials stored with excessive permissions
- Sharing links generated without expiration dates
- Gateway connections using service accounts with admin rights
- Personal workspace content promoted to production without review

**Data Pipeline Security:**
- ETL processes running with excessive database permissions
- Transformation logic exposing PII in error logs
- Incremental refresh patterns leaking row counts or ranges
- Data lineage metadata revealing sensitive source systems
- Staging tables accessible to report developers
- Connection strings or credentials in Power Query M code
- Dataflow entities missing RLS enforcement before consumption
- Scheduled refresh failures exposing connection details in emails
```

### Kroger Client-Specific Checks

```
**Kroger Data Handling:**
- Customer loyalty data (Kroger Plus) exposed in analytics
- PII in transaction logs (names, addresses, payment methods)
- Prescription data (pharmacy) not segregated with HIPAA controls
- Employee data (schedules, wages) accessible outside HR systems
- Vendor pricing below negotiated floors due to calculation errors
- Product recall data leaked before public announcement
- Store security incident data in reports without proper access control
- Fuel rewards calculation manipulation allowing point inflation

**Retail Operations Security:**
- Inventory management API allowing unauthorized stock adjustments
- Price override mechanisms lacking audit trail or approval workflow
- Promotional pricing applied outside authorized date ranges
- Shrink reporting data accessible to store-level users
- Labor scheduling data revealing staffing patterns to competitors
- Perishable goods markdown timing exploitable for arbitrage
- Self-checkout bypass patterns not flagged in analytics
- Loss prevention camera feeds accessible via insecure endpoints
```

### Compliance for Retail Industry

```
**Retail Compliance:**
- SOC 2 Type II audit trail gaps in data modification logs
- CCPA "Do Not Sell" flags not respected in marketing pipelines
- GDPR consent records missing or not linked to customer profiles
- PCI DSS cardholder data environment (CDE) boundary violations
- State privacy law variations (California, Virginia, Colorado) not handled
- Data retention policies not enforced (transaction logs, marketing lists)
- Third-party vendor data sharing without proper DPAs
- Cross-border data transfer violations (EU, Canada)
- Children's data (COPPA) in loyalty programs without parental consent
- Biometric data (time clocks, security) lacking Illinois BIPA compliance
```

### Microsoft Power Platform Security

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
