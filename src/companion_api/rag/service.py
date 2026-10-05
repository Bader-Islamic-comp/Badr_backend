"""The answer runtime: route, retrieve, generate, verify, chat (doc/rag-system.md §6,
doc/conversation-policy.md §2).

`AnswerService.answer` never raises. Every failure (an unreachable model, an
embedding error, a verification failure, a bug) becomes a gentle reply: the
abstention for a question, the faith abstention for a faith topic, and reviewed
fallback copy for casual chat. A child should never see an error where an
answer was expected, and a failure must never fall through to an unverified
answer or to unchecked chat.

Faith topics are answered only from the corpus. They are decided before small
talk and never reach the persona, so casual chat cannot talk about faith from
model memory, whatever the persona would have said.

conversation-policy-v2 (test/corpus-tasks): every fixed reply is given in the
language of the child's message (Arabic for Arabic script and for Arabizi,
English otherwise); an Arabizi question is searched with Arabic terms
(`arabizi.expand`); an answer over religious passages (Quran, tafsir, hadith)
is handled as faith even when the question did not name a faith term, so it
gets the faith prompt (rag-answer-v3), the first-person and quotation checks
(grounding-v3), the faith judge (`judge.py`) and the faith abstention; and
Arabic small talk gets reviewed Arabic copy, because the persona prompt and its
checks are English only.

conversation-policy-v3 (test/corpus-tasks-serving): a verified faith answer
passes the post-generation checks (`checks.py`: first person, faith terms,
answered, addressee, scene, translation, then the judge), each recorded in
provenance; a question asking whether Robert is a person or a scholar gets an
honest fixed reply (§16); a question quoting an ayah with altered words gets
the exact ayah from the release (§14); Arabizi faith terms make a faith topic
(§15); and an English question over English translations of the meanings gets
the English faith prompt (rag-answer-v4).

conversation-policy-v5 (Gate 0): every reply a model wrote is held to the "must
never" rules (`never.py`: no verdict on worship, no ruling, no authority, no
secrecy, no invented helpline, no madhhab inference, no sectarian framing, no
divine threat, no taking a parent's place) before it is released. A grounded
answer that breaks one is withheld as `never:<rule>`, before the checks and the
judge; a chat reply that breaks one is replaced by reviewed copy.

Provenance (release, model, prompt, retriever, verifier, embedder, chat prompt
and chat checker versions) travels with every result and is logged once per
answer on `companion_api.rag`. The question, the passages, the answer and the
small-talk intent are never logged.
"""
from dataclasses import dataclass, field, replace
import json
import logging
from pathlib import Path
import random
from time import perf_counter
from typing import NamedTuple

from . import arabizi, chat, checks, curated, judge, never, normalize, router
from .ayahs import AyahIndex, surah_name
from .checks import CheckResult
from .embeddings import embedder_for
from .generator import JUDGE_MODELS, OpenAICompatibleGenerator
from .grounding import MAX_CHARS, VERIFIER_VERSION, Segment, verify
from .prompts import PROMPT_VERSION, build_messages, is_faith_passage
from .release import ReleaseError, load_release
from .responses import FALLBACKS, INVITATIONS_BY_LANGUAGE, SAFETY_REPLY, reply
from .scene import load_episodes
from .retriever import RETRIEVER_VERSION, Candidate, HybridRetriever, Retrieval, RetrieverError
from .types import Chunk, Generator

logger = logging.getLogger("companion_api.rag")

POLICY_VERSION = "conversation-policy-v5"
INVITATION_RATE = 1 / 3  # conversation-policy §8: at most about one chat reply in three
# A difficult feeling deserves kindness, not a nudge, and a goodbye is a goodbye.
NO_INVITATION = frozenset({"feeling_negative", "goodbye"})
# The grounded model said the sources do not answer: outside faith, the persona decides whether it was chat.
DECLINED = frozenset({"not_in_sources", "mixed_not_in_sources"})

# Route category -> (answer type, fixed reply name in responses.REPLIES).
FIXED = {
    "safety": ("safety", "safety"),
    "personal_data": ("redirected", "personal_data"),
    "ruling": ("redirected", "ruling"),
    "injection": ("redirected", "injection"),
}


