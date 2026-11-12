import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {contextFromText, redact} from "../extension/nlp.js";
import {apiBase, publicPageUrl} from "../extension/safety.js";

test("local excerpt and topics are bounded", () => {
  const text = "Semantic search uses embeddings to retrieve related documents. " +
    "Hybrid retrieval combines lexical terms with dense vectors for candidate discovery. " +
    "Reranking improves relevance after retrieving a bounded candidate set. ";
  const context = contextFromText(text.repeat(1000), "Hybrid search");
  assert.ok(context.summary.length <= 1200);
  assert.ok(context.keywords.length <= 10);
  assert.ok(context.keywords.includes("retrieval"));
});
test("obvious private identifiers are removed before preview", () => {
  assert.equal(redact("contact private@example.com"), "contact [redacted]");
  assert.ok(!redact("card 4111111111111111").includes("4111111111111111"));
});
test("no fabricated context from short pages", () => {
  assert.throws(() => contextFromText("Login", "Login"), /too little/);
});
test("strip source query and fragment", () => {
  assert.equal(publicPageUrl("https://public.example.org/story?token=x#private"),
    "https://public.example.org/story");
});
for (const url of ["chrome://extensions/", "file:///private", "http://127.0.0.1/a",
  "https://user:secret@public.example.org/", "https://mail.google.com/mail/",
  "https://public.example.org/account/orders", "https://intranet.internal/a"]) {
  test(`exclude private or unsupported context: ${url}`, () => {
    assert.throws(() => publicPageUrl(url));
  });
}
test("backend origin must be HTTPS or loopback", () => {
  assert.equal(apiBase("http://127.0.0.1:8000"), "http://127.0.0.1:8000");
  assert.equal(apiBase("https://api.example.org/"), "https://api.example.org");
  assert.throws(() => apiBase("http://api.example.org"));
  assert.throws(() => apiBase("https://user:secret@api.example.org"));
});
test("manifest never installs persistent page-reading permission", async () => {
  const manifest = JSON.parse(await readFile("extension/manifest.json", "utf8"));
  assert.equal(manifest.manifest_version, 3);
  assert.ok(manifest.permissions.includes("activeTab"));
  assert.ok(!manifest.permissions.includes("tabs"));
  assert.equal(manifest.content_scripts, undefined);
  assert.equal(manifest.background, undefined);
  assert.equal(manifest.incognito, "not_allowed");
});
test("results use text nodes and session tokens are destination-bound", async () => {
  const source = await readFile("extension/popup.js", "utf8");
  assert.ok(!source.includes("innerHTML"));
  assert.ok(source.includes("tokenOrigin === destination"));
  assert.ok(source.includes('credentials: "omit"'));
});
