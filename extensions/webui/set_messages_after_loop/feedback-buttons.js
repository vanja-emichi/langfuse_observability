/**
 * Langfuse user feedback — thumbs up/down on assistant responses.
 *
 * Loaded automatically by A0's extension system via the
 * `set_messages_after_loop` JS extension point.
 *
 * Uses the unified handler output: context.results[] = { args, result }
 * and sends assistant log identity (log no + message id) so the backend can
 * resolve the correct trace server-side without exposing raw trace ids.
 */

import { callJsonApi } from "/js/api.js";

const FEEDBACK_API = "/plugins/a0_langfuse/langfuse_feedback";

export default async function injectFeedbackButtons(context) {
  if (!context?.results?.length) return;

  const responseEntries = context.results.filter(
    (entry) => entry?.args?.type === "response" && entry?.result?.element,
  );
  const fallbackEntry = [...context.results].reverse().find(
    (entry) => entry?.args?.type === "agent" && entry?.result?.element,
  );
  const targetEntries = responseEntries.length ? responseEntries : (fallbackEntry ? [fallbackEntry] : []);

  for (const entry of targetEntries) {
    const logNo = entry.args?.no ?? "";
    const messageId = entry.args?.id ?? "";
    for (const bar of entry.result.element.querySelectorAll(".step-action-buttons")) {
      if (bar.querySelector(".lf-feedback-up")) continue;

      const divider = document.createElement("span");
      divider.className = "lf-feedback-divider";
      divider.style.cssText =
        "width:1px;height:18px;" +
        "background:var(--border-color,rgba(128,128,128,0.2));" +
        "margin:0 2px;display:inline-block;align-self:center;flex-shrink:0;";
      bar.appendChild(divider);

      bar.appendChild(createFeedbackButton("up", 1, logNo, messageId));
      bar.appendChild(createFeedbackButton("down", 0, logNo, messageId));
    }
  }
}

function createFeedbackButton(type, score, logNo, messageId) {
  const icon = type === "up" ? "thumb_up" : "thumb_down";
  const label = type === "up" ? "Good response" : "Bad response";

  const button = document.createElement("button");
  button.type = "button";
  button.className = `action-button lf-feedback-${type}`;
  button.setAttribute("aria-label", label);
  button.setAttribute("title", label);
  button.innerHTML = `<span class="material-symbols-outlined">${icon}</span>`;

  button.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (button.disabled) return;

    const ctxid = typeof globalThis.getContext === "function"
      ? globalThis.getContext() || ""
      : "";
    if (!ctxid) {
      console.warn("Langfuse feedback: no context ID available");
      return;
    }

    const container = button.closest(".step-action-buttons");
    const upBtn = container?.querySelector(".lf-feedback-up");
    const downBtn = container?.querySelector(".lf-feedback-down");
    if (upBtn) upBtn.disabled = true;
    if (downBtn) downBtn.disabled = true;

    const iconEl = button.querySelector(".material-symbols-outlined");
    const originalIcon = iconEl.textContent;
    iconEl.textContent = "hourglass_top";

    try {
      await callJsonApi(FEEDBACK_API, {
        context_id: ctxid,
        score,
        comment: "",
        log_no: logNo,
        message_id: messageId,
      });

      iconEl.textContent = originalIcon;
      button.classList.add(score === 1 ? "success" : "error");
    } catch (err) {
      console.error("Langfuse feedback failed:", err);
      iconEl.textContent = originalIcon;
      if (upBtn) upBtn.disabled = false;
      if (downBtn) downBtn.disabled = false;
      button.classList.add("error");
      setTimeout(() => button.classList.remove("error"), 1000);
    }
  });

  return button;
}
