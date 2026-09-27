# حزمة القرار 01 — التراخيص

**صاحب القرار:** Mousa al-Rashdan (`role: governance`). **الوقت المتوقع:** 10 دقائق للقرارات؛ الإيميلات مسودات
جاهزة للإرسال منك (ما انبعت شي). الشروط منقولة حرفياً من الملفات المنزّلة. جدول الحقوق الكامل:
[`doc/governance/rights-clearance.md`](../governance/rights-clearance.md).

| المصدر | الحالة اليوم | التوصية |
| --- | --- | --- |
| `source:tanzil-quran-uthmani` | pending_legal | اعتماد (approve) لـ uthmani و simple مع إبقاء الإشعار، وطلب تأكيد مكتوب إنه النسخة المطبّعة الداخلية مسموحة. ملف البيانات الوصفية |
| `source:tanzil-quran-simple` | pending_legal | اعتماد (approve) لـ uthmani و simple مع إبقاء الإشعار، وطلب تأكيد مكتوب إنه النسخة المطبّعة الداخلية مسموحة. ملف البيانات الوصفية |
| `source:tanzil-quran-metadata` | candidate | اعتماد (approve) لـ uthmani و simple مع إبقاء الإشعار، وطلب تأكيد مكتوب إنه النسخة المطبّعة الداخلية مسموحة. ملف البيانات الوصفية |
| `source:qurancom-chapters` | candidate | approve للاستخدام البنيوي فقط (بدون نص). |
| `source:alquran-cloud-muyassar` | candidate | إبقاؤه candidate (defer) لحين إذن مكتوب من مجمّع الملك فهد لطباعة المصحف الشريف، أو اختيار تفسير بترخيص واضح. |
| `source:fawazahmed0-ara-bukhari` | pending_legal | اعتماد مشروط |
| `source:fawazahmed0-ara-muslim` | pending_legal | اعتماد مشروط |
| `source:fawazahmed0-ara-nawawi` | pending_legal | اعتماد مشروط |
| `source:fawazahmed0-license` | pending_legal | ملف ترخيص (مرجع فقط) |
| `source:mhashim6-bukhari` | pending_legal | اعتماد للمطابقة فقط (approve) مع النسبة، وقرار صريح إنه ملف الـ mapping إذا نُشر بيتنشر بـ ODbL. |
| `source:mhashim6-muslim` | pending_legal | اعتماد للمطابقة فقط (approve) مع النسبة، وقرار صريح إنه ملف الـ mapping إذا نُشر بيتنشر بـ ODbL. |
| `source:mhashim6-license` | pending_legal | ملف ترخيص (مرجع فقط) |
| `source:ahmedbaset-nawawi40` | candidate | reject للاستخدام بالإصدارات؛ الاستمرار بالمطابقة الداخلية للنووية فقط لحين ترخيص. رياض الصالحين والأدب المفرد |
| `source:ahmedbaset-riyadussalihin` | candidate | reject للاستخدام بالإصدارات؛ الاستمرار بالمطابقة الداخلية للنووية فقط لحين ترخيص. رياض الصالحين والأدب المفرد |
| `source:ahmedbaset-adab-mufrad` | candidate | reject للاستخدام بالإصدارات؛ الاستمرار بالمطابقة الداخلية للنووية فقط لحين ترخيص. رياض الصالحين والأدب المفرد |

## tanzil-quran

- **البنود:** `source:tanzil-quran-uthmani`, `source:tanzil-quran-simple`, `source:tanzil-quran-metadata`
- **الخطر:** منخفض إلى متوسط: الشروط واضحة (CC BY 3.0 + منع التعديل)، والسؤال الوحيد هو النسخة المطبّعة للبحث.
- **التوصية:** اعتماد (approve) لـ uthmani و simple مع إبقاء الإشعار، وطلب تأكيد مكتوب إنه النسخة المطبّعة الداخلية مسموحة. ملف البيانات الوصفية: اعتماد للتحقق البنيوي فقط.

**الشروط حرفياً:**

