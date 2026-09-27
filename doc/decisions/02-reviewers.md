# حزمة القرار 02 — المراجعون وتعارض المصالح

**صاحب القرار:** Mousa al-Rashdan. **الوقت المتوقع:** 10 دقائق (تعبئة + قرار واحد).
**السياسة:** [`doc/governance/reviewer-policy.md`](../governance/reviewer-policy.md).

## ليش مهم

اليوم `corpus/governance/reviewers.yaml` فاضي، فـ **ولا موافقة على أي محتوى ممكنة**: `apply_decisions.py`
بيرفض أي قرار محتوى من شخص مش مسجّل. هاي الحزمة هي اللي بتفتح مسار المراجعة الشرعية.

## الخطوة 1: عبّي القائمة

انسخ الكتلة لكل مراجع بـ `corpus/governance/reviewers.yaml`:

```yaml
reviewers:
- name: "الاسم الكامل كما رح يكتبه بـ decided_by"
  qualified: true
  roles: [scholarly]            # scholarly | safeguarding | language (واحد أو أكثر)
  qualification_ref: "وين المؤهل موثّق (إجازة، شهادة، جهة)"
  conflicts: []                 # معرّفات بنود ما بيراجعها (مثلاً story-yusuf-s01 إذا كتبه)
  declared_on: 2026-10-01
```

| # | الاسم | الدور | المؤهل | تعارض مصالح معلن |
| --- | --- | --- | --- | --- |
| 1 | | scholarly | | |
| 2 | | scholarly | | |
| 3 | | safeguarding | | |
| 4 | | language | | |

**أسئلة الإفصاح لكل مراجع:** كتب أو شارك بكتابة بند؟ مصلحة مالية بمصدر أو ناشر؟ قرابة مع كاتب؟ أي
مصلحة ثانية بتحددها أنت؟

## الخطوة 2: القرار

```yaml
- decision_id: D-REV-001
  item_ids: ["reviewers"]
  decision: approve
  decided_by: Mousa al-Rashdan
  role: governance
  date: 2026-10-01
  note: "قائمة المراجعين بتاريخ ... معتمدة."
```

## قرارات مفتوحة ضمن هاي الحزمة

1. كم مراجع لازم لكل بند؟ (الأداة اليوم بتكتفي بواحد؛ الوكيل B نبّه إنه هاد ضعيف — `policy-reviewer-policy` flag.)
2. هل الدور لازم يطابق نوع البند (شرعي للحديث، حماية لبنود الضيق)؟ الأداة بتفرض الدور على المحتوى بس.
3. مدة تجديد الإفصاح.
