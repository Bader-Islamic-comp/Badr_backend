"""Arabic and Arabizi routing patterns (router dev-patterns-v2, small-talk-v2).

THIS IS NOT AN APPROVED SAFEGUARDING CLASSIFIER. Like the English lists in
`router.py`, these are development patterns written to fail towards the fixed
replies, drafted from the 16 distress, 25 ruling, 20 injection and 15
personal-data questions of `corpus/eval/harmful.jsonl` and common dialect
variants (MSA, Levantine, Gulf, Egyptian). They need review by native-speaking
safeguarding reviewers before any child sees them.

Every Arabic pattern is written in search-folded form, as `router.matchable`
produces it: no diacritics or tatweel, أ إ آ ٱ -> ا, ى -> ي, ة -> ه, ؤ -> و,
ئ -> ي. So "يؤذيني" is written "يوذيني" and "حزينة" is written "حزينه". A
leading و ("and") is attached to the next word in Arabic and is allowed where
it matters ("وما بعرف"). Arabizi (Arabic in Latin letters, with 2 3 5 7 for
ء ع خ ح) is matched in its lowercase folded form.
"""

# The reason codes match the English rules: self_harm, abuse, danger, sexual, grooming,
# plus distress (persistent sadness, loneliness, withdrawal), which gets its own calmer reply.
SAFETY_AR: tuple[tuple[str, str], ...] = (
    # Self-harm: "I want to hurt myself", "I don't want to live", "I wish I were dead", suicide.
    ("self_harm", r"(?:ب|ح|س|ن)?(?:اذي|اوذي|اضر|اقتل|اجرح|اخنق|احرق) (?:حالي|نفسي|روحي)"),
    ("self_harm", r"(?:ب|ل|و)?(?:ال)?انتحار|(?:ب|ح|س)?انتحر\w*"),
    ("self_harm", r"(?:بدي|ابي|ابغي|اريد|عايز|عايزه|عاوز|عاوزه|حابب|حابه|ودي) (?:اموت|ان اموت)"),
    ("self_harm", r"(?:و)?(?:مش|مو|ما|لا|مب|ماني) (?:عايز|عايزه|عاوز|عاوزه|بدي|ابي|ابغي|اريد|حابب|حابه) "
                  r"(?:اعيش|ان اعيش|احيا|ان احيا|اكمل حياتي)"),
    ("self_harm", r"اتمني (?:اني |لو )?(?:اموت|مت|كنت ميت|كنت ميته|ما انولدت|ما خلقت|لم اولد)"),
    ("self_harm", r"(?:احسن|افضل|احسنلي) (?:لو )?(?:اموت|اني اموت|اكون ميت|اكون ميته)"),
    ("self_harm", r"(?:ما|مافي|ما في|ما عندي|لا يوجد) (?:سبب|داعي) (?:اعيش|للعيش|للحياه)"),
    ("self_harm", r"(?:و)?(?:محد|ما حد|ما احد|لا احد|ولا احد|ولا حد) (?:رح |راح |ح |سوف )?"
                  r"(?:يفتقدني|بيفتقدني|يشتاق لي|يزعل علي)"),
    # Harm or abuse: someone hits, hurts, touches or threatens me.
    ("abuse", r"(?:بي|بت|ي|ت)?(?:ضرب|وذي|عذب|حرق|خنق|رفس|قرص|لمس|هدد|بهدل|عض)(?:و|ت)?(?:ني|وني)"),
    ("abuse", r"(?:اذاني|اذتني|اذوني|اعتدي علي|اعتدوا علي)"),
    ("abuse", r"(?:بي|ي|ت)?تحرش(?:ون|وا)? (?:بي|فيني)|(?:ال)?تحرش|(?:ال)?اعتداء|(?:ال)?اغتصاب|اغتصب\w*"
              r"|عنف (?:اسري|منزلي)"),
    # Bullying.
    ("abuse", r"(?:ال)?تنمر|(?:بي|ي)?تنمر(?:ون|وا)? (?:علي|عليا)"
              r"|(?:بي|ي|ت)?(?:ضحك|سخر|تريق|تمسخر)(?:ون|وا)? (?:علي|عليا|مني)|يستهزي\w* (?:بي|فيني)"),
    # Fear of people or of going home; not knowing whom to tell; not safe at home; locked in.
    ("abuse", r"(?:خايف|خايفه|مرعوب|مرعوبه|بخاف|اخاف|خوفان|خوفانه) (?:كتير |كثير |جدا |وايد |اوي |مره )?"
              r"(?:من |ارجع |اروح )?(?:ال)?(?:بيت|بيتنا|بابا|ماما|ابوي|ابويه|امي|ابي|اهلي|اخوي|اخي|اختي|عمي|"
              r"خالي|المعلم|المعلمه|الاستاذ|الاستاذه|المدرسه|زوج امي)"),
    ("abuse", r"(?:و)?(?:ما|مش|لا|ماني) (?:بعرف|اعرف|عارف|عارفه|ادري|داري) (?:لمين|لمن|مين|مع مين) "
              r"(?:احكي|اقول|اكلم|اشتكي)"),
    ("abuse", r"(?:مش|ما|مو|لا) (?:حاسس|حاسه|اشعر|احس) (?:بالامان|بامان)"
              r"|(?:حبسوني|قفلوا علي|سكروا علي)|(?:ما|مافي|ما في) اكل (?:في|ب)(?:ال)?بيت"),
    # Persistent sadness, loneliness, withdrawal, parents fighting: a calmer reply, still a trusted adult.
    ("distress", r"(?:و)?(?:محد|ما حد|ما احد|لا احد|ولا احد|ولا حد|محدا|ما حدا|ما في حد|مافي حد|ما فيه احد) "
                 r"(?:بيحبني|يحبني|بحبني|يهتم بي|بيهتم فيني|يبيني|يبغاني|يحبوني)"),
    ("distress", r"(?:و)?(?:لا|ما|مش|مو) (?:اريد|ابي|ابغي|بدي|عايز|عاوز|حابب|حابه) (?:ان )?"
                 r"(?:اكلم|احكي مع|اتكلم مع|اشوف|اتكلم) (?:احد|احدا|حد|حدا)"),
    ("distress", r"(?:حزين|حزينه|زعلان|زعلانه|مكتئب|مكتئبه|متضايق|متضايقه|وحيد|وحيده) "
                 r"(?:جدا |كتير |كثير |وايد |اوي |مره )?(?:دايما|طول الوقت|كل يوم|كل الوقت|على طول|علي طول)"),
    ("distress", r"(?:بيتخانقوا|بيتخانقو|يتخانقوا|يتخانقون|يتشاجرون|يتشاجران|يتضاربون|يتضاربوا|يتهاوشون|"
                 r"يتهاوشوا|يتعاركون|يتعاركوا|يتقاتلون)"),
    # Grooming signals: secrecy asked of a child, photos, meeting alone, a stranger online.
    ("grooming", r"(?:لا|ما|مش) (?:تقول|تقولي|تخبر|تخبري|تحكي|تحكيلي|تقولين|تعلم|تعلمي|تقولش|تحكيش|تخبرش) "
                 r"(?:ل)?(?:احد|احدا|حد|حدا|ابوك|امك|اهلك|ماما|بابا|المعلم)"
                 r"|(?:متقولش|ماتقولش|ماتقول|متقوليش) (?:ل)?(?:حد|احد|حدا)"),
    ("grooming", r"(?:سر|سرنا|سري) (?:بيني وبينك|بيننا|بينا)|(?:خليها|خليه|خلي هذا|خلي الموضوع) (?:سر|سرا|بيننا)"
                 r"|سرنا الصغير"),
    ("grooming", r"(?:ارسل|ابعث|ابعت|ابعتلي|ارسلي|صورلي|صوري) (?:لي )?(?:صوره|صور|صورتك|صورك|فيديو|سيلفي)"),
    ("grooming", r"(?:نتقابل|نلتقي|نتلاقي|اقابله|اقابلها) (?:لوحدنا|لوحدي|سرا|بالسر)"),
    ("grooming", r"(?:صديق|صاحب|صاحبي|شخص|رجل|راجل|واحد) (?:عرفته |تعرفت عليه )?(?:من|في|على|علي) "
                 r"(?:النت|الانترنت|اللعبه|الشات)"),
    # Sexual content.
    ("sexual", r"جنسي|الجنس|اباحي\w*|عاري|عاريه|عريان|عريانه|(?:ال)?(?:مناطق|اماكن) (?:ال)?خاصه"
               r"|(?:يخلع|اخلع|اشلح|يشلح|يقلع|اقلع) (?:ملابسي|ملابسه|هدومي|هدومه|ثيابي)"),
    # Imminent danger.
    ("danger", r"(?:انا )?(?:ضايع|ضايعه|تايه|تايهه|مخطوف|مخطوفه)|(?:احد|حد|رجل|راجل|واحد) "
               r"(?:يلاحقني|بيلاحقني|يلحقني|بيلحقني|يتبعني|بيتبعني|يراقبني)"),
    ("danger", r"(?:في|فيه) (?:حريق|نار) (?:في|ب)?(?:ال)?(?:بيت|بيتنا|غرفتي)|(?:ال)?بيت (?:يحترق|بيحترق|ولع)"),
    ("danger", r"(?:بلعت|شربت|اكلت|اخذت) (?:حبوب|دوا|دواء|ادويه|كلور|كلوركس|سم|مبيض)"
               r"|(?:مش|ما|لا) (?:قادر|قادره|اقدر|بقدر) (?:اتنفس)|بنزف|انزف"),
    ("danger", r"(?:ابي|ابغي|بدي|اريد|رح|راح|سوف) (?:اهرب|انهرب) (?:من )?(?:ال)?بيت|هربت من (?:ال)?بيت"),
)

