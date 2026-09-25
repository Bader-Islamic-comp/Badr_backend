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

from . import chat, normalize, router
from .embeddings import embedder_for
from .generator import OpenAICompatibleGenerator
from .grounding import DECLINE, MAX_CHARS, VERIFIER_VERSION, Segment, verify
from .prompts import PROMPT_VERSION, build_messages
from .release import ReleaseError, load_release
from .responses import (ABSTAIN, ABSTAIN_FAITH, CHAT_FALLBACKS, INJECTION, INVITATIONS, PERSONAL_DATA, RULING,
                        SAFETY, SALAM_RETURN)
from .retriever import RETRIEVER_VERSION, Candidate, HybridRetriever, Retrieval, RetrieverError
from .types import Chunk, Generator

logger = logging.getLogger("companion_api.rag")

POLICY_VERSION = "conversation-policy-v1"
INVITATION_RATE = 1 / 3  # conversation-policy §8: at most about one chat reply in three
# A difficult feeling deserves kindness, not a nudge, and a goodbye is a goodbye.
NO_INVITATION = frozenset({"feeling_negative", "goodbye"})
# The grounded model said the sources do not answer: outside faith, the persona decides whether it was chat.
DECLINED = frozenset({"not_in_sources", "mixed_not_in_sources"})

# Route category -> (answer type, fixed reply).
FIXED = {
    "safety": ("safety", SAFETY),
    "personal_data": ("redirected", PERSONAL_DATA),
    "ruling": ("redirected", RULING),
    "injection": ("redirected", INJECTION),
}


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

    @property
    def citations(self) -> tuple[str, ...]:
        return tuple(source.id for source in self.sources)


