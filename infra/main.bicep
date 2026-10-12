targetScope = 'resourceGroup'

@description('Azure region for the deployment.')
param location string = resourceGroup().location
@description('Globally unique lowercase name for the Blob and Queue Storage account (3–24 chars).')
@minLength(3)
@maxLength(24)
param storageAccountName string
@description('Globally unique name for the Container Apps environment.')
param containerAppsEnvironmentName string
@description('Globally unique name for the PostgreSQL Flexible Server.')
param postgresServerName string
@description('Container image reference, including registry, repository, and immutable tag.')
param backendImage string
@description('Entra External ID tenant identifier.')
param entraTenantId string
@description('Exact issuer URL expected in Entra access tokens.')
param entraIssuer string
@description('Audience expected in Entra access tokens, usually api://<API app client ID>.')
param entraApiAudience string
@description('Allowed frontend origin used when createStaticWebApp is false, for example https://app.example.com.')
param frontendOrigin string = ''
@description('Azure OpenAI endpoint, for example https://<resource>.openai.azure.com.')
param azureOpenAiEndpoint string
@description('GPT-4o deployment name configured in the Azure OpenAI resource.')
param azureOpenAiDeployment string
@description('Name of the existing Azure OpenAI Cognitive Services account in this resource group.')
param azureOpenAiResourceName string
@description('Azure AI Document Intelligence endpoint.')
param documentIntelligenceEndpoint string
@description('Name of the existing Document Intelligence Cognitive Services account in this resource group.')
param documentIntelligenceResourceName string
@description('PostgreSQL administrator login (letters and digits only).')
param postgresAdminLogin string = 'carefolioadmin'
@secure()
@description('PostgreSQL password: use at least 12 characters with uppercase, lowercase, and digits; letters and digits only avoid URL escaping issues.')
param postgresAdminPassword string
@description('Azure Queue Storage queue name.')
param queueName string = 'document-processing'
@description('Whether to create a free-tier Azure Static Web App shell. Link a source repository and configure its build separately.')
param createStaticWebApp bool = true
@description('Allow Azure services through the PostgreSQL firewall. This demo setting is broad; disable and add private networking before any real patient data.')
param allowAzureServicesToPostgres bool = true

var postgresDatabaseName = 'carefolio'
var queueAccountUrl = 'https://${storageAccountName}.queue.core.windows.net'
var blobAccountUrl = 'https://${storageAccountName}.blob.core.windows.net'
var postgresHost = '${postgresServerName}.postgres.database.azure.com'
var databaseUrl = 'postgresql+asyncpg://${postgresAdminLogin}:${postgresAdminPassword}@${postgresHost}:5432/${postgresDatabaseName}?ssl=require'
var blobContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
var blobReaderRoleId = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
var queueSenderRoleId = 'c6a89b2d-59bc-44d0-9896-0f6e12d7b80a'
var queueProcessorRoleId = '8a0f0c08-91a1-4084-bc3d-661d67233fed'
var queueReaderRoleId = '19e7f393-937e-4f77-808e-94535e297925'
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}
resource blobContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'medical-documents'
  properties: { publicAccess: 'None' }
}
resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2023-05-01' = {
  parent: storage
  name: 'default'
}
resource documentQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2023-05-01' = {
  parent: queueService
  name: queueName
}

resource azureOpenAi 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: azureOpenAiResourceName
}
resource documentIntelligence 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: documentIntelligenceResourceName
}

resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresServerName
  location: location
  sku: { name: 'Standard_B1ms', tier: 'Burstable' }
  properties: {
    administratorLogin: postgresAdminLogin
    administratorLoginPassword: postgresAdminPassword
    version: '16'
    storage: { storageSizeGB: 32 }
    backup: { backupRetentionDays: 7, geoRedundantBackup: 'Disabled' }
    highAvailability: { mode: 'Disabled' }
    publicNetworkAccess: 'Enabled'
  }
}
resource postgresDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: postgresDatabaseName
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}
resource postgresAzureServicesFirewall 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = if (allowAzureServicesToPostgres) {
  parent: postgres
  name: 'allow-azure-services-demo-only'
  properties: { startIpAddress: '0.0.0.0', endIpAddress: '0.0.0.0' }
}

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${containerAppsEnvironmentName}-logs'
  location: location
  properties: { sku: { name: 'PerGB2018' }, retentionInDays: 30 }
}
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${containerAppsEnvironmentName}-insights'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
  }
}
resource containerAppsEnvironment 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: containerAppsEnvironmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

