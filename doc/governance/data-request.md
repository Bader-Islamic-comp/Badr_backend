# Data request to the organizers (draft, not sent)

Status: **draft for the governance owner (Mousa al-Rashdan); nothing has been sent.** It asks the challenge's
organizers, or Dorar directly, for the reference package's data that scripts cannot fetch: dorar.net answers
scripted requests with Cloudflare 403 ("you have been blocked"), and this project does not work around that
block. Background: [`reference-package.md`](reference-package.md), open question Q3.

- **To:** the organizers of «تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي».
- **Alternative:** Dorar's support team, `support@dorar.net` (the same text, with the first paragraph addressed
  to them).
- **Before sending:** the governance owner fills in the team's name, contact person and email, and attaches the
  reference to the organizers' permission once it is confirmed in writing (open question Q5).

The Arabic text is the one to send; the English text below it is for the team's review.

---

## العربية

**الموضوع:** طلب نسخة من بيانات موسوعات «الدرر السنية» المدرجة في «المرجعية والحزمة العلمية والبيانات» (الإصدار 20/3/1448)

السلام عليكم ورحمة الله وبركاته،

نحن فريق مشروع «روبرت»، المشارك في «تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي». روبرت رفيقٌ تعليمي
للأطفال من 7 إلى 11 سنة، يجيب عن أسئلتهم الدينية من محتوى موثّق ومراجَع فقط، ويُحيل ما سوى ذلك إلى الوالدين أو
المعلّم أو أهل العلم.

تنصّ الحزمة المرجعية للتحدي على موسوعات «الدرر السنية» مصدرًا معتمدًا للتفسير والحديث والعقيدة. غير أن موقع
dorar.net يرفض الطلبات الآلية (رسالة Cloudflare: you have been blocked)، ونحن لا نتجاوز هذا المنع ولا نحاول
الالتفاف عليه. لذا نرجو تزويدنا بنسخة من البيانات الآتية، بأي صيغة متاحة (JSON أو CSV أو غيرهما)، مع رقم الإصدار
وتاريخه وشروط الاستخدام:

1. **موسوعة التفسير** (dorar.net/tafseer): لكل مقطع: «غريب الكلمات»، و«المعنى الإجمالي»، و«تفسير الآيات»،
   و«الفوائد التربوية»، مع رقم السورة وأرقام الآيات التي يغطيها المقطع.
2. **الموسوعة الحديثية** (dorar.net/hadith): لأحاديث صحيح البخاري وصحيح مسلم والأربعين النووية ورياض الصالحين
   والأدب المفرد: درجة الحديث، واسم المحدِّث الذي حكم عليه، والكتاب، ورقم الحديث فيه. ولصحيح مسلم خاصةً: أرقام
   الأحاديث بترقيم محمد فؤاد عبد الباقي؛ فهي تمكّننا من ربط 1,189 إحالةً إلى صحيح مسلم في تفسير ابن كثير لا نستطيع
   ربطها اليوم لاختلاف الترقيم.
3. **الموسوعة العقدية** (dorar.net/aqeeda): الأقسام التي ترونها مناسبة لأطفال من 7 إلى 11 سنة (كأركان الإيمان
   ومعاني الأسماء الحسنى بعبارة ميسّرة).
4. **موسوعة الأخلاق والسلوك** و**موسوعة الآداب الشرعية**.
5. قائمة **«أحاديث منتشرة لا تصح»**، لنمنع روبرت من نسبة أي منها إلى النبي ﷺ، ولنختبره عليها.

**الاستخدام المقصود:**

- نسخة محفوظة داخل خادم المشروع (offline)، ولا يتصل روبرت بموقع الدرر أثناء الاستخدام، ولا يبحث في الإنترنت.
- لا يصل نصٌّ إلى طفل قبل أن يراجعه مراجعون مؤهَّلون، ويُعرض النص كما هو منسوبًا إلى «الدرر السنية» مع موضعه،
  ولا يُغيَّر ولا يُنسب إلى غير مصدره.
- لا نعيد نشر البيانات قاعدةَ بيانات أو مجموعة بيانات، ونحفظ رقم الإصدار، ونحدّث النسخة عند صدور تصحيحات،
  ونحذفها إن طلبتم ذلك.
- لا نجمع من الأطفال بيانات شخصية لهذا الغرض.

