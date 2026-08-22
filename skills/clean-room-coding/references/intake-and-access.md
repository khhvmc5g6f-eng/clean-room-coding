# Intake and access authority

Before analysing ANY reference material, establish:

- What material has been supplied, and by whom.
- Whether it's public, and if so whether public accessibility actually
  grants permission to reverse-engineer/benchmark it (it usually doesn't,
  by itself -- see the relevant jurisdiction pack(s)'
  `interoperability_permitted_acts` sections for the specific statutory
  exceptions that might apply, e.g. CDPA 1988 s.50B/50BA (England & Wales),
  DMCA 17 U.S.C. §1201(f) (US federal), Software Directive 2009/24/EC
  Art. 6 (EU), CPI Art. L122-6-1 (France), UrhG §69e (Germany), or
  Copyright Act Art. 47-3/47-4 (Japan)).
- Whether access is under a licence or contract with its own restrictions
  (reverse-engineering bans, confidentiality, technical protection
  measures).
- Whether the material contains trade secrets or personal data.

`cleanroom intake --source "..." --access-authority public|licensed|contractual|unknown`
records this in `ACCESS_AND_AUTHORITY_REPORT.md` and the evidence ledger.
**`unknown` is not a placeholder to fill in later** -- treat it as a hard
stop. Do not proceed to `cleanroom analyse` (or any manual reading of Zone
R content) while access authority is `unknown`; ask the user to resolve it,
or recommend they consult counsel if they're not sure.

Possession is not permission. A file being on disk, or a repo being public
on GitHub, does not by itself establish that studying/copying/decompiling
it for the purpose of a clean-room reimplementation is authorised.
