# Changelog

Development increments, newest first. Nothing here is a release: this is an
adult-operated local demo on synthetic data, and the gates in
[`doc/development-boundary.md`](doc/development-boundary.md) are still open.

Paired client changes are in `comp-mobile/CHANGELOG.md`; the shared files under
`contracts/` must stay byte-identical between the two repositories.

## Unreleased — 2026-09-22

A cosmetic catalogue that is actually earned, so the client's new customization
tab has something server-authoritative behind it.

### Added

- **A four-look catalogue** in `content.py` (`COSMETICS`, `CATALOGUE`), priced
  in the same learning stars the lesson ledger grants: Robert Original (0),
  Sunset Copper (5), Dune Walker (15), Midnight Teal (30). Ids match the room's
  own fixed allowlist; the service never invents one.
- **`POST /v1/cosmetics/claim`** — spends the catalogue price against the
  ledger. The price and the balance are read here, never sent by the client, so
  a look cannot be unlocked by a tampered app.
  - `403 insufficient_stars` when it costs more than the balance.
  - `404 not_found` for an unknown id.
  - An already-owned look is a no-op reporting `"spent": 0`, so a lost response
    or a second key cannot charge twice.
  - The balance can never go negative.
- **`tools/export_contracts.py`** — writes `contracts/openapi-v1.json` from the
  app itself, and optionally a consumer's copy. The app serves no
  `/openapi.json`, so that file is the published contract; hand-editing is how
  it drifts from the routes it describes.
- **Ownership and equipment state** in `DemoStore`: `_owned`, `_equipped`,
  `_completed_lessons`, plus `inventory()`, `claim()` and `completed_any_lesson`.

### Changed

- **`GET /v1/inventory`** now returns the whole catalogue from the store, with
  `description` and `cost` on each entry, instead of one hard-coded item.
- **`PUT /v1/equipped-cosmetics`** accepts any look this process records as
  owned, instead of only `default`. Anything else is `403 cosmetic_not_owned`.
- **Lesson completion is tracked explicitly** rather than inferred from the
  ledger being empty. Spending stars writes to the same ledger, so the old
  `if not self._ledger` guard would have silently stopped granting the lesson's
  five stars after the first purchase. `GET /v1/challenges/today` reads
  `store.completed_any_lesson` for the same reason.
- Spending appends a **negative** entry to the append-only ledger, so the
  balance stays a sum over that ledger and is never stored as a mutable number.
  Earn-only still holds in the sense the roadmap means it: stars come from
  learning, never from money, trade or chance.

### Contracts and docs

- `contracts/openapi-v1.json` regenerated: the claim route, the `Claimed`
  schema, and `description`/`cost` on `Cosmetic`.
- `contracts/avatar-bridge-v1.schema.json`: `cosmeticId` widened from
  `const: "default"` to the four-id enum.
- `doc/product-architecture-roadmap.md`: the claim route added to the API list.
- `README.md`: the new endpoint's rules, the ledger note and how to regenerate
  the contract.

### Verification

25 → **28 tests**. The new ones cover looks being earned from the ledger and
never going negative, equipment following ownership, and the published contract
matching the routes the app actually serves.

`DemoStore` remains a bounded, process-local adapter for synthetic tests. All of
this ownership state disappears on restart and is not a PostgreSQL replacement.
