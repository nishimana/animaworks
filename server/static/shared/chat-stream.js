// ── Shared Chat Stream ──────────────────────────────────
// Common SSE chat streaming logic used across all chat modules.
// Extracts the duplicated fetch + ReadableStream + SSE parse loop
// into a single reusable function with callback-based UI injection.

import { parseConvSSE, getErrorMessage } from "./sse-parser.js";

/**
 * SSE chat stream processor.
 *
 * Handles the full lifecycle: fetch -> ReadableStream -> SSE parse -> callbacks.
 * UI-specific logic (bubble updates, Live2D expressions, state management)
 * is injected via the callbacks parameter.
 *
 * @param {string} animaName - Target Anima name
 * @param {string|FormData} body - Request body (JSON string or FormData)
 * @param {AbortSignal|null} signal - Optional AbortSignal for cancellation
 * @param {object} callbacks - Event callbacks
 * @param {function(string): void} [callbacks.onTextDelta] - Text delta received
 * @param {function(string): void} [callbacks.onToolStart] - Tool execution started (tool name)
 * @param {function(): void} [callbacks.onToolEnd] - Tool execution ended
 * @param {function({summary: string, emotion: string}): void} [callbacks.onDone] - Stream completed
 * @param {function({message: string}): void} [callbacks.onError] - SSE error event received
 * @param {function(object): void} [callbacks.onBootstrap] - Bootstrap event (data object)
 * @param {function(): void} [callbacks.onChainStart] - Chain continuation event
 * @returns {Promise<void>}
 * @throws {Error} On HTTP error (non-ok response) or network failure
 */
export async function streamChat(animaName, body, signal, callbacks) {
  const url = `/api/animas/${encodeURIComponent(animaName)}/chat/stream`;
  // TODO: Replace console.* with logger.info() when shared/logger.js is available
  const start = performance.now();
  console.info(`[chat-stream] Stream start: ${animaName}`);

  const headers = body instanceof FormData ? {} : { "Content-Type": "application/json" };

  const res = await fetch(url, {
    method: "POST",
    headers,
    body,
    ...(signal ? { signal } : {}),
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    // TODO: Replace with logger.error() when shared/logger.js is available
    console.error(`[chat-stream] Stream failed: ${res.status} ${text}`);
    throw new Error(`API ${res.status}: ${text}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const { parsed, remaining } = parseConvSSE(buffer);
      buffer = remaining;

      for (const { event, data } of parsed) {
        switch (event) {
          case "text_delta":
            callbacks.onTextDelta?.(data.text || "");
            break;

          case "tool_start":
            callbacks.onToolStart?.(data.tool_name);
            break;

          case "tool_end":
            callbacks.onToolEnd?.();
            break;

          case "done":
            callbacks.onDone?.({
              summary: data.summary || null,
              emotion: data.emotion || "neutral",
            });
            break;

          case "error":
            callbacks.onError?.({ message: getErrorMessage(data) });
            break;

          case "bootstrap":
            callbacks.onBootstrap?.(data);
            break;

          case "chain_start":
            callbacks.onChainStart?.();
            break;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }

  const elapsed = ((performance.now() - start) / 1000).toFixed(1);
  // TODO: Replace with logger.info() when shared/logger.js is available
  console.info(`[chat-stream] Stream complete: ${animaName} (${elapsed}s)`);
}
