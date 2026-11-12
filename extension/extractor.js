// Self-contained: Chrome serializes this function into an isolated execution world.
export function extractVisiblePage() {
  const language = document.documentElement.lang?.split("-")[0]?.toLowerCase();
  if (language && language !== "en") throw new Error("The first release supports English pages.");
  if (document.querySelector('input[type="password"], [contenteditable="true"]')) {
    throw new Error("Pages with passwords or editable content are excluded.");
  }
  const root = document.querySelector("article") || document.querySelector("main") || document.body;
  let text = "";
  let inspected = 0;
  for (const node of root.querySelectorAll("h1, h2, h3, p, li")) {
    if (++inspected > 500 || text.length >= 30000) break;
    if (node.closest("nav, header, footer, aside, form, [hidden], [aria-hidden='true'], [contenteditable]")) continue;
    if (!node.getClientRects().length) continue;
    const style = getComputedStyle(node);
    if (style.visibility === "hidden" || style.display === "none") continue;
    text += " " + node.innerText;
  }
  return {url: location.href, title: document.title, text: text.slice(0, 30000)};
}
