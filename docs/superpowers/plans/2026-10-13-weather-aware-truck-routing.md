# Weather-Aware Truck Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Django + React app where a truck driver enters origin, destination, departure time and load weight, and gets 3 truck routes scored for weather risk at each checkpoint's ETA, a recommended route, and a 0–48 h weather-risk heatmap over the trip corridor.

**Architecture:** Django (SQLite) owns every rule: it calls Valhalla (truck routing), Open-Meteo (hourly forecast) and Photon (geocoding), places checkpoints along each route, looks up the forecast at each checkpoint's ETA, classifies risk with the brief's rules, ranks the routes, and persists the trip. The pure rule engine (`trips/engine/`) has no Django or network imports and carries most of the tests. The React SPA (Vite+, bun, TanStack Router + Query, MapLibre) only renders: one persistent map in the root layout, a route panel per URL, and a "logbook" timeline scrubber that drives the heatmap and truck positions. In production Django serves the built SPA, so there is one deploy and no CORS.

**Tech Stack:** Python 3.13, uv, Django 5, django-ninja, httpx, polyline, pytest + pytest-django + respx, whitenoise, gunicorn · bun, Vite+ (`vp`), React 19, TypeScript, TanStack Router (file-based) + React Query, Tailwind v4, shadcn CLI + Aceternity UI (Multi Step Loader), MapLibre GL via `react-map-gl/maplibre`, OpenFreeMap tiles, Fontsource fonts.

**Spec:** `docs/brief.md` (the assessment brief, verbatim).

## Global Constraints

