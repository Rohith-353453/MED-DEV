# Carefolio hackathon demo

Use this path when the Azure API is unavailable or when Azure AI credentials must not
be moved to another host. It runs the existing backend and frontend locally with mock
OCR/AI providers and local private storage. It does not require Azure credentials,
Firebase Admin credentials, Entra credentials, or access to ABDM.

## Start the demo

From the repository root:

```powershell
docker compose up --build
```

In a second terminal:

```powershell
Set-Location frontend
Copy-Item .env.example .env
npm install
npm run dev
```

Open the Vite URL, normally `http://localhost:5173`. Confirm the header says
**Local demo** and that the frontend is using `VITE_API_BASE_URL=/api`. The Vite
configuration proxies `/api` to `http://127.0.0.1:8000`; do not point this build at
the unhealthy Azure API.

Upload only `samples/synthetic-lab-report.pdf`. The local mock pipeline recognizes
that explicitly marked fictional fixture. Other documents are moved to
`needs_review` without invented OCR or health facts.

## Demo boundaries

- The backend uses `AUTH_MODE=mock` and associates local requests with the configured
  `MOCK_USER_SUB`; it is not suitable for production or public deployment.
- OCR and summaries are mock-provider output for the synthetic fixture. This demo
  does not prove Azure Document Intelligence or Azure OpenAI processing works.
- The FHIR endpoint is a prototype export only. It uses mock identifiers and does
  not connect to ABDM or another health exchange.
- Firebase client login and the multilingual UI remain separate frontend features;
  this local mock backend does not validate Firebase tokens or provide production
  identity isolation.

Do not upload real patient records. Delete the local database and uploads after the
demo if they are no longer needed.
