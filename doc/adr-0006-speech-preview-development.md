# ADR 0006: A speech preview on the team's speech service, development only

Status: proposed. Date: 2026-10-06. Decisions by the product owner on 2026-10-06 (below).
Supersedes in part [ADR 0002](development-boundary.md), for a speech preview only. The release gate's `voice`
switch is unchanged and stays off.

## Context

The release gate ([`governance/release-gate.md`](governance/release-gate.md)) keeps push-to-talk (`voice`) off for
children until its items are green: a voice DPIA (G04), a retention policy (G08), guardian consent (G06), provider
due diligence (G07) and the voice privacy tests (A09), among others. None of the human items is decided.

The team has built a speech service, Dua-a_stt, that runs on our own machine: Whisper large-v3 Arabic
(`Abu-Dju/whisper-large-v3-ar`, CTranslate2 INT8, Apache 2.0) for pronunciation practice, and F5-TTS
(`IbrahimSalah/Arabic-F5-TTS-v2`, non-commercial licence) for Robert's voice. Its v1 is for adults with consent
only (its ADR 0002), and its scoring is practice, never a verdict on worship (its ADR 0001). Those reviews need
something concrete: an integration that keeps audio in memory, never logs a transcript, and can be switched off
piece by piece. Building it now, for adult operators, lets the privacy tests (A09) and the reviewers see it working
without a child ever using it.

On the development machine (GTX 1650) only one model fits in video memory at a time, and F5-TTS takes 20 to 55
seconds for a three-second sentence. Pre-rendered audio is preferred wherever it can be.

## The product owner's decisions (2026-10-06)

- **D-A, text to speech.** It demonstrates only four short adhkar (takbeer, tasbeeh, tahmeed, istighfar), through
  a reviewed allowlist in the speech service (its ADR 0007), for development and demo profiles only. Longer duas
  and Quranic duas get a slot for a recorded human voice, empty until recordings exist. Quran, hadith and duas are
  never generated otherwise.
- **D-B, voice questions.** A development-only `/v1/transcribe` in the speech service (its ADR 0006), behind its
  own kill switch. The transcript goes only to this backend, is never logged or stored, is shown to the child to
  check before sending, and then enters the normal chat safety pipeline as typed text. Push-to-talk only.
- **D-C, Robert's voice.** An on-demand "Listen" under Robert's answers. The model adds tashkeel to Robert's own
  sentences (quotations skipped), the backend verifies that no letter changed, the speech service renders them as
  `persona` copy, and the app plays the parts as they become ready.
- Recitation is pronunciation **practice**: outcomes are `clear`, `try_again` and `unsure`, never right or wrong.
  Stars reward practice effort, not correctness or religious merit.
- Everything is a **development preview for adult operators**. `features.voice` stays false. No child use until
  the voice DPIA (G04), a retention owner and the release gate's voice items are green.

## Decision

1. **A separate preview, never the voice switch.** `/v1/bootstrap` reports
   `features.speech = {preview, recitation, voiceQuestions, robertVoice, maxRecordingSeconds: 15}`. The schema keeps
   `features.voice` as `Literal[False]`, and `preview` may be true only when the bootstrap mode is `development`
   (`tests/test_release_gate.py`). With `COMPANION_SPEECH_ENABLED` unset every field is false and every speech route
   answers 404 `speech_disabled`.
2. **Kill switches.** `COMPANION_SPEECH_ENABLED` is the master switch for the whole preview. Each feature has its
   own (`COMPANION_SPEECH_RECITATION`, `COMPANION_SPEECH_VOICE_QUESTIONS`, `COMPANION_SPEECH_ROBERT_VOICE`), on while
   the master is on unless set to `false`. Robert's voice also needs the answer model (grounded answers on), which
   adds the tashkeel; without it Robert's voice is off. When the preview is on, the server fails closed at startup,
   naming every problem: demo mode off, a missing or public speech address, a missing token, a switch that is
   neither `true` nor `false`, a malformed voice id or an out-of-range timeout.
3. **Provider.** Only the team's Dua-a_stt service, on `localhost` or a private IP address
   (`require_private_endpoint`, the same rule as the model endpoints), with its token in `X-Speech-Token`. Its
   models are its own decision: any change there needs its own ADR and evaluation.
4. **What reaches the speech service, and what comes back.**

   | Feature | Sent | Returned |
   | --- | --- | --- |
   | Practice and the dhikr game | One recording (raw WAV, at most 1 MiB), the dua id, segment, version and attempt number | Per-word states, an abstain reason, a feedback copy id. No transcript. |
   | Voice questions | One recording and the language (`ar` or `en`) | A transcript of at most 1000 characters, or an abstention |
   | Robert's voice | Robert's own diacritized sentence, the voice id and `category: persona` | WAV audio, or a guard's refusal |
   | Learn content | Nothing about the child | The adhkar, duas and feedback-copy lists, capabilities, pre-rendered or recorded WAV files |

   Never a name, a profile, a conversation id or anything the child typed.