- Risk bands, copied from the brief. Wind: Low <25 mph, Moderate 25–34, High 35–44, Severe 45–54, No Travel ≥55 mph. Rain: Low <0.10 in/hr, Moderate 0.10–0.25, High 0.25–0.50, Severe 0.50–1.00, No Travel >1.00. Snow: Low <0.5 in/hr, Moderate 0.5–1.0, High 1.0–2.0, Severe 2.0–3.0, No Travel >3.0.
- Band edges are half-open on the lower bound: a value equal to an edge belongs to the higher band (25.0 mph is Moderate, 0.25 in/hr is High, 1.0 in/hr snow is High). The top band follows the brief's symbol: wind ≥55 is No Travel; rain and snow must be strictly >1.00 / >3.00 (exactly 1.00 in/hr rain is Severe).
- Load rules: wind ≥55 mph → No Travel for any load; wind 45–54 mph and load >30,000 lb → No Travel; wind 35–44 mph and load >40,000 lb → Severe. "More than" is strict: exactly 30,000 lb and exactly 40,000 lb do not trigger.
- A checkpoint's level is the worst of its wind (after load rules), rain and snow levels.
- Wind means sustained 10 m wind (`wind_speed_10m`). Gusts are shown but not scored. Rain means `rain + showers`. Snow means `snowfall` (Open-Meteo returns inches when `precipitation_unit=inch` — verified).
- Recommendation order: fewest No Travel miles, then fewest Severe miles, then fewest High miles, then lowest average risk, then shortest travel time. (No Travel is ranked first because it is worse than Severe; the brief's list starts at Severe.)
- Weather sampling interval is user-selectable: 10, 25 or 50 miles. Default 25.
- Route count target: exactly 3; fewer only when 3 distinct routes do not exist, and the UI says so.
- Departure accepted from 1 hour in the past up to 7 days ahead. Load accepted from 1 to 150,000 lb.
- Units in the UI: miles, mph, in/hr, lb. Times shown in the browser's local time zone; the API speaks UTC ISO-8601.
- No API keys required anywhere. Outbound requests send `User-Agent: WeatherAwareTruckRouting/1.0 (+<repo url>)`.
- Copy: sentence case, active verbs, errors say what happened and what to do, never apologize.
- Respect `prefers-reduced-motion`; every control reachable and visibly focused by keyboard; layout works at 375 px wide.

## Design Direction

Subject: a long-haul driver (or their dispatcher) deciding, before rolling, which of three highways to take tomorrow. The page's single job: make the safest choice obvious and show *when and where* weather bites.

**Palette** (all chrome and data colors derive from these; defined once in `frontend/src/styles/app.css`):

| Token | Hex | Use |
|---|---|---|
| `paper` | `#EEF1EE` | App background — cool road-atlas paper |
| `ink` | `#1E2328` | Text, route casings — asphalt |
| `guide` | `#0E6B45` | Route signs — MUTCD guide-sign green |
| `sign-white` | `#FAFAF7` | Text on signs, plaques |
| `interstate` | `#1E4FA3` | Selected route casing, focus ring — interstate shield blue |
| Risk ramp | low `#5E9C76` · moderate `#E9B824` · high `#EA7A1F` · severe `#C8232C` · no travel `#4A1050` | Checkpoints, segments, heatmap, logbook |

The risk ramp borrows the MUTCD sign family (warning yellow, work-zone orange, stop red) so drivers read it without a legend.

**Type:** Overpass 700/800 (open-source descendant of the FHWA Highway Gothic used on US signs) for route signs and headings only · Public Sans 400/500/600 (the US Web Design System face) for body and forms · Overpass Mono 400/600 for mileposts, ETAs, numbers. Scale: 12 / 14 / 16 / 20 / 28 px.

**Layout:**

```
desktop ≥ 900px                                   mobile
┌──────── 420px panel ───────┬──── map ─────────┐ ┌──────── map 52svh ───────┐
│ Weather-aware truck routing│ heat raster      │ │                          │
│ [form]  or  [trip summary] │ route segments   │ ├── logbook scrubber ──────┤
│ ┌ B ─ I 80 W · I 76 ──────┐│ checkpoints      │ │ panel (form / signs /    │
│ │ 1,016 mi 15 h 45 m      ││ truck markers    │ │ checkpoint table) scrolls│
│ │ ▇▇▇▇▇▅▅▇▇▇ risk strip   ││                  │ └──────────────────────────┘
│ └ RECOMMENDED — fewest …  ┘├──────────────────┤
│ ┌ A ─ … ┐ ┌ C ─ … ┐        │ logbook 0–48 h   │
│ checkpoint table           │ A ━━━━╍╍━━       │
└────────────────────────────┴──────────────────┘
```

**Signature — the logbook scrubber.** The 0–48 h forecast slider is drawn as a driver's duty-status logbook grid: one row per route, one column per hour, midnight lines heavy. Each row's trace is colored by the risk the truck meets during that hour and ends at arrival. Dragging the cursor repaints the heatmap and moves a lettered truck marker along every route to where it would be at that hour. It answers the real question (where am I when the storm hits?) in the visual language of the cab.

**The one aesthetic risk:** route options are rendered as green freeway guide signs (Overpass on `guide`), with a white plaque under the recommended one, like an `EXIT ONLY` panel. Everything else stays quiet: paper background, hairline-free cards, no gradients, no glow. Aceternity is used once, for the Multi Step Loader while a trip is planned, restyled to these tokens.

Self-review notes: rejected a yellow recommended plaque (collides with Moderate amber); rejected an all-green panel (two loud elements compete with the logbook); rejected a density heatmap (overlap inflates "risk") in favor of a per-cell risk raster.

## Review Focus

1. **Values exactly on a band edge** (25 mph, 0.25 in/hr, 1.00 in/hr rain, 3.0 in/hr snow, 30,000 lb, 40,000 lb) — a driver expects the documented band, not floating-point luck. Pinned in Task 3.
2. **Routing returns fewer than 3 distinct routes** (Valhalla's truck profile returned 1 alternate for Chicago→Denver during research; short trips have none) — expect detour-based alternates, near-duplicates rejected, and a visible note if 3 still don't exist; never a crash. Pinned in Task 8.
3. **Departure outside the forecast window, or a trip whose late checkpoints fall past the forecast** — expect a 422 naming the problem and the fix. Pinned in Task 10.
4. **Every route crosses No Travel** — expect the least-bad route still ranked first, `all_blocked: true`, and a banner telling the driver to leave later. Pinned in Task 6 (ranking test) and Task 14 (banner).
5. **Upstream service down or slow** (Open-Meteo, Valhalla, Photon) — expect a 502 with a readable message and the form still usable, not a 500. Pinned in Tasks 7, 8, 9 and 10.

Also covered: a checkpoint ETA between two forecast hours (wind interpolated, precipitation taken from the hour that contains the ETA — Task 5); a departure typed in a non-UTC zone (Task 10).

---

## File Structure

```
Spotter/
├── CLAUDE.md                      (exists — RTK instructions)
├── README.md                      Task 17
├── Dockerfile, render.yaml        Task 17
├── docs/brief.md                  spec
├── backend/
│   ├── pyproject.toml, manage.py  Task 1
│   ├── config/settings.py urls.py views.py wsgi.py
│   └── trips/
│       ├── models.py              Trip, ForecastCache
│       ├── api.py                 NinjaAPI: /health /geocode /trips /trips/{id} /trips/{id}/corridor
│       ├── schemas.py             request schemas
│       ├── errors.py              TripError, NoRouteError, ProviderError
│       ├── services.py            plan_trip(), build_corridor() — orchestration only
│       ├── engine/                pure, no Django/network
│       │   ├── geo.py             haversine, cumulative miles, interpolation, offsets
│       │   ├── route.py           RouteGeometry
│       │   ├── risk.py            Level, assess()
│       │   ├── forecast.py        HourlySeries, Conditions, conditions_at()
│       │   ├── checkpoints.py     checkpoint_miles, place_checkpoints, thin, slice_path
│       │   ├── scoring.py         summarize, recommend
│       │   └── corridor.py        build_grid, corridor_scores
│       ├── providers/
│       │   ├── http.py            shared httpx client
│       │   ├── open_meteo.py      fetch_series() + SQLite cache
│       │   ├── valhalla.py        fetch_routes() + detour alternates
│       │   └── photon.py          search_places()
│       └── tests/                 factories.py + one test file per module
└── frontend/
    ├── vite.config.ts, components.json, package.json
    └── src/
        ├── main.tsx, routeTree.gen.ts (generated)
        ├── styles/app.css         tokens + component classes
        ├── routes/__root.tsx      shell: panel <Outlet/> + persistent TripStage
        ├── routes/index.tsx       plan form
        ├── routes/trips.$tripId.tsx  route signs + checkpoint table
        ├── api/                   types.ts client.ts queries.ts
        ├── lib/                   risk.ts format.ts timeline.ts useDebouncedValue.ts
        ├── features/planner/      TripForm.tsx PlaceInput.tsx validate.ts
        ├── features/map/          TripMap.tsx layers.ts CorridorLayer.tsx corridorPixels.ts geojson.ts
        ├── features/logbook/      LogbookScrubber.tsx
        ├── features/routes/       RouteSign.tsx RiskStrip.tsx CheckpointTable.tsx
        ├── features/stage/        TripStage.tsx
        └── components/ui/multi-step-loader.tsx (Aceternity, via shadcn CLI)
```

## API Contract (shared by backend Tasks 10–11 and frontend Task 12)

`POST /api/trips` body:
```json
{"origin": {"label": "Chicago, Illinois, US", "lat": 41.88, "lon": -87.63},
 "destination": {"label": "Denver, Colorado, US", "lat": 39.74, "lon": -104.99},
 "departure": "2026-10-14T11:00:00Z", "load_lb": 42000, "interval_mi": 25}
```
`201` and `GET /api/trips/{id}` return a `Trip`:
```json
{"id": "uuid", "created_at": "iso", "origin": {...}, "destination": {...},
 "departure": "2026-10-14T11:00:00+00:00", "load_lb": 42000, "interval_mi": 25,
 "timeline_start": "2026-10-14T11:00:00+00:00",
 "routes": [{"id": "A", "label": "I 80 W · I 76 W", "distance_mi": 1016.4, "duration_s": 56695,
   "arrival": "iso", "rank": 1,
   "path": {"coordinates": [[-87.63, 41.88], ...], "seconds": [0, 41, ...]},
   "segments": [{"level": "low", "start_mile": 0, "end_mile": 25, "coordinates": [[lon, lat], ...]}],
   "checkpoints": [{"mile": 0, "lon": -87.63, "lat": 41.88, "eta": "iso", "wind_mph": 14.8,
     "gust_mph": 24.2, "rain_in_hr": 0.0, "snow_in_hr": 0.0, "level": "low",
     "drivers": [], "load_adjusted": false}],
   "summary": {"miles_by_level": {"low": 990.0, "moderate": 26.4, "high": 0, "severe": 0, "no_travel": 0},
     "avg_risk": 0.026, "max_level": "moderate"}}],
 "recommendation": {"route_id": "A", "reason": "Fewest severe miles: 0 vs 42 on Route B.", "all_blocked": false},
 "notes": []}
```
`GET /api/trips/{id}/corridor` → `{"start": "iso", "bounds": [west, south, east, north], "cols": 40, "rows": 22, "scores": [[...cols*rows floats...] × 49]}` — `scores[h][row*cols+col]`, row 0 = north edge, value = continuous risk score 0–4, `-1` = outside corridor or no forecast. Hour `h` is `start + h` hours; `start` = departure floored to the hour (same as `timeline_start`).

`GET /api/geocode?q=denver` → `[{"label": "Denver, Colorado, US", "lat": 39.739, "lon": -104.985}]`.

Errors: `{"detail": "message"}` with 422 (bad input / no route / outside forecast) or 502 (upstream down). Schema validation errors from django-ninja are 422 with `detail` as an array of `{msg}`.

---

### Task 1: Backend scaffold with health check

**Files:**
- Create: `backend/pyproject.toml` (via uv), `backend/manage.py`, `backend/config/*` (via startproject), `backend/trips/*` (via startapp), `backend/trips/api.py`, `backend/trips/tests/__init__.py`, `backend/trips/tests/test_health.py`, `.gitignore`
- Modify: `backend/config/settings.py`, `backend/config/urls.py`

**Interfaces:**
- Produces: `trips.api.api` (a `NinjaAPI` mounted at `/api/`); settings `VALHALLA_URL`, `HTTP_USER_AGENT`, `FRONTEND_DIST` (Path); pytest configured so `uv run pytest` works from `backend/`.

- [ ] **Step 1: Scaffold the project**

```bash
cd /Users/Apple/Documents/repo/assesment/Spotter
mkdir backend && cd backend
uv init --bare --python 3.13
uv add "django>=5.2,<6" "django-ninja>=1.4" httpx polyline whitenoise gunicorn
uv add --dev pytest pytest-django respx ruff
uv run django-admin startproject config .
uv run python manage.py startapp trips
mkdir -p trips/tests trips/engine trips/providers
touch trips/tests/__init__.py trips/engine/__init__.py trips/providers/__init__.py
rm trips/tests.py trips/admin.py trips/views.py
```

Append to `backend/pyproject.toml`:

```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "config.settings"
python_files = ["test_*.py"]

[tool.ruff]
line-length = 100
```

Create `/Users/Apple/Documents/repo/assesment/Spotter/.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc
backend/db.sqlite3
backend/frontend_dist/
backend/staticfiles/
node_modules/
frontend/dist/
.env
.DS_Store
```

- [ ] **Step 2: Write the failing test**

`backend/trips/tests/test_health.py`:

```python
def test_health_returns_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd backend && uv run pytest trips/tests/test_health.py -v`
Expected: FAIL — 404 (no `/api/` route yet).

- [ ] **Step 4: Configure settings, urls and the API**

Replace the generated parts of `backend/config/settings.py` so it contains (keep the generated `BASE_DIR`, `TEMPLATES`, `AUTH_PASSWORD_VALIDATORS`, i18n blocks):

```python
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-not-secret")
DEBUG = os.environ.get("DJANGO_DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = [
    o for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o
]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "trips",
]

MIDDLEWARE = [
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SQLITE_PATH", BASE_DIR / "db.sqlite3"),
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
FRONTEND_DIST = BASE_DIR / "frontend_dist"
WHITENOISE_ROOT = FRONTEND_DIST if FRONTEND_DIST.exists() else None

VALHALLA_URL = os.environ.get("VALHALLA_URL", "https://valhalla1.openstreetmap.de/route")
HTTP_USER_AGENT = os.environ.get(
    "HTTP_USER_AGENT",
    "WeatherAwareTruckRouting/1.0 (+https://github.com/<you>/weather-aware-truck-routing)",
)
```

Delete `django.contrib.admin`, `auth`, `sessions`, `messages` references (the app has no users). Keep `TEMPLATES` as generated but set `"OPTIONS": {"context_processors": []}`.

`backend/trips/api.py`:

```python
from ninja import NinjaAPI

api = NinjaAPI(title="Weather-Aware Truck Routing")


@api.get("/health")
def health(request):
    return {"ok": True}
```

`backend/config/urls.py`:

```python
from django.urls import path

from trips.api import api

urlpatterns = [
    path("api/", api.urls),
]
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd backend && uv run pytest -v`
Expected: PASS (1 test). Also run `uv run python manage.py check` → `System check identified no issues`.

- [ ] **Step 6: Commit**

```bash
cd /Users/Apple/Documents/repo/assesment/Spotter
git add .gitignore CLAUDE.md docs backend
git commit -m "chore: scaffold Django backend with ninja health endpoint"
```

---

### Task 2: Frontend scaffold, design tokens, shell

**Files:**
- Create: `frontend/` (via Vite+), `frontend/src/styles/app.css`, `frontend/src/main.tsx`, `frontend/src/routes/__root.tsx`, `frontend/src/routes/index.tsx`, `frontend/src/lib/risk.ts`, `frontend/src/lib/risk.test.ts`, `frontend/components.json`, `frontend/src/components/ui/multi-step-loader.tsx` (via shadcn), `frontend/src/lib/utils.ts` (via shadcn)
- Modify: `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/tsconfig.app.json`, `frontend/package.json`, `frontend/index.html`

**Interfaces:**
- Produces: `Level`, `LEVELS`, `LEVEL_LABEL`, `LEVEL_COLOR`, `levelIndex(level)`, `maxLevel(a, b)` from `@/lib/risk`; root route with context `{ queryClient: QueryClient }`; CSS classes `.panel`, `.field-label`, `.field-input`, `.btn-primary`, `.chip`; dev server proxies `/api` → `http://127.0.0.1:8000`.

- [ ] **Step 1: Scaffold with Vite+ and bun**

```bash
cd /Users/Apple/Documents/repo/assesment/Spotter
bunx --package vite-plus vp create vite:application --no-interactive
```

When the template prompts (or via its flags), choose: directory `frontend`, framework React, variant TypeScript, package manager bun. If `vp create` cannot pick React non-interactively, use the fallback and migrate:

```bash
bun create vite@latest frontend --template react-ts
cd frontend && bunx --package vite-plus vp migrate
```

Then install dependencies:

```bash
cd frontend
bun add @tanstack/react-router @tanstack/react-query maplibre-gl react-map-gl motion clsx tailwind-merge \
  @fontsource/overpass @fontsource/public-sans @fontsource/overpass-mono
bun add -d @tanstack/router-plugin @tailwindcss/vite tailwindcss @types/node
```

Ensure `package.json` scripts are:

```json
{
  "scripts": {
    "dev": "vp dev",
    "build": "vp build",
    "test": "vp test",
    "check": "vp check"
  }
}
```

- [ ] **Step 2: Configure Vite+, router plugin, Tailwind, alias, proxy**

`frontend/vite.config.ts` (keep any keys the scaffold added that are not listed here):

```ts
import path from 'node:path';
import { defineConfig } from 'vite-plus';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { tanstackRouter } from '@tanstack/router-plugin/vite';

export default defineConfig({
  plugins: [tanstackRouter({ target: 'react', autoCodeSplitting: true }), react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(import.meta.dirname, 'src') } },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  test: { environment: 'node' },
  lint: { options: { typeAware: true, typeCheck: true } },
});
```

Add to `compilerOptions` in both `tsconfig.json` and `tsconfig.app.json`:

```json
"baseUrl": ".",
"paths": { "@/*": ["./src/*"] }
```

- [ ] **Step 3: Write the failing test for the risk palette helpers**

`frontend/src/lib/risk.test.ts`:

```ts
import { describe, expect, it } from 'vite-plus/test';
import { LEVELS, levelIndex, maxLevel } from './risk';

describe('risk levels', () => {
  it('orders levels from low to no travel', () => {
    expect(LEVELS).toEqual(['low', 'moderate', 'high', 'severe', 'no_travel']);
    expect(levelIndex('severe')).toBe(3);
  });

  it('picks the worse of two levels', () => {
    expect(maxLevel('moderate', 'high')).toBe('high');
    expect(maxLevel('no_travel', 'low')).toBe('no_travel');
  });
});
```

Run: `cd frontend && bun run test`
Expected: FAIL — cannot resolve `./risk`.

- [ ] **Step 4: Implement `lib/risk.ts`**

```ts
export const LEVELS = ['low', 'moderate', 'high', 'severe', 'no_travel'] as const;
export type Level = (typeof LEVELS)[number];

export const LEVEL_LABEL: Record<Level, string> = {
  low: 'Low',
  moderate: 'Moderate',
  high: 'High',
  severe: 'Severe',
  no_travel: 'No travel',
};

// Keep in sync with --color-risk-* in styles/app.css.
export const LEVEL_COLOR: Record<Level, string> = {
  low: '#5E9C76',
  moderate: '#E9B824',
  high: '#EA7A1F',
  severe: '#C8232C',
  no_travel: '#4A1050',
};

export const levelIndex = (level: Level): number => LEVELS.indexOf(level);

export const maxLevel = (a: Level, b: Level): Level => (levelIndex(a) >= levelIndex(b) ? a : b);
```

Run: `bun run test` → PASS.

- [ ] **Step 5: Tokens, fonts and component classes**

`frontend/src/styles/app.css`:

```css
@import 'tailwindcss';
@import '@fontsource/overpass/700.css';
@import '@fontsource/overpass/800.css';
@import '@fontsource/public-sans/400.css';
@import '@fontsource/public-sans/500.css';
@import '@fontsource/public-sans/600.css';
@import '@fontsource/overpass-mono/400.css';
@import '@fontsource/overpass-mono/600.css';

@theme {
  --color-paper: #eef1ee;
  --color-ink: #1e2328;
  --color-ink-soft: #4b535c;
  --color-rule: #d5dbd6;
  --color-guide: #0e6b45;
  --color-guide-deep: #0a4f33;
  --color-sign-white: #fafaf7;
  --color-interstate: #1e4fa3;
  --color-risk-low: #5e9c76;
  --color-risk-moderate: #e9b824;
  --color-risk-high: #ea7a1f;
  --color-risk-severe: #c8232c;
  --color-risk-no-travel: #4a1050;
  --font-display: 'Overpass', system-ui, sans-serif;
  --font-sans: 'Public Sans', system-ui, sans-serif;
  --font-mono: 'Overpass Mono', ui-monospace, monospace;
}

@layer base {
  html,
  body,
  #root {
    height: 100%;
  }
  body {
    background: var(--color-paper);
    color: var(--color-ink);
    font-family: var(--font-sans);
    font-size: 14px;
    -webkit-font-smoothing: antialiased;
  }
  :focus-visible {
    outline: 3px solid var(--color-interstate);
    outline-offset: 2px;
  }
  @media (prefers-reduced-motion: reduce) {
    *,
    *::before,
    *::after {
      animation-duration: 0.01ms !important;
      transition-duration: 0.01ms !important;
    }
  }
}

@layer components {
  .panel {
    @apply flex flex-col gap-5 overflow-y-auto p-5 md:p-6;
  }
  .field-label {
    @apply mb-1 block text-xs font-semibold tracking-wide text-ink-soft uppercase;
  }
  .field-input {
    @apply h-11 w-full rounded-md border border-rule bg-white px-3 text-[15px] text-ink;
  }
  .field-input:focus-visible {
    outline-offset: 0;
  }
  .btn-primary {
    @apply inline-flex h-11 items-center justify-center rounded-md bg-ink px-5 font-display text-[15px] font-bold tracking-wide text-sign-white;
  }
  .btn-primary:disabled {
    @apply opacity-50;
  }
  .chip {
    @apply inline-flex items-center gap-1.5 rounded-full border border-rule bg-white px-3 py-1 text-xs font-medium;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }
}
```

- [ ] **Step 6: Router + Query bootstrapping**

`frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider, createRouter } from '@tanstack/react-router';
import { routeTree } from './routeTree.gen';
import './styles/app.css';

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5 * 60_000, retry: 1, refetchOnWindowFocus: false } },
});

const router = createRouter({
  routeTree,
  context: { queryClient },
  defaultPreload: 'intent',
  defaultPreloadStaleTime: 0,
});

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router;
  }
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
```

`frontend/src/routes/__root.tsx` (the map stage slot is filled in Task 15):

```tsx
import { Outlet, createRootRouteWithContext } from '@tanstack/react-router';
import type { QueryClient } from '@tanstack/react-query';

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  component: Shell,
});

function Shell() {
  return (
    <div className="grid h-full grid-rows-[52svh_1fr] md:grid-cols-[420px_1fr] md:grid-rows-1">
      <aside className="order-2 min-h-0 border-rule bg-paper md:order-1 md:border-r">
        <Outlet />
      </aside>
      <main className="order-1 min-h-0 md:order-2" aria-label="Route map" />
    </div>
  );
}
```

`frontend/src/routes/index.tsx` (replaced in Task 13):

```tsx
import { createFileRoute } from '@tanstack/react-router';

export const Route = createFileRoute('/')({
  component: () => (
    <div className="panel">
      <h1 className="font-display text-xl font-extrabold">Weather-aware truck routing</h1>
    </div>
  ),
});
```

Delete the scaffold's `App.tsx`, `App.css`, `index.css` and their imports. In `index.html` set `<title>Weather-aware truck routing</title>`.

- [ ] **Step 7: Install the Aceternity Multi Step Loader through the shadcn CLI**

```bash
cd frontend
bunx shadcn@latest init --yes --base-color neutral
```

Then add the Aceternity registry to `frontend/components.json`:

```json
"registries": { "@aceternity": "https://ui.aceternity.com/registry/{name}.json" }
```

```bash
bunx shadcn@latest add @aceternity/multi-step-loader
```

If `shadcn init` rewrote `src/styles/app.css` or created `src/index.css`, restore the Step 5 file and point `components.json` → `tailwind.css` at `src/styles/app.css`. Delete any CSS variables shadcn injected that duplicate the tokens above.

- [ ] **Step 8: Verify**

Run: `bun run build` first (the router plugin generates `src/routeTree.gen.ts`), then `bun run test` → PASS, `bun run check` → no errors, `bun run dev` → open http://localhost:5173, see the heading in Overpass on paper `#EEF1EE`, empty map column on the right (≥900 px) / top (mobile).

- [ ] **Step 9: Commit**

```bash
cd /Users/Apple/Documents/repo/assesment/Spotter
git add frontend
git commit -m "chore: scaffold Vite+ React app with TanStack Router, Query, Tailwind tokens, Aceternity loader"
```

---

### Task 3: Risk classifier with load rules

**Files:**
- Create: `backend/trips/engine/risk.py`
- Test: `backend/trips/tests/test_risk.py`

**Interfaces:**
- Produces:
  - `class Level(IntEnum)`: `LOW=0, MODERATE=1, HIGH=2, SEVERE=3, NO_TRAVEL=4`; property `slug -> str` (`"low"`, …, `"no_travel"`).
  - `@dataclass(frozen=True) class Assessment: level: Level; drivers: tuple[str, ...]; load_adjusted: bool; score: float` — `drivers` ⊂ `("wind","rain","snow")`, empty when Low; `score` ∈ [0, 4] with `floor(score) == level`.
  - `def assess(*, wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment`

- [ ] **Step 1: Write the failing tests**

`backend/trips/tests/test_risk.py`:

```python
import math

import pytest

from trips.engine.risk import Level, assess

L, M, H, S, N = Level.LOW, Level.MODERATE, Level.HIGH, Level.SEVERE, Level.NO_TRAVEL


def level(wind=0.0, rain=0.0, snow=0.0, load=20_000):
    return assess(wind_mph=wind, rain_in_hr=rain, snow_in_hr=snow, load_lb=load).level


@pytest.mark.parametrize(
    "wind,expected",
    [(0, L), (24.9, L), (25, M), (34.9, M), (35, H), (44.9, H), (45, S), (54.9, S), (55, N), (80, N)],
)
def test_wind_bands_with_light_load(wind, expected):
    assert level(wind=wind, load=10_000) == expected


@pytest.mark.parametrize(
    "rain,expected",
    [(0.09, L), (0.10, M), (0.24, M), (0.25, H), (0.49, H), (0.50, S), (1.00, S), (1.01, N)],
)
def test_rain_bands(rain, expected):
    assert level(rain=rain) == expected


@pytest.mark.parametrize(
    "snow,expected",
    [(0.49, L), (0.5, M), (0.99, M), (1.0, H), (1.99, H), (2.0, S), (3.0, S), (3.01, N)],
)
def test_snow_bands(snow, expected):
    assert level(snow=snow) == expected


@pytest.mark.parametrize(
    "wind,load,expected",
    [
        (60, 1_000, N),      # >=55 is No Travel for any load
        (50, 30_000, S),     # exactly 30,000 is not "more than"
        (50, 30_001, N),     # 45-54 + >30,000 -> No Travel
        (40, 40_000, H),     # exactly 40,000 is not "more than"
        (40, 40_001, S),     # 35-44 + >40,000 -> Severe
        (40, 35_000, H),     # heavy-ish but under the 40k rule
        (30, 80_000, M),     # load rules never touch Moderate wind
    ],
)
def test_load_rules(wind, load, expected):
    assert level(wind=wind, load=load) == expected


def test_worst_condition_wins_and_is_named():
    a = assess(wind_mph=30, rain_in_hr=0.6, snow_in_hr=0, load_lb=10_000)
    assert a.level == S
    assert a.drivers == ("rain",)


def test_tied_conditions_are_all_named():
    a = assess(wind_mph=40, rain_in_hr=0.3, snow_in_hr=0, load_lb=10_000)
    assert a.level == H
    assert a.drivers == ("wind", "rain")


def test_low_has_no_drivers():
    assert assess(wind_mph=5, rain_in_hr=0, snow_in_hr=0, load_lb=10_000).drivers == ()


def test_load_adjusted_flag():
    assert assess(wind_mph=40, rain_in_hr=0, snow_in_hr=0, load_lb=45_000).load_adjusted
    assert not assess(wind_mph=40, rain_in_hr=0, snow_in_hr=0, load_lb=5_000).load_adjusted


def test_negative_inputs_are_treated_as_zero():
    assert level(wind=-3, rain=-0.1, snow=-1) == L


def test_score_floor_always_matches_level():
    for wind10 in range(0, 700, 7):
        for rain100 in (0, 10, 30, 75, 120):
            for load in (20_000, 45_000):
                a = assess(wind_mph=wind10 / 10, rain_in_hr=rain100 / 100, snow_in_hr=0, load_lb=load)
                assert math.floor(a.score) == a.level
                assert 0 <= a.score <= 4
```

- [ ] **Step 2: Run to verify failure**

Run: `cd backend && uv run pytest trips/tests/test_risk.py -v`
Expected: FAIL — `ModuleNotFoundError: trips.engine.risk`.

- [ ] **Step 3: Implement**

`backend/trips/engine/risk.py`:

```python
"""Weather risk rules from the brief. Pure functions, no I/O."""

from dataclasses import dataclass
from enum import IntEnum


class Level(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def slug(self) -> str:
        return self.name.lower()


# Lower edge of Moderate, High, Severe, No Travel. A value on an edge belongs to the higher band.
WIND_EDGES_MPH = (25.0, 35.0, 45.0, 55.0)  # No Travel is ">= 55"
RAIN_EDGES_IN_HR = (0.10, 0.25, 0.50, 1.00)  # No Travel is "> 1.00"
SNOW_EDGES_IN_HR = (0.5, 1.0, 2.0, 3.0)  # No Travel is "> 3.0"

HEAVY_LOAD_NO_TRAVEL_LB = 30_000  # with Severe wind
HEAVY_LOAD_SEVERE_LB = 40_000  # with High wind

_MAX_FRACTION = 0.99  # keeps floor(score) == level


@dataclass(frozen=True)
class Assessment:
    level: Level
    drivers: tuple[str, ...]
    load_adjusted: bool
    score: float  # level + progress through that band, 0..4, for the heatmap


def _band(value: float, edges: tuple[float, ...], *, top_inclusive: bool) -> tuple[Level, float]:
    """Return the band for value and how far (0..0.99) it sits inside that band."""
    value = max(value, 0.0)
    top = edges[-1]
    if value > top or (top_inclusive and value >= top):
        return Level.NO_TRAVEL, 0.0
    bounds = (0.0, *edges)
    for lvl in (Level.SEVERE, Level.HIGH, Level.MODERATE, Level.LOW):
        lo, hi = bounds[lvl], bounds[lvl + 1]
        if value >= lo:
            return lvl, min((value - lo) / (hi - lo), _MAX_FRACTION)
    raise AssertionError("unreachable: value >= 0")


def _apply_load_rules(wind: Level, load_lb: float) -> Level:
    if wind == Level.SEVERE and load_lb > HEAVY_LOAD_NO_TRAVEL_LB:
        return Level.NO_TRAVEL
    if wind == Level.HIGH and load_lb > HEAVY_LOAD_SEVERE_LB:
        return Level.SEVERE
    return wind


def assess(*, wind_mph: float, rain_in_hr: float, snow_in_hr: float, load_lb: float) -> Assessment:
    wind_base, wind_frac = _band(wind_mph, WIND_EDGES_MPH, top_inclusive=True)
    wind = _apply_load_rules(wind_base, load_lb)
    parts = {
        "wind": (wind, wind_frac),
        "rain": _band(rain_in_hr, RAIN_EDGES_IN_HR, top_inclusive=False),
        "snow": _band(snow_in_hr, SNOW_EDGES_IN_HR, top_inclusive=False),
    }
    level = max(lvl for lvl, _ in parts.values())
    drivers = tuple(name for name, (lvl, _) in parts.items() if lvl == level) if level else ()
    score = max(min(float(lvl) + frac, 4.0) for lvl, frac in parts.values())
    return Assessment(
        level=level, drivers=drivers, load_adjusted=wind != wind_base, score=round(score, 2)
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest trips/tests/test_risk.py -v`
Expected: PASS (all parametrized cases).

- [ ] **Step 5: Commit**

```bash
git add backend/trips/engine/risk.py backend/trips/tests/test_risk.py
git commit -m "feat(engine): classify checkpoint weather risk with load rules"
```

---

### Task 4: Geometry, route model and checkpoint placement

**Files:**
- Create: `backend/trips/engine/geo.py`, `backend/trips/engine/route.py`, `backend/trips/engine/checkpoints.py`, `backend/trips/tests/factories.py`
- Test: `backend/trips/tests/test_checkpoints.py`

**Interfaces:**
- Produces:
  - `geo.LonLat = tuple[float, float]` (lon, lat — GeoJSON order everywhere)
  - `geo.haversine_mi(a, b) -> float`, `geo.cumulative_miles(points) -> list[float]`, `geo.locate(cum, at) -> tuple[int, float]`, `geo.sample(cum, values, at) -> float`, `geo.point_at(points, cum, at) -> LonLat`, `geo.offset_mi(p, east_mi, north_mi) -> LonLat`, `geo.MI_PER_DEG_LAT = 69.0`
  - `route.RouteGeometry(label: str, points: list[LonLat], cum_miles: list[float], cum_seconds: list[float])` with properties `distance_mi`, `duration_s`
  - `checkpoints.CheckpointPosition(mile: float, lon: float, lat: float, offset_s: float)`
  - `checkpoints.checkpoint_miles(total_mi, interval_mi) -> list[float]`
  - `checkpoints.place_checkpoints(route, interval_mi) -> list[CheckpointPosition]`
  - `checkpoints.thin(route, step_mi=0.5) -> RouteGeometry`
  - `checkpoints.slice_path(route, start_mi, end_mi) -> list[LonLat]`
  - `tests.factories.straight_route(label, start, end, hours, n=21) -> RouteGeometry`

- [ ] **Step 1: Write the test factories**

`backend/trips/tests/factories.py`:

```python
from datetime import UTC, datetime, timedelta

from trips.engine.forecast import HourlySeries
from trips.engine.geo import LonLat, cumulative_miles
from trips.engine.route import RouteGeometry


def straight_route(label: str, start: LonLat, end: LonLat, hours: float, n: int = 21) -> RouteGeometry:
    """Evenly spaced straight route driven at constant speed."""
    points = [
        (start[0] + (end[0] - start[0]) * i / (n - 1), start[1] + (end[1] - start[1]) * i / (n - 1))
        for i in range(n)
    ]
    cum = cumulative_miles(points)
    seconds = [hours * 3600 * m / cum[-1] for m in cum]
    return RouteGeometry(label=label, points=points, cum_miles=cum, cum_seconds=seconds)


def floor_hour(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def flat_series(
    start: datetime, hours: int = 240, wind: float = 5.0, rain: float = 0.0, snow: float = 0.0
) -> HourlySeries:
    times = [start + timedelta(hours=h) for h in range(hours)]
    return HourlySeries(
        times=times,
        wind_mph=[wind] * hours,
        gust_mph=[wind * 1.4] * hours,
        rain_in=[rain] * hours,
        snow_in=[snow] * hours,
    )
```

(`flat_series` imports `HourlySeries` from Task 5; create `forecast.py` with just the dataclass now if executing out of order — Task 5 adds the function and tests.)

Create `backend/trips/engine/forecast.py` with only the dataclasses for now:

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HourlySeries:
    """Hourly forecast for one location. `times` are UTC and one hour apart.

    `rain_in` and `snow_in` are totals for the hour ENDING at each timestamp
    (Open-Meteo's convention), so they read directly as in/hr.
    """

    times: list[datetime]
    wind_mph: list[float | None]
    gust_mph: list[float | None]
    rain_in: list[float | None]
    snow_in: list[float | None]


@dataclass(frozen=True)
class Conditions:
    wind_mph: float
    gust_mph: float
    rain_in_hr: float
    snow_in_hr: float
```

- [ ] **Step 2: Write the failing tests**

`backend/trips/tests/test_checkpoints.py`:

```python
import pytest

from trips.engine.checkpoints import checkpoint_miles, place_checkpoints, slice_path, thin
from trips.engine.geo import haversine_mi, locate, offset_mi
from trips.engine.route import RouteGeometry
from trips.tests.factories import straight_route


def test_haversine_one_degree_of_longitude_at_equator():
    assert haversine_mi((0, 0), (1, 0)) == pytest.approx(69.09, abs=0.05)


def test_locate_handles_ends_and_middle():
    cum = [0.0, 10.0, 30.0]
    assert locate(cum, -5) == (0, 0.0)
    assert locate(cum, 20) == (1, 0.5)
    assert locate(cum, 99) == (1, 1.0)


def test_offset_moves_north_and_east():
    lon, lat = offset_mi((-100.0, 40.0), east_mi=0, north_mi=69.0)
    assert (lon, lat) == pytest.approx((-100.0, 41.0))


@pytest.mark.parametrize(
    "total,interval,expected",
    [
        (60, 25, [0, 25, 50, 60]),
        (50, 25, [0, 25, 50]),
        (0, 10, [0]),
        (0.3, 50, [0, 0.3]),
        (120, 50, [0, 50, 100, 120]),
    ],
)
def test_checkpoint_miles_always_include_origin_and_destination(total, interval, expected):
    assert checkpoint_miles(total, interval) == expected


def test_checkpoint_miles_rejects_non_positive_interval():
    with pytest.raises(ValueError):
        checkpoint_miles(100, 0)


def _two_speed_route() -> RouteGeometry:
    # 200 miles: first 100 mi take 2 h, second 100 mi take 1 h.
    return RouteGeometry(
        label="test",
        points=[(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)],
        cum_miles=[0.0, 100.0, 200.0],
        cum_seconds=[0.0, 7200.0, 10800.0],
    )


def test_checkpoint_offsets_follow_drive_time_not_distance():
    cps = place_checkpoints(_two_speed_route(), 50)
    assert [c.mile for c in cps] == [0, 50, 100, 150, 200]
    assert [c.offset_s for c in cps] == [0, 3600, 7200, 9000, 10800]
    assert (cps[1].lon, cps[1].lat) == pytest.approx((0.5, 0.0))


def test_thin_keeps_endpoints_and_spacing():
    route = straight_route("A", (-100, 40), (-98, 40), hours=2, n=400)
    t = thin(route, step_mi=5)
    assert t.points[0] == route.points[0] and t.points[-1] == route.points[-1]
    assert t.distance_mi == route.distance_mi
    gaps = [b - a for a, b in zip(t.cum_miles, t.cum_miles[1:-1])]
    assert all(g >= 5 for g in gaps)


def test_slice_path_interpolates_its_ends():
    path = slice_path(_two_speed_route(), 50, 150)
    assert path[0] == pytest.approx((0.5, 0.0))
    assert path[1] == (1.0, 0.0)
    assert path[-1] == pytest.approx((1.5, 0.0))
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest trips/tests/test_checkpoints.py -v`
Expected: FAIL — `ModuleNotFoundError: trips.engine.checkpoints`.

- [ ] **Step 4: Implement**

`backend/trips/engine/geo.py`:

```python
"""Small spherical-geometry helpers. Coordinates are (lon, lat) tuples."""

import math
from bisect import bisect_right

LonLat = tuple[float, float]

EARTH_RADIUS_MI = 3958.7613
MI_PER_DEG_LAT = 69.0


def haversine_mi(a: LonLat, b: LonLat) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def cumulative_miles(points: list[LonLat]) -> list[float]:
    out = [0.0]
    for a, b in zip(points, points[1:]):
        out.append(out[-1] + haversine_mi(a, b))
    return out


def locate(cum: list[float], at: float) -> tuple[int, float]:
    """Segment index i and fraction f so that `at` lies f of the way from cum[i] to cum[i+1]."""
    if len(cum) == 1 or at <= cum[0]:
        return 0, 0.0
    if at >= cum[-1]:
        return len(cum) - 2, 1.0
    i = bisect_right(cum, at) - 1
    span = cum[i + 1] - cum[i]
    return i, (at - cum[i]) / span if span > 0 else 0.0


def _lerp(a: float, b: float, f: float) -> float:
    return a + (b - a) * f


def sample(cum: list[float], values: list[float], at: float) -> float:
    if len(cum) == 1:
        return values[0]
    i, f = locate(cum, at)
    return _lerp(values[i], values[i + 1], f)


def point_at(points: list[LonLat], cum: list[float], at: float) -> LonLat:
    if len(points) == 1:
        return points[0]
    i, f = locate(cum, at)
    (lon1, lat1), (lon2, lat2) = points[i], points[i + 1]
    return (_lerp(lon1, lon2, f), _lerp(lat1, lat2, f))


def offset_mi(p: LonLat, east_mi: float, north_mi: float) -> LonLat:
    lon, lat = p
    return (
        lon + east_mi / (MI_PER_DEG_LAT * math.cos(math.radians(lat))),
        lat + north_mi / MI_PER_DEG_LAT,
    )
```

`backend/trips/engine/route.py`:

```python
from dataclasses import dataclass

from .geo import LonLat


@dataclass(frozen=True)
class RouteGeometry:
    """A drivable path with distance (mi) and drive time (s) accumulated at every vertex."""

    label: str
    points: list[LonLat]
    cum_miles: list[float]
    cum_seconds: list[float]

    @property
    def distance_mi(self) -> float:
        return self.cum_miles[-1]

    @property
    def duration_s(self) -> float:
        return self.cum_seconds[-1]
```

`backend/trips/engine/checkpoints.py`:

```python
"""Where along a route we sample weather, and when the truck gets there."""

import math
from dataclasses import dataclass

from .geo import LonLat, point_at, sample
from .route import RouteGeometry


@dataclass(frozen=True)
class CheckpointPosition:
    mile: float
    lon: float
    lat: float
    offset_s: float  # drive time from departure


def checkpoint_miles(total_mi: float, interval_mi: float) -> list[float]:
    """Origin, every `interval_mi`, and the destination."""
    if interval_mi <= 0:
        raise ValueError("interval_mi must be positive")
    count = math.ceil(total_mi / interval_mi)
    return [k * interval_mi for k in range(count)] + [total_mi]


def place_checkpoints(route: RouteGeometry, interval_mi: float) -> list[CheckpointPosition]:
    out = []
    for mile in checkpoint_miles(route.distance_mi, interval_mi):
        lon, lat = point_at(route.points, route.cum_miles, mile)
        offset = sample(route.cum_miles, route.cum_seconds, mile)
        out.append(CheckpointPosition(mile=round(mile, 2), lon=lon, lat=lat, offset_s=offset))
    return out


def thin(route: RouteGeometry, step_mi: float = 0.5) -> RouteGeometry:
    """Drop vertices closer than step_mi to the previous kept one; keep both ends."""
    keep = [0]
    for k in range(1, len(route.points) - 1):
        if route.cum_miles[k] - route.cum_miles[keep[-1]] >= step_mi:
            keep.append(k)
    if len(route.points) > 1:
        keep.append(len(route.points) - 1)
    return RouteGeometry(
        label=route.label,
        points=[route.points[k] for k in keep],
        cum_miles=[route.cum_miles[k] for k in keep],
        cum_seconds=[route.cum_seconds[k] for k in keep],
    )


def slice_path(route: RouteGeometry, start_mi: float, end_mi: float) -> list[LonLat]:
    inner = [p for p, m in zip(route.points, route.cum_miles) if start_mi < m < end_mi]
    return [
        point_at(route.points, route.cum_miles, start_mi),
        *inner,
        point_at(route.points, route.cum_miles, end_mi),
    ]
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest trips/tests/test_checkpoints.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/trips/engine backend/trips/tests
git commit -m "feat(engine): place checkpoints along routes with drive-time offsets"
```

---

### Task 5: Forecast lookup at a checkpoint's ETA

**Files:**
- Modify: `backend/trips/engine/forecast.py`
- Test: `backend/trips/tests/test_forecast.py`

**Interfaces:**
- Consumes: `HourlySeries`, `Conditions` (Task 4 stub).
- Produces: `conditions_at(series: HourlySeries, when: datetime) -> Conditions | None` — `None` when `when` is outside the series or any needed value is missing.

Rule: wind and gusts are instantaneous → linear interpolation between the two surrounding hours. Rain and snow at timestamp T are the total for (T−1h, T] → use the value at `ceil(hour)`, i.e. the hour that contains the ETA.

- [ ] **Step 1: Write the failing tests**

`backend/trips/tests/test_forecast.py`:

```python
from datetime import UTC, datetime, timedelta

import pytest

from trips.engine.forecast import HourlySeries, conditions_at

T0 = datetime(2026, 10, 14, 0, tzinfo=UTC)


def series(**overrides):
    base = dict(
        times=[T0 + timedelta(hours=h) for h in range(4)],
        wind_mph=[10.0, 20.0, 30.0, 40.0],
        gust_mph=[15.0, 25.0, 35.0, 45.0],
        rain_in=[0.0, 0.2, 0.4, 0.0],
        snow_in=[0.0, 0.0, 0.0, 0.0],
    )
    base.update(overrides)
    return HourlySeries(**base)


def test_between_hours_wind_interpolates_and_rain_uses_containing_hour():
    c = conditions_at(series(), T0 + timedelta(hours=1, minutes=30))
    assert c.wind_mph == pytest.approx(25.0)
    assert c.gust_mph == pytest.approx(30.0)
    assert c.rain_in_hr == 0.4  # hour ending 02:00 contains 01:30


def test_on_the_hour_uses_that_hour():
    c = conditions_at(series(), T0 + timedelta(hours=1))
    assert c.wind_mph == 20.0
    assert c.rain_in_hr == 0.2


def test_tiny_float_noise_past_the_hour_does_not_jump_an_hour():
    c = conditions_at(series(), T0 + timedelta(hours=1, microseconds=3))
    assert c.rain_in_hr == 0.2


def test_last_timestamp_is_inside_the_series():
    assert conditions_at(series(), T0 + timedelta(hours=3)).wind_mph == 40.0


@pytest.mark.parametrize("delta", [timedelta(minutes=-1), timedelta(hours=3, minutes=1)])
def test_outside_the_series_returns_none(delta):
    assert conditions_at(series(), T0 + delta) is None


def test_missing_values_return_none():
    s = series(wind_mph=[10.0, None, 30.0, 40.0])
    assert conditions_at(s, T0 + timedelta(minutes=30)) is None


def test_missing_gust_falls_back_to_wind():
    s = series(gust_mph=[None, None, None, None])
    assert conditions_at(s, T0).gust_mph == 10.0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest trips/tests/test_forecast.py -v`
Expected: FAIL — `ImportError: cannot import name 'conditions_at'`.

- [ ] **Step 3: Implement — append to `backend/trips/engine/forecast.py`**

```python
import math  # add to the imports at the top of the file


def conditions_at(series: HourlySeries, when: datetime) -> Conditions | None:
    """Weather the truck meets at `when`, or None if the forecast doesn't cover it."""
    if not series.times:
        return None
    hours = round((when - series.times[0]).total_seconds() / 3600, 6)
    last = len(series.times) - 1
    if hours < 0 or hours > last:
        return None
    i, frac = math.floor(hours), hours - math.floor(hours)
    containing = math.ceil(hours)

    def instantaneous(values: list[float | None]) -> float | None:
        a, b = values[i], values[min(i + 1, last)]
        if a is None or b is None:
            return None
        return a + (b - a) * frac

    wind = instantaneous(series.wind_mph)
    gust = instantaneous(series.gust_mph)
    rain = series.rain_in[containing]
    snow = series.snow_in[containing]
    if wind is None or rain is None or snow is None:
        return None
    return Conditions(
        wind_mph=round(wind, 1),
        gust_mph=round(gust if gust is not None else wind, 1),
        rain_in_hr=rain,
        snow_in_hr=snow,
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest trips/tests/test_forecast.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/trips/engine/forecast.py backend/trips/tests/test_forecast.py
git commit -m "feat(engine): read forecast at checkpoint ETA with correct precip-hour semantics"
```

---

### Task 6: Route summaries and recommendation

**Files:**
- Create: `backend/trips/engine/scoring.py`
- Test: `backend/trips/tests/test_scoring.py`

**Interfaces:**
- Consumes: `Level` (Task 3).
- Produces:
  - `segment_levels(levels: list[Level]) -> list[Level]` — segment between checkpoints k and k+1 takes the worse of the two (conservative).
  - `RouteSummary(miles_by_level: dict[Level, float], avg_risk: float, max_level: Level)`; `.miles(level) -> float`
  - `summarize(miles: list[float], levels: list[Level]) -> RouteSummary` — `avg_risk` is the distance-weighted mean level (0–4).
  - `Candidate(route_id: str, summary: RouteSummary, duration_s: float)`
  - `Recommendation(route_id: str, reason: str, ranking: list[str], all_blocked: bool)`
  - `recommend(candidates: list[Candidate]) -> Recommendation`

- [ ] **Step 1: Write the failing tests**

`backend/trips/tests/test_scoring.py`:

```python
import pytest

from trips.engine.risk import Level
from trips.engine.scoring import Candidate, RouteSummary, recommend, segment_levels, summarize

L, M, H, S, N = Level.LOW, Level.MODERATE, Level.HIGH, Level.SEVERE, Level.NO_TRAVEL


def summary(nt=0.0, sev=0.0, high=0.0, avg=0.0, low=100.0):
    by = {L: low, M: 0.0, H: high, S: sev, N: nt}
    return RouteSummary(miles_by_level=by, avg_risk=avg, max_level=max(k for k, v in by.items() if v) if any(by.values()) else L)


def test_segment_takes_worse_endpoint():
    assert segment_levels([L, H, L, L]) == [H, H, L]


def test_summarize_attributes_miles_per_segment():
    s = summarize([0, 25, 50, 60], [L, H, L, L])
    assert s.miles(H) == 50
    assert s.miles(L) == 10
    assert s.avg_risk == pytest.approx(100 / 60, abs=1e-3)
    assert s.max_level == H


def test_summarize_single_checkpoint_route():
    s = summarize([0], [M])
    assert sum(s.miles_by_level.values()) == 0
    assert s.avg_risk == 1.0


def test_fewest_severe_miles_wins_over_speed():
    rec = recommend([
        Candidate("A", summary(sev=10), duration_s=100),
        Candidate("B", summary(high=50, avg=1.0), duration_s=200),
    ])
    assert rec.route_id == "B"
    assert rec.ranking == ["B", "A"]
    assert rec.reason == "Fewest severe miles: 0 vs 10 on Route A."


def test_no_travel_outranks_severe():
    rec = recommend([
        Candidate("A", summary(nt=5), duration_s=100),
        Candidate("B", summary(sev=30), duration_s=100),
    ])
    assert rec.route_id == "B"
    assert not rec.all_blocked


def test_high_miles_break_severe_tie():
    rec = recommend([
        Candidate("A", summary(high=40), duration_s=100),
        Candidate("B", summary(high=12.5), duration_s=300),
    ])
    assert rec.route_id == "B"
    assert rec.reason == "Fewest high-risk miles: 12.5 vs 40 on Route A."


def test_average_risk_breaks_high_tie():
    rec = recommend([
        Candidate("A", summary(avg=0.9), duration_s=100),
        Candidate("B", summary(avg=0.4), duration_s=300),
    ])
    assert rec.route_id == "B"
    assert rec.reason == "Lowest average risk: 0.40 vs 0.90 on Route A."


def test_equal_risk_picks_faster():
    rec = recommend([
        Candidate("A", summary(), duration_s=9000),
        Candidate("B", summary(), duration_s=7200),
    ])
    assert rec.route_id == "B"
    assert rec.reason == "Same risk as Route A, 30 min faster."


def test_all_blocked_still_ranks_least_bad():
    rec = recommend([
        Candidate("A", summary(nt=40), duration_s=100),
        Candidate("B", summary(nt=5), duration_s=100),
    ])
    assert rec.route_id == "B"
    assert rec.all_blocked


def test_single_route():
    rec = recommend([Candidate("A", summary(), duration_s=1)])
    assert rec.reason == "Only route available."


def test_empty_candidates_raise():
    with pytest.raises(ValueError):
        recommend([])
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest trips/tests/test_scoring.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`backend/trips/engine/scoring.py`:

```python
"""Per-route risk totals and the recommendation order from the brief."""

from dataclasses import dataclass
from itertools import pairwise

from .risk import Level


@dataclass(frozen=True)
class RouteSummary:
    miles_by_level: dict[Level, float]
    avg_risk: float  # distance-weighted mean level, 0..4
    max_level: Level

    def miles(self, level: Level) -> float:
        return self.miles_by_level[level]


@dataclass(frozen=True)
class Candidate:
    route_id: str
    summary: RouteSummary
    duration_s: float


@dataclass(frozen=True)
class Recommendation:
    route_id: str
    reason: str
    ranking: list[str]
    all_blocked: bool


def segment_levels(levels: list[Level]) -> list[Level]:
    """The stretch between two checkpoints is as risky as the worse of them."""
    return [max(a, b) for a, b in pairwise(levels)]


def summarize(miles: list[float], levels: list[Level]) -> RouteSummary:
    by_level = {lvl: 0.0 for lvl in Level}
    total = weighted = 0.0
    for (start, end), lvl in zip(pairwise(miles), segment_levels(levels)):
        length = end - start
        by_level[lvl] += length
        total += length
        weighted += length * lvl
    worst = max(levels, default=Level.LOW)
    avg = weighted / total if total > 0 else float(worst)
    return RouteSummary(
        miles_by_level={k: round(v, 2) for k, v in by_level.items()},
        avg_risk=round(avg, 3),
        max_level=worst,
    )


def _rank_key(c: Candidate) -> tuple[float, float, float, float, float]:
    s = c.summary
    return (
        round(s.miles(Level.NO_TRAVEL), 1),
        round(s.miles(Level.SEVERE), 1),
        round(s.miles(Level.HIGH), 1),
        round(s.avg_risk, 2),
        c.duration_s,
    )


def _mi(x: float) -> str:
    return f"{x:,.1f}".removesuffix(".0")


def _reason(best: Candidate, runner_up: Candidate | None) -> str:
    if runner_up is None:
        return "Only route available."
    b, o, other = _rank_key(best), _rank_key(runner_up), runner_up.route_id
    if b[0] != o[0]:
        return f"Fewest No Travel miles: {_mi(b[0])} vs {_mi(o[0])} on Route {other}."
    if b[1] != o[1]:
        return f"Fewest severe miles: {_mi(b[1])} vs {_mi(o[1])} on Route {other}."
    if b[2] != o[2]:
        return f"Fewest high-risk miles: {_mi(b[2])} vs {_mi(o[2])} on Route {other}."
    if b[3] != o[3]:
        return f"Lowest average risk: {b[3]:.2f} vs {o[3]:.2f} on Route {other}."
    minutes = round((o[4] - b[4]) / 60)
    if minutes > 0:
        return f"Same risk as Route {other}, {minutes} min faster."
    return f"Ties with Route {other} on risk and time."


def recommend(candidates: list[Candidate]) -> Recommendation:
    if not candidates:
        raise ValueError("recommend() needs at least one route")
    ordered = sorted(candidates, key=_rank_key)
    return Recommendation(
        route_id=ordered[0].route_id,
        reason=_reason(ordered[0], ordered[1] if len(ordered) > 1 else None),
        ranking=[c.route_id for c in ordered],
        all_blocked=all(c.summary.miles(Level.NO_TRAVEL) > 0 for c in candidates),
    )
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest trips/tests/test_scoring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/trips/engine/scoring.py backend/trips/tests/test_scoring.py
git commit -m "feat(engine): summarize risk miles and recommend safest route"
```

---

### Task 7: Open-Meteo provider with SQLite cache

**Files:**
- Create: `backend/trips/errors.py`, `backend/trips/providers/http.py`, `backend/trips/providers/open_meteo.py`
- Modify: `backend/trips/models.py` (add `ForecastCache`), new migration
- Test: `backend/trips/tests/test_open_meteo.py`

**Interfaces:**
- Consumes: `HourlySeries` (Task 4/5), `LonLat`.
- Produces:
  - `errors.TripError(message)` with `.message`, `.status = 422`; `errors.NoRouteError(TripError)` (422); `errors.ProviderError(TripError)` (502).
  - `http.http_client() -> httpx.Client`; `http.client_or_new(client) -> ContextManager[httpx.Client]`
  - `open_meteo.OPEN_METEO_URL`, `open_meteo.fetch_series(points: list[LonLat], *, client=None, now=None) -> list[HourlySeries]` — same order and length as `points`; locations are snapped to a 0.05° grid, cached 1 h, fetched in batches of 50; window is 1 past day + 10 forecast days.
  - `models.ForecastCache(lat_key, lon_key, fetched_at, payload)`

- [ ] **Step 1: Write the failing tests**

`backend/trips/tests/test_open_meteo.py`:

```python
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from trips.errors import ProviderError
from trips.models import ForecastCache
from trips.providers.open_meteo import OPEN_METEO_URL, fetch_series


def _location(lat: float, lon: float) -> dict:
    return {
        "latitude": lat,
        "longitude": lon,
        "hourly": {
            "time": ["2026-10-14T00:00", "2026-10-14T01:00"],
            "wind_speed_10m": [12.0, 14.0],
            "wind_gusts_10m": [20.0, 22.0],
            "rain": [0.05, 0.10],
            "showers": [0.05, None],
            "snowfall": [0.0, 0.2],
        },
    }


def _handler(request: httpx.Request) -> httpx.Response:
    q = parse_qs(urlparse(str(request.url)).query)
    lats = [float(x) for x in q["latitude"][0].split(",")]
    lons = [float(x) for x in q["longitude"][0].split(",")]
    body = [_location(a, o) for a, o in zip(lats, lons)]
    return httpx.Response(200, json=body if len(body) > 1 else body[0])


@pytest.mark.django_db
@respx.mock
def test_fetches_unique_cells_once_and_caches():
    route = respx.get(OPEN_METEO_URL).mock(side_effect=_handler)
    points = [(-87.63, 41.88), (-104.99, 39.74), (-87.631, 41.881)]  # 1st and 3rd share a cell

    series = fetch_series(points)

    assert len(series) == 3
    assert route.call_count == 1
    q = parse_qs(urlparse(str(route.calls[0].request.url)).query)
    assert len(q["latitude"][0].split(",")) == 2
    assert q["wind_speed_unit"] == ["mph"] and q["precipitation_unit"] == ["inch"]
    assert series[0] == series[2]
    assert ForecastCache.objects.count() == 2

    fetch_series(points)
    assert route.call_count == 1  # served from cache


@pytest.mark.django_db
@respx.mock
def test_rain_includes_showers_and_times_are_utc():
    respx.get(OPEN_METEO_URL).mock(side_effect=_handler)
    s = fetch_series([(-87.63, 41.88)])[0]
    assert s.rain_in == [pytest.approx(0.10), pytest.approx(0.10)]  # None showers count as 0
    assert s.snow_in == [0.0, 0.2]
    assert s.times[0].tzinfo is not None and s.times[0].utcoffset().total_seconds() == 0


@pytest.mark.django_db
@respx.mock
def test_batches_of_fifty():
    route = respx.get(OPEN_METEO_URL).mock(side_effect=_handler)
    points = [(-100 + i * 0.2, 40.0) for i in range(120)]
    assert len(fetch_series(points)) == 120
    assert route.call_count == 3


@pytest.mark.django_db
@respx.mock
def test_upstream_failure_is_a_provider_error():
    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(ProviderError) as exc:
        fetch_series([(-87.63, 41.88)])
    assert exc.value.status == 502
    assert "weather service" in exc.value.message.lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest trips/tests/test_open_meteo.py -v`
Expected: FAIL — `ModuleNotFoundError: trips.errors`.

- [ ] **Step 3: Implement errors, http client, model, provider**

`backend/trips/errors.py`:

```python
class TripError(Exception):
    """A problem the person planning the trip can act on. `message` is shown to them."""

    status = 422

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NoRouteError(TripError):
    status = 422


class ProviderError(TripError):
    status = 502
```

`backend/trips/providers/http.py`:

```python
from contextlib import nullcontext

import httpx
from django.conf import settings


def http_client() -> httpx.Client:
    return httpx.Client(
        timeout=httpx.Timeout(20.0, connect=5.0),
        headers={"User-Agent": settings.HTTP_USER_AGENT},
    )


def client_or_new(client: httpx.Client | None):
    """Use the caller's client without closing it, or open and close a new one."""
    return nullcontext(client) if client is not None else http_client()
```

`backend/trips/models.py`:

```python
import uuid

from django.db import models


class ForecastCache(models.Model):
    """Hourly forecast for one 0.05° cell, reused for an hour."""

    lat_key = models.FloatField()
    lon_key = models.FloatField()
    fetched_at = models.DateTimeField()
    payload = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["lat_key", "lon_key"], name="forecast_cell_unique")
        ]
```

(`uuid` is used by `Trip` in Task 10.)

`backend/trips/providers/open_meteo.py`:

```python
"""Hourly forecasts from Open-Meteo (no API key)."""

from datetime import UTC, datetime, timedelta
from itertools import batched

import httpx
from django.utils import timezone

from trips.engine.forecast import HourlySeries
from trips.engine.geo import LonLat
from trips.errors import ProviderError
from trips.models import ForecastCache

from .http import client_or_new

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY_FIELDS = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"
CELL_DEG = 0.05  # ~3.5 mi; finer than the model grid, so snapping loses nothing
BATCH_SIZE = 50
CACHE_TTL = timedelta(hours=1)

Key = tuple[float, float]


def cell_key(point: LonLat) -> Key:
    lon, lat = point
    return (round(round(lat / CELL_DEG) * CELL_DEG, 2), round(round(lon / CELL_DEG) * CELL_DEG, 2))


def fetch_series(
    points: list[LonLat], *, client: httpx.Client | None = None, now: datetime | None = None
) -> list[HourlySeries]:
    now = now or timezone.now()
    keys = [cell_key(p) for p in points]
    wanted = set(keys)
    payloads: dict[Key, dict] = {
        (row.lat_key, row.lon_key): row.payload
        for row in ForecastCache.objects.filter(
            fetched_at__gte=now - CACHE_TTL, lat_key__in={k[0] for k in wanted}
        )
        if (row.lat_key, row.lon_key) in wanted
    }
    missing = [k for k in dict.fromkeys(keys) if k not in payloads]
    if missing:
        with client_or_new(client) as http:
            for batch in batched(missing, BATCH_SIZE):
                for key, payload in zip(batch, _request(http, batch)):
                    ForecastCache.objects.update_or_create(
                        lat_key=key[0],
                        lon_key=key[1],
                        defaults={"payload": payload, "fetched_at": now},
                    )
                    payloads[key] = payload
    series = {k: _to_series(payloads[k]) for k in wanted}
    return [series[k] for k in keys]


def _request(http: httpx.Client, batch: tuple[Key, ...]) -> list[dict]:
    params = {
        "latitude": ",".join(str(lat) for lat, _ in batch),
        "longitude": ",".join(str(lon) for _, lon in batch),
        "hourly": HOURLY_FIELDS,
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "GMT",
        "past_days": 1,
        "forecast_days": 10,
    }
    try:
        response = http.get(OPEN_METEO_URL, params=params)
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ProviderError(
            "The weather service didn't respond. Try again in a minute."
        ) from exc
    locations = data if isinstance(data, list) else [data]
    return [_compact(loc["hourly"]) for loc in locations]


def _compact(hourly: dict) -> dict:
    rain = hourly["rain"]
    showers = hourly.get("showers") or [0.0] * len(rain)
    return {
        "time": hourly["time"],
        "wind": hourly["wind_speed_10m"],
        "gust": hourly["wind_gusts_10m"],
        "rain": [None if r is None else r + (s or 0.0) for r, s in zip(rain, showers)],
        "snow": hourly["snowfall"],
    }


def _to_series(payload: dict) -> HourlySeries:
    return HourlySeries(
        times=[datetime.fromisoformat(t).replace(tzinfo=UTC) for t in payload["time"]],
        wind_mph=payload["wind"],
        gust_mph=payload["gust"],
        rain_in=payload["rain"],
        snow_in=payload["snow"],
    )
```

Make the migration:

```bash
uv run python manage.py makemigrations trips
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest trips/tests/test_open_meteo.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/trips
git commit -m "feat(providers): fetch hourly Open-Meteo forecasts with batching and SQLite cache"
```

---

### Task 8: Valhalla truck routes with guaranteed alternates

**Files:**
- Create: `backend/trips/providers/valhalla.py`
- Test: `backend/trips/tests/test_valhalla.py`

**Interfaces:**
- Consumes: `RouteGeometry`, geo helpers, `client_or_new`, `NoRouteError`, `ProviderError`.
- Produces:
  - `fetch_routes(origin: LonLat, destination: LonLat, load_lb: float, *, want: int = 3, client=None) -> list[RouteGeometry]` — Valhalla's best route first; then its alternates; then detours through via points either side of the trip, accepted only if ≤1.6× the fastest drive time and ≤80% overlapping existing routes.
  - `overlap(candidate: RouteGeometry, existing: list[RouteGeometry]) -> float`
  - `detour_points(origin, destination) -> Iterator[LonLat]`
  - `parse_trip(trip: dict) -> RouteGeometry`

- [ ] **Step 1: Write the failing tests**

`backend/trips/tests/test_valhalla.py`:

```python
import json
import math

import httpx
import polyline
import pytest
import respx
from django.conf import settings

from trips.engine.geo import haversine_mi
from trips.errors import NoRouteError, ProviderError
from trips.providers.valhalla import fetch_routes, parse_trip

CHI = (-87.63, 41.88)
DEN = (-104.99, 39.74)
MID_LAT = (CHI[1] + DEN[1]) / 2


def bent_line(a, b, bend_deg=0.0, n=60):
    """(lat, lon) pairs from a to b bowed north (+) or south (-) by bend_deg at the middle."""
    return [
        (
            a[1] + (b[1] - a[1]) * t + bend_deg * math.sin(math.pi * t),
            a[0] + (b[0] - a[0]) * t,
        )
        for t in (i / (n - 1) for i in range(n))
    ]


def trip_json(latlons, hours, name="I 80 W"):
    length = sum(haversine_mi((a[1], a[0]), (b[1], b[0])) for a, b in zip(latlons, latlons[1:]))
    last = len(latlons) - 1
    return {
        "legs": [
            {
                "shape": polyline.encode(latlons, 6),
                "maneuvers": [
                    {"begin_shape_index": 0, "end_shape_index": last // 2, "time": hours * 1800,
                     "length": length / 2, "street_names": [name]},
                    {"begin_shape_index": last // 2, "end_shape_index": last, "time": hours * 1800,
                     "length": length / 2, "street_names": ["I 76"]},
                    {"begin_shape_index": last, "end_shape_index": last, "time": 0, "length": 0},
                ],
            }
        ],
        "summary": {"length": length * 1.01, "time": hours * 3600},
    }


def body_of(request):
    return json.loads(request.content)


def test_parse_trip_spreads_maneuver_time_by_distance_and_scales_to_summary():
    route = parse_trip(trip_json(bent_line(CHI, DEN), hours=15))
    assert route.points[0] == pytest.approx(CHI, abs=1e-5)
    assert route.duration_s == pytest.approx(15 * 3600)
    assert route.distance_mi == pytest.approx(
        trip_json(bent_line(CHI, DEN), 15)["summary"]["length"]
    )
    assert all(b >= a for a, b in zip(route.cum_seconds, route.cum_seconds[1:]))
    assert route.label == "I 80 W · I 76"


@respx.mock
def test_uses_valhalla_alternates_when_it_returns_enough():
    call = respx.post(settings.VALHALLA_URL).mock(return_value=httpx.Response(200, json={
        "trip": trip_json(bent_line(CHI, DEN), 15),
        "alternates": [
            {"trip": trip_json(bent_line(CHI, DEN, 1.5), 16)},
            {"trip": trip_json(bent_line(CHI, DEN, -1.5), 16.5)},
        ],
    }))
    routes = fetch_routes(CHI, DEN, 40_000)
    assert len(routes) == 3
    assert call.call_count == 1
    sent = body_of(call.calls[0].request)
    assert sent["costing"] == "truck"
    assert sent["costing_options"]["truck"]["weight"] == pytest.approx(18.14, abs=0.01)
    assert sent["alternates"] == 2 and sent["units"] == "miles"


def _detour_handler(detour_hours):
    def handler(request):
        body = body_of(request)
        if len(body["locations"]) == 2:
            return httpx.Response(200, json={
                "trip": trip_json(bent_line(CHI, DEN), 15),
                "alternates": [{"trip": trip_json(bent_line(CHI, DEN, 1.5), 16)}],
            })
        via = body["locations"][1]
        assert via["type"] == "through"
        bend = 3.0 if via["lat"] > MID_LAT else -3.0
        return httpx.Response(200, json={"trip": trip_json(bent_line(CHI, DEN, bend), detour_hours)})
    return handler


@respx.mock
def test_tops_up_with_a_detour_when_valhalla_returns_too_few():
    call = respx.post(settings.VALHALLA_URL).mock(side_effect=_detour_handler(detour_hours=18))
    routes = fetch_routes(CHI, DEN, 40_000)
    assert len(routes) == 3
    assert call.call_count == 2


@respx.mock
def test_rejects_detours_that_are_far_slower():
    call = respx.post(settings.VALHALLA_URL).mock(side_effect=_detour_handler(detour_hours=40))
    routes = fetch_routes(CHI, DEN, 40_000)
    assert len(routes) == 2
    assert call.call_count == 5  # primary + four detour attempts


@respx.mock
def test_rejects_detours_that_duplicate_an_existing_route():
    def handler(request):
        if len(body_of(request)["locations"]) == 2:
            return httpx.Response(200, json={"trip": trip_json(bent_line(CHI, DEN), 15)})
        return httpx.Response(200, json={"trip": trip_json(bent_line(CHI, DEN), 15.2)})
    respx.post(settings.VALHALLA_URL).mock(side_effect=handler)
    assert len(fetch_routes(CHI, DEN, 40_000)) == 1


@respx.mock
def test_unroutable_detour_is_skipped():
    def handler(request):
        if len(body_of(request)["locations"]) == 2:
            return httpx.Response(200, json={"trip": trip_json(bent_line(CHI, DEN), 15)})
        return httpx.Response(400, json={"error_code": 171, "error": "No suitable edges"})
    respx.post(settings.VALHALLA_URL).mock(side_effect=handler)
    assert len(fetch_routes(CHI, DEN, 40_000)) == 1


@respx.mock
def test_no_path_raises_no_route():
    respx.post(settings.VALHALLA_URL).mock(
        return_value=httpx.Response(400, json={"error_code": 442, "error": "No path could be found"})
    )
    with pytest.raises(NoRouteError):
        fetch_routes(CHI, (-157.85, 21.30), 40_000)


@respx.mock
def test_server_error_is_provider_error():
    respx.post(settings.VALHALLA_URL).mock(return_value=httpx.Response(500))
    with pytest.raises(ProviderError):
        fetch_routes(CHI, DEN, 40_000)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest trips/tests/test_valhalla.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`backend/trips/providers/valhalla.py`:

```python
"""Truck routes from Valhalla (FOSSGIS public server, no key)."""

import math
from collections import Counter
from collections.abc import Iterator

import httpx
import polyline
from django.conf import settings

from trips.engine.geo import (
    MI_PER_DEG_LAT,
    LonLat,
    cumulative_miles,
    haversine_mi,
    offset_mi,
    point_at,
)
from trips.engine.route import RouteGeometry
from trips.errors import NoRouteError, ProviderError

from .http import client_or_new

LB_TO_TONNES = 0.000453592
MAX_DETOUR_RATIO = 1.6  # a detour may take at most 60% longer than the fastest route
MAX_OVERLAP = 0.8  # share of a candidate already covered by existing routes
DETOUR_FRACTIONS = (0.15, -0.15, 0.30, -0.30)  # sideways offset as a share of trip length
OVERLAP_CELL_DEG = 0.01  # ~0.7 mi


def fetch_routes(
    origin: LonLat,
    destination: LonLat,
    load_lb: float,
    *,
    want: int = 3,
    client: httpx.Client | None = None,
) -> list[RouteGeometry]:
    with client_or_new(client) as http:
        data = _post(http, _body([origin, destination], load_lb, alternates=want - 1))
        routes: list[RouteGeometry] = []
        for trip in [data["trip"], *(alt["trip"] for alt in data.get("alternates", []))]:
            candidate = parse_trip(trip)
            if not routes or overlap(candidate, routes) <= MAX_OVERLAP:
                routes.append(candidate)

        for via in detour_points(origin, destination):
            if len(routes) >= want:
                break
            try:
                detour = _post(http, _body([origin, via, destination], load_lb, alternates=0))
            except NoRouteError:
                continue
            candidate = parse_trip(detour["trip"])
            fastest = min(r.duration_s for r in routes)
            if candidate.duration_s <= MAX_DETOUR_RATIO * fastest and overlap(candidate, routes) <= MAX_OVERLAP:
                routes.append(candidate)
    return routes[:want]


def _body(points: list[LonLat], load_lb: float, *, alternates: int) -> dict:
    locations = [{"lat": lat, "lon": lon} for lon, lat in points]
    if len(locations) == 3:
        locations[1]["type"] = "through"  # pass by, no stop, no extra leg
    return {
        "locations": locations,
        "costing": "truck",
        "costing_options": {"truck": {"weight": round(load_lb * LB_TO_TONNES, 2)}},
        "units": "miles",
        "alternates": alternates,
        "directions_options": {"units": "miles"},
    }


def _post(http: httpx.Client, body: dict) -> dict:
    try:
        response = http.post(settings.VALHALLA_URL, json=body)
    except httpx.HTTPError as exc:
        raise ProviderError("The routing service didn't respond. Try again in a minute.") from exc
    if response.status_code == 400:
        raise NoRouteError(
            "No truck route connects these places. Pick a start and destination reachable by road."
        )
    if response.status_code != 200:
        raise ProviderError("The routing service is having trouble. Try again in a minute.")
    return response.json()


def parse_trip(trip: dict) -> RouteGeometry:
    points: list[LonLat] = []
    seconds: list[float] = []
    names: Counter[str] = Counter()
    for leg in trip["legs"]:
        shape = [(lon, lat) for lat, lon in polyline.decode(leg["shape"], 6)]
        cum = cumulative_miles(shape)
        leg_seconds = [0.0] * len(shape)
        for m in leg["maneuvers"]:
            begin, end = m["begin_shape_index"], m["end_shape_index"]
            span = cum[end] - cum[begin]
            for k in range(begin + 1, end + 1):
                share = (cum[k] - cum[k - 1]) / span if span > 0 else 1 / (end - begin)
                leg_seconds[k] = leg_seconds[k - 1] + m["time"] * share
            for name in m.get("street_names", []):
                names[name] += m["length"]
        if points:  # each leg starts where the previous ended
            shape, leg_seconds = shape[1:], leg_seconds[1:]
        start = seconds[-1] if seconds else 0.0
        points += shape
        seconds += [start + s for s in leg_seconds]

    cum_miles = cumulative_miles(points)
    summary = trip["summary"]
    mile_scale = summary["length"] / cum_miles[-1] if cum_miles[-1] > 0 else 1.0
    time_scale = summary["time"] / seconds[-1] if seconds[-1] > 0 else 1.0
    return RouteGeometry(
        label=" · ".join(name for name, _ in names.most_common(2)) or "Local roads",
        points=points,
        cum_miles=[m * mile_scale for m in cum_miles],
        cum_seconds=[s * time_scale for s in seconds],
    )


def detour_points(origin: LonLat, destination: LonLat) -> Iterator[LonLat]:
    """Via points on either side of the straight line, near its middle."""
    mid = ((origin[0] + destination[0]) / 2, (origin[1] + destination[1]) / 2)
    east = (destination[0] - origin[0]) * MI_PER_DEG_LAT * math.cos(math.radians(mid[1]))
    north = (destination[1] - origin[1]) * MI_PER_DEG_LAT
    norm = math.hypot(east, north) or 1.0
    side_east, side_north = -north / norm, east / norm
    trip_mi = haversine_mi(origin, destination)
    for fraction in DETOUR_FRACTIONS:
        distance = math.copysign(min(max(abs(fraction) * trip_mi, 10.0), 150.0), fraction)
        yield offset_mi(mid, side_east * distance, side_north * distance)


def _samples(route: RouteGeometry, step_mi: float) -> list[LonLat]:
    count = int(route.distance_mi / step_mi) + 1
    return [point_at(route.points, route.cum_miles, k * step_mi) for k in range(count)]


def _cell(p: LonLat) -> tuple[int, int]:
    return (round(p[1] / OVERLAP_CELL_DEG), round(p[0] / OVERLAP_CELL_DEG))


def overlap(candidate: RouteGeometry, existing: list[RouteGeometry]) -> float:
    covered: set[tuple[int, int]] = set()
    for route in existing:
        for p in _samples(route, 0.5):
            r, c = _cell(p)
            covered.update((r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1))
    samples = _samples(candidate, 2.0)
    return sum(_cell(p) in covered for p in samples) / len(samples)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest trips/tests/test_valhalla.py -v`
Expected: PASS. If `test_tops_up_with_a_detour…` fails on overlap, print `overlap()` for the bend-3 route vs bends 0 and 1.5 — it should be well under 0.8 (only the shared ends overlap).

- [ ] **Step 5: Live smoke check (network)**

```bash
uv run python -c "
import django, os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings'; django.setup()
from trips.providers.valhalla import fetch_routes
rs = fetch_routes((-87.63, 41.88), (-104.99, 39.74), 40000)
print([(r.label, round(r.distance_mi), round(r.duration_s/3600, 1)) for r in rs])"
```

Expected: 3 tuples, distances ~1,000–1,150 mi.

- [ ] **Step 6: Commit**

```bash
git add backend/trips/providers/valhalla.py backend/trips/tests/test_valhalla.py
git commit -m "feat(providers): fetch 3 distinct Valhalla truck routes with detour fallback"
```

---

### Task 9: Geocoding endpoint (Photon)

**Files:**
- Create: `backend/trips/providers/photon.py`
- Modify: `backend/trips/api.py`
- Test: `backend/trips/tests/test_geocode.py`

**Interfaces:**
- Produces: `photon.PHOTON_URL`; `photon.search_places(q: str, *, client=None) -> list[dict]` returning `{"label", "lat", "lon"}`; `GET /api/geocode?q=` → that list; registers the `TripError` exception handler on `api`.

- [ ] **Step 1: Write the failing tests**

`backend/trips/tests/test_geocode.py`:

```python
import httpx
import respx

from trips.providers.photon import PHOTON_URL

DENVER = {
    "type": "FeatureCollection",
    "features": [
        {
            "properties": {"name": "Denver", "state": "Colorado", "countrycode": "US", "city": "Denver"},
            "geometry": {"type": "Point", "coordinates": [-104.984862, 39.7392364]},
        }
    ],
}


@respx.mock
def test_geocode_returns_labelled_places(client):
    route = respx.get(PHOTON_URL).mock(return_value=httpx.Response(200, json=DENVER))
    response = client.get("/api/geocode", {"q": "denver"})
    assert response.status_code == 200
    assert response.json() == [{"label": "Denver, Colorado, US", "lat": 39.73924, "lon": -104.98486}]
    assert "bbox" in str(route.calls[0].request.url)


@respx.mock
def test_short_queries_skip_the_network(client):
    route = respx.get(PHOTON_URL)
    assert client.get("/api/geocode", {"q": "de"}).json() == []
    assert route.call_count == 0


@respx.mock
def test_geocoder_outage_is_502_with_message(client):
    respx.get(PHOTON_URL).mock(return_value=httpx.Response(500))
    response = client.get("/api/geocode", {"q": "denver co"})
    assert response.status_code == 502
    assert "place search" in response.json()["detail"].lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest trips/tests/test_geocode.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`backend/trips/providers/photon.py`:

```python
"""Place search via Photon (komoot, OSM data, no key)."""

import httpx
from django.core.cache import cache

from trips.errors import ProviderError

from .http import client_or_new

PHOTON_URL = "https://photon.komoot.io/api/"
NORTH_AMERICA_BBOX = "-170,15,-50,72"
CACHE_SECONDS = 24 * 3600


def search_places(q: str, *, client: httpx.Client | None = None) -> list[dict]:
    q = q.strip()
    if len(q) < 3:
        return []
    cache_key = f"photon:{q.lower()}"
    if (hit := cache.get(cache_key)) is not None:
        return hit
    with client_or_new(client) as http:
        try:
            response = http.get(
                PHOTON_URL, params={"q": q, "limit": 6, "lang": "en", "bbox": NORTH_AMERICA_BBOX}
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ProviderError("Place search isn't responding. Try again in a minute.") from exc
    places = [_place(f) for f in response.json().get("features", [])]
    cache.set(cache_key, places, CACHE_SECONDS)
    return places


def _place(feature: dict) -> dict:
    props = feature["properties"]
    lon, lat = feature["geometry"]["coordinates"]
    parts = [props.get(k) for k in ("name", "city", "state", "countrycode")]
    label = ", ".join(dict.fromkeys(p for p in parts if p))
    return {"label": label, "lat": round(lat, 5), "lon": round(lon, 5)}
```

Update `backend/trips/api.py`:

```python
from ninja import NinjaAPI

from .errors import TripError
from .providers.photon import search_places

api = NinjaAPI(title="Weather-Aware Truck Routing")


@api.exception_handler(TripError)
def trip_error(request, exc: TripError):
    return api.create_response(request, {"detail": exc.message}, status=exc.status)


@api.get("/health")
def health(request):
    return {"ok": True}


@api.get("/geocode")
def geocode(request, q: str = ""):
    return search_places(q)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest -v`
Expected: all PASS. (Note: the test cache is LocMem and persists between tests in one process; the queries differ per test so they don't collide.)

- [ ] **Step 5: Commit**

```bash
git add backend/trips
git commit -m "feat(api): place search endpoint backed by Photon"
```

---

### Task 10: Plan and persist a trip — `POST /api/trips`, `GET /api/trips/{id}`

**Files:**
- Create: `backend/trips/schemas.py`, `backend/trips/services.py`
- Modify: `backend/trips/models.py` (add `Trip`), `backend/trips/api.py`, new migration
- Test: `backend/trips/tests/test_trips_api.py`

**Interfaces:**
- Consumes: `fetch_routes` (Task 8), `fetch_series` (Task 7), `place_checkpoints`/`thin`/`slice_path` (Task 4), `conditions_at` (Task 5), `assess` (Task 3), `summarize`/`segment_levels`/`recommend`/`Candidate` (Task 6).
- Produces:
  - `services.Place(label, lat, lon)` with `.point -> LonLat`; `services.TripRequest(origin, destination, departure, load_lb, interval_mi)`
  - `services.plan_trip(req: TripRequest, *, now: datetime | None = None) -> dict` — the Trip JSON from the API Contract minus `id`/`created_at`.
  - `services.floor_hour(dt) -> datetime`
  - `models.Trip(id: UUID, created_at, load_lb, result: JSON, corridor: JSON | None)`
  - Endpoints per the API Contract.

- [ ] **Step 1: Write the failing tests**

`backend/trips/tests/test_trips_api.py`:

```python
from datetime import UTC, timedelta

import pytest
from django.utils import timezone

from trips import services
from trips.errors import NoRouteError, ProviderError
from trips.tests.factories import flat_series, floor_hour, straight_route

ORIGIN = {"label": "Origin", "lat": 40.0, "lon": -100.0}
DEST = {"label": "Destination", "lat": 40.0, "lon": -98.0}


def fake_routes(origin, destination, load_lb):
    return [
        straight_route("A road", (-100, 40.0), (-98, 40.0), hours=2.0),
        straight_route("B road", (-100, 40.0), (-98, 40.6), hours=2.5),
        straight_route("C road", (-100, 40.0), (-98, 39.4), hours=1.8),
    ]


def fake_series(points, now=None):
    start = floor_hour(timezone.now()) - timedelta(days=1)
    # South of 39.8° is windy: 40 mph is High, and Severe for loads over 40,000 lb.
    return [flat_series(start, wind=40.0 if lat < 39.8 else 5.0) for lon, lat in points]


@pytest.fixture
def fakes(monkeypatch):
    monkeypatch.setattr(services, "fetch_routes", fake_routes)
    monkeypatch.setattr(services, "fetch_series", fake_series)


def payload(**overrides):
    body = {
        "origin": ORIGIN,
        "destination": DEST,
        "departure": (timezone.now() + timedelta(hours=2)).isoformat(),
        "load_lb": 45_000,
        "interval_mi": 25,
    }
    body.update(overrides)
    return body


def post(client, body):
    return client.post("/api/trips", body, content_type="application/json")


@pytest.mark.django_db
def test_plans_three_routes_and_recommends_the_safe_fast_one(client, fakes):
    response = post(client, payload())
    assert response.status_code == 201
    trip = response.json()
    assert [r["id"] for r in trip["routes"]] == ["A", "B", "C"]
    rec = trip["recommendation"]
    assert rec["route_id"] == "A"
    assert rec["reason"] == "Same risk as Route B, 30 min faster."
    assert {r["id"]: r["rank"] for r in trip["routes"]} == {"A": 1, "B": 2, "C": 3}
    c = trip["routes"][2]
    assert c["summary"]["miles_by_level"]["severe"] > 0
    assert any(cp["load_adjusted"] for cp in c["checkpoints"])


@pytest.mark.django_db
def test_checkpoints_carry_eta_and_conditions(client, fakes):
    body = payload(interval_mi=10)
    trip = post(client, body).json()
    a = trip["routes"][0]
    miles = [cp["mile"] for cp in a["checkpoints"]]
    assert miles[:3] == [0, 10, 20] and miles[-1] == a["distance_mi"]
    assert a["checkpoints"][0]["eta"] == trip["departure"]
    assert a["checkpoints"][-1]["eta"] == a["arrival"]
    assert a["segments"][0]["coordinates"][0] == [-100.0, 40.0]
    assert len(a["path"]["coordinates"]) == len(a["path"]["seconds"])


@pytest.mark.django_db
def test_departure_with_offset_is_stored_as_utc(client, fakes):
    local = (timezone.now() + timedelta(days=1)).astimezone(timezone.get_fixed_timezone(-300))
    local = local.replace(minute=0, second=0, microsecond=0)
    trip = post(client, payload(departure=local.isoformat())).json()
    assert trip["departure"] == local.astimezone(UTC).isoformat()
    assert trip["timeline_start"] == trip["departure"]


@pytest.mark.django_db
def test_get_returns_the_saved_trip(client, fakes):
    created = post(client, payload()).json()
    fetched = client.get(f"/api/trips/{created['id']}").json()
    assert fetched == created


@pytest.mark.django_db
def test_unknown_trip_is_404(client):
    assert client.get("/api/trips/00000000-0000-0000-0000-000000000000").status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides,message",
    [
        ({"departure": "2020-01-01T00:00:00Z"}, "Departure is in the past"),
        ({"departure": "2099-01-01T00:00:00Z"}, "within the next 7 days"),
        ({"destination": ORIGIN}, "same place"),
    ],
)
def test_rejects_unplannable_trips(client, fakes, overrides, message):
    response = post(client, payload(**overrides))
    assert response.status_code == 422
    assert message in response.json()["detail"]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        {"load_lb": 0},
        {"load_lb": 150_001},
        {"interval_mi": 30},
        {"departure": "2026-10-14T06:00:00"},  # no offset
    ],
)
def test_schema_validation(client, fakes, overrides):
    assert post(client, payload(**overrides)).status_code == 422


@pytest.mark.django_db
def test_trip_ending_past_the_forecast_is_422(client, monkeypatch):
    monkeypatch.setattr(services, "fetch_routes", fake_routes)
    short = lambda points, now=None: [
        flat_series(floor_hour(timezone.now()) - timedelta(hours=1), hours=3) for _ in points
    ]
    monkeypatch.setattr(services, "fetch_series", short)
    response = post(client, payload(departure=(timezone.now() + timedelta(hours=1)).isoformat()))
    assert response.status_code == 422
    assert "beyond the forecast" in response.json()["detail"]


@pytest.mark.django_db
@pytest.mark.parametrize("error,status", [(NoRouteError("No truck route"), 422), (ProviderError("down"), 502)])
def test_provider_errors_surface_with_message(client, monkeypatch, error, status):
    def boom(*args, **kwargs):
        raise error
    monkeypatch.setattr(services, "fetch_routes", boom)
    response = post(client, payload())
    assert response.status_code == status
    assert response.json()["detail"] == error.message


@pytest.mark.django_db
def test_fewer_than_three_routes_adds_a_note(client, monkeypatch):
    monkeypatch.setattr(services, "fetch_routes", lambda *a: fake_routes(*a)[:2])
    monkeypatch.setattr(services, "fetch_series", fake_series)
    trip = post(client, payload()).json()
    assert len(trip["routes"]) == 2
    assert trip["notes"] == ["Only 2 distinct truck routes exist between these places."]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest trips/tests/test_trips_api.py -v`
Expected: FAIL — `AttributeError: module 'trips.services'…` / 404s.

- [ ] **Step 3: Add the Trip model**

Append to `backend/trips/models.py`:

```python
class Trip(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    load_lb = models.PositiveIntegerField()
    result = models.JSONField()  # the planned trip, shaped as the API returns it
    corridor = models.JSONField(null=True, blank=True)  # filled on first corridor request

    def as_json(self) -> dict:
        return {"id": str(self.id), "created_at": self.created_at.isoformat(), **self.result}
```

```bash
uv run python manage.py makemigrations trips
```

- [ ] **Step 4: Request schemas**

`backend/trips/schemas.py`:

```python
from datetime import datetime
from typing import Literal

from ninja import Field, Schema
from pydantic import field_validator


class PlaceIn(Schema):
    label: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class TripIn(Schema):
    origin: PlaceIn
    destination: PlaceIn
    departure: datetime
    load_lb: int = Field(gt=0, le=150_000)
    interval_mi: Literal[10, 25, 50] = 25

    @field_validator("departure")
    @classmethod
    def departure_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Departure must include a time zone offset.")
        return value
```

- [ ] **Step 5: The orchestration service**

`backend/trips/services.py`:

```python
"""Turns a trip request into scored routes. Orchestration only; rules live in engine/."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise

from django.utils import timezone

from .engine.checkpoints import CheckpointPosition, place_checkpoints, slice_path, thin
from .engine.forecast import Conditions, conditions_at
from .engine.geo import LonLat, haversine_mi
from .engine.risk import Assessment, assess
from .engine.route import RouteGeometry
from .engine.scoring import Candidate, RouteSummary, recommend, segment_levels, summarize
from .errors import TripError
from .providers.open_meteo import fetch_series
from .providers.valhalla import fetch_routes

ROUTE_IDS = "ABC"
DEPARTURE_GRACE = timedelta(hours=1)
MAX_DEPARTURE_AHEAD = timedelta(days=7)


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float

    @property
    def point(self) -> LonLat:
        return (self.lon, self.lat)


@dataclass(frozen=True)
class TripRequest:
    origin: Place
    destination: Place
    departure: datetime
    load_lb: int
    interval_mi: int


@dataclass(frozen=True)
class _Row:
    position: CheckpointPosition
    eta: datetime
    conditions: Conditions
    assessment: Assessment


def floor_hour(dt: datetime) -> datetime:
    return dt.astimezone(UTC).replace(minute=0, second=0, microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


def _coords(points: list[LonLat]) -> list[list[float]]:
    return [[round(lon, 5), round(lat, 5)] for lon, lat in points]


def _validate(req: TripRequest, now: datetime) -> None:
    if req.departure < now - DEPARTURE_GRACE:
        raise TripError("Departure is in the past. Pick a time from now on.")
    if req.departure > now + MAX_DEPARTURE_AHEAD:
        raise TripError("Forecasts reach about a week out. Pick a departure within the next 7 days.")
    if haversine_mi(req.origin.point, req.destination.point) < 1:
        raise TripError("Start and destination are the same place. Pick a different destination.")


def plan_trip(req: TripRequest, *, now: datetime | None = None) -> dict:
    now = now or timezone.now()
    _validate(req, now)
    departure = req.departure.astimezone(UTC)

    routes = fetch_routes(req.origin.point, req.destination.point, req.load_lb)
    placed = [place_checkpoints(route, req.interval_mi) for route in routes]
    series = iter(fetch_series([(c.lon, c.lat) for cps in placed for c in cps]))

    out_routes, candidates = [], []
    for route_id, route, positions in zip(ROUTE_IDS, routes, placed):
        rows = []
        for position in positions:
            eta = departure + timedelta(seconds=position.offset_s)
            conditions = conditions_at(next(series), eta)
            if conditions is None:
                raise TripError(
                    f"Route {route_id} reaches mile {position.mile:.0f} at "
                    f"{eta:%a %H:%M} UTC, beyond the forecast. Pick an earlier departure."
                )
            assessment = assess(
                wind_mph=conditions.wind_mph,
                rain_in_hr=conditions.rain_in_hr,
                snow_in_hr=conditions.snow_in_hr,
                load_lb=req.load_lb,
            )
            rows.append(_Row(position, eta, conditions, assessment))
        summary = summarize([r.position.mile for r in rows], [r.assessment.level for r in rows])
        candidates.append(Candidate(route_id, summary, route.duration_s))
        out_routes.append(_route_json(route_id, route, rows, summary))

    recommendation = recommend(candidates)
    for r in out_routes:
        r["rank"] = recommendation.ranking.index(r["id"]) + 1
    notes = []
    if len(routes) < len(ROUTE_IDS):
        notes.append(f"Only {len(routes)} distinct truck routes exist between these places.")

    return {
        "origin": vars(req.origin),
        "destination": vars(req.destination),
        "departure": _iso(departure),
        "load_lb": req.load_lb,
        "interval_mi": req.interval_mi,
        "timeline_start": _iso(floor_hour(departure)),
        "routes": out_routes,
        "recommendation": {
            "route_id": recommendation.route_id,
            "reason": recommendation.reason,
            "all_blocked": recommendation.all_blocked,
        },
        "notes": notes,
    }


def _route_json(route_id: str, route: RouteGeometry, rows: list[_Row], summary: RouteSummary) -> dict:
    path = thin(route)
    miles = [r.position.mile for r in rows]
    levels = [r.assessment.level for r in rows]
    return {
        "id": route_id,
        "label": route.label,
        "distance_mi": round(route.distance_mi, 2),
        "duration_s": round(route.duration_s),
        "arrival": _iso(rows[-1].eta),
        "path": {"coordinates": _coords(path.points), "seconds": [round(s) for s in path.cum_seconds]},
        "segments": [
            {
                "level": level.slug,
                "start_mile": start,
                "end_mile": end,
                "coordinates": _coords(slice_path(path, start, end)),
            }
            for (start, end), level in zip(pairwise(miles), segment_levels(levels))
        ],
        "checkpoints": [
            {
                "mile": r.position.mile,
                "lon": round(r.position.lon, 5),
                "lat": round(r.position.lat, 5),
                "eta": _iso(r.eta),
                "wind_mph": r.conditions.wind_mph,
                "gust_mph": r.conditions.gust_mph,
                "rain_in_hr": round(r.conditions.rain_in_hr, 3),
                "snow_in_hr": round(r.conditions.snow_in_hr, 3),
                "level": r.assessment.level.slug,
                "drivers": list(r.assessment.drivers),
                "load_adjusted": r.assessment.load_adjusted,
            }
            for r in rows
        ],
        "summary": {
            "miles_by_level": {lvl.slug: m for lvl, m in summary.miles_by_level.items()},
            "avg_risk": summary.avg_risk,
            "max_level": summary.max_level.slug,
        },
    }
```

Note `checkpoint_miles` puts the destination at the exact route length, and `_route_json` rounds `distance_mi` to 2 dp while `CheckpointPosition.mile` is rounded to 2 dp — so `miles[-1] == distance_mi` in the test holds.

- [ ] **Step 6: Endpoints**

Add to `backend/trips/api.py`:

```python
import uuid

from django.shortcuts import get_object_or_404

from .models import Trip
from .schemas import TripIn
from .services import Place, TripRequest, plan_trip


@api.post("/trips")
def create_trip(request, payload: TripIn):
    req = TripRequest(
        origin=Place(**payload.origin.model_dump()),
        destination=Place(**payload.destination.model_dump()),
        departure=payload.departure,
        load_lb=payload.load_lb,
        interval_mi=payload.interval_mi,
    )
    trip = Trip.objects.create(load_lb=payload.load_lb, result=plan_trip(req))
    return api.create_response(request, trip.as_json(), status=201)


@api.get("/trips/{trip_id}")
def get_trip(request, trip_id: uuid.UUID):
    return get_object_or_404(Trip, id=trip_id).as_json()
```

- [ ] **Step 7: Run to verify pass**

Run: `uv run pytest -v`
Expected: all PASS.

- [ ] **Step 8: Live smoke check**

```bash
uv run python manage.py migrate && uv run python manage.py runserver &
curl -s -X POST localhost:8000/api/trips -H 'content-type: application/json' -d "{\"origin\":{\"label\":\"Chicago\",\"lat\":41.88,\"lon\":-87.63},\"destination\":{\"label\":\"Denver\",\"lat\":39.74,\"lon\":-104.99},\"departure\":\"$(date -u -v+2H +%Y-%m-%dT%H:00:00Z)\",\"load_lb\":42000,\"interval_mi\":25}" | python3 -c "import json,sys;t=json.load(sys.stdin);print(t['recommendation']);print([(r['id'],r['label'],r['distance_mi'],len(r['checkpoints'])) for r in t['routes']])"
kill %1
```

Expected: a recommendation and 3 routes with ~40 checkpoints each.

- [ ] **Step 9: Commit**

```bash
git add backend/trips
git commit -m "feat(api): plan, score, recommend and persist trips"
```

---

### Task 11: Corridor heatmap data — `GET /api/trips/{id}/corridor`

**Files:**
- Create: `backend/trips/engine/corridor.py`
- Modify: `backend/trips/services.py`, `backend/trips/api.py`
- Test: `backend/trips/tests/test_corridor.py`

**Interfaces:**
- Consumes: `assess`, `conditions_at`, `fetch_series`, `Trip`.
- Produces:
  - `corridor.Grid(west, south, east, north, cols, rows, active: list[int], centers: list[LonLat])` — `active` are flat indices `row*cols+col`, row 0 = north.
  - `corridor.build_grid(paths: list[list[LonLat]], *, cell_mi=20.0, buffer_mi=40.0) -> Grid` — guarantees `cols*rows <= 2500` and `len(active) <= 400`.
  - `corridor.corridor_scores(grid, series, start, load_lb, hours=48) -> list[list[float]]` — 49 frames.
  - `services.build_corridor(trip: Trip) -> dict` — the Contract's corridor JSON, cached on the trip.

- [ ] **Step 1: Write the failing tests**

`backend/trips/tests/test_corridor.py`:

```python
from datetime import timedelta

import pytest
from django.utils import timezone

from trips import services
from trips.engine.corridor import build_grid, corridor_scores
from trips.engine.geo import haversine_mi
from trips.tests.factories import flat_series, floor_hour
from trips.tests.test_trips_api import fake_routes, fake_series, payload, post

LINE = [(-100.0 + i * 0.05, 40.0) for i in range(41)]  # ~105 mi east-west


def test_grid_covers_route_with_buffer_and_masks_far_cells():
    g = build_grid([LINE], cell_mi=20, buffer_mi=40)
    assert g.west < -100 and g.east > -98 and g.south < 40 < g.north
    assert 0 < len(g.active) < g.cols * g.rows
    for (lon, lat) in g.centers:
        nearest = min(haversine_mi((lon, lat), p) for p in LINE)
        assert nearest <= 40 + 20 * 1.5  # buffer plus a cell diagonal


def test_grid_is_capped_for_long_routes():
    coast_to_coast = [(-122.0 + i * 0.5, 37.0 + (i % 3) * 0.3) for i in range(100)]
    g = build_grid([coast_to_coast])
    assert g.cols * g.rows <= 2500
    assert len(g.active) <= 400


def test_scores_have_49_frames_and_mask_inactive_cells():
    g = build_grid([LINE])
    start = floor_hour(timezone.now())
    series = [flat_series(start - timedelta(hours=1), wind=40.0) for _ in g.centers]
    frames = corridor_scores(g, series, start, load_lb=45_000)
    assert len(frames) == 49
    assert all(len(f) == g.cols * g.rows for f in frames)
    inactive = set(range(g.cols * g.rows)) - set(g.active)
    assert all(frames[0][i] == -1 for i in inactive)
    assert all(3 <= frames[0][i] < 4 for i in g.active)  # 40 mph + 45k lb = Severe


@pytest.mark.django_db
def test_corridor_endpoint_builds_once_then_reuses(client, monkeypatch):
    calls = []
    monkeypatch.setattr(services, "fetch_routes", fake_routes)

    def counting_series(points, now=None):
        calls.append(len(points))
        return fake_series(points)

    monkeypatch.setattr(services, "fetch_series", counting_series)
    trip = post(client, payload()).json()
    before = len(calls)

    first = client.get(f"/api/trips/{trip['id']}/corridor").json()
    second = client.get(f"/api/trips/{trip['id']}/corridor").json()

    assert first == second
    assert len(calls) == before + 1
    assert first["start"] == trip["timeline_start"]
    assert len(first["scores"]) == 49
    assert len(first["scores"][0]) == first["cols"] * first["rows"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest trips/tests/test_corridor.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement the grid and scores**

`backend/trips/engine/corridor.py`:

```python
"""A coarse lon/lat grid around the routes, scored hour by hour for the heatmap."""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from .forecast import HourlySeries, conditions_at
from .geo import MI_PER_DEG_LAT, LonLat
from .risk import assess

MAX_CELLS = 2500
MAX_ACTIVE = 400
GROWTH = 1.25
MASKED = -1.0


@dataclass(frozen=True)
class Grid:
    west: float
    south: float
    east: float
    north: float
    cols: int
    rows: int
    active: list[int]  # row * cols + col, row 0 is the north edge
    centers: list[LonLat]  # one per active index


def build_grid(paths: list[list[LonLat]], *, cell_mi: float = 20.0, buffer_mi: float = 40.0) -> Grid:
    points = [p for path in paths for p in path]
    while True:
        grid = _grid(points, cell_mi, buffer_mi)
        if grid.cols * grid.rows <= MAX_CELLS and len(grid.active) <= MAX_ACTIVE:
            return grid
        cell_mi *= GROWTH


def _grid(points: list[LonLat], cell_mi: float, buffer_mi: float) -> Grid:
    lons, lats = [p[0] for p in points], [p[1] for p in points]
    mi_per_deg_lon = MI_PER_DEG_LAT * math.cos(math.radians((min(lats) + max(lats)) / 2))
    dlat, dlon = cell_mi / MI_PER_DEG_LAT, cell_mi / mi_per_deg_lon
    west = min(lons) - buffer_mi / mi_per_deg_lon
    north = max(lats) + buffer_mi / MI_PER_DEG_LAT
    cols = max(1, math.ceil((max(lons) + buffer_mi / mi_per_deg_lon - west) / dlon))
    rows = max(1, math.ceil((north - (min(lats) - buffer_mi / MI_PER_DEG_LAT)) / dlat))

    reach = math.ceil(buffer_mi / cell_mi)
    touched = {(int((north - lat) / dlat), int((lon - west) / dlon)) for lon, lat in points}
    active: set[int] = set()
    for r, c in touched:
        for dr in range(-reach, reach + 1):
            for dc in range(-reach, reach + 1):
                rr, cc = r + dr, c + dc
                if dr * dr + dc * dc <= reach * reach and 0 <= rr < rows and 0 <= cc < cols:
                    active.add(rr * cols + cc)
    ordered = sorted(active)
    return Grid(
        west=west,
        south=north - rows * dlat,
        east=west + cols * dlon,
        north=north,
        cols=cols,
        rows=rows,
        active=ordered,
        centers=[(west + (i % cols + 0.5) * dlon, north - (i // cols + 0.5) * dlat) for i in ordered],
    )


def corridor_scores(
    grid: Grid, series: list[HourlySeries], start: datetime, load_lb: float, hours: int = 48
) -> list[list[float]]:
    frames = []
    for h in range(hours + 1):
        when = start + timedelta(hours=h)
        frame = [MASKED] * (grid.cols * grid.rows)
        for index, s in zip(grid.active, series):
            c = conditions_at(s, when)
            if c is not None:
                frame[index] = assess(
                    wind_mph=c.wind_mph, rain_in_hr=c.rain_in_hr, snow_in_hr=c.snow_in_hr, load_lb=load_lb
                ).score
        frames.append(frame)
    return frames
```

- [ ] **Step 4: Service + endpoint**

Append to `backend/trips/services.py`:

```python
from .engine.corridor import build_grid, corridor_scores  # add to imports
from .models import Trip  # add to imports


def build_corridor(trip: Trip) -> dict:
    if trip.corridor:
        return trip.corridor
    paths = [[tuple(p) for p in r["path"]["coordinates"]] for r in trip.result["routes"]]
    grid = build_grid(paths)
    start = datetime.fromisoformat(trip.result["timeline_start"])
    frames = corridor_scores(grid, fetch_series(grid.centers), start, trip.load_lb)
    trip.corridor = {
        "start": trip.result["timeline_start"],
        "bounds": [round(v, 5) for v in (grid.west, grid.south, grid.east, grid.north)],
        "cols": grid.cols,
        "rows": grid.rows,
        "scores": frames,
    }
    trip.save(update_fields=["corridor"])
    return trip.corridor
```

Add to `backend/trips/api.py`:

```python
from .services import build_corridor  # extend the existing services import


@api.get("/trips/{trip_id}/corridor")
def get_corridor(request, trip_id: uuid.UUID):
    return build_corridor(get_object_or_404(Trip, id=trip_id))
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run pytest -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/trips
git commit -m "feat(api): 0-48h corridor risk grid for the heatmap"
```

---

### Task 12: Frontend API layer, formatting and timeline helpers

**Files:**
- Create: `frontend/src/api/types.ts`, `frontend/src/api/client.ts`, `frontend/src/api/queries.ts`, `frontend/src/lib/format.ts`, `frontend/src/lib/timeline.ts`, `frontend/src/lib/useDebouncedValue.ts`
- Test: `frontend/src/lib/format.test.ts`, `frontend/src/lib/timeline.test.ts`, `frontend/src/api/client.test.ts`

**Interfaces:**
- Consumes: API Contract; `Level`, `maxLevel`, `levelIndex` (Task 2).
- Produces:
  - Types `Place`, `TripInput`, `Checkpoint`, `Segment`, `Route`, `Trip`, `Corridor`, `LonLat`.
  - `api.geocode(q)`, `api.createTrip(input)`, `api.trip(id)`, `api.corridor(id)`; `class ApiError extends Error { status: number }`.
  - `geocodeQuery(q)`, `tripQuery(id)`, `corridorQuery(id)` (`queryOptions`), `useCreateTrip()`.
  - `formatDuration(s)`, `formatMiles(mi)`, `formatClock(isoOrMs)`, `formatHourTick(ms)`, `localZoneName()`.
  - `HOUR_MS`, `TIMELINE_HOURS = 48`, `positionAt(path, secondsSinceDeparture) -> { coord: LonLat; arrived: boolean }`, `levelDuring(route, startMs, hour) -> Level | null`.
  - `useDebouncedValue<T>(value, ms) -> T`.

- [ ] **Step 1: Types**

`frontend/src/api/types.ts`:

```ts
import type { Level } from '@/lib/risk';

export type LonLat = [number, number];
export type Interval = 10 | 25 | 50;

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface TripInput {
  origin: Place;
  destination: Place;
  departure: string; // ISO-8601 with offset
  load_lb: number;
  interval_mi: Interval;
}

export interface Checkpoint {
  mile: number;
  lon: number;
  lat: number;
  eta: string;
  wind_mph: number;
  gust_mph: number;
  rain_in_hr: number;
  snow_in_hr: number;
  level: Level;
  drivers: Array<'wind' | 'rain' | 'snow'>;
  load_adjusted: boolean;
}

export interface Segment {
  level: Level;
  start_mile: number;
  end_mile: number;
  coordinates: LonLat[];
}

export interface Route {
  id: string;
  label: string;
  distance_mi: number;
  duration_s: number;
  arrival: string;
  rank: number;
  path: { coordinates: LonLat[]; seconds: number[] };
  segments: Segment[];
  checkpoints: Checkpoint[];
  summary: { miles_by_level: Record<Level, number>; avg_risk: number; max_level: Level };
}

export interface Trip {
  id: string;
  created_at: string;
  origin: Place;
  destination: Place;
  departure: string;
  load_lb: number;
  interval_mi: Interval;
  timeline_start: string;
  routes: Route[];
  recommendation: { route_id: string; reason: string; all_blocked: boolean };
  notes: string[];
}

export interface Corridor {
  start: string;
  bounds: [west: number, south: number, east: number, north: number];
  cols: number;
  rows: number;
  scores: number[][]; // [hour][row * cols + col], -1 = no data
}
```

- [ ] **Step 2: Write the failing tests**

`frontend/src/lib/format.test.ts`:

```ts
import { describe, expect, it } from 'vite-plus/test';
import { formatDuration, formatMiles } from './format';

describe('format', () => {
  it('formats drive time as hours and minutes', () => {
    expect(formatDuration(56_695)).toBe('15 h 45 m');
    expect(formatDuration(1_500)).toBe('25 m');
  });
  it('formats miles with separators', () => {
    expect(formatMiles(1016.44)).toBe('1,016 mi');
    expect(formatMiles(4.26)).toBe('4.3 mi');
  });
});
```

`frontend/src/lib/timeline.test.ts`:

```ts
import { describe, expect, it } from 'vite-plus/test';
import type { Checkpoint, Route } from '@/api/types';
import { HOUR_MS, levelDuring, positionAt } from './timeline';

const path = { coordinates: [[0, 0], [1, 0], [2, 0]] as [number, number][], seconds: [0, 3600, 5400] };

describe('positionAt', () => {
  it('stays at the origin before departure', () => {
    expect(positionAt(path, -100)).toEqual({ coord: [0, 0], arrived: false });
  });
  it('interpolates by drive time', () => {
    expect(positionAt(path, 4500).coord).toEqual([1.5, 0]);
  });
  it('parks at the destination after arrival', () => {
    expect(positionAt(path, 9999)).toEqual({ coord: [2, 0], arrived: true });
  });
});

const T0 = Date.parse('2026-10-14T00:00:00Z');
const cp = (minutes: number, level: Checkpoint['level']): Checkpoint => ({
  mile: minutes, lon: 0, lat: 0, eta: new Date(T0 + minutes * 60_000).toISOString(),
  wind_mph: 0, gust_mph: 0, rain_in_hr: 0, snow_in_hr: 0, level, drivers: [], load_adjusted: false,
});
const route = { checkpoints: [cp(30, 'low'), cp(80, 'severe'), cp(200, 'moderate'), cp(320, 'low')] } as Route;

describe('levelDuring', () => {
  it('is null before departure and after arrival', () => {
    expect(levelDuring(route, T0 - HOUR_MS, 0)).toBeNull();
    expect(levelDuring(route, T0, 6)).toBeNull();
  });
  it('takes the worst checkpoint inside the hour', () => {
    expect(levelDuring(route, T0, 1)).toBe('severe');
  });
  it('uses the surrounding stretch when no checkpoint falls inside the hour', () => {
    expect(levelDuring(route, T0, 2)).toBe('severe'); // 120–180 min between 80 (severe) and 200 (moderate)
  });
});
```

`frontend/src/api/client.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from 'vite-plus/test';
import { ApiError, api } from './client';

afterEach(() => vi.unstubAllGlobals());

describe('api client', () => {
  it('surfaces the server message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Departure is in the past.' }), { status: 422 })));
    await expect(api.trip('x')).rejects.toEqual(new ApiError(422, 'Departure is in the past.'));
  });
  it('joins schema validation messages', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [{ msg: 'a' }, { msg: 'b' }] }), { status: 422 })));
    await expect(api.trip('x')).rejects.toThrow('a; b');
  });
  it('explains a dead server', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(api.trip('x')).rejects.toThrow("Can't reach the server");
  });
});
```

Run: `cd frontend && bun run test`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement**

`frontend/src/lib/format.ts`:

```ts
const clock = new Intl.DateTimeFormat(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' });
const hourTick = new Intl.DateTimeFormat(undefined, { hour: 'numeric' });
const day = new Intl.DateTimeFormat(undefined, { weekday: 'short' });

export function formatDuration(seconds: number): string {
  const total = Math.round(seconds / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h ? `${h} h ${m} m` : `${m} m`;
}

export function formatMiles(mi: number): string {
  return `${mi.toLocaleString(undefined, { maximumFractionDigits: mi < 10 ? 1 : 0 })} mi`;
}

export const formatClock = (t: string | number): string => clock.format(new Date(t));

/** Logbook tick: weekday at local midnight, otherwise the hour ("6 PM"). */
export function formatHourTick(ms: number): string {
  const d = new Date(ms);
  return d.getHours() === 0 ? day.format(d) : hourTick.format(d);
}

export const localZoneName = (): string =>
  new Intl.DateTimeFormat(undefined, { timeZoneName: 'short' })
    .formatToParts(new Date())
    .find((p) => p.type === 'timeZoneName')?.value ?? '';
```

`frontend/src/lib/timeline.ts`:

```ts
import type { LonLat, Route } from '@/api/types';
import { type Level, maxLevel } from './risk';

export const HOUR_MS = 3_600_000;
export const TIMELINE_HOURS = 48;

/** Where the truck is `t` seconds after departure. */
export function positionAt(path: Route['path'], t: number): { coord: LonLat; arrived: boolean } {
  const { coordinates: c, seconds: s } = path;
  const last = s.length - 1;
  if (t <= 0) return { coord: c[0], arrived: false };
  if (t >= s[last]) return { coord: c[last], arrived: true };
  let lo = 0;
  let hi = last;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (s[mid] <= t) lo = mid;
    else hi = mid;
  }
  const span = s[hi] - s[lo];
  const f = span > 0 ? (t - s[lo]) / span : 0;
  return { coord: [c[lo][0] + (c[hi][0] - c[lo][0]) * f, c[lo][1] + (c[hi][1] - c[lo][1]) * f], arrived: false };
}

/** Worst risk the truck meets during timeline hour `hour`, or null if it isn't driving then. */
export function levelDuring(route: Pick<Route, 'checkpoints'>, startMs: number, hour: number): Level | null {
  const from = startMs + hour * HOUR_MS;
  const to = from + HOUR_MS;
  const times = route.checkpoints.map((c) => Date.parse(c.eta));
  if (to <= times[0] || from > times[times.length - 1]) return null;
  let worst: Level | null = null;
  for (let i = 0; i < times.length; i++) {
    const level = route.checkpoints[i].level;
    if (times[i] >= from && times[i] < to) worst = worst ? maxLevel(worst, level) : level;
  }
  if (worst) return worst;
  const next = times.findIndex((t) => t >= to);
  return maxLevel(route.checkpoints[next - 1].level, route.checkpoints[next].level);
}
```

`frontend/src/api/client.ts`:

```ts
import type { Corridor, Place, Trip, TripInput } from './types';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function messageFrom(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) return detail.map((d: { msg?: string }) => d.msg ?? '').join('; ');
  return `The server returned an error (${status}). Try again.`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { headers: { 'content-type': 'application/json' }, ...init });
  } catch {
    throw new ApiError(0, "Can't reach the server. Check your connection and try again.");
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(res.status, messageFrom(body, res.status));
  return body as T;
}