```text
# PLEASE DO NOT REMOVE OR CHANGE THIS COPYRIGHT BLOCK
#====================================================================
#
#  Tanzil Quran Text (Uthmani, Version 1.1)
#  Copyright (C) 2007-2026 Tanzil Project
#  License: Creative Commons Attribution 3.0
#
#  This copy of the Quran text is carefully produced, highly 
#  verified and continuously monitored by a group of specialists 
#  at Tanzil Project.
#
#  TERMS OF USE:
#
#  - Permission is granted to copy and distribute verbatim copies 
#    of this text, but CHANGING IT IS NOT ALLOWED.
#
#  - This Quran text can be used in any website or application, 
#    provided that its source (Tanzil Project) is clearly indicated, 
#    and a link is made to tanzil.net to enable users to keep
#    track of changes.
#
#  - This copyright notice shall be included in all verbatim copies 
#    of the text, and shall be reproduced appropriately in all files 
#    derived from or containing substantial portion of this text.
#
#  Please check updates at: http://tanzil.net/updates/
#
#====================================================================
```

**مسودة إيميل (لم تُرسل) — إلى:** Tanzil Project (عبر tanzil.net / مجموعة tanzil-text)

```text
Subject: Permission question - Tanzil Quran text in a children's learning app

Dear Tanzil team,

We are building a children's Islamic learning app (ages 7-11). We display the Tanzil Uthmani text verbatim, with your copyright notice and a link to tanzil.net, as your terms require. For search only, we also keep an internal copy with diacritics removed and letters normalized; it is never displayed. Could you confirm that this internal search copy is acceptable under your terms, or tell us how you would like it handled?

Thank you,
Mousa al-Rashdan
[Organisation, contact]
```

## qurancom-api

- **البنود:** `source:qurancom-chapters`
- **الخطر:** منخفض: ما في نص مستخدم، فقط أعداد الآيات للتحقق.
- **التوصية:** approve للاستخدام البنيوي فقط (بدون نص).

**الشروط حرفياً:**

```text
لا يوجد نص ترخيص عند المصدر.
```

## alquran-cloud

- **البنود:** `source:alquran-cloud-muyassar`
- **الخطر:** مرتفع: لا يوجد ترخيص منشور للنسخة المنزّلة، والمصدر الأصلي (مجمّع الملك فهد) ما أعطى إذناً موثّقاً لنا.
- **التوصية:** إبقاؤه candidate (defer) لحين إذن مكتوب من مجمّع الملك فهد لطباعة المصحف الشريف، أو اختيار تفسير بترخيص واضح.

**الشروط حرفياً:**

```text
لا يوجد نص ترخيص عند المصدر.
```

**مسودة إيميل (لم تُرسل) — إلى:** مجمّع الملك فهد لطباعة المصحف الشريف (قسم الحقوق/الشؤون العلمية)

```text
الموضوع: طلب إذن باستخدام التفسير الميسّر في تطبيق تعليمي للأطفال

السلام عليكم ورحمة الله وبركاته،

نعمل على تطبيق تعليمي إسلامي للأطفال (7-11 سنة) يعرض القرآن الكريم بالنص العثماني ويعتمد على شرح مبسّط. نرغب في استخدام "التفسير الميسّر" الصادر عن المجمّع مرجعاً داخلياً لمراجعينا ولنظام البحث، مع نسبته إلى المجمّع وعدم تعديل نصه. نرجو إفادتنا بشروط الإذن وصيغة النسبة المطلوبة، والجهة المخوّلة بمنحه.

وجزاكم الله خيراً،
موسى الرشدان
[الجهة، وسيلة التواصل]
```

## fawazahmed0-hadith-api

- **البنود:** `source:fawazahmed0-ara-bukhari`, `source:fawazahmed0-ara-muslim`, `source:fawazahmed0-ara-nawawi`, `source:fawazahmed0-license`
- **الخطر:** متوسط: المستودع في الملكية العامة، لكن مصدر النص العربي الأصلي غير موثّق، فالإهداء قد لا يغطي حقوق المصدر.
- **التوصية:** اعتماد مشروط: approve بعد جواب صاحب المستودع عن مصدر النص؛ وإلا defer.

