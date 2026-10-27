# Security Policy

The security of Assured Route and the systems that rely on it is taken seriously. This policy outlines supported versions, vulnerability reporting procedures, and specific security considerations related to LLM routing and invoice processing.

---

## Supported Versions

Security updates and patches are actively maintained for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1.0 | :x:                |

---

## Reporting a Vulnerability

**Please do NOT disclose security vulnerabilities publicly via GitHub Issues, Discussions, or social media.**

### How to Report

1. **GitHub Security Advisories (Preferred)**:
   Navigate to the [Security Advisories](https://github.com/onurozkir/assured-route/security/advisories) page of the repository and click **"New draft security advisory"** to disclose the issue privately.

2. **Email**:
   If you cannot use GitHub Security Advisories, send an encrypted or plain email with the subject line `[SECURITY] Assured Route Vulnerability Report` to:
   **[onurozkir@hotmail.com](mailto:onurozkir@hotmail.com)**

### Information to Include

To help triage and resolve the issue quickly, please provide:
- A clear description of the vulnerability.
- Proof-of-concept (PoC) scripts, steps to reproduce, or sample payloads.
- An assessment of the potential attack vector, severity, and operational impact.
- Any known mitigations or suggested fixes.

### Response Timeline

- **Initial Acknowledgment**: Within 48 hours of receipt.
- **Triage & Status Update**: Within 5 business days, including confirmation of reproducibility and planned remediation steps.
- **Disclosure & Release**: We follow coordinated vulnerability disclosure. A public release and advisory will be coordinated after a patch is ready and tested.

---

## Domain-Specific Security Considerations

When deploying or integrating Assured Route with production pipelines, keep the following security vectors in mind:

### 1. API Keys & Upstream Credentials
- Never hardcode or commit provider API keys or model endpoints to source control.
- Ensure `.env` and runtime secret files remain ignored by Git.
- In production environments, inject credentials using container secrets or a dedicated secrets manager (e.g., AWS Secrets Manager, HashiCorp Vault, Azure Key Vault).

### 2. Untrusted OCR Input & Prompt Injection
- Optical Character Recognition (OCR) text passed to the router originates from external invoices and documents and must be treated as **untrusted user input**.
- Malicious actors may attempt indirect prompt injection via invoice text (e.g., embedding instructions inside invoice line items or notes).
- Assured Route mitigates injection risk by:
  - Enforcing strict JSON schema validation.
  - Employing deterministic grounding validators that cross-verify parsed tokens against source spans.
  - Applying deterministic business arithmetic rules (such as subtotal + tax = total) that no LLM prompt manipulation can bypass.

### 3. PII & Financial Data Confidentiality
- Real invoices contain Personally Identifiable Information (PII) and sensitive financial details.
- Audit logs (`src/assured_route/audit.py`) are intentionally designed with value-free decision logging to prevent inadvertent leakage of invoice line-item details or customer names.
- Ensure network connections to upstream OpenAI-compatible model endpoints use TLS 1.3 encryption.

### 4. Production Hardening
- Assured Route in its repository state serves as a reference architecture and runnable companion.
- Before deploying to internet-facing environments:
  - Put an API Gateway or reverse proxy (e.g., NGINX, Cloudflare) in front of the service.
  - Enforce authentication and authorization (e.g., OAuth 2.0 / JWT tokens).
  - Implement ingress rate limiting and payload size limits to protect against denial-of-service (DoS) attempts.
