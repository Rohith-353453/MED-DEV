# AI Health Copilot

Azure student deployment instructions: [docs/azure-student-deployment.md](docs/azure-student-deployment.md)

Architecture: [docs/architecture.md](docs/architecture.md) · Demo script: [docs/demo-script.md](docs/demo-script.md)

Build specification: [AI-Health-Copilot-AZURE-SPEC.md](AI-Health-Copilot-AZURE-SPEC.md)

## Backend

The current implementation focus is the FastAPI backend. See [backend/README.md](backend/README.md) for local setup and API details. The local default runs with mock OCR/AI providers and deliberately produces no invented medical facts. The backend supports editable profile/document/extraction/summary/timeline data and keeps user corrections separate from machine-extracted baselines.

## Frontend

The React interface in [frontend/](frontend/) now uses the FastAPI endpoints for documents, summaries, profile, and timeline. See [frontend/README.md](frontend/README.md) for local setup and Entra SPA configuration.

## Synthetic demo

Use [samples/synthetic-lab-report.pdf](samples/synthetic-lab-report.pdf) for a local end-to-end demonstration. It contains fictional values and is processed only by the explicit local mock fixture path.

## Languages

Carefolio supports English (`en`), Hindi (`hi`), Tamil (`ta`), Telugu (`te`), and Malayalam (`ml`) in the interface and generated summaries. Choose a language in the top-bar switcher or the profile preference selector. The saved preference controls upload-time summaries; use **Generate from current fields** to create an existing document's summary in the selected language. Recorded test names and medical values remain as they appear in the source.

## Frozen hackathon finish scope

Until the Azure deployment passes an end-to-end smoke test, feature work is limited to:

- A reliable sign-in and document workflow: upload, extraction, summary, edits, refresh/persistence, and timeline.
- Essential navigation, responsive layout, accessible controls, and clear loading/error states.
- The five supported interface and summary languages listed above.
- FHIR R4 export for recorded data, with mock identifiers clearly labeled. The local ABHA demo control is not a real ABHA or ABDM integration.
- Deployment and demo instructions that match the current Azure architecture.

Defer new integrations, additional languages, and optional UI effects until the deployment is verified.