export const api = {
  geocode: (q: string) => request<Place[]>(`/geocode?q=${encodeURIComponent(q)}`),
  createTrip: (input: TripInput) => request<Trip>('/trips', { method: 'POST', body: JSON.stringify(input) }),
  trip: (id: string) => request<Trip>(`/trips/${id}`),
  corridor: (id: string) => request<Corridor>(`/trips/${id}/corridor`),
};
```

`frontend/src/api/queries.ts`:

```ts
import { queryOptions, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from './client';

export const geocodeQuery = (q: string) =>
  queryOptions({ queryKey: ['geocode', q.toLowerCase()], queryFn: () => api.geocode(q), staleTime: Infinity });

export const tripQuery = (id: string) =>
  queryOptions({ queryKey: ['trip', id], queryFn: () => api.trip(id), staleTime: Infinity });

export const corridorQuery = (id: string) =>
  queryOptions({ queryKey: ['trip', id, 'corridor'], queryFn: () => api.corridor(id), staleTime: Infinity });

export function useCreateTrip() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createTrip,
    onSuccess: (trip) => queryClient.setQueryData(tripQuery(trip.id).queryKey, trip),
  });
}
```

`frontend/src/lib/useDebouncedValue.ts`:

```ts
import { useEffect, useState } from 'react';

