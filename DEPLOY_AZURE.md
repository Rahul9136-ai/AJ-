# Deploy AJ to Azure

AJ is a Streamlit web app, packaged as a container ([`Dockerfile`](Dockerfile)). The
easiest path is **Azure Container Apps**, which can build the image *in the cloud* from
this folder — so you don't even need Docker installed locally.

> ⏱️ ~15 min the first time. 💳 Needs an Azure account (free tier available; this app on
> the smallest paid tier is a few dollars/month — see Cost below).

---

## 1. Prerequisites (one time)

1. An **Azure account** → https://azure.microsoft.com/free (free credits for new accounts).
2. The **Azure CLI** → https://aka.ms/installazurecli (Windows installer).
3. Open PowerShell and sign in:
   ```powershell
   az login
   az extension add --name containerapp --upgrade
   az provider register --namespace Microsoft.App
   az provider register --namespace Microsoft.OperationalInsights
   ```

---

## 2. Deploy (one command)

From the project folder, run this (replace the secret values with your real keys):

```powershell
cd "C:\Users\lenovo\Desktop\AI Agent"

az containerapp up `
  --name aj-app `
  --resource-group aj-rg `
  --location centralindia `
  --source . `
  --ingress external `
  --target-port 8501 `
  --env-vars `
    AGENT_PROVIDER=groq `
    AGENT_FALLBACKS=gemini `
    GROQ_API_KEY=gsk_your_groq_key `
    GEMINI_API_KEY=your_gemini_key `
    AGENT_MODEL=llama-3.3-70b-versatile `
    AJ_PASSWORD=your-app-password
```

What this does: creates a resource group, builds the container from the `Dockerfile`
in the cloud, deploys it to Container Apps, and gives it a public HTTPS URL. When it
finishes it prints the URL (looks like `https://aj-app.<random>.centralindia.azurecontainerapps.io`).

> **Note on the chain:** `ollama` is dropped here — there's no local Ollama server in the
> cloud. The deployed failover is `groq → gemini`. Groq is set as primary (fast, generous
> free tier); flip with `AGENT_PROVIDER`/`AGENT_FALLBACKS` if you prefer.

---

## 3. Open it

Visit the printed URL → you'll get AJ's lock screen → enter your `AJ_PASSWORD`.
Voice (mic + spoken replies) works because Azure serves it over HTTPS.

---

## Updating after code changes

Re-run the same `az containerapp up` command — it rebuilds and rolls out the new version.
(Push your code to GitHub too, as usual.)

---

## Handling secrets properly (recommended)

Passing keys via `--env-vars` stores them in plain config. For real use, store them as
**secrets** instead:

```powershell
az containerapp secret set --name aj-app --resource-group aj-rg `
  --secrets groqkey=gsk_your_groq_key geminikey=your_gemini_key ajpw=your-app-password

az containerapp update --name aj-app --resource-group aj-rg `
  --set-env-vars GROQ_API_KEY=secretref:groqkey GEMINI_API_KEY=secretref:geminikey AJ_PASSWORD=secretref:ajpw
```

---

## Cost & scaling

- **Container Apps** has a monthly free grant; a low-traffic app often costs **$0–5/month**,
  and can **scale to zero** when idle (set `--min-replicas 0`).
- To avoid cold starts, set `--min-replicas 1` (small always-on cost).
- This app is single-user-ish (shared password); keep `--max-replicas 1` so the to-do
  list / memory stay consistent (they're stored on the container's local disk).

## Persisting memory & to-dos (optional)

`workspace/` (memory + to-dos) lives on the container and resets on redeploy. To keep it,
mount an Azure Files share to `/app/workspace` (Container Apps storage), or accept that it's
ephemeral. For a personal assistant, ephemeral is usually fine to start.

---

## Alternative: Azure Web App for Containers

If you prefer App Service: build/push the image to Azure Container Registry, create a
Linux Web App from that image, set `WEBSITES_PORT=8501`, turn **Web sockets = On** (required
for Streamlit), and add the same env vars under Configuration → Application settings.
Container Apps (above) is simpler and is the recommended path.
