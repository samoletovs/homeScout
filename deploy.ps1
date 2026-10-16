# homeScout deploy — provisions infra (Cosmos serverless + Function App + monitoring) and
# publishes the function code. Run from the repo root: pwsh ./deploy.ps1
#
# State + learned family feedback live in Cosmos DB (durable), so the Function App runs on
# the Flex Consumption plan (FC1). Secret app settings are set once, after the first deploy.
param(
    [string]$ResourceGroup = "homescout-rg",
    [string]$Location = "northeurope"
)
$ErrorActionPreference = "Stop"

Write-Host "== Tests ==" -ForegroundColor Cyan
Push-Location $PSScriptRoot
python -m unittest discover tests
if ($LASTEXITCODE -ne 0) { Write-Error "tests failed — aborting"; exit 1 }
Pop-Location

Write-Host "== Infrastructure (Bicep) ==" -ForegroundColor Cyan
az group create -n $ResourceGroup -l $Location -o none
# Bicep merges live app settings into its own, so secrets set out of band survive a
# redeploy. Reading them needs the app to exist; tell the template whether it does.
# A failed lookup must stop the deploy: treating it as "no app" would wipe the settings.
$sitesJson = az resource list -g $ResourceGroup --resource-type Microsoft.Web/sites -o json
if ($LASTEXITCODE -ne 0) { Write-Error "could not list Function Apps in $ResourceGroup - aborting"; exit 1 }
$appExists = [bool]($sitesJson | ConvertFrom-Json | Where-Object { $_.name -match '^homescout-func-[a-z0-9]{13}$' })
$outputs = az deployment group create -g $ResourceGroup -n homescout-deploy `
    --template-file "$PSScriptRoot/infrastructure/main.bicep" `
    --parameters appExists=$($appExists.ToString().ToLower()) `
    --query "properties.outputs" -o json | ConvertFrom-Json
$funcApp = $outputs.functionAppName.value
Write-Host "Function App: $funcApp  |  Cosmos: $($outputs.cosmosEndpoint.value)" -ForegroundColor Green

Write-Host "== Publish function code (remote build) ==" -ForegroundColor Cyan
Push-Location "$PSScriptRoot/functions"
func azure functionapp publish $funcApp --build remote --python
Pop-Location

Write-Host ""
Write-Host "== One-time secret app settings (not in Bicep) ==" -ForegroundColor Yellow
Write-Host "az functionapp config appsettings set -g $ResourceGroup -n $funcApp --settings ``"
Write-Host '  TELEGRAM_BOT_TOKEN=<token> TELEGRAM_CHAT_ID=<chat id[,chat id,...] - one per family member> `'
Write-Host '  AZURE_OPENAI_ENDPOINT=<endpoint> AZURE_OPENAI_API_KEY=<key> AZURE_OPENAI_DEPLOYMENT=gpt-4.1-nano'
Write-Host ""
Write-Host "Then wire the agentMode gate to the feedback endpoint:" -ForegroundColor Yellow
Write-Host "  <function key> = az functionapp keys list -g $ResourceGroup -n $funcApp --query functionKeys.default -o tsv"
Write-Host "  set agentMode HOMESCOUT_FEEDBACK_URL = https://$funcApp.azurewebsites.net/api/feedback?code=<function key>"
Write-Host ""
Write-Host "Seed once (first run seeds silently; the daily 12:00 UTC timer then sends briefs):" -ForegroundColor Yellow
Write-Host "  \$mk = az functionapp keys list -g $ResourceGroup -n $funcApp --query masterKey -o tsv"
Write-Host "  Invoke-RestMethod -Method Post -Uri https://$funcApp.azurewebsites.net/admin/functions/poll_listings -Headers @{'x-functions-key'=\$mk} -Body '{}' -ContentType application/json"