@dataclass(frozen=True)
class Plan:
    """What `prepare` decided before any model call (conversation-policy §2).

    `route` names the step that decided: fixed, language, faith, exact,
    small_talk or retrieval. `step` is "done" when `result` is final,
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
                 classifiers: tuple[router.SafetyClassifier, ...] = (), rng: random.Random | None = None):
        self.retriever, self.generator = retriever, generator
        self.language, self.max_tokens, self.age_band = language, max_tokens, age_band
        self.classifiers = classifiers
        # Chooses fallback lines and invitations; injectable so tests are deterministic.
        self.rng = rng or random.Random()
        identity = retriever.embedder.identity
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
        }

    def _result(self, answer_type: str, text: str, reason: str, segments: tuple[Segment, ...] | None = None,
                sources: tuple[Source, ...] = ()) -> AnswerResult:
        return AnswerResult(answer_type, text, segments or (Segment(text, ()),), sources, dict(self.provenance), reason)

    def _abstain(self, reason: str) -> AnswerResult:
        return self._result("abstained", ABSTAIN, reason)

    def _abstain_faith(self, reason: str) -> AnswerResult:
        return self._result("abstained", ABSTAIN_FAITH, "faith_abstain:" + reason)

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
        answer_type, reply = FIXED[found.category]
        return self._result(answer_type, reply, "route:" + found.category)

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
        if normalize.detect_language(text) != self.language:
            # The router's patterns and both detectors only read this service's language.
            return Plan("language", self._abstain("language_mismatch"))
        where = {"language": self.language, "age_band": self.age_band}
        if router.is_faith_topic(text):
            # Only the corpus answers faith: never small talk, never the persona.
            retrieval = self.retriever.retrieve(text, **where)
            if retrieval.weak:
                return Plan("faith", self._abstain_faith("weak_evidence"), retrieval, faith=True)
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
            return Plan("small_talk", step="chat", intent=intent)
        retrieval = self.retriever.retrieve(text, **where)
        if retrieval.weak:
            return Plan("retrieval", None, retrieval, "chat")
        reviewed = self._reviewed(retrieval.reviewed)
        if reviewed is not None:
            return Plan("retrieval", reviewed, retrieval)
        return Plan("retrieval", None, retrieval, "generate")

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
            result = self._abstain_faith(code) if faith or _faith_or_false(text) else self._abstain(code)
        self._log(result, passages, started)
        return result

    def _generate(self, text: str, passages: list[Chunk], faith: bool) -> AnswerResult:
        output = self.generator.complete(build_messages(text, passages), max_tokens=self.max_tokens)
        grounding = verify(output, passages)
        if grounding.ok:
            released = " ".join(segment.text for segment in grounding.segments)
            by_id = {chunk.id: chunk for chunk in passages}
            cited = list(dict.fromkeys(chunk_id for segment in grounding.segments for chunk_id in segment.citations))
            unanswered = _unanswered_faith(text, released, [by_id[chunk_id] for chunk_id in cited]) if faith else None
            if unanswered is not None:
                return replace(self._abstain_faith(unanswered), grounding=unanswered)
            result = self._result("grounded", released, "grounded", grounding.segments,
                                  tuple(Source.of(by_id[chunk_id]) for chunk_id in cited))
            return replace(result, grounding="ok")
        failure = str(grounding.failure)
        if faith:
            result = self._abstain_faith("grounding:" + failure)
        elif failure in DECLINED:
            result = self._chat(text, None)
        else:
            result = self._abstain("grounding:" + failure)
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
        return self._chat_reply(intent, verdict, "chat")

    def _chat_reply(self, intent: str | None, verdict: chat.ChatVerdict | None, reason: str) -> AnswerResult:
        """A chat turn: the checked reply or reviewed fallback copy, now and then with an invitation (§7, §8)."""
        feeling = verdict.feeling if verdict is not None else intent == "feeling_negative"
        if reason == "chat":
            reply = verdict.reply
        else:
            # A difficult feeling the model reported always gets the calm line that points to a trusted
            # grown-up, even when the detector did not see it ("I'm scared of the dark").
            distress = verdict is not None and verdict.distress
            fallback = "feeling_negative" if distress else intent or "other"
            reply = self.rng.choice(CHAT_FALLBACKS.get(fallback, CHAT_FALLBACKS["other"]))
        if not feeling and intent not in NO_INVITATION and self.rng.random() < INVITATION_RATE:
            reply = f"{reply} {self.rng.choice(INVITATIONS)}"
        return self._result("chat", reply, reason)

    def _return_salam(self, text: str, result: AnswerResult) -> AnswerResult:
        """A child's salam is returned before a chat reply or an abstention that does not already return it (§7)."""
        if result.answer_type not in ("chat", "abstained") or not router.has_salam(text) \
                or router.has_salam(result.text):
            return result
        reply = f"{SALAM_RETURN} {result.text}"
        return replace(result, text=reply, segments=(Segment(reply, ()),))

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
        logger.info("rag_answer %s", json.dumps(fields, sort_keys=True), extra={"rag": fields})


def _unanswered_faith(question: str, answer: str, cited: list[Chunk]) -> str | None:
    """Why a verified answer on a faith topic is not an answer from the corpus, or None (§2 step 3).

    Found on the real model: "Hi Robert! What is Ramadan?" drew "I am a learning
    companion ... so I cannot answer about what Ramadan is [1]", and "Tell me a
    story about the prophets" drew "I am not an imam or a scholar, so for
    questions about prophets, please ask a parent [4]". Both pass the lexical
    support check, because every word is in passages about Robert. So a decline
    is refused, and the answer and the passages it cites must both mention the
    question's own faith terms (any faith term when the question has none of
    its own, such as "What does alhamdulillah mean?").
    """
    if DECLINE.search(router.matchable(answer)):
        return "declined"
    wanted = router.faith_words(question)
    for text in (answer, " ".join(chunk.text for chunk in cited)):
        found = router.faith_words(text)
        if not (found & wanted if wanted else found):
            return "off_topic"
    return None


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
    except (RetrieverError, ValueError) as exception:
        raise RuntimeError(f"Grounded answers cannot start: {exception}") from None
    return AnswerService(retriever, generator)


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
    service = assemble(settings, settings.rag_release)
    _record_provenance()
    return service
