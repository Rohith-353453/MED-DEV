# Carefolio frontend

React + TypeScript + Vite interface for the AI Health Copilot described in `../AI-Health-Copilot-AZURE-SPEC.md`.

## Run locally

```powershell
cd frontend
npm install
npm run dev
```

Open the local URL Vite prints (normally `http://localhost:5173`).

## Current scope

- Live dashboard, document upload and processing status, timeline, document detail, profile settings, extraction correction, summary correction, and original-file download.
- Status polling continues while documents are queued or processing. Empty accounts stay empty; the UI does not add pretend patient records.
- Upload accepts PDF, JPG, and PNG up to 10 MB. The local mock providers process the included synthetic fixture only; arbitrary documents are marked for review without invented OCR or health facts.
- Entra External ID sign-in uses Authorization Code with PKCE. Without the Entra variables, the frontend connects to a backend configured with local `AUTH_MODE=mock`.

Copy `.env.example` to `.env` for local development. Vite proxies `/api` to `http://127.0.0.1:8000` by default. For Entra mode, set the client ID, authority, API scope, and registered redirect URI shown in the example. The authority should publish `/.well-known/openid-configuration`. These are public SPA settings; never place a client secret, database password, or private key in Vite variables. Entra must allow the SPA origin and redirect URI; use HTTPS except on localhost.

The browser stores the short-lived access token in tab-scoped session storage. The API validates its signature, issuer, audience, expiration, and required scope. Register both the local frontend origin and the deployed Static Web App origin in the SPA app registration, and allow the SPA to request the API scope.
