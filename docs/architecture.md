# Carefolio architecture

## Cloud deployment

```mermaid
flowchart LR
  Browser[React + TypeScript SPA]
  Identity[Microsoft Entra External ID\nAuthorization Code + PKCE]
  Static[Azure Static Web Apps]
  API[Azure Container Apps\nFastAPI API]
  Queue[(Azure Storage Queue)]
  Worker[Azure Container Apps\nprocessing worker]
  Blob[(Private Azure Blob Storage)]
  DB[(Azure Database for PostgreSQL)]
  OCR[Azure AI Document Intelligence]
  LLM[Azure OpenAI\nGPT-4o deployment]
  Monitor[Application Insights\nPHI-safe telemetry]

  Browser --> Identity
  Browser --> Static
  Static -->|Bearer access token| API
  API -->|enqueue document ID| Queue
  API -->|save original| Blob
  API --> DB
  Queue -->|scale worker from queue depth| Worker
  Worker --> DB
  Worker -->|read private original| Blob
  Worker --> OCR
  Worker --> LLM
  API -. traces and metrics .-> Monitor
  Worker -. traces and metrics .-> Monitor
```

The API and worker use separate system-assigned managed identities. The API sends queue messages and accesses the configured blob container. The worker processes queue messages, reads blobs, and calls the configured AI resources. Queue messages contain document IDs, not document text or health values. The database remains the authority for job status and owner-scoped records.

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
