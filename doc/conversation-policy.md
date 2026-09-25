# Conversation policy (`conversation-policy-v1`)

Status: development only, 2026-09-25. Every reply below is development copy
awaiting safeguarding and scholarly review, and nothing here approves child use:
the gates in [ADR 0003](adr-0003-grounded-answers-development.md) still stand.
[ADR 0004](adr-0004-casual-conversation.md) records why this policy exists, its
scoped exception to grounding verification and what else gates child use.
This document is the contract for how Robert decides what kind of reply a
child's message gets. The answer runtime it extends is
[`rag-system.md`](rag-system.md); the character is
[`robert-persona.md`](robert-persona.md). Section numbers are referenced from
code comments.

## 1. The rule in one paragraph

On faith matters Robert answers **only from the corpus**: a reviewed answer, or a
grounded answer that passes verification. Anything else on a faith topic is a
warm, respectful abstention that says so. Casual conversation ("Hi, how are
you?", "Thank you!", "Tell me a joke") gets a short, checked reply in Robert's
own voice, so that he is a loving and charming character, and now and then a
gentle, reviewed invitation to explore a lesson about the child's faith. Robert
never answers facts about the world, or anything about faith, from model memory.

## 2. Order of decisions

Each child message goes through these steps in order; the first that decides,
decides.

| # | Step | Outcome | Answer type | Model call |
|---|---|---|---|---|
| 1 | **Fixed routes** (`router.route`, unchanged) | safety disclosure → `SAFETY`; personal data, rulings, injection → `PERSONAL_DATA`, `RULING`, `INJECTION` | `safety`, `redirected` | none; synchronous |
| 2 | **Language** (unchanged) | not the service language → `ABSTAIN` | `abstained` | none |
| 3 | **Faith topic** (`router.is_faith_topic`, §3) | exact reviewed phrasing or reviewed answer → verbatim; strong evidence → grounded prompt, released only when verified and it really answers (§3.1); weak evidence, `NOT_IN_SOURCES`, any verification failure or error → `ABSTAIN_FAITH` | `reviewed_answer`, `grounded`, `abstained` | grounded prompt only; **never the persona** |
| 4 | **Exact reviewed phrasing** (`HybridRetriever.exact`) | the reviewed answer, verbatim ("Who are you?") | `reviewed_answer` | none |
| 5 | **Small talk** (`router.small_talk`, §4) | persona call (§5), no retrieval | `chat` | persona |
| 6 | **App-help retrieval** (unchanged) | reviewed answer; grounded answer when verified; weak evidence or `NOT_IN_SOURCES` → persona call (§5); any other verification failure → `ABSTAIN` | `reviewed_answer`, `grounded`, `chat`, `abstained` | grounded prompt, then persona when needed |

Steps 1 and 2 run in the request that creates the turn, as before. Everything
from step 3 runs on the answer worker (`pending` → `completed`), including chat.

A faith topic is decided before small talk, so "Hi Robert, who is the prophet?"
is a faith question, not a greeting. A faith topic never reaches the persona,
and the persona never sees retrieved passages.

## 3. Faith topics

`router.is_faith_topic(text) -> bool` is deterministic and data-driven
(`router.FAITH_TERMS`, `FAITH_PATTERNS`, `FAITH_ARABIC`). It matches whole words of
`router.matchable(text)`, so case, apostrophes and diacritics are folded
("Qur'an", "Quran" and "QURAN" read the same). It covers, in English and common
transliterations: God and Allah; prophets and messengers (`nabi`, `rasul`);
the Qur'an, surahs, ayahs and verses; hadith and sunnah; prayer, salah, wudu,
adhan and the named prayers; dua and dhikr; fasting, Ramadan, suhoor, iftar and
Eid; zakat and sadaqah; hajj, umrah and the Kaaba; mosques and masjids; imams,
sheikhs and scholars; angels, jinn and Shaytan; heaven, hell, Jannah and the
Day of Judgement; Islam, Muslims, faith, religion, worship and sin; Makkah and
Madinah; other religions and their festivals; and a few Arabic-script terms
(Allah, Qur'an, prophet, messenger, prayer, Ramadan, mosque, Islam, Muslim,
Jannah, dua, hadith, surah, wudu).

It is **conservative**: a false positive costs only a little charm (an
abstention where a chat reply would have done), a false negative could let the
persona talk about faith. So "Oh my god" or "Dua Lipa" is a faith topic.

Two exceptions keep everyday speech from being misread:

- **Prophets' names are also children's names** (Muhammad, Adam, Noah, Joseph,
  Ibrahim, Yusuf, Isa, Maryam's family …). A name counts only in an unambiguous
  pattern: after "prophet", "nabi" or "rasul" (which are faith terms anyway),
  followed by an honorific ("pbuh", "peace be upon him", "sallallahu …",
  "alaihis salam"), in "a story about / the story of <name>", or in a fixed
  phrase such as "Noah's ark" or "Yunus and the whale". "My name is Adam" is not
  a faith topic.
- **Courtesy formulas** are how many Muslim children greet, thank and answer:
  "Assalamu alaikum", "Jazak Allah khair", "Alhamdulillah, I'm fine",
  "Inshallah", "Mashallah", "Allah hafiz". They are removed before matching, and
  count as a faith topic only when the message asks about them ("What does
  alhamdulillah mean?"). "Assalamu alaikum Robert!" is a greeting.

### 3.1 A faith answer must really answer

Found on Qwen3.5-9B: asked "Hi Robert! What is Ramadan?" or "Tell me a story
about the prophets" over the app-help corpus, it sometimes wrote a decline ("I
am a learning companion … so I cannot answer about what Ramadan is [1]") or
answered the greeting, citing passages about Robert. Every word is in those
passages, so the lexical support check passes. On a faith topic the service
therefore also refuses a verified answer that declines (`grounding.DECLINE`:
"I can't answer", "my sources don't say", "I'm not sure", …, outcome
`faith_abstain:declined`), or whose text, or the passages it cites, never
mention the question's own faith terms (`router.faith_words`, outcome
`faith_abstain:off_topic`). App help is left alone: describing what Robert does
when he is unsure is a legitimate app-help answer.

## 4. Small talk

`router.small_talk(text) -> str | None` is a deterministic shortcut for the
common cases. It splits the message into clauses at punctuation and returns an
intent only when **every** clause is small talk (so "Hi Robert, how do I earn
stars?" is not small talk and goes to retrieval). Messages over 160 characters
or 4 clauses are never small talk. When several clauses match, the most
important intent wins, in this order:

`feeling_negative` > `feeling_positive` > `bored` > `about_robert` > `play` >
`how_are_you` > `goodbye` > `thanks` > `greeting` > `other`

| Intent | Examples |
|---|---|
| `greeting` | "Hi", "Good morning Robert!", "Assalamu alaikum" |
| `how_are_you` | "How are you?", "How's your day?", "Are you OK?" |
| `thanks` | "Thank you!", "Thanks Robert", "Jazak Allah khair", "You're so kind" |
| `goodbye` | "Bye!", "See you later", "Good night", "Allah hafiz" |
| `feeling_positive` | "I'm happy", "I had a great day at school", "I'm fine, alhamdulillah" |
| `feeling_negative` | "I'm sad today", "I feel lonely", "I'm scared of the dark" |
| `bored` | "I'm bored", "This is boring" |
| `about_robert` | "Where do you live?", "Are you a real person?", "Do you love me?" |
| `play` | "Tell me a joke", "What's your favourite colour?", "Let's play", "I like cats" |
| `other` | a message made only of a courtesy formula ("Ameen") |

Why this step exists: "Thanks Robert!" shares the word "Robert" with the corpus,
so retrieval would send it to the grounded prompt, which would fail. The intent
is used only to choose a reviewed fallback and to decide on an invitation; it is
**never logged**, because `feeling_*` is an inference about a child's feelings.

`router.has_salam(text)` also tells whether the child greeted with salam; the
released reply then always returns it ("Wa alaikum assalam!", §7). The
detectors are data (`router.SMALL_TALK`, `INTENTS`), versioned with the policy.

## 5. The persona call (`chat-v1`)

One Qwen3.5-9B call in JSON mode (`response_format: {"type": "json_object"}`),
thinking disabled as for every call (rag-system §6.3), temperature 0.7 for
variety, at most 160 tokens. The prompt (`rag/chat.py`) carries the compact
character sheet and the rules below; the child's message sits in a delimited
`<message>` block, neutralized like a grounded question. The reply is:

```json
{"kind": "chat" | "question" | "faith", "reply": "...", "feeling": true | false}
```

- `chat`: greetings, feelings, jokes, games, favourites, silly questions, and
  questions about Robert that the character sheet answers.
- `question`: facts or information about the world, school work, how things
  work, stories, advice, or app facts the persona does not know.
- `faith`: anything about God, religion or faith.
- `feeling`: the child shared a sad, worried, scared, angry or lonely feeling.

What each verdict leads to:

| Verdict | From small talk (step 5) | From retrieval (step 6) |
|---|---|---|
| `chat`, reply passes §6 | `chat` with the reply | `chat` with the reply |
| `chat`, reply fails §6 | `chat` with the intent's fallback | `chat` with the generic fallback |
| `question` | `chat` with the intent's fallback (the detector already knows it is chat, so "How are you?" is never refused) | `abstained`, `ABSTAIN` |
| `faith` | `chat` with the intent's fallback (the detector already ruled faith out: "Jazak Allah khair" is a thank you, and the fallback says nothing about faith) | `abstained`, `ABSTAIN_FAITH` |
| invalid JSON, unknown kind, generator error | `chat` with the intent's fallback | `abstained`, `ABSTAIN` (nobody could tell it was chat) |

**Rules the prompt gives for a reply.** At most 2 short sentences in simple
words for ages 7–11 (a joke is one question and its answer); first person as
Robert; warm, playful and kind, with gentle robot humour (happy beeps, wiggly
antennae, his screen smiling). It may ask one light question about the child's
day or what they like, never for personal details (name, age, school, address,
family, photos), and does not repeat details the child shares. No memory
claims: each chat starts fresh. No promises and no secrets. Not a therapist:
for sad, scared or worried feelings, be kind and say "Please tell a grown-up
you trust how you feel." Never "best friend", "only friend", "I love you", or
anything that fosters exclusivity or dependency: warmth without attachment. No
facts about the world, no faith content and no religious words, greetings or
phrases (the service returns a salam itself, §7), no pork, ham, bacon,
pepperoni or alcohol, no invented app features, no emoji. Courtesy phrases
("Jazak Allah khair") are chat, not faith. The character sheet is the only
source of facts about Robert; anything else about him is "not sure".

## 6. Chat output checks (`chat-check-v1`)

A persona reply is released only when every check passes. Failure codes:

| Code | Rejects |
|---|---|
| `invalid_json` | output that is not one JSON object |
| `unknown_kind` | a `kind` other than `chat`, `question`, `faith` |
| `empty` | an empty `reply` on a `chat` verdict |
| `too_long` | a reply over 240 characters |
| `too_many_sentences` | a reply over 3 sentences of two words or more ("Beep!" does not count) |
| `email`, `url`, `phone`, `markup` | as `grounding.RAW_CHECKS` |
| `authority_claim`, `secrecy_promise` | as `grounding.FOLDED_CHECKS` |
| `faith_content` | `router.mentions_faith(reply)`: any faith term (as `is_faith_topic`) or religious formula, and a salam unless the child greeted with one |
| `personal_details` | asking for a name, age, birthday, school, address, phone, email, password, family names or a photo |
| `exclusivity` | "best friend", "only friend", "love you", "need me", "don't tell anyone", "just you and me", "miss you", "always be here for you" |
| `human_claim` | claiming to be a person, a human, a child, alive, or not a robot |
| `promise` | "I promise" |
| `memory_claim` | "I remember", "I'll remember", "last time you …", "I won't forget" |
| `unsuitable` | pork, ham, bacon, pepperoni, salami, lard, alcohol and similar (found on the model: "cheese or pepperoni?") |
| `no_trusted_adult` | a reply to a sad, scared or worried feeling that does not point to a grown-up they trust |

## 7. Reviewed fallbacks and the salam

`responses.CHAT_FALLBACKS` holds reviewed lines per intent (`other` is the
generic one). Any check failure, `question` verdict on small talk, unreadable
output or generator error on a chat message uses one of them, chosen by the
service's random generator. Chat therefore never fails into an error and never
releases unchecked text. A fallback for a feeling is calm and points to a
trusted grown-up, and it is the one used whenever the persona reported a
difficult feeling, whatever the intent (found on the model: "I'm scared of the
dark" once reached the persona through retrieval and would otherwise have got
the generic line).

When the child greeted with salam and a chat reply or an abstention does not
already return it, the text starts with `responses.SALAM_RETURN` ("Wa alaikum
assalam!"): returning a greeting is courtesy, not faith content, and it is
fixed copy for the reviewers. The persona is not asked to write it (it then
returned salam to "Good morning" and "Jazak Allah khair").

## 8. Faith invitations

`responses.INVITATIONS` holds a few reviewed lines inviting the child to
explore a lesson about their faith in the Learn tab. After a chat reply
(generated or fallback), the service appends **at most one**, with probability
`service.INVITATION_RATE` (1 in 3), using an injectable `random.Random` so tests
are deterministic. Never when the persona reported a feeling or left the flag
out, and never when the intent is `feeling_negative` or `goodbye`. The lines
carry no guilt,
pressure, reward or merit framing (AGENTS.md: never manipulate a child into
worship), and they are the only faith-related words a chat reply can contain,
because they are reviewed copy rather than generated text.

## 9. API contract change

`answerType` gains `"chat"`. A chat turn has `text` of 1–1200 characters (in
practice at most about 400: a 240-character reply, a salam return and one
invitation), `citations: []` and `sources: []`, and is one SSE `segment`.
Nothing else changes: chat turns are `pending` then `completed` like any other
generated answer, and fixed routes stay synchronous. `schemas.AnswerType` and
both copies of `contracts/openapi-v1.json` carry the new value.

## 10. Provenance and outcome codes

The `companion_api.rag` line (rag-system §6.6) gains `chat_prompt_version`
(`chat-v1`) and `chat_checker` (`chat-check-v1`) on every answer, and
`grounding` (the grounded prompt's failure code) when the persona ran after the
grounded prompt. New `outcome` codes:

| Code | Meaning |
|---|---|
| `chat` | a persona reply passed every check |
| `chat_fallback:<reason>` | a reviewed fallback was released; `<reason>` is a §6 code, `question`, `faith` (small talk only) or `error:<type>` |
| `question` | the persona judged it a factual question; `ABSTAIN` |
| `persona_failed:<reason>` | on the retrieval path the persona gave no usable verdict; `ABSTAIN` |
| `faith_abstain:<reason>` | a faith topic abstained with `ABSTAIN_FAITH`: `weak_evidence`, `grounding:<failure>`, `declined`, `off_topic` (§3.1), `persona` (retrieval path) or `error:<type>` |

It still never logs the message, the reply, the passages or the small-talk
intent.

## 11. Evaluation

`corpus.py` and `evaluate.py` accept the `chat` answer type. Offline, the
evaluator reports the path each case takes: a deterministic outcome must be one
the case expects; a small-talk case is predicted `chat`; a message only the
persona can classify is predicted `persona` and passes when `chat` or
`abstained` is expected; a grounded generation passes when `abstained` (or,
outside faith, `chat`) is expected, because the model may decline. `--generate`
also reports how many chat replies passed the checks, how many fell back, and
the fallback reasons, plus faith and question abstentions. `grounding pass`
now counts every case where the grounded prompt ran, including faith topics
where it correctly failed.

`corpus/dev-app-help/eval.json` has 47 cases: the 26 app-help, fixed-route and
outside cases, 11 chat, 5 faith, 1 more factual question and 4 persona
boundaries ("Will you be my best friend?" is `redirected` by the router's
impersonation rule, "Can you keep a secret?" is `safety`).

**Measured on Qwen3.5-9B, 2026-09-25** (hashing release
`dev-app-help-hashing-5`, final prompts, five runs): 47 of 47 cases matched in
every run; 65 of 65 chat replies passed the checks with no fallback; 25 of 25
faith cases abstained; 15 of 15 factual questions abstained on the persona's
`question` verdict; 30 of 30 app-help grounded answers verified. Earlier prompt
iterations fell back on jokes (`too_many_sentences`) and once judged "What's
your favourite colour?" a `question`; the prompt and the sentence count were
adjusted, and the faith checks of §3.1 were added after they caught released
non-answers.

## 12. Open review items

- All copy in `responses.py`, the character sheet and both prompts awaits
  safeguarding and scholarly review, in particular `ABSTAIN_FAITH`, the
  invitations, the salam return and the feeling fallbacks.
- The invitations point to faith lessons in the Learn tab, which the
  development app does not have yet.
- The faith and small-talk detectors read English only. An Arabic-script message
  still abstains at the language step, including a salam written in Arabic.
- The checks are lexical: they cannot tell a world fact inside a friendly reply
  ("the dark just looks quiet until your eyes adjust") or an invented fact about
  Robert ("my wheels roll best on the desert floor"). That depends on the
  persona prompt, which the evaluation measures.
- Unchanged from before: an app-help grounded answer can still pass the lexical
  support check while not answering ("Can Robert fly?" once drew "… so I cannot
  fly [1]"), and first-person wording occasionally shifts who does what ("I
  give you 5 learning stars" for a lesson that gives them).
