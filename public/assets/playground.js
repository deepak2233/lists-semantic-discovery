import {contextFromText} from "./nlp.js";
import {publicPageUrl} from "./safety.js";

export const EXAMPLES = {
  hybrid: {
    title: "Hybrid search: connecting words and meaning",
    excerpt: "A search application retrieves candidate documents using BM25 lexical search and sentence embeddings. Reciprocal rank fusion combines lexical and dense retrieval rankings without assuming their scores share a scale. A cross encoder can rerank the candidate passages for relevance. Diversity selection reduces repetitive pages and makes room for different sources.",
    url: "https://reader.example.org/articles/hybrid-search",
  },
  kafka: {
    title: "Reliable Kafka consumers and duplicate event handling",
    excerpt: "An at least once Kafka consumer can receive the same event again after a retry or restart. Idempotency keys and database unique constraints help avoid applying business effects twice. Kafka transactions solve specific producer and consumer boundaries, while downstream side effects need their own duplicate handling. How should we design a reliable message processing pipeline?",
    url: "https://reader.example.org/articles/kafka-reliability",
  },
  chrome: {
    title: "Chrome extensions with narrow page permissions",
    excerpt: "A Manifest V3 browser extension can read a public article after the user clicks its action. The activeTab permission and scripting API avoid installing a permanent reader on every website. Local storage holds settings while session storage holds temporary access tokens. A useful extension should explain what it shares and render untrusted search results as plain text.",
    url: "https://reader.example.org/articles/browser-extensions",
  },
};

export function validateResponse(data) {
  if (!data || !["demo", "live"].includes(data.mode) || typeof data.ranker !== "string" ||
      !Array.isArray(data.recommendations) || data.recommendations.length > 10 ||
      !Array.isArray(data.warnings) || !data.warnings.every(w => typeof w === "string") ||
      typeof data.request_id !== "string" || typeof data.elapsed_ms !== "number" ||
      !Number.isFinite(data.elapsed_ms) || !Number.isInteger(data.candidate_count)) {
    throw new Error("The server returned an unexpected response. No results were displayed.");
  }
  for (const item of data.recommendations) {
    if (!["url", "title", "snippet", "host", "reason"].every(key => typeof item[key] === "string") ||
        typeof item.ranking_score !== "number" || !Number.isFinite(item.ranking_score) ||
        item.ranking_score < 0 || item.ranking_score > 1) {
      throw new Error("A recommendation has an invalid shape. No results were displayed.");
    }
  }
  return data;
}

