# Data Protection Impact Assessment (template)

**Product:** Amakuru  
**Owner organisations:** Beta-Tech Labs Co. Limited / [University name]  
**Status:** Template - confirm with Ugandan counsel before production go-live  

## 1. Processing description

Amakuru answers student/parent/applicant questions from an approved university answer bank via web widget and optional WhatsApp. Questions may be scrubbed, embedded, retrieved against tenant-scoped knowledge, and occasionally sent to an external LLM for grounded composition.

## 2. Data categories

| Category | Examples | Intentional collection? |
|----------|----------|-------------------------|
| Question text | Free-text chat | Yes (service delivery) |
| Incidental PII | Phone, email, NIN, card patterns typed by users | No - scrubbed when detected |
| Staff accounts | Email, password hash, TOTP secret | Yes (admin access) |
| Channel secrets | WhatsApp tokens | Yes (encrypted at rest) |
| Traces / metrics | Scores, latency, tokens, cost estimates | Yes (quality & ops) |

## 3. Necessity and proportionality

- Answers come only from approved bank content.
- Widget privacy notice asks users not to type personal details.
- Retention: `TRANSCRIPT_RETENTION_DAYS` then anonymise.
- Tenant isolation via Postgres RLS.

## 4. Cross-border transfers

If `ALLOW_EXTERNAL_AI_CALLS=true`, scrubbed question text and retrieved approved snippets may be sent to an LLM provider outside Uganda. Document the provider, location, contractual clauses, and university approval here: **[to complete]**.

## 5. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Invented fees/dates | Number firewall; verbatim fallback |
| Cross-tenant leakage | RLS + isolation test suite |
| Prompt injection | Delimited untrusted input; no tools |
| WhatsApp spoofing | Meta signature verification |

## 6. Sign-off

| Role | Name | Date |
|------|------|------|
| University DPO / privacy lead | | |
| Beta-Tech Labs | | |
| Legal counsel (Uganda) | | |
