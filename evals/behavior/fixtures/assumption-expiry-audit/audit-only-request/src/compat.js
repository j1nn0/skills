export function fetchWithFallback(url) {
  if (typeof globalThis.fetch === "function") return globalThis.fetch(url);
  return legacyFetch(url);
}


function legacyFetch(url) {
  return Promise.resolve({ ok: true, url });
}
