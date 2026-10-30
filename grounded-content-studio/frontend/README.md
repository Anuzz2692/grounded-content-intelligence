# Grounded Content Studio (frontend)

React + Vite single-page app for the content generation API.

## Run it

**Production-style (one server, recommended):** build once, then FastAPI serves the UI and the API together.

```powershell
cd frontend
npm install
npm run build
cd ..
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000. Rebuild (`npm run build`) after changing frontend code.

**Development (hot reload):** run the backend, then in a second terminal:

```powershell
cd frontend
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` and `/health` to `http://127.0.0.1:8000`; set `VITE_BACKEND_URL` to use another address.

## Test

```powershell
npm test
```

## Re-branding

All colours and fonts are CSS variables in `src/styles/theme.css`. The values there are placeholders, not a real brand palette: replace `--brand*`, `--accent` and the two font families.

## API key

If the server sets `API_KEYS`, add a key under Settings (gear icon). It is kept for the browser tab only unless "Remember on this device" is ticked. A key held in browser code is visible to anyone using that browser, so for a public deployment keep access control on the server side.
