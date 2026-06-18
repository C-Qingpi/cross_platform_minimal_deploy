import type { Message } from "../types/api";

export interface MessagePage {
  messages: Message[];
  start_index: number;
  total: number;
}

/** Sync loaded messages with a fresh tail page when user is at the live edge. */
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