export function useDebouncedValue<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(id);
  }, [value, ms]);
  return debounced;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `bun run test && bun run check`
Expected: PASS, no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(web): typed API client, queries, formatting and timeline helpers"
```

---

### Task 13: Plan form (`/`) with place search and loader

**Files:**
- Create: `frontend/src/features/planner/validate.ts`, `frontend/src/features/planner/validate.test.ts`, `frontend/src/features/planner/PlaceInput.tsx`, `frontend/src/features/planner/TripForm.tsx`
- Modify: `frontend/src/routes/index.tsx`, `frontend/src/components/ui/multi-step-loader.tsx` (restyle only)

**Interfaces:**
- Consumes: `geocodeQuery`, `useCreateTrip`, `useDebouncedValue`, `Place`, `TripInput`, `Interval`.
- Produces: `FormState`, `validateForm(form, now) -> string | null`, `toTripInput(form) -> TripInput`, `defaultForm(now) -> FormState`, `<TripForm pending error onSubmit />`, `<PlaceInput id label value onChange />`.

- [ ] **Step 1: Write the failing validation tests**

`frontend/src/features/planner/validate.test.ts`:

```ts
import { describe, expect, it } from 'vite-plus/test';
import { defaultForm, toTripInput, validateForm } from './validate';

const NOW = new Date('2026-10-14T15:20:00');
const chicago = { label: 'Chicago, Illinois, US', lat: 41.88, lon: -87.63 };
const denver = { label: 'Denver, Colorado, US', lat: 39.74, lon: -104.99 };
const ok = { ...defaultForm(NOW), origin: chicago, destination: denver };

