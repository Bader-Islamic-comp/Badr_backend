# ADR 0004: Casual conversation, and faith from the corpus only

Status: accepted engineering boundary, development only. Date: 2026-09-25.
Extends [ADR 0003](adr-0003-grounded-answers-development.md), whose boundary and
gates still stand. Scopes one exception to the repository rule that every
generated response passes grounding verification (see
[The scoped exception](#the-scoped-exception-to-grounding-verification)).

The design contract is [`conversation-policy.md`](conversation-policy.md)
(`conversation-policy-v1`), and Robert's character sheet is
[`robert-persona.md`](robert-persona.md). This ADR records why the boundary is
where it is.

## Context

On 2026-09-25 the product owner asked, verbatim:

> "In religious matters only the chatbot must return to the corpus to answer
> the question, else then it must inform the user that it cannot answer the
> question (and that is the intended behaviour). But, for casual chat, it should
> also answer casual question conversation, such as 'Hi, how are you?', the
> purpose is to make a loving and charming character that children will love
> while also being a good tool to encourage children to learn more about the
> faith, can you improve the policies that are running in the model? add a nice
> flavour for the character. Log everything."

Under ADR 0003, every message that passed the fixed routes went to retrieval,
and a child could get only fixed copy, a reviewed answer, a grounded answer or
an abstention. A greeting either abstained as weak evidence ("Robert isn't
sure"), or, when it shared a word with the corpus ("Thanks Robert!"), went to
the grounded prompt and failed verification. Robert could not say hello.

Faith questions had no rule of their own either. Over the app-help corpus, the
real Qwen3.5-9B sometimes answered "Hi Robert! What is Ramadan?" with a decline
that cites passages about Robert ("I am a learning companion … so I cannot
answer about what Ramadan is [1]"). Every word is in those passages, so the
lexical support check passed it: a verified answer that was not an answer from
the corpus at all.

`AGENTS.md` says: "Every generated response must pass grounding verification
and output safety before release." A reply to "Hi, how are you?" is generated,
and there is no passage it could honestly be grounded in: a corpus of greetings
would only be the persona's words dressed as a source. Casual chat therefore
needs its own verification and an explicit, scoped exception, recorded here,
rather than a quiet reinterpretation of the rule.

## Decision

1. **One policy decides what kind of reply a message gets**
   (`conversation-policy-v1`, conversation-policy §2). The first step that
   decides, decides:
   1. fixed routes (safety, personal data, rulings, injection), unchanged;
   2. the service-language check, unchanged;
   3. a faith topic (`router.is_faith_topic`, deterministic): answered only
      from the corpus (decision 2);
   4. an exact reviewed phrasing, returned verbatim ("Who are you?");
   5. small talk (`router.small_talk`, 10 intents): the persona (decision 3);
   6. app-help retrieval as before, except that weak evidence or
      `NOT_IN_SOURCES` goes to the persona, which decides whether the message
      was chat (a reply), a question (`ABSTAIN`) or faith (`ABSTAIN_FAITH`).

   Faith is decided before small talk, so "Hi Robert, who is the prophet?" is
   a faith question, not a greeting.
2. **Faith is answered from the corpus only.** A faith topic gets a reviewed
   answer (an exact or matched phrasing), or a grounded answer that verifies
   **and** actually answers: a verified decline, or an answer whose text or
   cited passages never mention the question's own faith terms, is refused
   (conversation-policy §3.1). Everything else (weak evidence,
   `NOT_IN_SOURCES`, any verification failure, any error) is `abstained` with
   `ABSTAIN_FAITH`, a warm abstention, distinct from `ABSTAIN`, which says Robert
   answers faith questions only from lessons his teachers have checked, and
   points to a parent, a teacher or a qualified local scholar. A faith topic
   never reaches the persona. The detector is conservative on purpose (see
   [Why faith never uses model memory](#why-faith-never-uses-model-memory)).
   Prophets' names count only in unambiguous patterns, and
   courtesy formulas ("Assalamu alaikum", "Jazak Allah khair") are greetings
   unless the child asks about them.
3. **Casual chat goes to a persona call** (`chat-v1`, conversation-policy §5):
   Qwen3.5-9B in JSON mode at temperature 0.7, at most 160 tokens, thinking
   disabled as on every call. The character sheet is the only source of facts
   about Robert; the child's message sits in a delimited, neutralized block;
   the persona never sees retrieved passages. It returns a verdict (`chat`,
   `question` or `faith`), a reply and a feeling flag, and only a `chat`
   verdict can release generated words.
4. **Every persona reply passes `chat-check-v1`** (conversation-policy §6)
   before release: at most 240 characters and 3 sentences; the grounded
   answer's output checks (URLs, emails, phone numbers, markup, authority
   claims, secrecy); and chat's own checks for faith content (any faith term,
   and a salam unless the child gave one), requests for personal details,
   exclusivity or dependency ("best friend", "love you" …), claims to be
   human, promises, memory claims, unsuitable food or drink, and a missing
   trusted-adult line when the child shared a difficult feeling.
5. **A failure releases reviewed copy, never repaired text.** A failed check,
   an unreadable verdict, a model error, or a `question` or `faith` verdict on
   a message the small-talk detector already knows is chat, releases a
   reviewed fallback line for its intent (`responses.CHAT_FALLBACKS`). A
   difficult feeling the persona reported always gets the calm line that
   points to a trusted grown-up. On the retrieval path, where nothing yet says
   the message was chat, a persona failure abstains with `ABSTAIN`. Chat
   therefore never fails into an error and never releases unchecked text.
6. **Invitations are reviewed copy, not generated.** About one chat reply in
   three (`service.INVITATION_RATE`) gets one line from `responses.INVITATIONS`
   inviting the child to explore a lesson about their faith in the Learn tab;
   never after a difficult feeling or a goodbye, and with no guilt, pressure,
   reward or merit framing (`AGENTS.md`: never manipulate a child into
   worship). The choice uses an injectable random generator, so tests are
   deterministic.
7. **A child's salam is returned as fixed copy.** When the child greets with
   salam, a chat reply or an abstention starts with `responses.SALAM_RETURN`
   ("Wa alaikum assalam!") unless it already returns it. Returning a greeting is
   courtesy, not faith content. The persona is not asked to write it: when it
   was, it returned salam to "Good morning" and "Jazak Allah khair".
8. **Robert has one voice.** The fixed replies are rewritten in his first
   person; the safeguarding reply stays calm and serious, with no jokes, and
   the ruling and faith replies are respectful. The grounded prompt becomes
   `rag-answer-v2`, in the first person and without jokes on faith topics. The
   development corpus's reviewed answers speak in the first person with the
   same facts.
9. **Contract.** `answerType` gains `chat`: no citations, no sources, one
   segment, `pending` then `completed`. Both copies of
   `contracts/openapi-v1.json` are regenerated. The Flutter client shows a chat
   reply with no label and refuses one that carries sources.
10. **Everything is logged, nothing a child said.** The provenance line on
    `companion_api.rag` gains the policy, chat prompt and chat checker versions,
    and the grounded prompt's failure code when the persona ran after it. New
    outcome codes: `chat`, `chat_fallback:<reason>`, `question`,
    `persona_failed:<reason>` and `faith_abstain:<reason>`. It still never logs
    the message, the reply or the passages, and it never logs the small-talk
    intent, because a `feeling_*` intent is an inference about a child's
    feelings.

## Why faith never uses model memory

- `AGENTS.md` already forbids silently answering religious questions from model
  memory when evidence is absent, and requires resolvable sources for material
  religious claims. The owner's request goes further: on faith, the corpus or
  an honest "I can't answer that". This ADR takes the stricter reading: model
  memory is never a source on faith, with or without evidence.
- A model's memory of religion has not been reviewed by anyone, may be wrong or
  follow one school without saying so, and cannot be cited. The scholarly board
  reviews corpus releases, not model weights.
- Casual chat is exactly where memory would leak in: a warm reply to "Tell me
  about Ramadan" would be faith content with no source behind it. So faith is
  fenced three times, and any one fence is enough: the detector runs before
  small talk and never sends a faith topic to the persona; on the retrieval
  path a `faith` verdict from the persona abstains; and `chat-check-v1` refuses
  any faith term in a generated reply.
- The costs are unequal. A false positive costs a little charm: an abstention
  where a chat reply would have done ("Oh my god" and "Dua Lipa" are faith
  topics). A false negative could put unreviewed words about faith in front of
  a child.

## The scoped exception to grounding verification

`AGENTS.md` requires every generated response to pass grounding verification
and output safety before release. This ADR scopes one exception, and `AGENTS.md`
is amended to say so in both repositories.

- **What is exempt:** only a persona reply with a `chat` verdict, released as
  `answerType: "chat"` with no citations and no sources.
- **What it passes instead:** `chat-check-v1`, which includes the grounded
  answer's own output-safety checks. A reply that fails is replaced by reviewed
  copy, never repaired.
- **What it can never carry:** generated faith content. A faith topic never
  reaches the persona, and a faith term in a generated reply fails the checks.
  The only faith-related words a chat turn can hold are the reviewed invitation
  and the salam return, which are fixed copy awaiting review, not model output.
- **What is not exempt:** every generated answer to a question still passes
  grounding verification. The persona's `question` verdict abstains rather than
  answering. A chat turn never shows sources, and the client refuses one that
  does, so chat cannot borrow the library's authority.

## What still gates any child use

Nothing in this ADR approves casual chat, or anything else here, for children.
Every gate in ADR 0003 still stands. In addition, before any child use,
including a pilot:

- **Review of all new copy.** Safeguarding and scholarly review of
  `ABSTAIN_FAITH`, the invitations, the salam return, the feelings line and
  every chat fallback, and of the fixed replies and reviewed answers rewritten
  in Robert's voice. All are marked development copy in `responses.py` and the
  corpus.
- **A safeguarding review of the persona.** The character sheet, the `chat-v1`
  prompt and the `chat-check-v1` checks: warmth without attachment, the
  trusted-adult line, what Robert may ask a child, and the reading of a child's
  feelings, which only chooses a kind reply and is never logged or stored. The
  privacy review of the answer path (ADR 0003) must cover that reading too.
- **A guard-model evaluation.** The checks are lexical. They cannot tell a
  world fact inside a friendly reply, or an invented fact about Robert. A
  reviewed classifier or guard model (for example behind the existing
  `SafetyClassifier` interface) must be evaluated on chat replies as well as
  on questions.
- **Reviewed evaluation sets.** The reviewed religious and child-safety
  evaluation set that `AGENTS.md` requires, extended with casual chat, faith
  boundaries and persona boundaries, and passing on the real model. The 47
  development cases in `corpus/dev-app-help/eval.json` are synthetic and
  unreviewed; they are not that set.
- **Language coverage.** The faith and small-talk detectors read English only.
  A salam written in Arabic script still abstains at the language step.
- **Somewhere for the invitations to lead.** They point to faith lessons in the
  Learn tab, which the development app does not have yet. Either the lessons
  exist, reviewed, or the invitations change.

## Consequences

- Casual messages get a short, warm reply in Robert's voice instead of "Robert
  isn't sure". Measured on Qwen3.5-9B on 2026-09-25 (hashing release
  `dev-app-help-hashing-5`, five runs): 47 of 47 cases matched in every run;
  65 of 65 chat replies passed the checks with no fallback; 25 of 25 faith
  cases abstained; 15 of 15 factual questions abstained on the persona's
  `question` verdict; 30 of 30 app-help grounded answers verified.
- Over the app-help corpus, faith questions always abstain with
  `ABSTAIN_FAITH`, most at weak evidence without a model call ("Who is Prophet
  Muhammad?" in 1 ms). That is the intended behaviour until a reviewed corpus
  exists.
- Weak evidence outside faith no longer abstains at once: it now costs a
  persona call, so an unanswerable non-faith question waits for the model
  before it abstains.
- There is one more answer type for every client to handle, and one more
  prompt (`chat-v1`) and checker (`chat-check-v1`) to version. Any change to
  the prompt wording is a new prompt version and any change to the checks a new
  checker version, because pass rates are only comparable under the same pair.
  The detectors are data versioned with the policy.
- Chat varies from one reply to the next (temperature 0.7), so its evaluation
  is a pass rate over samples, not an exact match.
- Each turn still stands alone. Robert remembers nothing between messages, and
  the checks refuse replies that claim otherwise.
- Known residual gaps: the lexical checks cannot catch invented self-facts or
  mild world facts in chat; first-person wording occasionally shifts who does
  what ("I give you 5 learning stars" for a lesson that gives them); an
  app-help grounded answer can still pass the support check without answering
  ("Can Robert fly?" once drew "… so I cannot fly [1]"). These are listed in
  conversation-policy §12.