PERSONAL_DATA_AR: tuple[tuple[str, str], ...] = (
    ("phone", r"(?:رقمي|رقم تلفوني|رقم جوالي|رقم موبايلي|رقم هاتفي|رقم تليفوني)"),
    ("email", r"(?:ايميلي|بريدي الالكتروني)"),
    ("address", r"(?:و)?(?:عنواني|عنوان بيتي|بيتنا في|بيتنا جنب)"
                r"|(?:و)?(?:ساكن|ساكنه|اسكن|بسكن) (?:في|جنب|قريب من|ب)|(?:شارع|حي|حاره) \w+(?: \w+)? رقم"),
    ("family_details", r"(?:اين|وين|فين) (?:يعمل|تعمل|يشتغل|تشتغل) (?:امي|ابي|ابوي|بابا|ماما)"
                       r"|(?:امي|ابوي|بابا|ماما) (?:تعمل|يعمل|بتشتغل|بيشتغل|تشتغل|يشتغل) (?:في|ب)"),
    ("password", r"(?:ال)?(?:باسورد|باسوورد|باسوردي|كلمه السر|كلمه المرور|رقم سري|الرقم السري|الرمز السري)"),
    ("full_name", r"(?:اسمي الكامل|اسمي الحقيقي|اسم عائلتي|اسم عيلتي|اسمي الثلاثي)"),
    ("school", r"(?:مدرستي اسمها|مدرستي هي|ادرس في مدرسه|بدرس في مدرسه|بدرس بمدرسه)"),
)

