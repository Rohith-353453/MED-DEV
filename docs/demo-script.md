# Hackathon demo script

Use only [`samples/synthetic-lab-report.pdf`](../samples/synthetic-lab-report.pdf). Its name and contents identify it as a fictional training fixture; do not upload real patient information.

## Prepare

1. Start PostgreSQL and the FastAPI service with `docker compose up --build`, or start the backend with the commands in [`backend/README.md`](../backend/README.md).
2. In a second terminal, copy `frontend/.env.example` to `frontend/.env` if needed, then run `npm install` and `npm run dev` from `frontend/`.
3. Open the Vite URL and confirm the profile says **Local demo**. With local mock providers, no Entra or Azure keys are needed.

## Show the product

1. Point out the empty account state and explain that the demo starts without fabricated patient records.
2. Upload `samples/synthetic-lab-report.pdf`.
3. Open the new record and show its queued/processing status, fictional extracted lab fields, confidence and source page.
4. Show the summary. Point out that the `H` flag is copied from the sample report and is not a medical interpretation; read the full disclaimer.
5. Open the timeline and show the document event and lab result events.
6. Edit a display name, a structured extraction field, a summary, and a timeline event. Refresh the page to show the saved changes.
7. Upload a different synthetic PDF/image while mock providers are active. Explain that it is marked for review because the local mock does not pretend to perform OCR on arbitrary files.
8. Optionally show the FHIR bundle at `GET /api/profile/me/fhir` in the API docs. It is a prototype export and does not connect to ABDM or another health exchange.

## After the demo

Delete local demo records if they are no longer needed. For Azure, follow [`azure-student-deployment.md`](azure-student-deployment.md), monitor Cost Management, and remove the demo resource group when finished.
