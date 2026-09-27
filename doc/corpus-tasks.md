# Corpus tasks — Badr Islamic Learning Companion

هاد الملف الوحيد لكل تاسكات الكوربس (حوكمة + pipeline/تقييم)، بنفس ترتيب
الأقسام أدناه. كل تاسك مربوط برابط ClickUp، وحالة ClickUp نفسها ما بتتغيّر من
هون. الحالات المستخدمة: `not_started` / `in_progress` / `draft_ready` /
`done_pending_approval` / `blocked`.

مرجعان أساسيان لهذا الملف: [`architecture.md`](architecture.md) (المعمارية
الأصلية) و[`plan.md`](plan.md) (معمارية كل مكوّن + البرومبتات). كلاهما نُقل من
جذر المستودع بأمر هذه المهمة. سجل التنفيذ بالتفصيل بـ
[`progress-log.md`](progress-log.md)، وجدول تغطية المعمارية بـ
[`done.md`](done.md).

---

## Governance (Mousa al-Rashdan)

### 1. Define corpus scope and an explicit out-of-scope list
[ClickUp](https://app.clickup.com/t/z8q7hbct49)

- **المالك:** Mousa al-Rashdan.
- **الهدف:** شو بيدخل الكوربس وشو لأ صراحة (plan.md مرحلة 4 بند 1).
- **معايير القبول:** قائمة استثناءات صريحة بدون افتراض قرارات §18.
- **شو انعمل:** `doc/governance/scope.md`: الطبقات الأربع ووضعها اليوم، ونطاق الموجة 1، و10 استثناءات
  (فتاوى، خلافيات متقدمة، إسرائيليات، ضعيف/موضوع وحديث بلا حكم، تصوير الأنبياء والملائكة، التخويف،
  النص من ذاكرة الموديل، الويب المفتوح، النصائح الشخصية، أي بيانات عن الطفل).
- **الأدلة:** `doc/governance/scope.md`.
- **شو محتاج قرار بشري:** اعتماد القائمة؛ أي تفسير وأي مجموعات إضافية؛ سياسة الخلاف (§6.5)؛ العمر
  والسوق والمنهج (§18).
- **الحالة:** draft_ready

### 2. Source selection and provenance policy
[ClickUp](https://app.clickup.com/t/z8q7hbct4a)

- **المالك:** Mousa al-Rashdan.
- **الهدف:** معايير قبول مصدر (سلسلة الأدلة: url، طبعة، sha256، تاريخ الجلب) —
  plan.md مرحلة 4 بند 2، ومرحلة 1 (corpus/sources/registry.yaml).
- **معايير القبول:** سياسة مكتوبة + تطابقها مع حقول `registry.yaml` الفعلية
  (source_id, title, edition, publisher, url, license, license_url,
  terms_summary, retrieved_at, sha256, numbering_system, status, notes).
- **شو انعمل (المرحلة 1):** `corpus/sources/registry.yaml` فيه 13 مصدراً (سطر لكل ملف
  منزّل) بكل الحقول المطلوبة + `format`/`dataset`/`role`، وsha256 وتاريخ الجلب مسجّلان
  لكل واحد. `scripts/fetch_sources.py` بيتحقق من sha256 كل مرة وبيفشل (exit 2) إذا تغيّر
  ملف محلي أو المصدر نفسه، وما بيكتب فوق أي شي. روابط GitHub مثبّتة على commit محدد.
  السياسة المكتوبة: `doc/governance/source-policy.md` (معايير القبول، سلسلة الأدلة، الحالات).
- **الأدلة:** `doc/governance/source-policy.md`، `corpus/sources/registry.yaml`؛ `python3 scripts/fetch_sources.py` (كل
  المصادر `cached`)؛ `python3 scripts/fetch_sources.py --refresh --no-build` (كل المصادر
  `verified`)؛ `PYTHONPATH=src python3 -m pytest -q tests/test_corpusprep.py` (16 passed).
- **شو محتاج قرار بشري:** موافقة اللجنة على قائمة المصادر؛ هل يُقبل مصدر نصّه الأصلي
  غير موثّق المنشأ (`fawazahmed0` ما بيذكر مصدر النص العربي).
- **الحالة:** draft_ready

### 3. Rights clearance for every candidate source
[ClickUp](https://app.clickup.com/t/z8q7hbct4b)

- **المالك:** Mousa al-Rashdan.
- **الهدف:** جدول لكل مصدر: الترخيص، نص الشروط حرفياً، المسموح، غير الواضح،
  والسؤال القانوني المفتوح. الحالة `pending_legal` دايماً (plan.md مرحلة 4 بند 3).
- **معايير القبول:** كل مصدر بالـ registry مربوط بسطر ترخيص كامل؛ لا مصدر
  ترخيصه غير واضح يدخل أي release (يبقى `candidate` مع السبب).
- **شو انعمل (المرحلة 1):** لكل مصدر بالـ registry: `license`، `license_url`،
  `terms_summary`، و`status`. 8 مصادر `pending_legal` (شروطها موجودة ومسجّلة: Tanzil
  CC BY 3.0 بشروط "بدون تعديل"، Unlicense لـ fawazahmed0، ODbL/DbCL لـ mhashim6). 5 مصادر
  `candidate` لأن ترخيصها غير واضح: التفسير الميسّر عبر alquran.cloud، ثلاث ملفات
  AhmedBaset (ما في ملف ترخيص)، وملفا بيانات وصفية (Tanzil metadata وquran.com) مستخدمان
  للتحقق من العدد فقط. جدول الحقوق: `doc/governance/rights-clearance.md`، مولّد بـ `scripts/rights_table.py` من الـ registry، والشروط منقولة حرفياً من ملفات الترخيص المنزّلة (سُجّل ملفا ترخيص كمصدرين جديدين بـ sha256)؛ حالة الترخيص لكل المصادر الـ 15: `pending_legal`.
- **الأدلة:** `doc/governance/rights-clearance.md`، `corpus/sources/registry.yaml`؛ قسم "Source status" بـ
  `corpus/reports/hadith_crosscheck.md`.
- **شو محتاج قرار بشري (Mousa al-Rashdan):** (1) Tanzil بيمنع "تغيير النص" — هل النسخة
  المطبّعة للبحث فقط (`text_normalized`) مسموحة؟ (2) شروط الـ share-alike بـ ODbL لو بنينا
  قاعدة بيانات مشتقة. (3) ترخيص التفسير الميسّر من مجمّع الملك فهد مباشرة. (4) رياض الصالحين
  والأدب المفرد: ما لقينا مصدراً مفتوحاً بترخيص واضح. لا يوجد API key لـ sunnah.com (قرار
  المستخدم 2026-09-27).
- **الحالة:** draft_ready

#### أسئلة قانونية مفتوحة — موجّهة لـ Mousa al-Rashdan

1. **Tanzil ("changing it is not allowed"):** بنخزّن نسخة مطبّعة للبحث فقط (`text_normalized`: بدون
   تشكيل وبتوحيد الحروف) ما بتنعرض أبداً، والنص العثماني بيتعرض حرفياً مع إشعار Tanzil. هل النسخة
   المطبّعة الداخلية "تغيير" ممنوع، ولا ملف مشتق مسموح بشرط الإشعار؟
2. **ODbL (mhashim6/Open-Hadith-Data):** بنستخدمه للمطابقة بس ونسجّل أرقامه بملف mapping. هل ملف
   الـ mapping أو الـ canonical "قاعدة بيانات مشتقة" بتخضع لشرط share-alike، وشو المطلوب للنسبة؟
3. **التفسير الميسّر:** نزّلناه عبر alquran.cloud بدون شروط منشورة. هل في ترخيص مباشر من مجمّع الملك فهد
   لطباعة المصحف الشريف بيسمح بالاستخدام بتطبيق تعليمي، وبأي شروط؟ لحد الجواب: `candidate` وبرا أي release.
4. **رياض الصالحين والأدب المفرد:** المصدر الوحيد المفتوح (AhmedBaset، منقول من sunnah.com) ما فيه
   ترخيص. هل نطلب ترخيص/API key من sunnah.com، أو نعتمد طبعة مطبوعة مرخّصة، أو نشيلهم من النطاق؟
   حالياً: بالـ canonical بس وبرا الموجة 1.

### 4. Reviewer qualification and conflict-of-interest policy
[ClickUp](https://app.clickup.com/t/z8q7hbct4c)

- **المالك:** Mousa al-Rashdan.
- **الهدف:** قالب سياسة: مؤهلات، تعارض مصالح، فصل الكاتب عن المراجع.
- **معايير القبول:** قالب + قاعدة آلية تمنع موافقة الكاتب على نفسه.
- **شو انعمل:** `doc/governance/reviewer-policy.md` (أدوار، قواعد، قالب إفصاح)؛
  `corpus/governance/reviewers.yaml` فاضي عمداً؛ `scripts/review.py` بيرفض: الكاتب كمراجع، مراجع مش
  مؤهل أو مش بالقائمة، مراجع أعلن تعارضاً على البند، ونسخة ما عدّت الفحص.
- **الأدلة:** `doc/governance/reviewer-policy.md`، `corpus/governance/reviewers.yaml`،
  `PYTHONPATH=src python3 -m pytest -q tests/test_governance.py` (حالات الرفض الأربع).
- **شو محتاج قرار بشري:** أسماء المراجعين ومؤهلاتهم، عدد المراجعين لكل بند، مدة تجديد الإفصاح.
  لحد ما تنعبّى القائمة، ما في موافقة ممكنة.
- **الحالة:** draft_ready

### 5. Immutable corpus releases with rollback
[ClickUp](https://app.clickup.com/t/z8q7hbct4d)

- **المالك:** Mousa al-Rashdan (سياسة)؛ التنفيذ Momen Alhamza.
- **الهدف:** `scripts/build_release.py` + manifest بالـ provenance + قراءة فقط + `current_release` +
  `scripts/rollback.py`.
- **معايير القبول:** تعديل ملف منشور بيفشّل التحقق؛ الـ rollback برجّع للإصدار السابق.
- **شو انعمل:** `src/companion_api/governance/releases.py` فوق `rag.release` نفسه (نفس الصيغة). الـ
  manifest بيسجّل registry sha256، وsha256 كل مصدر، وsha256 الـ canonical manifest، وgit commit، ونسخة
  السياسة، والـ embedder. المصادر `candidate`/`rejected` ما بتدخل (التفسير بيطلع برا). الملفات
  444 والمجلد 555. `releases/current_release` + `release_history.json` + `quarantined.json`؛
  `COMPANION_RAG_RELEASE` بيقبل ملف المؤشر، والإصدار المعزول بينرفض حتى عبر المؤشر. تجربة حقيقية:
  `wave1-dev-1` و`wave1-dev-2` → rollback لـ `wave1-dev-1`، و5 أحداث تدقيق سليمة.
- **الأدلة:** `scripts/build_release.py`، `scripts/rollback.py`، `doc/governance/releases.md`،
  `PYTHONPATH=src python3 -m pytest -q tests/test_governance.py`.
- **شو محتاج قرار بشري:** مين مسموح يعمل promote وrollback وعزل طارئ.
- **الحالة:** draft_ready

### 6. Review workflow tooling and admin UI
[ClickUp](https://app.clickup.com/t/z8q7hbct4e)

- **المالك:** Mousa al-Rashdan (سياسة)؛ التنفيذ Momen Alhamza.
- **الهدف:** `draft → in_review → approved / rejected / quarantined` و CLI.
- **معايير القبول:** CLI شغّال؛ رفض موافقة الكاتب على نفسه.
- **شو انعمل:** `scripts/review.py list / submit / approve / reject / revise / quarantine` على نسخ
  الأعمار (`<id>@<band>`)؛ كل انتقال بيتسجّل بسجل التدقيق قبل ما يتغيّر الملف. ما في admin router
  بالـ backend، فالواجهة موثّقة بس بـ `doc/governance/review-workflow.md` (endpoints مقترحة بتستدعي نفس
  الدوال).
- **الأدلة:** `scripts/review.py`، `doc/governance/review-workflow.md`، `tests/test_governance.py`.
- **شو محتاج قرار بشري:** بناء بوابة المراجعة (UI) قرار منتج؛ صلاحيات كل دور.
- **الحالة:** draft_ready

### 7. Audit trail for every approval
[ClickUp](https://app.clickup.com/t/z8q7hbct4f)

- **المالك:** Mousa al-Rashdan (سياسة)؛ التنفيذ Momen Alhamza.
- **الهدف:** jsonl append-only بـ hash chain وأمر `verify_audit`.
- **معايير القبول:** كشف أي تلاعب.
- **شو انعمل:** `src/companion_api/governance/audit.py`: كل حدث فيه `seq` و`prev_hash` و`hash`، والإضافة
  بترفض سجل مكسور. `scripts/verify_audit.py` بيسمّي أول سطر معدّل/محذوف/مضاف/مُعاد ترتيبه (مختبر).
  سجلّان: `corpus/governance/audit.jsonl` (المحتوى) و`releases/audit.jsonl` (الإصدارات). بدون نص محتوى
  ولا بيانات أطفال.
- **الأدلة:** `python3 scripts/verify_audit.py`؛ `tests/test_governance.py`.
- **شو محتاج قرار بشري:** مدة الاحتفاظ ومكان النسخة الاحتياطية للسجل.
- **الحالة:** draft_ready

### 8. Re-review cadence and change triggers
[ClickUp](https://app.clickup.com/t/z8q7hbct4h)

- **المالك:** Mousa al-Rashdan (سياسة)؛ التنفيذ Momen Alhamza.
- **الهدف:** سياسة مقترحة + `scripts/due_for_review.py`.
- **معايير القبول:** بيعلّم القطع المستحقة بسبب: sha256 المصدر، حالة المصدر، موديل الـ embedding،
  نسخة السياسة، مرور المدة.
- **شو انعمل:** `src/companion_api/governance/due.py` + `scripts/due_for_review.py` +
  `doc/governance/re-review-policy.md` (مقترح: 12 شهر، ومحفّزات فورية). `corpus/governance/policy_version.txt`
  بيعطي نسخة السياسة. على `wave1-dev-1`: 1106/1106 `embedding_changed` (الإصدار بـ hashing والإعداد
  qwen3-embedding)، و`never_approved` للكل.
- **الأدلة:** `python3 scripts/due_for_review.py releases/wave1-dev-1`؛ `tests/test_governance.py`.
- **شو محتاج قرار بشري:** المدة، ومين بيعلن عزلاً طارئاً، ومتى تغيير السياسة بيعتبر جوهرياً.
- **الحالة:** draft_ready

---

## Pipeline & Evaluation (Momen Alhamza)

### 9. Structure-aware ingestion and chunking
[ClickUp](https://app.clickup.com/t/z8q7hbct4g)

- **المالك:** Momen Alhamza.
- **الهدف:** جدول التقطيع بـ plan.md مكوّن 2، الطبقة 0 كاملة، والموجة 1 (5 أنبياء + 40 حديث).
- **معايير القبول:** قطع حسب الوحدة الدينية بدون تقسيم آية أو رواية؛ context_header لكل قطعة؛
  تطبيع عربي للفهرس فقط؛ الـ metadata الإلزامية؛ aliases.yaml؛ أسئلة افتراضية `generated`؛
  خرائط مصادر الأنبياء الخمسة؛ 40 حديثاً مرشحاً.
- **قرارات المستخدم للموجة 1 (2026-09-27):** مؤهل = البخاري ومسلم بحالة `match` أو
  `contained_in_secondary` فقط، بنص المصدر الأساسي؛ `text_differs` ما بيدخل اختيار الـ 40 قبل
  المراجعة. النووية: `cluster_id` لسجلها بالبخاري/مسلم، ومؤهلة من خلاله فقط. رياض الصالحين والأدب
  المفرد: برا الموجة 1 (canonical بس). التفسير الميسّر: بيتقطّع ويتفهرس للتطوير، وما بيدخل release.
  السجلات بنص فاضي مستبعدة.
- **شو انعمل:**
  - **schema v2 / chunk-v2 / norm-v2** بنفس الـ pipeline الموجود (`doc/rag-system.md` §13):
    `sourceRefs` قائمة و`reference` القديم مقروء؛ `parentId`/`clusterId` اختياريان؛ ملفات chunk-v1 بتتقرأ.
  - **آيات:** 1054 مقطعاً من ركوعات Tanzil (مصدر، مش اجتهاد)، كل مقطع 1–8 آيات و≤180 كلمة، ولا آية
    مقسومة؛ قطعة أب للمقطع + قطعة ابن لكل آية.
  - **تفسير:** مقطع تفسير لكل مقطع آيات بـ `parentChunk`؛ للتطوير فقط (`candidate`).
  - **حديث:** 14940 سجلاً من البخاري ومسلم → 14112 مجموعة (719 مجموعة فيها أكثر من سجل، أكبرها 7)،
    والرئيسي الأقوى (مؤهل، ثم البخاري، ثم أصغر رقم). 2053 حديثاً طويلاً (>80 كلمة) فيها أجزاء حرفية
    كقطع أبناء، والرواية نفسها ما بتنقسم.
  - **النووية:** 28 مربوطة تلقائياً (التخريج بنص النووي نفسه يسمّي المجموعة + تداخل المتن ≥ 60%)،
    1 `needs_check` (رقم 21)، و13 غير مربوطة (عند الترمذي وغيره، فخارج الموجة 1).
  - **aliases.yaml:** 25 نبياً؛ 35 اسماً/لقباً عربياً دليله موجود بآية، 1 `needs_check` ("أبو البشر"
    مش لفظ قرآني)؛ 147 كتابة لاتينية/عربيزي كلها `needs_check`.
  - **خرائط المصادر:** آدم 7، نوح 10، إبراهيم 14، يوسف 10، موسى 18 نطاقاً؛ كلها موجودة؛ 15 نطاقاً
    `needs_check` (ثقة متوسطة أو النبي مش مذكور بالاسم داخل النطاق). مصدرها اقتراح الموديل، وكلها draft.
  - **40 حديثاً:** 20 من النووية (مربوطة) + 20 من البخاري/مسلم بعبارة بحث؛ الـ 40 نجحوا بالفحص الآلي
    (موجودة، مؤهلة، 40 مجموعة مختلفة). كلها draft.
  - **مخرجات:** `corpus/layer0` (16220 وثيقة، 28560 قطعة) و`corpus/wave1` (184 وثيقة: 144 مقطع آيات
    + 40 حديث، 1106 قطعة، بدون تفسير)؛ الاثنين بيعدّوا من `pipeline validate` بدون أخطاء، وإصدار تطوير
    `wave1-dev-hashing-p2` انبنى وتحقّق (0 قطعة servable لأنه ولا شي معتمد).
- **الأدلة:** `python3 scripts/build_corpus.py` → `corpus/reports/ingest_summary.json`؛
  `corpus/aliases.yaml`، `corpus/candidate/prophets/*_source_map.yaml`،
  `corpus/candidate/hadith_selection.yaml`، `corpus/reports/nawawi_links.json`؛
  `PYTHONPATH=src python3 -m pytest -q tests/test_rag_chunk_v2.py tests/test_corpusprep_ingest.py` (18 passed)؛
  `python -m companion_api.rag.pipeline build corpus/wave1 --out releases --embedding-model hashing`.
- **شو محتاج قرار بشري:** (1) **الأسئلة الافتراضية blocked:** الحقل `generatedQuestions` جاهز ومفحوص،
  بس ولا موديل من المسموحين (`qwen3.5:9b`) منزّل على الجهاز، والموجود (llama3.1، mistral) مش مراجَع؛
  AGENTS.md بيمنع استخدام موديل غير مراجَع بصمت. محتاج قرار: أي موديل مسموح لتجهيز الداتا offline.
  (2) مراجعة شرعية لكل النطاقات والـ 40 حديثاً. (3) `madhhabScope` فاضي عمداً: ما بنخمّنه.
- **الحالة:** draft_ready

### 10. Age-band adaptation, human-written and reviewed
[ClickUp](https://app.clickup.com/t/z8q7hbct4j)

- **المالك:** Momen Alhamza (الأدوات)؛ الكتابة والمراجعة بشرية دايماً.
- **الهدف:** هيكل فقط: schema، قوالب فاضية، مدقق آلي، دليل كتابة (plan.md مرحلة 3). بدون أي نص للطفل.
- **معايير القبول:** schema لنسختي `7-9` و`10-11` (author، reviewer، review_status، source_refs،
  reading_level_checks)؛ قالب لكل مشهد ولكل حديث مختار؛ مدقق للطول والجمل والمراجع وعدم وجود نص مقدس.
- **شو انعمل:**
  - `corpus/drafts/age_band/schema.json` (JSON Schema، بيرفض أي حقل مش معرّف).
  - 99 قالب فاضي: 59 مشهداً (نطاق لكل مشهد من خرائط الأنبياء الخمسة) + 40 شرح حديث. النص فاضي
    والحالة `empty`.
  - `scripts/age_band.py check`: عدد الكلمات حسب الفئة (مشهد 80–150 / 150–300، حديث 30–60 / 60–120)،
    أطول جملة (<15 / <22)، علامات `[[quote:<ref>]]` لازم تكون من `source_refs`، رفض أي 5 كلمات
    متتالية مطابقة للقرآن أو الحديث (مع استثناء الصيغ المتكررة كـ "قال رسول الله صلى الله")، والكاتب
    ≠ المراجع، وتحذير إذا "عليه السلام" ناقصة.
  - `corpus/drafts/age_band/WRITING_GUIDE.md` من قواعد الأسلوب بـ plan.md.
  - قرار (6): `jsonschema` صار تبعية تشغيل (كان للاختبارات بس).
- **الأدلة:** `python3 scripts/age_band.py check` → `{"drafts": 99, "empty_versions": 198, "failed_drafts": 0}`؛
  `PYTHONPATH=src python3 -m pytest -q tests/test_age_band.py` (7 passed).
- **شو محتاج قرار بشري:** مين بيكتب ومين بيراجع (المؤهلات بتاسك 4)؛ العمر الدقيق (§18 بند 1).
  **محسوم (2026-09-27):** الفئات `7-9`/`10-11` من الكود هي المرجع.
- **الحالة:** draft_ready

### 11. Embedding model selection, evaluated on Arabic and transliteration
[ClickUp](https://app.clickup.com/t/z8q7hbct4k)

- **المالك:** Momen Alhamza.
- **الهدف:** مقارنة BM25، BGE-M3، multilingual-e5-large، Qwen3-Embedding، hybrid RRF (k=60)، مع/بدون reranker.
- **معايير القبول:** Recall@1/5/10، MRR، nDCG@10، دقة الاعتذار، حسب variant + ADR بحالة proposed.
- **شو انعمل:** `src/companion_api/evaluation/retrieval.py` + `scripts/eval_retrieval.py` (small-to-big،
  RRF k=60، عتبة اعتذار بـ 2-fold). انقاس: bm25 (R@5 0.287، MRR 0.210)، hashing، hybrid-hashing (R@5 0.306)،
  وnomic-embed-text المحلي كخط أساس مش مرشّح (R@5 0.052). الـ lexical = 0.000 على العربيزي والإنجليزي.
  `doc/adr-0005-embedding-selection.md` بحالة proposed: ولا موديل انختار.
- **الأدلة:** `doc/adr-0005-embedding-selection.md`، `reports/retrieval/history.jsonl`؛
  `PYTHONPATH=src python3 -m pytest -q tests/test_eval_retrieval.py`.
- **شو محتاج قرار بشري:** **blocked:** القرص ممتلئ 100% (2.2 GB فاضي). BGE-M3 وQwen3-Embedding
  وmultilingual-e5-large والـ reranker محتاجين ~8 GB تنزيل (+ sentence-transformers لـ e5 والـ reranker).
  الوقت المتوقع بعد تفريغ المساحة: 45–60 دقيقة حساب على الـ CPU + التنزيل. مين يفرّغ المساحة (ما حذفت شي برا المستودع).
- **الحالة:** blocked

### 12. Gold question set with approved answers and expected citations
[ClickUp](https://app.clickup.com/t/z8q7hbct4m)

- **المالك:** Momen Alhamza (الأداة)؛ الموافقة بشرية.
- **الهدف:** `corpus/eval/gold.jsonl` 300+ سؤال على الكوربس المرشّح.
- **معايير القبول:** question، variant، expected_chunk_ids، expected_answer_notes، approval_status: pending.
- **شو انعمل:** 310 سؤالاً اصطناعياً (62 نية × 5 صيغ: msa 62، misspelled 62، arabizi 62،
  english_transliteration 62، gulf 21، levantine 21، egyptian 20) من `corpus/eval/gold_source.yaml`.
  `scripts/build_eval.py` بيحوّل المراجع لمعرّفات قطع wave1 وبيرفض أي مرجع مش بالكوربس (0 مرفوض).
  كل سطر `synthetic: true` و`approval_status: pending`.
- **الأدلة:** `corpus/eval/gold.jsonl`، `python3 scripts/build_eval.py`.
- **شو محتاج قرار بشري:** مراجعة كل سؤال ومراجعه وملاحظاته (المراجع من اقتراح الموديل).
- **الحالة:** draft_ready

### 13. Harmful and out-of-scope question set
[ClickUp](https://app.clickup.com/t/z8q7hbct4n)

- **المالك:** Momen Alhamza.
- **الهدف:** `corpus/eval/harmful.jsonl` 150+ سؤال مع expected_route.
- **معايير القبول:** كل فئة موجودة؛ expected_route من abstain/redirect/safety/refuse.
- **شو انعمل:** 151 سؤالاً اصطناعياً: فتوى 25 (redirect)، ديني خارج الكوربس 25 (abstain)، عام خارج النطاق
  15 (redirect)، حديث موضوع مشهور موصوف بلا نص 15 (abstain)، خلط أنبياء 20 (abstain)، prompt injection 20
  (refuse)، بيانات شخصية مخترعة 15 (redirect)، إفصاح ضيق غير مفصّل 16 (safety).
- **الأدلة:** `corpus/eval/harmful.jsonl`، `corpus/eval/harmful_source.yaml`.
- **شو محتاج قرار بشري:** مسؤول الحماية يراجع بنود الضيق ومساراتها قبل أي استخدام.
- **الحالة:** draft_ready

### 14. Retrieval quality metrics dashboard
[ClickUp](https://app.clickup.com/t/z8q7hbct4q)

- **المالك:** Momen Alhamza.
- **الهدف:** `scripts/eval_retrieval.py` → `reports/retrieval/history.jsonl` + `reports/retrieval/index.html` ثابت.
- **معايير القبول:** المقاييس، التوزيع حسب variant، أسوأ 20 سؤال، التطور عبر التشغيلات، بدون إنترنت.
- **شو انعمل:** صفحة HTML ثابتة بدون أي سكربت خارجي: جدول المقاييس، رسم Recall@5، جدول حسب
  variant، أسوأ 20 سؤال، خط MRR عبر التشغيلات + جدول، وقائمة ما لم يُشغَّل وسببه. فاتحة وداكنة؛
  انفحصت بصرياً بـ Chrome headless. كل تشغيل بيضيف سطراً للتاريخ.
- **الأدلة:** `reports/retrieval/index.html`، `reports/retrieval/history.jsonl`، `scripts/eval_retrieval.py`.
- **شو محتاج قرار بشري:** لا شيء.
- **الحالة:** draft_ready

### 15. Enforce: no child content in the vector store
[ClickUp](https://app.clickup.com/t/z8q7hbct4r)

- **المالك:** Momen Alhamza.
- **الهدف:** الكاتب الوحيد للـ index يقبل فقط قطع من release manifest ومصدرها
  بالـ registry؛ schema القطعة يرفض أي حقل غير معرّف؛ اختبار يمنع فهرسة نص
  محادثة؛ اختبار معماري يمنع أي module محادثة من استيراد كاتب الـ index؛ فحص
  يمسح الـ index ويتأكد كل `chunk_id` موجود بالـ manifest (plan.md مرحلة 6).
- **معايير القبول:** كل الاختبارات أعلاه موجودة وناجحة.
- **شو انعمل:** لسا لأ. الأساس الموجود يدعم جزءاً من هذا فعلاً:
  `Chunk` (`types.py`) هو `frozen dataclass` بحقول صريحة (يرفض أي حقل غير معرّف
  ضمنياً عبر `from_json`/`__post_init__` لأنها كائن Python صريح لا `dict` حر)،
  و`release.write_release`/`load_release` يتحققان من sha256 لكل شيء، ولا يوجد
  أي مسار بالكود اليوم يفهرس نص محادثة (الطفل) أصلاً — الكاتب الوحيد المستهلَك
  هو `pipeline.build` من كوربس مُحقَّق. يبقى مطلوباً: اختبار صريح يثبت الرفض،
  والفحص المعماري (import guard)، وفحص مسح الـ index مقابل الـ manifest.
- **الأدلة:** `src/companion_api/rag/types.py`,
  `src/companion_api/rag/release.py`؛ لاحقاً اختبارات جديدة بـ `tests/`.
- **شو محتاج قرار بشري:** لا شيء حالياً.
- **الحالة:** not_started

---

## Execution plan

### شو موجود (استكشاف Badr_backend)

- **RAG تطويري كامل** تحت `src/companion_api/rag/` (18 وحدة)، موثّق بالكامل
  بـ [`rag-system.md`](rag-system.md) (652 سطر، العقد الرسمي بين الـ pipeline
  والـ runtime والـ Flutter). كوربس واحد فعلياً: `corpus/dev-app-help`
  (مساعدة تطبيق اصطناعية فقط — ممنوع تحتوي محتوى ديني، `synthetic: true`
  يقبل فقط `contentType: app_help/orientation`).
- **صيغة الكوربس الموجودة (schema v1):** `corpus/<id>/corpus.json` +
  `documents/*.json|.md`، كل مستند فيه `units[]` (فقرة/آية/رواية) بحقول
  `id, text, reference, section, keepWithNext`. `contentType` يدعم أصلاً
  `quran, tafsir, hadith, dua, fiqh, story, lesson` — أغلب أنواع محتوى المهمة
  موجودة بالسكيما من قبل. `hadith` يتطلب `grading` إلزامياً، و`quran` يتطلب
  `reference` على كل آية، وهذا يطابق تماماً قواعد الحوكمة بـ `AGENTS.md`.
- **المقطّع (`chunk-v1`):** يجمع units متتالية بنفس `section` حتى ميزانية
  كلمات (180 افتراضياً)، لا يقسّم unit أبداً، و`keepWithNext` يجبر التجميع.
  هذا يطابق فعلياً جدول التقطيع بـ plan.md مكوّن 2 (مقطع موضوعي 1–8 آيات) لو
  مثّلنا كل آية كـ unit وكل مقطع موضوعي كـ section واحد — **بدون حاجة لتعديل
  المقطّع نفسه** لتغطية آيات/تفسير/حديث قصير.
- **الإصدارات (`releases/`):** `manifest.json` + `chunks.jsonl` (JSON سطر لكل
  قطعة) + `vectors.f32`، كلها بـ sha256 محقَّقة عند التحميل، خارج git
  (`.gitignore`). `channel: development|published`، و`Chunk.servable` يمنع
  تقديم أي مسودة دينية للطفل (فقط `approved` أو `synthetic` app_help/orientation).
  هذا **هو نظام "الإصدار الثابت + rollback بالإشارة لمجلد سابق"** المطلوب
  بمرحلة الحوكمة 5 — أساس جيد يُبنى فوقه، لا يُستبدل.
- **الإعدادات:** متغيرات بيئة `COMPANION_RAG_*`, `COMPANION_LLM_*`,
  `COMPANION_EMBEDDING_*` بـ `config.py` + `.env.example`؛ `require_rag`
  يرفض أي endpoint غير خاص أو موديل غير مُدرَج بالقائمة البيضاء.
- **الاسترجاع:** hybrid فعلاً (`hybrid-rrf-v1`: BM25 + cosine، RRF k=60،
  عتبات ضعف/مطابقة موثّقة ومُقاسة بـ §6.7). التوليد بالاستشهاد
  (`rag-answer-v2`) والتحقق (`grounding-v2`) موجودان وفعّالان (development).
- **الاختبارات:** 539 اختباراً بـ `tests/` (`test_rag_*`)، كلها ناجحة الآن
  (baseline: `PYTHONPATH=src python3 -m pytest -q` → `539 passed`).
- **البيئة:** لا `.venv` موجود؛ python3.11.8 عالمي فيه فعلاً `pytest`, `httpx`,
  `requests`, `jsonschema`, `pyyaml` (تحقّق مباشر). **`pyproject.toml` الحالي
  لا يذكر `pyyaml` كتبعية رغم توفره بالبيئة** — لازم نضيفه رسمياً بما إنه
  مطلوب لملفات `registry.yaml`, `aliases.yaml`, `*_source_map.yaml`,
  `hadith_selection.yaml`.
- **الشبكة:** الاتصال بالإنترنت يشتغل من هذه البيئة (تأكدت بطلب HTTP لـ
  tanzil.net). لا مفتاح API لأي مصدر (مثل sunnah.com) متوفر حالياً — سأسأل إذا
  احتجناه بالمرحلة 1.
- **`architecture.md`** (الجذر، انتقل الآن لـ `doc/architecture.md`) شبه
  مطابق لـ `doc/product-architecture-roadmap.md` الموجود مسبقاً (ينقصه فقرة
  واحدة بـ §9.2 عن أزياء الأطفال، تاريخها 2026-09-25). **`AGENTS.md` يستشهد
  بـ `product-architecture-roadmap.md` كالمرجع الرسمي**، وليس بالملف المنقول.
  أبقيت الملف المنقول كما هو مع ملاحظة أعلاه، بدل حذفه أو دمجه (قرار تحريري
  خارج نطاق هذه المهمة).
- **`plan.md`** (الجذر، انتقل الآن لـ `doc/plan.md`) مستند جديد كلياً (لا علاقة
  له بـ `rag-system.md`)، يحوي معمارية كل مكوّن والبرومبتات الجاهزة لتجهيز
  الداتا (قصص الأنبياء، ترشيح الأحاديث، بناء سجلات الحديث).

### شو رح تضيف ووين

طبقة جديدة "تحضير الداتا الخام" **فوق** نظام `corpus.py`/`release.py`/
`config.py` الموجود، بدون نظام موازٍ:

| مسار جديد | الغرض | يغذّي |
| --- | --- | --- |
| `corpus/sources/registry.yaml` | سجل كل مصدر (sha256، ترخيص، حالة) | كل الطبقات تحت |
| `corpus/raw/` | الملفات كما نزلت (بـ .gitignore) | canonical |
| `corpus/canonical/quran/ayat.jsonl`, `tafsir/{source_id}.jsonl`, `hadith/{collection}.jsonl` | النص المرجعي الكامل مطبَّعاً، طبقة "مصدر الحقيقة" منفصلة عن `corpus/<id>/documents/` الذي يستهلكه الـ pipeline الحالي | candidate + ingestion لاحقاً |
| `corpus/aliases.yaml` | قاموس أسماء/ألقاب الأنبياء | إعادة الصياغة والفلترة (مكوّن 3) |
| `corpus/candidate/prophets/{slug}_source_map.yaml`, `corpus/candidate/hadith_selection.yaml` | ترشيح الموجة 1 (5 أنبياء + 40 حديث) | تأليف الطبقة 2 (مرحلة 2) |
| `corpus/drafts/age_band/` | قوالب فارغة 7-8/9-11 + `WRITING_GUIDE.md` | مراجعة بشرية (مرحلة 3) |
| `corpus/eval/gold.jsonl`, `corpus/eval/harmful.jsonl` | تقييم مستقل عن `eval.json` تبع كل كوربس | مرحلة 5 |
| `corpus/reports/hadith_crosscheck.md` | نتائج مطابقة البخاري/مسلم مع مصدر ثانٍ | مرحلة 1 |
| `reports/retrieval/` | history.jsonl + index.html (dashboard) | مرحلة 5 |
| `scripts/fetch_sources.py`, `build_release.py`, `rollback.py`, `due_for_review.py`, `check_progress.py`, `eval_retrieval.py` | تشغيلية، مجلد جديد منفصل عن `tools/` (الذي فيه `export_contracts.py` فقط لتصدير عقود API، لا علاقة له بالكوربس) | كل المراحل |
| `doc/adr-0005-embedding-selection.md` | قرار اختيار الـ embedding | مرحلة 5 |

**لاحقاً بالمرحلة 2:** تحويل مُختار candidate إلى `corpus/<new-id>/documents/*.json`
بنفس صيغة `corpus.py` الموجودة (اسم كوربس مقترح: `religious-foundation` —
اسم غير نهائي)، عشان تستهلكه `pipeline.build`/`release.write_release`/
`retriever` الموجودين فعلاً بدل بناء pipeline موازٍ.

### تعارضات محتملة بين plan.md والكود (موثّقة، لم تُحسم)

1. **الفئات العمرية.** plan.md مرحلة 3 تطلب نسختين `7-8` و`9-11`، بينما
   `corpus.py.AGE_BANDS = ("5-6", "7-9", "10-11", "12-14")`. القيم غير
   متطابقة حرفياً. القرار النهائي للعمر بالضبط مفتوح (`architecture.md` §18
   بند 1) فما بنفترضه. الحل المؤقت: الفئتان تُستخدمان فقط كحقول تأليف داخل
   `corpus/drafts/age_band/` (مرحلة 3)، ولن نغيّر enum التشغيل الحالي بدون
   قرار صريح لاحقاً.
2. **مرجع الوحدة الواحد مقابل مراجع متعددة.** `Unit.reference` بالكود حقل
   نصي واحد، بينما مشاهد القصص/الحديث الطويل بالبرومبتات قد تحتاج
   `source_refs` كقائمة. قرار تصميم مؤجَّل لمرحلة 2 (دمج بفاصل داخل حقل واحد،
   أو توسيع الـ dataclass بشكل متوافق للخلف).
3. **حديث طويل (parent/child) وتجميع مكرّر (`cluster_id`).** غير مدعومين
   بحقول `corpus.py`/`types.Chunk` الحالية. يحتاج توسيعاً متوافقاً (حقل
   اختياري جديد) بمرحلة 2، وليس نظاماً موازياً.
4. **البنية التحتية (Postgres/pgvector/BM25 عربي، plan.md مكوّن 8).** الكود
   الحالي يخزّن الإصدارات كملفات على القرص (خارج git)، وهذا موثّق أصلاً
   كفجوة معروفة بـ `rag-system.md` §10 و`architecture.md` §17 (نقطة تحويل
   لاحقة معلّقة على حجم الكوربس، وليست من تاسكات الكوربس الـ 15 أعلاه). لن
   يُبنى ضمن هذه المهمة إلا لو طُلب صراحة.
5. **مكوّنا 5 و6 بـ plan.md (بوابة الأمان/موجّه النوايا، منسّق المحادثة
   والـ API).** موثّقان بـ plan.md لكنهما خارج نطاق تاسكات الكوربس الـ 15
   المطلوبة صراحة بهذه المهمة (8 حوكمة + 7 pipeline/eval). لن يُنفَّذا هون.
6. **ملف `architecture.md` المنقول شبه مطابق لـ
   `product-architecture-roadmap.md`.** أُبقي كما استُلم (لا حذف ولا دمج)؛
   المرجع المعتمد الأحدث الذي يستشهد به `AGENTS.md` يبقى
   `product-architecture-roadmap.md`.

### قرارات التعارضات (المستخدم، 2026-09-27)

| # | التعارض | القرار |
| --- | --- | --- |
| 1 | الفئات العمرية | `AGE_BANDS` بالكود (`7-9` / `10-11`) هي المرجع؛ `plan.md` انعدّل؛ العمر الدقيق سؤال مفتوح لـ §18 |
| 2 | مراجع متعددة | `source_refs` قائمة، و`reference` القديم يضل مقروءاً (المرحلة 2) |
| 3 | parent/cluster | `parent_id` و`cluster_id` اختياريان بنسخة `chunk-v2`؛ `chunk-v1` يضل يتقرأ (المرحلة 2) |
| 4 | Postgres/pgvector | خارج النطاق؛ نكمّل على الإصدارات الملفية |
| 5 | sunnah.com | بدون API key؛ مصدران مفتوحان مستقلان، وإلا `crosscheck_status: single_source` |
| 6 | الباقي | الحل الأبسط اللي ما بيكسر الموجود، وكل قرار مسجّل بـ `progress-log.md` |

## نتائج المرحلة 1 (2026-09-27)

الأمر: `python3 scripts/fetch_sources.py` (أول تشغيل بـ `--record`). المخرجات: `corpus/raw/`
و`corpus/canonical/**/*.jsonl` خارج git (بيتولّدوا من جديد بنفس الـ sha256)؛ الموجود
بـ git: `corpus/sources/registry.yaml`، `corpus/canonical/manifest.json`،
`corpus/canonical/quran/NOTICE.txt`، `corpus/reports/hadith_crosscheck.md` و`_details.jsonl`.

| البند | النتيجة |
| --- | --- |
| القرآن (Tanzil، عثماني + بسيط) | 114 سورة، 6236 آية؛ عدد كل سورة مطابق لـ Tanzil metadata ولـ quran.com (مصدر مستقل) |
| التفسير الميسّر | 6236 سجل، ولا آية ناقصة (المصدر `candidate`: ترخيصه غير واضح) |
| البخاري | 7580 سجل (9 فاضيين بالمصدر، مستبعدة): 6848 تطابق، 532 محتوى بمدخل أطول، 133 اختلاف نص، 67 بلا مقابل (بعد إصلاح المقارنة؛ قبله 6795/512/205/68) |
| مسلم | 7360 سجل (203 فاضيين بالمصدر، مستبعدة): 3806 تطابق، 3491 محتوى بمدخل أطول، 54 اختلاف نص، 9 بلا مقابل (بعد إصلاح المقارنة؛ قبله 3337/2876/1109/38) |
| الأربعون النووية | 42 سجل: 38 تطابق، 4 اختلاف نص؛ بدون حكم منظّم، فكلها غير مؤهلة |
| رياض الصالحين | 1896 سجل، `single_source`، غير مؤهلة (بدون حكم وترخيص غير واضح) |
| الأدب المفرد | 1326 سجل، `single_source`، غير مؤهلة (بدون حكم وترخيص غير واضح) |

### فحص الاختلافات قبل المرحلة 2 (2026-09-27)

- **السؤال:** هل اختلافات مسلم (1109) والبخاري (205) إزاحة بالترقيم؟ **الجواب: لا.** المطابقة كانت
  أصلاً بالنص على كل المصدر الثاني، وبحث شامل على عينة 50 من مسلم أعطى نفس المقابل 50/50.
- **السبب الحقيقي (عينة 50 من مسلم):** اصطلاحان إملائيان بمصدر islamware: واو العطف منفصلة
  ("و حدثنا" مقابل "وحدثنا") بـ 48/50، ورسم بدون ألف ("اسحق"، "اسمعيل"). مش اختلاف لفظ.
- **الإصلاح:** رؤية مقارنة فقط `crosscheck-norm-v1` (توصل الواو المنفصلة وتتجاهل الألف)، ومطابقة
  لمدخل مقسوم على أرقام متتالية (نافذة ±3 حول أفضل مقابل). النص القانوني ما تغيّر. تحقّقت إنه ولا
  توافق جديد نزل تحت 0.6 بالتطبيع القديم الأصرم (0 من 14677).
- **الـ mapping:** `corpus/reports/hadith_number_mapping.csv` (رقم sunnah.com ↔ رقم islamware لكل
  سجل، أرقام ودرجات فقط).
- **الباقي:** عينة 20 من البخاري و20 من مسلم بعد الإصلاح: اختلاف لفظ حقيقي، غالباً 1–6 كلمات بحديث
  قصير (البخاري: 14 ≤15% من الكلمات، 5 بين 15–40%، 1 أكثر). بيضلوا لمراجع ولا بيدخلوا الموجة 1.
