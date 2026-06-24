import type { Message } from "../types/api";

export interface MessagePage {
  messages: Message[];
  start_index: number;
  total: number;
}

export const DEFAULT_NUM_PAGES = 3;

/** Merge a fresh tail page into currently-loaded messages.
 *
 *  Compare the tail message IDs — if the tail content changed (new
 *  message at the end), always accept the fresh page.  Otherwise keep
 *  loaded when it has older pages that the fresh tail doesn't include
 *  (loadOlder will handle extending).
 */
export function mergeTailIntoWindow(
  loaded: Message[],
  page: MessagePage,
): Message[] {
  if (!page.messages.length) return loaded;

  const tailLoaded = loaded[loaded.length - 1];
  const tailPage = page.messages[page.messages.length - 1];

  // Tail changed? Always accept the fresh page (new message arrived).
  if (!tailLoaded || tailLoaded.id !== tailPage.id) {
    return page.messages;
  }

  // Same tail — keep loaded if it has older pages the page doesn't.
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
