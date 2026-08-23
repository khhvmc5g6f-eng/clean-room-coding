# Real licence texts (regression fixtures)

These are verbatim copies of real, canonical licence documents, fetched
from their authoritative sources, used to regression-test
`cleanroom.licence.discovery._fingerprint_text` against real-world input
rather than short synthetic excerpts (see
`tests/unit/test_licence_discovery_real_texts.py` -- this is the fixture
set that caught and proves the fix for the fingerprint-collision bug where
canonical BSD-3-Clause and AGPL-3.0 text were misclassified as
"conflicting evidence").

- `BSD-3-Clause.txt` -- a canonical BSD 3-Clause template.
- `AGPL-3.0.txt`, `LGPL-3.0.txt`, `LGPL-2.1.txt` -- fetched from
  https://www.gnu.org/licenses/ on 2026-08-22. Copyright Free Software
  Foundation, Inc. Each document's own terms explicitly permit verbatim
  copying and distribution ("Everyone is permitted to copy and distribute
  verbatim copies of this license document, but changing it is not
  allowed."), which is why they're stored here unmodified.
- `GPL-3.0.txt` -- a byte-for-byte copy of the real, unmodified GPLv3
  LICENSE file from the `Flymaster-Variometer-Log-Pc` repository (present
  locally in this machine's `~/skill-review/` clone), added 2026-08-23 as
  the regression fixture for a false-positive where this fingerprint-text's
  own Section 13 ("Use with the GNU Affero General Public License")
  previously caused a genuine GPL-3.0 file to be misclassified as
  AGPL-3.0-only. Same FSF copyright and verbatim-copying terms as above.

Not covered by this project's own BUSL-1.1 licence -- these are the FSF's
documents, reproduced verbatim under their own stated terms, solely as
test fixtures.
