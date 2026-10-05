// Generates dashboard/public/_headers for the static export.
//
// Two reasons this is generated instead of committed as a literal:
//
//   1. connect-src must name the deployed API origin. The dashboard is a static
//      bundle on a different host from the API, so `connect-src 'self'` alone
//      blocks every fetch and the app silently stops working.
//   2. The _headers grammar is only `<path>` followed by indented `Name: value`
//      lines. Prose, even as a comment, is not reliably supported by Cloudflare
//      Pages and can invalidate the whole file. So the emitted file contains
//      nothing but directives and this file carries the explanation.
//
// Runs from `prebuild`, so `next build` output in out/ always matches the API URL
// baked into the bundle.

import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const outFile = join(here, "..", "public", "_headers");

const raw = process.env.NEXT_PUBLIC_ATLAS_URL;
let connectSrc = "'self'";

if (raw) {
  try {
    // Normalise to a bare origin: the CSP source expression takes no path.
    connectSrc = `'self' ${new URL(raw).origin}`;
  } catch {
    console.warn(
      `[headers] NEXT_PUBLIC_ATLAS_URL="${raw}" is not a valid URL; ` +
        `falling back to connect-src 'self'. The dashboard will not reach the API.`
    );
  }
}

const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "form-action 'self'",
  // Next's static export inlines hydration data as a <script> tag. Without a
  // nonce there is no way to keep that working and drop 'unsafe-inline'; revisit
  // if the app ever loads untrusted third-party content.
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src ${connectSrc}`,
  "frame-src 'none'",
  "upgrade-insecure-requests",
].join("; ");

const contents = `/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Resource-Policy: same-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()
  X-DNS-Prefetch-Control: off
  Content-Security-Policy: ${csp}

/*
  Cache-Control: no-cache, no-store, must-revalidate

/_next/static/*
  Cache-Control: public, max-age=31536000, immutable
`;

writeFileSync(outFile, contents);
console.log(`[headers] wrote public/_headers (connect-src ${connectSrc})`);
