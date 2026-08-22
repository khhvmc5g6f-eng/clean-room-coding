// SPDX-License-Identifier: MIT
// Synthetic benchmark fixture -- wholly owned by this project (a
// successful clean-room simulation: implements the same OBSERVABLE
// behaviour as js-app/filterUtils.js -- filter by active+priority, count
// by owner -- from an independently-written behavioural spec, using a
// deliberately different structural approach: functional array methods
// instead of manual loops, and a single combined pass instead of two
// separate functions).
function selectAndSummarize(widgets, priorityFloor) {
  const selected = widgets.filter((w) => w.active && w.priority >= priorityFloor);
  const ownerCounts = selected.reduce((acc, w) => {
    acc[w.owner] = (acc[w.owner] ?? 0) + 1;
    return acc;
  }, {});
  return { selected, ownerCounts };
}
