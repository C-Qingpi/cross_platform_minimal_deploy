/** Short label for model badge; full spec in title attribute. */
export function modelLabel(model: string): string {
  const colon = model.lastIndexOf(":");
  return colon >= 0 ? model.slice(colon + 1) : model;
}
