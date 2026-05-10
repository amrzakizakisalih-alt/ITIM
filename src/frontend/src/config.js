/**
 * Centralized frontend configuration.
 * In dev, Vite proxies /api and /ws to the backend.
 */

const PROTO = window.location.protocol === "https:" ? "wss:" : "ws:";
const PORT =
  window.location.port ||
  (window.location.protocol === "https:" ? "443" : "80");
const PORT_SUFFIX = PORT === "443" || PORT === "80" ? "" : `:${PORT}`;

export const WS_URL = `${PROTO}//${window.location.hostname}${PORT_SUFFIX}/ws`;
export const API_BASE = "";
