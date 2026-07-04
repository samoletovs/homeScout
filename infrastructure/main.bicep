targetScope = 'resourceGroup'

@description('Project name (lowerCamelCase, flatcase for resource names)')
param projectName string = 'homescout'

@description('Azure region')
param location string = 'northeurope'

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
//   * Storage account (required by the Function App).
//   * Function App (Python 3.11, Consumption/Flex) — timer-triggered pipeline.
//       - App settings from Function App settings, NOT committed secrets.
//   * Cosmos DB (free tier: 1000 RU/s + 25 GB) — listings, price-history, dedup state.
//   * (Later) Static Web App (Free) for the read-only dashboard.
// Deploy: az deployment group create -g <rg> --template-file infrastructure/main.bicep

output appInsightsConnectionString string = monitoring.outputs.connectionString
