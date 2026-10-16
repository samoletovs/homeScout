targetScope = 'resourceGroup'

@description('Project name (lowerCamelCase, flatcase for resource names)')
param projectName string = 'homescout'

@description('Azure region')
param location string = 'northeurope'

@description('Family communication language (data stays English)')
param commLanguage string = 'ru'

// The Flex plan and package container were auto-named when the app moved off Linux
// Consumption (2026-10). A Flex app cannot change plans, so these must match the live names.
@description('Flex Consumption plan name')
param functionPlanName string = 'ASP-homescoutrg-384c'

@description('Blob container holding the Flex deployment package')
param deploymentContainerName string = 'app-package-homescoutfuncpk3dbg3673hg2-6732414'

@description('True when the Function App already exists. Its live app settings are then merged under the declared ones, so secrets set out of band survive a redeploy. Pass false only when creating the app.')
param appExists bool = true

var suffix = uniqueString(resourceGroup().id)
var functionAppName = '${projectName}-func-${suffix}'
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

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource deploymentContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: deploymentContainerName
  properties: { publicAccess: 'None' }
}

var storageConnection = 'DefaultEndpointsProtocol=https;AccountName=${storage.name};AccountKey=${storage.listKeys().keys[0].value};EndpointSuffix=${environment().suffixes.storage}'

// ── Function App (Flex Consumption, Python 3.11). State lives in Cosmos, so the
//    instance's ephemeral disk is fine — no persistence needed on the host. ──
resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: functionPlanName
  location: location
  tags: tags
  sku: { name: 'FC1', tier: 'FlexConsumption' }
  kind: 'functionapp'
  properties: { reserved: true }
}

resource func 'Microsoft.Web/sites@2024-04-01' = {
  name: functionAppName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: { type: 'SystemAssigned' }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}${deploymentContainerName}'
          authentication: {
            type: 'StorageAccountConnectionString'
            storageAccountConnectionStringName: 'DEPLOYMENT_STORAGE_CONNECTION_STRING'
          }
        }
      }
      scaleAndConcurrency: { maximumInstanceCount: 10, instanceMemoryMB: 2048 }
      runtime: { name: 'python', version: '3.11' }
    }
    siteConfig: {
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: appSettings
    }
  }
  dependsOn: [ deploymentContainer ]
}

// siteConfig.appSettings replaces the whole set, so the live settings are read first and the
// declared values win. Secrets (Telegram, Azure OpenAI, ...) are set out of band and survive.
var declaredAppSettings = {
  AzureWebJobsStorage: storageConnection
  DEPLOYMENT_STORAGE_CONNECTION_STRING: storageConnection
  APPLICATIONINSIGHTS_CONNECTION_STRING: monitoring.outputs.connectionString
  COSMOS_ENDPOINT: cosmos.properties.documentEndpoint
  COSMOS_DATABASE: 'homescout'
  HOMESCOUT_LANG: commLanguage
}
var appSettings = map(items(union(liveSettings.outputs.settings, declaredAppSettings)), s => { name: s.key, value: s.value })

module liveSettings 'modules/live-app-settings.bicep' = {
  name: 'live-app-settings-${projectName}'
  params: {
    functionAppName: functionAppName
    appExists: appExists
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
