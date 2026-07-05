targetScope = 'resourceGroup'

@description('Project name (lowerCamelCase, flatcase for resource names)')
param projectName string = 'homescout'

@description('Azure region')
param location string = 'northeurope'

@description('Family communication language (data stays English)')
param commLanguage string = 'ru'

var suffix = uniqueString(resourceGroup().id)
var tags = {
  project: projectName
  managedBy: 'bicep'
  costCenter: 'naurolabs-research'
}

// Shared monitoring module (App Insights + Log Analytics) — golden path.
module monitoring '../../.github/infrastructure/modules/monitoring.bicep' = {
  name: 'monitoring-${projectName}'
  params: {
    projectName: projectName
    location: location
    tags: tags
  }
}

// TODO (Phase 0 infra build — keep on the golden path where possible):
//   * (Later) Static Web App (Free) for the read-only dashboard.

// ── Cosmos DB (serverless — pay-per-use, scales to zero; durable state + knowledge) ──
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: '${projectName}-cosmos-${suffix}'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [ { name: 'EnableServerless' } ]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    disableLocalAuth: true // enforce Entra ID (managed identity) data-plane auth — no keys
    locations: [ { locationName: location, failoverPriority: 0 } ]
  }
}

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: cosmos
  name: 'homescout'
  properties: { resource: { id: 'homescout' } }
}

var containers = [
  { name: 'listings', pk: '/key' }
  { name: 'feedback', pk: '/listing_key' }
  { name: 'geocache', pk: '/id' }
]
resource cosmosContainers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = [for c in containers: {
  parent: cosmosDb
  name: c.name
  properties: {
    resource: {
      id: c.name
      partitionKey: { paths: [ c.pk ], kind: 'Hash' }
    }
  }
}]

// ── Storage (required by the Function App runtime) ──
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: 'st${projectName}${suffix}'
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
  }
}

// ── Function App (Linux Consumption, Python 3.11). State lives in Cosmos, so the
//    plan's ephemeral disk is fine — no persistence needed on the host. ──
resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: '${projectName}-plan-${suffix}'
  location: location
  tags: tags
  sku: { name: 'Y1', tier: 'Dynamic' }
  kind: 'functionapp'
  properties: { reserved: true }
}

resource func 'Microsoft.Web/sites@2023-12-01' = {
  name: '${projectName}-func-${suffix}'
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    reserved: true
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'Python|3.11'
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        { name: 'AzureWebJobsStorage', value: 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}' }
        { name: 'FUNCTIONS_EXTENSION_VERSION', value: '~4' }
        { name: 'FUNCTIONS_WORKER_RUNTIME', value: 'python' }
        { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: monitoring.outputs.connectionString }
        { name: 'COSMOS_ENDPOINT', value: cosmos.properties.documentEndpoint }
        { name: 'COSMOS_DATABASE', value: 'homescout' }
        { name: 'HOMESCOUT_LANG', value: commLanguage }
      ]
    }
  }
}

// ── Cosmos data-plane RBAC: Function App identity → Built-in Data Contributor ──
resource cosmosDataRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, func.id, '00000000-0000-0000-0000-000000000002')
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    principalId: func.identity.principalId
    scope: cosmos.id
  }
}

output functionAppName string = func.name
output cosmosEndpoint string = cosmos.properties.documentEndpoint
output storageAccountName string = storage.name
output appInsightsConnectionString string = monitoring.outputs.connectionString
