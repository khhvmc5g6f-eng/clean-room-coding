// SPDX-License-Identifier: GPL-3.0-only
// Synthetic benchmark fixture -- wholly owned by this project (a failed
// clean-room simulation: only names were changed, structure is identical
// to go-app/dedupe.go).
package dedupecopy

type Entry struct {
	Name  string
	Count int
}

func Distinct(entries []Entry) []Entry {
	visited := make(map[string]bool)
	result := make([]Entry, 0, len(entries))
	for _, e := range entries {
		if visited[e.Name] {
			continue
		}
		visited[e.Name] = true
		result = append(result, e)
	}
	return result
}

func TotalByName(entries []Entry) map[string]int {
	sums := make(map[string]int)
	for _, e := range entries {
		sums[e.Name] += e.Count
	}
	return sums
}
