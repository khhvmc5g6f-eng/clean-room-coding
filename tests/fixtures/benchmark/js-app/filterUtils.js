// SPDX-License-Identifier: GPL-3.0-only
// Synthetic benchmark fixture -- wholly owned by this project.
function filterActiveWidgets(widgets, minPriority) {
  const kept = [];
  for (const widget of widgets) {
    if (widget.active && widget.priority >= minPriority) {
      kept.push(widget);
    }
  }
  return kept;
}

function summarizeByOwner(widgets) {
  const counts = {};
  for (const widget of widgets) {
    counts[widget.owner] = (counts[widget.owner] || 0) + 1;
  }
  return counts;
}