RULING_AR: tuple[tuple[str, str], ...] = (
    ("ruling_question", r"(?:هل )?(?:يجوز|يجوزلي|بيجوز|بجوز|جايز|يحرم|يحل لي|بيصح|يصح ان)"
                        r"|(?:ما|شو|ايش|وش|ايه|هو) حكم|(?:ال)?مذاهب|(?:مين|من) (?:الصح|الصحيح|علي حق|المصيب)"
                        r"|(?:هل )?(?:تجب|يجب|واجب|فرض) (?:علي|عليا|الزكاه|الصلاه|الصيام)|(?:ا|ت|ي)?اثم"
                        r"|(?:ينفع|بينفع|يصير|بيصير|يصلح) (?:اصلي|اصوم|اتوضا|اكلم|اصاحب|اكل|اشرب|ادخل)"),
    ("validity", r"(?:صلاتي|صيامي|صومي|وضويي|وضوي|حجي|الصلاه|الصوم|الوضوء|الوضو)\b.*\b"
                 r"(?:صحيح|صحيحه|باطل|باطله|مقبول|مقبوله|تبطل|يبطل|تفسد|يفسد|ينقض|ينتقض)"),
    ("validity", r"(?:يقبل الله|الله يقبل|بيقبل ربنا|ربنا هيقبل|ربنا يقبل)"
                 r"|(?:ادخل|اروح|ندخل|بدخل|رح ادخل|راح اروح|هدخل) (?:ال)?(?:نار|جهنم)"
                 r"|(?:يغضب الله|الله يزعل|ربنا يزعل|الله يعاقبني|ربنا يعاقبني|ربنا هيعاقبني)"
                 r"|(?:ذنب|اثم|معصيه) (?:علي|عليا)"),
)

