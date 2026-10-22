// Presentation only. Never controls scoring, admission or notifications.
export function alertQualityLabel(q) {
  if(q?.disposition==='defer')return 'Research only: shadow defer. Entry conditions are not qualified.';
  if(q?.disposition==='retain')return 'Research only: shadow retain. Execution and safety are not verified.';
  return 'Research only: qualification unavailable. Execution and safety are not verified.';
}