نشكر لكم تعاونكم، ونسأل الله أن يجعله في ميزان حسناتكم.

[اسم الفريق، والشخص المسؤول، والبريد الإلكتروني]

---

## English

**Subject:** Request for a copy of the Dorar encyclopedias' data listed in the reference package «المرجعية والحزمة
العلمية والبيانات» (version 20/3/1448)

Peace be upon you,

We are the team behind "Robert", an entry in the AI in the Service of Islamic Content challenge. Robert is a
learning companion for children aged 7 to 11. He answers their religious questions only from documented,
reviewed content, and refers everything else to a parent, a teacher or a scholar.

The challenge's reference package names the Dorar encyclopedias as an approved source for tafsir, hadith and
creed. dorar.net refuses scripted requests (Cloudflare: "you have been blocked"), and we do not work around that
block. We therefore ask for a copy of the following, in any available format (JSON, CSV or other), with its
version, date and terms of use:

1. **The tafsir encyclopedia** (dorar.net/tafseer): for each passage, the difficult words (غريب الكلمات), the
   overall meaning (المعنى الإجمالي), the explanation of the ayat (تفسير الآيات) and the lessons for upbringing
   (الفوائد التربوية), with the surah and the ayat each passage covers.
2. **The hadith encyclopedia** (dorar.net/hadith): for the hadith of Sahih al-Bukhari, Sahih Muslim, an-Nawawi's
   Forty, Riyad as-Salihin and al-Adab al-Mufrad: the grading, the name of the scholar who graded it, the book and
   the hadith's number in it. For Sahih Muslim in particular, the numbers in Muhammad Fu'ad Abdul-Baqi's numbering:
   they would let us link 1,189 citations of Sahih Muslim in Tafsir Ibn Kathir that we cannot link today because
   the numberings differ.
3. **The creed encyclopedia** (dorar.net/aqeeda): the sections you consider suitable for children aged 7 to 11
   (such as the pillars of iman and the meanings of Allah's names in simple words).
4. **The encyclopedia of ethics and conduct** (موسوعة الأخلاق والسلوك) and **the encyclopedia of Islamic
   etiquette** (موسوعة الآداب الشرعية).
5. The list **«أحاديث منتشرة لا تصح»** (widespread hadith that are not authentic), so that Robert never attributes
   any of them to the Prophet ﷺ, and so that we can test him on them.

**Intended use:**

- An offline copy kept inside the project's server. Robert never contacts dorar.net while in use and never
  searches the web.
- No text reaches a child before qualified reviewers have checked it. Text is shown as it is, attributed to
  Dorar with its location, never changed and never attributed to another source.
- We do not republish the data as a database or dataset; we keep the version, update the copy when
  corrections are published, and delete it if you ask.
- No personal data is collected from children for this purpose.

Thank you for your help.

[Team name, contact person, email]

---

## The Bayyinat PDF: a manual download

«بينات - أسئلة وأجوبة عن الإسلام» (Osool Center, 1445 AH) is listed under «الشبهات والأسئلة المتكررة». It is
for adults; the project uses it only to write test questions. dawa.center's robots.txt disallows automated
downloads, so a person downloads it:

1. Open <https://dawa.center/file/7937> in a browser and download the Arabic PDF from that page. Do not script
   the download.
2. Save it as `corpus/raw/dawa-center-bayyinat/dawa-center-bayyinat.pdf`. `corpus/raw/` is outside git; never
   commit the PDF.
3. Compute its digest: `python -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" corpus/raw/dawa-center-bayyinat/dawa-center-bayyinat.pdf`.
4. Register it in `corpus/sources/registry.yaml` as `dawa-center-bayyinat`: `acquisition: manual`,
   `status: candidate`, `package_rule: listed`, the URL above, the digest and the download time, and the site's
   terms in `license` and `terms_summary`. The registry accepts no `pdf` format yet: the pipeline owner adds it to
   `FORMATS` in `src/companion_api/corpusprep/registry.py` first. `scripts/fetch_sources.py` then verifies the
   file on every run and never downloads it.
5. Name the new registry id in the «الشبهات والأسئلة المتكررة» row of `corpus/sources/reference_package.yaml`
   (`acquisition: manual`, `registry: [dawa-center-bayyinat]`) and run `python scripts/check_reference_package.py --write`.
