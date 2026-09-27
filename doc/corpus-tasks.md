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
- **الهدف:** توثيق شو بيدخل الكوربس وشو لأ صراحة — plan.md مرحلة 4 بند 1: فتاوى،
  مسائل خلافية متقدمة، إسرائيليات، أحاديث ضعيفة، تصوير الأنبياء والملائكة، إلخ.
- **معايير القبول:** مستند out-of-scope صريح لا يفترض قرارات architecture.md §18
  (السوق، العمر الدقيق، المنهج)، بل يسجّلها كأسئلة مفتوحة.
- **شو انعمل:** لسا لأ.
- **الأدلة:** —
- **شو محتاج قرار بشري:** نطاق السوق/العمر/المنهج (architecture.md §18)؛ قائمة
  الاستثناءات الشرعية النهائية من اللجنة.
- **الحالة:** not_started

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
  السياسة المكتوبة نفسها لسا (المرحلة 4).
- **الأدلة:** `corpus/sources/registry.yaml`؛ `python3 scripts/fetch_sources.py` (كل
  المصادر `cached`)؛ `python3 scripts/fetch_sources.py --refresh --no-build` (كل المصادر
  `verified`)؛ `PYTHONPATH=src python3 -m pytest -q tests/test_corpusprep.py` (16 passed).
- **شو محتاج قرار بشري:** موافقة اللجنة على قائمة المصادر؛ هل يُقبل مصدر نصّه الأصلي
  غير موثّق المنشأ (`fawazahmed0` ما بيذكر مصدر النص العربي).
- **الحالة:** in_progress

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
  للتحقق من العدد فقط. جدول الحقوق الكامل بنص الشروط حرفياً = المرحلة 4.
- **الأدلة:** `corpus/sources/registry.yaml`؛ قسم "Source status" بـ
  `corpus/reports/hadith_crosscheck.md`.
- **شو محتاج قرار بشري (Mousa al-Rashdan):** (1) Tanzil بيمنع "تغيير النص" — هل النسخة
  المطبّعة للبحث فقط (`text_normalized`) مسموحة؟ (2) شروط الـ share-alike بـ ODbL لو بنينا
  قاعدة بيانات مشتقة. (3) ترخيص التفسير الميسّر من مجمّع الملك فهد مباشرة. (4) رياض الصالحين
  والأدب المفرد: ما لقينا مصدراً مفتوحاً بترخيص واضح. لا يوجد API key لـ sunnah.com (قرار
  المستخدم 2026-09-27).
- **الحالة:** in_progress

