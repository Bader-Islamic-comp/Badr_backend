# Knowledge graph (`kg-v2`, test/corpus-tasks)

The graph connects every ayah, every section of Tafsir Ibn Kathir and of the 13 Quranpedia tafsir books, every
hadith of the five collections and the 25 prophets named in the Quran. It is a draft index for reviewers: it
shows where a prophet's story is told, explained and narrated, which hadith Ibn Kathir cites for an ayah, which
other ayat he quotes, and which books of the reference package explain an ayah. Nothing in it is reviewed, and
it is not used to answer children.

**kg-v2** (2026-10-02) adds the Quranpedia tafsir books as sections linked to the ayat they explain (`EXPLAINS`
only, with `source_id` and `package_rule` on node and edge), the English translations that give each ayah (ayah
attribute `translations`) and the King Fahd Complex check of the Quran text (ayah attribute `kfc_check`,
[`corpus/reports/quran_text_comparison.md`](../corpus/reports/quran_text_comparison.md)). Ibn Kathir's sections
and every other edge are unchanged from kg-v1; Ibn Kathir's nodes and edges also carry `source_id` and
`package_rule` now.

## Build and look things up

```bash
python scripts/fetch_sources.py      # canonical Quran, hadith, Tafsir Ibn Kathir, Quranpedia books and translations
python scripts/build_corpus.py       # layer 0 (the hadith clusters the graph reads)
python scripts/build_graph.py        # ~19 s: corpus/graph/ + the review report
python scripts/graph_query.py prophet yusuf
python scripts/graph_query.py ayah 12:4 --text
python scripts/graph_query.py hadith bukhari:3395
python scripts/graph_query.py section ibn-kathir:12:4
python scripts/graph_query.py section tabari:12:4     # a Quranpedia book's section: <book>:<surah>:<ayat>
```

`graph_query.py` prints the node's attributes first (for an ayah: `kfc_check`, `translations`).
`corpus/graph/` (nodes.jsonl, edges.jsonl, unresolved.jsonl, summary.json, 20 MB) is rebuilt from the corpus
and stays out of git. The review report `corpus/reports/knowledge_graph.md` and the per-prophet index
`corpus/reports/knowledge_graph_prophets.json` are in git. The graph holds ids, references and counts only,
never source text; `graph_query.py --text` prints text from the local canonical files to the terminal.

## Nodes and edges

| Node | Id | Count |
| --- | --- | ---: |
| surah | `surah:12` | 114 |
| ayah | `quran:12:4` | 6,236 |
| tafsir section | `ibn-kathir:12:4-6` (consecutive ayat Ibn Kathir explains together) | 1,911 |
| tafsir section (kg-v2) | `tabari:12:4`, `mujahid:2:14`: a Quranpedia book's passages on one range of ayat | 20,900 |
| hadith | `bukhari:13`, `muslim:45`, `nawawi40:13`, `riyadussalihin:7`, `adab_mufrad:3` | 18,204 |
| prophet | `prophet:yusuf` | 25 |

| Edge | From → to | How it is found | Count |
| --- | --- | --- | ---: |
| `IN_SURAH` | ayah → surah | structure | 6,236 |
| `EXPLAINS` | section → ayah | the section's range (Ibn Kathir: `section_range`, Quranpedia books: `passage_range`) | 42,645 |
| `QUOTES_AYAH` | section or hadith → ayah | 5-word runs; at least 60% of an ayah of 6+ words, outside the section's own range | 4,057 |
| `CITES_HADITH` | section → hadith | the editor's takhrij notes (`صحيح البخاري برقم (٤٦٨٨)`), and 6-word runs shared with the hadith text (isnad boilerplate removed) | 2,628 |
| `MENTIONS_PROPHET` | ayah, section or hadith → prophet | names from `corpus/aliases.yaml` (titles too, for ayat) | 3,690 |
| `STORY_IN` | prophet → ayah | the curated source maps (`corpus/candidate/prophets/`) | 809 |
| `SAME_NARRATION` | hadith → hadith | the hadith clusters and the Nawawi links | 885 |

Every edge has a `method` and a `status`: `exact` (structure), `draft` (curated, under review),
`text_confirmed` (an editor's citation whose hadith text is found in the section), and `needs_check`.

## The tafsir books (kg-v2)

A Quranpedia passage names the ayat it explains (`content[].ayahs` in the dump); a section is a book's passages
on the same range, in the book's order (`passages`, `words` on the node). Passages flagged `out_of_place` (an
introduction filed under the last ayat, Tafsir Mujahid's al-Fatiha filed under 12:51) or empty are left out.

| Book (`source_id` without `quranpedia-tafsir-`) | `package_rule` | Sections | Ayat explained | Words |
| --- | --- | ---: | ---: | ---: |
| mujahid | in_rule | 1,537 | 1,537 | 81,656 |
| sufyan-thawri | in_rule | 606 | 634 | 23,162 |
| yahya-ibn-sallam (surahs 16-37 except 22) | in_rule | 1,880 | 1,880 | 170,756 |
| malik (compiled) | in_rule | 587 | 587 | 58,174 |
| shafii (compiled) | in_rule | 302 | 302 | 119,430 |
| farra-maani | in_rule | 777 | 1,400 | 243,515 |
| abu-ubayda-majaz | in_rule | 657 | 4,782 | 91,108 |
| ibn-qutayba-gharib | in_rule | 391 | 4,046 | 56,002 |
| tabari | borderline | 3,731 | 6,231 | 2,907,453 |
| nasai | borderline | 448 | 590 | 68,986 |
| sahih-masbur | borderline | 1,742 | 1,742 | 574,539 |
| mukhtasar | outside_rule | 6,236 | 6,236 | 190,303 |
| saadi | outside_rule | 2,006 | 6,236 | 609,845 |

The outside_rule books are in the graph (and in `corpus/canonical`) for comparison only; layer 0 has documents
for the in_rule and borderline books. The new sections have no quotation, hadith or name links yet: those rules
were tuned on Ibn Kathir's text and editor's notes, and the early books cite differently (full isnads, no
takhrij numbers).

The English translations are an ayah attribute rather than nodes: `translations` lists `hilali-khan`,
`sahih-international`, `ruwwad` and `mukhtasar` where the translation gives the ayah (6,236 ayat each, except
al-Mukhtasar's English, 6,164: 72 of its records hold the text labelled for another ayah).

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

- The sources are `candidate` (Ibn Kathir, al-Muyassar, every Quranpedia book and translation) and
  `pending_legal` (Tanzil, hadith): the graph may be used for development and review only.
- The graph is rebuilt, not edited: corrections belong in the aliases, the source maps or the matching rules.
- It does not decide anything about authenticity: a hadith Ibn Kathir cites can be weak, and Ibn Kathir himself
  grades many narrations he quotes.
