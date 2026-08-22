// SPDX-License-Identifier: GPL-3.0-only
// Synthetic benchmark fixture -- wholly owned by this project (a failed
// clean-room simulation: only names were changed, structure is identical
// to js-app/filterUtils.js).
function keepEnabledItems(items, floorRank) {
  const result = [];
  for (const item of items) {
    if (item.active && item.priority >= floorRank) {
      result.push(item);
    }
  }
  return result;
}

function tallyByOwner(items) {
  const tally = {};
  for (const item of items) {
    tally[item.owner] = (tally[item.owner] || 0) + 1;
  }
  return tally;
}