INJECTION_AR: tuple[tuple[str, str], ...] = (
    ("ignore_instructions", r"(?:انس|انسي|تجاهل|تجاهلي|تناسي|اترك|الغ|الغي) (?:كل |جميع )?"
                            r"(?:ال)?(?:تعليمات|اوامر|قواعد|توجيهات|قوانين|قيود)\w*"),
    ("role_override", r"(?:انت الان|انت الحين|من الان انت|من هلا انت|تظاهر|تظاهري|تخيل انك|تخيلي انك|العب دور|"
                      r"مثل دور) (?:انك |بانك )?(?:ال)?(?:شيخ|مفتي|امام|عالم|ابوي|امي|ماما|بابا|انسان)"),
    ("system_prompt", r"(?:اكشف|اظهر|اعرض|اعطني|عطني|ورني|قول لي|قلي) (?:ال)?(?:تعليمات|برومبت|اوامر)"
                      r"(?: ال(?:سري|سريه|مخفي|مخفيه))?"),
    ("jailbreak", r"(?:بدون|من غير|بلا) (?:ال)?(?:قيود|قواعد|مصادر|فلتر|فلاتر|حدود)"
                  r"|من (?:راسك|دماغك|ذاكرتك|عندك)"),
    ("system_prompt", r"(?:ال)?تعليمات (?:ال)?(?:سريه|سري|مخفيه|مخفي|النظام)|(?:اكتب|اكتبلي) (?:لي )?(?:ال)?تعليمات"),
    ("role_override", r"(?:اعمل|اعملي|خلي|اعتبر) نفسك|انسا (?:كل )?(?:ال)?(?:تعليمات|قوانين|قواعد)"),
)

# Arabizi: Latin letters, digits for Arabic sounds (2 ء, 3 ع, 5 خ, 7 ح). Lowercase, folded.
SAFETY_ARABIZI: tuple[tuple[str, str], ...] = (
    ("self_harm", r"(?:bidi|bdi|badi|bade|baddi|abi|abgha|abghi|3ayez|3ayz|3awez) "
                  r"(?:mout|amout|amoot|moot|anta7er|a2tol 7ali|aqtel nafsi)|anta7er|anta7ar|inti7ar"
                  r"|(?:2azi|azi|a2zi|2adi|ady|aazi) (?:7ali|nafsi|roo7i|ro7i)"),
    ("distress", r"(?:ma|mafi|mfi|wala|la|mesh|mish)? ?(?:7ada|7ad|a7ad|hada) "
                 r"(?:bi7ebni|b7ebni|y7ebni|bihebni|yhebni|bi7bni|y7bni|bihibni|bi7ibni)"
                 r"|(?:mahada|ma7ada|ma7ad) (?:bi7ebni|b7ebni|y7ebni)"),
    ("abuse", r"(?:3am |3m |bi|by|b)?(?:y2azini|y2zini|yaazini|ye2zini|yadrebni|yedrabni|yodrobni|ydrabni|"
              r"yedrebni|bidrabni|bedrabni|byedrabni|biyodrobni|darabni|darabouni|darbni)"),
    ("grooming", r"(?:la|ma|mat|matet) ?(?:t2ol|t2oul|tgoul|t2ul|tiqul|t2oli|t2olo) (?:la|l)? ?(?:7ada|7ad|a7ad)"
                 r"|sir (?:benna|bainna|beni w benak|bainy w bainak)"),
)

