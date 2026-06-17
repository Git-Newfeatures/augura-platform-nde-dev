// Search groups for the ⌘K overlay. There is no backend search endpoint yet, so
// this returns no results (the overlay shows its empty state). Wire a real search
// source here when one exists; each item is { icon, title, sub, to }.
export function getSearchGroups() {
  return []
}
