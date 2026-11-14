import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {JSDOM} from "jsdom";
import {initComparison} from "../public/assets/comparison.js";

const html = await readFile("public/index.html", "utf8");
const data = {request_id:"comparison-123",baseline_cosine:.6,fine_tuned_cosine:.8,
  fine_tuned_model:"bm25-minilm-snli-lora-v1-rrf-mmr"};
const flush = () => new Promise(r => setImmediate(r));
async function setup(handler) {
  const dom = new JSDOM(html, {url:"https://play.example.org"});
  const calls = [];
  const app = initComparison({document:dom.window.document,fetch:async (url,init) => {
    calls.push({url,init});
    if (url === "/v1/config") return {ok:true,json:async()=>({fine_tuned_available:true})};
    return handler ? handler(url,init) : {ok:true,json:async()=>data};
  }});
  await app.ready;
  const $ = id => dom.window.document.getElementById(id);
  return {dom,app,calls,$,submit:()=>$("comparison-form").dispatchEvent(new dom.window.Event("submit",{cancelable:true})),
    close:()=>{app.destroy();dom.window.close();}};
}

test("arbitrary passages use actual baseline and trained scores with a same-origin session",async()=>{
  const t=await setup(); t.$("access-token").value="session-secret";
  t.$("compare-a").value="Please contact private@example.org about this public idea.";
  t.submit(); await flush();
  const call=t.calls.find(c=>c.url==="/v1/compare");
  assert.equal(call.init.credentials,"same-origin");
  assert.equal(call.init.headers.Authorization,"Bearer session-secret");
  assert.ok(!call.init.body.includes("private@example.org"));
  assert.ok(!call.init.body.includes("session-secret"));
  assert.equal(t.$("baseline-cosine").textContent,"0.600");
  assert.equal(t.$("adapted-cosine").textContent,"0.800");
  assert.equal(t.$("comparison-results").hidden,false); t.close();
});

test("missing trained checkpoint shows an explicit error without fake scores",async()=>{
  const t=await setup(async()=>({ok:false,status:409}));
  t.submit();await flush();
  assert.equal(t.$("comparison-results").hidden,true);
  assert.match(t.$("comparison-status").textContent,/not available/); t.close();
});

test("nonfinite model output cannot become an inference result",async()=>{
  const t=await setup(async()=>({ok:true,json:async()=>({...data,fine_tuned_cosine:NaN})}));
  t.submit();await flush();
  assert.equal(t.$("comparison-results").hidden,true);
  assert.match(t.$("comparison-status").textContent,/invalid model evidence/);t.close();
});

test("changing examples cancels a comparison and ignores its stale response",async()=>{
  let finish;
  const t=await setup(()=>new Promise(r=>{finish=r;}));
  t.submit();await flush();t.$("compare-different").click();
  finish({ok:true,json:async()=>data});await flush();
  assert.equal(t.$("comparison-results").hidden,true);
  assert.match(t.$("compare-b").value,/baker/);t.close();
});
