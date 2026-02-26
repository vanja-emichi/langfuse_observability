/**
 * Injects per-chat fork buttons into the sidebar chat list items.
 * Each chat <li> gets a fork icon next to the close (×) button.
 */

const INJECTED_CLASS = "lf-fork-injected";
let observer = null;

export function setup() {
  const trySetup = () => {
    // Look for the chat list container in the sidebar
    const container = findChatListContainer();
    if (container) {
      injectAll(container);
      observer = new MutationObserver(() => injectAll(container));
      observer.observe(container, { childList: true, subtree: true });
    } else {
      // Retry until the sidebar is rendered
      setTimeout(trySetup, 1000);
    }
  };
  trySetup();
}

function findChatListContainer() {
  // The chat list is typically in #chats-section or a .chats-list-container
  const candidates = [
    document.getElementById("chats-section"),
    document.querySelector(".chats-list-container"),
    document.querySelector(".chats-list"),
  ];
  for (const el of candidates) {
    if (el && el.querySelectorAll("li").length > 0) return el;
  }
  // Fallback: look for any sidebar element with <li> children
  const sidebar = document.querySelector(
    '.sidebar, [class*="sidebar"], nav, aside',
  );
  if (sidebar && sidebar.querySelectorAll("li").length > 0) return sidebar;
  return null;
}

function injectAll(container) {
  const chatsStore = window.Alpine?.store("chats");
  if (!chatsStore?.list) return;
  const chatList = chatsStore.list;

  // Find all <li> items not yet injected
  const items = container.querySelectorAll("li:not(." + INJECTED_CLASS + ")");
  let chatIndex = 0;

  items.forEach((li) => {
    // Skip <li> that don't look like chat items (no text content, nested in other components)
    if (!li.textContent.trim()) return;

    const chat = chatList[chatIndex];
    if (!chat) return;
    chatIndex++;

    li.classList.add(INJECTED_CLASS);
    injectButton(li, chat.id);
  });
}

function injectButton(li, contextId) {
  const btn = document.createElement("button");
  btn.className = "lf-fork-icon";
  btn.title = "Fork this chat";
  const icon = document.createElement("span");
  icon.className = "material-symbols-outlined";
  icon.textContent = "call_split";
  btn.appendChild(icon);

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    e.preventDefault();
    const forkStore = window.Alpine?.store("forkActions");
    if (forkStore) forkStore.forkChat(contextId);
  });

  // Insert before the close (×) button if it exists, otherwise append
  const closeBtn = li.querySelector(
    'button:last-of-type, [class*="close"], [class*="delete"]',
  );
  if (closeBtn) {
    closeBtn.parentNode.insertBefore(btn, closeBtn);
  } else {
    li.appendChild(btn);
  }
}
