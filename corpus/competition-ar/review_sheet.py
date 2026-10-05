"""The scholarly review sheet for the package's flagged items (doc/decisions/07-competition-review.md).

    python corpus/competition-ar/review_sheet.py           write the sheet
    python corpus/competition-ar/review_sheet.py --check   exit 1 when the sheet is out of date

Every item of content.json with `needs_check` gets its wording, references, evidence link and entry, grading, what
changed, and the one question the reviewer decides, with room for the decision. The sheet is generated, so it
always shows the package as it is; tests/test_competition_ar.py fails when it is stale.
"""
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SHEET = ROOT / "doc/decisions/07-competition-review.md"

# The question each flagged item puts to the reviewer. A new flagged item without one gets the general question.
QUESTIONS = {
    "adam-01": "هل «وعلّمه الأسماء كلها» مطابقة للبقرة 31، وهل «أظهر الله بذلك فضل العلم الذي منحه له» معنى صحيح بلا "
               "زيادة على الآيات؟",
    "isa-01": "هل تسمية المبشِّر «المَلَك» صحيحة (الملائكة في آل عمران 45، و«رسول ربك» في مريم 19)؟",
    "morning-evening-three-surahs": "هل الدرجة «حسن» ونسبتها للألباني في صحيح أبي داود 5082 صحيحتان، وهل قراءة "
                                    "السور الثلاث ثلاثًا صباحًا ومساءً هي ما يدل عليه الحديث؟",
    "morning-by-god": "هل صيغة الصباح بهذا اللفظ («…وبك نموت، وإليك النشور») ومصدرها أبو داود 5068 صحيحان للتعليم؟",
    "evening-by-god": "أي صيغة للمساء نعلّمها؟ (أ) اللفظ الحالي من أبي داود 5068، أو (ب) رواية «…وبك أصبحنا … وإليك "
                      "المصير» (البغوي، شرح السنة؛ الترمذي 3391). إن اخترت (ب) فاكتب لفظها كاملًا كما في المصدر.",
    "after-prayer-istighfar": "هل «أستغفر الله» ثلاثًا بعد السلام مطابقة لصحيح مسلم 591 كما يعرضه الرابط؟",
    "after-prayer-salam": "هل اللفظ بلا «يا» («تباركت ذا الجلال والإكرام») هو لفظ مسلم 591 الذي نعلّمه؟",
    "prayer-03": "هل هذه الخطوة تعليم مبسّط صحيح لحديث المسيء صلاته (البخاري 757)، والطمأنينة فيها كما ينبغي؟",
    "prayer-04": "هل هذه الخطوة تعليم مبسّط صحيح لحديث المسيء صلاته (البخاري 757)، والطمأنينة فيها كما ينبغي؟",
    "prayer-05": "هل هذه الخطوة تعليم مبسّط صحيح لحديث المسيء صلاته (البخاري 757)، والطمأنينة فيها كما ينبغي؟",
}
GENERAL = "هل الصياغة والمرجع والدليل صحيحة ومناسبة لطفل؟"
SECTIONS = {"stories": "قصة", "adhkar": "ذكر", "daily_duas": "دعاء", "prayer_learning": "درس الصلاة"}


def flagged(content: dict) -> list[tuple[str, dict]]:
    """(section, item) for every item marked `needs_check`, in the package's order."""
    found = []

    def walk(node, section):
        if isinstance(node, dict):
            if node.get("needs_check"):
                found.append((section, node))
            for value in node.values():
                walk(value, section)
        elif isinstance(node, list):
            for value in node:
                walk(value, section)

    for section in SECTIONS:
        walk(content.get(section), section)
    return found


def render(content: dict) -> str:
    items = flagged(content)
    lines = [
        "# حزمة القرار 07 — مراجعة شرعية لعناصر حزمة المسابقة المعلَّمة",
        "",
        "مولَّدة من `corpus/competition-ar/content.json` بـ `python corpus/competition-ar/review_sheet.py`؛ لا تُعدَّل "
        "يدويًا.",
        "",
        f"**صاحب القرار:** مراجع شرعي مؤهل (`role: religious`). **عدد البنود:** {len(items)}. **الوقت المتوقع:** "
        "نحو دقيقتين لكل بند.",
        "",
        "لكل بند: اقرأ الصياغة والدليل، ثم اكتب القرار: **اعتماد** كما هي، أو **تعديل** مع الصياغة الصحيحة، أو "
        "**رفض**. روابط الدرر تفتح الموضع الذي تذكره خانة «الموضع».",
        "",
        "بعد المراجعة يحدّث الفريق `content.json` (الصياغة المعتمدة، `needs_check: false`، `review_status: approved`)، "
        "ويضيف المراجع سطرًا في `corpus/competition-ar/approvals.json` تحت `package_reviews` باسمه ومرجع مؤهله "
        "وتجزئة المحتوى، كما يطلب `validate.py --release`.",
        "",
    ]
    for number, (section, item) in enumerate(items, start=1):
        wording = item.get("display") or item.get("text") or ""
        lines += [f"## {number}. `{item['id']}` ({SECTIONS[section]})", "",
                  f"**الصياغة الحالية:** {wording}", ""]
        if item.get("repeat"):
            lines += [f"**التكرار:** {item['repeat']}", ""]
        if item.get("lesson"):
            lines += [f"**الدرس للطفل:** {item['lesson']}", ""]
        lines += [f"**المراجع:** {'، '.join(f'`{ref}`' for ref in item.get('refs', []))}", ""]
        if item.get("evidence_url"):
            entry = item.get("evidence_entry", "")
            lines += [f"**الدليل:** [{item['evidence_url']}]({item['evidence_url']})"
                      + (f" — الموضع: {entry}" if entry else ""), ""]
        if item.get("grading"):
            lines += [f"**الدرجة:** {item['grading']}", ""]
        if item.get("change_note"):
            lines += [f"**ما تغيّر:** {item['change_note']}", ""]
        if item.get("review_note"):
            lines += [f"**ملاحظة للمراجع:** {item['review_note']}", ""]
        lines += [f"**السؤال:** {QUESTIONS.get(item['id'], GENERAL)}", "",
                  "| القرار (اعتماد / تعديل / رفض) | الصياغة المعدّلة (عند التعديل) | ملاحظة |",
                  "| --- | --- | --- |",
                  "|  |  |  |", ""]
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    content = json.loads((HERE / "content.json").read_text(encoding="utf-8"))
    text = render(content)
    if "--check" in args:
        current = SHEET.read_text(encoding="utf-8") if SHEET.is_file() else ""
        if current != text:
            print(f"{SHEET.relative_to(ROOT)} is out of date: run python corpus/competition-ar/review_sheet.py")
            return 1
        print("review sheet up to date")
        return 0
    SHEET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {SHEET.relative_to(ROOT)} ({len(flagged(content))} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
