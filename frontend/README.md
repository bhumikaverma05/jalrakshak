# JalRakshak Frontend

React and Vite frontend with dashboard and GIS map routes. The map reads paginated water-body registry data from FastAPI and draws only returned boundaries or registered points. Satellite observation APIs remain staff-only and are not called by the public map.

## Local setup (PowerShell)

From the repository root:

```powershell
Copy-Item frontend/.env.example frontend/.env
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

Open `http://localhost:5173`. The frontend uses `VITE_API_BASE_URL` from `.env` to reach the backend. Create a production bundle with `npm.cmd run build` and run the static preview with `npm.cmd run preview`.

The GIS map uses Leaflet with OpenStreetMap tiles by default. Configure `VITE_OSM_TILE_URL` and `VITE_MAP_TILE_ATTRIBUTION` together if using a different tile provider; keep that provider's required attribution visible. Registry boundaries are optional, and the map does not estimate missing boundaries.
