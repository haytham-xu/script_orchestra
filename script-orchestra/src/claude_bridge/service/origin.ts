/**
 * Claude Bridge — backend origin resolution.
 *
 * Two deployment shapes:
 *  - Local/LAN dev: the frontend is served on the Vite port (5001) or opened via
 *    a LAN IP; the backend is a *separate* process on :50001. We must target
 *    that explicit port.
 *  - Tunnel / same-origin (Cloudflare Tunnel → backend, or any reverse proxy):
 *    the page is served on a real domain over 80/443 with no explicit dev port,
 *    and the backend is reachable at the SAME origin. We must NOT append :50001.
 *
 * Heuristic: if the page has an explicit non-standard port (the Vite dev server),
 * talk to the separate backend on :50001. Otherwise assume same-origin.
 */
const BACKEND_PORT = '50001'

export function backendOrigin(): string {
  const { protocol, hostname, port, origin } = window.location
  // Dev server (Vite) runs on a port like 5001 → backend is a separate process.
  const isDevPort = port !== '' && port !== '80' && port !== '443'
  if (isDevPort) {
    const host = hostname === '127.0.0.1' ? 'localhost' : hostname
    return `${protocol}//${host}:${BACKEND_PORT}`
  }
  // Served through a domain / tunnel on 80/443 → same origin as this page.
  return origin
}
