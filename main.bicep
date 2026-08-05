// main.bicep — EnzymeTK on Azure Container Apps, using Azure Cache for Redis
// instead of a self-hosted redis container, and GHCR (already populated by
// ci.yml's `build` job) instead of a dedicated Azure Container Registry.
// Deploy with:
//
//   az deployment group create -g <resource-group> -f main.bicep \
//     --parameters imageTag=<git-sha-or-branch> ghcrPat=<pat-with-read:packages> \
//                  adminToken=<token> secretKey=<random-64-char-secret>
//
// API versions below are current as of writing — re-check with
// `az provider show -n Microsoft.App --query "resourceTypes[].apiVersions[0]"`
// before relying on this long-term.

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Base name used to derive resource names')
param appName string = 'enzyme-tk'

@description('GHCR image path as "<owner>/<repo>" — matches the github.repository value ci.yml publishes under')
param imageRepository string = 'ssec-jhu/enzyme-tk-app'

@description('Image tag to deploy — ci.yml publishes "main" on every push to main, and the release tag name on a GitHub release')
param imageTag string = 'main'

@description('GitHub user/org the pull PAT belongs to — defaults to the repository owner')
param ghcrUsername string = split(imageRepository, '/')[0]

@secure()
@description('GitHub PAT (classic, scope read:packages, or fine-grained "Packages: read") used by Container Apps to pull the private GHCR image')
param ghcrPat string

@secure()
@description('ETK_ADMIN_TOKEN — leave empty to keep the /admin dashboard disabled (fail-closed default)')
param adminToken string = ''

@secure()
@description('ETK_SECRET_KEY — Flask session-signing key; leave empty to disable /admin along with adminToken')
param secretKey string = ''

@allowed(['Basic', 'Standard', 'Premium'])
param redisSku string = 'Basic'

param redisFamily string = 'C'
param redisCapacity int = 1

var containerImage = 'ghcr.io/${imageRepository}:${imageTag}'
var storageAccountName = 'st${uniqueString(resourceGroup().id)}'

// ── Log Analytics — required by the Container Apps Environment ────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: '${appName}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ── Storage account + file shares (job-outputs, app-data) ─────────
// Azure Files gives ReadWriteMany semantics — required since job-outputs
// is written by worker and read by web, on different nodes.
//
// HDD provisioned v2 (kind: FileStorage, sku: StandardV2_LRS) — sized for a
// non-production/dev deployment: 32 GiB is the provisioned-v2 floor, and
// SKUFamily HDD is ~13x cheaper per GiB than SSD for workloads that don't
// need premium IOPS/throughput. job-outputs is transient (orphan-swept daily,
// see CELERY_SWEEP_INTERVAL_SECONDS) and app-data is read-only reference
// data, so grow the quota later if real dev data outgrows the floor —
// provisioned storage resizes online with no downtime.
// IOPS and throughput are left unset so Azure applies the recommended
// (free, storage-proportional) baseline instead of a manually provisioned
// — and separately billed — amount.
resource storage 'Microsoft.Storage/storageAccounts@2024-01-01' = {
  name: storageAccountName
  location: location
  sku: { name: 'StandardV2_LRS' }
  kind: 'FileStorage'
  properties: {
    minimumTlsVersion: 'TLS1_2'
  }
}

resource fileServices 'Microsoft.Storage/storageAccounts/fileServices@2024-01-01' = {
  parent: storage
  name: 'default'
}

resource jobOutputsShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2024-01-01' = {
  parent: fileServices
  name: 'job-outputs'
  properties: { shareQuota: 32 }
}

resource appDataShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2024-01-01' = {
  parent: fileServices
  name: 'app-data'
  properties: { shareQuota: 32 }
}

// ── Container Apps Environment ─────────────────────────────────────
resource containerEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${appName}-env'
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

resource jobOutputsStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: containerEnv
  name: 'job-outputs-storage'
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: jobOutputsShare.name
      accessMode: 'ReadWrite'
    }
  }
}

resource appDataStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: containerEnv
  name: 'app-data-storage'
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: appDataShare.name
      accessMode: 'ReadOnly'
    }
  }
}

// ── Azure Cache for Redis — replaces the `redis` compose service ──
// Broker + result backend for Celery, matching REDIS_URL's dual role
// in celery_app.py. TLS-only (port 6380); no code change needed since
// kombu/redis-py handle the `rediss://` scheme natively.
resource redisCache 'Microsoft.Cache/redis@2023-08-01' = {
  name: '${appName}-redis'
  location: location
  properties: {
    sku: {
      name: redisSku
      family: redisFamily
      capacity: redisCapacity
    }
    minimumTlsVersion: '1.2'
    // Public endpoint + TLS + access key auth — the default reachable
    // path when the Container Apps Environment is NOT VNet-integrated.
    // Switch to 'Disabled' + a private endpoint once the environment
    // is VNet-injected.
    publicNetworkAccess: 'Enabled'
  }
}

