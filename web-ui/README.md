# Synthadoc Web Chat UI

This is the browser-based chat interface for Synthadoc. It is a React 19 / TypeScript / Vite SPA that runs inside the Synthadoc HTTP server — there is no separate Node.js process in production.

## What it does

When you run `synthadoc serve`, FastAPI serves this UI at `/app`. All API calls in the frontend (`src/api.ts`) use `BASE = ""` (same-origin), so they go directly to the FastAPI server on the same port. The server mounts the built assets from `web-ui/dist/` at startup; if `dist/` is missing or empty, `GET /app` returns HTTP 503 with a plain-text message.

The UI provides:
- Streaming chat against any wiki via `GET /query/stream` (SSE)
- Session persistence — resume prior conversations from the sidebar
- HintEngine chips — follow-up suggestions returned by the server after each answer
- Clarify/notice SSE events — the server can ask for disambiguation mid-stream
- Settings popover — per-tab no-cache toggle and query timeout

Open it with:
```bash
synthadoc web -w history-of-computing    # reads port from config, opens browser
synthadoc web -w history-of-computing --no-browser  # print URL only
```

## Source layout

```
web-ui/
  src/
    api.ts               # all fetch/SSE calls to the FastAPI server
    App.tsx              # root layout: Sidebar + main ChatWindow panel
    useSession.ts        # create/resume session hook
    useSessions.ts       # session list hook (sidebar)
    useQueryStream.ts    # SSE streaming hook
    useQueryHistory.ts   # per-session message history
    components/
      ChatWindow.tsx     # main chat area, input bar, hint chips
      Sidebar.tsx        # session list, wiki name, new-session button
      MessageBubble.tsx  # message rendering (react-markdown + remark-gfm)
      HintChips.tsx      # clickable hint suggestion chips
      Hero.tsx           # welcome screen shown on empty session
      SettingsPopover.tsx # no-cache / timeout controls
  dist/                  # built output — served by FastAPI; never commit this
  vite.config.ts         # base: "/app/", outDir: "dist"
  package.json
```

## Building after a code change

The dist is **not** auto-rebuilt. Any change to `src/` requires a manual rebuild:

```bash
cd web-ui
npm install          # only needed the first time or after package.json changes
npm run build        # tsc -b && vite build → writes web-ui/dist/
```

Then restart `synthadoc serve`. The server mounts `dist/` at startup, so a running server will not pick up the new build until it restarts.

> **Tip:** If you see "Web UI not built. Run: `cd web-ui && npm run build`" in the browser, the `dist/` directory is missing or was deleted.

## Development with HMR

For faster iteration, run the Vite dev server alongside a running `synthadoc serve`. Because `api.ts` uses same-origin paths, you need to proxy API calls to the FastAPI port. Add a `server.proxy` block to `vite.config.ts` temporarily:

```ts
// vite.config.ts — temporary for local dev; don't commit the proxy block
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  base: "/app/",
  build: { outDir: "dist" },
  server: {
    proxy: {
      '/query':      'http://127.0.0.1:7070',
      '/sessions':   'http://127.0.0.1:7070',
      '/hints':      'http://127.0.0.1:7070',
      '/health':     'http://127.0.0.1:7070',
      '/lifecycle':  'http://127.0.0.1:7070',
      '/lint':       'http://127.0.0.1:7070',
      '/jobs':       'http://127.0.0.1:7070',
    },
  },
})
```

Then:

```bash
# Terminal 1 — FastAPI backend
synthadoc serve -w history-of-computing --port 7070

# Terminal 2 — Vite dev server with HMR
cd web-ui
npm run dev        # starts on http://localhost:5173/app/
```

Open `http://localhost:5173/app/` in the browser. Edits to `src/` hot-reload immediately. When done, remove the `server.proxy` block and run `npm run build`.

## Linting

```bash
cd web-ui
npm run lint       # eslint over all .ts / .tsx files
```

Type-checking is part of the build (`tsc -b` in `npm run build`). Run it standalone with:

```bash
npx tsc --noEmit
```

## Manual integration testing

There are no automated UI tests in this directory. Integration testing is done against the live HTTP API using the Obsidian plugin test suite, which covers the same FastAPI endpoints the web UI depends on:

```bash
# Requires synthadoc serve running on port 7070
cd obsidian-plugin
npx vitest run src/api.integration.test.ts
```

To manually smoke-test the web UI itself:

1. Start the server: `synthadoc serve -w history-of-computing`
2. Build the UI: `cd web-ui && npm run build`
3. Open: `synthadoc web -w history-of-computing`
4. Type a question — the answer should stream token by token
5. Check that hint chips appear after the answer
6. Open the sidebar, click a prior session — the conversation history should reload
7. Use the settings popover to toggle no-cache; repeat the same question and confirm a fresh answer

## Adding a new API endpoint to the UI

1. Add the fetch call to `src/api.ts`
2. Call it from the relevant hook or component
3. Rebuild (`npm run build`) and restart `synthadoc serve`
4. Verify the endpoint is covered in `obsidian-plugin/src/api.integration.test.ts`; if not, add a test there
