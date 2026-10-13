# Carefolio architecture

## Cloud deployment

```mermaid
flowchart LR
  Browser[React + TypeScript SPA]
  Identity[Firebase Authentication\nFirebase ID token]
  Static[Azure Static Web Apps]
  API[Azure Container Apps\nFastAPI API]
  Queue[(Azure Storage Queue)]
  Worker[Azure Container Apps Express\nqueue polling worker]
  Blob[(Private Azure Blob Storage)]
  DB[(Azure Database for PostgreSQL)]
  OCR[Azure AI Document Intelligence]
  LLM[Azure OpenAI\nconfigured deployment]
  Monitor[Application Insights\nPHI-safe telemetry]

  Browser --> Identity
  Browser --> Static
  Static -->|Bearer access token| API
  API -->|enqueue document ID| Queue
  API -->|save original| Blob
  API --> DB
  Worker -->|poll for queued document IDs| Queue
  Worker --> DB
  Worker -->|read private original| Blob
  Worker --> OCR
  Worker --> LLM
  API -. traces and metrics .-> Monitor
  Worker -. traces and metrics .-> Monitor
```

The API and worker use separate user-assigned managed identities, and a third user-assigned identity grants image-pull access to the existing Azure Container Registry. The API sends queue messages and accesses the configured blob container. The worker polls the queue continuously because the Express environment does not support the custom queue scaler used by standard Container Apps environments. Stop or scale down the worker when the demo is idle to limit charges. Queue messages contain document IDs, not document text or health values. The database remains the authority for job status and owner-scoped records.

The FHIR R4 download is a prototype export containing only recorded data. Demo patient identifiers are explicitly marked as mock identifiers. The local ABHA linking control is a visual demo state only; the app does not connect to ABDM or government systems.

## Local development

```mermaid
flowchart LR
  Browser[React + Vite\nlocal mock account]
  API[FastAPI\nAUTH_MODE=mock]
  DB[(SQLite or Compose PostgreSQL)]
  Files[(Private local uploads)]
  Fixture[Marked synthetic PDF]
  Mock[Deterministic fixture OCR/AI\nno extraction for other uploads]

  Browser --> API
  API --> DB
  API --> Files
  Files --> Fixture
  API --> Mock
```

The local mock processes only the exact included synthetic PDF fixture. Other user uploads are not given fabricated OCR text or medical information and finish in `needs_review`. The prototype is for synthetic or properly de-identified documents only and is not for clinical decision-making.