describe('validateForm', () => {
  it('defaults to the next whole hour, 40,000 lb, every 25 mi', () => {
    const f = defaultForm(NOW);
    expect(f.departure).toBe('2026-10-14T16:00');
    expect(f.loadLb).toBe('40000');
    expect(f.intervalMi).toBe(25);
  });
  it('accepts a complete form', () => {
    expect(validateForm(ok, NOW)).toBeNull();
  });
  it.each([
    [{ origin: null }, 'Pick a start from the list.'],
    [{ destination: null }, 'Pick a destination from the list.'],
    [{ destination: chicago }, 'Start and destination are the same place.'],
    [{ departure: '2026-10-14T13:00' }, 'Departure is in the past.'],
    [{ departure: '2026-10-22T16:00' }, 'Pick a departure within the next 7 days.'],
    [{ loadLb: '0' }, 'Enter a load between 1 and 150,000 lb.'],
    [{ loadLb: 'heavy' }, 'Enter a load between 1 and 150,000 lb.'],
  ])('rejects %o', (patch, message) => {
    expect(validateForm({ ...ok, ...patch }, NOW)).toBe(message);
  });
});

describe('toTripInput', () => {
  it('sends departure as UTC and load as a number', () => {
    const input = toTripInput({ ...ok, departure: '2026-10-14T16:00', loadLb: '42,500' });
    expect(input.departure).toBe(new Date('2026-10-14T16:00').toISOString());
    expect(input.load_lb).toBe(42500);
  });
});
```

Run: `bun run test` → FAIL (module missing).

- [ ] **Step 2: Implement validation**

`frontend/src/features/planner/validate.ts`:

```ts
import type { Interval, Place, TripInput } from '@/api/types';