resource api 'Microsoft.App/containerApps@2025-01-01' = {
  name: '${containerAppsEnvironmentName}-api'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'appinsights-connection', value: appInsights.properties.ConnectionString }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: backendImage
          resources: { cpu: 0.5, memory: '1Gi' }
          env: [
            { name: 'APP_ENV', value: 'production' }
            { name: 'API_PREFIX', value: '/api' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'AUTO_CREATE_SCHEMA', value: 'false' }
            { name: 'AUTH_MODE', value: 'entra' }
            { name: 'ENTRA_TENANT_ID', value: entraTenantId }
            { name: 'ENTRA_ISSUER', value: entraIssuer }
            { name: 'ENTRA_API_AUDIENCE', value: entraApiAudience }
            { name: 'STORAGE_PROVIDER', value: 'azure' }
            { name: 'AZURE_STORAGE_ACCOUNT_URL', value: blobAccountUrl }
            { name: 'AZURE_STORAGE_CONTAINER', value: 'medical-documents' }
            { name: 'QUEUE_PROVIDER', value: 'azure' }
            { name: 'AZURE_STORAGE_QUEUE_ACCOUNT_URL', value: queueAccountUrl }
            { name: 'AZURE_STORAGE_QUEUE_NAME', value: queueName }
            { name: 'QUEUE_MESSAGE_VISIBILITY_SECONDS', value: '3600' }
            { name: 'PROCESSING_LEASE_SECONDS', value: '3300' }
            { name: 'OCR_PROVIDER', value: 'azure' }
            { name: 'AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT', value: documentIntelligenceEndpoint }
            { name: 'LLM_PROVIDER', value: 'azure' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: azureOpenAiDeployment }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection' }
            { name: 'FRONTEND_ORIGINS', value: createStaticWebApp ? 'https://${staticWebApp.properties.defaultHostname}' : frontendOrigin }
            { name: 'MAX_DOCUMENT_PAGES', value: '2' }
            { name: 'AZURE_DOCUMENT_INTELLIGENCE_MAX_MB', value: '4' }
          ]
          probes: [
            { type: 'Liveness', httpGet: { path: '/health/live', port: 8000 }, initialDelaySeconds: 10, periodSeconds: 30 }
            { type: 'Readiness', httpGet: { path: '/health/ready', port: 8000 }, initialDelaySeconds: 10, periodSeconds: 30 }
          ]
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 2 }
    }
  }
}

