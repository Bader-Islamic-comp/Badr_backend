# Done — تغطية المعمارية والخطة

جدول واحد يغطي كل قسم رقمي بـ [`architecture.md`](architecture.md) وكل مكوّن بـ [`plan.md`](plan.md)
وكل تاسك بـ [`corpus-tasks.md`](corpus-tasks.md). لا بند `done` بدون دليل. الحالات: `not_started` /
`in_progress` / `draft_ready` / `done_pending_approval` / `blocked`. بيتحقق منه
`python3 scripts/check_progress.py`: كل مسار دليل لازم يكون موجود، وكل أمر دليل لازم يشتغل.

بنود `in_progress` بدون تاسك (—) هي تنفيذ RAG تطويري موجود قبل هاي المهمة، مش من شغل هاي الجلسة.

| id | البند | المرجع | الحالة | الدليل | التاسك | آخر تحديث |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | رؤية المنتج (وثيقة، لا تنفيذ كوربس) | architecture §1 | not_started | — | — | 2026-09-27 |
| 2 | افتراضات التخطيط؛ العمر والسوق والمنهج مفتوحة | architecture §2 | not_started | — | — | 2026-09-27 |
| 3 | مبادئ المنتج (وثيقة) | architecture §3 | not_started | — | — | 2026-09-27 |
| 4 | معمارية Flutter/Unity/Backend — خارج تاسكات الكوربس | architecture §4 | not_started | — | — | 2026-09-27 |
| 5 | تدفّق المحادثة — نصّي تطويري موجود، الصوت غير منفَّذ | architecture §5 | in_progress | `src/companion_api/rag/service.py`, `src/companion_api/store.py` | — | 2026-09-27 |
| 6 | حوكمة الـ RAG: النطاق وسياسة المصادر (مسودات، ولا شي معتمد) | architecture §6 | draft_ready | `doc/governance/scope.md`, `doc/governance/source-policy.md` | 1,2 | 2026-09-27 |
| 6.1 | مسؤولية الحوكمة: مراجعين مؤهلين وتعارض مصالح (قالب؛ القائمة فاضية) | architecture §6.1 | draft_ready | `doc/governance/reviewer-policy.md`, `corpus/governance/reviewers.yaml` | 4 | 2026-09-27 |
| 6.2 | سجل المصادر وجدول الحقوق — 15 مصدراً، كلها `pending_legal` | architecture §6.2 | draft_ready | `corpus/sources/registry.yaml`, `doc/governance/rights-clearance.md`; `python3 scripts/rights_table.py` | 2,3 | 2026-09-27 |
| 6.3 | خط الإدخال: جلب بـ sha256، تحقق القرآن 114/6236، مطابقة الحديث، chunk-v2 | architecture §6.3 | draft_ready | `scripts/fetch_sources.py`, `src/companion_api/corpusprep/ingest.py`, `corpus/reports/hadith_crosscheck.md`; `PYTHONPATH=src python3 -m pytest -q tests/test_corpusprep.py tests/test_corpusprep_ingest.py tests/test_rag_chunk_v2.py` | 9 | 2026-09-27 |
| 6.3b | إصدارات ثابتة للقراءة فقط، rollback بخطوة، وعزل طارئ | architecture §6.3 | draft_ready | `src/companion_api/governance/releases.py`, `doc/governance/releases.md`; `PYTHONPATH=src python3 -m pytest -q tests/test_governance.py` | 5 | 2026-09-27 |
| 6.3c | مسار المراجعة البشرية وسجل التدقيق بـ hash chain | architecture §6.3 | draft_ready | `scripts/review.py`, `src/companion_api/governance/audit.py`, `doc/governance/review-workflow.md`; `python3 scripts/verify_audit.py` | 6,7 | 2026-09-27 |
| 6.4 | سياسة الاستعلام — تطويري، بدون reranker ولا pgvector | architecture §6.4 | in_progress | `src/companion_api/rag/retriever.py`, `src/companion_api/rag/grounding.py`, `src/companion_api/rag/router.py` | — | 2026-09-27 |
| 6.5 | خلافات الاجتهاد — حقل `madhhabScope` موجود وفاضي عمداً | architecture §6.5 | not_started | `src/companion_api/rag/types.py` | 1 | 2026-09-27 |
| 7 | الأمان والحماية — قواعد تطويرية، مش مصنّف معتمد | architecture §7 | in_progress | `src/companion_api/rag/router.py`, `src/companion_api/rag/responses.py` | — | 2026-09-27 |
| 8 | الخصوصية وضبط الأهل — خارج تاسكات الكوربس | architecture §8 | not_started | — | — | 2026-09-27 |
| 9 | التحديات والمكافآت — خارج تاسكات الكوربس | architecture §9 | not_started | — | — | 2026-09-27 |
| 10 | كيانات البيانات — لا بيانات أطفال بالـ vector store | architecture §10 | not_started | — | 15 | 2026-09-27 |
| 11 | سلوك الفشل: المحتوى المخترق → عزل ورجوع للإصدار السابق | architecture §11 | draft_ready | `scripts/rollback.py` | 5 | 2026-09-27 |
| 12 | المراقبة والتقييم: مجموعة تقييم + dashboard؛ الـ embedding blocked | architecture §12 | draft_ready | `scripts/eval_retrieval.py`, `reports/retrieval/history.jsonl` | 12,13,14 | 2026-09-27 |
| 13 | نطاق الـ MVP — قرار منتج | architecture §13 | not_started | — | — | 2026-09-27 |
| 14 | خارطة الطريق — قرار منتج | architecture §14 | not_started | — | — | 2026-09-27 |
| 15 | الفريق — قرار تنظيمي | architecture §15 | not_started | — | — | 2026-09-27 |
| 16 | المخاطر: إعادة المراجعة ومحفّزاتها | architecture §16 | draft_ready | `doc/governance/re-review-policy.md`, `scripts/due_for_review.py` | 8 | 2026-09-27 |
| 17 | مسار التوسّع (pgvector لاحقاً) — خارج النطاق بقرار المستخدم | architecture §17 | blocked | `doc/rag-system.md` | — | 2026-09-27 |
| 18 | قرارات قبل التنفيذ — مفتوحة عمداً | architecture §18 | blocked | — | 1,10 | 2026-09-27 |
| p1 | مصادر البيانات: الطبقة 0 منزّلة ومتحقَّق منها | plan مكوّن 1 | draft_ready | `corpus/sources/registry.yaml`, `corpus/canonical/manifest.json`; `python3 scripts/fetch_sources.py` | 2,3 | 2026-09-27 |
| p1b | محتوى الطفل (الطبقة 2) — هيكل وقوالب ومدقق؛ النص بشري | plan مكوّن 1 | draft_ready | `corpus/drafts/age_band/schema.json`, `corpus/drafts/age_band/WRITING_GUIDE.md`; `python3 scripts/age_band.py check` | 10 | 2026-09-27 |
| p2 | الإدخال والتقطيع — schema v2 / chunk-v2 / norm-v2، الطبقة 0 والموجة 1 | plan مكوّن 2 | draft_ready | `scripts/build_corpus.py`, `corpus/reports/ingest_summary.json`, `corpus/aliases.yaml`, `corpus/candidate/hadith_selection.yaml` | 9 | 2026-09-27 |
| p2b | اختيار الـ embedding — blocked: القرص ممتلئ؛ ADR proposed | plan مكوّن 2 | blocked | `doc/adr-0005-embedding-selection.md` | 11 | 2026-09-27 |
| p3 | الاسترجاع — hybrid RRF موجود، بدون إعادة صياغة ولا reranker | plan مكوّن 3 | in_progress | `src/companion_api/rag/retriever.py` | — | 2026-09-27 |
| p4 | التوليد والتحقق — تطويري | plan مكوّن 4 | in_progress | `src/companion_api/rag/generator.py`, `src/companion_api/rag/grounding.py` | — | 2026-09-27 |
| p5 | بوابة الأمان — خارج التاسكات الـ 15 | plan مكوّن 5 | not_started | — | — | 2026-09-27 |
| p6 | المنسّق والـ API — خارج التاسكات الـ 15 | plan مكوّن 6 | not_started | — | — | 2026-09-27 |
| p7 | Flutter و Unity — خارج التاسكات الـ 15 | plan مكوّن 7 | not_started | — | — | 2026-09-27 |
| p8 | البيانات والبنية التحتية (pgvector) — خارج النطاق | plan مكوّن 8 | blocked | `doc/rag-system.md` | — | 2026-09-27 |
| p8b | لا محتوى أطفال بالـ vector store | plan مكوّن 8 | not_started | — | 15 | 2026-09-27 |
| p9 | التقييم: gold (310)، harmful (151)، dashboard | plan مكوّن 9 | draft_ready | `corpus/eval/gold.jsonl`, `corpus/eval/harmful.jsonl`, `reports/retrieval/index.html`; `PYTHONPATH=src python3 -m pytest -q tests/test_eval_retrieval.py` | 12,13,14 | 2026-09-27 |
