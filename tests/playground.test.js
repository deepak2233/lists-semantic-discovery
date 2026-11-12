import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {JSDOM} from "jsdom";
import {initPlayground, validateResponse} from "../public/assets/playground.js";

const html = await readFile("public/index.html", "utf8");
const config = {mode: "demo", semantic_available: false, authentication_required: false, corpus_documents: 44};
const item = {url: "https://resource.example.org/search", title: "A useful search reference",
  host: "resource.example.org", snippet: "BM25 and semantic retrieval of related documents.",
  reason: "Shared topics: search", ranking_score: .95, lexical_score: 8.1,
  semantic_similarity: null};
const responseData = overrides => ({mode: "demo", ranker: "bm25-rrf-mmr", request_id: "test-request-123",
  recommendations: [item], warnings: ["Fixed demo corpus, not live web search."],
  elapsed_ms: 25.5, candidate_count: 40, ...overrides});
const response = (data, status = 200) => ({ok: status >= 200 && status < 300, status,
  headers: new Headers({"X-Request-ID": "test-request-123"}), json: async () => data});
const flush = () => new Promise(resolve => setImmediate(resolve));

async function setup(handler = async () => response(responseData()), options = {}) {
  const dom = new JSDOM(html, {url: "https://play.example.org"});
  const calls = [];
  const clipboard = [];
  const app = initPlayground({document: dom.window.document,
    fetch: async (url, init) => {
      calls.push({url, init});
      if (url === "/v1/config") return response(config);
      return handler(url, init);
    }, clipboard: {writeText: async value => clipboard.push(value)}, ...options});
  await app.ready;
  const $ = id => dom.window.document.getElementById(id);
  const submit = () => $("inference-form").dispatchEvent(new dom.window.Event("submit", {cancelable: true}));
  const close = () => {app.destroy(); dom.window.close();};
  return {dom, app, $, calls, submit, close, clipboard};
}

test("page starts with a labeled real mode and never auto-submits an excerpt", async () => {
  const t = await setup();
  assert.equal(t.calls.length, 1);
  assert.equal(t.calls[0].url, "/v1/config");
  assert.match(t.$("mode-text").textContent, /Demo corpus.*Lexical/);
  assert.match(t.$("dataset-disclosure").textContent, /44.*not live web discovery/);
  assert.equal(t.$("semantic-option").disabled, true);
  t.close();
});

test("valid inference displays server scores and inspectable request/response", async () => {
  const t = await setup();
  t.submit(); await flush();
  assert.equal(t.calls.filter(c => c.url === "/v1/recommend").length, 1);
  assert.equal(t.$("results").children.length, 1);
  assert.match(t.$("results").textContent, /0\.950/);
  assert.match(t.$("results").textContent, /BM25 8\.10/);
  assert.equal(t.$("result-badge").textContent, "1");
  assert.equal(JSON.parse(t.$("response-json").textContent).request_id, "test-request-123");
  assert.equal(JSON.parse(t.$("request-json").textContent).limit, 10);
  assert.equal(t.$("run").disabled, false);
  t.close();
});

test("private identifiers and source query strings are removed from sent context", async () => {
  const t = await setup();
  t.$("excerpt").value += " Contact private@example.org about embeddings.";
  t.$("page-url").value = "https://public.example.org/article?token=secret#private";
  t.submit(); await flush();
  const payload = t.calls.find(c => c.url === "/v1/recommend").init.body;
  assert.ok(!payload.includes("private@example.org"));
  assert.ok(!payload.includes("token=secret"));
  t.close();
});

test("short context and private URLs are blocked before network inference", async () => {
  const t = await setup();
  t.$("excerpt").value = "Too short"; t.submit(); await flush();
  assert.match(t.$("error-message").textContent, /40/);
  t.dom.window.document.querySelector('[data-example="hybrid"]').click();
  t.$("page-url").value = "http://127.0.0.1/admin"; t.submit(); await flush();
  assert.equal(t.calls.filter(c => c.url === "/v1/recommend").length, 0);
  t.close();
});

test("hostile result text cannot create executable markup and unsafe links are skipped", async () => {
  const t = await setup(async () => response(responseData({recommendations: [
    {...item, title: '<img src=x onerror="alert(1)">'},
    {...item, url: "javascript:alert(1)"},
  ]})));
  t.submit(); await flush();
  assert.equal(t.dom.window.document.querySelector("#results img"), null);
  assert.equal(t.$("results").children.length, 1);
  assert.match(t.$("results").textContent, /<img/);
  t.close();
});

test("empty candidates produce an honest empty result state", async () => {
  const t = await setup(async () => response(responseData({recommendations: [], candidate_count: 0})));
  t.submit(); await flush();
  assert.equal(t.$("results").children.length, 0);
  assert.equal(t.$("no-results").hidden, false);
  assert.equal(t.$("result-badge").textContent, "0");
  t.close();
});

for (const status of [401, 403, 409, 413, 422, 429, 503]) {
  test(`HTTP ${status} has an explicit error state with no substitute results`, async () => {
    const t = await setup(async () => response({private: "do not render"}, status));
    t.submit(); await flush();
    assert.equal(t.$("error").hidden, false);
    assert.equal(t.$("results").children.length, 0);
    assert.equal(t.$("run").disabled, false);
    assert.ok(!t.$("error-message").textContent.includes("do not render"));
    if (status === 401) assert.equal(t.$("session-options").hidden, false);
    t.close();
  });
}

test("malformed JSON and invalid scores cannot appear as recommendations", async () => {
  const t = await setup(async () => ({ok: true, json: async () => {throw new SyntaxError("bad json");}}));
  t.submit(); await flush();
  assert.match(t.$("error-message").textContent, /unreadable JSON/);
  assert.equal(t.$("results").children.length, 0);
  assert.throws(() => validateResponse(responseData({recommendations: [{...item, ranking_score: NaN}]})));
  t.close();
});

test("switching examples cancels a request and suppresses its late response", async () => {
  let resolveOld;
  const t = await setup(async () => new Promise(resolve => {resolveOld = resolve;}));
  t.submit(); await flush();
  t.dom.window.document.querySelector('[data-example="kafka"]').click();
  resolveOld(response(responseData())); await flush();
  assert.match(t.$("page-title").value, /Kafka/);
  assert.equal(t.$("results").children.length, 0);
  assert.equal(t.$("run").disabled, false);
  t.close();
});

test("deadline covers a stalled response body, not only response headers", async () => {
  const t = await setup(async (url, init) => ({ok: true, json: () => new Promise((resolve, reject) => {
    init.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  })}), {timeoutMs: 20});
  t.submit(); await new Promise(resolve => setTimeout(resolve, 45));
  assert.match(t.$("error-message").textContent, /timed out/);
  assert.equal(t.$("run").disabled, false);
  t.close();
});

test("API inspector is keyboard navigable and copied request never contains a bearer token", async () => {
  const t = await setup();
  t.$("access-token").value = "private-user-token";
  t.submit(); await flush();
  t.$("recommendations-tab").dispatchEvent(new t.dom.window.KeyboardEvent("keydown", {key: "ArrowRight"}));
  assert.equal(t.$("inspection-view").hidden, false);
  assert.equal(t.$("inspection-tab").getAttribute("aria-selected"), "true");
  t.$("copy-request").click(); await flush();
  assert.equal(t.clipboard.length, 1);
  assert.ok(!t.clipboard[0].includes("private-user-token"));
  t.$("reset").click();
  assert.equal(t.$("access-token").value, "");
  assert.equal(t.$("results").children.length, 0);
  t.close();
});
