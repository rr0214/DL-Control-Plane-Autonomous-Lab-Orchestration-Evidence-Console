// Keyboard focus helpers. After an action removes the focused button (opening a form, deciding, cancelling), focus would
// fall back to the page top; these move it somewhere sensible instead. Runs after React has re-rendered.
export function focusById(id: string): void {
  requestAnimationFrame(() => requestAnimationFrame(() => document.getElementById(id)?.focus()));
}

export const REVIEW_DETAIL_ID = "review-detail";
export const EXPERIMENT_DETAIL_ID = "experiment-detail";

// A click with detail 0 came from the keyboard (Enter or Space on a button), not from a mouse.
export const fromKeyboard = (e: React.MouseEvent) => e.detail === 0;