resource worker 'Microsoft.App/containerApps@2025-01-01' = {
  name: '${containerAppsEnvironmentName}-worker'
  location: location
  identity: { type: 'SystemAssigned' }
  properties: {
    managedEnvironmentId: containerAppsEnvironment.id
    configuration: {
      activeRevisionsMode: 'Single'
      secrets: [
        { name: 'database-url', value: databaseUrl }
        { name: 'appinsights-connection', value: appInsights.properties.ConnectionString }
      ]
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: backendImage
          command: ['python', '-m', 'app.worker']
          resources: { cpu: 0.5, memory: '1Gi' }
          env: [
            { name: 'APP_ENV', value: 'production' }
            { name: 'DATABASE_URL', secretRef: 'database-url' }
            { name: 'AUTO_CREATE_SCHEMA', value: 'false' }
            { name: 'AUTH_MODE', value: 'entra' }
            { name: 'ENTRA_TENANT_ID', value: entraTenantId }
            { name: 'ENTRA_ISSUER', value: entraIssuer }
            { name: 'ENTRA_API_AUDIENCE', value: entraApiAudience }
            { name: 'STORAGE_PROVIDER', value: 'azure' }
            { name: 'AZURE_STORAGE_ACCOUNT_URL', value: blobAccountUrl }
            { name: 'AZURE_STORAGE_CONTAINER', value: 'medical-documents' }
            { name: 'QUEUE_PROVIDER', value: 'azure' }
            { name: 'AZURE_STORAGE_QUEUE_ACCOUNT_URL', value: queueAccountUrl }
            { name: 'AZURE_STORAGE_QUEUE_NAME', value: queueName }
            { name: 'QUEUE_MESSAGE_VISIBILITY_SECONDS', value: '3600' }
            { name: 'PROCESSING_LEASE_SECONDS', value: '3300' }
            { name: 'OCR_PROVIDER', value: 'azure' }
            { name: 'AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT', value: documentIntelligenceEndpoint }
            { name: 'LLM_PROVIDER', value: 'azure' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: azureOpenAiEndpoint }
            { name: 'AZURE_OPENAI_DEPLOYMENT', value: azureOpenAiDeployment }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', secretRef: 'appinsights-connection' }
            { name: 'MAX_DOCUMENT_PAGES', value: '2' }
            { name: 'AZURE_DOCUMENT_INTELLIGENCE_MAX_MB', value: '4' }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 2
        rules: [
          {
            name: 'document-queue'
            custom: {
              type: 'azure-queue'
              metadata: {
                queueName: queueName
                queueLength: '1'
                accountName: storageAccountName
              }
              identity: 'system'
            }
          }
        ]
      }
    }
  }
}

resource apiBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(blobContainer.id, api.id, blobContributorRoleId)
  scope: blobContainer
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobContributorRoleId), principalId: api.identity.principalId, principalType: 'ServicePrincipal' }
}
resource apiQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(documentQueue.id, api.id, queueSenderRoleId)
  scope: documentQueue
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', queueSenderRoleId), principalId: api.identity.principalId, principalType: 'ServicePrincipal' }
}
resource workerBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(blobContainer.id, worker.id, blobReaderRoleId)
  scope: blobContainer
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', blobReaderRoleId), principalId: worker.identity.principalId, principalType: 'ServicePrincipal' }
}
resource workerQueueRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(documentQueue.id, worker.id, queueProcessorRoleId)
  scope: documentQueue
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', queueProcessorRoleId), principalId: worker.identity.principalId, principalType: 'ServicePrincipal' }
}
resource workerQueueScalerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(documentQueue.id, worker.id, queueReaderRoleId)
  scope: documentQueue
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', queueReaderRoleId), principalId: worker.identity.principalId, principalType: 'ServicePrincipal' }
}
resource apiOpenAiRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(azureOpenAi.id, api.id, openAiUserRoleId)
  scope: azureOpenAi
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId), principalId: api.identity.principalId, principalType: 'ServicePrincipal' }
}
resource workerOpenAiRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(azureOpenAi.id, worker.id, openAiUserRoleId)
  scope: azureOpenAi
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId), principalId: worker.identity.principalId, principalType: 'ServicePrincipal' }
}
resource workerDocumentIntelligenceRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(documentIntelligence.id, worker.id, cognitiveServicesUserRoleId)
  scope: documentIntelligence
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId), principalId: worker.identity.principalId, principalType: 'ServicePrincipal' }
}

resource staticWebApp 'Microsoft.Web/staticSites@2023-12-01' = if (createStaticWebApp) {
  name: '${containerAppsEnvironmentName}-web'
  location: 'eastus2'
  sku: { name: 'Free', tier: 'Free' }
  properties: { buildProperties: { appLocation: 'frontend', outputLocation: 'dist' } }
}

output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output storageAccountUrl string = blobAccountUrl
output queueAccountUrl string = queueAccountUrl
output queueName string = queueName
output postgresHost string = postgresHost
output postgresDatabase string = postgresDatabaseName
output staticWebAppName string = createStaticWebApp ? staticWebApp.name : ''
output staticWebAppHostname string = createStaticWebApp ? staticWebApp.properties.defaultHostname : ''
