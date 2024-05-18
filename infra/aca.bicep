param name string
param location string = resourceGroup().location
param tags object = {}

param identityName string
param containerAppsEnvironmentName string
param containerRegistryName string
param serviceName string = 'aca'
param exists bool
param openAiDeploymentName string
param openAiEndpoint string
param openAiApiVersion string
param openAiComAPIKeySecretName string
param azureKeyVaultName string

param clientId string

param tenantIdForAuth string
param loginEndpoint string

@secure()
param clientSecret string

// the issuer is different depending if we are in a workforce or external tenant
var openIdIssuer = empty(loginEndpoint) ? '${environment().authentication.loginEndpoint}${tenantIdForAuth}/v2.0' : 'https://${loginEndpoint}/${tenantIdForAuth}/v2.0'

var secrets = {
  'microsoft-provider-authentication-secret': clientSecret
}

resource acaIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: identityName
  location: location
}


module app 'core/host/container-app-upsert.bicep' = {
  name: '${serviceName}-container-app-module'
  params: {
    name: name
    location: location
    tags: union(tags, { 'azd-service-name': serviceName })
    identityName: acaIdentity.name
    exists: exists
    containerAppsEnvironmentName: containerAppsEnvironmentName
    containerRegistryName: containerRegistryName
    env: [
      {
        name: 'AZURE_OPENAI_CHATGPT_DEPLOYMENT'
        value: openAiDeploymentName
      }
      {
        name: 'AZURE_OPENAI_ENDPOINT'
        value: openAiEndpoint
      }
      {
        name: 'AZURE_OPENAI_API_VERSION'
        value: openAiApiVersion
      }
      {
        name: 'RUNNING_IN_PRODUCTION'
        value: 'true'
      }
      // Must be named AZURE_CLIENT_ID for DefaultAzureCredential to find it automatically
      {
        name: 'AZURE_CLIENT_ID'
        value: acaIdentity.properties.clientId
      }
      {
        name: 'OPENAICOM_API_KEY_SECRET_NAME'
        value: openAiComAPIKeySecretName
      }
      {
        name: 'AZURE_KEY_VAULT_NAME'
        value: azureKeyVaultName
      }
    ]
    targetPort: 50505
    secrets: secrets
  }
}


module auth 'core/host/container-apps-auth.bicep' = {
  name: '${serviceName}-container-apps-auth-module'
  params: {
    name: app.outputs.name
    clientId: clientId
    clientSecretName: 'microsoft-provider-authentication-secret'
    openIdIssuer: openIdIssuer
  }
}

output SERVICE_ACA_IDENTITY_PRINCIPAL_ID string = acaIdentity.properties.principalId
output SERVICE_ACA_NAME string = app.outputs.name
output SERVICE_ACA_URI string = app.outputs.uri
output SERVICE_ACA_IMAGE_NAME string = app.outputs.imageName
