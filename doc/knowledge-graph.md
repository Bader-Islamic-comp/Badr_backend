# Knowledge graph (`kg-v1`, test/corpus-tasks)

The graph connects every ayah, every section of Tafsir Ibn Kathir, every hadith of the five collections and the
25 prophets named in the Quran. It is a draft index for reviewers: it shows where a prophet's story is told,
explained and narrated, which hadith Ibn Kathir cites for an ayah, and which other ayat he quotes. Nothing in
it is reviewed, and it is not used to answer children.

## Build and look things up

```bash
python scripts/fetch_sources.py      # canonical Quran, hadith and Tafsir Ibn Kathir
python scripts/build_corpus.py       # layer 0 (the hadith clusters the graph reads)
python scripts/build_graph.py        # ~17 s: corpus/graph/ + the review report
python scripts/graph_query.py prophet yusuf
python scripts/graph_query.py ayah 12:4 --text
python scripts/graph_query.py hadith bukhari:3395
python scripts/graph_query.py section ibn-kathir:12:4
```

`corpus/graph/` (nodes.jsonl, edges.jsonl, unresolved.jsonl, summary.json, 6.8 MB) is rebuilt from the corpus
and stays out of git. The review report `corpus/reports/knowledge_graph.md` and the per-prophet index
`corpus/reports/knowledge_graph_prophets.json` are in git. The graph holds ids, references and counts only,
never source text; `graph_query.py --text` prints text from the local canonical files to the terminal.

## Nodes and edges

| Node | Id | Count |
| --- | --- | ---: |
| surah | `surah:12` | 114 |
| ayah | `quran:12:4` | 6,236 |
| tafsir section | `ibn-kathir:12:4-6` (consecutive ayat Ibn Kathir explains together) | 1,911 |
| hadith | `bukhari:13`, `muslim:45`, `nawawi40:13`, `riyadussalihin:7`, `adab_mufrad:3` | 18,204 |
| prophet | `prophet:yusuf` | 25 |

| Edge | From → to | How it is found | Count |
| --- | --- | --- | ---: |
| `IN_SURAH` | ayah → surah | structure | 6,236 |
| `EXPLAINS` | section → ayah | the section's range | 6,236 |
| `QUOTES_AYAH` | section or hadith → ayah | 5-word runs; at least 60% of an ayah of 6+ words, outside the section's own range | 4,057 |
| `CITES_HADITH` | section → hadith | the editor's takhrij notes (`صحيح البخاري برقم (٤٦٨٨)`), and 6-word runs shared with the hadith text (isnad boilerplate removed) | 2,628 |
| `MENTIONS_PROPHET` | ayah, section or hadith → prophet | names from `corpus/aliases.yaml` (titles too, for ayat) | 3,690 |
| `STORY_IN` | prophet → ayah | the curated source maps (`corpus/candidate/prophets/`) | 809 |
| `SAME_NARRATION` | hadith → hadith | the hadith clusters and the Nawawi links | 885 |

Every edge has a `method` and a `status`: `exact` (structure), `draft` (curated, under review),
`text_confirmed` (an editor's citation whose hadith text is found in the section), and `needs_check`.

## How good the links are (measured 2026-10-01)

- **Editor citations.** 1,554 Bukhari citations link to a hadith; 1,052 of them are confirmed by shared text,
  and 547 were also found by text matching alone. Sahih Muslim is cited by Abdul-Baqi's numbers while the
  canonical collection uses sunnah.com numbering, so a Muslim citation is linked only when the section's text
  matches exactly one Muslim hadith (92); the other 1,189 are listed in `corpus/graph/unresolved.jsonl` with
  their candidate hadith, until a number mapping exists.
- **Quotations.** In a sample, every `QUOTES_AYAH` edge from tafsir was an exact quotation; Ibn Kathir labels
  them himself ("الزخرف ٤٥"), which a later version can use as a second check.
- **Hadith by text.** Sampled `CITES_HADITH` text matches were on topic (the descent of Isa ↔ muslim:392, the
  cursed tree ↔ bukhari:6613, the major sins ↔ bukhari:6857).
- **Prophets' names in ayat** match the checked counts in `corpus/aliases.yaml` (Dawud 16, Ishaq 16, Yusuf 25,
  Adam 18 once "بني آدم" is excluded). Hud, Salih and Yahya are also ordinary words (هودا "Jews", صالح
  "righteous", يُحيي "gives life") and count only with a context word, so some mentions are missed.
- **Prophets' names in hadith** are the weakest link: narrators share the prophets' names ("موسى بن
  إسماعيل", "قال يونس", "أبو موسى"). Names in the isnad (before the first mention of the Prophet ﷺ), after
  narrator words, before بن, in kunyas and in "بني إسرائيل" are skipped; about four in five of the remaining
  mentions were right in a sample of 40. Every such edge is `needs_check`.

## Limits

- The sources are `candidate` (Ibn Kathir, al-Muyassar) and `pending_legal` (Tanzil, hadith): the graph may be
  used for development and review only.
- The graph is rebuilt, not edited: corrections belong in the aliases, the source maps or the matching rules.
- It does not decide anything about authenticity: a hadith Ibn Kathir cites can be weak, and Ibn Kathir himself
  grades many narrations he quotes.
