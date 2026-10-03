// Build-time guard: NEXT_PUBLIC_ATLAS_URL is inlined into the bundle at build
// time, so a static export built without it ships a dashboard pointing at
// 127.0.0.1 and silently fails once deployed. Warn loudly instead of building
// something broken.
if (!process.env.NEXT_PUBLIC_ATLAS_URL) {
  console.warn(
    [
      "",
      "  WARNING: NEXT_PUBLIC_ATLAS_URL is not set.",
      "",
      "  The static export will hardcode http://127.0.0.1:800{0-3} and will not",
      "  reach a deployed backend. Set it before building for Cloudflare Pages:",
      "",
      "    NEXT_PUBLIC_ATLAS_URL=https://atlas-<hash>.onrender.com npm run build",
      "",
      "  Local builds against separately running services are fine.",
      "",
    ].join("\n")
  );
}