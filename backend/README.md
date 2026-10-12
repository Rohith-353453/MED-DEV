# Carefolio API

FastAPI backend for the AI Health Copilot. The API is designed around editable patient-owned records: names, profile details, extracted fields, document dates/types, summaries, and timeline events can all be corrected through `PATCH` endpoints.

## Local run

From the `backend` directory:

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
uvicorn app.main:app --reload
```

The default local configuration uses SQLite, local private file storage, local in-process background processing, and mock OCR/AI providers. OpenAPI is available at `http://localhost:8000/docs`. The mock pipeline processes the explicitly marked synthetic fixture in `samples/synthetic-lab-report.pdf`; arbitrary uploads receive no invented OCR text or health facts and move to `needs_review`. Local queued and interrupted processing records resume when the API restarts.

Alternatively, run PostgreSQL and the API using Docker Compose from the repository root:

```powershell
docker compose up --build
```

The demo profile is created on the first authenticated request. In local `AUTH_MODE=mock`, requests are associated with the configured `MOCK_USER_SUB`. This mode is rejected automatically when `APP_ENV` is a deployed environment.

For the full local demo, start the backend and frontend, then upload `samples/synthetic-lab-report.pdf`. The mock flow produces only the fictional facts embedded in this marked fixture and clearly labels it synthetic. Other documents are not read by mock OCR. OpenAPI is available at `http://localhost:8000/docs` for direct API use.

## API outline

- `GET/PATCH /api/profile/me` — edit profile details and preferences.
- `POST /api/documents` — upload PDF/JPG/PNG; returns a processing document ID.
- `GET /api/documents` and `GET /api/documents/{id}` — list/details, scoped to current owner.
- `PATCH /api/documents/{id}` — edit display name, type/date, or the complete validated extraction payload.
- `DELETE /api/documents/{id}/extraction-overrides` — restore the latest machine-extraction baseline.
- `GET /api/documents/{id}/content` — authenticated streaming of the private original.
- `POST /api/documents/{id}/reprocess`, `DELETE /api/documents/{id}`.
- `PATCH /api/documents/{id}/summary/{summary_id}` — edit summary text/language; required disclaimer is retained.
- `POST /api/documents/{id}/summaries` — generate a new summary from the current, possibly corrected extraction.
- `GET /api/timeline`, `PATCH/DELETE /api/timeline/{event_id}`.
- `GET /api/profile/me/fhir` — prototype FHIR Bundle export.
- `GET /health/live`, `GET /health/ready`.

All user endpoints use bearer authentication. Entra mode validates the access token signature, issuer, audience, expiration, subject, and required scope/role. Set `ENTRA_JWKS_URI` when the External ID tenant exposes signing keys at a custom URL; otherwise it is derived from the configured issuer. Data is always queried with the authenticated profile ID. Requests for another owner's document return 404.

The API retains an extraction baseline and top-level manual overrides. Reprocessing applies those overrides over the new machine result. A user can reset to the latest baseline explicitly. Timeline events corrected by a user are retained when AI events are rebuilt.

## Azure providers

Copy `.env.example` values into local secrets or configure Container Apps secrets/managed identity. Set:

- `AUTH_MODE=entra` and Entra tenant, issuer, audience, and required scope.
- `STORAGE_PROVIDER=azure` and storage account URL; grant the container app managed identity Blob Data Contributor access.
- `QUEUE_PROVIDER=azure` and `AZURE_STORAGE_QUEUE_ACCOUNT_URL`; provision the configured queue before starting the API. The API identity needs Storage Queue Data Message Sender, and the worker identity needs Storage Queue Data Message Processor plus Blob Data Reader. Run a separate worker process with `python -m app.worker` using the same image and settings. Queue messages contain only document IDs; unacknowledged messages become available again after the visibility timeout if a worker exits unexpectedly.
- `OCR_PROVIDER=azure` and Document Intelligence endpoint; use a key only for local development or managed identity in Azure.
- `LLM_PROVIDER=azure` with the Azure OpenAI endpoint and deployment name. `AZURE_OPENAI_DEPLOYMENT` is the shared fallback. Set `AZURE_OPENAI_EXTRACTION_DEPLOYMENT` and/or `AZURE_OPENAI_SUMMARY_DEPLOYMENT` to route those tasks to separate deployments; this lets you tune capacity and cost without changing code. `AZURE_OPENAI_EXTRACTION_MAX_TOKENS` and `AZURE_OPENAI_SUMMARY_MAX_TOKENS` bound generated output. Prefer managed identity; API-key configuration exists for development only.
- `DATABASE_URL` to Azure Database for PostgreSQL using TLS.

The queue worker claims jobs with a conditional database update and a processing lease, so duplicate queue deliveries do not process the same document concurrently. Keep `PROCESSING_LEASE_SECONDS` lower than `QUEUE_MESSAGE_VISIBILITY_SECONDS`; the defaults leave room for recovery after a worker crash while avoiding duplicate work during the bounded OCR/AI calls.

Azure OCR submits at most `MAX_DOCUMENT_PAGES` pages and reports total versus processed PDF pages. The default is two pages for the Azure F0 demo case. Update it only after verifying the resource tier and quota.

## Schema and deployment notes

Local development can create the schema at startup. For deployed environments set `AUTO_CREATE_SCHEMA=false` and run migrations with `alembic upgrade head` from `backend/` as a deployment step. Do not use local mock auth outside a local/dev/test environment. The API has no raw-content logging; avoid adding OCR, summaries, prompts, filenames, tokens, or extracted values to telemetry.

For Azure student infrastructure provisioning, managed-identity permissions, migration steps, and cleanup, see [`docs/azure-student-deployment.md`](../docs/azure-student-deployment.md) and [`infra/main.bicep`](../infra/main.bicep).

This prototype is for educational development and demonstration. Use synthetic or de-identified documents, not real patient records.

Supported profile and summary language codes are `en`, `hi`, `ta`, `te`, and `ml`. The profile preference controls upload-time summaries and is used as the default when generating a summary from current fields. Unexpected legacy values safely fall back to English.