export interface FormState {
  origin: Place | null;
  destination: Place | null;
  departure: string; // <input type="datetime-local"> value, local time
  loadLb: string;
  intervalMi: Interval;
}

const HOUR = 3_600_000;
const MAX_AHEAD = 7 * 24 * HOUR;

export function toLocalInput(d: Date): string {
  return new Date(d.getTime() - d.getTimezoneOffset() * 60_000).toISOString().slice(0, 16);
}

export function defaultForm(now = new Date()): FormState {
  const next = new Date(now);
  next.setMinutes(60, 0, 0);
  return { origin: null, destination: null, departure: toLocalInput(next), loadLb: '40000', intervalMi: 25 };
}

const parseLoad = (s: string) => Number(s.replaceAll(',', '').trim());

export function validateForm(f: FormState, now = new Date()): string | null {
  if (!f.origin) return 'Pick a start from the list.';
  if (!f.destination) return 'Pick a destination from the list.';
  if (f.origin.lat === f.destination.lat && f.origin.lon === f.destination.lon) {
    return 'Start and destination are the same place.';
  }
  const departure = new Date(f.departure).getTime();
  if (Number.isNaN(departure) || departure < now.getTime() - HOUR) return 'Departure is in the past.';
  if (departure > now.getTime() + MAX_AHEAD) return 'Pick a departure within the next 7 days.';
  const load = parseLoad(f.loadLb);
  if (!Number.isFinite(load) || load < 1 || load > 150_000) return 'Enter a load between 1 and 150,000 lb.';
  return null;
}

export function toTripInput(f: FormState): TripInput {
  return {
    origin: f.origin!,
    destination: f.destination!,
    departure: new Date(f.departure).toISOString(),
    load_lb: Math.round(parseLoad(f.loadLb)),
    interval_mi: f.intervalMi,
  };
}
```

Run: `bun run test` → PASS.

- [ ] **Step 3: Place search combobox**

`frontend/src/features/planner/PlaceInput.tsx`:

```tsx
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { geocodeQuery } from '@/api/queries';
import type { Place } from '@/api/types';
import { useDebouncedValue } from '@/lib/useDebouncedValue';

interface Props {
  id: string;
  label: string;
  value: Place | null;
  onChange: (place: Place | null) => void;
}

