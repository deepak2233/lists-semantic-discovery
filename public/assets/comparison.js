import {redact} from "./nlp.js";

export function initComparison({document, fetch, timeoutMs = 20000}) {
  const $ = id => document.getElementById(id);
  if (!$("comparison-form")) return {ready: Promise.resolve(), destroy() {}};
  let controller = null;
  let serial = 0;
  let active = true;
  const status = (message, error = false) => {
    $("comparison-status").textContent = message;
    $("comparison-status").classList.toggle("error", error);
  };
  const stop = () => {
    serial += 1;
    controller?.abort(); controller = null;
    $("compare-run").disabled = false;
    $("compare-cancel").hidden = true;
  };
  function example(related) {
    stop();
    $("compare-a").value = "An engineer adds request deadlines and retries to a Python service.";
    $("compare-b").value = related ?
      "A developer configures timeouts and retry handling for an application server." :
      "A baker prepares a loaf of bread using flour, water and yeast.";
    $("comparison-results").hidden = true;
    status("Example loaded. Review both passages, then compare.");
  }
  async function run(event) {
    event.preventDefault(); stop();
    const id = serial;
    $("comparison-results").hidden = true;
    let timer;
    let timedOut = false;
    try {
      const body = {text_a: redact($("compare-a").value).replace(/\s+/g, " ").trim(),
        text_b: redact($("compare-b").value).replace(/\s+/g, " ").trim()};
      if (Object.values(body).some(s => s.length < 3 || s.length > 1800)) {
        throw new Error("Each passage must contain between 3 and 1,800 characters.");
      }
      controller = new AbortController();
      const current = controller;
      timer = setTimeout(() => {timedOut = true; current.abort();}, timeoutMs);
      $("compare-run").disabled = true; $("compare-cancel").hidden = false;
      status("Running both models on your reviewed passages…");
      const token = $("access-token")?.value.trim();
      const response = await fetch("/v1/compare", {method: "POST", credentials: "same-origin",
        redirect: "error", signal: current.signal,
        headers: {"Content-Type": "application/json", ...(token ? {Authorization: `Bearer ${token}`} : {})},
        body: JSON.stringify(body)});
      if (id !== serial || !active) return;
      if (!response.ok) {
        const messages = {401: "Update the protected API session before comparing.",
          403: "This website is not an allowed API origin.",
          409: "The trained checkpoint is not available on this server yet.",
          422: "Review both passages; their content did not pass validation.",
          429: "The request limit was reached. Wait a minute and try again.",
          503: "Model inference is temporarily unavailable. Try again shortly."};
        if (response.status === 401 && $("session-options")) {
          $("session-options").hidden = false; $("session-options").open = true;
        }
        throw new Error(messages[response.status] || `The server returned HTTP ${response.status}.`);
      }
      const data = await response.json();
      if (id !== serial || !active) return;
      if (![data.baseline_cosine, data.fine_tuned_cosine].every(n => Number.isFinite(n) && n >= -1 && n <= 1) ||
          typeof data.request_id !== "string" || typeof data.fine_tuned_model !== "string" ||
          !data.fine_tuned_model.includes("snli-lora")) throw new Error("The server returned invalid model evidence.");
      $("baseline-cosine").textContent = data.baseline_cosine.toFixed(3);
      $("adapted-cosine").textContent = data.fine_tuned_cosine.toFixed(3);
      $("comparison-json").textContent = JSON.stringify(data, null, 2);
      $("comparison-results").hidden = false;
      status(`Both models completed. Request ${data.request_id.slice(0, 8)}.`);
    } catch (error) {
      if (id !== serial || !active) return;
      if (error.name === "AbortError" && !timedOut) return;
      status(timedOut ? "The comparison timed out. Please retry." :
        error instanceof TypeError ? "The inference service could not be reached." : error.message, true);
    } finally {
      clearTimeout(timer);
      if (id === serial && active) {$("compare-run").disabled = false; $("compare-cancel").hidden = true; controller = null;}
    }
  }
  $("comparison-form").addEventListener("submit", run);
  $("compare-related").addEventListener("click", () => example(true));
  $("compare-different").addEventListener("click", () => example(false));
  $("compare-cancel").addEventListener("click", () => {stop(); status("Comparison cancelled.");});
  example(true);
  const ready = (async () => {
    try {
      const response = await fetch("/v1/config", {credentials: "same-origin", redirect: "error", signal: AbortSignal.timeout(20000)});
      if (!response.ok) throw new Error("Unavailable");
      const data = await response.json();
      if (!active) return;
      $("comparison-availability").textContent = data.fine_tuned_available ? "Trained checkpoint ready" : "Trained checkpoint unavailable";
    } catch {if (active) $("comparison-availability").textContent = "Check server connection";}
  })();
  return {ready, destroy() {active = false; stop();}};
}
