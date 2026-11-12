# Record of processing activities (template)

**Controller (typical):** University tenant  
**Processor (typical):** Beta-Tech Labs Co. Limited (hosted mode)  
**Law:** Data Protection and Privacy Act, 2019 (Uganda) - confirm registration status annually  

| # | Activity | Purpose | Data | Lawful basis (draft) | Retention | Recipients |
|---|----------|---------|------|----------------------|-----------|------------|
| 1 | Widget / WhatsApp Q&A | Answer FAQs from approved bank | Question text, language, channel | Public task / legitimate interests (confirm) | `TRANSCRIPT_RETENTION_DAYS` then anonymise | Hosting infra; optional LLM |
| 2 | Knowledge governance | Draft/approve/publish answers | Staff identity, answer versions, audit log | Contract / legitimate interests | While tenant active + audit retention | None external |
| 3 | Evaluation | Quality gate before publish | Golden questions, scores | Legitimate interests | Eval run history | None external |
| 4 | Channel connectivity | Deliver WhatsApp replies | Phone number IDs, encrypted tokens, message ids | Contract | While channel enabled | Meta (WhatsApp Cloud API) |
| 5 | Metering | Cost awareness / invoicing | Token counts, message counts | Legitimate interests / contract | Billing period + statutory | Finance systems (export) |

Update this register whenever a new subprocessors or channel is added.
