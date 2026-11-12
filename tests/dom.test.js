import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {JSDOM} from "jsdom";
import {extractVisiblePage} from "../extension/extractor.js";

function installDom(html, url = "https://public.example.org/article") {
  const dom = new JSDOM(html, {url});
  global.document = dom.window.document;
  global.location = dom.window.location;
  global.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);
  // jsdom has no layout engine. Simulate visible boxes and use textContent for innerText.
  dom.window.HTMLElement.prototype.getClientRects = () => [{}];
  Object.defineProperty(dom.window.HTMLElement.prototype, "innerText", {
    get() {return this.textContent;}, configurable: true,
  });
  return dom;
}

test("extractor excludes hidden text and form/navigation content", () => {
  const dom = installDom(`<html lang="en"><head><title>Search article</title></head><body>
    <article><h1>Hybrid search</h1><p>Public text on dense and lexical retrieval.</p>
    <nav><p>Navigation should never be included.</p></nav>
    <form><p>Private form details should never be included.</p></form>
    <div hidden><p>Hidden private text should never be included.</p></div></article></body></html>`);
  const result = extractVisiblePage();
  assert.ok(result.text.includes("Public text"));
  assert.ok(!result.text.includes("never be included"));
  dom.window.close();
});

test("password and editable pages are declined", () => {
  for (const html of ['<input type="password">', '<div contenteditable="true">Private</div>']) {
    const dom = installDom(html);
    assert.throws(() => extractVisiblePage(), /excluded/);
    dom.window.close();
  }
});

test("declares English-only support", () => {
  const dom = installDom('<html lang="hi"><body><p>Example</p></body></html>');
  assert.throws(() => extractVisiblePage(), /English/);
  dom.window.close();
});

test("popup waits for review and renders hostile titles as text", async () => {
  const html = await readFile("extension/popup.html", "utf8");
  const dom = installDom(html);
  const calls = [];
  const sourceUrl = "https://public.example.org/article?private=remove";
  global.chrome = {
    runtime: {openOptionsPage() {}},
    tabs: {query: async () => [{id: 7, url: sourceUrl}], get: async () => ({url: sourceUrl})},
    scripting: {executeScript: async () => [{result: {url: sourceUrl, title: "Semantic retrieval",
      text: "ConfidentialSecret appears in the old text about hybrid search. " +
        "Sentence embeddings support semantic retrieval of related documents. " +
        "Lexical retrieval matches query terms to candidate text."}}]},
    storage: {local: {get: async () => ({apiUrl: "http://127.0.0.1:8000"})},
      session: {get: async () => ({accessToken: "not-for-this-host", tokenOrigin: "https://other.example.org"})}},
  };
  global.fetch = async (url, options) => {
    calls.push({url, options});
    return {ok: true, json: async () => ({mode: "demo", ranker: "test", warnings: [],
      recommendations: [{url: "https://results.example.org/article", host: "results.example.org",
        title: '<img src=x onerror="alert(1)">', snippet: "Safe excerpt", reason: "Shared topics"}]})};
  };
  await import("../extension/popup.js?dom-test");
  document.getElementById("prepare").click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.length, 0);
  assert.equal(document.getElementById("preview").hidden, false);
  document.getElementById("summary").value = "Sentence embeddings and lexical retrieval " +
    "find useful candidate documents for a semantic search application.";
  document.getElementById("send").click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(calls.length, 1);
  const body = JSON.parse(calls[0].options.body);
  assert.ok(!JSON.stringify(body).includes("ConfidentialSecret"));
  assert.ok(!body.page_url.includes("private"));
  assert.equal(calls[0].options.headers.Authorization, undefined);
  assert.equal(document.querySelector("#results img"), null);
  assert.ok(document.querySelector("#results a").textContent.startsWith("<img"));
  dom.window.close();
  delete global.chrome;
  delete global.fetch;
});
