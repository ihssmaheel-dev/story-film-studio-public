# Studio Monitor frontend

A local production dashboard built with Vite, React 19, TypeScript, Tailwind CSS, shadcn/ui's Base UI components, TanStack Table, React Flow and Lucide React. It reads the studio's existing loopback API and can record explicit character-change requests. It does not start production, make provider calls, edit canonical character data or record approvals.

## Build and run

Use Node 22.12 or newer. From the repository root:

```powershell
npm --prefix apps/monitor ci
npm --prefix apps/monitor run build
python tools/studio.py monitor --workspace . --port 8765
```

Open the printed address. The Python server serves `dist/` and the read-only API on the same origin. Node is only needed to develop/build the frontend; no Node process is required to view a built monitor. Build output and `node_modules/` are ignored by Git. A missing build returns an explicit 503 with setup instructions while the API remains available.

For frontend development, leave the Python server running on port 8765 and run `npm --prefix apps/monitor run dev` in another terminal. Vite proxies `/api` and `/logo.png` to that backend. Set `STUDIO_MONITOR_API` to a different loopback backend URL when needed. The production build always uses relative API/media URLs.

## Structure

```text
src/
  app.tsx                   Section navigation and composition
  components/
    ui/                     Shared shadcn/Base UI primitives
    app-shell.tsx           Sidebar, mobile navigation and theme
  features/
    production/             Current operation and task data table
    progress/               Live React Flow, step evidence and side drawer
    media/                  Custom player, film tracks and clip inspection
    voices/                 Cast and voice revision records
    cast/                   Character profiles, reference sheets, coverage and change requests
  hooks/use-monitor.ts      Cancelable polling and per-project snapshots
  lib/                      Transport, formatting and pure selectors
  types/monitor.ts          Read-only API contract
  styles.css                Design tokens, layout and compact density
tests/monitor.test.ts        Clocks, chronology, selectors and API boundaries
tests/progress.test.ts       Live states, actual evidence and revision currency
```

The overview prioritizes the task data table. Search, status filters, sortable columns, pagination and expandable task evidence operate on actual returned jobs. **Production Progress** visualizes the currently recorded workflow in React Flow. Clicking a step opens a live side drawer with its task status, start/finish times, measured duration, counters, estimate evidence and timestamped activity. The graph keeps failed, stale, reused and waiting work distinct. Verified running tasks and submitted provider requests show loaders; a lost connection stops unverified activity animations. Unknown durations stay unknown. The production clock stops at a current recorded part delivery rather than continuing to count time spent viewing the dashboard.

The graph groups actual records by stage and selected part. Compact 210 × 108 px cards keep status, timing and measured counters readable, with tighter padding and 28 px gaps. Its connectors show workflow order, not a measured time scale or proof of a strict dependency. No unrecorded future phases or gate approvals are created. Pan/zoom and the selected drawer are retained while polling updates values. Use **Current step** to locate live work or **Fit all** for an overview. Narrow screens focus nearby steps at a readable scale above the map controls. Closing the drawer restores focus to its originating control. Old `#history` and `#activity-panel` bookmarks still open Production Progress.

The film workspace has custom playback, keyboard seeking, volume, playback speed, full-screen controls, zoomable measured tracks and a clip inspector. It keeps the loaded preview stable during polling and offers new revisions explicitly. A stale preview without verified timing cannot synchronize the current timeline. User decisions remain with the existing production-agent workflow.

The Cast sheets workspace uses a compact searchable/filterable table and a live side drawer for the full design, current/earlier images, actual inspection coverage and revision history. A Base UI multiline field records a change request against the exact displayed design version. Same-origin/token checks protect the request-only endpoint; a request never directly changes canon or starts media generation. See [cast workflow](../../docs/18-cast-sheets.md). `#cast` opens this section; voice assignments remain under `#voices`.

All interactive controls use shared shadcn/Base UI components. Icons come only from `lucide-react`. The video element has no browser-default controls. `npm run check` enforces these source constraints and strict TypeScript. Base UI still renders the semantic DOM and hidden inputs required for accessibility.

## Checks

```powershell
npm --prefix apps/monitor run check
npm --prefix apps/monitor test
npm --prefix apps/monitor run build
```

`npm run format` formats source/configuration with Prettier. The npm lockfile pins the installed dependency graph. No production mock data is bundled.

The visual reference informs the white/near-black hierarchy, restrained weight, thin borders and tight geometry. The studio's no-green preference is retained; purple, blue, pink and amber differentiate recorded categories. Inter is self-hosted through Fontsource. Dark mode, keyboard focus and reduced motion are supported.

Component sources were generated from the official shadcn `base-nova` registry and adapted to the shared local utility, density and accessible slider labels. References: [shadcn/Vite](https://ui.shadcn.com/docs/installation/vite), [Base UI](https://base-ui.com/react/overview/quick-start), [Tailwind/Vite](https://tailwindcss.com/docs/installation/using-vite), [TanStack Table](https://tanstack.com/table/latest/docs/framework/react/quick-start), [React Flow](https://reactflow.dev/api-reference/hooks/use-nodes-initialized).