### 4. Reviewer qualification and conflict-of-interest policy
[ClickUp](https://app.clickup.com/t/z8q7hbct4c)

- **المالك:** Mousa al-Rashdan.
- **الهدف:** قالب سياسة: مؤهلات المراجع، تعارض المصالح، فصل الكاتب عن المراجع
  (plan.md مرحلة 4 بند 4).
- **معايير القبول:** مسودة سياسة + قاعدة آلية تمنع موافقة مراجع هو نفسه الكاتب
  (تُنفَّذ لاحقاً بأداة `review` بالمرحلة 4 بند 6).
- **شو انعمل:** لسا لأ.
- **الأدلة:** —
- **شو محتاج قرار بشري:** تسمية المراجعين المؤهلين فعلياً.
- **الحالة:** not_started

### 5. Immutable corpus releases with rollback
[ClickUp](https://app.clickup.com/t/z8q7hbct4d)

- **المالك:** Mousa al-Rashdan (سياسة) — التنفيذ التقني عند Momen Alhamza.
- **الهدف:** `scripts/build_release.py` ينتج `releases/{release_id}/` للقراءة
  فقط بـ manifest (ملفات + sha256 + نسخة registry + موديل embedding + git
  commit)، مع مؤشر `current_release`، و`scripts/rollback.py` (plan.md مرحلة 4
  بند 5).
- **معايير القبول:** اختبار تعديل ملف منشور يفشّل التحقق؛ اختبار rollback
  برجّع للإصدار السابق. **يبني فوق `release.write_release` /
  `release.load_release` الموجودين حالياً (نفس manifest.json / chunks.jsonl /
  vectors.f32 وsha256)، ما بيعمل صيغة موازية.**
- **شو انعمل:** لسا لأ. الأساس الموجود: `src/companion_api/rag/release.py`
  (immutable releases + sha256 checksums موجودة أصلاً لصيغة الـ chunks/vectors،
  لكن بدون `current_release` pointer ولا nested registry/git-commit metadata
  ولا `rollback.py` منفصل).
- **الأدلة:** `src/companion_api/rag/release.py` (اليوم)؛ لاحقاً
  `python -m scripts.build_release` و`python -m scripts.rollback` + نتائج pytest.
- **شو محتاج قرار بشري:** لا شيء حالياً.
- **الحالة:** not_started

### 6. Review workflow tooling and admin UI
[ClickUp](https://app.clickup.com/t/z8q7hbct4e)

- **المالك:** Mousa al-Rashdan (سياسة) — التنفيذ التقني عند Momen Alhamza.
- **الهدف:** حالات `draft → in_review → approved / rejected / quarantined`، و
  CLI: `review list / approve / reject / quarantine`، يرفض الموافقة إذا الكاتب
  هو المراجع (plan.md مرحلة 4 بند 6). لو في admin بالـ backend، endpoints
  بسيطة؛ وإلا توثيق الواجهة فقط بدون UI كامل.
- **معايير القبول:** CLI يعمل ومختبر؛ منع self-review مثبت باختبار.
- **شو انعمل:** لسا لأ. الموجود اليوم: `review.status` بسيط (`draft`/`approved`)
  بـ `corpus.py`، بدون `in_review`/`rejected`/`quarantined` ولا CLI مراجعة.
- **الأدلة:** —
- **شو محتاج قرار بشري:** هل يوجد admin UI بالـ backend فعلاً أصلاً؟ (فحص
  `src/companion_api/main.py` — لا يوجد حالياً admin router).
- **الحالة:** not_started

### 7. Audit trail for every approval
[ClickUp](https://app.clickup.com/t/z8q7hbct4f)

- **المالك:** Mousa al-Rashdan (سياسة) — التنفيذ التقني عند Momen Alhamza.
- **الهدف:** سجل append-only (jsonl) بـ hash chain، وأمر `verify_audit` يكشف أي
  تلاعب. كل تغيير حالة يمر من هون (plan.md مرحلة 4 بند 7).
- **معايير القبول:** اختبار يعدّل سطراً بالسجل ويتأكد `verify_audit` يكشفه.
- **شو انعمل:** لسا لأ.
- **الأدلة:** —
- **شو محتاج قرار بشري:** لا شيء حالياً.
- **الحالة:** not_started

### 8. Re-review cadence and change triggers
[ClickUp](https://app.clickup.com/t/z8q7hbct4h)

- **المالك:** Mousa al-Rashdan (سياسة) — التنفيذ التقني عند Momen Alhamza.
- **الهدف:** سياسة مقترحة + `scripts/due_for_review.py` يعلّم القطع المستحقة
  بسبب تغيّر sha256 المصدر، أو موديل الـ embedding، أو السياسة، أو مرور المدة
  (plan.md مرحلة 4 بند 8).
- **معايير القبول:** السكربت يشتغل على release فعلي ويطبع قائمة قطع مستحقة
  بسبب واضح.
- **شو انعمل:** لسا لأ.
- **الأدلة:** —
- **شو محتاج قرار بشري:** المدة الزمنية المقترحة للـ cadence.
- **الحالة:** not_started

---

## Pipeline & Evaluation (Momen Alhamza)

### 9. Structure-aware ingestion and chunking
[ClickUp](https://app.clickup.com/t/z8q7hbct4g)

- **المالك:** Momen Alhamza.
- **الهدف:** جدول التقطيع بـ plan.md مكوّن 2 (آيات 1–8، حديث قصير/طويل،
  context_header، تطبيع عربي للفهرس، aliases.yaml، أسئلة افتراضية `generated:
  true`). النطاق: طبقة 0 كاملة + الموجة 1 (5 أنبياء + 40 حديث).
- **معايير القبول:** انظر "Execution plan" تحت — القرار الأساسي: **لا نبني
  مقطّعاً موازياً**؛ نمثّل الوحدات الدينية كـ `Document`/`Unit` بصيغة
  `corpus.py` الموجودة (بحقول `section`/`reference`/`keepWithNext`) ونمرّرها
  على `chunking.chunk_document` (`chunk-v1`) الموجود فعلاً. توسيعات الحقول
  (parent/child للحديث الطويل، cluster_id للمكرّر، مراجع متعددة بالمشهد الواحد)
  تحتاج تصميماً متوافقاً للـ dataclasses الحالية، موثّق كسؤال هندسي مفتوح.
- **شو انعمل:** لسا لأ. الأساس الموجود: `corpus.py` (يدعم أصلاً
  `contentType: quran/tafsir/hadith/story`, `grading` إلزامي للحديث، `reference`
  إلزامي لكل آية قرآن)، `chunking.py` (`chunk-v1`، تقطيع حسب section +
  keepWithNext + ميزانية كلمات، بدون تقسيم unit).
- **الأدلة:** `src/companion_api/rag/corpus.py`,
  `src/companion_api/rag/chunking.py`، أوامر
  `python -m companion_api.rag.pipeline validate` /
  `python -m companion_api.rag.pipeline build`.
- **شو محتاج قرار بشري:** لا شيء. الطبقة 0 صارت جاهزة كمدخل (المرحلة 1:
  `corpus/canonical/`). قرارات المستخدم 2026-09-27: `source_refs` قائمة مع بقاء
  `reference` القديم مقروءاً؛ `parent_id`/`cluster_id` حقول اختيارية بنسخة `chunk-v2`
  و`chunk-v1` يضل يتقرأ.
- **الحالة:** not_started

### 10. Age-band adaptation, human-written and reviewed
[ClickUp](https://app.clickup.com/t/z8q7hbct4j)

- **المالك:** Momen Alhamza (الأداة) — الكتابة بشرية دايماً (plan.md/المهمة).
- **الهدف:** هيكل فقط (schema + قوالب فارغة + مدقق آلي + WRITING_GUIDE.md) بدون
  أي نص موجّه للطفل مكتوب من الموديل (plan.md مرحلة 3).
- **معايير القبول:** مدقق آلي يتحقق: طول الجملة، عدد الكلمات، وجود
  `source_refs`، وعدم وجود نص قرآني/حديثي حرفي داخل نص الطفل (مقارنة مع
  canonical).
- **شو انعمل:** لسا لأ.
- **الأدلة:** —
- **شو محتاج قرار بشري:** العمر الدقيق للإطلاق (`architecture.md` §18 بند 1) مفتوح.
  **محسوم (المستخدم، 2026-09-27):** الفئات `7-9`/`10-11` من `AGE_BANDS` بالكود هي
  المرجع؛ `plan.md` انعدّل ليطابقها، والقوالب بالمرحلة 3 رح تستخدمها.
- **الحالة:** not_started

### 11. Embedding model selection, evaluated on Arabic and transliteration
[ClickUp](https://app.clickup.com/t/z8q7hbct4k)

- **المالك:** Momen Alhamza.
- **الهدف:** مقارنة BM25 وحده، BGE-M3، multilingual-e5-large،
  Qwen3-Embedding، وhybrid RRF (k=60)، مع/بدون reranker (plan.md مكوّن 2 و9).
- **معايير القبول:** Recall@1/5/10، MRR، nDCG@10، دقة عتبة الاعتذار، مقسّمة حسب
  variant + `doc/adr-0005-embedding-selection.md` بحالة `proposed`.
- **شو انعمل:** لسا لأ. الأساس الموجود: `embeddings.py` يدعم أصلاً
  `HashingEmbedder` (offline) و`OpenAICompatibleEmbedder` (قابل للتوسعة لموديلات
  أخرى عبر LiteLLM-compatible endpoint)، و`retriever.py` يطبّق hybrid RRF
  (`hybrid-rrf-v1`) فعلاً بنفس k=60.
- **الأدلة:** `src/companion_api/rag/embeddings.py`,
  `src/companion_api/rag/retriever.py`، لاحقاً
  `python -m companion_api.rag.evaluate`.
- **شو محتاج قرار بشري:** هذا التشغيل قد يأخذ وقتاً طويلاً (تنزيل موديلات +
  قياس) — سأخبرك بالوقت المتوقع قبل التشغيل الفعلي بالمرحلة 5.
- **الحالة:** not_started

### 12. Gold question set with approved answers and expected citations
[ClickUp](https://app.clickup.com/t/z8q7hbct4m)

- **المالك:** Momen Alhamza (الأداة) — الموافقة النهائية بشرية.
- **الهدف:** `corpus/eval/gold.jsonl`، 300 سؤال+ (plan.md مكوّن 9؛ المهمة تفصّل
  variants: msa/gulf/levantine/egyptian/misspelled/arabizi/english_transliteration).
- **معايير القبول:** كل سؤال فيه `question`, `variant`, `expected_chunk_ids`,
  `expected_answer_notes`, `approval_status: pending`.
- **شو انعمل:** لسا لأ. الأساس الموجود: `corpus.py.parse_eval` يدعم صيغة
  `eval.json` أبسط (`id/question/expect{answerTypes,documents}`) لكل كوربس على
  حدة — `gold.jsonl` هو مجموعة تقييم مستقلة أوسع، منفصلة عن `eval.json` تبع كل
  كوربس فردي، وليست بديلاً عنها.
- **الأدلة:** —
- **شو محتاج قرار بشري:** لا شيء لبدء الهيكلة؛ المحتوى يعتمد على وجود كوربس
  candidate فعلي أولاً (تاسك 9).
- **الحالة:** not_started

### 13. Harmful and out-of-scope question set
[ClickUp](https://app.clickup.com/t/z8q7hbct4n)

- **المالك:** Momen Alhamza.
- **الهدف:** `corpus/eval/harmful.jsonl`، 150 سؤال+: فتوى، خارج الكوربس، حديث
  موضوع مشهور (بالوصف لا بالنص)، خلط بين نبيين، prompt injection، بيانات
  شخصية، إفصاح عن ضيق (plan.md مكوّن 9).
- **معايير القبول:** كل سؤال فيه `expected_route`:
  abstain/redirect/safety/refuse.
- **شو انعمل:** لسا لأ.
- **الأدلة:** —
- **شو محتاج قرار بشري:** لا شيء لبدء الهيكلة.
- **الحالة:** not_started

### 14. Retrieval quality metrics dashboard
[ClickUp](https://app.clickup.com/t/z8q7hbct4q)

- **المالك:** Momen Alhamza.
- **الهدف:** `scripts/eval_retrieval.py` يكتب `reports/retrieval/history.jsonl`
  ويولّد `reports/retrieval/index.html` ثابت بدون إنترنت (plan.md مكوّن 9).
- **معايير القبول:** المقاييس + التوزيع حسب variant + أسوأ 20 سؤال + التطور عبر
  التشغيلات، تعمل offline بالكامل.
- **شو انعمل:** لسا لأ. الأساس الموجود: `evaluate.py` (`python -m
  companion_api.rag.evaluate`) يطبّق recall@4 + دقة التوجيه أصلاً؛
  `eval_retrieval.py` يوسّعه بتقرير HTML وتاريخ تشغيلات، لا يستبدله.
- **الأدلة:** `src/companion_api/rag/evaluate.py` (اليوم).
- **شو محتاج قرار بشري:** لا شيء حالياً.
- **الحالة:** not_started

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
| البخاري | 7580 سجل (9 فاضيين بالمصدر): 6795 تطابق، 512 محتوى بمدخل أطول، 205 اختلاف نص، 68 بلا مقابل |
| مسلم | 7360 سجل (203 فاضيين بالمصدر): 3337 تطابق، 2876 محتوى بمدخل أطول، 1109 اختلاف نص، 38 بلا مقابل |
| الأربعون النووية | 42 سجل: 38 تطابق، 4 اختلاف نص؛ بدون حكم منظّم، فكلها غير مؤهلة |
| رياض الصالحين | 1896 سجل، `single_source`، غير مؤهلة (بدون حكم وترخيص غير واضح) |
| الأدب المفرد | 1326 سجل، `single_source`، غير مؤهلة (بدون حكم وترخيص غير واضح) |
