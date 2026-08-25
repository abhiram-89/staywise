# staywise

An AI-powered hotel budget forecasting app. Sign in, import a hotel P&L file, review live KPIs, generate a 3 / 6 / 12 month forecast, and inspect rooms, graphs, and clients.

This repository has **two folders**:

```
frontend/    Next.js staywise UI
Backend/     FastAPI API + CognoDB graph database
```

The browser never talks to the database. Flow is always:

**User → frontend (Next.js) → Backend (FastAPI) → CognoDB (graph)**

---

## End-to-end approach

1. A GM or analyst **creates an account**. The API stores the user in the graph and emails a 6-digit OTP (or shows it on screen if email is not configured).
2. After OTP verify + login, the UI sends a JWT on every request and an `X-Hotel-Id` header for the active **workspace / client**.
3. **Import report** uploads Excel / CSV / JSON. The frontend parses the file; the backend normalizes rows (`year`, `month`, revenue) and writes monthly snapshots, department spend, and room mix into CognoDB. That file becomes the live source for every screen.
4. **Overview** reads KPIs, trend, and expense mix from those snapshots.
5. **Historical** lists the same months with date and category filters.
6. **Forecasts** run a graph-analog model (Prophet is used as a blend when installed), save a `ForecastRun`, and can export Excel.
7. **Graph explorer** shows how hotel, city, months, rooms, departments, and forecast runs are linked.
8. **Rooms & rates** show unique room types, availability, nightly rate, and demand from the latest imported month.
9. **Settings** lets you edit your username. The header avatar shows name, email, and current property on hover or click.
10. **Workspace** in the sidebar switches clients or adds a new one. Each client has its own history and forecasts.
11. **MIRA** answers questions about import, forecast, rooms, and this workspace using the same graph data.

If CognoDB is down, the API returns **503** and the UI shows an error instead of crashing.

---

## What you need

- Node.js 18+ (pnpm or npm)
- Python 3.11+
- A free [CognoDB](https://console.cognodb.com/signup) instance

Do not commit `env/`, `venv/`, `.venv/`, or `.env` files. Copy the example env files locally.

---

## 1. Start the backend

```bash
cd Backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
copy .env.example .env          # then edit .env
```

Minimum `Backend/.env`:

```
COGNODB_URI=bolt+s://<instance-id>.bravo.databases.cognodb.com
COGNODB_USER=cognodb
COGNODB_PASSWORD=<password shown once in the CognoDB console>
JWT_SECRET=change-me-to-a-long-random-string
FRONTEND_ORIGIN=http://localhost:3000
HOTEL_ID=grand-metro
```

Create the instance at [console.cognodb.com](https://console.cognodb.com/signup), copy the Bolt URI and password, then:

```bash
python -m scripts.seed
uvicorn main:app --reload --port 8000
```

Health check: http://127.0.0.1:8000/api/health

`scripts.seed` loads the demo hotel, months, rooms, and departments. Re-running it rebuilds financial data and leaves user accounts in place.

Optional SMTP (so OTP is emailed):

```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=<gmail-app-password>
DEBUG_RETURN_OTP=false
```

---

## 2. Start the frontend

Keep the API running. In another terminal:

```bash
cd frontend
pnpm install                    # or npm install
copy .env.example .env.local    # Windows; already set in most clones
```

`frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

```bash
pnpm dev                        # or npm run dev
```

Open http://localhost:3000

---

## 3. Walk through the product

| Step | What to do |
| --- | --- |
| Sign up | Name, email, password (8+ characters) → OTP |
| Verify | Enter the 6-digit code, then sign in |
| Import | **Import report** — columns: year, month (or date), `Room Revenue` |
| Overview | Revenue, expenses, profit, occupancy, charts |
| Historical | Filter months and categories |
| Forecasts | Horizon 3 / 6 / 12 months → Run forecast → Export Excel |
| Graph explorer | Click nodes to see relationships |
| Rooms & rates | Unique types, rates, demand |
| Header avatar | Hover or click for name, email, and property |
| Workspace | Switch or add clients |
| MIRA | Bottom-right assistant |
| Logout | Icon at the bottom of the sidebar |

Report files: `.xlsx`, `.xls`, `.csv`, or `.json`.

---

## Project map

| Path | Role |
| --- | --- |
| `frontend/app` | Routes: `/`, `/login`, `/signup`, `/verify-otp` |
| `frontend/components` | Dashboard, auth, MIRA |
| `frontend/lib` | API client, report parser, formatting |
| `Backend/main.py` | HTTP API |
| `Backend/ingest.py` | Normalize uploads into the graph |
| `Backend/forecast_engine.py` | Graph-analog forecast |
| `Backend/queries.py` | Parameterized Cypher |
| `Backend/scripts/seed.py` | Demo graph |
| `Backend/data/` | Seed CSV |

---

## Deploy (free)

1. **API** — [Render](https://render.com) or [Railway](https://railway.app): `uvicorn main:app --host 0.0.0.0 --port $PORT`. Set `COGNODB_*`, `JWT_SECRET`, and `FRONTEND_ORIGIN` as secrets.
2. **UI** — [Vercel](https://vercel.com) or [Netlify](https://www.netlify.com): root directory `frontend`, env `NEXT_PUBLIC_API_URL` = public API URL.
3. Point `FRONTEND_ORIGIN` at the UI origin so CORS allows the browser.

Repo: https://github.com/abhiram-89/staywise
