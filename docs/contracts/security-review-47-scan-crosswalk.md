# Security Review 47-Scan Crosswalk

## Purpose

This crosswalk maps the operator-supplied original 47 enterprise security scan list to the drafted Security Review Scan Catalog.

This document is coverage evidence only. It does not implement scans, run scans, authorize target repo access, add commands, mutate repositories, or replace Work Order approval.

## Source And Catalog References

- Source list: `docs/contracts/security-review-source-47-enterprise-scans.md`
- Draft catalog: `docs/contracts/security-review-scan-catalog.md`
- Profile pack contract: `docs/contracts/security-review-profile-pack-contract.md`

## Coverage Status Values

- `explicit`: the catalog has a direct scan entry for the original item.
- `grouped`: the catalog covers the item as part of a broader scan or scan family.
- `partial`: the catalog covers part of the item, but a clearer scan or split is recommended.
- `deferred_runtime`: execution-oriented coverage should wait for validation profiles and approval.
- `deferred_infrastructure`: infrastructure-specific coverage should wait for target/infrastructure scope.
- `not_applicable_by_default`: the item should not be assumed applicable without target profile evidence.
- `missing`: the catalog does not currently represent the source item well enough.

## Source-To-Catalog Coverage Matrix

| Original # | Original item name | Original domain | Coverage status | Catalog scan ID or IDs | Rationale | Recommended catalog action |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | SQL Injection Detection | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.static.injection_patterns`, `sec.api.input_validation_surface` | Catalog injection and input-validation scans explicitly include query and request-boundary injection risk. | keep |
| 2 | Cross-Site Scripting (XSS) | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.static.xss_output_encoding`, `sec.static.injection_patterns` | Catalog now includes a direct XSS/output-encoding scan alongside the broader injection scan. | keep |
| 3 | Command Injection | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.static.injection_patterns` | Catalog injection scan names shell and interpreter injection risk. | keep |
| 4 | Path Traversal / Directory Traversal | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.static.path_traversal_patterns` | Catalog has a direct path traversal scan. | keep |
| 5 | Insecure Deserialization | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.static.deserialization_patterns` | Catalog has a direct unsafe parsing/deserialization scan. | keep |
| 6 | Hardcoded Credentials & Secrets in Code | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.secrets.high_entropy_patterns`, `sec.config.secret_storage_policy` | Catalog includes high-entropy credential pattern planning and secret storage policy review. | keep |
| 7 | Buffer Overflow / Memory Safety | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.static.memory_safety_boundary_review` | Catalog now includes a direct memory-safety and unsafe-boundary review scan. | keep |
| 8 | Race Conditions & Concurrency Bugs | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.static.concurrency_race_review` | Catalog now includes a direct security-sensitive concurrency and race-condition review scan. | keep |
| 9 | Broken Authentication Logic | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.auth.broken_auth_logic_review`, `sec.auth.access_boundary_review`, `sec.auth.session_cookie_policy`, `sec.auth.password_reset_flow_review` | Catalog now includes a direct broken-authentication logic review plus supporting access/session/recovery scans. | keep |
| 10 | Broken Access Control / Authorization Flaws | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.auth.access_boundary_review`, `sec.auth.role_permission_matrix`, `sec.manual.sensitive_route_review` | Catalog has direct access-boundary, role/permission, and sensitive-route review coverage. | keep |
| 11 | Cryptographic Failures | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.static.crypto_misuse_patterns`, `sec.data.encryption_at_rest_review`, `sec.data.encryption_in_transit_review` | Catalog covers crypto misuse and encryption posture. | keep |
| 12 | Server-Side Request Forgery (SSRF) | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.static.ssrf_request_boundary_review`, `sec.api.input_validation_surface` | Catalog now includes a direct SSRF/request-boundary review scan. | keep |
| 13 | XML External Entity (XXE) Injection | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.static.xxe_parser_review`, `sec.static.deserialization_patterns` | Catalog now includes a direct XXE/parser configuration scan. | keep |
| 14 | Unsafe Reflection / Dynamic Code Loading | SOURCE CODE ANALYSIS (SAST) | explicit | `sec.static.unsafe_eval_exec` | Catalog has a direct unsafe dynamic execution and interpretation scan. | keep |
| 15 | Known Vulnerability Detection (CVE Scanning) | DEPENDENCY & SUPPLY CHAIN (SCA) | explicit | `sec.dependency.vulnerability_inventory` | Catalog has direct vulnerability inventory evidence coverage. | keep |
| 16 | License Compliance Scanning | DEPENDENCY & SUPPLY CHAIN (SCA) | explicit | `sec.dependency.license_policy_review` | Catalog has direct license policy review coverage. | keep |
| 17 | Dependency Freshness & End-of-Life | DEPENDENCY & SUPPLY CHAIN (SCA) | explicit | `sec.dependency.freshness_eol_review`, `sec.manual.dependency_update_risk_review` | Catalog now includes a direct dependency freshness and end-of-life review scan. | keep |
| 18 | Typosquatting & Malicious Package Detection | DEPENDENCY & SUPPLY CHAIN (SCA) | explicit | `sec.dependency.typosquatting_malicious_package_review`, `sec.dependency.provenance_review` | Catalog now includes a direct typosquatting and malicious package review scan. | keep |
| 19 | Software Bill of Materials (SBOM) Generation | DEPENDENCY & SUPPLY CHAIN (SCA) | deferred_runtime | `sec.dependency.sbom_generation_planning`, `sec.release.artifact_provenance_review` | Catalog now has direct SBOM generation planning, but generation remains deferred because it may write artifacts. | defer |
| 20 | Dependency Pinning & Integrity Verification | DEPENDENCY & SUPPLY CHAIN (SCA) | explicit | `sec.dependency.lockfile_integrity`, `sec.dependency.provenance_review` | Catalog directly covers lockfile integrity and provenance. | keep |
| 21 | Git History Secret Scanning | SECRETS & CREDENTIAL SCANNING | deferred_runtime | `sec.secrets.git_history_secret_review`, `sec.secrets.high_entropy_patterns` | Catalog now includes direct git-history secret review planning, deferred because history scans need redaction and artifact controls. | defer |
| 22 | Environment Variable & Config File Audit | SECRETS & CREDENTIAL SCANNING | explicit | `sec.secrets.env_template_drift`, `sec.config.secret_storage_policy` | Catalog has direct environment/config secret posture coverage. | keep |
| 23 | Certificate & Key Management Review | SECRETS & CREDENTIAL SCANNING | explicit | `sec.secrets.certificate_key_management_review`, `sec.data.encryption_in_transit_review` | Catalog now includes direct certificate and key management coverage. | keep |
| 24 | CI/CD Pipeline Secret Exposure | SECRETS & CREDENTIAL SCANNING | explicit | `sec.secrets.cicd_secret_exposure_review`, `sec.release.ci_security_gate_review` | Catalog now includes direct CI/CD secret exposure review coverage. | keep |
| 25 | Container Image Vulnerability Scanning | CONTAINER & IMAGE SECURITY | deferred_runtime | `sec.infra.container_image_vulnerability_review`, `sec.infra.container_config_review` | Catalog now includes direct image vulnerability review planning, deferred because tool/report execution requires approval. | defer |
| 26 | Dockerfile Security Best Practices | CONTAINER & IMAGE SECURITY | explicit | `sec.infra.dockerfile_security_best_practices`, `sec.infra.container_config_review` | Catalog now includes direct Dockerfile best-practice review coverage. | keep |
| 27 | Container Runtime Security Configuration | CONTAINER & IMAGE SECURITY | explicit | `sec.infra.container_config_review`, `sec.infra.runtime_env_policy` | Catalog directly covers container/runtime configuration and runtime environment policy. | keep |
| 28 | Container Registry Security | CONTAINER & IMAGE SECURITY | deferred_infrastructure | `sec.infra.container_registry_security_review`, `sec.dependency.provenance_review`, `sec.release.artifact_provenance_review` | Catalog now includes direct container registry review, deferred until registry/infrastructure scope is approved. | defer |
| 29 | Kubernetes Security Posture (Pod Security) | CONTAINER & IMAGE SECURITY | deferred_infrastructure | `sec.infra.kubernetes_pod_security_review`, `sec.infra.container_config_review`, `sec.infra.cloud_permission_review` | Catalog now includes direct Kubernetes pod security review, deferred until cluster/IaC scope is approved. | defer |
| 30 | Cloud Misconfiguration Detection | INFRASTRUCTURE-AS-CODE (IaC) SECURITY | deferred_infrastructure | `sec.infra.cloud_misconfiguration_review`, `sec.infra.cloud_permission_review` | Catalog now includes direct cloud misconfiguration review, deferred until cloud/IaC scope is approved. | defer |
| 31 | IAM & Least Privilege Analysis | INFRASTRUCTURE-AS-CODE (IaC) SECURITY | deferred_infrastructure | `sec.infra.iam_least_privilege_review`, `sec.infra.cloud_permission_review`, `sec.auth.role_permission_matrix` | Catalog now includes direct IAM and least-privilege review, deferred until identity/infrastructure scope is approved. | defer |
| 32 | Network Security & Segmentation | INFRASTRUCTURE-AS-CODE (IaC) SECURITY | deferred_infrastructure | `sec.infra.network_segmentation_review` | Catalog now includes direct network segmentation review, deferred until network/infrastructure scope is approved. | defer |
| 33 | Encryption Configuration | INFRASTRUCTURE-AS-CODE (IaC) SECURITY | explicit | `sec.data.encryption_at_rest_review`, `sec.data.encryption_in_transit_review` | Catalog directly covers encryption at rest and in transit. | keep |
| 34 | Logging, Monitoring & Audit Trail | INFRASTRUCTURE-AS-CODE (IaC) SECURITY | explicit | `sec.obs.security_logging_review`, `sec.obs.audit_trail_review` | Catalog directly covers logging and audit trail readiness. | keep |
| 35 | Backup & Disaster Recovery Configuration | INFRASTRUCTURE-AS-CODE (IaC) SECURITY | explicit | `sec.manual.backup_restore_security_review`, `sec.data.retention_policy_review` | Catalog covers backup/restore and retention evidence. | keep |
| 36 | Injection Testing (Runtime) | DYNAMIC & RUNTIME TESTING (DAST) | deferred_runtime | `sec.dast.runtime_injection_testing`, `sec.static.injection_patterns`, `sec.api.input_validation_surface` | Catalog now includes direct runtime injection testing planning, deferred until target and validation profiles are approved. | defer |
| 37 | Authentication & Session Testing | DYNAMIC & RUNTIME TESTING (DAST) | deferred_runtime | `sec.dast.auth_session_testing`, `sec.auth.session_cookie_policy`, `sec.auth.password_reset_flow_review` | Catalog now includes direct DAST auth/session testing planning, deferred until credentials and target scope are approved. | defer |
| 38 | API Security Testing | DYNAMIC & RUNTIME TESTING (DAST) | deferred_runtime | `sec.dast.api_security_testing`, `sec.api.input_validation_surface`, `sec.api.rate_limit_review`, `sec.api.webhook_signature_review` | Catalog now includes direct runtime API security testing planning, deferred until endpoint scope is approved. | defer |
| 39 | Security Header Validation | DYNAMIC & RUNTIME TESTING (DAST) | deferred_runtime | `sec.dast.security_header_validation`, `sec.config.security_headers_review` | Catalog now includes direct runtime header validation planning, deferred until deployed URL or response-artifact scope is approved. | defer |
| 40 | TLS/SSL Configuration | DYNAMIC & RUNTIME TESTING (DAST) | explicit | `sec.dast.tls_ssl_configuration_review`, `sec.data.encryption_in_transit_review` | Catalog now includes direct TLS/SSL configuration review coverage. | keep |
| 41 | Business Logic Vulnerability Testing | DYNAMIC & RUNTIME TESTING (DAST) | deferred_runtime | `sec.dast.business_logic_testing`, `sec.manual.abuse_case_review`, `sec.manual.admin_workflow_review` | Catalog now includes direct business-logic test planning, deferred until workflow and account scope are approved. | defer |
| 42 | Regulatory Compliance Mapping (GDPR/HIPAA/PCI/SOC2) | COMPLIANCE, GOVERNANCE & OPERATIONAL SECURITY | explicit | `sec.compliance.regulatory_mapping_review` | Catalog now includes direct compliance mapping coverage without claiming certification. | keep |
| 43 | Data Privacy & PII Detection | COMPLIANCE, GOVERNANCE & OPERATIONAL SECURITY | explicit | `sec.data.pii_inventory_review`, `sec.data.export_classification_review` | Catalog directly covers PII inventory and export classification. | keep |
| 44 | SBOM & Software Supply Chain Attestation | COMPLIANCE, GOVERNANCE & OPERATIONAL SECURITY | explicit | `sec.compliance.sbom_attestation_review`, `sec.release.artifact_provenance_review`, `sec.dependency.provenance_review` | Catalog now includes direct SBOM and supply-chain attestation review coverage. | keep |
| 45 | Security Logging & Alerting Completeness | COMPLIANCE, GOVERNANCE & OPERATIONAL SECURITY | explicit | `sec.obs.security_logging_review`, `sec.obs.incident_handoff_review` | Catalog covers security logging and incident readiness. | keep |
| 46 | Incident Response & Error Handling | COMPLIANCE, GOVERNANCE & OPERATIONAL SECURITY | explicit | `sec.obs.incident_response_error_handling_review`, `sec.obs.incident_handoff_review`, `sec.manual.security_retrospective_review` | Catalog now includes direct incident response and error-handling review coverage. | keep |
| 47 | Dependency & Build Reproducibility | COMPLIANCE, GOVERNANCE & OPERATIONAL SECURITY | explicit | `sec.dependency.lockfile_integrity`, `sec.release.branch_state_evidence`, `sec.release.ci_security_gate_review` | Catalog directly covers lockfile integrity, branch evidence, and release gates. | keep |

## Coverage Summary

| Coverage status | Count |
| --- | ---: |
| `explicit` | 34 |
| `grouped` | 0 |
| `partial` | 0 |
| `deferred_runtime` | 8 |
| `deferred_infrastructure` | 5 |
| `not_applicable_by_default` | 0 |
| `missing` | 0 |

## Recommended Revision Themes

- Preserve runtime and infrastructure deferrals until target, validation, and evidence profiles can safely scope execution.
- Add `source_item_refs` once the catalog moves from draft rows to a structured data shape.
- Ask for human security review of the 35 explicit and 12 deferred mappings before any implementation.
