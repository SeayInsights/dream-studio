# Security Review Scan Catalog

## Purpose

This catalog drafts enterprise security review scans as Security Review Profile Pack data. It classifies the scans by tier, category, scan kind, evidence inputs, and remediation handoff placement.

The catalog is not execution authority. It does not run scans, inspect target repositories, mutate target repositories, install tools, update dependencies, write generated target artifacts, push, stage, commit, open the native runtime database, or bypass Work Order approval.

## Relationship To The Profile Pack Contract

Each row is a catalog-level `ScanDefinition` draft that must conform to `docs/contracts/security-review-profile-pack-contract.md`.

The scan definitions are planning data. A future Work Order may turn selected scan definitions into approved validation or review prompts, but that future Work Order must separately define scope, approval mode, target access, validation commands, evidence requirements, stop conditions, and safe failure behavior.

Source provenance and source-to-catalog coverage are tracked in:

- `docs/contracts/security-review-source-47-enterprise-scans.md`
- `docs/contracts/security-review-47-scan-crosswalk.md`
- `docs/contracts/security-review-scan-definition-schema.md`
- `docs/contracts/security-review-scan-catalog.sample.yaml`
- `docs/contracts/security-review-scan-catalog.yaml`
- `docs/contracts/security-review-catalog-governance.md`

## Tier Model

| Tier | Name | Intended use |
| --- | --- | --- |
| `T0` | Release Gate Essentials | Minimal release-gate review coverage for high-impact security posture. |
| `T1` | Application Security Core | Core application and integration review coverage. |
| `T2` | Assurance Expansion | Broader assurance coverage for infrastructure, data, release, and incident readiness. |
| `T3` | Manual and Contextual Review | Context-heavy review items that require human interpretation or operator decisions. |

## Valid Categories

Catalog entries must use one of the Security Review Profile Pack category IDs:

- `dependency_supply_chain`
- `secrets_exposure`
- `static_code_security`
- `configuration_posture`
- `auth_session_access`
- `api_surface`
- `data_handling_privacy`
- `build_release_integrity`
- `infrastructure_runtime`
- `observability_incident`

## Catalog Data Fields

The catalog table uses this compact documentation shape:

| Field | Meaning |
| --- | --- |
| `Scan ID` | Stable profile-pack scan identifier. |
| `Tier` | `T0`, `T1`, `T2`, or `T3`. |
| `Category` | Security taxonomy category ID. |
| `Scan Kind` | Profile-pack scan kind. |
| `Intent` | Risk or evidence gap the scan is meant to reveal. |
| `Mutation Risk` | Expected mutation-risk class before execution planning. |
| `Network Risk` | Expected network-risk class before execution planning. |
| `Evidence Inputs` | Evidence the scan would need or produce when later approved. |
| `Remediation Handoff` | Existing Handoff Packet family likely used when findings appear. |

## Non-Execution Rules

- Catalog rows are data only and must not be treated as commands.
- Command-based scans may be described as `static_command`, but command templates remain absent from this draft.
- Target repo access requires a future scoped Work Order.
- Networked or mutating scans require separate approval before execution.
- Findings remain evidence; they do not grant mutation authority.
- Risk acceptance requires a file-backed operator decision.

## Catalog Entries

This catalog started as a 47-entry draft and now includes additional non-executing coverage rows from the source-list crosswalk. The source list remains exactly 47 original enterprise items; the catalog may contain more scan definitions when explicit coverage requires split rows.

