# Layer 5: First Working Frontend Dashboard

## Purpose
Layer 5 is the first user-facing interface for the ADITI 4.0 SSA Platform. It is a React application that communicates exclusively with the Layer 4 FastAPI backend. No orbital calculations are performed in the frontend.

## Technology Stack
- **React 18** — UI framework
- **TypeScript** — type safety and API contract enforcement
- **Vite 5** — build tool and dev server
- **Tailwind CSS 3** — utility-first styling
- **react-router-dom 6** — client-side routing

## Pages
| Route | Page | Purpose |
|-------|------|---------|
| `/` | DashboardPage | System status, satellite sample, navigation |
| `/satellites` | SatelliteExplorerPage | GP data lookup and orbit propagation |
| `/conjunction` | ConjunctionAnalysisPage | Close-approach analysis |

## API Client
All HTTP requests pass through `src/api/client.ts`. Components and pages never call `fetch()` directly.

In development the Vite dev server proxies `/health`, `/satellites`, and `/conjunction` to `http://localhost:8000`, avoiding CORS entirely without modifying the backend.

## Running the Application
Start the FastAPI backend:
```bash
uvicorn backend.main:app --reload
```
Start the Vite dev server:
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173` in the browser.

## Environment Variable
`VITE_API_BASE_URL` — defaults to empty (Vite proxy) in development. Set to the backend URL for production deployments.

## Out of Scope
This layer does NOT implement CesiumJS, PostgreSQL, ML, risk scoring, authentication, or deployment configuration.
