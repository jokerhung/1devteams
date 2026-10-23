# aiTeams frontend

Next.js 15 App Router, TypeScript, Tailwind CSS, TanStack Query and shadcn/Base UI.

Frontend: `http://localhost:3060`; backend: `http://localhost:8060` by default.
Run both from the repository root with `./scripts/dev.ps1` (`-Setup` on first run).
Ports are configurable in the root `.env`.

The workspace includes login, Agents & Teams, projects/settings/members, notifications,
workflow overview/template publishing and ticket creation. Canvas and ticket chat are
placeholders for Phases 5–6.

Auth uses a same-origin server proxy with an httpOnly JWT cookie. `BACKEND_URL` can set
the server-side backend address; it falls back to `NEXT_PUBLIC_API_URL` then port 8060.
Backend WebSockets are bridged through a streaming Next route; the token stays server-side.

```powershell
npm ci
npm run gen:api
npm run lint
npm run typecheck
npm run test
npm run build
npx playwright install chromium
npx playwright test
```

`gen:api` uses `OPENAPI_URL` or `${BACKEND_URL}/openapi.json` (default port 8060).
Playwright launches isolated services on 3062/8062, an isolated database and a Git
workspace under `.e2e-data/`; it does not use the application's local database.
Prepare `backend/.venv` first. On Linux it uses `.venv/bin/python`; on Windows
`.venv/Scripts/python.exe`. Override with `E2E_PYTHON` if needed.

See [Phase 4 implementation notes](../docs/specs/PHASE_4_IMPLEMENTATION_NOTES.md)
for details and verification results.
