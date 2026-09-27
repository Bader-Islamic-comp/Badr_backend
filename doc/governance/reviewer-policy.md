# Reviewer qualification and conflict-of-interest policy (template)

Status: **template; owner Mousa al-Rashdan; not approved.** Task:
[Reviewer qualification and conflict-of-interest policy](https://app.clickup.com/t/z8q7hbct4c).

## Roles

| Role | Reviews | Proposed qualification (to be set by the owner) |
| --- | --- | --- |
| Scholarly reviewer | Religious accuracy of layer 2 text, source maps, hadith selection | [formal study in hadith/tafsir, ijaza or equivalent — to define] |
| Safeguarding reviewer | Tone, fear, age suitability, sensitive topics | [child-safeguarding training — to define] |
| Language reviewer | Reading level for 7-9 and 10-11 | [Arabic education background — to define] |

## Rules (enforced by `scripts/review.py`)

1. **Separation:** the author of a draft version never reviews it.
2. **Qualification:** only reviewers listed in `corpus/governance/reviewers.yaml` with
   `qualified: true` can approve or reject. The list is empty today, so nothing can be approved.
3. **Conflicts of interest:** a reviewer lists the draft ids they must not review (`conflicts`);
   approval of those is refused. Declaration is renewed [yearly — to define].
4. **Checks first:** a version is approved only if its reading-level checks pass.
5. **Every decision is audited** (`corpus/governance/audit.jsonl`, hash-chained).

## Conflict-of-interest declaration (template)

```yaml
- name:            # full name, as used with --actor
  qualified: true
  roles: []        # scholarly | safeguarding | language
  qualification_ref:
  conflicts: []    # draft ids, e.g. story-yusuf-s01
  declared_on:     # YYYY-MM-DD
```

Declare: authorship or co-authorship of the item, financial interest in a source or publisher,
family relationship with the author, and any other interest the owner lists.

## Decisions needed

Named reviewers, their qualifications, the minimum number of reviewers per item, and the renewal period.
