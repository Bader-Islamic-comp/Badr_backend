# سجل التقدّم — تاسكات الكوربس

سجل زمني لكل خطوة: الوقت، المرحلة، الخطوة، النتيجة، الملفات المتغيّرة. يُحدَّث
بعد كل خطوة فعلية، ولا يُعاد ترتيبه بأثر رجعي.

| الوقت (UTC) | المرحلة | الخطوة | النتيجة | الملفات المتغيّرة |
| --- | --- | --- | --- | --- |
| 2026-09-27 | 0 | استكشاف Badr_backend (src/، doc/، corpus/، tests/، tools/، pyproject.toml، AGENTS.md) | فهم كامل لنظام RAG التطويري الموجود (18 وحدة بـ `src/companion_api/rag/`)، صيغة الكوربس (schema v1)، صيغة الإصدارات (manifest+chunks+vectors)، الإعدادات (env vars)، وnaming الاختبارات | — |
| 2026-09-27 | 0 | تشغيل الاختبارات كخط أساس قبل أي تعديل | `539 passed` (`PYTHONPATH=src python3 -m pytest -q`) | — |
| 2026-09-27 | 0 | فحص توفّر PyYAML/pytest/httpx/requests/jsonschema بالبيئة، وفحص الاتصال بالإنترنت | كلها متوفرة عالمياً (لا `.venv` بعد)؛ الاتصال يعمل (اختُبر مع tanzil.net)؛ لا مفتاح API لأي مصدر متوفر حالياً | — |
| 2026-09-27 | 0 | نقل `architecture.md` و`plan.md` من الجذر إلى `doc/` وإضافة ملاحظة provenance بكل منهما (لا مراجع أخرى بالمستودع كانت تشير لمسارهما القديم) | نقل ناجح، لا كسر لأي مرجع | `doc/architecture.md` (جديد، منقول)، `doc/plan.md` (جديد، منقول) |
| 2026-09-27 | 0 | إنشاء `doc/corpus-tasks.md`: 15 تاسكاً (8 حوكمة + 7 pipeline/eval) بكل الحقول المطلوبة، وقسم Execution plan (شو موجود / شو رح تضيف ووين / 6 تعارضات موثّقة بين plan.md والكود) | ملف كامل، كل التاسكات `not_started` | `doc/corpus-tasks.md` (جديد) |
| 2026-09-27 | 0 | إنشاء `doc/done.md`: جدول تغطية لكل قسم بـ architecture.md (1–18) وكل مكوّن بـ plan.md (1–9)، مع دليل حقيقي لكل بند `in_progress` | ملف كامل، لا بند `done` بدون دليل | `doc/done.md` (جديد) |
| 2026-09-27 | 0 | إنشاء `doc/progress-log.md` (هذا الملف) | — | `doc/progress-log.md` (جديد) |
| 2026-09-27 | 0 | commit `a863eff` (نقل المراجع + ملفات التتبّع) | 539 passed | — |
| 2026-09-27 | 1 | قرارات المستخدم على التعارضات 1–6 | انسجّلت بـ `doc/corpus-tasks.md` (جدول "قرارات التعارضات") | `doc/corpus-tasks.md` |
| 2026-09-27 | 1 | فحص المصادر: Tanzil (نموذج التنزيل `/pub/download/index.php`)، alquran.cloud، quran.com، fawazahmed0/hadith-api، AhmedBaset/hadith-json، mhashim6/Open-Hadith-Data | sunnah.com وdorar.net رجعوا 403 (ومحتاجين مفتاح)؛ الباقي شغّال. تنزيل Tanzil ثابت (نفس sha256 مرتين) | — |
| 2026-09-27 | 1 | قرار (6): التفسير الميسّر عبر alquran.cloud = `candidate` (صفحة الشروط 404، ما في ترخيص منشور) | مخزّن بس ما بيدخل أي release | `corpus/sources/registry.yaml` |
| 2026-09-27 | 1 | قرار (5): مصدر ثانٍ مستقل للبخاري ومسلم = mhashim6 (أصله islamware، ترقيم مختلف، ODbL). النووية: AhmedBaset للتحقق فقط (ما في ترخيص). رياض الصالحين والأدب المفرد: مصدر واحد (AhmedBaset) = `single_source` | — | `corpus/sources/registry.yaml` |
| 2026-09-27 | 1 | قرار (6): `corpus/raw/` و`corpus/canonical/**/*.jsonl` خارج git (نص طرف ثالث، والتراخيص كلها `pending_legal`)؛ الموجود بـ git هو `manifest.json` بالـ sha256 لكل ملف مولّد | الملفات بتتولّد من جديد بـ `fetch_sources.py` | `.gitignore` |
| 2026-09-27 | 1 | قرار (6): إضافة `pyyaml>=6,<7` لـ `pyproject.toml` | — | `pyproject.toml` |
| 2026-09-27 | 1 | بناء `src/companion_api/corpusprep/` (registry, fetch, quran, hadith, build) و`scripts/fetch_sources.py` | النص المقدّس منسوخ حرفياً من الملف المنزّل (تحقّقت: 6236/6236 آية و7580/7580 بخاري مطابقة بايت ببايت) | `src/companion_api/corpusprep/*.py`, `scripts/fetch_sources.py` |
| 2026-09-27 | 1 | أول تشغيل `--record` (13 مصدراً، ~36MB، 16 ثانية) | sha256 + retrieved_at مسجّلين؛ القرآن 114/6236 مطابق لمرجعين | `corpus/sources/registry.yaml`, `corpus/canonical/` |
| 2026-09-27 | 1 | مشكلة: مسلم 2004 "بلا مقابل" بالتشغيل الأول. السبب: islamware بيجمع أكثر من رواية تحت رقم واحد. الحل: مقياس containment وحالة `contained_in_secondary`، و`text_differs` إذا Dice أو containment ≥ 0.6 | مسلم: بلا مقابل 2004 → 38 | `src/companion_api/corpusprep/hadith.py`, `build.py` |
| 2026-09-27 | 1 | قرار (6): `text_normalized` = `norm-v1` (الموجود بـ `rag/normalize.py`) على النص البسيط؛ جدول مقابلة الرسم العثماني = المرحلة 2. `narrator` = null إلا إذا المصدر بيعطيه منظّماً (AhmedBaset: بالإنجليزي) | ما في استخراج راوٍ من المتن بالتخمين | `quran.py`, `hadith.py` |
| 2026-09-27 | 1 | اختبار التلاعب: تعديل بايت بملف raw منسوخ | exit 2 مع رسالة "modified after download" | — |
| 2026-09-27 | 1 | `--refresh`: أول مرة فشل مصدر واحد بخطأ شبكة عابر، وثلاث تشغيلات بعدها نجحت (13/13 `verified`). قرار (6): إعادة محاولة لأخطاء الشبكة فقط (3 مرات)، وعدم تطابق sha256 بيفشل فوراً | — | `src/companion_api/corpusprep/fetch.py` |
| 2026-09-27 | 1 | قرار المستخدم (1): تعديل `plan.md` لـ `7-9`/`10-11` مع ملاحظة | 9 أسطر | `doc/plan.md` |
| 2026-09-27 | 1 | اختبارات: `tests/test_corpusprep.py` (16) + كل المشروع | 555 passed | `tests/test_corpusprep.py` |
| 2026-09-27 | 1 | تحديث `corpus-tasks.md` (تاسك 2 و3 → in_progress، نتائج المرحلة 1) و`done.md` (p1، 6.2، 6.3a) | `check_progress.py` لسا ما انبنى (المرحلة 4) | `doc/corpus-tasks.md`, `doc/done.md` |
| 2026-09-27 | 1b | فحص عينة 50 من اختلافات مسلم: بحث شامل على كل المصدر الثاني | مش إزاحة ترقيم (نفس المقابل 50/50)؛ السبب واو منفصلة (48/50) ورسم بدون ألف بـ islamware | — |
| 2026-09-27 | 1b | إصلاح: رؤية مقارنة `crosscheck-norm-v1` + مطابقة مدخل مقسوم على أرقام متتالية (±3) + ملف mapping | مسلم: اختلاف نص 1109→54، بلا مقابل 38→9؛ البخاري: 205→133، 68→67 | `src/companion_api/corpusprep/hadith.py`, `build.py`, `scripts/fetch_sources.py`, `corpus/reports/hadith_number_mapping.csv` |
| 2026-09-27 | 1b | فحص ضد الإيجابيات الكاذبة: كل توافق جديد بالتطبيع القديم | 0 من 14677 تحت 0.6 containment | — |
| 2026-09-27 | 1b | عينة 20 بخاري + 20 مسلم من الباقي | اختلاف لفظ حقيقي (1–6 كلمات غالباً)؛ بيضل لمراجع | — |
| 2026-09-27 | 1b | اختبارات جديدة (واو/ألف، span) + كل المشروع | 557 passed | `tests/test_corpusprep.py` |
| 2026-09-27 | 1b | الأسئلة القانونية الأربعة بقسم منفصل تحت Rights clearance، وقرارات الموجة 1 تحت تاسك 9 | — | `doc/corpus-tasks.md` |
| 2026-09-27 | 2 | schema v2 + chunk-v2 + norm-v2 بنفس الـ pipeline (قرارات المستخدم 2 و3) | chunk-v1 بيتقرأ (اختبار)؛ اختباران قديمان انعدّلوا عمداً: `schemaVersion: 2` صار صالح (الاختبار صار يستعمل 3)، والـ manifest صار `norm-v2`/`chunk-v2` | `src/companion_api/rag/types.py`, `corpus.py`, `chunking.py`, `normalize.py`, `tests/test_rag_corpus.py`, `tests/test_rag_pipeline.py` |
| 2026-09-27 | 2 | قرار (6): معرّفات القطع الأبناء بنفس صيغة `<doc>#<n>` (مرقّمة بعد الآباء) لأن عقد الـ API (`contracts/openapi-v1.json`) بيقبل هاي الصيغة بس | ولا تغيير بعقد الـ API | `chunking.py` |
| 2026-09-27 | 2 | جدول الرسم العثماني مشتق من محاذاة نصّي Tanzil (مش من الذاكرة) | 750 مدخل؛ تطابق الكلمات 90.5% → 97.5% | `src/companion_api/corpusprep/rasm.py`, `src/companion_api/rag/data/rasm_map.tsv` |
| 2026-09-27 | 2 | قرار (6): مقاطع الآيات من ركوعات Tanzil (556) مقسومة لـ 1–8 آيات و≤180 كلمة | 1054 مقطعاً، كل آية بمقطع واحد (تحقق آلي) | `src/companion_api/corpusprep/segments.py` |
| 2026-09-27 | 2 | قرار (6): النص المرجعي (tier 0/1 بـ sourceRefs) مستثنى من كشف التكرار، لأن التكرار حقيقي (آية مكررة، تفسير لعدة آيات) | الحديث المكرّر بيتعالج بالتجميع | `src/companion_api/rag/corpus.py` |
| 2026-09-27 | 2 | تجميع الحديث بالمتن (Dice ≥ 0.85 بعد "صلى الله عليه وسلم") | 14940 → 14112 مجموعة، أكبرها 7 (فحصتها يدوياً: نفس الحديث) | `src/companion_api/corpusprep/cluster.py` |
| 2026-09-27 | 2 | ربط النووية: يشترط أن التخريج داخل نص النووي يسمّي المجموعة. خطأ أول: "ومسلم" بواو ملتصقة ما انقرأت → انصلح | 24 → 28 مربوطة، 1 needs_check، 13 غير مربوطة | `cluster.py` |
| 2026-09-27 | 2 | عبارات البحث للـ 40 حديث: مطابقة كلمة بكلمة فشلت مع السوابق (و/ف) → مطابقة نصية على التطبيع. "من أحق الناس بحسن صحابتي" مش بلفظ البخاري 5971 (بدون "الناس") → نقلتها لمسلم (6500) | 40/40 نجحوا بالفحص | `candidates.py`, `corpus/candidate/hadith_selection.yaml` |
| 2026-09-27 | 2 | الأجزاء الحرفية فشلت أول مرة لأن المدقق بيحوّل نص الوحدة لـ NFC → الأجزاء كمان NFC | 0 أخطاء | `src/companion_api/rag/corpus.py` |
| 2026-09-27 | 2 | `scripts/build_corpus.py` → `corpus/layer0` و`corpus/wave1` (خارج git) + `pipeline build` لـ wave1 بـ hashing | layer0: 16220 وثيقة / 28560 قطعة؛ wave1: 184 / 1106؛ 0 أخطاء؛ release انبنى وتحقّق | `scripts/build_corpus.py`, `.gitignore` |
| 2026-09-27 | 2 | الأسئلة الافتراضية: blocked — ولا موديل مسموح منزّل (llama3.1/mistral مش مراجَعين) | الحقل جاهز، التوليد بانتظار قرار | — |
| 2026-09-27 | 2 | اختبارات: `test_rag_chunk_v2.py` (7) + `test_corpusprep_ingest.py` (11) + كل المشروع | 575 passed | `tests/` |
| 2026-09-27 | 3 | schema.json + 99 قالب فاضي (59 مشهد + 40 حديث) + مدقق + WRITING_GUIDE.md | الفحص: 99 ملف، 198 نسخة فاضية، 0 فشل | `corpus/drafts/age_band/`, `src/companion_api/corpusprep/age_band.py`, `scripts/age_band.py` |
| 2026-09-27 | 3 | قرار (6): كشف النص المقدس بـ 5 كلمات متتالية مقابل كل القرآن وكل حديث البخاري/مسلم/النووية، مع استثناء الـ 5-grams الموجودة بأكثر من 50 حديث (صيغ) | المدقق بيطبع المواضع بس، بدون النص | `age_band.py` |
| 2026-09-27 | 3 | قرار (6): `jsonschema` تبعية تشغيل | — | `pyproject.toml` |
| 2026-09-27 | 3 | اختبارات `test_age_band.py` (7) + كل المشروع | انظر السطر التالي | `tests/test_age_band.py` |
| 2026-09-27 | 3 | كل المشروع | 582 passed | — |
| 2026-09-27 | 4 | سجل تدقيق بـ hash chain + `verify_audit.py` | كشف التعديل والحذف وإعادة الترتيب (اختبار)؛ الإضافة بترفض سجل مكسور | `src/companion_api/governance/audit.py`, `scripts/verify_audit.py` |
| 2026-09-27 | 4 | مسار المراجعة (`review.py`) + `reviewers.yaml` فاضي عمداً | ما في موافقة ممكنة لحد ما Mousa يسمّي المراجعين | `src/companion_api/governance/review.py`, `scripts/review.py`, `corpus/governance/` |
| 2026-09-27 | 4 | قرار (6): ما في admin router بالـ backend → الواجهة موثّقة بس | endpoints مقترحة بتستدعي نفس الدوال | `doc/governance/review-workflow.md` |
| 2026-09-27 | 4 | إصدارات ثابتة: `build_release.py` / `rollback.py` فوق `rag.release`؛ مؤشر `current_release` مقبول بـ `COMPANION_RAG_RELEASE` | تجربة: wave1-dev-1 → wave1-dev-2 → rollback لـ wave1-dev-1؛ 5 أحداث سليمة | `src/companion_api/governance/releases.py`, `src/companion_api/rag/release.py`, `src/companion_api/config.py` |
| 2026-09-27 | 4 | قرار (6): سجلّا تدقيق (محتوى بـ git، إصدارات محلي مع `releases/`) بنفس الآلية | — | — |
| 2026-09-27 | 4 | `due_for_review.py` على wave1-dev-1 | 1106/1106 `embedding_changed` (hashing مقابل qwen3-embedding) | `src/companion_api/governance/due.py`, `scripts/due_for_review.py` |
| 2026-09-27 | 4 | ملفا ترخيص مسجّلين كمصدرين (sha256) عشان جدول الحقوق ينقل الشروط حرفياً | 15 مصدراً بالـ registry | `corpus/sources/registry.yaml` |
| 2026-09-27 | 4 | مسودات السياسات: scope، source-policy، rights-clearance (مولّد)، reviewer-policy، review-workflow، releases، re-review-policy | كلها draft، المالك Mousa al-Rashdan | `doc/governance/*.md`, `scripts/rights_table.py` |
| 2026-09-27 | 4 | `check_progress.py`: أول تشغيل كشف 5 تعارضات حقيقية (حالات تاسكات 4،5،8،11 ما تحدّثت) → انصلحت | 0 تعارض، 6 أوامر دليل اشتغلت | `scripts/check_progress.py`, `doc/done.md`, `doc/corpus-tasks.md` |
| 2026-09-27 | 4 | اختبارات `test_governance.py` (14) + كل المشروع | 596 passed | `tests/test_governance.py` |
| 2026-09-27 | 4 | خطأ: نتائج المطابقة والتجميع كانت بتتغيّر بين التشغيلات (ترتيب الـ set بيتأثر بـ hash randomization) → كسر التعادل بالموقع | نفس الـ sha256 مع PYTHONHASHSEED=1 و2؛ الأرقام الرئيسية ما تغيّرت | `src/companion_api/corpusprep/hadith.py`, `cluster.py` |
| 2026-09-27 | 5 | gold: 62 نية × 5 صيغ = 310 سؤال اصطناعي؛ المراجع انحلّت لقطع wave1 (0 مرفوض) | pending كلها | `corpus/eval/gold_source.yaml`, `corpus/eval/gold.jsonl`, `scripts/build_eval.py` |
| 2026-09-27 | 5 | harmful: 151 سؤال بـ 8 فئات (حديث موضوع موصوف بلا نص، ضيق غير مفصّل، بيانات مخترعة) | pending كلها | `corpus/eval/harmful_source.yaml`, `corpus/eval/harmful.jsonl` |
| 2026-09-27 | 5 | **مشكلة: القرص ممتلئ 100% (2.2 GB فاضي من 233)**؛ ولا sentence-transformers؛ ~3 GB RAM فاضي | BGE-M3 / e5-large / Qwen3-Embedding / reranker blocked؛ ما حذفت شي برا المستودع | — |
| 2026-09-27 | 5 | قرار (6): nomic-embed-text (موجود محلياً) كخط أساس dense مش مرشّح | R@5 0.052: موديل إنجليزي ما بيفيد العربي | `scripts/eval_retrieval.py` |
| 2026-09-27 | 5 | eval: bm25 R@5 0.287 / MRR 0.210؛ hybrid-hashing R@5 0.306؛ عربيزي وإنجليزي 0.000 lexical | كل عتبات الاعتذار ≤ 0.51 balanced | `reports/retrieval/history.jsonl` |
| 2026-09-27 | 5 | خطأ بالعتبة: كانت تقع على أقل عيّنة موجبة → نقاط منتصف بين الدرجات (اختبار كشفه) | — | `src/companion_api/evaluation/retrieval.py` |
| 2026-09-27 | 5 | dashboard ثابت بدون إنترنت، انفحص بصرياً (Chrome headless)، صلّحت حجم النص وتداخل التسميات | — | `reports/retrieval/index.html` |
| 2026-09-27 | 5 | ADR-0005 proposed: ولا موديل انختار؛ hybrid RRF k=60 باقي | — | `doc/adr-0005-embedding-selection.md` |
| 2026-09-27 | 6 | `write_release` = بوابة القبول الوحيدة + `chunkIds` بالـ manifest + `scan()` | — | `src/companion_api/rag/release.py`, `src/companion_api/rag/types.py` |
| 2026-09-27 | 6 | قرار (6): الوثائق الحقيقية بصيغة v1 (بدون sourceIds) ما عادت قابلة للإصدار؛ `pipeline build` بياخد `--registry` | تعديل fixtures اختبارين قديمين ليستشهدوا بمصدر مسجّل (بدل تخفيف القاعدة) | `src/companion_api/rag/pipeline.py`, `tests/test_rag_pipeline.py`, `tests/test_rag_runtime.py` |
| 2026-09-27 | 6 | `scan_index.py` + `test_no_child_content.py` (24) | wave1-dev-3 نظيف؛ wave1-dev-1 (قبل القائمة) مكشوف | `scripts/scan_index.py`, `tests/test_no_child_content.py` |
| 2026-09-27 | 6 | كل المشروع + check_progress كامل (9 أوامر دليل) | 623 passed؛ 0 تعارض | — |
| 2026-09-27 | B1 | git: كل الـ commits على branch `corpus-tasks`؛ `main` رجع لـ bd15d42؛ push رُفض (403: momenalhamza بدون صلاحية كتابة على Bader-Islamic-comp/Badr_backend) | محتاج صلاحية أو fork | — |
| 2026-09-27 | B1 | تنزيل: qwen3-embedding:0.6b (Ollama)، bge-m3 (Ollama ثم HF)، multilingual-e5-large، bge-reranker-v2-m3 | القرص 34 → ~25 GB فاضي | — |
| 2026-09-27 | B1 | الأسئلة الافتراضية: 552 (3 لكل قطعة من 184: فصحى، عامية، عربيزي) كتبتها بعد قراءة كل مقطع؛ فحص الـ 5-grams رفض 4 كانت بتقتبس لفظ آيات → أعدت صياغتها | `generated: true`، ما بتنعرض للطفل | `corpus/candidate/retrieval_questions.json`, `scripts/build_corpus.py` |
| 2026-09-27 | B1 | خطأ: bge-m3 عبر Ollama بيرجّع NaN (HTTP 500) على هالنص حتى بدون تشكيل (39/60) → تشغيله عبر transformers (BAAI/bge-m3، CLS) | — | `src/companion_api/evaluation/models.py` |
| 2026-09-27 | B1 | خطأ: Ollama رفض دفعات فيها نصوص طويلة → قص مدخل الـ embedding لـ 350 كلمة (الأجزاء الحرفية بتغطي الباقي) + دفعات تنقسم عند الخطأ | — | `scripts/eval_retrieval.py` |
| 2026-09-27 | B1 | الذاكرة: 3 GB فاضي؛ Ollama حاجز 2.4 GB → `ollama stop`؛ الموديلات bf16 وواحد بكل مرة، والـ reranker بيتحمّل آخر شي | — | `scripts/eval_retrieval.py`, `models.py` |
| 2026-09-27 | B1 | ملاحظة: bm25+q قفز لـ R@5 0.671 من 0.287 — مشكوك: نفس الكاتب (أنا) كتب gold والأسئلة الافتراضية → تسرّب | لازم gold مستقل قبل ما نعتمد الرقم | — |
| 2026-09-27 | B2 | الوكيل B: `.claude/agents/corpus-reviewer.md`؛ 15 دفعة (567 بند) كل دفعة وكيل جديد بدون سياق؛ الوكيل المخصّص ما انسجّل بهالجلسة فاستخدمت general-purpose بتعليمات الملف | 567/567؛ 0 مشاكل schema؛ 0 كتابة برا `corpus/reviews/` | `corpus/reviews/ai_prereview/`, `scripts/prereview_batches.py` |
| 2026-09-27 | B2 | قيد: بعض وكلاء B ما لقوا Grep/Glob (Read بس) فخفّضوا الثقة ببعض البنود | مسجّل بـ reasons | — |
| 2026-09-27 | B2 | مراجع خارجي (LiteLLM): ما في `.env` ولا مفتاح مزوّد → تخطّيت | — | — |
| 2026-09-27 | B2 | B لقى: 2:259 مش عن إبراهيم (fail)؛ حديث الخمسين صلاة صحيح وموصوف كموضوع (flag)؛ سؤال "إماطة الأذى صدقة" قطعته ما فيها الطريق (5 fail)؛ الإصدار بيقبل مصادر pending_legal (flag سياسة)؛ ۞ و۩ موجودين رغم "بدون علامات" | الوصف بالـ registry انصلح (النص ما تغيّر)؛ الباقي بحزم القرار | `corpus/sources/registry.yaml` |
| 2026-09-27 | B3 | حالة `cleared` (بس عبر apply_decisions)؛ المنشور بيحتاج كل المصادر cleared؛ review.py ما عاد بيقبل approve/reject بدون decision_id | — | `src/companion_api/governance/decisions.py`, `releases.py`, `review.py`, `corpusprep/registry.py` |
| 2026-09-27 | B3 | `apply_decisions.py` + `decisions.yaml` فاضي + 6 حزم قرار | اختبارات 11 | `doc/decisions/`, `scripts/apply_decisions.py`, `scripts/build_decision_packages.py`, `tests/test_decisions.py` |
| 2026-09-27 | B4 | `progress_score.py` + `doc/progress_items.yaml` (بنود M/H بأوزان، كل تاسك 100/15) | تشغيل جاف: 52.0 (كله آلي) | `scripts/progress_score.py`, `doc/progress_items.yaml` |
| 2026-09-27 | B3 | قرار (6): حزمة 04 فيها نص آيات وأحاديث منقول → برا git (نفس قاعدة canonical)، وبتتولّد بأمر | — | `.gitignore`, `doc/decisions/README.md` |
| 2026-09-27 | B1 | انقطاع: تشغيل التقييم الكامل انقتل بـ OOM killer (00:13:02 محلي، 5.4 GB) بعد ما خلص bge-m3 وقبل e5؛ الجلسة وقفت معه. ولا عملية معلّقة بعدها | cache qwen3 وbge-m3 كامل (1658 مدخل + 461 سؤال لكل واحد) ومستخدم؛ ما في سطر history للتشغيل | — |
| 2026-09-28 | B1 | سبب الـ OOM: الـ fallback بـ lambda الاستعلام كان ماسك الـ embedder فالموديل ما بيتحرّر، و`HFEmbedder` بيحمّل الموديل حتى لو الـ cache كامل → تحميل كسول + `close()` بيحرّر الأوزان | موديل مخزّن ما بيتحمّل أبداً (172 MB بدل >2.3 GB)؛ اختبارات التقييم 3 passed | `src/companion_api/evaluation/models.py` |
| 2026-09-28 | B1 | e5-large: embedding كامل ومخزّن (1658 + 461). التشغيل الأول للـ reranker وقفته أنا: RSS 4.3 GB والـ swap مليان (ذاكرة e5 ما رجعت للنظام) → إعادة بعملية جديدة | ولا خسارة، كل شي بالـ cache | — |
| 2026-09-28 | B1 | قياس الـ reranker على هالـ CPU: 0.96 زوج/ث (384 token)، 1.59 (256). الإعداد الأصلي (k=30، 8 طرق) = 24394 زوج ≈ 7 ساعات → قرار (6): k=10 على 3 طرق (hybrid:bge-m3، hybrid:bge-m3+q، hybrid:qwen3) + أعلام `--rerank-k` و`--rerank-on` | مسجّل بالـ run (`rerank`) وبالـ ADR | `scripts/eval_retrieval.py` |
| 2026-09-28 | B1 | تقييم كامل بدون reranker (3 موديلات، مع/بدون أسئلة) | بدون +q: hybrid:qwen3 R@5 0.610 / MRR 0.437 (الأفضل)؛ مع +q: dense:bge-m3+q R@5 0.884 / MRR 0.746 (مشكوك: تسرّب) | `reports/retrieval/history.jsonl`, `reports/retrieval/index.html` |
| 2026-09-28 | B1 | ADR-0005 (proposed): جداول كاملة + تقسيم variant + تحفّظات + خيارين (A qwen3 / B bge-m3) بدون اختيار | قسم الـ reranker بانتظار التشغيل | `doc/adr-0005-embedding-selection.md` |
| 2026-09-28 | B1 | تقييم الـ reranker خلص (EXIT 0، run 00:43Z): hybrid:qwen3 MRR 0.437→0.538؛ hybrid:bge-m3 0.417→0.484؛ hybrid:bge-m3+q 0.726→0.678 (بيضرّ فوق +q) | ADR-0005 قسم الـ reranker + خيار A = qwen3 + reranker | `doc/adr-0005-embedding-selection.md`, `reports/retrieval/history.jsonl` |
| 2026-09-28 | B4 | تاسك 11 → draft_ready؛ p2b → draft_ready؛ progress_score --write؛ الـ dashboard انولّد من جديد بالرقم | 58.7 / 100 (الآلي 58.7 من 58.7 ممكن، البشري 0 من 41.3)؛ check_progress: 0 تعارض؛ 634 passed | `doc/corpus-tasks.md`, `doc/done.md`, `reports/progress/score.json`, `reports/retrieval/index.html` |
| 2026-09-28 | R1 | فحص ما قبل الرفع: على `corpus-tasks`، 11 commit فوق main (bd15d42 = origin/main، main نظيف)؛ الشجرة نظيفة. `gh` بالجهاز حزمة pip مش GitHub CLI → فحص عبر API | الـ repo **public**؛ الحساب momenalhamza صلاحيته pull بس (push: false) | — |
| 2026-09-28 | R2 | فحص كل الـ blobs بتاريخ main..corpus-tasks (مش بس HEAD): أسرار (grep بأنماط معروفة؛ gitleaks مش منزّل)، ملفات >5MB، مولّدات، مسارات /home/momen، إيميلات وأرقام | ولا سر؛ أكبر blob 1.47 MB (`hadith_number_mapping.csv`، أرقام بس)؛ ولا مسار جهاز؛ الإيميل الوحيد fixture اختبار | — |
| 2026-09-28 | R2 | مقارنة آلية لكل الـ blobs مع canonical (قرآن + ميسّر + 5 مجموعات حديث) بـ 7-grams و5-grams بعد التطبيع | ولا تطابق ≥ 8 كلمات؛ ولا شي من التفسير؛ التطابقات: صيغ ("قال النبي ﷺ عن")، ~10 عبارات بحث 5–6 كلمات بـ `hadith_selection.yaml`، ومقطع 5 كلمات (12:23) بتعليق B (`batch-03.jsonl`). كلها بـ HEAD وبالتاريخ → قرار المستخدم | — |
| 2026-09-28 | R3 | جرّبت كل أمر على clone نظيف + venv جديد: pytest، fetch_sources (16 ث)، build_corpus (29 ث)، build_release ×2، rollback (status/رجوع/promote)، scan_index، due_for_review، verify_audit، eval_retrieval، apply_decisions --check، review list، age_band check، progress_score، check_progress | كلها exit 0؛ canonical manifest مطابق للأصل؛ أوامر الموديلات الثقيلة موثّقة من تشغيل النسخة الرئيسية اليوم | — |
| 2026-09-28 | R3 | توثيق: `doc/SETUP.md` جديد، قسم الكوربس بـ README، مدخل CHANGELOG، `SUNNAH_API_KEY` اختياري (معلّق) بـ `.env.example`، وصف PR | ملاحظة: build_decision_packages وbuild_eval وrights_table ما بيقبلوا `--help` (بيشتغلوا، ونتيجتهم ثابتة) | `doc/SETUP.md`, `README.md`, `CHANGELOG.md`, `.env.example`, `doc/pr/corpus-tasks.md` |