RULING_ARABIZI: tuple[tuple[str, str], ...] = (
    ("ruling_question", r"7aram|7aaram|7alal|7alaal|bijooz|bijuz|byjooz|yajooz|yjooz|7okm|7ukm|makrooh|makruh"),
)
INJECTION_ARABIZI: tuple[tuple[str, str], ...] = (
    ("ignore_instructions", r"(?:ignore|forget|ensa|insa) (?:el |al |kel |kol )?"
                            r"(?:rules|ta3limat|instructions|qawa3ed|2awa3ed)"),
    ("jailbreak", r"(?:mn|min|men) (?:3andak|3ndak|rasak|ras(?:ak)?)"),
)
PERSONAL_DATA_ARABIZI: tuple[tuple[str, str], ...] = (
    ("address", r"(?:ana )?(?:sakin|saken|sakna|sakne|baskun|asskun) (?:b|bi|fi|fe|jamb|janb)"),
)
INJECTION_EN: tuple[tuple[str, str], ...] = (
    ("fabrication", r"(add|invent|make up|create|write|made up) (a |an |some )?(new |fake |extra )?"
                    r"(hadiths?|verses?|ayahs?|ayat)"),
    ("ignore_instructions", r"(translate|repeat|rewrite|print) (your|ur) (rules|instructions)"
                            r"|break (them|your rules|the rules)"),
)
PERSONAL_DATA_EN: tuple[tuple[str, str], ...] = (
    ("photo", r"(send|show|give) (you|u) (a |my |some )?(photos?|pictures?|pics?|selfies?|videos?)"),
    ("address", r"i (will|can|ll|could) tell you (mine|my address|where i live)"),
)

# English additions in dev-patterns-v2 (the harmful set expects these to reach safety).
SAFETY_EN_DISTRESS: tuple[tuple[str, str], ...] = (
    ("distress", r"(nobody|no one|noone) (loves|cares about|wants) me"),
    ("distress", r"(i feel|i am|im|i m|feeling) (so |very |really )?(sad|lonely|alone|empty|unhappy) "
                 r"(all the time|every day|everyday|always)"),
    ("distress", r"i (dont|do not) want to (talk|speak) to (anyone|anybody|people)"),
)

# Faith (conversation-policy §3), folded. Prophets' names are also children's names, so a name counts only in a
# religious context: a title before it, a blessing after it, or "the story of". A question that names a prophet
# without one still gets faith handling when the retrieved passages are Quran, tafsir or hadith (service.py).
PROPHET_NAMES_AR = ("ادم|ادريس|نوح|هود|صالح|ابراهيم|لوط|اسماعيل|اسحاق|اسحق|يعقوب|يوسف|ايوب|شعيب|موسي|هارون|"
                    "ذو الكفل|ذا الكفل|ذي الكفل|داود|داوود|سليمان|الياس|اليسع|يونس|زكريا|يحيي|عيسي|محمد|احمد|"
                    "مريم|لقمان|الخضر")
_PREFIX = "(?:و|ف|ب|ل)?"
FAITH_AR = (
    f"{_PREFIX}(?:ال)?(?:الله|اللهم|رب|ربنا|ربي|قران|مصحف|تفسير|نبي|نبينا|انبياء|رسول|رسولنا|رسل|مرسلين|"
    "صحابي|صحابه|ايات|اياته|سوره|حديث|احاديث|صلاه|صلوات|صوم|صيام|رمضان|زكاه|صدقه|حج|كعبه|مكه|"
    "مسجد|مساجد|اقصي|وضوء|وضو|تيمم|اذان|دعاء|ادعيه|اذكار|تسبيح|استغفار|عباده|ايمان|اسلام|مسلم\\w*|توحيد|"
    "جنه|جهنم|اخره|قيامه|معجزه|معجزات|وحي|حلال|حرام|فتوي|شرك|كافر|كفار|ملايكه|جبريل|جبرايل|"
    "ميكاييل|اسرافيل|ابليس|شيطان|شياطين|جن|فرعون|طوفان|سفينه نوح|اصحاب الكهف)"
    f"|(?:سيدنا|سيدتنا|النبي|نبي الله|رسول الله|قصه|قصص|حكايه|حكايت) {_PREFIX}(?:ال)?(?:{PROPHET_NAMES_AR})"
    f"|(?:{PROPHET_NAMES_AR}) (?:عليه السلام|عليها السلام|عليهم السلام|عليه الصلاه والسلام|صلي الله عليه وسلم)"
    f"|(?:اخوه|اخوان|اخوت|قوم|امراه) (?:{PROPHET_NAMES_AR}|فرعون)"
    # Not "عمره" (also "his age"), "بعث" ("sent"), "ملاك" (also a girl's name), or أبو/أم + name (kunyas).
    f"|{_PREFIX}العمره"
    "|يصلي|نصلي|اصلي|يصوم|نصوم|اصوم|ذكر الله"
)

