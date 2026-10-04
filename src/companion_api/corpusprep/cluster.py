"""Duplicate hadith clusters across Bukhari and Muslim, and Nawawi 40 links into them.

Two records are the same hadith when their matn (the text after the first
"صلى الله عليه وسلم", or the whole text when it has none) agrees: Dice >= 0.85
on comparison trigrams. The chain differs between narrations, so it is left
out of the comparison. A cluster is one record for retrieval; its primary is
the strongest source (an eligible record first, Bukhari before Muslim, then
the lowest number), and the others are listed as cluster members.

A Nawawi hadith is linked to a record only when its own takhrij names that
collection ("رواه ... البخاري / مسلم", "صحيحيهما") and at least 60% of the
matn overlaps; 45-60% is `needs_check`. Nothing is linked by guesswork.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass

from .hadith import compare_tokens, containment, dice

CLUSTER_DICE = 0.85
LINK = 0.6
LINK_CHECK = 0.45
MIN_GRAMS = 6
_RARE_DF = 100
_PBUH = ["صلي", "لله", "عليه", "وسلم"]  # compare_tokens form of the salutation
STRENGTH = {"bukhari": 0, "muslim": 1}


def matn_tokens(text: str) -> list[str]:
    words = compare_tokens(text)
    for position in range(len(words) - 3):
        if words[position:position + 4] == _PBUH and position < 0.8 * len(words):
            return words[position + 4:]
    return words


def grams(words: list[str]) -> set:
    return set(words) if len(words) < 3 else {tuple(words[i:i + 3]) for i in range(len(words) - 2)}


@dataclass(frozen=True)
class Record:
    collection: str
    number: str
    eligible: bool
    grams: frozenset

    @property
    def ref(self) -> str:
        return f"{self.collection}:{self.number}"


def _number_key(number: str) -> tuple:
    return tuple(float(part) for part in number.split("."))


def _index(records: list[Record]) -> dict:
    index: dict = defaultdict(list)
    for position, record in enumerate(records):
        for gram in record.grams:
            index[gram].append(position)
    return index


def cluster(records: list[Record]) -> dict[str, dict]:
    """ref -> {"cluster_id", "primary", "members"} for every record (singletons included)."""
    index = _index(records)
    parent = list(range(len(records)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for position, record in enumerate(records):
        if len(record.grams) < MIN_GRAMS:
            continue
        votes = Counter(other for gram in record.grams for other in index[gram]
                        if len(index[gram]) <= _RARE_DF and other != position)
        for other, _ in sorted(votes.items(), key=lambda item: (-item[1], item[0]))[:10]:
            if len(records[other].grams) >= MIN_GRAMS and dice(record.grams, records[other].grams) >= CLUSTER_DICE:
                left, right = find(position), find(other)
                if left != right:
                    parent[left] = right
    groups: dict[int, list[Record]] = defaultdict(list)
    for position, record in enumerate(records):
        groups[find(position)].append(record)
    result = {}
    for members in groups.values():
        members.sort(key=lambda r: (not r.eligible, STRENGTH.get(r.collection, 9), _number_key(r.number)))
        primary = members[0]
        info = {"cluster_id": f"hc-{primary.collection}-{primary.number.replace('.', '-')}", "primary": primary.ref,
                "members": [member.ref for member in members]}
        for member in members:
            result[member.ref] = info
    return result


def _takhrij_names(words: list[str]) -> set[str]:
    """Collections named by the takhrij sentence(s) inside a Nawawi text."""
    names = set()
    for position, word in enumerate(words):
        if word == "روه":
            window = words[position + 1:position + 12]
            if any(token.endswith("بخري") for token in window):
                names.add("bukhari")
            if any(token in ("مسلم", "ومسلم") for token in window):
                names.add("muslim")
        if word.startswith("صحيحيهم") or word.startswith("لصحيحين"):
            names.update(("bukhari", "muslim"))
    return names


def link_nawawi(nawawi: list[tuple[str, str]], records: list[Record]) -> dict[str, dict]:
    """nawawi number -> {"status", "ref", "score", "takhrij"}; status linked | needs_check | not_linked."""
    index = _index(records)
    links = {}
    for number, text in nawawi:
        mine = grams(matn_tokens(text))
        named = _takhrij_names(compare_tokens(text))
        votes = Counter(other for gram in mine for other in index.get(gram, ()) if len(index[gram]) <= 200)
        best = None
        for other, _ in sorted(votes.items(), key=lambda item: (-item[1], item[0]))[:30]:
            record = records[other]
            if record.collection not in named:
                continue
            score = max(containment(record.grams, mine), containment(mine, record.grams))
            key = (score, record.eligible, -STRENGTH.get(record.collection, 9))
            if best is None or key > best[0]:
                best = (key, record)
        if best and best[0][0] >= LINK:
            status = "linked"
        elif best and best[0][0] >= LINK_CHECK:
            status = "needs_check"
        else:
            status = "not_linked"
        links[number] = {"status": status, "ref": best[1].ref if best and status != "not_linked" else None,
                         "score": round(best[0][0], 3) if best else None, "takhrij": sorted(named)}
    return links
