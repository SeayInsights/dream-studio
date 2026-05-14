# Security Review Source 47 Enterprise Scans

## Purpose

This document records the operator-supplied original 47 enterprise security scan list used as source evidence for the Security Review Scan Catalog crosswalk.

This source list is documentation/data only. It does not authorize scan execution, target repo access, target repo mutation, runtime code, CLI commands, dependency changes, or authority expansion.

## Source Provenance

- Source: operator-supplied inline content in Phase 18S.3A.
- Intake Work Order: `wo-dream-studio-018s3a-security-catalog-source-list-intake-crosswalk`.
- Required preservation: domain grouping, numbering, and item names.

## Original 47 Enterprise Security Scan List

DOMAIN 1 — SOURCE CODE ANALYSIS (SAST)

1. SQL Injection Detection
2. Cross-Site Scripting (XSS)
3. Command Injection
4. Path Traversal / Directory Traversal
5. Insecure Deserialization
6. Hardcoded Credentials & Secrets in Code
7. Buffer Overflow / Memory Safety
8. Race Conditions & Concurrency Bugs
9. Broken Authentication Logic
10. Broken Access Control / Authorization Flaws
11. Cryptographic Failures
12. Server-Side Request Forgery (SSRF)
13. XML External Entity (XXE) Injection
14. Unsafe Reflection / Dynamic Code Loading

DOMAIN 2 — DEPENDENCY & SUPPLY CHAIN (SCA)

15. Known Vulnerability Detection (CVE Scanning)
16. License Compliance Scanning
17. Dependency Freshness & End-of-Life
18. Typosquatting & Malicious Package Detection
19. Software Bill of Materials (SBOM) Generation
20. Dependency Pinning & Integrity Verification

DOMAIN 3 — SECRETS & CREDENTIAL SCANNING

21. Git History Secret Scanning
22. Environment Variable & Config File Audit
23. Certificate & Key Management Review
24. CI/CD Pipeline Secret Exposure

DOMAIN 4 — CONTAINER & IMAGE SECURITY

25. Container Image Vulnerability Scanning
26. Dockerfile Security Best Practices
27. Container Runtime Security Configuration
28. Container Registry Security
29. Kubernetes Security Posture (Pod Security)

DOMAIN 5 — INFRASTRUCTURE-AS-CODE (IaC) SECURITY

30. Cloud Misconfiguration Detection
31. IAM & Least Privilege Analysis
32. Network Security & Segmentation
33. Encryption Configuration
34. Logging, Monitoring & Audit Trail
35. Backup & Disaster Recovery Configuration

DOMAIN 6 — DYNAMIC & RUNTIME TESTING (DAST)

36. Injection Testing (Runtime)
37. Authentication & Session Testing
38. API Security Testing
39. Security Header Validation
40. TLS/SSL Configuration
41. Business Logic Vulnerability Testing

DOMAIN 7 — COMPLIANCE, GOVERNANCE & OPERATIONAL SECURITY

42. Regulatory Compliance Mapping (GDPR/HIPAA/PCI/SOC2)
43. Data Privacy & PII Detection
44. SBOM & Software Supply Chain Attestation
45. Security Logging & Alerting Completeness
46. Incident Response & Error Handling
47. Dependency & Build Reproducibility
