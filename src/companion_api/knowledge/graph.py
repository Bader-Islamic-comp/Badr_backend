"""Build the corpus knowledge graph (`kg-v1`): nodes and typed edges between the Quran, Tafsir Ibn Kathir, hadith
and the prophets, from the canonical files (doc/knowledge-graph.md).

Nodes                                  Edges (source -> target)
  surah:12                               IN_SURAH          ayah -> surah
  quran:12:4          (ayah)             EXPLAINS          tafsir section -> ayah        (the ayat it explains)
  ibn-kathir:12:4-6   (tafsir section)   QUOTES_AYAH       tafsir section | hadith -> ayah (a quotation found in the text)
  bukhari:13, muslim:45, nawawi40:13 ... CITES_HADITH      tafsir section -> hadith      (editor's takhrij note, text match)
  prophet:yusuf                          MENTIONS_PROPHET  ayah | tafsir section | hadith -> prophet
                                         STORY_IN          prophet -> ayah               (the curated source maps)
                                         SAME_NARRATION    hadith -> hadith              (clusters, Nawawi links)

Every edge records how it was found (`method`) and whether a person still has to look (`status`). Nothing here
is reviewed: the graph is a draft index for reviewers, built from candidate and pending_legal sources. It holds
ids, references and counts only, never source text, so it can be shared for review; `graph_query.py` shows text
from the local canonical files when a reviewer asks for it.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import Path
import re

import yaml

from ..corpusprep import ibn_kathir
from ..rag import normalize

GRAPH_VERSION = "kg-v1"
QUOTE_GRAM = 5             # words per n-gram when finding a Quran quotation
MIN_QUOTED_AYAH_WORDS = 6  # shorter ayat are formulas that recur everywhere
MIN_AYAH_COVERAGE = 0.6    # share of an ayah's n-grams found in the text
HADITH_GRAM = 6            # words per n-gram when finding a hadith in tafsir text
COMMON_GRAM_LIMIT = 20     # an n-gram in more hadith than this is isnad boilerplate ("حدثنا عبد الله بن يوسف")
MIN_HADITH_GRAMS = 8       # rare n-grams a text must share with a hadith for a text match
MIN_HADITH_COVERAGE = 0.25
VERIFY_GRAMS = 3           # rare n-grams that confirm an editor's citation
HADITH_COLLECTIONS = ("bukhari", "muslim", "nawawi40", "riyadussalihin", "adab_mufrad")

# Prophets' names are also narrators' names: "موسى بن إسماعيل", "حدثنا يحيى", "أبو موسى". A name right after one
# of these words, or right before بن/ابن, is a narrator or a kunya, not a mention of the prophet.
_NARRATOR_BEFORE = frozenset({"حدثنا", "حدثني", "اخبرنا", "اخبرني", "انبانا", "عن", "سمعت", "ابو", "ابي", "ابا",
                              "ام", "ابن", "بن", "وحدثنا", "وحدثني", "واخبرنا", "فحدثنا", "وابو", "وابي", "وابا",
                              "وام", "فابو", "روايه", "زياده", "حديث", "تابعه", "وتابعه", "نحو", "بنحو", "وابن",
                              "وتابع", "تابع", "رواه", "يقل", "خالفه", "وقال", "وعن", "واللفظ", "اللفظ", "لفظ",
                              "وحديث"})
_SON_OF = frozenset({"بن", "ابن"})
# A name followed by an isnad word is a narrator ("يونس عن الزهري", "اسحاق اخبرنا").
_NARRATOR_AFTER = frozenset({"عن", "حدثنا", "اخبرنا", "حدثني", "اخبرني", "انبانا", "يعني"})
# "بني اسراييل", "بني ادم": a people named after the prophet, not the prophet.
_CHILDREN_OF = frozenset({"بني", "بنو", "وبني", "يابني"})
_KEEP_SON_OF = {("عيسي", "مريم")}  # Isa son of Maryam is the prophet
# Names that are also ordinary words count only where their story is in view.
_CONTEXT = {
    "hud": re.compile(r"\b(?:عاد|اخاهم|يا هود|قوم هود)\b"),
    "salih": re.compile(r"\b(?:ثمود|الناقه|يا صالح|قوم صالح|اخاهم صالحا)\b"),
    "yahya": re.compile(r"\b(?:زكريا|يا يحيي|نبشرك|بيحيي)\b"),
}
_AMBIGUOUS_NAMES = {"احمد"}  # also "I praise" and "more praiseworthy"
# In hadith and tafsir prose two more names need their context: أدم is also "leather" and "brown", and many
# narrators are called محمد (the Prophet is named with a blessing, a title or an address).
_PROSE_CONTEXT = {
    "adam": re.compile(r"\b(?:يا ادم|ابونا ادم|ابوكم ادم|ابيكم ادم|ادم عليه السلام|خلق ادم|خلق الله ادم|ذريه ادم|"
                       r"صلب ادم|حاج ادم|فيقول ادم|قال ادم يا|ادم وموسي|موسي وادم|اباكم ادم|ادم ابو)\b"),
    "muhammad": re.compile(r"\b(?:محمد صلي الله عليه وسلم|محمد رسول الله|محمدا رسول الله|يا محمد|بنت محمد|"
                           r"ال محمد|امه محمد|محمدا عبده|محمد عبده|نبيك محمد|محمد نبي)\b"),
}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_MARKS = re.compile("[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed\u0640]")
_TAKHRIJ = re.compile(r"صحيح\s+(البخاري|مسلم)[^()\[\]]{0,20}\(([0-9٠-٩][0-9٠-٩،,\s/-]*)\)")
_COLLECTION = {"البخاري": "bukhari", "مسلم": "muslim"}


@dataclass
class Graph:
    nodes: dict[str, dict] = field(default_factory=dict)
    edges: dict[tuple[str, str, str], dict] = field(default_factory=dict)
    unresolved: list[dict] = field(default_factory=list)

    def node(self, node_id: str, kind: str, **attrs) -> None:
        self.nodes.setdefault(node_id, {"id": node_id, "type": kind}).update(attrs)

    def edge(self, kind: str, source: str, target: str, **attrs) -> None:
        current = self.edges.setdefault((kind, source, target), {"type": kind, "source": source, "target": target})
        methods = set(current.get("method", "").split("+")) - {""}
        methods |= set(attrs.pop("method", "").split("+")) - {""}
        current.update(attrs)
        if methods:
            current["method"] = "+".join(sorted(methods))


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def _tokens(text: str) -> list[str]:
    return normalize.search_text(text).split()


def matn(tokens: list[str]) -> list[str]:
    """A hadith's tokens from its first mention of the Prophet: the isnad before it is mostly narrators' names."""
    for index, token in enumerate(tokens):
        if token in ("النبي", "نبي") or (token == "رسول" and index + 1 < len(tokens) and tokens[index + 1] == "الله"):
            return tokens[index:]
    return tokens


def _grams(tokens: list[str], size: int) -> set[str]:
    return {" ".join(tokens[index:index + size]) for index in range(len(tokens) - size + 1)}


# Prophets ----------------------------------------------------------------------------------------------------

def load_prophets(aliases_path: Path) -> list[dict]:
    data = yaml.safe_load(Path(aliases_path).read_text(encoding="utf-8"))
    prophets = []
    for entry in data["prophets"]:
        names = [normalize.search_text(item["alias"]) for item in entry.get("names_ar") or []]
        titles = [normalize.search_text(item["alias"]) for item in entry.get("titles_ar") or []
                  if item.get("status") == "evidence_found"]
        prophets.append({"id": entry["id"], "names": [n for n in names if n], "titles": [t for t in titles if t],
                         "latin": entry.get("latin") or []})
    return prophets


class NameMatcher:
    """Finds the prophets a folded text names, with the narrator, kunya and context rules above."""

    def __init__(self, prophets: list[dict], *, titles: bool, prose: bool = False):
        # `prose`: hadith and tafsir text, where Adam and Muhammad also need a context (_PROSE_CONTEXT).
        self.context = {**_CONTEXT, **(_PROSE_CONTEXT if prose else {})}
        self.single: dict[str, str] = {}
        self.phrases: list[tuple[list[str], str]] = []
        for prophet in prophets:
            spellings = prophet["names"] + (prophet["titles"] if titles else [])
            # The Quran's own spelling too: the simple text writes داوود where an alias may say داود (norm-v3).
            spellings += [normalize.search_text(name, quranic=True) for name in spellings]
            for name in dict.fromkeys(spellings):
                words = name.split()
                if len(words) == 1:
                    self.single[words[0]] = prophet["id"]
                else:
                    self.phrases.append((words, prophet["id"]))

    def _core(self, token: str) -> str | None:
        for candidate in (token, token[1:] if token[:1] in "وفبلك" and len(token) > 3 else None):
            if candidate is None:
                continue
            if candidate in self.single:
                return candidate
            if candidate.endswith("ا") and candidate[:-1] in self.single:  # accusative: نوحا, لوطا
                return candidate[:-1]
        return None

    def find(self, tokens: list[str]) -> Counter:
        found: Counter = Counter()
        joined = " ".join(tokens)
        for index, token in enumerate(tokens):
            name = self._core(token)
            if name is None:
                continue
            before = tokens[index - 1] if index else ""
            after = tokens[index + 1] if index + 1 < len(tokens) else ""
            after2 = tokens[index + 2] if index + 2 < len(tokens) else ""
            if before in _NARRATOR_BEFORE or before in _CHILDREN_OF or after in _NARRATOR_AFTER:
                continue
            if after in _SON_OF and (name, after2) not in _KEEP_SON_OF:
                continue
            if name in _AMBIGUOUS_NAMES and before != "اسمه":
                continue
            prophet = self.single[name]
            if prophet in self.context and not self.context[prophet].search(joined):
                continue
            found[prophet] += 1
        for words, prophet in self.phrases:
            found[prophet] += joined.count(" ".join(words))
        return +found


# Quotations of the Quran ---------------------------------------------------------------------------------------

class QuranIndex:
    """5-gram index of the simple-spelling Quran, to find the ayat a text quotes."""

    def __init__(self, ayat: dict[tuple[int, int], str]):
        self.grams: dict[tuple[int, int], set[str]] = {}
        self.index: dict[str, list[tuple[int, int]]] = defaultdict(list)
        for key, text in ayat.items():
            tokens = text.split()
            if len(tokens) < MIN_QUOTED_AYAH_WORDS:
                continue
            grams = _grams(tokens, QUOTE_GRAM)
            self.grams[key] = grams
            for gram in grams:
                self.index[gram].append(key)

    def quoted(self, tokens: list[str]) -> dict[tuple[int, int], float]:
        hits: dict[tuple[int, int], set[str]] = defaultdict(set)
        for gram in _grams(tokens, QUOTE_GRAM):
            for key in self.index.get(gram, ()):
                hits[key].add(gram)
        return {key: round(len(found) / len(self.grams[key]), 3) for key, found in hits.items()
                if len(found) / len(self.grams[key]) >= MIN_AYAH_COVERAGE}


# Hadith in tafsir text -----------------------------------------------------------------------------------------

class HadithIndex:
    """6-gram index of hadith texts without isnad boilerplate, to find the hadith a text quotes."""

    def __init__(self, texts: dict[str, list[str]]):
        grams = {hadith_id: _grams(tokens, HADITH_GRAM) for hadith_id, tokens in texts.items()}
        frequency = Counter(gram for found in grams.values() for gram in found)
        self.grams = {hadith_id: {gram for gram in found if frequency[gram] <= COMMON_GRAM_LIMIT}
                      for hadith_id, found in grams.items()}
        self.index: dict[str, list[str]] = defaultdict(list)
        for hadith_id, found in self.grams.items():
            for gram in found:
                self.index[gram].append(hadith_id)

    def shared(self, tokens: list[str]) -> dict[str, int]:
        counts: Counter = Counter()
        for gram in _grams(tokens, HADITH_GRAM):
            for hadith_id in self.index.get(gram, ()):
                counts[hadith_id] += 1
        return counts

    def matches(self, shared: dict[str, int]) -> dict[str, float]:
        return {hadith_id: round(count / len(self.grams[hadith_id]), 3) for hadith_id, count in shared.items()
                if count >= MIN_HADITH_GRAMS and self.grams[hadith_id]
                and count / len(self.grams[hadith_id]) >= MIN_HADITH_COVERAGE}


def takhrij(note: str) -> list[tuple[str, int]]:
    """(collection, number) pairs an editor's note cites, e.g. "صحيح البخاري برقم (٤٦٨٨)" -> ("bukhari", 4688)."""
    plain = _MARKS.sub("", note).replace("أ", "ا").replace("إ", "ا")
    found = []
    for match in _TAKHRIJ.finditer(plain):
        for part in re.split(r"[،,\s/]+", match.group(2).translate(_DIGITS)):
            if part.isdigit():
                found.append((_COLLECTION[match.group(1)], int(part)))
    return found


