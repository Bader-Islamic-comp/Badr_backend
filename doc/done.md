# Done — تغطية المعمارية والخطة

جدول واحد يغطي كل قسم رقمي بـ [`architecture.md`](architecture.md) وكل مكوّن
بـ [`plan.md`](plan.md). لا بند `done` بدون دليل (مسار أو أمر حقيقي). الحالات:
`not_started` / `in_progress` / `draft_ready` / `done_pending_approval` /
`blocked`. يتحقق منه آلياً `scripts/check_progress.py` (من أول ما يُبنى،
المرحلة 4).

بنود كثيرة تحت مرتبطة بتنفيذ RAG تطويري **موجود مسبقاً** قبل هذه المهمة (فرع
`feature/rag-system-and-data-pipeline`)، وليس بعمل هذه الجلسة. علّمتها
`in_progress` (development-only، غير مُعتمد للأطفال بعد) مع دليلها الحقيقي،
تمييزاً عن البنود التي ستُنجَز ضمن تاسكات الكوربس الـ 15.

| id | البند | المرجع | الحالة | الدليل | التاسك | آخر تحديث |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | رؤية المنتج (وثيقة فقط، لا تنفيذ كوربس مرتبط) | architecture §1 | not_started | — | — | 2026-09-27 |
| 2 | افتراضات التخطيط؛ عمر/سوق/منهج مفتوحة (§18 بند 1-4) | architecture §2 | not_started | — | — | 2026-09-27 |
| 3 | مبادئ المنتج (وثيقة فقط) | architecture §3 | not_started | — | — | 2026-09-27 |
| 4 | معمارية Flutter/Unity/Backend — خارج نطاق تاسكات الكوربس | architecture §4 | not_started | — | — | 2026-09-27 |
| 5 | تدفّق المحادثة والصوت — تنفيذ نصّي تطويري موجود، الصوت غير منفَّذ | architecture §5 | in_progress | `src/companion_api/rag/service.py`, `store.py` | — | 2026-09-27 |
| 6 | حوكمة الـ RAG والمحتوى الديني (نظرة عامة) | architecture §6 | not_started | — | 1,2,3,4 | 2026-09-27 |
| 6.2 | سجل المصادر (قرآن مرخّص، تفسير، حديث بحكمه) — 13 مصدراً، كلها `pending_legal` أو `candidate`، ولا شي معتمد | architecture §6.2 | in_progress | `corpus/sources/registry.yaml`; أمر `PYTHONPATH=src python3 -m pytest -q tests/test_corpusprep.py` | 2,3 | 2026-09-27 |
| 6.3a | جلب المصادر والتحقق بـ sha256 والتحقق البنيوي للقرآن (114/6236) ومطابقة الحديث بين مصدرين | architecture §6.3 | in_progress | `scripts/fetch_sources.py`, `src/companion_api/corpusprep/`, `corpus/reports/hadith_crosscheck.md` | 2,9 | 2026-09-27 |
| 6.3 | خط أنابيب الإدخال (تسجيل، تطبيع، تقطيع حسب الوحدة، embeddings) — chunk-v2 على الكوربس الديني (draft)، الموافقة البشرية لسا | architecture §6.3 | draft_ready | `src/companion_api/rag/chunking.py` (`chunk-v2`), `src/companion_api/corpusprep/ingest.py`; أمر `PYTHONPATH=src python3 -m companion_api.rag.pipeline validate corpus/dev-app-help` | 9 | 2026-09-27 |
| 6.4 | سياسة الاستعلام (توجيه، فلترة، hybrid، rerank، توليد، تحقق) — بدون reranker وبدون pgvector بعد | architecture §6.4 | in_progress | `src/companion_api/rag/retriever.py`, `generator.py`, `grounding.py`, `router.py` | 3,4 | 2026-09-27 |
| 6.5 | خلافات الاجتهاد (madhhab) — حقل `madhhab` موجود بالسكيما، بدون منطق فلترة أو محتوى فعلي | architecture §6.5 | not_started | `src/companion_api/rag/types.py` (`Chunk.madhhab`) | 1 | 2026-09-27 |
| 7 | الأمان والحماية — قواعد تطويرية (keywords)، ليست مصنّف معتمد | architecture §7 | in_progress | `src/companion_api/rag/router.py`, `responses.py` | — | 2026-09-27 |
| 8 | الخصوصية وضبط الأهل — خارج نطاق تاسكات الكوربس | architecture §8 | not_started | — | — | 2026-09-27 |
| 9 | التحديات والمكافآت والأزياء — خارج نطاق تاسكات الكوربس | architecture §9 | not_started | — | — | 2026-09-27 |
| 10 | كيانات البيانات الأساسية — خارج نطاق تاسكات الكوربس المباشر | architecture §10 | not_started | — | — | 2026-09-27 |
| 11 | سلوك الفشل — خارج نطاق تاسكات الكوربس | architecture §11 | not_started | — | — | 2026-09-27 |
| 12 | المراقبة والتقييم — تقييم retrieval موجود جزئياً | architecture §12 | in_progress | `src/companion_api/rag/evaluate.py` | 11,12,13,14 | 2026-09-27 |
| 13 | نطاق الـ MVP — قرار منتج، لا تنفيذ كوربس | architecture §13 | not_started | — | — | 2026-09-27 |
| 14 | خارطة طريق التسليم — قرار منتج | architecture §14 | not_started | — | — | 2026-09-27 |
| 15 | الفريق — قرار تنظيمي | architecture §15 | not_started | — | — | 2026-09-27 |
| 16 | المخاطر الرئيسية والتخفيف | architecture §16 | not_started | — | — | 2026-09-27 |
| 17 | مسار التوسّع (Postgres/pgvector لاحقاً) — موثّق كفجوة معروفة، ليس تاسك كوربس مباشر | architecture §17 | blocked | `doc/rag-system.md` §10 (يذكر الفجوة صراحة) | — | 2026-09-27 |
| 18 | قرارات مطلوبة قبل التنفيذ (عمر، سوق، لغة، منهج، صوت، نموذج عمل، أداء) — مفتوحة عمداً، لا تُفترض | architecture §18 | blocked | — | 1,10 | 2026-09-27 |
| p1 | مصادر البيانات وتجهيز الكوربس — الطبقة 0 منزّلة ومتحقَّق منها (قرآن، تفسير، 5 مجموعات حديث)؛ الطبقة 2 (محتوى الطفل) لسا | plan مكوّن 1 | in_progress | `corpus/sources/registry.yaml`, `corpus/canonical/manifest.json`; أمر `python3 scripts/fetch_sources.py` | 1,2,3,9 | 2026-09-27 |
| p2 | الإدخال والتقطيع والـ embeddings — schema v2 / chunk-v2 / norm-v2، الطبقة 0 كاملة والموجة 1 مقطّعة؛ الـ embeddings: المرحلة 5 | plan مكوّن 2 | draft_ready | `scripts/build_corpus.py`, `corpus/reports/ingest_summary.json`; أمر `PYTHONPATH=src python3 -m pytest -q tests/test_rag_chunk_v2.py tests/test_corpusprep_ingest.py` | 9,11 | 2026-09-27 |
| p3 | الاسترجاع — hybrid RRF k=60 موجود، بدون query rewriting ولا reranker بعد | plan مكوّن 3 | in_progress | `src/companion_api/rag/retriever.py` (`hybrid-rrf-v1`) | 11 | 2026-09-27 |
| p4 | التوليد والتحقق — quote-by-reference وverifier موجودان تطويرياً | plan مكوّن 4 | in_progress | `src/companion_api/rag/generator.py`, `grounding.py`, `prompts.py` (`rag-answer-v2`, `grounding-v2`) | 12,13 | 2026-09-27 |
| p5 | بوابة الأمان وموجّه النوايا — خارج نطاق تاسكات الكوربس الـ 15 | plan مكوّن 5 | not_started | — | — | 2026-09-27 |
| p6 | منسّق المحادثة والـ API — خارج نطاق تاسكات الكوربس الـ 15 | plan مكوّن 6 | not_started | — | — | 2026-09-27 |
| p7 | Flutter و Unity — خارج نطاق تاسكات الكوربس الـ 15 | plan مكوّن 7 | not_started | — | — | 2026-09-27 |
| p8 | البيانات والبنية التحتية (Postgres/pgvector) — موثّق كفجوة معروفة، ليس تاسك كوربس مباشر | plan مكوّن 8 | blocked | `doc/rag-system.md` §10 | — | 2026-09-27 |
| p9 | التقييم والمراقبة — recall@4 offline موجود، gold/harmful/dashboard غير مبنية بعد | plan مكوّن 9 | in_progress | `src/companion_api/rag/evaluate.py`؛ أمر `python -m companion_api.rag.evaluate --release <dir> --cases <eval.json>` | 11,12,13,14 | 2026-09-27 |
