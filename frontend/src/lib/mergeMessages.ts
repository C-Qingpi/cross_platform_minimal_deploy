import type { Message } from "../types/api";

export interface MessagePage {
  messages: Message[];
  start_index: number;
  total: number;
}

export const DEFAULT_NUM_PAGES = 3;

/** Merge a fresh tail page into currently-loaded messages.
 *
 *  When the user is near the live tail (no older pages loaded), we
 *  simply replace with the fresh tail. Otherwise we keep the current
 *  window unchanged — loadOlder will handle extending it.
 */
export function mergeTailIntoWindow(
  loaded: Message[],
  page: MessagePage,
): Message[] {
  // If loaded window is same or longer, keep it (user may have loaded older pages)
  if (loaded.length >= page.messages.length) {
    return loaded;
  }
  return page.messages;
}

export function syncLiveTailPage(
  loaded: Message[],
  headIndex: number,
  page: MessagePage,
): Message[] {
  const { messages: tail, start_index: tailStart } = page;
  const offsetInPage = headIndex - tailStart;

  if (offsetInPage >= 0) {
    return tail.slice(offsetInPage);
  }

  const keepFromPrev = tailStart - headIndex;
  return [...loaded.slice(0, keepFromPrev), ...tail];
}

export function wasAtLiveTail(headIndex: number, loadedCount: number, total: number): boolean {
  return loadedCount === 0 || headIndex + loadedCount >= total;
}
