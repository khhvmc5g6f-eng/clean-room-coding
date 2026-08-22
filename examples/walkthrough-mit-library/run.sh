#!/usr/bin/env bash
# A complete, runnable clean-room walkthrough against a synthetic MIT-licensed
# reference. Run from anywhere with `cleanroom` installed:
#   bash examples/walkthrough-mit-library/run.sh /tmp/crc-walkthrough
set -euo pipefail

PROJECT_DIR="${1:-/tmp/crc-walkthrough}"
rm -rf "$PROJECT_DIR"
mkdir -p "$PROJECT_DIR"
cd "$PROJECT_DIR"

echo "== init =="
cleanroom init --name "Sort Library Reimplementation" --id sort-reimpl

echo "== reference material (synthetic, MIT-licensed) =="
mkdir -p zone-r/upstream-sort-lib
cat > zone-r/upstream-sort-lib/LICENSE <<'EOF'
MIT License

Copyright (c) 2020 Example Upstream Authors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software.
EOF
cat > zone-r/upstream-sort-lib/main.py <<'EOF'
# SPDX-License-Identifier: MIT
def sort_entries(entries, ascending=True):
    return sorted(entries, key=lambda e: e.name, reverse=not ascending)
EOF

echo "== intake =="
cleanroom intake --source "upstream-sort-lib v1.0 (synthetic example)" --access-authority public

echo "== licence discovery =="
cleanroom licence zone-r

echo "== jurisdiction =="
cleanroom jurisdiction

echo "== analyse + specify =="
cleanroom analyse
cleanroom specify add-requirement --id CR-REQ-000001 --kind requirement \
  --statement "Entries can be sorted ascending or descending by name" \
  --classification observable_requirement
cleanroom specify add-behavioral --given "a list of entries" \
  --when "ascending order by name is requested" \
  --then "entries are returned alphabetically ascending" \
  --requirement CR-REQ-000001

echo "== sanitise + handoff =="
cat > zone-h/sort-behaviour.md <<'EOF'
# Feature: sort entries

GIVEN a list of entries
WHEN the user requests ascending order by name
THEN entries are returned sorted alphabetically ascending
EOF
cleanroom sanitise zone-h/sort-behaviour.md
cleanroom handoff --specification-version v1 --all-c0

echo "== build (register a fresh, source-blind implementation agent) =="
cleanroom build --role "Backend Team"
cleanroom architect --title "Sort implementation" \
  --decision "Use Python's stable sorted() keyed on the entries' name field" \
  --rationale "Derived from the handed-off behavioural spec; no dependency on the reference's internal data structures or naming"

echo "== implement (independently, from the spec only) =="
cat > zone-i/sort.py <<'EOF'
def sort_by_name(entries, ascending=True):
    return sorted(entries, key=lambda entry: entry["name"], reverse=not ascending)
EOF
cat > zone-i/requirements.txt <<'EOF'
# no third-party dependencies
EOF

echo "== test / provenance / audit =="
cleanroom test
cleanroom provenance
cleanroom audit

echo "== legal / judge / report / release / status =="
cleanroom legal --access-authority public
cleanroom judge
cleanroom report --version 0.1.0
set +e
cleanroom release
echo "(exit code $? -- 9/MANUAL_REVIEW_REQUIRED is expected here, not a failure)"
set -e
cleanroom status

echo
echo "Done. See $PROJECT_DIR/CLEAN_ROOM_REPORT.md and $PROJECT_DIR/CLEAN_ROOM_CERTIFICATE.json"