**الشروط حرفياً:**

```text
This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.

In jurisdictions that recognize copyright laws, the author or authors
of this software dedicate any and all copyright interest in the
software to the public domain. We make this dedication for the benefit
of the public at large and to the detriment of our heirs and
successors. We intend this dedication to be an overt act of
relinquishment in perpetuity of all present and future rights to this
software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <https://unlicense.org>
```

**مسودة إيميل (لم تُرسل) — إلى:** fawazahmed0 (GitHub: github.com/fawazahmed0/hadith-api)

```text
Subject: Source of the Arabic hadith text in hadith-api

Hello,

Thank you for hadith-api. We use the Arabic Bukhari, Muslim and Nawawi editions (commit df57907) in a children's learning app, citing your repository. Your repository is released under the Unlicense. Could you tell us where the Arabic text comes from, so we can confirm we may use it under that dedication?

Thank you,
Mousa al-Rashdan
```

## mhashim6-open-hadith-data

- **البنود:** `source:mhashim6-bukhari`, `source:mhashim6-muslim`, `source:mhashim6-license`
- **الخطر:** متوسط: ODbL بيفرض النسبة والـ share-alike على أي قاعدة بيانات مشتقة.
- **التوصية:** اعتماد للمطابقة فقط (approve) مع النسبة، وقرار صريح إنه ملف الـ mapping إذا نُشر بيتنشر بـ ODbL.

**الشروط حرفياً:**

```text
This Open-Hadith-Data project is made available under the Open Database License:
http://opendatacommons.org/licenses/odbl/1.0/.
Any rights in individual contents of the database are licensed under the Database Contents License:
http://opendatacommons.org/licenses/dbcl/1.0/
```

**مسودة إيميل (لم تُرسل) — إلى:** mhashim6 (GitHub: github.com/mhashim6/Open-Hadith-Data)

```text
Subject: Open-Hadith-Data (ODbL) used for cross-checking

Hello,

We use Open-Hadith-Data only to cross-check the wording and numbering of Sahih al-Bukhari and Sahih Muslim in a children's learning app, with attribution. We may publish a number-mapping table derived from it under ODbL. Is there anything else you would like us to do beyond ODbL's terms?

Thank you,
Mousa al-Rashdan
```

## ahmedbaset-hadith-json

- **البنود:** `source:ahmedbaset-nawawi40`, `source:ahmedbaset-riyadussalihin`, `source:ahmedbaset-adab-mufrad`
- **الخطر:** مرتفع: لا يوجد ملف ترخيص، والبيانات منقولة من sunnah.com.
- **التوصية:** reject للاستخدام بالإصدارات؛ الاستمرار بالمطابقة الداخلية للنووية فقط لحين ترخيص. رياض الصالحين والأدب المفرد: طلب ترخيص من sunnah.com أو الاكتفاء بالنطاق الحالي.

**الشروط حرفياً:**

```text
لا يوجد نص ترخيص عند المصدر.
```

**مسودة إيميل (لم تُرسل) — إلى:** AhmedBaset (GitHub) و sunnah.com (للبيانات الأصلية)

```text
Subject: Licence for hadith-json (Riyad as-Salihin, Al-Adab Al-Mufrad, Nawawi 40)

Hello,

We would like to use hadith-json (v1.2.0) for a children's learning app. The repository has no licence file, and the README says the data was scraped from sunnah.com. Could you tell us under which licence, if any, we may use it? Would sunnah.com's permission also be needed?

Thank you,
Mousa al-Rashdan
```

## صيغة القرار

```yaml
- decision_id: D-LIC-001
  item_ids: ["source:tanzil-quran-uthmani", "source:tanzil-quran-simple"]
  decision: approve
  decided_by: Mousa al-Rashdan
  role: governance
  date: 2026-10-01
  note: "..."
```

`approve` على مصدر = `cleared` بالـ registry؛ والقناة المنشورة ما بتقبل إلا مصادر `cleared`.