# Assembly ------------------------------------------------------------------------------------------------------

def build(corpus: Path, surah_names: dict[int, str] | None = None) -> Graph:
    """The graph from `corpus/` (canonical files, aliases, source maps, layer 0 hadith documents, reports)."""
    corpus = Path(corpus)
    graph = Graph()
    canonical = corpus / "canonical"
    ayat_rows = _jsonl(canonical / "quran/ayat.jsonl")
    ayat = {(row["surah"], row["ayah"]): row["text_normalized"] for row in ayat_rows}
    for surah in sorted({surah for surah, _ in ayat}):
        graph.node(f"surah:{surah}", "surah", number=surah,
                   **({"name_ar": surah_names[surah]} if surah_names and surah in surah_names else {}))
    for (surah, ayah), text in ayat.items():
        graph.node(f"quran:{surah}:{ayah}", "ayah", surah=surah, ayah=ayah, words=len(text.split()))
        graph.edge("IN_SURAH", f"quran:{surah}:{ayah}", f"surah:{surah}", method="structure", status="exact")

    prophets = load_prophets(corpus / "aliases.yaml")
    for prophet in prophets:
        graph.node(f"prophet:{prophet['id']}", "prophet", name_ar=prophet["names"][0] if prophet["names"] else None,
                   latin=prophet["latin"][:3])
    quran_names = NameMatcher(prophets, titles=True)
    text_names = NameMatcher(prophets, titles=False, prose=True)
    for (surah, ayah), text in ayat.items():
        for prophet, count in quran_names.find(text.split()).items():
            graph.edge("MENTIONS_PROPHET", f"quran:{surah}:{ayah}", f"prophet:{prophet}", method="name",
                       status="needs_check", count=count)

    for path in sorted((corpus / "candidate/prophets").glob("*_source_map.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for number, item in enumerate(data["ranges"], 1):
            match = re.match(r"^quran:(\d+):(\d+)(?:-(\d+))?$", item["ref"])
            if not match:
                continue
            surah, first = int(match.group(1)), int(match.group(2))
            for ayah in range(first, int(match.group(3) or first) + 1):
                if (surah, ayah) in ayat:
                    graph.edge("STORY_IN", f"prophet:{data['prophet_id']}", f"quran:{surah}:{ayah}",
                               method="source_map", status="draft", map_item=f"map-{data['prophet_id']}-{number:02d}",
                               topic=item.get("topic"))

    quran_index = QuranIndex(ayat)
    hadith_texts: dict[str, list[str]] = {}
    for collection in HADITH_COLLECTIONS:
        path = canonical / f"hadith/{collection}.jsonl"
        if not path.is_file():
            continue
        for row in _jsonl(path):
            hadith_id = f"{collection}:{row['number']}"
            tokens = _tokens(row.get("arabic_text") or "")
            hadith_texts[hadith_id] = tokens
            graph.node(hadith_id, "hadith", collection=collection, number=str(row["number"]),
                       grading=row.get("grading"), eligible=bool(row.get("eligible")),
                       crosscheck=row.get("crosscheck_status"))
            for prophet, count in text_names.find(matn(tokens)).items():
                graph.edge("MENTIONS_PROPHET", hadith_id, f"prophet:{prophet}", method="name", status="needs_check",
                           count=count)
            for (surah, ayah), coverage in quran_index.quoted(tokens).items():
                graph.edge("QUOTES_AYAH", hadith_id, f"quran:{surah}:{ayah}", method="ngram", status="needs_check",
                           coverage=coverage)

    _clusters(graph, corpus)
    _selection(graph, corpus)

    tafsir_path = canonical / "tafsir/ibn-kathir.jsonl"
    if tafsir_path.is_file():
        index = HadithIndex({hid: toks for hid, toks in hadith_texts.items() if hid.split(":")[0] in ("bukhari",
                                                                                                      "muslim")})
        for record in _jsonl(tafsir_path):
            _tafsir_section(graph, record, quran_index, index, text_names)
    return graph


def _tafsir_section(graph: Graph, record: dict, quran_index: QuranIndex, index: HadithIndex,
                    names: NameMatcher) -> None:
    section = record["section_id"]
    surah, first, last = record["surah"], record["from_ayah"], record["to_ayah"]
    notes = ibn_kathir.editor_notes(record["text"])
    tokens = _tokens(ibn_kathir.display_text(record["text"]))
    graph.node(section, "tafsir_section", surah=surah, from_ayah=first, to_ayah=last, words=record["words"],
               editor_notes=len(notes), source_id=record["source_id"])
    own = {(surah, ayah) for ayah in range(first, last + 1)}
    for key in own:
        graph.edge("EXPLAINS", section, f"quran:{key[0]}:{key[1]}", method="section_range", status="exact")
    for (s, a), coverage in quran_index.quoted(tokens).items():
        if (s, a) not in own:
            graph.edge("QUOTES_AYAH", section, f"quran:{s}:{a}", method="ngram", status="needs_check",
                       coverage=coverage)
    for prophet, count in names.find(tokens).items():
        graph.edge("MENTIONS_PROPHET", section, f"prophet:{prophet}", method="name", status="needs_check", count=count)
    shared = index.shared(tokens)
    matched = index.matches(shared)
    for hadith_id, coverage in matched.items():
        graph.edge("CITES_HADITH", section, hadith_id, method="text_match", status="needs_check", coverage=coverage)
    cited = {pair for note in notes for pair in takhrij(note)}
    muslim_numbers = sorted(number for collection, number in cited if collection == "muslim")
    muslim_matches = sorted(hadith_id for hadith_id in matched if hadith_id.startswith("muslim:"))
    for collection, number in sorted(cited):
        target = f"{collection}:{number}"
        if collection == "bukhari" and target in graph.nodes:
            confirmed = shared.get(target, 0) >= VERIFY_GRAMS
            graph.edge("CITES_HADITH", section, target, method="editor_note",
                       status="text_confirmed" if confirmed else "needs_check", editor_number=number)
        elif collection == "muslim" and len(muslim_numbers) == 1 and len(muslim_matches) == 1:
            # The editor numbers Muslim by Abdul-Baqi (1-3033), the canonical file sunnah.com-style: one cited
            # number and one Muslim hadith found in the same section's text are taken to be the same narration.
            graph.edge("CITES_HADITH", section, muslim_matches[0], method="editor_note",
                       status="text_confirmed", editor_number=number, editor_numbering="abdul-baqi")
        else:
            graph.unresolved.append({"section": section, "collection": collection, "editor_number": number,
                                     "candidates": muslim_matches if collection == "muslim" else [],
                                     "reason": "numbering differs (Abdul-Baqi)" if collection == "muslim"
                                     else "number not in the canonical collection"})


def _clusters(graph: Graph, corpus: Path) -> None:
    documents = corpus / "layer0/documents"
    if documents.is_dir():
        for path in sorted(documents.glob("hadith-*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            primary = data["units"][0]["reference"]
            for member in data.get("clusterRefs") or []:
                if member in graph.nodes and primary in graph.nodes:
                    graph.edge("SAME_NARRATION", primary, member, method="cluster", status="needs_check",
                               cluster=data.get("clusterId"))
    links = corpus / "reports/nawawi_links.json"
    if links.is_file():
        for number, link in json.loads(links.read_text(encoding="utf-8")).items():
            if link.get("ref") and link["ref"] in graph.nodes and f"nawawi40:{number}" in graph.nodes:
                graph.edge("SAME_NARRATION", f"nawawi40:{number}", link["ref"], method="nawawi_link",
                           status="text_confirmed" if link["status"] == "linked" else "needs_check",
                           score=link.get("score"))


def _selection(graph: Graph, corpus: Path) -> None:
    path = corpus / "candidate/hadith_selection.yaml"
    if path.is_file():
        for entry in yaml.safe_load(path.read_text(encoding="utf-8")).get("hadith") or []:
            primary = entry.get("cluster_primary")
            if primary in graph.nodes:
                graph.nodes[primary].update(wave1_selected=True, selection_topic=entry.get("topic"))


# Output --------------------------------------------------------------------------------------------------------

def write(graph: Graph, out: Path, *, inputs_sha256: str) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    nodes = sorted(graph.nodes.values(), key=lambda node: node["id"])
    edges = sorted(graph.edges.values(), key=lambda edge: (edge["type"], edge["source"], edge["target"]))
    (out / "nodes.jsonl").write_text("".join(json.dumps(n, ensure_ascii=False) + "\n" for n in nodes),
                                     encoding="utf-8", newline="\n")
    (out / "edges.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in edges),
                                     encoding="utf-8", newline="\n")
    (out / "unresolved.jsonl").write_text("".join(json.dumps(u, ensure_ascii=False) + "\n" for u in graph.unresolved),
                                          encoding="utf-8", newline="\n")
    summary = stats(graph)
    summary.update(graph_version=GRAPH_VERSION, inputs_sha256=inputs_sha256)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8",
                                      newline="\n")
    return summary


def stats(graph: Graph) -> dict:
    by_type = Counter(node["type"] for node in graph.nodes.values())
    edges = Counter(edge["type"] for edge in graph.edges.values())
    methods = Counter(f"{edge['type']}:{edge.get('method')}:{edge.get('status')}" for edge in graph.edges.values())
    per_prophet = {}
    for node in graph.nodes.values():
        if node["type"] != "prophet":
            continue
        incoming = [edge for edge in graph.edges.values()
                    if edge["type"] == "MENTIONS_PROPHET" and edge["target"] == node["id"]]
        per_prophet[node["id"]] = {
            "ayat_naming": sum(1 for edge in incoming if edge["source"].startswith("quran:")),
            "story_ayat": sum(1 for edge in graph.edges.values()
                              if edge["type"] == "STORY_IN" and edge["source"] == node["id"]),
            "tafsir_sections_naming": sum(1 for edge in incoming if edge["source"].startswith("ibn-kathir:")),
            "hadith_naming": sum(1 for edge in incoming
                                 if graph.nodes.get(edge["source"], {}).get("type") == "hadith"),
        }
    cites = [edge for edge in graph.edges.values() if edge["type"] == "CITES_HADITH"]
    editor = [edge for edge in cites if "editor_note" in edge.get("method", "") and edge["target"].startswith("bukhari:")]
    muslim = [edge for edge in cites if "editor_note" in edge.get("method", "") and edge["target"].startswith("muslim:")]
    return {"nodes": dict(sorted(by_type.items())), "edges": dict(sorted(edges.items())),
            "edges_by_method_status": dict(sorted(methods.items())), "per_prophet": per_prophet,
            "editor_citations": {"bukhari_linked": len(editor),
                                 "bukhari_text_confirmed": sum(1 for e in editor if e["status"] == "text_confirmed"),
                                 "bukhari_also_found_by_text": sum(1 for e in editor if "text_match" in e["method"]),
                                 "muslim_linked_through_text": len(muslim),
                                 "unresolved": dict(Counter(u["reason"] for u in graph.unresolved))}}


def inputs_digest(corpus: Path) -> str:
    """sha256 over the inputs that decide the graph, so a reader can tell which corpus build it came from."""
    digest = sha256()
    for relative in ("canonical/manifest.json", "aliases.yaml", "candidate/hadith_selection.yaml",
                     "reports/nawawi_links.json"):
        path = Path(corpus) / relative
        if path.is_file():
            digest.update(path.read_bytes())
    for path in sorted((Path(corpus) / "candidate/prophets").glob("*_source_map.yaml")):
        digest.update(path.read_bytes())
    return digest.hexdigest()
