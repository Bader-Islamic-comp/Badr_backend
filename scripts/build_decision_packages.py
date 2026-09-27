"""Generate the decision packages that are built from data (doc/decisions/01, 03, 04, 05).

    python scripts/build_decision_packages.py

01 licensing: terms quoted verbatim from the downloaded licence files, risk, recommendation, draft emails.
03 policies: one page per governance policy with its three open decisions and reviewer B's notes.
04 content: hadith selection and prophet source-map ranges, fail -> flag -> pass, with text copied from
   corpus/canonical and reviewer B's reasons.
05 evaluation: gold and harmful questions, fail -> flag -> pass.
Draft emails are drafts only; nothing is sent.
"""
import json
import sys

import yaml

import _common  # noqa: F401
from _common import ROOT
from companion_api.corpusprep import registry as registry_module
from companion_api.corpusprep.candidates import parse_quran_ref
from companion_api.corpusprep.fetch import raw_path

OUT = ROOT / "doc/decisions"
ORDER = {"fail": 0, "flag": 1, "pass": 2}


def _verdicts() -> dict[str, dict]:
    rows = {}
    for path in sorted((ROOT / "corpus/reviews/ai_prereview").glob("batch-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row["item_id"]] = row
    return rows


def _b(row: dict | None) -> str:
    if not row:
        return "ai_prereview: **not reviewed**"
    reasons = "؛ ".join(row["reasons"]) or "—"
    fix = f" — مقترح: {row['suggested_fix']}" if row.get("suggested_fix") else ""
    return f"ai_prereview: **{row['verdict']}** (ثقة {row['confidence']}) — {reasons}{fix}"


# --- 01 licensing ---------------------------------------------------------------------------------------
LICENSING = {
    "tanzil-quran": {
        "risk": "منخفض إلى متوسط: الشروط واضحة (CC BY 3.0 + منع التعديل)، والسؤال الوحيد هو النسخة المطبّعة للبحث.",
        "recommendation": "اعتماد (approve) لـ uthmani و simple مع إبقاء الإشعار، وطلب تأكيد مكتوب إنه النسخة المطبّعة الداخلية مسموحة. "
                          "ملف البيانات الوصفية: اعتماد للتحقق البنيوي فقط.",
        "to": "Tanzil Project (عبر tanzil.net / مجموعة tanzil-text)",
        "email": ("Subject: Permission question - Tanzil Quran text in a children's learning app\n\n"
                  "Dear Tanzil team,\n\nWe are building a children's Islamic learning app (ages 7-11). We display the "
                  "Tanzil Uthmani text verbatim, with your copyright notice and a link to tanzil.net, as your terms "
                  "require. For search only, we also keep an internal copy with diacritics removed and letters "
                  "normalized; it is never displayed. Could you confirm that this internal search copy is acceptable "
                  "under your terms, or tell us how you would like it handled?\n\nThank you,\nMousa al-Rashdan\n[Organisation, contact]"),
    },
    "alquran-cloud": {
        "risk": "مرتفع: لا يوجد ترخيص منشور للنسخة المنزّلة، والمصدر الأصلي (مجمّع الملك فهد) ما أعطى إذناً موثّقاً لنا.",
        "recommendation": "إبقاؤه candidate (defer) لحين إذن مكتوب من مجمّع الملك فهد لطباعة المصحف الشريف، أو اختيار تفسير بترخيص واضح.",
        "to": "مجمّع الملك فهد لطباعة المصحف الشريف (قسم الحقوق/الشؤون العلمية)",
        "email": ("الموضوع: طلب إذن باستخدام التفسير الميسّر في تطبيق تعليمي للأطفال\n\n"
                  "السلام عليكم ورحمة الله وبركاته،\n\nنعمل على تطبيق تعليمي إسلامي للأطفال (7-11 سنة) يعرض القرآن الكريم "
                  "بالنص العثماني ويعتمد على شرح مبسّط. نرغب في استخدام \"التفسير الميسّر\" الصادر عن المجمّع مرجعاً داخلياً "
                  "لمراجعينا ولنظام البحث، مع نسبته إلى المجمّع وعدم تعديل نصه. نرجو إفادتنا بشروط الإذن وصيغة النسبة المطلوبة، "
                  "والجهة المخوّلة بمنحه.\n\nوجزاكم الله خيراً،\nموسى الرشدان\n[الجهة، وسيلة التواصل]"),
    },
    "fawazahmed0-hadith-api": {
        "risk": "متوسط: المستودع في الملكية العامة، لكن مصدر النص العربي الأصلي غير موثّق، فالإهداء قد لا يغطي حقوق المصدر.",
        "recommendation": "اعتماد مشروط: approve بعد جواب صاحب المستودع عن مصدر النص؛ وإلا defer.",
        "to": "fawazahmed0 (GitHub: github.com/fawazahmed0/hadith-api)",
        "email": ("Subject: Source of the Arabic hadith text in hadith-api\n\nHello,\n\nThank you for hadith-api. We use the "
                  "Arabic Bukhari, Muslim and Nawawi editions (commit df57907) in a children's learning app, citing your "
                  "repository. Your repository is released under the Unlicense. Could you tell us where the Arabic text "
                  "comes from, so we can confirm we may use it under that dedication?\n\nThank you,\nMousa al-Rashdan"),
    },
    "mhashim6-open-hadith-data": {
        "risk": "متوسط: ODbL بيفرض النسبة والـ share-alike على أي قاعدة بيانات مشتقة.",
        "recommendation": "اعتماد للمطابقة فقط (approve) مع النسبة، وقرار صريح إنه ملف الـ mapping إذا نُشر بيتنشر بـ ODbL.",
        "to": "mhashim6 (GitHub: github.com/mhashim6/Open-Hadith-Data)",
        "email": ("Subject: Open-Hadith-Data (ODbL) used for cross-checking\n\nHello,\n\nWe use Open-Hadith-Data only to "
                  "cross-check the wording and numbering of Sahih al-Bukhari and Sahih Muslim in a children's learning app, "
                  "with attribution. We may publish a number-mapping table derived from it under ODbL. Is there anything "
                  "else you would like us to do beyond ODbL's terms?\n\nThank you,\nMousa al-Rashdan"),
    },
    "ahmedbaset-hadith-json": {
        "risk": "مرتفع: لا يوجد ملف ترخيص، والبيانات منقولة من sunnah.com.",
        "recommendation": "reject للاستخدام بالإصدارات؛ الاستمرار بالمطابقة الداخلية للنووية فقط لحين ترخيص. رياض الصالحين والأدب المفرد: "
                          "طلب ترخيص من sunnah.com أو الاكتفاء بالنطاق الحالي.",
        "to": "AhmedBaset (GitHub) و sunnah.com (للبيانات الأصلية)",
        "email": ("Subject: Licence for hadith-json (Riyad as-Salihin, Al-Adab Al-Mufrad, Nawawi 40)\n\nHello,\n\nWe would "
                  "like to use hadith-json (v1.2.0) for a children's learning app. The repository has no licence file, and "
                  "the README says the data was scraped from sunnah.com. Could you tell us under which licence, if any, we "
                  "may use it? Would sunnah.com's permission also be needed?\n\nThank you,\nMousa al-Rashdan"),
    },
    "qurancom-api": {
        "risk": "منخفض: ما في نص مستخدم، فقط أعداد الآيات للتحقق.",
        "recommendation": "approve للاستخدام البنيوي فقط (بدون نص).",
        "to": None, "email": None,
    },
}


def licensing() -> str:
    registry = registry_module.load(ROOT / "corpus/sources/registry.yaml")
    lines = ["# حزمة القرار 01 — التراخيص", "",
             "**صاحب القرار:** Mousa al-Rashdan (`role: governance`). **الوقت المتوقع:** 10 دقائق للقرارات؛ الإيميلات مسودات",
             "جاهزة للإرسال منك (ما انبعت شي). الشروط منقولة حرفياً من الملفات المنزّلة. جدول الحقوق الكامل:",
             "[`doc/governance/rights-clearance.md`](../governance/rights-clearance.md).", "",
             "| المصدر | الحالة اليوم | التوصية |", "| --- | --- | --- |"]
    datasets: dict[str, list] = {}
    for source in registry.sources:
        datasets.setdefault(source["dataset"], []).append(source)
    for dataset, sources in datasets.items():
        info = LICENSING.get(dataset)
        for source in sources:
            rec = "ملف ترخيص (مرجع فقط)" if source["role"] == "licence_text" else (info["recommendation"].split(":")[0]
                                                                                   if info else "—")
            lines.append(f"| `source:{source['source_id']}` | {source['status']} | {rec} |")
    for dataset, sources in datasets.items():
        info = LICENSING.get(dataset)
        if not info:
            continue
        lines += ["", f"## {dataset}", "", "- **البنود:** " + ", ".join(f"`source:{s['source_id']}`" for s in sources),
                  f"- **الخطر:** {info['risk']}", f"- **التوصية:** {info['recommendation']}", "", "**الشروط حرفياً:**", ""]
        if dataset == "tanzil-quran":
            terms = (ROOT / "corpus/canonical/quran/NOTICE.txt").read_text(encoding="utf-8").strip()
        else:
            licence = next((s for s in registry.sources if s["dataset"] == dataset and s["role"] == "licence_text"), None)
            terms = raw_path(ROOT / "corpus/raw", licence).read_text(encoding="utf-8").strip() if licence else \
                "لا يوجد نص ترخيص عند المصدر."
        lines += ["```text", terms, "```"]
        if info["email"]:
            lines += ["", f"**مسودة إيميل (لم تُرسل) — إلى:** {info['to']}", "", "```text", info["email"], "```"]
    lines += ["", "## صيغة القرار", "", "```yaml",
              "- decision_id: D-LIC-001", "  item_ids: [\"source:tanzil-quran-uthmani\", \"source:tanzil-quran-simple\"]",
              "  decision: approve", "  decided_by: Mousa al-Rashdan", "  role: governance", "  date: 2026-10-01",
              "  note: \"...\"", "```", "",
              "`approve` على مصدر = `cleared` بالـ registry؛ والقناة المنشورة ما بتقبل إلا مصادر `cleared`."]
    return "\n".join(lines) + "\n"


# --- 03 policies ----------------------------------------------------------------------------------------
POLICIES = {
    "scope": ("ما بيدخل الكوربس وما بيطلع برّاه: 10 استثناءات صريحة (فتاوى، خلافيات، إسرائيليات، ضعيف، تصوير الأنبياء، ...).",
              ["اعتماد قائمة الاستثناءات العشرة كما هي أو تعديلها.", "أي تفسير (إن وُجد) مسموح للموجة 1.",
               "سياسة الخلاف المعتبر (§6.5): أساسيات مشتركة فقط، أو منهج محدد."]),
    "source-policy": ("معايير قبول مصدر، وسلسلة الأدلة (url، طبعة، sha256، تاريخ)، ومصدران مستقلان للحديث.",
                      ["هل يُقبل مصدر نصّه الأصلي غير موثّق المنشأ.", "هل تدخل مجموعة بمصدر واحد أي إصدار.",
                       "من يعتمد طبعة جديدة لما يتغيّر sha256 المصدر."]),
    "rights-clearance": ("جدول لكل مصدر بالشروط حرفياً؛ كل التراخيص pending_legal حتى قرارك.",
                         ["القرارات بحزمة 01.", "من يرسل إيميلات طلب الإذن ومتى.", "ماذا يحدث لو ما جاء رد."]),
    "reviewer-policy": ("أدوار المراجعين، فصل الكاتب عن المراجع، إفصاح تعارض المصالح.",
                        ["أسماء المراجعين (حزمة 02).", "عدد المراجعين لكل بند (اليوم واحد).",
                         "هل يجب مطابقة الدور لنوع البند."]),
    "releases": ("إصدارات ثابتة للقراءة فقط، مؤشر current_release، rollback، عزل؛ المنشور يحتاج مصادر cleared.",
                 ["من يسمح له بـ promote و rollback.", "من يعلن عزلاً طارئاً.", "هل التقييم الشرعي/الأمان إلزامي قبل كل promote."]),
    "review-workflow": ("draft → in_review → approved/rejected/quarantined، والقرارات فقط من decisions.yaml، وسجل تدقيق.",
                        ["اعتماد أن approve/reject لا تأتي إلا من decisions.yaml.", "مدة الاحتفاظ بسجل التدقيق ونسخته الاحتياطية.",
                         "بناء بوابة المراجعة (UI) أم الاكتفاء بالملف."]),
    "re-review-policy": ("محفّزات إعادة المراجعة (تغيّر المصدر، الموديل، السياسة، المدة) ومدة مقترحة 12 شهراً.",
                         ["المدة.", "إضافة محفّز لتغيّر الموديل التوليدي/البرومبت/المسترجع (نبّه له B).",
                          "هل عيّنة الـ 5% الأسبوعية تُنقّح من بيانات الطفل قبل إرسالها (نبّه له B)."]),
}


def policies(verdicts: dict) -> str:
    lines = ["# حزمة القرار 03 — اعتماد السياسات", "",
             "**صاحب القرار:** Mousa al-Rashdan (`role: governance`). **الوقت المتوقع:** ~1 دقيقة لكل سياسة. كل سياسة مسودة",
             "بـ `doc/governance/`؛ ملاحظات الوكيل B بجانبها. ترتيب: fail ثم flag ثم pass.", ""]
    keys = sorted(POLICIES, key=lambda k: (ORDER.get((verdicts.get(f"policy-{k}") or {}).get("verdict"), 3), k))
    for key in keys:
        summary, points = POLICIES[key]
        lines += [f"## `policy-{key}` — [{key}.md](../governance/{key}.md)", "", summary, "", "**أهم 3 نقاط للقرار:**"]
        lines += [f"{n}. {point}" for n, point in enumerate(points, 1)]
        lines += ["", _b(verdicts.get(f"policy-{key}")), ""]
    lines += ["## صيغة القرار", "", "```yaml", "- decision_id: D-POL-001",
              "  item_ids: [\"policy-scope\", \"policy-source-policy\"]", "  decision: approve",
              "  decided_by: Mousa al-Rashdan", "  role: governance", "  date: 2026-10-01", "  note: \"...\"", "```"]
    return "\n".join(lines) + "\n"


# --- 04 content -----------------------------------------------------------------------------------------
def content(verdicts: dict) -> str:
    ayat = {(r["surah"], r["ayah"]): r["text_uthmani"] for r in map(json.loads, (ROOT / "corpus/canonical/quran/ayat.jsonl")
                                                                    .open(encoding="utf-8"))}
    hadith = {}
    for name in ("bukhari", "muslim"):
        for line in (ROOT / f"corpus/canonical/hadith/{name}.jsonl").open(encoding="utf-8"):
            row = json.loads(line)
            hadith[f"{name}:{row['number']}"] = row
    selection = yaml.safe_load((ROOT / "corpus/candidate/hadith_selection.yaml").read_text(encoding="utf-8"))["hadith"]
    items = []
    for n, entry in enumerate(selection, 1):
        item_id = f"selection-{n:02d}"
        row = hadith[entry["cluster_primary"]]
        body = (f"**{entry['cluster_primary']}**" + (f" (النووية {entry['number']})" if entry["collection"] == "nawawi40" else "")
                + f" — الموضوع: {entry['topic']} — الحكم: {row['grading']} ({row['grader']}) — المطابقة: {row['crosscheck_status']}"
                + f"\n\n<details><summary>النص (منقول من corpus/canonical)</summary>\n\n{row['arabic_text']}\n\n</details>")
        items.append((item_id, "hadith", body))
    for path in sorted((ROOT / "corpus/candidate/prophets").glob("*_source_map.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for n, item in enumerate(data["ranges"], 1):
            surah, first, last = parse_quran_ref(item["ref"])
            text = "\n".join(f"({surah}:{a}) {ayat[(surah, a)]}" for a in range(first, last + 1))
            body = (f"**{data['prophet_id']} — {item['ref']}** — {item['topic']}"
                    f"\n\n<details><summary>الآيات (منقولة من Tanzil)</summary>\n\n{text}\n\n</details>")
            items.append((f"map-{data['prophet_id']}-{n:02d}", "source_map_range", body))
    items.sort(key=lambda it: (ORDER.get((verdicts.get(it[0]) or {}).get("verdict"), 3), it[0]))
    counts = {v: sum(1 for i in items if (verdicts.get(i[0]) or {}).get("verdict") == v) for v in ORDER}
    lines = ["# حزمة القرار 04 — المحتوى الشرعي", "",
             "**صاحب القرار:** اللجنة الشرعية — مراجع مسجّل بـ `reviewers.yaml` بدور `scholarly` (حزمة 02 أولاً).",
             f"**العدد:** {len(items)} بند — fail {counts['fail']}، flag {counts['flag']}، pass {counts['pass']}. "
             "الترتيب: fail ثم flag ثم pass. أحكام B مساعدة فقط.",
             "**الوقت:** البنود fail و flag أولاً (~10 دقائق)؛ الـ pass ممكن قرار جماعي بعد نظرة سريعة.", "",
             "نص الآيات والأحاديث منقول حرفياً من الملفات المنزّلة؛ ما انكتب شي من الذاكرة.", ""]
    for item_id, kind, body in items:
        lines += [f"### `{item_id}`", "", body, "", _b(verdicts.get(item_id)), ""]
    lines += ["## صيغة القرار", "", "```yaml", "- decision_id: D-CNT-001",
              "  item_ids: [\"selection-01\", \"map-yusuf-01\"]", "  decision: approve   # أو reject / revise",
              "  decided_by: \"<اسم المراجع كما بـ reviewers.yaml>\"", "  role: scholarly", "  date: 2026-10-01",
              "  note: \"...\"", "```"]
    return "\n".join(lines) + "\n"


# --- 05 eval --------------------------------------------------------------------------------------------
def evaluation(verdicts: dict) -> str:
    gold = [json.loads(l) for l in (ROOT / "corpus/eval/gold.jsonl").open(encoding="utf-8")]
    harmful = [json.loads(l) for l in (ROOT / "corpus/eval/harmful.jsonl").open(encoding="utf-8")]
    lines = ["# حزمة القرار 05 — أسئلة التقييم (gold و harmful)", "",
             "**صاحب القرار:** Momen Alhamza (`role: pipeline`)؛ بنود `distress_disclosure-*` مع مسؤول الحماية.",
             "كل الأسئلة اصطناعية. الترتيب: fail ثم flag ثم pass. الـ pass بجدول مختصر للقرار الجماعي.", ""]
    for title, rows, render in (
        ("gold", gold, lambda r: f"{r['question']} — `{r['variant']}` — متوقع: {', '.join(r['expected_chunk_ids'][:4])}"),
        ("harmful", harmful, lambda r: f"{r['question']} — `{r['variant']}` — {r['category']} → **{r['expected_route']}**"),
    ):
        ordered = sorted(rows, key=lambda r: (ORDER.get((verdicts.get(r["id"]) or {}).get("verdict"), 3), r["id"]))
        counts = {v: sum(1 for r in rows if (verdicts.get(r["id"]) or {}).get("verdict") == v) for v in ORDER}
        lines += [f"## {title} — {len(rows)} سؤال (fail {counts['fail']}، flag {counts['flag']}, pass {counts['pass']})", ""]
        for row in ordered:
            verdict = (verdicts.get(row["id"]) or {}).get("verdict")
            if verdict in ("fail", "flag"):
                lines += [f"- `{row['id']}` {render(row)}  \n  {_b(verdicts.get(row['id']))}"]
        lines += ["", "<details><summary>البنود pass</summary>", "", "| id | السؤال |", "| --- | --- |"]
        lines += [f"| `{r['id']}` | {render(r)} |" for r in ordered if (verdicts.get(r["id"]) or {}).get("verdict") == "pass"]
        lines += ["", "</details>", ""]
    lines += ["## صيغة القرار", "", "```yaml", "- decision_id: D-EVAL-001", "  item_ids: [\"adam-01-msa\", \"adam-01-gulf\"]",
              "  decision: approve", "  decided_by: Momen Alhamza", "  role: pipeline", "  date: 2026-10-01", "  note: \"...\"", "```"]
    return "\n".join(lines) + "\n"


def main() -> int:
    verdicts = _verdicts()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, text in (("01-licensing.md", licensing()), ("03-policies.md", policies(verdicts)),
                       ("04-content-review.md", content(verdicts)), ("05-eval-review.md", evaluation(verdicts))):
        (OUT / name).write_text(text, encoding="utf-8")
        print(f"wrote doc/decisions/{name} ({len(text) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