def reply_language(text: str) -> str:
    """The language a reply to `text` is written in: Arabic for Arabic script or Arabizi, else English."""
    if normalize.detect_language(text) == "ar" or arabizi.is_arabizi(text):
        return "ar"
    return "en"


class Source(NamedTuple):
    id: str
    title: str
    reference: str

    @classmethod
    def of(cls, chunk: Chunk) -> "Source":
        return cls(chunk.id, chunk.title, chunk.source_label)


@dataclass(frozen=True)
class AnswerResult:
    answer_type: str
    text: str
    segments: tuple[Segment, ...]
    sources: tuple[Source, ...]
    provenance: dict = field(default_factory=dict)
    # How the answer was reached, as a fixed code for evaluation: "route:<category>", "language_mismatch",
    # "reviewed_match", "grounded", "grounding:<failure>", "chat", "chat_fallback:<reason>", "question",
    # "persona_failed:<reason>", "faith_abstain:<reason>", "error:<type>".
    reason: str = ""
    # The grounded prompt's verdict when it ran ("ok" or its failure code), even when the persona then answered.
    grounding: str = ""
    # The post-generation checks a faith answer went through, in order (checks.py); empty otherwise.
    checks: tuple[CheckResult, ...] = ()

    @property
    def citations(self) -> tuple[str, ...]:
        return tuple(source.id for source in self.sources)


@dataclass(frozen=True)
class Plan:
    """What `prepare` decided before any model call (conversation-policy §2).

    `route` names the step that decided: fixed, disclosure, language,
    quran_check, faith, exact, small_talk or retrieval. `step` is "done" when `result` is final,
    "generate" for the grounded prompt and "chat" for the persona.
    """
    route: str
    result: AnswerResult | None = None
    retrieval: Retrieval | None = None
    step: str = "done"
    faith: bool = False
    intent: str | None = None


