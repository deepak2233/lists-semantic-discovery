import {contextFromText} from "./nlp.js";
import {apiBase, publicPageUrl} from "./safety.js";
import {extractVisiblePage} from "./extractor.js";

const $ = id => document.getElementById(id);
let context;
let sourceTabId;
let destination;

$("settings").addEventListener("click", () => chrome.runtime.openOptionsPage());
$("prepare").addEventListener("click", async () => {
  $("status").textContent = "Reading the visible article on this device…";
  $("prepare").disabled = true;
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    if (!tab?.id || tab.incognito) throw new Error("Private browsing is excluded.");
    const url = publicPageUrl(tab.url);
    const [{result}] = await chrome.scripting.executeScript({
      target: {tabId: tab.id}, func: extractVisiblePage,
    });
    // An SPA or navigation may have changed the page during extraction.
    if (publicPageUrl(result.url) !== url) throw new Error("The page changed. Open LISTS again.");
    const settings = await chrome.storage.local.get({apiUrl: "http://127.0.0.1:8000"});
    destination = apiBase(settings.apiUrl);
    context = {...contextFromText(result.text, result.title), page_url: url};
    sourceTabId = tab.id;
    $("title").value = context.title;
    $("summary").value = context.summary;
    $("keywords").textContent = context.keywords.join(" · ");
    $("disclosure").textContent = `Send this title, excerpt, topic words and page address to ${destination}. ` +
      "In live mode, topic words also go to the search provider. Remove private details first. " +
      "Automatic redaction is incomplete.";
    $("preview").hidden = false;
    $("prepare").hidden = true;
    $("status").textContent = "Nothing has been sent. Review the excerpt, then find related pages.";
  } catch (error) {
    $("status").textContent = error.message || "This page could not be read.";
  } finally {
    $("prepare").disabled = false;
  }
});

$("send").addEventListener("click", async () => {
  if (!context) return;
  $("send").disabled = true;
  $("status").textContent = "Finding related pages…";
  $("results").replaceChildren();
  $("mode").hidden = true;
  try {
    const tab = await chrome.tabs.get(sourceTabId);
    if (publicPageUrl(tab.url) !== context.page_url) throw new Error("The page changed. Open LISTS again.");
    // Regenerate keywords from the edited preview. Never send the original, unedited keywords.
    const edited = contextFromText($("summary").value, $("title").value);
    const {accessToken, tokenOrigin} = await chrome.storage.session.get(["accessToken", "tokenOrigin"]);
    const response = await fetch(`${destination}/v1/recommend`, {
      method: "POST", headers: {"Content-Type": "application/json",
        ...(accessToken && tokenOrigin === destination ? {Authorization: `Bearer ${accessToken}`} : {})},
      body: JSON.stringify({...edited, page_url: context.page_url,
        exclude_same_host: $("samehost").checked, limit: 10, language: "en"}),
      signal: AbortSignal.timeout(12000), credentials: "omit", redirect: "error",
    });
    if (!response.ok) {
      const messages = {401: "Your session token is missing or expired. Update it in Settings.",
        403: "This extension is not allowed by the server.",
        429: "Request limit reached. Try again in a minute.",
        503: "Search is temporarily unavailable. Try again shortly.",
        422: "The preview is too short or invalid. Check its title and excerpt."};
      throw new Error(messages[response.status] || `Server returned ${response.status}.`);
    }
    const data = await response.json();
    $("mode").hidden = false;
    $("mode").textContent = `${data.mode === "demo" ? "DEMO CORPUS" : "LIVE WEB"} · ${data.ranker}`;
    for (const [index, item] of data.recommendations.entries()) {
      let url;
      try {url = publicPageUrl(item.url);} catch {continue;}
      // Preserve safe provider query strings for meaningful result navigation.
      const safeTarget = new URL(item.url);
      if (new URL(url).origin !== safeTarget.origin) continue;
      const li = document.createElement("li");
      const number = document.createElement("span");
      number.className = "number"; number.textContent = String(index + 1).padStart(2, "0");
      const body = document.createElement("div");
      const host = document.createElement("small"); host.textContent = item.host;
      const link = document.createElement("a"); link.href = safeTarget.href;
      link.target = "_blank"; link.rel = "noopener noreferrer"; link.textContent = item.title;
      const snippet = document.createElement("p"); snippet.textContent = item.snippet;
      const reason = document.createElement("small"); reason.textContent = item.reason;
      body.append(host, link, snippet, reason); li.append(number, body); $("results").append(li);
    }
    $("status").textContent = `${data.recommendations.length} related pages. ` + data.warnings.join(" ");
  } catch (error) {
    $("status").textContent = error.name === "TimeoutError" ? "The request timed out. Try again." :
      error.message === "Failed to fetch" ? "Cannot reach the API. Check Settings and start the backend." :
      error.message;
  } finally {
    $("send").disabled = false;
  }
});
