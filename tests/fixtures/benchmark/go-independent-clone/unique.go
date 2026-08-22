// SPDX-License-Identifier: MIT
// Synthetic benchmark fixture -- wholly owned by this project (a
// successful clean-room simulation: implements the same OBSERVABLE
// behaviour as go-app/dedupe.go -- de-duplicate by key, sum values by
// key -- from an independently-written behavioural spec, using a
// deliberately different structural approach: a single struct with
// methods and slice-index tracking instead of two free functions).
package unique

type Ledger struct {
	seenIndex map[string]int
	Items     []LedgerItem
}

type LedgerItem struct {
	ID    string
	Total int
}

func NewLedger() *Ledger {
	return &Ledger{seenIndex: make(map[string]int)}
}

func (l *Ledger) Add(id string, amount int) {
	if idx, ok := l.seenIndex[id]; ok {
		l.Items[idx].Total += amount
		return
	}
	l.seenIndex[id] = len(l.Items)
	l.Items = append(l.Items, LedgerItem{ID: id, Total: amount})
}
