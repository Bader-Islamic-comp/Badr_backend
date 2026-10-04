# Corpus scope and out-of-scope list (draft)

Status: **draft for the governance owner (Mousa al-Rashdan); not approved.** Task:
[Define corpus scope and an explicit out-of-scope list](https://app.clickup.com/t/z8q7hbct49).
Open product decisions are not assumed here: exact age band, launch market and curriculum
framework stay open (`doc/architecture.md` §18, items 1-4).

## In scope

| Layer | Content | Status today |
| --- | --- | --- |
| 0 Reference text | Quran (Tanzil Uthmani, verbatim); Sahih al-Bukhari and Sahih Muslim narrations whose text agrees across two sources | Fetched and checked; draft |
| 1 Scholarly explanation | An approved simplified tafsir tied to its ayat | Tafsir al-Muyassar fetched for development only (licence unclear) |
| 2 Child content | Prophet story scenes and hadith explanations written and reviewed by people, citing layer 0 | Templates only |
| 3 App help | Synthetic app help (`corpus/dev-app-help`) | Existing; never religious |

Wave 1: Adam, Nuh, Ibrahim, Yusuf and Musa (peace be upon them) from the Quran; 40 hadith from
Bukhari, Muslim and an-Nawawi's Forty (only through a linked Bukhari/Muslim record).

## Out of scope (the corpus does not contain, and Robert does not answer from)

1. **Rulings (fatwa)** and "is it haram / allowed" questions: redirected to a parent, teacher or
   qualified scholar; reviewed content only if the board provides it.
2. **Advanced or disputed questions** (fiqh differences, creed controversies, sectarian topics):
   escalated to a human, never answered generatively; a family's madhhab is never inferred.
3. **Isra'iliyyat** and unverified story details (names, ages, numbers, places, durations not in
   the Quran or an authentic hadith), even when well known.
4. **Weak (da'if) or fabricated (mawdu') hadith**, and any hadith without a grading and a named grader
   from the source. Riyad as-Salihin and al-Adab al-Mufrad are outside Wave 1 until a licensed,
   graded source exists.
5. **Depiction of prophets, companions and angels**: no physical description, no invented dialogue,
   no images; Robert narrates and is never a character in a prophet's story (plan.md component 7).
6. **Frightening detail**: graphic violence, punishment or torment; the fate of those who rejected a
   prophet is told briefly and calmly.
7. **Model-memory religious text**: no ayah or hadith text written, corrected or completed from memory;
   sacred text is always copied from a registered, checksummed source and quoted by reference.
8. **Open web** and unregistered sources.
9. **Personal, safeguarding or medical advice** beyond the reviewed fixed replies.
10. **Anything about the child** (utterances, names, disclosures) in the corpus or the vector store.

## Decisions needed

- Which tafsir, and which extra collections, the board accepts.
- Whether Wave 1 prophets' stories may use the tafsir or only the ayat.
- The board's policy for recognized differences (architecture §6.5).
