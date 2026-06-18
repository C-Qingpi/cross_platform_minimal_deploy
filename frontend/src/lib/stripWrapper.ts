/** Strip the backend-applied wrapper (timestamp + workflow) from user messages. */

const END_USER_MESSAGE = "\n--- END OF USER MESSAGE ---";

/**
 * Strip the wrapper that `wrap_user_message` adds to every user message.
 *
 * Input:  "2026-06-19-(Thursday)-CST-14-30-00 RECEIVED FROM USER: hello\n--- END OF USER MESSAGE ---\n<workflow>..."
 * Output: "hello"
 *
 * If the content doesn't contain the wrapper, returns it unchanged
 * (safe for messages that bypass wrapping or come from older versions).
 */
export function stripUserMessageWrapper(content: string): string {
  if (typeof content !== "string") return content;

  // Find the start of the actual user message (after "RECEIVED FROM USER: ")
  const prefix = "RECEIVED FROM USER: ";
  const userIdx = content.indexOf(prefix);
  if (userIdx === -1) return content; // not wrapped — return as-is

  const afterPrefix = content.slice(userIdx + prefix.length);

  // Find the END OF USER MESSAGE delimiter
  const endIdx = afterPrefix.indexOf(END_USER_MESSAGE);
  if (endIdx !== -1) {
    return afterPrefix.slice(0, endIdx);
  }

  // Fallback: no delimiter found, return everything after the prefix
  return afterPrefix;
}
