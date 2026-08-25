# Deployment

The whole system ships as one container: the built web app served by the API
that drives the agent. It runs with **zero environment variables** — demo mode
is keyless by design, and live mode lights up per session when a client
supplies its own credentials. The deployed demo therefore holds no model keys
of its own.

## Run it locally

```bash
docker build -t interview-prep-agent .
docker run --rm -p 8000:8000 interview-prep-agent
```

Then open `http://127.0.0.1:8000`. `GET /api/health` reports the version and
which modes are available, which is also what the platform's probe reads.

## One-time Azure setup

Everything below is run once, from a shell with the `az` CLI signed in. Values
in angle brackets are yours to choose; the rest can be pasted as written.

```bash
# Names used throughout. Pick a region close to you.
export RG=interview-prep-agent-rg
export LOCATION=eastus
export ENVIRONMENT=interview-prep-agent-env
export APP=interview-prep-agent
export GHCR_IMAGE=ghcr.io/<your-github-user>/interview-prep-agent:latest
```

```bash
# Resource group and the Container Apps environment.
az group create --name "$RG" --location "$LOCATION"

az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App --wait
az provider register --namespace Microsoft.OperationalInsights --wait

az containerapp env create \
  --name "$ENVIRONMENT" \
  --resource-group "$RG" \
  --location "$LOCATION"
```

```bash
# The app itself. min-replicas 0 is the important flag: the app scales to
# zero when idle, which is what keeps a credit-funded deployment near free.
az containerapp create \
  --name "$APP" \
  --resource-group "$RG" \
  --environment "$ENVIRONMENT" \
  --image "$GHCR_IMAGE" \
  --target-port 8000 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 1 \
  --cpu 0.5 --memory 1.0Gi \
  --env-vars PORT=8000
```

If the image is private, register the registry once:

```bash
az containerapp registry set \
  --name "$APP" --resource-group "$RG" \
  --server ghcr.io \
  --username <your-github-user> \
  --password <a-github-token-with-read:packages>
```

### The federated credential the workflow signs in with

No secret is stored in the repository. The deploy workflow authenticates with
OIDC against an app registration that trusts this repository's `main` branch.

```bash
# An app registration and a service principal for it.
export APP_ID=$(az ad app create --display-name "$APP-deploy" --query appId -o tsv)
az ad sp create --id "$APP_ID"

# Let it change only this resource group.
export SUBSCRIPTION_ID=$(az account show --query id -o tsv)
az role assignment create \
  --assignee "$APP_ID" \
  --role Contributor \
  --scope "/subscriptions/$SUBSCRIPTION_ID/resourceGroups/$RG"

# Trust GitHub Actions running on main in this repository.
az ad app federated-credential create --id "$APP_ID" --parameters '{
  "name": "github-main",
  "issuer": "https://token.actions.githubusercontent.com",
  "subject": "repo:<your-github-user>/interview-prep-agent:ref:refs/heads/main",
  "audiences": ["api://AzureADTokenExchange"]
}'

# The three identifiers the workflow needs.
echo "AZURE_CLIENT_ID=$APP_ID"
echo "AZURE_TENANT_ID=$(az account show --query tenantId -o tsv)"
echo "AZURE_SUBSCRIPTION_ID=$SUBSCRIPTION_ID"
```

### Repository variables to set

Under **Settings → Secrets and variables → Actions → Variables**, set these
six. They are identifiers, not secrets — which is the point of the OIDC
setup:

| Variable | Value |
|---|---|
| `AZURE_CLIENT_ID` | the app registration's client id, printed above |
| `AZURE_TENANT_ID` | the tenant id, printed above |
| `AZURE_SUBSCRIPTION_ID` | the subscription id, printed above |
| `AZURE_RESOURCE_GROUP` | `interview-prep-agent-rg` |
| `AZURE_CONTAINERAPP_NAME` | `interview-prep-agent` |

## Steady state

Run the **Deploy** workflow from the Actions tab. It builds the image, pushes
it to the registry under both the commit SHA and `latest`, rolls the Container
App onto the SHA-tagged image, and prints the public hostname. That is the
whole loop: one manual trigger per deployment, nothing else to remember.

## Cost

The app is configured to scale to zero. An idle deployment runs no replicas
and costs approximately nothing; a request wakes one replica, which pays a
cold start of a few seconds. The ceiling is one replica at 0.5 vCPU, so a
runaway cost is not available even under load — requests queue instead. This
suits a credit-funded deployment, and the session bounds below keep the
queue honest.

## Security

- **The demo is keyless by design.** Demo sessions run against the fixture
  provider the regression suite injects. No model is called, so no credential
  is needed and none is held server-side.
- **Live sessions carry their own credentials.** A client supplies a key at
  session creation; it lives on the session object in memory, is never logged,
  never written to disk, never echoed back, and is dropped with the session.
  The deployed instance stores no model keys of its own — `GET /api/health`
  reports `server_side_credentials: false`, which you can check on the live
  hostname.
- **The abuse controls are the session bounds**, not authentication: a
  concurrent-session ceiling, a per-IP session cap, a TTL with a cleanup task,
  and input-size ceilings on the posting, the evidence, the round text, the
  research text and each answer. Every one is a setting, and exceeding any of
  them is a structured refusal rather than a crash. Tighten them for a public
  deployment; the defaults suit a demonstration.
- **CORS is closed by default.** Set `cors_origins` only if a different origin
  must reach the API.
