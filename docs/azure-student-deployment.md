# Azure student deployment

This deployment is a **hackathon and synthetic-data environment**, not a production health-data environment. It creates Azure Container Apps, PostgreSQL Flexible Server, Storage, Log Analytics, and Application Insights. Those services can spend student credit even when the app is idle. Check Cost Management and the subscription's service availability before deployment; set a budget alert, then delete the resource group when finished. A budget alert does not stop charges.

## Before deploying

1. Sign in with Azure CLI and select the Azure for Students subscription:

   ```powershell
   az login
   az account set --subscription <subscription-id>
   az account show --query '{name:name,id:id}'
   ```

2. Create a resource group in a region where the subscription has quota for PostgreSQL Flexible Server, Container Apps, and the AI resources. Deploy the existing Azure OpenAI and Document Intelligence accounts in the same resource group as the template; their **account names**, endpoints, selected model deployment name, and access quota must be known first. Azure OpenAI deployments and Student offer availability vary by account and region.

### Confirm AI access before creating resources

Check model availability and quota in [Microsoft Foundry](https://ai.azure.com/) before creating the app infrastructure:

1. Select the Azure for Students subscription and the region you plan to use.
2. Open **Manage → Quota** and check whether your chosen chat model can be deployed in the project region. Quota and capacity depend on the subscription, model, region, and deployment type. If GPT-4o is unavailable, choose another supported model and deployment type that has quota; verify that the app's configured Azure OpenAI API version supports it.
3. In the model catalog, deploy the available chat model using a standard, pay-per-use deployment type where possible. Record the **deployment name** exactly; the app sends that name as `AZURE_OPENAI_DEPLOYMENT`. Avoid provisioned throughput for this demo.
4. Create a Document Intelligence resource in the same region where possible. F0 is available for trying the service, with a 4 MB document limit and two analyzed pages. The project defaults (`AZURE_DOCUMENT_INTELLIGENCE_MAX_MB=4`, `MAX_DOCUMENT_PAGES=2`) match those limits. Check the current tier limits and costs before creating S0 resources.

After creating the AI resources, record their resource names and endpoints. The Azure deployment uses managed identities and role assignments, so it needs the account names/endpoints and GPT-4o deployment name, not account keys. For local API development, keys can be placed in the ignored `backend/.env` file; never put them in frontend `VITE_*` variables or commit them.

Microsoft's guides: [manage Azure OpenAI quota](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/quota), [Document Intelligence resource setup](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/create-document-intelligence-resource?view=doc-intel-4.0.0), and [Document Intelligence service limits](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/service-limits?tabs=v30&view=doc-intel-3.0.0).

3. Build and push the backend image to a registry the Container Apps environment can pull from. Use a versioned tag, not `latest`. The repository has a backend Dockerfile but does not provision a container registry or build/push pipeline.

4. Register/configure Entra External ID applications. Configure an SPA app registration with Authorization Code + PKCE, the deployed Static Web App origin, and the API delegated scope `access_as_user`. The API audience and issuer must exactly match the access token it receives. Add the same client ID, authority, and scope to `frontend/.env` before building the frontend.

5. Copy `infra/parameters.example.json` to a local parameters file, edit every `<placeholder>`, and choose unique lowercase resource names. Keep the edited file and password out of Git. The template creates a Static Web App shell and uses its generated hostname for API CORS. It remains empty until it is linked to a source repository or deployed through the Static Web Apps CLI.

## Deploy infrastructure

Create the group and deploy. Enter a PostgreSQL password at the PowerShell prompt without saving it in the parameter file. Use at least 12 characters with uppercase, lowercase, and digits; letters/digits only are easiest because the template builds a PostgreSQL connection URL.

```powershell
$resourceGroup = 'carefolio-demo-rg'
$location = 'centralindia'
az group create --name $resourceGroup --location $location
$dbPassword = Read-Host 'PostgreSQL password (letters and digits only)' -AsSecureString
$dbPasswordPlain = [System.Net.NetworkCredential]::new('', $dbPassword).Password
az deployment group create `
  --resource-group $resourceGroup `
  --template-file infra/main.bicep `
  --parameters @infra/parameters.example.json `
  --parameters postgresAdminPassword=$dbPasswordPlain
Remove-Variable dbPassword, dbPasswordPlain
```

The template grants separate managed identities access to storage and AI: the API sends queue messages and accesses blobs; the worker reads queue messages, reads blobs, and calls the AI services. The worker scales to zero when the queue is empty. Storage has no public blob access and shared-key access is disabled. The template configures a two-page OCR limit for the low-cost demo scenario.

`allowAzureServicesToPostgres` defaults to `true` so Container Apps can connect in this simple demo network. This PostgreSQL firewall exception is broad. Do not store real patient information in this deployment. A production design must use private networking/private endpoints, tighter ingress, managed database identity or a dedicated least-privilege database user, secret rotation, retention/deletion policy, and a privacy/security review.

## First release and migrations

The Bicep deployment sets `AUTO_CREATE_SCHEMA=false`, correctly avoiding automatic schema creation by the web service. Before sending traffic, install the backend and run Alembic against the new database from a trusted deployment environment:

```powershell
Set-Location backend
python -m pip install -e .
$env:DATABASE_URL = 'postgresql+asyncpg://carefolioadmin:<password>@<postgres-host>:5432/carefolio?ssl=require'
python -m alembic upgrade head
Remove-Item Env:DATABASE_URL
Set-Location ..
```

Use the same database password entered during deployment. Avoid placing it in shell history in shared environments. The template creates a free-tier Static Web App shell but does not configure GitHub authorization or frontend builds. Link the repository in Azure and set the app build output to `frontend/dist`. Set `VITE_API_BASE_URL` to the API URL output by the deployment and set the Entra SPA variables in the frontend build environment. Register the Static Web App URL as an allowed redirect URI in Entra and allow the SPA to request the API delegated scope.

The Bicep outputs include the API URL, PostgreSQL hostname, storage URL, queue name, and Static Web App hostname. Wait for RBAC role assignments to propagate before the API/worker can access storage and AI resources. A failed initial worker start can be restarted after propagation from the Container Apps revision view.

## Cost and cleanup

- Container Apps API and worker are configured with zero minimum replicas; requests/jobs can still incur consumption charges.
- PostgreSQL Flexible Server is the persistent cost risk. Check whether the selected student subscription supports a free allowance and whether the chosen SKU/region is eligible. Stop or delete it when idle; verify current billing behavior in the portal.
- Storage, Log Analytics ingestion/retention, Application Insights, AI calls, backups, networking, and registry storage can incur charges. Keep demo uploads synthetic and small; review usage after each session.
- The app's current AI page limit is two pages, matching the F0-style demo cap. Confirm the selected Document Intelligence tier and quotas before changing it.

To remove the demo and its resources:

```powershell
az group delete --name carefolio-demo-rg --yes --no-wait
```

If AI or the registry lives in another resource group, delete those resources separately when no longer needed. Review Cost Management after deletion; metering can take time to settle.

## Current implementation boundaries

- The backend API, queue worker, storage adapters, AI adapters, ownership-scoped routes, and migrations are in the repository.
- The frontend now supports Entra Authorization Code with PKCE and calls the backend APIs. The template does not configure GitHub authorization or an automated frontend build-and-deploy workflow.
- `infra/main.bicep` does not create Azure OpenAI or Document Intelligence accounts; those need to exist and have quota first.
- This is not certified for clinical use. Use only synthetic or properly de-identified sample documents.