export function PlaceInput({ id, label, value, onChange }: Props) {
  const [text, setText] = useState(value?.label ?? '');
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const q = useDebouncedValue(text.trim(), 250);

  useEffect(() => {
    if (value) setText(value.label);
  }, [value]);

  const search = useQuery({ ...geocodeQuery(q), enabled: open && q.length >= 3 && q !== value?.label });
  const options = search.data ?? [];
  const listId = `${id}-options`;

  const choose = (place: Place) => {
    onChange(place);
    setText(place.label);
    setOpen(false);
  };

  return (
    <div className="relative">
      <label htmlFor={id} className="field-label">
        {label}
      </label>
      <input
        id={id}
        className="field-input"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open && options.length > 0}
        aria-controls={listId}
        aria-activedescendant={open && options[active] ? `${id}-opt-${active}` : undefined}
        autoComplete="off"
        placeholder="City, address, or ZIP"
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          onChange(null);
          setOpen(true);
          setActive(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (!open || options.length === 0) return;
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            setActive((i) => Math.min(i + 1, options.length - 1));
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            setActive((i) => Math.max(i - 1, 0));
          } else if (e.key === 'Enter') {
            e.preventDefault();
            choose(options[active]);
          } else if (e.key === 'Escape') {
            setOpen(false);
          }
        }}
      />
      {open && q.length >= 3 && q !== value?.label && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-md border border-rule bg-white py-1 shadow-lg"
        >
          {search.isError && <li className="px-3 py-2 text-ink-soft">{search.error.message}</li>}
          {search.isSuccess && options.length === 0 && (
            <li className="px-3 py-2 text-ink-soft">No places match. Try a city and state.</li>
          )}
          {options.map((place, i) => (
            <li
              key={`${place.lat},${place.lon}`}
              id={`${id}-opt-${i}`}
              role="option"
              aria-selected={i === active}
              className={`cursor-pointer px-3 py-2 ${i === active ? 'bg-paper' : ''}`}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setActive(i)}
              onClick={() => choose(place)}
            >
              {place.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 4: The form**

`frontend/src/features/planner/TripForm.tsx`:

```tsx
import { useState } from 'react';
import type { Interval, TripInput } from '@/api/types';
import { PlaceInput } from './PlaceInput';
import { type FormState, defaultForm, toTripInput, validateForm } from './validate';

const INTERVALS: Interval[] = [10, 25, 50];
const EXAMPLE = {
  origin: { label: 'Chicago, Illinois, US', lat: 41.87556, lon: -87.62442 },
  destination: { label: 'Denver, Colorado, US', lat: 39.73924, lon: -104.98486 },
};

interface Props {
  pending: boolean;
  serverError: string | null;
  onSubmit: (input: TripInput) => void;
}

export function TripForm({ pending, serverError, onSubmit }: Props) {
  const [form, setForm] = useState<FormState>(() => defaultForm());
  const [error, setError] = useState<string | null>(null);
  const set = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }));

  return (
    <form
      className="flex flex-col gap-4"
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        const problem = validateForm(form);
        setError(problem);
        if (!problem) onSubmit(toTripInput(form));
      }}
    >
      <PlaceInput id="origin" label="From" value={form.origin} onChange={(origin) => set({ origin })} />
      <PlaceInput id="destination" label="To" value={form.destination} onChange={(destination) => set({ destination })} />

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor="departure" className="field-label">Leaving at</label>
          <input id="departure" type="datetime-local" className="field-input num" value={form.departure}
            onChange={(e) => set({ departure: e.target.value })} />
        </div>
        <div>
          <label htmlFor="load" className="field-label">Load weight (lb)</label>
          <input id="load" inputMode="numeric" className="field-input num" value={form.loadLb}
            onChange={(e) => set({ loadLb: e.target.value })} />
        </div>
      </div>

      <fieldset>
        <legend className="field-label">Check weather every</legend>
        <div className="grid grid-cols-3 overflow-hidden rounded-md border border-rule bg-white">
          {INTERVALS.map((mi) => (
            <label key={mi}
              className="num cursor-pointer py-2.5 text-center text-sm has-checked:bg-ink has-checked:text-sign-white has-focus-visible:outline-3 has-focus-visible:outline-interstate">
              <input type="radio" name="interval" className="sr-only" checked={form.intervalMi === mi}
                onChange={() => set({ intervalMi: mi })} />
              {mi} mi
            </label>
          ))}
        </div>
      </fieldset>

      {(error ?? serverError) && (
        <p role="alert" className="rounded-md border-l-4 border-risk-severe bg-white px-3 py-2 text-sm">
          {error ?? serverError}
        </p>
      )}

      <div className="flex items-center gap-3">
        <button type="submit" className="btn-primary flex-1" disabled={pending}>
          {pending ? 'Planning routes…' : 'Plan routes'}
        </button>
        <button type="button" className="chip" onClick={() => set(EXAMPLE)}>
          Try Chicago → Denver
        </button>
      </div>
    </form>
  );
}
```

- [ ] **Step 5: The index route with the Aceternity loader**

Restyle `frontend/src/components/ui/multi-step-loader.tsx` minimally: replace its overlay background classes with `bg-paper/85 backdrop-blur-sm`, the active-step text color with `text-ink`, the check icon active color with `text-guide`, and inactive text with `text-ink-soft`. Do not change its props or animation logic.

`frontend/src/routes/index.tsx`:

```tsx
import { createFileRoute, useNavigate } from '@tanstack/react-router';
import { useCreateTrip } from '@/api/queries';
import { MultiStepLoader } from '@/components/ui/multi-step-loader';
import { TripForm } from '@/features/planner/TripForm';

export const Route = createFileRoute('/')({ component: PlanPage });

const PLAN_STEPS = [
  { text: 'Finding three truck routes' },
  { text: 'Placing weather checkpoints' },
  { text: 'Reading the forecast at each ETA' },
  { text: 'Scoring risk for your load' },
  { text: 'Picking the safest route' },
];

function PlanPage() {
  const navigate = useNavigate();
  const createTrip = useCreateTrip();

  return (
    <div className="panel">
      <header>
        <p className="font-display text-xs font-bold tracking-[0.14em] text-guide uppercase">
          Weather-aware truck routing
        </p>
        <h1 className="mt-1 font-display text-[28px] leading-tight font-extrabold">Plan a run</h1>
        <p className="mt-2 text-ink-soft">
          Compare three truck routes against the forecast at the time you'll reach each stretch.
        </p>
      </header>
      <TripForm
        pending={createTrip.isPending}
        serverError={createTrip.error?.message ?? null}
        onSubmit={(input) =>
          createTrip.mutate(input, {
            onSuccess: (trip) => navigate({ to: '/trips/$tripId', params: { tripId: trip.id } }),
          })
        }
      />
      <MultiStepLoader loadingStates={PLAN_STEPS} loading={createTrip.isPending} duration={1400} loop={false} />
    </div>
  );
}
```

(`/trips/$tripId` is created in Task 14; until then the router plugin will flag the link target — create Task 14's route file before running `check`, or run Tasks 13 and 14 back to back.)

- [ ] **Step 6: Verify in the browser**

Run backend (`cd backend && uv run python manage.py runserver`) and frontend (`cd frontend && bun run dev`). At http://localhost:5173: type "denv" → options appear; arrow keys + Enter choose; "Try Chicago → Denver" fills both; submitting an empty form shows "Pick a start from the list."; Tab order is From → To → Leaving at → Load → interval → Plan routes → Try.

- [ ] **Step 7: Commit**

```bash
git add frontend/src
git commit -m "feat(web): trip planning form with place search and planning loader"
```

---

### Task 14: Trip panel — route signs, risk strip, checkpoint table

**Files:**
- Create: `frontend/src/routes/trips.$tripId.tsx`, `frontend/src/features/routes/RouteSign.tsx`, `frontend/src/features/routes/RiskStrip.tsx`, `frontend/src/features/routes/CheckpointTable.tsx`

**Interfaces:**
- Consumes: `tripQuery`, `Trip`, `Route`, `formatDuration`, `formatMiles`, `formatClock`, `localZoneName`, `LEVEL_COLOR`, `LEVEL_LABEL`.
- Produces: route `/trips/$tripId` with search `{ route?: string }`; `<RouteSign route recommended reason selected onSelect />`; `<RiskStrip route />`; `<CheckpointTable route />`.

- [ ] **Step 1: Risk strip**

`frontend/src/features/routes/RiskStrip.tsx`:

```tsx
import type { Route } from '@/api/types';
import { LEVEL_COLOR } from '@/lib/risk';

/** The whole route as one bar, each stretch as wide as its miles. */
export function RiskStrip({ route }: { route: Route }) {
  const total = route.distance_mi || 1;
  return (
    <svg viewBox="0 0 100 6" preserveAspectRatio="none" className="h-1.5 w-full rounded-full" aria-hidden>
      {route.segments.map((s) => (
        <rect key={s.start_mile} x={(s.start_mile / total) * 100} width={((s.end_mile - s.start_mile) / total) * 100 + 0.05}
          y={0} height={6} fill={LEVEL_COLOR[s.level]} />
      ))}
    </svg>
  );
}
```

- [ ] **Step 2: Route sign**

`frontend/src/features/routes/RouteSign.tsx`:

```tsx
import type { Route } from '@/api/types';
import { formatClock, formatDuration, formatMiles } from '@/lib/format';
import { RiskStrip } from './RiskStrip';

interface Props {
  route: Route;
  recommended: boolean;
  reason: string;
  selected: boolean;
  onSelect: () => void;
}

export function RouteSign({ route, recommended, reason, selected, onSelect }: Props) {
  const m = route.summary.miles_by_level;
  return (
    <button type="button" onClick={onSelect} aria-pressed={selected}
      className={`block w-full text-left transition-transform duration-150 hover:-translate-y-px ${selected ? 'ring-4 ring-interstate' : ''} rounded-lg`}>
      <div className="rounded-lg border-2 border-sign-white bg-guide px-4 pt-3 pb-3.5 text-sign-white shadow-[0_0_0_2px_var(--color-guide)]">
        <div className="flex items-baseline gap-3">
          <span className="font-display text-[28px] leading-none font-extrabold">{route.id}</span>
          <span className="truncate font-display text-lg leading-tight font-bold">{route.label}</span>
        </div>
        <div className="num mt-2 flex flex-wrap gap-x-4 text-[13px] opacity-95">
          <span>{formatMiles(route.distance_mi)}</span>
          <span>{formatDuration(route.duration_s)}</span>
          <span>arrive {formatClock(route.arrival)}</span>
        </div>
        <div className="mt-3 rounded-full bg-sign-white/20 p-0.5">
          <RiskStrip route={route} />
        </div>
        <p className="num mt-2 text-[12px] opacity-90">
          {formatMiles(m.no_travel)} no travel · {formatMiles(m.severe)} severe · {formatMiles(m.high)} high · avg {route.summary.avg_risk.toFixed(2)}/4
        </p>
      </div>
      {recommended && (
        <div className="mx-3 rounded-b-md border-2 border-t-0 border-ink bg-sign-white px-3 py-1.5 text-ink">
          <span className="font-display text-xs font-extrabold tracking-[0.12em] uppercase">Recommended</span>
          <span className="ml-2 text-[13px]">{reason}</span>
        </div>
      )}
    </button>
  );
}
```

- [ ] **Step 3: Checkpoint table**

`frontend/src/features/routes/CheckpointTable.tsx`:

```tsx
import type { Route } from '@/api/types';
import { formatClock } from '@/lib/format';
import { LEVEL_COLOR, LEVEL_LABEL } from '@/lib/risk';

export function CheckpointTable({ route }: { route: Route }) {
  return (
    <section aria-labelledby="checkpoints-heading">
      <h2 id="checkpoints-heading" className="field-label">Route {route.id} checkpoints</h2>
      <div className="max-h-[42svh] overflow-auto rounded-md border border-rule bg-white">
        <table className="num w-full text-[12.5px]">
          <thead className="sticky top-0 bg-white text-left text-ink-soft">
            <tr>
              <th className="px-2 py-1.5 font-semibold">Mile</th>
              <th className="px-2 py-1.5 font-semibold">ETA</th>
              <th className="px-2 py-1.5 font-semibold">Wind</th>
              <th className="px-2 py-1.5 font-semibold">Rain</th>
              <th className="px-2 py-1.5 font-semibold">Snow</th>
              <th className="px-2 py-1.5 font-semibold">Risk</th>
            </tr>
          </thead>
          <tbody>
            {route.checkpoints.map((c) => (
              <tr key={c.mile} className="border-t border-rule">
                <td className="px-2 py-1.5">{Math.round(c.mile)}</td>
                <td className="px-2 py-1.5 whitespace-nowrap">{formatClock(c.eta)}</td>
                <td className="px-2 py-1.5 whitespace-nowrap">{Math.round(c.wind_mph)} <span className="text-ink-soft">g{Math.round(c.gust_mph)}</span></td>
                <td className="px-2 py-1.5">{c.rain_in_hr.toFixed(2)}</td>
                <td className="px-2 py-1.5">{c.snow_in_hr.toFixed(2)}</td>
                <td className="px-2 py-1.5 whitespace-nowrap">
                  <span className="mr-1.5 inline-block size-2.5 rounded-full align-middle" style={{ background: LEVEL_COLOR[c.level] }} />
                  {LEVEL_LABEL[c.level]}
                  {c.drivers.length > 0 && <span className="text-ink-soft"> · {c.drivers.join(', ')}{c.load_adjusted ? ' + load' : ''}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1 text-[12px] text-ink-soft">Wind in mph (g = gusts, not scored). Rain and snow in in/hr.</p>
    </section>
  );
}
```

- [ ] **Step 4: The route file**

`frontend/src/routes/trips.$tripId.tsx`:

```tsx
import { Link, createFileRoute, useNavigate } from '@tanstack/react-router';
import { useSuspenseQuery } from '@tanstack/react-query';
import { tripQuery } from '@/api/queries';
import { CheckpointTable } from '@/features/routes/CheckpointTable';
import { RouteSign } from '@/features/routes/RouteSign';
import { formatClock, localZoneName } from '@/lib/format';

export const Route = createFileRoute('/trips/$tripId')({
  validateSearch: (search: Record<string, unknown>): { route?: string } => ({
    route: typeof search.route === 'string' ? search.route : undefined,
  }),
  loader: ({ context: { queryClient }, params }) => queryClient.ensureQueryData(tripQuery(params.tripId)),
  component: TripPanel,
  errorComponent: ({ error }) => (
    <div className="panel">
      <p role="alert">{error.message}</p>
      <Link to="/" className="btn-primary">Plan a new trip</Link>
    </div>
  ),
});

function TripPanel() {
  const { tripId } = Route.useParams();
  const search = Route.useSearch();
  const navigate = useNavigate({ from: Route.fullPath });
  const { data: trip } = useSuspenseQuery(tripQuery(tripId));
  const selectedId = search.route ?? trip.recommendation.route_id;
  const selected = trip.routes.find((r) => r.id === selectedId) ?? trip.routes[0];
  const ranked = [...trip.routes].sort((a, b) => a.rank - b.rank);

  return (
    <div className="panel">
      <header>
        <Link to="/" className="text-[13px] font-medium text-interstate underline-offset-2 hover:underline">← Plan another trip</Link>
        <h1 className="mt-2 font-display text-xl leading-snug font-extrabold">
          {trip.origin.label} → {trip.destination.label}
        </h1>
        <p className="num mt-1 text-[13px] text-ink-soft">
          Leaving {formatClock(trip.departure)} · {trip.load_lb.toLocaleString()} lb · checks every {trip.interval_mi} mi · times in {localZoneName()}
        </p>
      </header>

      {trip.recommendation.all_blocked && (
        <p role="alert" className="rounded-md border-l-4 border-risk-no-travel bg-white px-3 py-2 text-sm">
          Every route crosses No Travel conditions at this departure time. Leave later — drag the timeline to see when the corridor clears.
        </p>
      )}
      {trip.notes.map((note) => (
        <p key={note} className="text-sm text-ink-soft">{note}</p>
      ))}

      <div className="flex flex-col gap-4">
        {ranked.map((route) => (
          <RouteSign key={route.id} route={route}
            recommended={route.id === trip.recommendation.route_id}
            reason={trip.recommendation.reason}
            selected={route.id === selected.id}
            onSelect={() => navigate({ search: { route: route.id }, replace: true })} />
        ))}
      </div>

      <CheckpointTable route={selected} />
    </div>
  );
}
```

- [ ] **Step 5: Verify**

Run `bun run check` (no errors) and plan Chicago → Denver in the browser: three green signs, the recommended one with a white "Recommended" plaque, clicking a sign updates `?route=` and the table; reload keeps the selection; `/trips/<bad-uuid>` shows the error with a working "Plan a new trip" link.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat(web): trip panel with guide-sign route options and checkpoint table"
```

---

### Task 15: Persistent map — routes, checkpoints, popups, heatmap raster

**Files:**
- Create: `frontend/src/features/map/geojson.ts`, `frontend/src/features/map/geojson.test.ts`, `frontend/src/features/map/corridorPixels.ts`, `frontend/src/features/map/corridorPixels.test.ts`, `frontend/src/features/map/layers.ts`, `frontend/src/features/map/CorridorLayer.tsx`, `frontend/src/features/map/TripMap.tsx`, `frontend/src/features/stage/TripStage.tsx`
- Modify: `frontend/src/routes/__root.tsx`

**Interfaces:**
- Consumes: `Trip`, `Corridor`, `positionAt`, `HOUR_MS`, `LEVEL_COLOR`, `LEVELS`, `tripQuery`, `corridorQuery`.
- Produces:
  - `segmentsGeoJson(trip)`, `checkpointsGeoJson(trip)`, `trucksGeoJson(trip, startMs, hour)`, `tripBounds(trip) -> [[w,s],[e,n]]`
  - `corridorPixels(corridor, hour: number) -> Uint8ClampedArray` (RGBA, cols×rows; fractional hours blend neighbouring frames)
  - `<TripMap trip? corridor? hour selectedId? onSelect />`, `<TripStage />` (rendered in root `<main>`; Task 16 adds the logbook to it).

- [ ] **Step 1: Write failing tests for the pure map helpers**

`frontend/src/features/map/corridorPixels.test.ts`:

```ts
import { describe, expect, it } from 'vite-plus/test';
import type { Corridor } from '@/api/types';
import { corridorPixels } from './corridorPixels';

const corridor: Corridor = {
  start: '2026-10-14T00:00:00Z', bounds: [0, 0, 2, 1], cols: 2, rows: 1,
  scores: [[-1, 0.5], [-1, 3.5]],
};

describe('corridorPixels', () => {
  it('leaves masked cells transparent', () => {
    expect(corridorPixels(corridor, 0)[3]).toBe(0);
  });
  it('colors by the level band and strengthens alpha with risk', () => {
    const low = corridorPixels(corridor, 0);
    const severe = corridorPixels(corridor, 1);
    expect([...low.slice(4, 7)]).toEqual([0x5e, 0x9c, 0x76]);
    expect([...severe.slice(4, 7)]).toEqual([0xc8, 0x23, 0x2c]);
    expect(severe[7]).toBeGreaterThan(low[7]);
  });
  it('blends frames for fractional hours', () => {
    expect([...corridorPixels(corridor, 0.5).slice(4, 7)]).toEqual([0xea, 0x7a, 0x1f]); // score 2.0 → high
  });
});
```

`frontend/src/features/map/geojson.test.ts`:

```ts
import { describe, expect, it } from 'vite-plus/test';
import type { Trip } from '@/api/types';
import { checkpointsGeoJson, segmentsGeoJson, tripBounds, trucksGeoJson } from './geojson';

const trip = {
  departure: '2026-10-14T00:30:00Z',
  timeline_start: '2026-10-14T00:00:00Z',
  routes: [{
    id: 'A',
    path: { coordinates: [[-100, 40], [-98, 41]], seconds: [0, 7200] },
    segments: [{ level: 'high', start_mile: 0, end_mile: 10, coordinates: [[-100, 40], [-98, 41]] }],
    checkpoints: [{ mile: 0, lon: -100, lat: 40, level: 'low' }],
  }],
} as unknown as Trip;

describe('map geojson', () => {
  it('tags segments with route and level', () => {
    expect(segmentsGeoJson(trip).features[0].properties).toEqual({ route: 'A', level: 'high' });
  });
  it('indexes checkpoints for hover lookup', () => {
    expect(checkpointsGeoJson(trip).features[0].properties).toMatchObject({ route: 'A', index: 0, level: 'low' });
  });
  it('places trucks relative to departure, not timeline start', () => {
    const start = Date.parse(trip.timeline_start);
    expect(trucksGeoJson(trip, start, 0).features[0].geometry.coordinates).toEqual([-100, 40]);
    expect(trucksGeoJson(trip, start, 1.5).features[0].geometry.coordinates).toEqual([-99, 40.5]);
  });
  it('bounds all route paths', () => {
    expect(tripBounds(trip)).toEqual([[-100, 40], [-98, 41]]);
  });
});
```

Run: `bun run test` → FAIL.

- [ ] **Step 2: Implement the helpers**

`frontend/src/features/map/corridorPixels.ts`:

```ts
import type { Corridor } from '@/api/types';
import { LEVEL_COLOR, LEVELS } from '@/lib/risk';

const RGB = LEVELS.map((level) => {
  const n = Number.parseInt(LEVEL_COLOR[level].slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255] as const;
});

/** RGBA for each grid cell at a (possibly fractional) hour. Color = level band, alpha grows with risk. */
export function corridorPixels(corridor: Corridor, hour: number): Uint8ClampedArray {
  const last = corridor.scores.length - 1;
  const h0 = Math.min(Math.max(Math.floor(hour), 0), last);
  const h1 = Math.min(h0 + 1, last);
  const f = hour - h0;
  const a = corridor.scores[h0];
  const b = corridor.scores[h1];
  const out = new Uint8ClampedArray(a.length * 4);
  for (let k = 0; k < a.length; k++) {
    if (a[k] < 0 || b[k] < 0) continue;
    const score = a[k] + (b[k] - a[k]) * f;
    const [r, g, bl] = RGB[Math.min(Math.floor(score), 4)];
    out.set([r, g, bl, Math.round(255 * Math.min(0.12 + score * 0.18, 0.85))], k * 4);
  }
  return out;
}
```

`frontend/src/features/map/geojson.ts`:

```ts
import type { FeatureCollection, LineString, Point } from 'geojson';
import type { LonLat, Trip } from '@/api/types';
import { HOUR_MS, positionAt } from '@/lib/timeline';

export function segmentsGeoJson(trip: Trip): FeatureCollection<LineString> {
  return {
    type: 'FeatureCollection',
    features: trip.routes.flatMap((r) =>
      r.segments.map((s) => ({
        type: 'Feature' as const,
        properties: { route: r.id, level: s.level },
        geometry: { type: 'LineString' as const, coordinates: s.coordinates },
      })),
    ),
  };
}

export function checkpointsGeoJson(trip: Trip): FeatureCollection<Point> {
  return {
    type: 'FeatureCollection',
    features: trip.routes.flatMap((r) =>
      r.checkpoints.map((c, index) => ({
        type: 'Feature' as const,
        properties: { route: r.id, index, level: c.level },
        geometry: { type: 'Point' as const, coordinates: [c.lon, c.lat] },
      })),
    ),
  };
}

export function trucksGeoJson(trip: Trip, startMs: number, hour: number): FeatureCollection<Point> {
  const sinceDeparture = (startMs + hour * HOUR_MS - Date.parse(trip.departure)) / 1000;
  return {
    type: 'FeatureCollection',
    features: trip.routes.map((r) => {
      const { coord, arrived } = positionAt(r.path, sinceDeparture);
      return { type: 'Feature' as const, properties: { route: r.id, arrived }, geometry: { type: 'Point' as const, coordinates: coord } };
    }),
  };
}

export function tripBounds(trip: Trip): [LonLat, LonLat] {
  let [w, s, e, n] = [Infinity, Infinity, -Infinity, -Infinity];
  for (const r of trip.routes)
    for (const [lon, lat] of r.path.coordinates) {
      w = Math.min(w, lon); s = Math.min(s, lat); e = Math.max(e, lon); n = Math.max(n, lat);
    }
  return [[w, s], [e, n]];
}
```

Install GeoJSON types: `bun add -d @types/geojson`.

Run: `bun run test` → PASS.

- [ ] **Step 3: Layer styles**

`frontend/src/features/map/layers.ts`:

```ts
import type { LayerProps } from 'react-map-gl/maplibre';
import type { ExpressionSpecification } from 'maplibre-gl';
import { LEVEL_COLOR } from '@/lib/risk';

export const BASEMAP = 'https://tiles.openfreemap.org/styles/positron';
export const US_VIEW = { longitude: -97.5, latitude: 39.2, zoom: 3.3 };

const levelColor: ExpressionSpecification = [
  'match', ['get', 'level'],
  'low', LEVEL_COLOR.low, 'moderate', LEVEL_COLOR.moderate, 'high', LEVEL_COLOR.high,
  'severe', LEVEL_COLOR.severe, 'no_travel', LEVEL_COLOR.no_travel, '#888888',
];
const isSelected = (id: string): ExpressionSpecification => ['==', ['get', 'route'], id];

export const casingLayer = (id: string): LayerProps => ({
  id: 'route-casing', type: 'line',
  layout: { 'line-cap': 'round', 'line-join': 'round', 'line-sort-key': ['case', isSelected(id), 1, 0] },
  paint: {
    'line-color': ['case', isSelected(id), '#1E4FA3', '#1E2328'],
    'line-width': ['interpolate', ['linear'], ['zoom'], 4, ['case', isSelected(id), 7, 4], 9, ['case', isSelected(id), 12, 7]],
    'line-opacity': ['case', isSelected(id), 1, 0.35],
  },
});

export const lineLayer = (id: string): LayerProps => ({
  id: 'route-line', type: 'line',
  layout: { 'line-cap': 'round', 'line-join': 'round', 'line-sort-key': ['case', isSelected(id), 1, 0] },
  paint: {
    'line-color': levelColor,
    'line-width': ['interpolate', ['linear'], ['zoom'], 4, ['case', isSelected(id), 4, 2], 9, ['case', isSelected(id), 7, 4]],
    'line-opacity': ['case', isSelected(id), 1, 0.6],
  },
});

export const hitLayer: LayerProps = { id: 'route-hit', type: 'line', paint: { 'line-width': 18, 'line-opacity': 0 } };

export const checkpointLayer = (id: string): LayerProps => ({
  id: 'checkpoint-dots', type: 'circle',
  paint: {
    'circle-color': levelColor,
    'circle-radius': ['case', isSelected(id), 5, 2.5],
    'circle-stroke-color': '#FAFAF7',
    'circle-stroke-width': ['case', isSelected(id), 1.5, 0.5],
    'circle-opacity': ['case', isSelected(id), 1, 0.6],
  },
});

export const truckLayer: LayerProps = {
  id: 'truck-dots', type: 'circle',
  paint: { 'circle-radius': 10, 'circle-color': '#1E2328', 'circle-stroke-color': '#FAFAF7', 'circle-stroke-width': 2 },
};

export const truckLabelLayer: LayerProps = {
  id: 'truck-labels', type: 'symbol',
  layout: { 'text-field': ['get', 'route'], 'text-font': ['Noto Sans Bold'], 'text-size': 12, 'text-allow-overlap': true },
  paint: { 'text-color': '#FAFAF7' },
};

export const heatLayer: LayerProps = {
  id: 'corridor-heat', type: 'raster',
  paint: { 'raster-opacity': 0.8, 'raster-resampling': 'linear', 'raster-fade-duration': 0 },
};
```

- [ ] **Step 4: Heatmap layer (canvas source, repainted per hour without re-uploading data)**

`frontend/src/features/map/CorridorLayer.tsx`:

```tsx
import { useEffect, useMemo } from 'react';
import { Layer, Source, useMap } from 'react-map-gl/maplibre';
import type { CanvasSource } from 'maplibre-gl';
import type { Corridor } from '@/api/types';
import { corridorPixels } from './corridorPixels';
import { heatLayer } from './layers';

export function CorridorLayer({ corridor, hour }: { corridor: Corridor; hour: number }) {
  const { current: map } = useMap();
  const canvas = useMemo(() => {
    const c = document.createElement('canvas');
    c.width = corridor.cols;
    c.height = corridor.rows;
    return c;
  }, [corridor]);

  useEffect(() => {
    canvas
      .getContext('2d')!
      .putImageData(new ImageData(corridorPixels(corridor, hour), corridor.cols, corridor.rows), 0, 0);
    const source = map?.getSource('corridor') as CanvasSource | undefined;
    if (!source) return;
    // A paused canvas source only re-reads its pixels while playing: play for one frame, then pause.
    source.play();
    map!.triggerRepaint();
    const id = requestAnimationFrame(() => requestAnimationFrame(() => source.pause()));
    return () => cancelAnimationFrame(id);
  }, [canvas, corridor, hour, map]);

  const [w, s, e, n] = corridor.bounds;
  return (
    <Source id="corridor" type="canvas" canvas={canvas} animate={false}
      coordinates={[[w, n], [e, n], [e, s], [w, s]]}>
      <Layer {...heatLayer} beforeId="route-casing" />
    </Source>
  );
}
```

If the raster does not update while dragging in Step 7, replace the play/pause block with `source.play()` on the slider's `pointerdown` and `source.pause()` on `pointerup` (wired through a `dragging` prop), which keeps the source live only during interaction.

- [ ] **Step 5: The map**

`frontend/src/features/map/TripMap.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Map, { Layer, Popup, Source, type MapLayerMouseEvent, type MapRef } from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { Corridor, Trip } from '@/api/types';
import { formatClock } from '@/lib/format';
import { LEVEL_LABEL } from '@/lib/risk';
import { CorridorLayer } from './CorridorLayer';
import { checkpointsGeoJson, segmentsGeoJson, tripBounds, trucksGeoJson } from './geojson';
import { BASEMAP, US_VIEW, casingLayer, checkpointLayer, hitLayer, lineLayer, truckLabelLayer, truckLayer } from './layers';

interface Props {
  trip?: Trip;
  corridor?: Corridor;
  hour: number;
  selectedId?: string;
  onSelect: (routeId: string) => void;
}

const EMPTY = { type: 'FeatureCollection' as const, features: [] };
const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

export function TripMap({ trip, corridor, hour, selectedId = '', onSelect }: Props) {
  const mapRef = useRef<MapRef>(null);
  const [loaded, setLoaded] = useState(false);
  const [hover, setHover] = useState<{ route: string; index: number } | null>(null);

  const segments = useMemo(() => (trip ? segmentsGeoJson(trip) : EMPTY), [trip]);
  const checkpoints = useMemo(() => (trip ? checkpointsGeoJson(trip) : EMPTY), [trip]);
  const startMs = trip ? Date.parse(trip.timeline_start) : 0;
  const trucks = useMemo(() => (trip ? trucksGeoJson(trip, startMs, hour) : EMPTY), [trip, startMs, hour]);

  useEffect(() => {
    if (!loaded || !trip) return;
    mapRef.current?.fitBounds(tripBounds(trip), { padding: 64, duration: reducedMotion() ? 0 : 900 });
  }, [loaded, trip?.id]);

  const onMove = useCallback((e: MapLayerMouseEvent) => {
    const f = e.features?.find((x) => x.layer.id === 'checkpoint-dots');
    setHover(f ? { route: f.properties.route, index: f.properties.index } : null);
  }, []);

  const hovered = hover && trip?.routes.find((r) => r.id === hover.route)?.checkpoints[hover.index];

  return (
    <Map ref={mapRef} initialViewState={US_VIEW} mapStyle={BASEMAP} onLoad={() => setLoaded(true)}
      interactiveLayerIds={['route-hit', 'checkpoint-dots']} onMouseMove={onMove} onMouseLeave={() => setHover(null)}
      onClick={(e) => { const id = e.features?.[0]?.properties?.route; if (id) onSelect(id); }}
      cursor={hover ? 'pointer' : 'grab'} attributionControl={{ compact: true }} style={{ width: '100%', height: '100%' }}>
      <Source id="segments" type="geojson" data={segments}>
        <Layer {...casingLayer(selectedId)} />
        <Layer {...lineLayer(selectedId)} />
        <Layer {...hitLayer} />
      </Source>
      {corridor && trip && <CorridorLayer corridor={corridor} hour={hour} />}
      <Source id="checkpoints" type="geojson" data={checkpoints}>
        <Layer {...checkpointLayer(selectedId)} />
      </Source>
      <Source id="trucks" type="geojson" data={trucks}>
        <Layer {...truckLayer} />
        <Layer {...truckLabelLayer} />
      </Source>
      {hovered && (
        <Popup longitude={hovered.lon} latitude={hovered.lat} closeButton={false} offset={10} maxWidth="260px">
          <div className="num text-[12px] leading-relaxed text-ink">
            <strong className="font-display text-[13px]">Route {hover!.route} · mile {Math.round(hovered.mile)}</strong>
            <div>ETA {formatClock(hovered.eta)}</div>
            <div>Wind {Math.round(hovered.wind_mph)} mph (gusts {Math.round(hovered.gust_mph)})</div>
            <div>Rain {hovered.rain_in_hr.toFixed(2)} in/hr · Snow {hovered.snow_in_hr.toFixed(2)} in/hr</div>
            <div className="font-semibold">
              {LEVEL_LABEL[hovered.level]}
              {hovered.drivers.length > 0 && ` — ${hovered.drivers.join(', ')}${hovered.load_adjusted ? ', raised by load' : ''}`}
            </div>
          </div>
        </Popup>
      )}
    </Map>
  );
}
```

- [ ] **Step 6: The stage in the root layout**

`frontend/src/features/stage/TripStage.tsx`:

```tsx
import { useState } from 'react';
import { useMatch, useNavigate } from '@tanstack/react-router';
import { useQuery } from '@tanstack/react-query';
import { corridorQuery, tripQuery } from '@/api/queries';
import { TripMap } from '@/features/map/TripMap';

export function TripStage() {
  const match = useMatch({ from: '/trips/$tripId', shouldThrow: false });
  const tripId = match?.params.tripId;
  return <Stage key={tripId ?? 'none'} tripId={tripId} routeParam={match?.search.route} />;
}

function Stage({ tripId, routeParam }: { tripId?: string; routeParam?: string }) {
  const navigate = useNavigate();
  const [hour, setHour] = useState(0);
  const trip = useQuery({ ...tripQuery(tripId ?? ''), enabled: !!tripId }).data;
  const corridor = useQuery({ ...corridorQuery(tripId ?? ''), enabled: !!trip }).data;
  const selectedId = routeParam ?? trip?.recommendation.route_id;

  return (
    <div className="relative h-full">
      <TripMap trip={trip} corridor={corridor} hour={hour} selectedId={selectedId}
        onSelect={(route) => tripId && navigate({ to: '/trips/$tripId', params: { tripId }, search: { route }, replace: true })} />
    </div>
  );
}
```

(Keying `Stage` by trip id resets the hour for each new trip without an effect; the `Map` lives in `TripMap`, which remounts only when the key changes — acceptable because a new trip refits the view anyway. If the remount flash is visible, lift `<TripMap>` above the keyed component and key only the hour state.)

`frontend/src/routes/__root.tsx` — replace the empty `<main>` with:

```tsx
<main className="order-1 min-h-0 md:order-2" aria-label="Route map">
  <TripStage />
</main>
```

and add `import { TripStage } from '@/features/stage/TripStage';`.

- [ ] **Step 7: Verify in the browser**

Plan Chicago → Denver. Check: the map flies to the routes; the selected route has a blue casing and full-color risk segments, the others are dimmed; hovering a checkpoint shows ETA, wind, rain, snow, level and driver; clicking a dimmed route selects it and the panel follows; once the corridor loads, a soft risk raster sits under the routes. Take a screenshot and compare against the Design Direction: signs green, paper background, nothing glowing.

- [ ] **Step 8: Commit**

```bash
git add frontend/src frontend/package.json frontend/bun.lock
git commit -m "feat(web): persistent MapLibre map with risk segments, checkpoints and corridor raster"
```

---

### Task 16: Logbook scrubber (signature) wired to heatmap and trucks

**Files:**
- Create: `frontend/src/features/logbook/LogbookScrubber.tsx`, `frontend/src/features/logbook/logbook.test.ts`
- Modify: `frontend/src/features/stage/TripStage.tsx`

**Interfaces:**
- Consumes: `levelDuring`, `HOUR_MS`, `TIMELINE_HOURS`, `formatClock`, `formatHourTick`, `LEVEL_COLOR`, `LEVEL_LABEL`, `Trip`.
- Produces: `logbookRows(trip, startMs) -> { id: string; cells: (Level | null)[] }[]`; `<LogbookScrubber trip hour onHour selectedId />`.

- [ ] **Step 1: Write the failing test**

`frontend/src/features/logbook/logbook.test.ts`:

```ts
import { describe, expect, it } from 'vite-plus/test';
import type { Trip } from '@/api/types';
import { logbookRows } from './LogbookScrubber';

const T0 = Date.parse('2026-10-14T00:00:00Z');
const cp = (h: number, level: string) => ({ eta: new Date(T0 + h * 3_600_000).toISOString(), level });
const trip = { routes: [{ id: 'A', checkpoints: [cp(0, 'low'), cp(1.5, 'high'), cp(3, 'low')] }] } as unknown as Trip;

describe('logbookRows', () => {
  it('has 48 hourly cells per route, empty after arrival', () => {
    const [row] = logbookRows(trip, T0);
    expect(row.cells).toHaveLength(48);
    expect(row.cells.slice(0, 4)).toEqual(['low', 'high', 'high', 'low']);
    expect(row.cells[4]).toBeNull();
  });
});
```

Run: `bun run test` → FAIL.

- [ ] **Step 2: Implement**

`frontend/src/features/logbook/LogbookScrubber.tsx`:

```tsx
import { useMemo } from 'react';
import type { Trip } from '@/api/types';
import { formatClock, formatHourTick } from '@/lib/format';
import { LEVEL_COLOR, LEVEL_LABEL, type Level } from '@/lib/risk';
import { HOUR_MS, TIMELINE_HOURS, levelDuring } from '@/lib/timeline';

const COL = 10;
const ROW = 16;
const TOP = 4;

export function logbookRows(trip: Trip, startMs: number): { id: string; cells: (Level | null)[] }[] {
  return trip.routes.map((r) => ({
    id: r.id,
    cells: Array.from({ length: TIMELINE_HOURS }, (_, h) => levelDuring(r, startMs, h)),
  }));
}

interface Props {
  trip: Trip;
  hour: number;
  onHour: (hour: number) => void;
  selectedId?: string;
}

export function LogbookScrubber({ trip, hour, onHour, selectedId }: Props) {
  const startMs = Date.parse(trip.timeline_start);
  const rows = useMemo(() => logbookRows(trip, startMs), [trip, startMs]);
  const width = TIMELINE_HOURS * COL;
  const height = TOP + rows.length * ROW;
  const atMs = startMs + hour * HOUR_MS;
  const ticks = Array.from({ length: TIMELINE_HOURS / 6 + 1 }, (_, i) => i * 6);

  return (
    <section aria-label="Forecast timeline" className="border-t border-rule bg-paper px-3 pt-2 pb-3 md:px-5">
      <div className="mb-1.5 flex items-baseline justify-between gap-3">
        <h2 className="field-label mb-0">Forecast · drag through the next 48 hours</h2>
        <p className="num text-[13px] font-semibold" aria-live="polite">
          {formatClock(atMs)} <span className="font-normal text-ink-soft">+{Math.floor(hour)} h</span>
        </p>
      </div>
      <div className="flex gap-2">
        <div className="flex flex-col pt-[3px]" aria-hidden>
          {rows.map((r) => (
            <span key={r.id} className={`font-display text-[13px] leading-[16px] font-extrabold ${r.id === selectedId ? 'text-interstate' : 'text-ink-soft'}`}>
              {r.id}
            </span>
          ))}
        </div>
        <div className="relative flex-1 rounded-[3px] bg-white ring-1 ring-rule has-[input:focus-visible]:ring-3 has-[input:focus-visible]:ring-interstate">
          <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" className="block h-[60px] w-full" aria-hidden>
            {Array.from({ length: TIMELINE_HOURS + 1 }, (_, h) => {
              const midnight = new Date(startMs + h * HOUR_MS).getHours() === 0;
              return (
                <line key={h} x1={h * COL} x2={h * COL} y1={0} y2={height}
                  stroke={midnight ? '#1E2328' : '#D5DBD6'} strokeWidth={midnight ? 1.2 : h % 6 === 0 ? 0.6 : 0.3}
                  vectorEffect="non-scaling-stroke" />
              );
            })}
            {rows.map((r, i) =>
              r.cells.map((level, h) =>
                level ? (
                  <line key={`${r.id}-${h}`} x1={h * COL} x2={(h + 1) * COL} y1={TOP + i * ROW + ROW / 2} y2={TOP + i * ROW + ROW / 2}
                    stroke={LEVEL_COLOR[level]} strokeWidth={r.id === selectedId ? 7 : 4} strokeLinecap="butt" vectorEffect="non-scaling-stroke">
                    <title>{`Route ${r.id}, hour ${h}: ${LEVEL_LABEL[level]}`}</title>
                  </line>
                ) : null,
              ),
            )}
            <line x1={hour * COL} x2={hour * COL} y1={0} y2={height} stroke="#1E4FA3" strokeWidth={2} vectorEffect="non-scaling-stroke" />
          </svg>
          <input type="range" min={0} max={TIMELINE_HOURS} step={0.25} value={hour}
            onChange={(e) => onHour(Number(e.target.value))}
            aria-label="Forecast hour" aria-valuetext={`${formatClock(atMs)}, ${Math.floor(hour)} hours after departure hour`}
            className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0" />
        </div>
      </div>
      <div className="num relative mt-1 ml-5 h-4 text-[11px] text-ink-soft" aria-hidden>
        {ticks.map((h) => (
          <span key={h} className="absolute -translate-x-1/2" style={{ left: `${(h / TIMELINE_HOURS) * 100}%` }}>
            {formatHourTick(startMs + h * HOUR_MS)}
          </span>
        ))}
      </div>
    </section>
  );
}
```

- [ ] **Step 3: Wire into the stage**

In `frontend/src/features/stage/TripStage.tsx`, change `Stage`'s return to:

```tsx
return (
  <div className="flex h-full flex-col">
    <div className="relative min-h-0 flex-1">
      <TripMap trip={trip} corridor={corridor} hour={hour} selectedId={selectedId}
        onSelect={(route) => tripId && navigate({ to: '/trips/$tripId', params: { tripId }, search: { route }, replace: true })} />
      {trip && !corridor && (
        <p className="chip absolute top-3 left-3">Loading the 48-hour forecast corridor…</p>
      )}
    </div>
    {trip && <LogbookScrubber trip={trip} hour={hour} onHour={setHour} selectedId={selectedId} />}
  </div>
);
```

and import `LogbookScrubber`.

- [ ] **Step 4: Verify behavior and smoothness**

`bun run test && bun run check` → PASS. In the browser: drag the logbook — the heatmap blends between hours, all three lettered truck markers move along their routes and park at the destination after arrival, the clock label updates; Tab to the logbook and press ←/→ — the cursor moves in 15-minute steps with a visible blue focus ring. Record a Chrome DevTools performance trace while dragging for ~5 s: no long tasks over 50 ms, frames ≥ 50 fps on a laptop. If repaint lags, check `CorridorLayer`'s play/pause fallback (Task 15 Step 4).

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(web): logbook timeline scrubber driving heatmap and truck positions"
```

---

### Task 17: Single-service deploy, README

**Files:**
- Create: `backend/config/views.py`, `Dockerfile`, `.dockerignore`, `render.yaml`, `README.md`
- Modify: `backend/config/urls.py`
- Test: `backend/trips/tests/test_spa.py`

**Interfaces:**
- Consumes: built SPA in `backend/frontend_dist/`.
- Produces: `GET /` and any non-`/api/` path → `index.html`; assets served by WhiteNoise from `FRONTEND_DIST`.

- [ ] **Step 1: Write the failing test**

`backend/trips/tests/test_spa.py`:

```python
def test_client_routes_serve_the_spa(client, settings, tmp_path):
    (tmp_path / "index.html").write_text("<div id=root></div>")
    settings.FRONTEND_DIST = tmp_path
    response = client.get("/trips/abc")
    assert response.status_code == 200
    assert b"id=root" in b"".join(response.streaming_content)


def test_missing_build_is_404(client, settings, tmp_path):
    settings.FRONTEND_DIST = tmp_path / "nope"
    assert client.get("/").status_code == 404
```

Run: `uv run pytest trips/tests/test_spa.py -v` → FAIL (404 on `/trips/abc` in the first test).

- [ ] **Step 2: Implement**

`backend/config/views.py`:

```python
from django.conf import settings
from django.http import FileResponse, Http404


def spa(request, path=""):
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        raise Http404("Frontend not built. Run `bun run build` in frontend/.")
    return FileResponse(index.open("rb"), content_type="text/html")
```

`backend/config/urls.py`:

```python
from django.urls import path, re_path

from config.views import spa
from trips.api import api

urlpatterns = [
    path("api/", api.urls),
    re_path(r"^(?!api/)(?P<path>.*)$", spa),
]
```

Run: `uv run pytest -v` → all PASS.

- [ ] **Step 3: Container**

`Dockerfile` (repo root):

```dockerfile
FROM oven/bun:1 AS web
WORKDIR /web
COPY frontend/package.json frontend/bun.lock ./
RUN bun install --frozen-lockfile
COPY frontend/ ./
RUN bun run build

FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY --from=web /web/dist ./frontend_dist
ENV PATH="/app/.venv/bin:$PATH" DJANGO_DEBUG=0 SQLITE_PATH=/app/data/db.sqlite3
RUN mkdir -p /app/data && python manage.py collectstatic --noinput
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 2 --threads 4 --timeout 120"]
```

`.dockerignore`:

```
**/node_modules
**/.venv
frontend/dist
backend/db.sqlite3
.git
```

`render.yaml`:

```yaml
services:
  - type: web
    name: weather-aware-truck-routing
    runtime: docker
    plan: free
    healthCheckPath: /api/health
    envVars:
      - key: DJANGO_SECRET_KEY
        generateValue: true
      - key: DJANGO_ALLOWED_HOSTS
        value: .onrender.com
      - key: DJANGO_CSRF_TRUSTED_ORIGINS
        value: https://*.onrender.com
```

Verify locally:

```bash
docker build -t truck-routing . && docker run --rm -p 8000:8000 -e DJANGO_ALLOWED_HOSTS=localhost truck-routing
```

Open http://localhost:8000, plan Chicago → Denver, reload a `/trips/<id>?route=B` URL directly — it must load.

- [ ] **Step 4: README**

`README.md` — write these sections with real content (no placeholders):
1. **What it does** — two sentences + screenshot (`docs/screenshot.png`, taken in Step 5).
2. **Run locally** — `cd backend && uv sync && uv run python manage.py migrate && uv run python manage.py runserver`; `cd frontend && bun install && bun run dev`; tests: `uv run pytest`, `bun run test`.
3. **How a trip is planned** — numbered pipeline (this one *is* a sequence): geocode → Valhalla truck routes (+detours to reach 3) → checkpoints every N mi with drive-time ETAs → Open-Meteo hourly forecast at each ETA → risk rules → segment miles → ranking → persisted trip; corridor grid scored for 49 hours.
4. **Risk rules as implemented** — the Global Constraints bullets on band edges, load rules, wind = sustained, rain = rain + showers, segment = worse endpoint, No Travel ranked before Severe.
5. **Assumptions and limits** — no hours-of-service breaks in ETAs; public Valhalla/Open-Meteo/Photon servers (fair-use, no SLA); forecasts cached 1 h, corridor cached per trip; 0.05° forecast snapping; departures within 7 days.
6. **Code map** — the File Structure tree trimmed to the important files.
7. **Deploy** — Render blueprint steps.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore render.yaml README.md backend/config backend/trips/tests/test_spa.py docs
git commit -m "chore: single-container deploy serving the SPA from Django; README"
```

---

### Task 18: End-to-end verification and hosting

**Files:** none new (fixes only, each with its own commit).

- [ ] **Step 1: Full test + static checks**

```bash
cd backend && uv run pytest -q && uv run ruff check .
cd ../frontend && bun run test && bun run check && bun run build
```

Expected: all green; build output under `frontend/dist`.

- [ ] **Step 2: Scenario walk-through in a real browser** (use the agent-browser or Chrome DevTools MCP)

1. Chicago → Denver, now + 2 h, 42,000 lb, every 25 mi → 3 signs, one recommended with a reason that matches the numbers on the signs.
2. Same trip at 10 mi and 50 mi → checkpoint counts change (~100 / ~21 per route); recommendation logic still consistent.
3. Load 30,000 vs 30,001 on a windy day → any 45–54 mph checkpoint flips Severe → No Travel (check the table's "+ load" marker).
4. Departure 8 days out → form blocks it with "Pick a departure within the next 7 days."
5. Two places 0.5 mi apart → server message about same place / note about fewer routes; no crash.
6. Stop the backend, submit → "Can't reach the server…" shown in the form.
7. Mobile (375×812): map on top, logbook under it, panel scrolls; all controls reachable by keyboard; reduced-motion on → map jumps instead of flying.
8. DevTools performance trace while dragging the logbook: no long tasks > 50 ms.

Fix anything that fails, with a test first where the failure is in logic.

- [ ] **Step 3: Host**

This needs the user's accounts — ask them before doing it:
- Push to a new GitHub repository (`gh repo create weather-aware-truck-routing --public --source . --push`), after the user confirms visibility.
- Create the Render service from `render.yaml` (Render dashboard → New → Blueprint → pick the repo). Set `HTTP_USER_AGENT` to include the real repo URL.
- Smoke-test the hosted URL with scenario 1; put the URL in the README.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "docs: hosted URL and verification notes"
```

The Loom walkthrough is recorded by the user; suggested outline: problem (30 s) → plan a trip (1 min) → read the signs and recommendation reason (1 min) → map hover + logbook scrub (2 min) → risk engine code and tests (2 min) → assumptions (1 min).