export function initPlayground({document, fetch, clipboard, timeoutMs = 20000}) {
  const $ = id => document.getElementById(id);
  let controller = null;
  let serial = 0;
  let active = true;
  let lastRequest = null;
  let lastResponse = null;
  let configuration = null;
  let hasInference = false;

  const show = (id, visible) => {$(id).hidden = !visible;};
  const status = text => {$("status").textContent = text;};
  function count() {$("character-count").textContent = `${$("excerpt").value.length.toLocaleString()} / 1,800`;}
  function busy(value) {
    $("run").disabled = value;
    $("run-text").textContent = value ? "Finding your next read…" : "Discover related pages";
    $("inference-form").setAttribute("aria-busy", String(value));
    show("cancel", value);
    show("loading", value);
  }
  function clearOutput() {
    $("results").replaceChildren();
    for (const id of ["error", "summary-bar", "warnings", "result-badge", "no-results", "result-note"]) show(id, false);
  }
  function stop(message = "Request cancelled. Your context is ready to edit.") {
    serial += 1;
    controller?.abort();
    controller = null;
    busy(false);
    status(message);
  }
  function example(key) {
    stop("Example loaded. Review the context, then discover related pages.");
    const data = EXAMPLES[key];
    $("page-title").value = data.title;
    $("excerpt").value = data.excerpt;
    $("page-url").value = data.url;
    for (const button of document.querySelectorAll("[data-example]")) button.classList.toggle("active", button.dataset.example === key);
    count();
    clearOutput();
    show("empty-state", true);
  }

  function tab(which) {
    const results = which === "recommendations";
    show("recommendations-view", results);
    show("inspection-view", !results);
    for (const [name, enabled] of [["recommendations", results], ["inspection", !results]]) {
      const button = $(`${name}-tab`);
      button.classList.toggle("active", enabled);
      button.setAttribute("aria-selected", String(enabled));
      button.tabIndex = enabled ? 0 : -1;
    }
  }

  function render(data) {
    hasInference = true;
    $("connection").classList.remove("offline");
    $("connection-text").textContent = "Inference online";
    if (!configuration) {
      $("mode-text").textContent = `${data.mode === "demo" ? "Demo corpus" : "Live web"} · ${data.ranker.includes("minilm") ? "Semantic" : "Lexical"}`;
    }
    const list = $("results");
    list.replaceChildren();
    let displayed = 0;
    const hosts = new Set();
    const seen = new Set();
    for (const item of data.recommendations) {
      let linkUrl;
      try {
        publicPageUrl(item.url);
        linkUrl = new URL(item.url);
      } catch {continue;}
      if (seen.has(linkUrl.href)) continue;
      seen.add(linkUrl.href);
      hosts.add(linkUrl.hostname);
      displayed += 1;
      const row = document.createElement("li"); row.className = "result-card";
      const number = document.createElement("span"); number.className = "result-number";
      number.textContent = String(displayed).padStart(2, "0");
      const body = document.createElement("article");
      const meta = document.createElement("div"); meta.className = "result-meta";
      const host = document.createElement("span"); host.className = "result-host";
      host.textContent = linkUrl.hostname.replace(/^www\./, "");
      const score = document.createElement("span"); score.className = "result-score";
      score.textContent = `${item.ranking_score.toFixed(3)} · relative rank`;
      score.title = "Normalized fused ranking score for this request. Not a probability.";
      meta.append(host, score);
      const title = document.createElement("h4");
      const link = document.createElement("a"); link.href = linkUrl.href;
      link.target = "_blank"; link.rel = "noopener noreferrer";
      link.textContent = item.title + " ";
      const arrow = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      arrow.setAttribute("class", "external-arrow"); arrow.setAttribute("viewBox", "0 0 24 24");
      arrow.setAttribute("aria-hidden", "true");
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("d", "M6 18 18 6M6 6h12v12"); arrow.append(path);
      link.append(arrow); title.append(link);
      const snippet = document.createElement("p"); snippet.className = "result-snippet";
      snippet.textContent = item.snippet;
      const bottom = document.createElement("div"); bottom.className = "result-bottom";
      const reason = document.createElement("span"); reason.className = "reason-tag"; reason.textContent = item.reason;
      const detail = document.createElement("span"); detail.className = "score-detail";
      const parts = [];
      if (Number.isFinite(item.lexical_score)) parts.push(`BM25 ${item.lexical_score.toFixed(2)}`);
      if (Number.isFinite(item.semantic_similarity)) parts.push(`cosine ${item.semantic_similarity.toFixed(3)}`);
      detail.textContent = parts.join(" · ");
      bottom.append(reason, detail); body.append(meta, title, snippet, bottom); row.append(number, body); list.append(row);
    }
    $("result-badge").textContent = String(displayed);
    $("candidate-count").textContent = String(data.candidate_count);
    $("source-count").textContent = String(hosts.size);
    $("elapsed").textContent = Math.round(data.elapsed_ms).toLocaleString();
    $("actual-ranker").textContent = data.ranker.includes("snli-lora") ? "Fine-tuned · SNLI" : data.ranker.includes("minilm") ? "Pretrained · MiniLM" : "Lexical baseline";
    for (const id of ["summary-bar", "result-badge"]) show(id, true);
    show("empty-state", false); show("result-note", displayed > 0); show("no-results", displayed === 0);
    $("warnings").replaceChildren();
    for (const warning of data.warnings) {
      const p = document.createElement("p"); p.textContent = warning; $("warnings").append(p);
    }
    show("warnings", data.warnings.length > 0);
    status(`${displayed} related ${displayed === 1 ? "page" : "pages"} from ${hosts.size} ${hosts.size === 1 ? "source" : "sources"}. Request ${data.request_id.slice(0, 8)}.`);
  }

  async function run(event) {
    event?.preventDefault();
    stop("");
    const runId = serial;
    clearOutput();
    let timer = null;
    let timedOut = false;
    try {
      const title = $("page-title").value.trim();
      const excerpt = $("excerpt").value.trim();
      if (title.length < 3 || title.length > 300) throw new Error("Add an article title between 3 and 300 characters.");
      if (excerpt.length < 40 || excerpt.length > 1800) throw new Error("Use an excerpt between 40 and 1,800 characters.");
      const context = contextFromText(excerpt, title);
      const url = $("page-url").value.trim();
      const payload = {...context, page_url: url ? publicPageUrl(url) : "https://reader.example.org/reviewed-context",
        ranking: $("ranking-mode").value, limit: Number($("result-limit").value),
        exclude_same_host: $("other-sites").checked, language: "en"};
      if (payload.ranking === "semantic" && configuration?.semantic_available === false) {
        throw new Error("This server has no semantic model. Choose the lexical baseline or automatic mode.");
      }
      if (payload.ranking === "fine_tuned" && configuration?.fine_tuned_available === false) {
        throw new Error("The trained checkpoint is unavailable on this server. Choose the pretrained model.");
      }
      lastRequest = payload; lastResponse = null;
      $("request-json").textContent = JSON.stringify(payload, null, 2);
      $("response-json").textContent = "Waiting for the actual server response…";
      controller = new AbortController();
      const requestController = controller;
      timer = setTimeout(() => {timedOut = true; requestController.abort();}, timeoutMs);
      busy(true); show("empty-state", false);
      status("Retrieving and ranking candidates. Scores will come from the server.");
      let response;
      try {
        const token = $("access-token").value.trim();
        response = await fetch("/v1/recommend", {method: "POST", headers: {"Content-Type": "application/json",
          ...(token ? {Authorization: `Bearer ${token}`} : {})}, body: JSON.stringify(payload),
          credentials: "same-origin", redirect: "error", signal: requestController.signal});
      } catch (error) {
        if (timedOut) throw new Error("The request timed out. Please try again in a moment.");
        throw error;
      }
      if (runId !== serial || !active) return;
      if (!response.ok) {
        if (response.status === 401) show("session-options", true);
        const messages = {401: "Your access token is missing or expired. Update the protected API session.",
          403: "This website is not in the server’s allowed origins.",
          409: "Semantic ranking is not configured on this server. Choose automatic or lexical mode.",
          413: "The request was too large. Reduce the excerpt.",
          422: "The title, excerpt or page address did not pass validation. Review the context.",
          429: "The request limit was reached. Wait a minute before trying again.",
          503: "Search, ranking or identity is temporarily unavailable. Try again shortly."};
        lastResponse = {status: response.status, request_id: response.headers?.get("X-Request-ID") || null};
        $("response-json").textContent = JSON.stringify(lastResponse, null, 2);
        throw new Error(messages[response.status] || `The server returned HTTP ${response.status}. Try again shortly.`);
      }
      const data = validateResponse(await response.json());
      if (runId !== serial || !active) return;
      lastResponse = data;
      $("response-json").textContent = JSON.stringify(data, null, 2);
      render(data);
    } catch (error) {
      if (runId !== serial || !active) return;
      if (error.name === "AbortError" && !timedOut) {status("Request cancelled. Your context is ready to edit.");return;}
      $("error-message").textContent = error instanceof SyntaxError ? "The server returned unreadable JSON. No results were displayed." :
        timedOut ? "The request timed out. Please try again in a moment." :
        error instanceof TypeError ? "The inference server could not be reached. Check your connection and try again." : error.message;
      if (lastRequest && !lastResponse) {
        lastResponse = {error: timedOut ? "request_timeout" : "response_unavailable"};
        $("response-json").textContent = JSON.stringify(lastResponse, null, 2);
      }
      show("error", true); show("empty-state", true);
      status("No recommendations displayed. Check the message above.");
    } finally {
      clearTimeout(timer);
      if (runId === serial && active) {busy(false); controller = null;}
    }
  }

  async function copy(which) {
    const data = which === "request" ? lastRequest : lastResponse;
    if (!data) {status("Run an inference first, then copy its data.");return;}
    try {await clipboard.writeText(JSON.stringify(data, null, 2));status(`${which === "request" ? "Request" : "Response"} copied.`);}
    catch {status("Clipboard access is unavailable. Select and copy the JSON manually.");}
  }

  $("inference-form").addEventListener("submit", run);
  $("excerpt").addEventListener("input", count);
  $("retry").addEventListener("click", run);
  $("cancel").addEventListener("click", () => stop());
  $("reset").addEventListener("click", () => {
    stop("Context cleared. Add a public excerpt or choose an example.");
    $("inference-form").reset(); clearOutput(); count(); show("empty-state", true);
    $("access-token").value = "";
    for (const button of document.querySelectorAll("[data-example]")) button.classList.remove("active");
    $("request-json").textContent = "Run an inference to inspect the exact request.";
    $("response-json").textContent = "The actual API response will appear here.";
    lastRequest = null; lastResponse = null;
  });
  for (const button of document.querySelectorAll("[data-example]")) button.addEventListener("click", () => example(button.dataset.example));
  $("recommendations-tab").addEventListener("click", () => tab("recommendations"));
  $("inspection-tab").addEventListener("click", () => tab("inspection"));
  for (const button of document.querySelectorAll('[role="tab"]')) button.addEventListener("keydown", event => {
    if (["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      const target = event.key === "Home" || event.key === "ArrowLeft" ? "recommendations" : "inspection";
      tab(target); $(`${target}-tab`).focus();
    }
  });
  $("copy-request").addEventListener("click", () => copy("request"));
  $("copy-response").addEventListener("click", () => copy("response"));
  document.addEventListener("keydown", event => {if (event.key === "Escape" && controller) stop();});
  example("hybrid");
  tab("recommendations");
  status("Ready when you are. Your next good read starts here.");
  const ready = (async () => {
    try {
      const response = await fetch("/v1/config", {credentials: "same-origin", redirect: "error",
        signal: AbortSignal.timeout(20000)});
      if (!response.ok) throw new Error("Unavailable");
      const config = await response.json();
      if (!["demo", "live"].includes(config.mode) || typeof config.semantic_available !== "boolean") throw new Error("Invalid configuration");
      if (!active) return;
      configuration = config;
      $("connection-text").textContent = "Inference online";
      $("mode-text").textContent = `${config.mode === "demo" ? "Demo corpus" : "Live web"} · ${config.semantic_available ? "Semantic" : "Lexical"}`;
      $("semantic-option").disabled = !config.semantic_available;
      $("fine-tuned-option").disabled = !config.fine_tuned_available;
      show("session-options", config.authentication_required);
      $("dataset-disclosure").textContent = config.mode === "demo" ?
        `Demo corpus: ${config.corpus_documents} authored technical-resource descriptions. This is real ${config.semantic_available ? "MiniLM + BM25" : "BM25"} ranking over a fixed collection, not live web discovery.` :
        "Live web candidates are retrieved from the configured search provider. Your reviewed context is sent to this server; derived topic queries also go to that provider.";
    } catch {
      if (!active || hasInference) return;
      $("connection").classList.add("offline");
      $("connection-text").textContent = "Connection unavailable";
      $("mode-text").textContent = "Server unavailable";
      status("The inference server is unavailable. You can still prepare your context.");
    }
  })();
  return {ready, destroy() {active = false; serial += 1; controller?.abort();}};
}
