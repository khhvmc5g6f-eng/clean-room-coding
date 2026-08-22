// SPDX-License-Identifier: GPL-3.0-only
// Synthetic benchmark fixture -- wholly owned by this project.
package dedupe

type Record struct {
	Key   string
	Value int
}

func RemoveDuplicates(records []Record) []Record {
	seen := make(map[string]bool)
	out := make([]Record, 0, len(records))
	for _, r := range records {
		if seen[r.Key] {
			continue
		}
		seen[r.Key] = true
		out = append(out, r)
	}
	return out
}

func SumByKey(records []Record) map[string]int {
	totals := make(map[string]int)
	for _, r := range records {
		totals[r.Key] += r.Value
	}
	return totals
}
