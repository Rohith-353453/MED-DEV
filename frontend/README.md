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
- Firebase Authentication handles email/password sign-in. Without the Firebase variables, the frontend connects to a backend configured with local `AUTH_MODE=mock`.

Copy `.env.example` to `.env` for local development. Vite proxies `/api` to `http://127.0.0.1:8000` by default. Configure `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, and `VITE_FIREBASE_APP_ID` for Firebase sign-in. These are Firebase web-app settings; never place Azure OpenAI keys, database passwords, or private keys in Vite variables. Add the deployed Static Web App hostname to Firebase Authentication's authorized domains.

The browser stores the short-lived Firebase ID token in tab-scoped session storage. The API validates its signature, issuer, audience, expiration, and Firebase project ID. Configure the backend with the same `FIREBASE_PROJECT_ID` and add the exact frontend origin to `FRONTEND_ORIGINS`.

The interface and generated summaries support English (`en`), Hindi (`hi`), Tamil (`ta`), Telugu (`te`), and Malayalam (`ml`). Select a language in the top bar or profile preferences. The preference is saved to the profile and used for new upload-time summaries; regenerate an existing document summary to apply a changed language.
