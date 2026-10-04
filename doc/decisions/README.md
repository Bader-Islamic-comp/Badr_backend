# حزم القرار

كل حزمة هون مكتوبة عشان صاحب القرار يقرر بأقل من 10 دقائق. القرار نفسه **ما بيصير إلا** لما
صاحبه يكتبه بـ [`decisions.yaml`](decisions.yaml) ويتشغّل `python3 scripts/apply_decisions.py`.
أحكام الوكيل المراجع (ai_prereview: pass / flag / fail) مساعدة للترتيب بس، ومش موافقة.

| الحزمة | صاحب القرار | الدور بـ decisions.yaml | عدد البنود |
| --- | --- | --- | --- |
| [01-licensing.md](01-licensing.md) — التراخيص ومسودات إيميلات الإذن | Mousa al-Rashdan | governance | 15 مصدر |
| [02-reviewers.md](02-reviewers.md) — المراجعون وتعارض المصالح | Mousa al-Rashdan | governance | قائمة المراجعين |
| [03-policies.md](03-policies.md) — اعتماد السياسات السبع | Mousa al-Rashdan | governance | 7 سياسات |
| [04-content-review.md](04-content-review.md) — المحتوى الشرعي (fail ثم flag ثم pass). فيه نص الآيات والأحاديث منقول من canonical، فهو برا git: `python3 scripts/build_decision_packages.py` بيولّده | اللجنة الشرعية (مراجعون مؤهلون) | scholarly | 40 حديث + 59 نطاق |
| [05-eval-review.md](05-eval-review.md) — أسئلة gold و harmful | Momen Alhamza (+ مسؤول الحماية لبنود الضيق) | pipeline | 310 + 151 |
| [06-section18.md](06-section18.md) — قرارات §18 | Mousa al-Rashdan (مع المنتج) | governance | 8 قرارات |
| ADR 0005 (`doc/adr-0005-embedding-selection.md`) | Momen Alhamza | pipeline | 1 |

## مين بيقرر شو (بيفرضه `apply_decisions.py`)

- `source:*`، `policy-*`، `section18:*`، `reviewers`: Mousa al-Rashdan بس، بدور `governance`.
- `selection-*`، `map-*`، ونسخ الأعمار (`<id>@7-9`): مراجع مسجّل بـ `corpus/governance/reviewers.yaml`
  بـ `qualified: true` وعنده الدور المطلوب، ومش كاتب البند، وما أعلن تعارض عليه.
- أسئلة gold و harmful و`adr-0005`: Momen Alhamza بدور `pipeline` (أو مراجع مؤهل للأسئلة).
- أي قرار ناقص الاسم أو التاريخ أو الدور، أو من شخص مش مخوّل، بيرفض الملف كله وما بيتطبّق شي.

## مثال

```yaml
decisions:
- decision_id: D-0001
  item_ids: ["policy-scope"]
  decision: approve
  decided_by: Mousa al-Rashdan
  role: governance
  date: 2026-10-01
  note: "النطاق معتمد كما هو."
```

## Signing a decision (test/corpus-tasks)

A decision applies only if every line of its entry was committed in a commit SSH-signed by the person in its
`decided_by` (`src/companion_api/governance/signatures.py`). Typing a name is no longer enough.

1. The governance owner registers each decider's public key in `corpus/governance/signers.yaml` (name exactly as
   in `decided_by`, a principal without spaces, the one-line `ssh-ed25519 ...` key). That file, `reviewers.yaml`
   and `decisions.yaml` are code-owned (`.github/CODEOWNERS`); turn on "Require review from Code Owners" in the
   branch protection of `main` (a repository setting) and put the real GitHub handle in `CODEOWNERS`.
2. The decider signs the commit that adds their entry:
   `git config gpg.format ssh`, `git config user.signingkey ~/.ssh/id_ed25519.pub`, `git commit -S -m "D-0001: ..."`.
3. `python scripts/apply_decisions.py --check` reports any entry that is uncommitted, unsigned, signed by an
   unregistered key or by someone other than `decided_by`; `apply_decisions.py` refuses the whole file then.
4. After applying, `python scripts/verify_audit.py --write-anchor` records the audit trail's head in
   `corpus/governance/audit_anchor.json`; commit it with the decision state, so a later deletion or rewrite of
   `corpus/governance/audit.jsonl` is caught.