var redisUrl = 'rediss://:${redisCache.listKeys().primaryKey}@${redisCache.properties.hostName}:${redisCache.properties.sslPort}/0'

// ── shared building blocks for web + worker ────────────────────────
var sharedEnv = [
  { name: 'REDIS_URL', secretRef: 'redis-url' }
  { name: 'JOB_OUTPUTS_PATH', value: '/job-outputs' }
  { name: 'ETK_DATA_DIR', value: '/app-data' }
]

var sharedVolumes = [
  { name: 'job-outputs', storageType: 'AzureFile', storageName: jobOutputsStorage.name }
  { name: 'app-data', storageType: 'AzureFile', storageName: appDataStorage.name }
]

var sharedVolumeMounts = [
  { volumeName: 'job-outputs', mountPath: '/job-outputs' }
  { volumeName: 'app-data', mountPath: '/app-data' }
]

// GHCR has no managed-identity pull path (that's ACR-only) — every app
// authenticates with the same PAT, stored as its own `ghcr-pat` secret.
var registryConfig = [
  { server: 'ghcr.io', username: ghcrUsername, passwordSecretRef: 'ghcr-pat' }
]

// ── web ─────────────────────────────────────────────────────────
resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${appName}-web'
  location: location
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      registries: registryConfig
      secrets: [
        { name: 'ghcr-pat', value: ghcrPat }
        { name: 'redis-url', value: redisUrl }
        { name: 'admin-token', value: adminToken }
        { name: 'secret-key', value: secretKey }
      ]
      ingress: {
        external: true
        targetPort: 8050
        transport: 'auto'
      }
    }
    template: {
      containers: [
        {
          name: 'web'
          image: containerImage
          resources: { cpu: json('1.0'), memory: '2.0Gi' }
          env: concat(sharedEnv, [
            { name: 'ETK_ADMIN_TOKEN', secretRef: 'admin-token' }
            { name: 'ETK_SECRET_KEY', secretRef: 'secret-key' }
          ])
          volumeMounts: sharedVolumeMounts
        }
      ]
      volumes: sharedVolumes
      // Mirrors gunicorn's 2 workers x 4 threads = 8 concurrent
      // requests per replica as the scale-out trigger.
      scale: {
        minReplicas: 1
        maxReplicas: 1
        rules: [
          {
            name: 'http-scale'
            http: { metadata: { concurrentRequests: '8' } }
          }
        ]
      }
    }
  }
}

// ── worker ──────────────────────────────────────────────────────
resource worker 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${appName}-worker'
  location: location
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      registries: registryConfig
      secrets: [
        { name: 'ghcr-pat', value: ghcrPat }
        { name: 'redis-url', value: redisUrl }
      ]
    }
    template: {
      containers: [
        {
          name: 'worker'
          image: containerImage
          command: ['celery']
          args: ['-A', 'enzyme_tk_app.app.backend.celery_app', 'worker', '-l', 'info']
          resources: { cpu: json('2.0'), memory: '4.0Gi' }
          env: sharedEnv
          volumeMounts: sharedVolumeMounts
        }
      ]
      volumes: sharedVolumes
      // Fixed at 3 to match today's compose `replicas: 3`.
      // Swap to a KEDA custom scale rule on Redis list length later
      // if worker count should track queue depth instead.
      scale: {
        minReplicas: 3
        maxReplicas: 3
      }
    }
  }
}

// ── beat — singleton; min=max=1 enforces "never more than one beat" ─
resource beat 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${appName}-beat'
  location: location
  properties: {
    managedEnvironmentId: containerEnv.id
    configuration: {
      registries: registryConfig
      secrets: [
        { name: 'ghcr-pat', value: ghcrPat }
        { name: 'redis-url', value: redisUrl }
      ]
    }
    template: {
      containers: [
        {
          name: 'beat'
          image: containerImage
          command: ['celery']
          args: ['-A', 'enzyme_tk_app.app.backend.celery_app', 'beat', '--loglevel=info']
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: [
            { name: 'REDIS_URL', secretRef: 'redis-url' }
            { name: 'CELERY_SWEEP_INTERVAL_SECONDS', value: '86400' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

output webFqdn string = web.properties.configuration.ingress.fqdn
output redisHostName string = redisCache.properties.hostName
