import {apiBase} from "./safety.js";
const $ = id => document.getElementById(id);
const settings = await chrome.storage.local.get({apiUrl: "http://127.0.0.1:8000"});
$("api").value = settings.apiUrl;
$("clear").addEventListener("click", async () => {
  await chrome.storage.session.remove("accessToken");
  $("token").value = "";
  $("status").textContent = "Session token cleared.";
});
$("options").addEventListener("submit", async event => {
  event.preventDefault();
  try {
    const origin = apiBase($("api").value);
    if (origin.startsWith("https:")) {
      const granted = await chrome.permissions.request({origins: [`${origin}/*`]});
      if (!granted) throw new Error("Permission was not granted for this server.");
    }
    await chrome.storage.local.set({apiUrl: origin});
    // Bind bearer tokens to the configured destination: never reuse one at a new origin.
    if (origin !== settings.apiUrl) await chrome.storage.session.remove("accessToken");
    if ($("token").value.trim()) {
      await chrome.storage.session.set({accessToken: $("token").value.trim(), tokenOrigin: origin});
    }
    settings.apiUrl = origin;
    $("token").value = "";
    $("status").textContent = "Settings saved.";
  } catch (error) {$("status").textContent = error.message;}
});