5. **Retention.**
   - A recording is read into memory, passed on and dropped with its request. It is never written to disk, logged
     or cached.
   - A transcript is returned once to the app and kept nowhere: the transcription route does not use the
     idempotency replay cache, and nothing logs it.
   - Practice and game writes need an `Idempotency-Key`. Their replay keeps a keyed fingerprint (an HMAC over the
     request and a SHA-256 of the recording, as for text turns) and the result (outcome, word states, feedback copy,
     round counts). It never keeps the audio or a transcript.
   - Robert's rendered audio lives in the API process's memory for at most 15 minutes and 16 turns, and is dropped
     at once when its conversation is deleted.
   - Logs carry no audio, transcript or sentence. `tests/test_voice_privacy.py` holds all of this (release gate
     item A09).
6. **Practice, never a verdict.** An abstention is `unsure`; a scored attempt is `clear` when every word is clear,
   else `try_again`. Word states are shown only on the first three attempts and never with an abstention. A feedback
   line from the speech service is shown only when it has none of the banned words (غلط، خطأ، فشلت، ما قُبل، باطل،
   لا يصح، ما بتنحسب، مرفوض، wrong, failed, invalid, rejected, incorrect, mistake) and breaks no must-never rule
   (`worship_verdict` among them); otherwise the backend's own gentle line for the outcome is used.
7. **Stars for practice.** A dhikr-game round completes on a `clear` attempt or after three counted attempts. An
   attempt counts when it is scored, or when the service was unsure of a child who spoke (`low_confidence`); an
   off-script, poor-audio, too-long or unavailable attempt does not. A completed round appends one learning star to
   the existing append-only ledger, once per round, and at most 10 per UTC day. Past the cap a round still
   completes; nothing is taken away, and the app calls it a lovely practice. Stars are spent on looks through the
   existing `/v1/cosmetics/claim`.
8. **Robert's voice.** Only answer types that are Robert's own words are spoken (`chat`, `grounded`,
   `reviewed_answer`, `abstained`, `redirected`), never `safety` or `unavailable`. A sentence holding a quotation
   is dropped whole, as are citation markers, references, sources lists and sentences with Latin letters. The rest
   becomes at most six parts of at most 140 characters. The answer model adds tashkeel (prompt `diacritize-v1`,
   temperature 0), and a part is kept only when removing harakat, tanween, shadda, sukun, the dagger alef and
   tatweel gives back its exact letters. A part the speech service's guards refuse is dropped. One render runs at
   a time.

## What still gates any child use

Nothing in this ADR approves speech for children. Before any child use, including a pilot:

- **G04**, the DPIA for child voice capture, decided and applied, with every other voice item of the release gate
  green (G01, G02, G05 to G08, G11, G12, A01, A06, A08). A09 now has its test, which shows software behaviour, not
  a review.
- A named **retention owner** and an approved retention and deletion policy (G08) covering recordings, transcripts
  and rendered audio.
- The speech service's **ADR 0006** (transcription) and **ADR 0007** (the adhkar allowlist) signed off by the
  scholarly committee, and its own v1 boundary (adults with consent) lifted by its own review, with STT evaluated
  on children's voices.
- A decision on the **F5-TTS non-commercial licence** for any use beyond research and demonstration.
- Review of the new copy: the adhkar names and transliterations, the fallback feedback lines and the
  `diacritize-v1` prompt.
- Guardian consent for the microphone (G06): the app's parent switch is an operator convenience, not consent.

## Consequences

- The API gains the routes in [`README.md`](../README.md) and `contracts/openapi-v1.json`. The app must handle
  404 `speech_disabled`, 415 `unsupported_media_type`, 503 `speech_unavailable` and 503 `speech_busy` (a full
  speech queue, retried twice by the backend first).
- Learn content degrades rather than fails: without the speech service the adhkar and duas are still listed, with no
  audio, no practice and no segments.
- Practice segments are offered only where the backend's split of `content.json` (the speech service's export
  rule) gives the speech service's own word counts. `after-prayer-tasbih` has none today, because the service
  spells "33" as two words.
- Rendering competes for the one GPU: while Robert's voice renders, a practice attempt waits behind it and may time
  out (`COMPANION_SPEECH_TIMEOUT_SECONDS`, default 30; renders have `COMPANION_SPEECH_TTS_TIMEOUT_SECONDS`, default
  240).
- The bounded memory store stays the system of record for this preview; rounds, replays and rendered audio
  disappear on restart, as everything else in it does (ADR 0002).