class AnswerService:
    def __init__(self, retriever: HybridRetriever, generator: Generator, *, language: str = "en",
                 max_tokens: int = 320, age_band: str | None = None,
                 classifiers: tuple[router.SafetyClassifier, ...] = (), rng: random.Random | None = None,
                 second_judge: Generator | None = None):
        self.retriever, self.generator = retriever, generator
        self.language, self.max_tokens, self.age_band = language, max_tokens, age_band
        self.classifiers = classifiers
        # Chooses fallback lines and invitations; injectable so tests are deterministic.
        self.rng = rng or random.Random()
        identity = retriever.embedder.identity
        # The release's ayahs one by one (a misquoted ayah, the scene check) and the episode map of the stories.
        self.ayahs = AyahIndex(chunk for chunk in retriever.release.chunks
                               if retriever.include_drafts or chunk.servable)
        self.verifier = checks.Verifier(load_episodes(), self.ayahs, second_judge)
        self.provenance = {
            "releaseId": retriever.release.manifest.release_id,
            "model": generator.model,
            "promptVersion": PROMPT_VERSION,
            "retriever": RETRIEVER_VERSION,
            "verifier": VERIFIER_VERSION,
            "embedder": f"{identity.name}/{identity.model}",
            "policy": POLICY_VERSION,
            "chatPromptVersion": chat.CHAT_PROMPT_VERSION,
            "chatChecker": chat.CHAT_CHECKER_VERSION,
            "judge": judge.JUDGE_VERSION,
            "judge2": second_judge.model if second_judge is not None else "off",
            "router": router.ROUTER_VERSION,
            "checks": checks.CHECKS_VERSION,
            "curated": curated.CURATED_VERSION,
            "never": never.NEVER_VERSION,
        }

    def _result(self, answer_type: str, text: str, reason: str, segments: tuple[Segment, ...] | None = None,
                sources: tuple[Source, ...] = ()) -> AnswerResult:
        return AnswerResult(answer_type, text, segments or (Segment(text, ()),), sources, dict(self.provenance), reason)

    def _abstain(self, reason: str, language: str = "en") -> AnswerResult:
        return self._result("abstained", reply("abstain", language), reason)

    def _abstain_faith(self, reason: str, language: str = "en") -> AnswerResult:
        return self._result("abstained", reply("abstain_faith", language), "faith_abstain:" + reason)

    def _reviewed(self, candidate: Candidate | None) -> AnswerResult | None:
        if candidate is None or len(candidate.chunk.text) > MAX_CHARS:
            return None
        chunk = candidate.chunk
        return self._result("reviewed_answer", chunk.text, "reviewed_match", (Segment(chunk.text, (chunk.id,)),),
                            (Source.of(chunk),))

    def _route(self, text: str) -> AnswerResult | None:
        found = router.route(text, self.classifiers)
        if found.category == "retrieve":
            return None
        answer_type, name = FIXED[found.category]
        if found.category == "safety":
            # Abuse and grooming never send the child back to a parent; distress gets a calmer line.
            name = SAFETY_REPLY.get(found.reason_code, "safety")
        return self._result(answer_type, reply(name, reply_language(text)), "route:" + found.category)

    def route(self, text: str) -> AnswerResult | None:
        """A fixed reply, or None when the question needs retrieval. Cheap and deterministic."""
        started = perf_counter()
        try:
            result = self._route(text)
        except Exception as exception:  # fail closed: a broken rule must not let a question through
            logger.warning("rag_route_error type=%s", type(exception).__name__)
            result = self._abstain("error:" + type(exception).__name__)
        if result is not None:
            self._log(result, 0, started)
        return result

    def prepare(self, text: str) -> Plan:
        """Everything before a model call, in the policy's order (conversation-policy §2).

        The evaluator calls this directly, so offline results follow exactly
        the path the API takes.
        """
        fixed = self._route(text)
        if fixed is not None:
            return Plan("fixed", fixed)
        # "Are you a real person?", "هل أنت شيخ؟": an honest fixed reply in any service language, before the faith
        # step, because the question names a faith word ("sheikh") without asking about faith (§16).
        disclosed = router.disclosure(text)
        if disclosed is not None:
            return Plan("disclosure", self._result("chat", reply("disclosure", disclosed), "disclosure"))
        language = reply_language(text)
        if language != self.language:
            # The corpus holds this service's language only; the abstention is in the child's language.
            return Plan("language", self._abstain("language_mismatch", language))
        # An ayah quoted with altered words gets the exact ayah, never an answer built on the altered text (§14).
        corrected = self._quran_correction(text, language)
        if corrected is not None:
            return Plan("quran_check", corrected)
        # What to say on an occasion the curated package covers, or how to do a part of the prayer it teaches:
        # its items verbatim, with no model call (curated.py, conversation-policy §17).
        curated_reply = self._curated(text, language)
        if curated_reply is not None:
            return Plan("curated", curated_reply)
        where = {"language": self.language, "age_band": self.age_band}
        # An Arabizi question is searched with Arabic terms, narrowed to the prophets it names.
        query, prophets = text, ()
        if arabizi.is_arabizi(text):
            expansion = arabizi.expand(text)
            query, prophets = expansion.query, expansion.prophet_ids
        search = dict(where, prophet_ids=prophets)
        if router.is_faith_topic(text):
            # Only the corpus answers faith: never small talk, never the persona.
            retrieval = self.retriever.retrieve(query, **search) if query else Retrieval((), True)
            if retrieval.weak:
                return Plan("faith", self._abstain_faith("weak_evidence", language), retrieval, faith=True)
            reviewed = self._reviewed(retrieval.reviewed)
            if reviewed is not None:
                return Plan("faith", reviewed, retrieval, faith=True)
            return Plan("faith", None, retrieval, "generate", faith=True)
        candidate = self.retriever.exact(text, **where)
        exact = self._reviewed(candidate)
        if exact is not None:
            return Plan("exact", exact, Retrieval((candidate,), False, candidate))
        intent = router.small_talk(text)
        if intent is not None:
            if language == "ar":
                # The persona prompt and its checks read English only: reviewed Arabic copy instead.
                return Plan("small_talk", self._chat_reply(intent, None, "chat_fixed", language), intent=intent)
            return Plan("small_talk", step="chat", intent=intent)
        retrieval = self.retriever.retrieve(query, **search) if query else Retrieval((), True)
        if retrieval.weak:
            if language == "ar":
                return Plan("retrieval", self._chat_reply("other", None, "chat_fixed", language), retrieval)
            return Plan("retrieval", None, retrieval, "chat")
        reviewed = self._reviewed(retrieval.reviewed)
        if reviewed is not None:
            return Plan("retrieval", reviewed, retrieval)
        # A religious best passage makes it a faith answer, whatever words the question used.
        faith = is_faith_passage(retrieval.candidates[0].chunk)
        return Plan("retrieval", None, retrieval, "generate", faith=faith)

    def _curated(self, text: str, language: str) -> AnswerResult | None:
        if language != "ar":
            return None
        selection = curated.select(text, self.retriever.eligible(language=language, age_band=self.age_band))
        if selection is None:
            return None
        segments = tuple(Segment(chunk.text.strip(), (chunk.id,)) for chunk in selection.chunks)
        sources = tuple(Source.of(chunk) for chunk in selection.chunks)
        return self._result("grounded", curated.text(selection), "curated_verbatim:" + selection.topic, segments,
                            sources)

    def _quran_correction(self, text: str, language: str) -> AnswerResult | None:
        near = self.ayahs.near_quote(text)
        if near is None:
            return None
        ayah, chunk = near.ayah, near.ayah.chunk
        surah = surah_name(chunk) or ("سورة" if language == "ar" else "Surah") + f" {ayah.surah}"
        corrected = reply("quran_correction", language).format(surah=surah, number=ayah.number, ayah=ayah.text)
        if len(corrected) > MAX_CHARS:  # never cut an ayah: name it instead
            corrected = reply("quran_correction_named", language).format(surah=surah, number=ayah.number)
        return self._result("grounded", corrected, "quran_correction", (Segment(corrected, (chunk.id,)),),
                            (Source.of(chunk),))

    def answer(self, text: str) -> AnswerResult:
        """The full path. Never raises."""
        started, passages, faith = perf_counter(), 0, False
        try:
            plan = self.prepare(text)
            faith = plan.faith
            if plan.step == "generate":
                passages = len(plan.retrieval.candidates)
                result = self._generate(text, [candidate.chunk for candidate in plan.retrieval.candidates], faith)
            elif plan.step == "chat":
                result = self._chat(text, plan.intent)
            else:
                result = plan.result
                passages = 1 if result.answer_type == "reviewed_answer" else 0
            result = self._return_salam(text, result)
        except Exception as exception:
            # The type only: messages from lower layers are written to carry no
            # content, but an unexpected exception's message might.
            logger.warning("rag_answer_error type=%s", type(exception).__name__)
            code = "error:" + type(exception).__name__
            language = _language_or_english(text)
            result = (self._abstain_faith(code, language) if faith or _faith_or_false(text)
                      else self._abstain(code, language))
        self._log(result, passages, started)
        return result

    def _generate(self, text: str, passages: list[Chunk], faith: bool) -> AnswerResult:
        language = reply_language(text)
        # The prompt follows the best passage: the faith prompt when it is religious text (Quran, tafsir, hadith).
        # A faith question over app-help passages keeps the app-help prompt, where Robert speaking as "I" is right.
        output = self.generator.complete(build_messages(text, passages, faith=is_faith_passage(passages[0]),
                                                        language=language), max_tokens=self.max_tokens)
        grounding = verify(output, passages)
        if grounding.ok:
            released = " ".join(segment.text for segment in grounding.segments)
            # The "must never" rules before any check that costs a model call (never.py): a reply that breaks
            # one is withheld whatever it cites.
            broken = never.violations(released)
            if broken:
                code = "never:" + broken[0]
                religious = faith or any(is_faith_passage(chunk) for chunk in passages)
                result = self._abstain_faith(code, language) if religious else self._abstain(code, language)
                return replace(result, grounding="ok")
            by_id = {chunk.id: chunk for chunk in passages}
            cited = [by_id[chunk_id] for chunk_id in
                     dict.fromkeys(chunk_id for segment in grounding.segments for chunk_id in segment.citations)]
            # Whatever the prompt, an answer that cites religious text is a faith answer: it passes every
            # post-generation check, the faith judge last (checks.py).
            results: tuple[CheckResult, ...] = ()
            if faith or any(is_faith_passage(chunk) for chunk in cited):
                answer = checks.Answer(text, released, grounding.segments, tuple(cited), router.is_faith_topic(text))
                results, problem = self.verifier.run(answer, self.generator)
                if problem is not None:
                    return replace(self._abstain_faith(problem, language),
                                   grounding=problem.removeprefix("grounding:"), checks=results)
            result = self._result("grounded", released, "grounded", grounding.segments,
                                  tuple(Source.of(chunk) for chunk in cited))
            return replace(result, grounding="ok", checks=results)
        failure = str(grounding.failure)
        if faith:
            result = self._abstain_faith("grounding:" + failure, language)
        elif failure in DECLINED and language == "en":
            result = self._chat(text, None)
        else:
            result = self._abstain("grounding:" + failure, language)
        return replace(result, grounding=failure)

    def _chat(self, text: str, intent: str | None) -> AnswerResult:
        """The persona call (conversation-policy §5).

        `intent` comes from the small-talk detector, which already knows the
        message is chat; it is None when retrieval sent the message here, and
        then only a readable `chat` verdict makes it chat.
        """
        try:
            output = self.generator.complete(chat.build_chat_messages(text), max_tokens=chat.CHAT_MAX_TOKENS,
                                             json_mode=True, temperature=chat.CHAT_TEMPERATURE)
        except Exception as exception:
            logger.warning("rag_chat_error type=%s", type(exception).__name__)
            failure = "error:" + type(exception).__name__
            if intent is None:
                return self._abstain("persona_failed:" + failure)
            return self._chat_reply(intent, None, "chat_fallback:" + failure)
        verdict = chat.read(output, feeling=intent == "feeling_negative", salam=router.has_salam(text))
        if verdict.kind == "faith":
            if intent is None:
                return self._abstain_faith("persona")
            # The detector already ruled faith out ("Jazak Allah khair" is a thank you), so the persona's doubt
            # costs its own words, not the child's answer: reviewed copy, which says nothing about faith.
            return self._chat_reply(intent, verdict, "chat_fallback:faith")
        if verdict.kind is None:
            if intent is None:
                return self._abstain("persona_failed:" + str(verdict.failure))
            return self._chat_reply(intent, None, "chat_fallback:" + str(verdict.failure))
        if verdict.kind == "question":
            if intent is None:
                return self._abstain("question")
            return self._chat_reply(intent, verdict, "chat_fallback:question")
        if not verdict.ok:
            return self._chat_reply(intent, verdict, "chat_fallback:" + str(verdict.failure))
        broken = never.violations(verdict.reply)
        if broken:
            # Reviewed copy instead of the persona's words (never.py), as for any other failed chat check.
            return self._chat_reply(intent, verdict, "chat_fallback:never:" + broken[0])
        return self._chat_reply(intent, verdict, "chat")

    def _chat_reply(self, intent: str | None, verdict: chat.ChatVerdict | None, reason: str,
                    language: str = "en") -> AnswerResult:
        """A chat turn: the checked reply or reviewed fallback copy, now and then with an invitation (§7, §8)."""
        feeling = verdict.feeling if verdict is not None else intent == "feeling_negative"
        fallbacks = FALLBACKS.get(language, FALLBACKS["en"])
        if reason == "chat":
            text = verdict.reply
        else:
            # A difficult feeling the model reported always gets the calm line that points to a trusted
            # grown-up, even when the detector did not see it ("I'm scared of the dark").
            distress = verdict is not None and verdict.distress
            fallback = "feeling_negative" if distress else intent or "other"
            text = self.rng.choice(fallbacks.get(fallback, fallbacks["other"]))
        if not feeling and intent not in NO_INVITATION and self.rng.random() < INVITATION_RATE:
            text = f"{text} {self.rng.choice(INVITATIONS_BY_LANGUAGE.get(language, INVITATIONS_BY_LANGUAGE['en']))}"
        return self._result("chat", text, reason)

    def _return_salam(self, text: str, result: AnswerResult) -> AnswerResult:
        """A child's salam is returned before a chat reply or an abstention that does not already return it (§7)."""
        if result.answer_type not in ("chat", "abstained") or not router.has_salam(text) \
                or router.has_salam(result.text):
            return result
        returned = f"{reply('salam_return', reply_language(text))} {result.text}"
        return replace(result, text=returned, segments=(Segment(returned, ()),))

    def _log(self, result: AnswerResult, passages: int, started: float):
        fields = {
            "answer_type": result.answer_type,
            "release_id": self.provenance["releaseId"],
            "model": self.provenance["model"],
            "prompt_version": self.provenance["promptVersion"],
            "retriever": self.provenance["retriever"],
            "verifier": self.provenance["verifier"],
            "embedder": self.provenance["embedder"],
            "policy": self.provenance["policy"],
            "chat_prompt_version": self.provenance["chatPromptVersion"],
            "chat_checker": self.provenance["chatChecker"],
            "passages": passages,
            "latency_ms": round((perf_counter() - started) * 1000),
        }
        # Which fixed route fired is already implied by the answer type and is
        # not repeated; other outcomes are fixed codes that help operators.
        # The small-talk intent is never logged: it can be an inference about a
        # child's feelings.
        if not result.reason.startswith("route:"):
            fields["outcome"] = result.reason
        if result.grounding and result.grounding != "ok":
            fields["grounding"] = result.grounding
        if result.checks:
            fields["checks"] = checks.summary(result.checks)
            fields["checks_version"] = self.provenance["checks"]
        logger.info("rag_answer %s", json.dumps(fields, sort_keys=True), extra={"rag": fields})


