# WARDEN Audit Scorecard
**Repository:** `.`
**Total Score:** `47/100`
**Grade:** `F`
**Profile Signature:** `6c454dff`

## Layer 1 (Mechanical Checks) - Score: 39
- **Coverage:** 78.5%
- **Lint Errors:** 155
- **Complexity:** 3.1 avg
- **Leaks:** 3
- **Security Findings:** 7
- **Resilience Findings:** 3
- **Vulnerable Dependencies:** 0

## Layer 2 (LLM Rubric Evaluator) - Score: 60
### 🤖 LLM Entegrasyonu & Prompt Güvenliği
- **Level:** 6/10
- **Justification:** Prompt sanitization ve injection koruma mekanizmaları uygulandı. Model fallback zinciri ve hata yönetimi yapılandırıldı.
- **Cited Evidence:** core/utils/prompt_sanitizer.py, core/services/rubric.py
### 🔀 Eşzamanlılık & Yarış Durumu Güvenliği
- **Level:** 6/10
- **Justification:** Asenkron asyncio.gather ve concurrency semaphore sınırlamaları mevcut. Thread-safe önbellek kilit mekanizması eklendi.
- **Cited Evidence:** core/services/orchestrator.py, core/services/package.py