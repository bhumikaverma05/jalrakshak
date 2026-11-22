# JalRakshak Frontend

React and Vite application shell with browser routing, an Axios API client, and an overview page that checks the FastAPI health route. Leaflet, React Leaflet, and Recharts are installed for later GIS and dashboard milestones; no map, chart, or monitoring workflow is implemented yet.

## Local setup (PowerShell)

From the repository root:

```powershell
Copy-Item frontend/.env.example frontend/.env
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:5173`. The frontend uses `VITE_API_BASE_URL` from `.env` to reach the backend. Create a production bundle with `npm.cmd run build` and run the static preview with `npm.cmd run preview`.
