---
source: https://github.com/anthropics/claude-code-security-review
extracted: 2026-05-02
purpose: Custom false positive filtering templates for security reviews
---

# Custom False Positive Filtering

This reference provides templates and examples for customizing false positive filtering in security reviews. Use these patterns to tailor security analysis to your specific environment and threat model.

## Overview

Every organization has unique security requirements, technology stacks, and threat models. Custom filtering instructions allow you to exclude findings that don't apply to your environment while maintaining focus on real vulnerabilities.

## Template Structure

A custom filtering file should contain three main sections:

### 1. HARD EXCLUSIONS
Automatically exclude findings matching these patterns.

### 2. SIGNAL QUALITY CRITERIA
Questions to assess whether a finding represents a real vulnerability.

### 3. PRECEDENTS
Specific guidance for common security patterns in your environment.

## Example Template

```
HARD EXCLUSIONS - Automatically exclude findings matching these patterns:
1. All DOS/resource exhaustion - we have k8s resource limits and autoscaling
2. Missing rate limiting - handled by our API gateway
3. Tabnabbing vulnerabilities - acceptable risk per our threat model
4. Test files (ending in _test.go, _test.js, or in __tests__ directories)
5. Documentation files (*.md, *.rst)
6. Configuration files that are not exposed to users (internal configs)
7. Memory safety in Rust, Go, or managed languages
8. GraphQL introspection queries - we intentionally expose schema in dev
9. Missing CSRF protection - we use stateless JWT auth exclusively
10. Timing attacks on non-cryptographic operations
11. Regex DoS in input validation (we have request timeouts)
12. Missing security headers in internal services (only public-facing services need them)

SIGNAL QUALITY CRITERIA - For remaining findings, assess:
1. Can an unauthenticated external attacker exploit this?
2. Is there actual data exfiltration or system compromise potential?
3. Is this exploitable in our production Kubernetes environment?
4. Does this bypass our API gateway security controls?

PRECEDENTS - 
1. We use AWS Cognito for all authentication - auth bypass must defeat Cognito
2. All APIs require valid JWT tokens validated at the gateway level
3. SQL injection is only valid if using raw queries (we use Prisma ORM everywhere)
4. All internal services communicate over mTLS within the k8s cluster
5. Secrets are in AWS Secrets Manager or k8s secrets, never in code
6. We allow verbose error messages in dev/staging (not production)
7. File uploads go directly to S3 with presigned URLs (no local file handling)
8. All user input is considered untrusted and validated on the backend
9. Frontend validation is only for UX, not security
10. We use CSP headers and strict Content-Type validation
11. CORS is configured per-service based on actual needs
12. All webhooks use HMAC signature verification
```

## PLMarketing/Kroger-Specific Examples

### Retail Data Security

```
HARD EXCLUSIONS - PLMarketing/Kroger Context:
1. Planogram data exposure in internal dashboards - restricted to authenticated users
2. Vendor pricing data in reports - access controlled via Power BI RLS
3. Category management metrics - internal use only, behind SSO
4. Store performance data - aggregated and anonymized in external reports
5. Missing encryption for cached dashboard data - handled by infrastructure

SIGNAL QUALITY CRITERIA - Retail Environment:
1. Does this expose PII (customer data, employee info)?
2. Can this leak competitive pricing or vendor agreements?
3. Is this exploitable outside our corporate network/VPN?
4. Does this bypass SSO or Power BI role-level security?

PRECEDENTS - Retail Analytics:
1. All external dashboards require SSO through corporate identity provider
2. Sensitive pricing data uses Power BI RLS based on user role
3. DAX queries are parameterized through Power BI semantic models
4. File uploads to SharePoint/OneDrive follow corporate DLP policies
5. API keys for external services stored in Azure Key Vault
6. Internal tools may show verbose errors for troubleshooting
7. Test data must not contain real customer or vendor information
```

### Power BI/Analytics Security

```
HARD EXCLUSIONS - BI Development:
1. Missing input validation in DAX measures - Power BI validates data types
2. SQL injection in Power Query - M language parameterization prevents injection
3. XSS in dashboard titles/labels - Power BI sanitizes text rendering
4. CORS issues in embedded reports - handled by Power BI service
5. Rate limiting on refresh operations - controlled by Power BI capacity

PRECEDENTS - Power BI Security Model:
1. Row-level security (RLS) is defined in semantic model, not application layer
2. Embedded reports use app-owns-data or user-owns-data patterns exclusively
3. Direct Query connections use service principal authentication
4. Sensitive columns use column-level security or dynamic masking
5. Export restrictions are enforced via workspace settings
6. Gateway connections use encrypted credentials
```

## Best Practices

1. **Start with defaults**: Begin with the template above and modify based on your environment
2. **Be specific**: Include details about your security architecture
3. **Document assumptions**: Explain why certain patterns are excluded
4. **Version control**: Track changes alongside your code
5. **Team review**: Have security team approve filtering instructions
6. **Regular updates**: Review and update as architecture changes

## Common Customizations

### Technology Stack
- Exclude findings that don't apply to your languages/frameworks
- Document ORM usage that prevents SQL injection
- Note authentication providers and their security guarantees

### Infrastructure
- Document k8s security controls (network policies, resource limits)
- Note API gateway security features (rate limiting, WAF)
- Explain cloud provider security controls (VPC, security groups)

### Compliance Requirements
- Adjust criteria based on regulatory needs (HIPAA, PCI DSS, SOC 2)
- Document data classification and handling requirements
- Note audit trail and logging requirements

### Development Practices
- Reflect team's security practices (code review, SAST/DAST)
- Document security testing in CI/CD pipeline
- Note security training and awareness programs

## Usage in dream-studio

To use custom filtering in security reviews:

1. Create a `.dream/security/false-positives.txt` file in your project
2. Use the template above and customize for your environment
3. Reference it when invoking security review mode
4. Update as you encounter false positives or architecture changes

## References

- [Anthropic Security Review Documentation](https://github.com/anthropics/claude-code-security-review)
- [OWASP False Positive Guidance](https://owasp.org/)
- [CWE/SANS Top 25](https://cwe.mitre.org/top25/)