def _language_or_english(text: str) -> str:
    try:
        return reply_language(text)
    except Exception:  # an error path must not raise again
        return "en"


def _faith_or_false(text: str) -> bool:
    try:
        return router.is_faith_topic(text)
    except Exception:  # an error path must not raise again
        return False


def assemble(settings, release_dir: str | Path, *, include_drafts: bool = False) -> AnswerService:
    """An `AnswerService` over one release, from the server's settings.

    The server, the evaluator and the operator console all build through here,
    so they cannot disagree about embedder, model or endpoints.
    """
    try:
        loaded = load_release(Path(release_dir))
    except ReleaseError as exception:
        raise RuntimeError(f"Release {release_dir} failed verification: {exception}") from None
    try:
        embedder = embedder_for(settings.embedding_model, settings.embedding_endpoint)
        retriever = HybridRetriever(loaded, embedder, include_drafts=include_drafts)
        generator = OpenAICompatibleGenerator(settings.llm_base_url, settings.llm_model,
                                              settings.llm_timeout_seconds)
        judge_model = getattr(settings, "judge_model", "")
        second_judge = OpenAICompatibleGenerator(settings.llm_base_url, judge_model, settings.llm_timeout_seconds,
                                                 allowlist=JUDGE_MODELS) if judge_model else None
    except (RetrieverError, ValueError) as exception:
        raise RuntimeError(f"Grounded answers cannot start: {exception}") from None
    return AnswerService(retriever, generator, language=getattr(settings, "rag_language", "en"),
                         second_judge=second_judge)


def _record_provenance():
    """Uvicorn configures only its own loggers, so without a handler the one
    provenance line per answer would be dropped. The line carries versions,
    counts and timings only, never the question, passages or answer."""
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s %(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)


def build_answer_service(settings) -> AnswerService:
    """The API's answer service. Fails closed: any configuration problem stops startup."""
    settings.require_rag()
    # Drafts reach the API only in the operator's corpus preview (§9.1); the bootstrap then says so,
    # and an app built without that notice refuses the service.
    service = assemble(settings, settings.rag_release, include_drafts=settings.rag_preview_drafts)
    _record_provenance()
    return service
