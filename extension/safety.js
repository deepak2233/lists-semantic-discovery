export function publicPageUrl(value) {
  const url = new URL(value);
  const host = url.hostname.toLowerCase().replace(/\.$/, "");
  if (!["https:", "http:"].includes(url.protocol) || url.username || url.password ||
      !host.includes(".") || /(?:\.local|\.internal|\.localhost)$/.test(host) ||
      /^[\d.]+$/.test(host) || host.includes(":") ||
      (url.port && !["80", "443"].includes(url.port))) {
    throw new Error("Open a public article. Local, private and browser pages are excluded.");
  }
  if (/^(?:mail\.google\.com|outlook\.(?:live|office)\.com|accounts\.google\.com)$/.test(host) ||
      /\/(?:login|signin|checkout|account|inbox)(?:\/|$)/i.test(url.pathname)) {
    throw new Error("This looks like an account or private page. Open a public article.");
  }
  url.search = "";
  url.hash = "";
  return url.href;
}

export function apiBase(value) {
  const url = new URL(value);
  if (url.username || url.password || url.search || url.hash ||
      (url.pathname !== "/" && url.pathname !== "")) {
    throw new Error("Use a server origin, for example https://discovery.example.com.");
  }
  if ((url.protocol === "https:" && url.port) ||
      (url.protocol !== "https:" && !(url.protocol === "http:" && url.hostname === "127.0.0.1"))) {
    throw new Error("The API requires HTTPS, except for 127.0.0.1 during development.");
  }
  return url.origin;
}