| Scan ID | Tier | Category | Scan Kind | Intent | Mutation Risk | Network Risk | Evidence Inputs | Remediation Handoff |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `sec.dependency.vulnerability_inventory` | `T0` | `dependency_supply_chain` | `artifact_review` | Inventory known dependency vulnerability evidence from approved reports. | `none` | `external_metadata` | dependency manifests, lockfiles, external report refs | `hold_review` |
| `sec.dependency.lockfile_integrity` | `T0` | `dependency_supply_chain` | `artifact_review` | Review lockfile presence, drift, and reproducibility evidence. | `none` | `local_only` | lockfile refs, branch state, diff proof | `hold_review` |
| `sec.secrets.high_entropy_patterns` | `T0` | `secrets_exposure` | `static_command` | Plan high-entropy and credential-pattern review with redacted evidence. | `none` | `local_only` | redacted match refs, file scope, false-positive notes | `recovery_decision` |
| `sec.secrets.env_template_drift` | `T0` | `secrets_exposure` | `config_review` | Compare expected environment placeholders against committed configuration guidance. | `none` | `local_only` | env example refs, config refs, secret storage notes | `hold_review` |
| `sec.static.injection_patterns` | `T0` | `static_code_security` | `static_command` | Identify source patterns that may allow injection into queries, shells, templates, or interpreters. | `none` | `local_only` | matched source refs, sanitizer refs, limitation notes | `approved_mutation_execution` |
| `sec.static.unsafe_eval_exec` | `T0` | `static_code_security` | `static_command` | Identify unsafe dynamic execution and interpretation surfaces. | `none` | `local_only` | matched source refs, call-path notes, exception notes | `approved_mutation_execution` |
| `sec.auth.access_boundary_review` | `T0` | `auth_session_access` | `manual_review` | Review whether protected actions have explicit authorization boundaries. | `none` | `local_only` | route refs, policy refs, role matrix refs | `hold_review` |
| `sec.auth.session_cookie_policy` | `T0` | `auth_session_access` | `config_review` | Review session cookie, token lifetime, and same-site posture evidence. | `none` | `local_only` | auth config refs, session policy notes | `approved_mutation_execution` |
| `sec.api.cors_policy_review` | `T0` | `api_surface` | `config_review` | Review cross-origin policy, allowed origins, and credential-sharing posture. | `none` | `local_only` | API config refs, route refs, environment assumptions | `approved_mutation_execution` |
| `sec.api.input_validation_surface` | `T0` | `api_surface` | `manual_review` | Review request boundaries for validation, normalization, and schema coverage. | `none` | `local_only` | route refs, schema refs, payload assumptions | `approved_mutation_execution` |
| `sec.release.branch_state_evidence` | `T0` | `build_release_integrity` | `artifact_review` | Verify release gate evidence can cite branch, HEAD, index, and ahead-behind state. | `none` | `local_only` | branch refs, HEAD proof, index proof | `hold_review` |
| `sec.release.forbidden_artifact_write_check` | `T0` | `build_release_integrity` | `artifact_review` | Confirm validation planning accounts for cache, coverage, snapshot, and generated-output writes. | `none` | `local_only` | validation profile refs, generated artifact policy | `hold_review` |
| `sec.dependency.license_policy_review` | `T1` | `dependency_supply_chain` | `external_report_review` | Review dependency license policy evidence and unresolved approval needs. | `none` | `external_metadata` | license report refs, policy refs, exception notes | `hold_review` |
| `sec.dependency.provenance_review` | `T1` | `dependency_supply_chain` | `external_report_review` | Review package provenance, registry trust, and source verification evidence. | `none` | `external_metadata` | provenance report refs, registry policy notes | `hold_review` |
| `sec.config.security_headers_review` | `T1` | `configuration_posture` | `config_review` | Review security header expectations for deployed HTTP surfaces. | `none` | `local_only` | config refs, deployment assumptions, header policy | `approved_mutation_execution` |
| `sec.config.debug_flag_review` | `T1` | `configuration_posture` | `config_review` | Review debug, trace, verbose logging, and unsafe default flags. | `none` | `local_only` | config refs, environment refs, release posture notes | `approved_mutation_execution` |
| `sec.config.secret_storage_policy` | `T1` | `configuration_posture` | `manual_review` | Review whether secrets are stored outside source and generated artifacts. | `none` | `local_only` | secret storage policy, env refs, operator notes | `hold_review` |
| `sec.static.path_traversal_patterns` | `T1` | `static_code_security` | `static_command` | Identify file path handling patterns that may allow traversal or unsafe file access. | `none` | `local_only` | matched source refs, normalization refs | `approved_mutation_execution` |
| `sec.static.crypto_misuse_patterns` | `T1` | `static_code_security` | `static_command` | Identify weak cryptography, unsafe randomness, and key-handling patterns. | `none` | `local_only` | matched source refs, crypto policy refs | `approved_mutation_execution` |
| `sec.static.deserialization_patterns` | `T1` | `static_code_security` | `static_command` | Identify unsafe parsing, deserialization, and object construction surfaces. | `none` | `local_only` | matched source refs, parser boundary notes | `approved_mutation_execution` |
| `sec.auth.role_permission_matrix` | `T1` | `auth_session_access` | `manual_review` | Review role, permission, and capability mapping for protected workflows. | `none` | `local_only` | role matrix refs, workflow refs, gaps | `hold_review` |
| `sec.auth.password_reset_flow_review` | `T1` | `auth_session_access` | `manual_review` | Review account recovery controls, token expiry, and abuse limits. | `none` | `local_only` | flow refs, token policy refs, rate-limit notes | `approved_mutation_execution` |
| `sec.api.rate_limit_review` | `T1` | `api_surface` | `manual_review` | Review rate-limit and abuse-control coverage for exposed routes. | `none` | `local_only` | route refs, throttle policy refs, gap notes | `approved_mutation_execution` |
| `sec.api.webhook_signature_review` | `T1` | `api_surface` | `manual_review` | Review inbound integration signature validation and replay protection. | `none` | `local_only` | webhook refs, secret policy refs, timestamp checks | `approved_mutation_execution` |
| `sec.data.pii_inventory_review` | `T1` | `data_handling_privacy` | `manual_review` | Inventory personal or sensitive data flows and classification gaps. | `none` | `local_only` | data flow refs, schema refs, privacy notes | `hold_review` |
| `sec.data.export_classification_review` | `T2` | `data_handling_privacy` | `manual_review` | Review export outputs for privacy classification and sharing constraints. | `none` | `local_only` | export refs, classification notes, operator constraints | `hold_review` |
| `sec.data.retention_policy_review` | `T2` | `data_handling_privacy` | `manual_review` | Review retention, deletion, backup, and lifecycle policy evidence. | `none` | `local_only` | retention refs, backup refs, deletion notes | `hold_review` |
| `sec.data.encryption_at_rest_review` | `T2` | `data_handling_privacy` | `external_report_review` | Review storage encryption evidence and gaps. | `none` | `external_metadata` | provider report refs, config refs, limitation notes | `hold_review` |
| `sec.data.encryption_in_transit_review` | `T2` | `data_handling_privacy` | `external_report_review` | Review transport encryption posture and certificate evidence. | `none` | `external_metadata` | transport policy refs, certificate refs, deployment notes | `hold_review` |
| `sec.infra.container_config_review` | `T2` | `infrastructure_runtime` | `config_review` | Review container or runtime image configuration when infrastructure is in scope. | `none` | `local_only` | container config refs, runtime assumptions | `approved_mutation_execution` |
| `sec.infra.runtime_env_policy` | `T2` | `infrastructure_runtime` | `config_review` | Review runtime environment variable, permission, and filesystem posture. | `none` | `local_only` | runtime config refs, env policy refs | `approved_mutation_execution` |
| `sec.infra.cloud_permission_review` | `T2` | `infrastructure_runtime` | `external_report_review` | Review cloud or platform permission evidence only when explicitly in scope. | `none` | `external_metadata` | permission report refs, scope notes, operator approval refs | `hold_review` |
| `sec.release.ci_security_gate_review` | `T2` | `build_release_integrity` | `artifact_review` | Review whether CI/release gates cite required security evidence before release. | `none` | `local_only` | CI config refs, gate policy refs, missing evidence | `hold_review` |
| `sec.release.artifact_provenance_review` | `T2` | `build_release_integrity` | `external_report_review` | Review build artifact provenance and source-to-release traceability. | `none` | `external_metadata` | artifact refs, build report refs, release notes | `hold_review` |
| `sec.obs.security_logging_review` | `T2` | `observability_incident` | `manual_review` | Review security-relevant logging coverage without exposing sensitive data. | `none` | `local_only` | log policy refs, event refs, redaction notes | `approved_mutation_execution` |
| `sec.obs.audit_trail_review` | `T2` | `observability_incident` | `manual_review` | Review auditability for sensitive actions and administrative changes. | `none` | `local_only` | audit event refs, actor tracking notes | `approved_mutation_execution` |
| `sec.obs.incident_handoff_review` | `T2` | `observability_incident` | `manual_review` | Review whether incident response handoff evidence is complete and bounded. | `none` | `local_only` | incident template refs, contact refs, escalation notes | `hold_review` |
| `sec.manual.threat_model_review` | `T3` | `static_code_security` | `manual_review` | Review assets, trust boundaries, threats, and controls for the scoped release. | `none` | `local_only` | threat model refs, architecture refs, assumptions | `hold_review` |
| `sec.manual.abuse_case_review` | `T3` | `api_surface` | `manual_review` | Review misuse and abuse cases across public and integration surfaces. | `none` | `local_only` | route refs, user-flow refs, abuse notes | `hold_review` |
| `sec.manual.admin_workflow_review` | `T3` | `auth_session_access` | `manual_review` | Review privileged workflows, approval boundaries, and audit expectations. | `none` | `local_only` | admin flow refs, permission refs, audit refs | `hold_review` |
| `sec.manual.third_party_integration_review` | `T3` | `api_surface` | `manual_review` | Review third-party integration trust, data sharing, and failure posture. | `none` | `external_metadata` | integration refs, vendor report refs, data flow notes | `hold_review` |
| `sec.manual.sensitive_route_review` | `T3` | `auth_session_access` | `manual_review` | Review high-risk routes for access control, validation, and logging expectations. | `none` | `local_only` | route refs, auth refs, logging refs | `approved_mutation_execution` |
| `sec.manual.backup_restore_security_review` | `T3` | `data_handling_privacy` | `manual_review` | Review backup and restore controls for sensitive data and operational continuity. | `none` | `local_only` | backup policy refs, restore evidence refs, gap notes | `hold_review` |
| `sec.manual.dependency_update_risk_review` | `T3` | `dependency_supply_chain` | `manual_review` | Review dependency update risk, exceptions, and follow-up sequencing. | `none` | `external_metadata` | dependency report refs, exception refs, upgrade notes | `hold_review` |
| `sec.manual.vulnerability_exception_review` | `T3` | `build_release_integrity` | `manual_review` | Review unresolved vulnerability exceptions and required operator decisions. | `none` | `local_only` | finding refs, operator decision refs, expiry notes | `recovery_decision` |
| `sec.manual.release_risk_acceptance_review` | `T3` | `build_release_integrity` | `manual_review` | Review release risk acceptance constraints, expiry, and evidence completeness. | `none` | `local_only` | release gate refs, accepted-risk refs, constraints | `hold_review` |
| `sec.manual.security_retrospective_review` | `T3` | `observability_incident` | `manual_review` | Review lessons, unresolved risks, and next Work Order recommendations after security work. | `none` | `local_only` | retrospective refs, finding refs, next prompt refs | `normal_next_work_order` |
| `sec.static.xss_output_encoding` | `T0` | `static_code_security` | `static_command` | Review cross-site scripting risk through output encoding, template sinks, and client-rendered input boundaries. | `none` | `local_only` | source refs, template refs, sanitizer notes | `approved_mutation_execution` |
| `sec.static.memory_safety_boundary_review` | `T0` | `static_code_security` | `manual_review` | Review native, unsafe, binary, or buffer-handling boundaries for memory-safety risk. | `none` | `local_only` | unsafe-code refs, native boundary refs, dependency notes | `hold_review` |
| `sec.static.concurrency_race_review` | `T0` | `static_code_security` | `manual_review` | Review security-sensitive state transitions for race conditions, time-of-check/time-of-use issues, and concurrency bugs. | `none` | `local_only` | state-transition refs, lock/transaction refs, limitation notes | `hold_review` |
| `sec.static.ssrf_request_boundary_review` | `T0` | `api_surface` | `static_command` | Review server-side request construction, URL allowlists, metadata endpoint exposure, and outbound fetch boundaries. | `none` | `local_only` | request-call refs, validation refs, allowlist notes | `approved_mutation_execution` |
| `sec.static.xxe_parser_review` | `T0` | `static_code_security` | `static_command` | Review XML parser configuration, entity expansion settings, and file/network entity resolution boundaries. | `none` | `local_only` | parser refs, config refs, entity-resolution notes | `approved_mutation_execution` |
| `sec.auth.broken_auth_logic_review` | `T0` | `auth_session_access` | `manual_review` | Review authentication state machines, recovery flows, token transitions, and bypass-prone logic. | `none` | `local_only` | auth flow refs, session refs, recovery refs | `hold_review` |
| `sec.dependency.freshness_eol_review` | `T1` | `dependency_supply_chain` | `external_report_review` | Review dependency freshness, end-of-life packages, and upgrade risk evidence. | `none` | `external_metadata` | dependency report refs, lifecycle refs, upgrade notes | `hold_review` |
| `sec.dependency.typosquatting_malicious_package_review` | `T1` | `dependency_supply_chain` | `external_report_review` | Review package name risk, malicious package indicators, registry trust, and provenance anomalies. | `none` | `external_metadata` | package inventory refs, provenance refs, exception notes | `hold_review` |
| `sec.dependency.sbom_generation_planning` | `T2` | `dependency_supply_chain` | `deferred` | Plan software bill of materials generation as a future approved artifact-producing validation step. | `writes_artifacts` | `external_metadata` | SBOM policy refs, output location policy, approval refs | `normal_next_work_order` |
| `sec.secrets.git_history_secret_review` | `T1` | `secrets_exposure` | `deferred` | Plan git-history secret review with redaction and artifact containment before any history scan is executed. | `unknown` | `local_only` | git-history scope, redaction policy, approval refs | `recovery_decision` |
| `sec.secrets.certificate_key_management_review` | `T1` | `secrets_exposure` | `manual_review` | Review certificate, private-key, rotation, expiry, and storage management evidence. | `none` | `local_only` | certificate refs, key storage refs, rotation notes | `hold_review` |
| `sec.secrets.cicd_secret_exposure_review` | `T1` | `secrets_exposure` | `manual_review` | Review CI/CD variables, pipeline logs, workflow configs, and secret propagation boundaries. | `none` | `local_only` | CI config refs, secret policy refs, log exposure notes | `hold_review` |
| `sec.infra.container_image_vulnerability_review` | `T2` | `infrastructure_runtime` | `deferred` | Plan container image vulnerability review as future approved tool/report evidence. | `unknown` | `external_metadata` | image refs, scanner report refs, registry scope | `hold_review` |
| `sec.infra.dockerfile_security_best_practices` | `T1` | `infrastructure_runtime` | `config_review` | Review Dockerfile hardening posture, base-image policy, user mode, and build-stage exposure. | `none` | `local_only` | Dockerfile refs, base-image notes, hardening checklist | `approved_mutation_execution` |
| `sec.infra.container_registry_security_review` | `T2` | `infrastructure_runtime` | `external_report_review` | Review container registry access, provenance, retention, signing, and vulnerability-report posture when registry scope is approved. | `none` | `external_metadata` | registry report refs, access policy refs, provenance refs | `hold_review` |
| `sec.infra.kubernetes_pod_security_review` | `T2` | `infrastructure_runtime` | `config_review` | Review Kubernetes pod security posture, workload privileges, namespaces, and policy evidence when cluster scope is approved. | `none` | `local_only` | manifest refs, policy refs, cluster-scope assumptions | `hold_review` |
| `sec.infra.cloud_misconfiguration_review` | `T2` | `infrastructure_runtime` | `external_report_review` | Review cloud misconfiguration evidence only when cloud target scope and source reports are approved. | `none` | `external_metadata` | cloud report refs, IaC refs, scope notes | `hold_review` |
| `sec.infra.iam_least_privilege_review` | `T2` | `infrastructure_runtime` | `external_report_review` | Review IAM and least-privilege evidence for roles, service accounts, tokens, and permission boundaries. | `none` | `external_metadata` | IAM report refs, role refs, exception notes | `hold_review` |
| `sec.infra.network_segmentation_review` | `T2` | `infrastructure_runtime` | `external_report_review` | Review network segmentation, exposure boundaries, firewall/security-group posture, and private/public route assumptions. | `none` | `external_metadata` | network report refs, topology refs, exposure notes | `hold_review` |
| `sec.dast.runtime_injection_testing` | `T2` | `api_surface` | `deferred` | Plan runtime injection testing as a future approved DAST validation step with target and artifact containment. | `unknown` | `external_service` | target URL approval, test scope, output policy | `normal_next_work_order` |
| `sec.dast.auth_session_testing` | `T2` | `auth_session_access` | `deferred` | Plan runtime authentication and session testing after target scope, credentials, and approval are file-backed. | `unknown` | `external_service` | test account policy, session scope, evidence policy | `normal_next_work_order` |
| `sec.dast.api_security_testing` | `T2` | `api_surface` | `deferred` | Plan runtime API security testing for approved endpoints, payloads, rate limits, and artifact containment. | `unknown` | `external_service` | endpoint scope, payload scope, output policy | `normal_next_work_order` |
| `sec.dast.security_header_validation` | `T2` | `configuration_posture` | `deferred` | Plan runtime security header validation for approved deployed URLs or captured response artifacts. | `unknown` | `external_service` | URL scope, response refs, header policy | `normal_next_work_order` |
| `sec.dast.tls_ssl_configuration_review` | `T2` | `configuration_posture` | `external_report_review` | Review TLS/SSL configuration evidence from approved reports or scoped runtime validation. | `none` | `external_metadata` | certificate refs, protocol report refs, deployment scope | `hold_review` |
| `sec.dast.business_logic_testing` | `T2` | `api_surface` | `deferred` | Plan business-logic vulnerability testing only after workflows, accounts, and action limits are approved. | `unknown` | `external_service` | workflow scope, abuse case refs, account policy | `normal_next_work_order` |
| `sec.compliance.regulatory_mapping_review` | `T2` | `data_handling_privacy` | `manual_review` | Map scoped evidence to regulatory frameworks such as GDPR, HIPAA, PCI, and SOC 2 without claiming certification. | `none` | `local_only` | compliance scope, evidence refs, gap notes | `hold_review` |
| `sec.compliance.sbom_attestation_review` | `T2` | `build_release_integrity` | `external_report_review` | Review SBOM and software supply-chain attestation evidence for release-gate readiness. | `none` | `external_metadata` | SBOM refs, attestation refs, provenance refs | `hold_review` |
| `sec.obs.incident_response_error_handling_review` | `T2` | `observability_incident` | `manual_review` | Review incident-response readiness and security-sensitive error handling without exposing sensitive details. | `none` | `local_only` | incident plan refs, error handling refs, logging refs | `hold_review` |

## Catalog Limitations

- The catalog does not decide which scans are required for a specific target.
- The catalog does not supply target paths, validation commands, secrets, credentials, or tool configuration.
- The catalog does not replace the future Work Order that would approve a scoped security review.
- Several rows intentionally use `manual_review` or `artifact_review` until future phases define safe validation profiles.
