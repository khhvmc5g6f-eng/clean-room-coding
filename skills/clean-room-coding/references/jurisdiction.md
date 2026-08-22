# Jurisdiction resolution

`cleanroom jurisdiction` (`src/cleanroom/jurisdiction/resolver.py`) builds
`JURISDICTION_MATRIX.json` from `.cleanroom.yml`'s `jurisdiction.required_markets`
/ `informational_markets` -- it never defaults to England & Wales, the US,
or the developer's own jurisdiction. A market with no matching pack is
recorded as tier `unknown`, not silently dropped.

For each of 9 legal issues (copyright, licence_contract, patents,
trademarks, database_rights, trade_secrets, confidentiality, consumer_law,
competition_law), every configured market gets a tier: `primary` (required
market with a pack), `secondary` (informational market with a pack), or
`unknown` (no pack available -- flag for qualified local counsel).

v0.1 ships two jurisdiction packs, `/jurisdictions/england-wales/framework.yml`
and `/jurisdictions/usa-federal/framework.yml`: governing statutes, leading
case law with real citations (Navitaire v Easyjet, SAS v WPL, IBCOS v
Barclays, Computer Associates v Altai, Sega v Accolade, Oracle v Google,
Lotus v Borland), conflicts-of-laws notes, court terminology (including the
`simulated_judicial_role_title` used by `cleanroom judge` -- never call a
simulated reviewer a generic "judge" without this jurisdiction-appropriate
framing), and `questions_for_review`.

**More than one jurisdiction is normal.** If `required_markets` has more
than one entry, `conflicts_of_law_panel_required` is set `true` in the
matrix -- this means the analysis needs to separately work out which
jurisdiction's law governs which question (a licence contract's governing
law, and the copyright law of the country where protection is sought, are
different questions that can point to different countries) before treating
any per-market pack as dispositive.

Adding a jurisdiction pack for a market not yet covered is a real,
substantive task (primary statutes + leading cases + conflicts notes +
structured questions) -- don't fabricate one inline; see CONTRIBUTING.md.