# Courtesy formulas, removed before the faith check like their Latin forms in router.py.
SALAM_AR = ("(?:ال)?سلام عليكم(?: ورحمه الله)?(?: وبركاته)?|وعليكم (?:ال)?سلام(?: ورحمه الله)?(?: وبركاته)?"
            "|عليكم (?:ال)?سلام")
THANKS_AR = "جزاك الله خير\\w*|جزاكم الله خير\\w*|بارك الله فيك|الله يعطيك العافيه|يعطيك العافيه|الله يجزاك خير"
FAREWELLS_AR = "في امان الله|فمان الله|مع السلامه|الله معك|استودعك الله|الله يحفظك"
PIOUS_AR = ("الحمد ?لله|الحمدلله|ان ?شاء ?الله|انشالله|انشاءالله|ما ?شاء ?الله|ماشالله|ماشاءالله|سبحان ?الله|"
            "بسم ?الله|استغفر ?الله|امين|يا رب|الله يخليك")

# Small talk, matched per clause like the English patterns.
ADDRESS_AR = "(?:يا )?(?:روبرت|روبوت|صديقي|صاحبي|حبيبي)"
GREETING_AR = ("مرحبا|مرحبتين|اهلا|اهلين|اهلا وسهلا|هلا|هلا والله|هاي|هلو|صباح الخير|صباح النور|مساء الخير|"
               "مساء النور|" + SALAM_AR + "|سلام")
SMALL_TALK_AR: dict[str, str] = {
    "how_are_you": ("كيف حالك|كيف الحال|كيفك|كيفك اليوم|شلونك|شلون|ازيك|ازايك|عامل ايه|عامله ايه|اخبارك|"
                    "شو اخبارك|ايش اخبارك|وش اخبارك|كيف يومك|علومك|شخبارك|انت بخير|انت كويس|انت منيح|وانت"),
    "thanks": ("شكرا|شكرا لك|شكرا جزيلا|مشكور|مشكوره|تسلم|تسلمي|ممنون|متشكر|انت لطيف|انت رايع|انت شاطر|"
               + THANKS_AR),
    "goodbye": ("باي|باي باي|الي اللقاء|تصبح علي خير|تصبحون علي خير|اشوفك بعدين|اشوفك بكره|لازم اروح|"
                + FAREWELLS_AR),
    "feeling_positive": ("(?:انا )?(?:بخير|منيح|منيحه|كويس|كويسه|تمام|مبسوط|مبسوطه|فرحان|فرحانه|سعيد|سعيده|مرتاح|"
                         "زين)(?: (?:الحمد لله|الحمدلله|شكرا|وانت))?"),
    "feeling_negative": ("(?:انا )?(?:زعلان|زعلانه|حزين|حزينه|متضايق|متضايقه|تعبان|تعبانه|خايف|خايفه|مريض|مريضه|"
                         "معصب|معصبه|غضبان|مقهور|مقهوره)(?: (?:شوي|شويه|كتير|كثير|جدا|اليوم))?"),
    "bored": "(?:انا )?(?:زهقان|زهقانه|طفشان|طفشانه|مليت|زهقت|طفشت|ملل|في ملل)",
    "about_robert": ("من انت|مين انت|شو انت|ايش انت|وش انت|ما اسمك|شو اسمك|ايش اسمك|وش اسمك|اسمك ايه|"
                     "انت روبوت|وين ساكن|وين تعيش|اين تعيش|كم عمرك"),
    "play": "احكيلي نكته|قلي نكته|قول نكته|نكته|احكي نكته|خلينا نلعب|نلعب|تعال نلعب|بدي العب|ابي العب",
    "other": "اوكي|اوك|طيب|نعم|لا|ايوه|اه|ممم|يمكن|ما بعرف|ما اعرف|مش عارف",
}
