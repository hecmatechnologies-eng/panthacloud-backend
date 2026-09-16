# Deploying Fussion to Railway

This guide walks you through deploying the Fussion backend service to [Railway](https://railway.com/) with an attached PostgreSQL database.

---

## Architecture on Railway

Fussion on Railway consists of two interconnected services in a single Railway project:

```text
[Railway Project]
   ├── PostgreSQL Service (Railway Plugin)
   │     └── DATABASE_URL (${{Postgres.DATABASE_URL}})
   │
   └── Fussion Backend Service (FastAPI + Pydantic AI)
         ├── Builder: Dockerfile (Root or backend/)
         ├── Pre-Deploy: alembic upgrade head
         └── Start: uvicorn app.main:app
```

> [!NOTE]
> The Fussion Studio (Next.js frontend) is maintained in a separate repository and deploys as its own service on Railway or Vercel.

---

## Prerequisites

1. A [Railway account](https://railway.com/).
2. A GitHub account with access to this repository.
3. API credentials for your chosen LLM provider (e.g., Google Gemini or DeepSeek).

---

## Step-by-Step Deployment

### 1. Create Project & Add PostgreSQL Database
1. In Railway, click **New Project**.
2. Select **Provision PostgreSQL**. Railway will spin up a managed PostgreSQL 17 instance.

### 2. Generate Production Secrets
Before deploying, generate high-entropy security keys for JWT auth and token encryption.

Run the local generator script:
```bash
cd backend
python scripts/generate_production_secrets.py
```
This will print a secure `JWT_SECRET_KEY` and Fernet `SECRET_ENCRYPTION_KEY`.

### 3. Deploy the Backend Service
1. In your Railway project canvas, click **New** $\rightarrow$ **GitHub Repo**.
2. Select the `fussion` (or `panthacloud-backend`) repository.
3. Railway will detect `railway.json` / `Dockerfile` automatically.

### 4. Configure Environment Variables
In the newly created backend service, navigate to **Variables** $\rightarrow$ **Raw Editor**, and paste the following (customizing values as needed):

```dotenv
APP_ENV=production
APP_NAME=fussion-backend
APP_VERSION=0.1.0

# References the Postgres service in the same project:
DATABASE_URL=${{Postgres.DATABASE_URL}}

# Keys generated from Step 2:
JWT_SECRET_KEY=<your-generated-jwt-secret>
SECRET_ENCRYPTION_KEY=<your-generated-fernet-key>

# Required production spend cap:
MODEL_DEFAULT_SPEND_LIMIT_USD=25.0

# Studio origin (Update with your Studio's actual URL):
CORS_ORIGINS=["https://your-studio.up.railway.app"]
FRONTEND_URL=https://your-studio.up.railway.app

# Model Gateway:
MODEL_PROVIDER=gemini
MODEL_ID=gemini-2.5-flash
MODEL_ALLOWED_IDS=["gemini-2.5-flash"]
MODEL_API_KEY=<your-gemini-api-key>

# Embeddings:
EMBEDDING_PROVIDER=gemini
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_DIMENSION=768
EMBEDDING_API_KEY=<your-gemini-api-key>
```

> [!TIP]
> The backend automatically converts Railway's `postgresql://` connection URL to `postgresql+psycopg://` at runtime, and automatically falls back to `RAILWAY_PUBLIC_DOMAIN` for the widget script URL if `PUBLIC_API_URL` is omitted.

### 5. Verify the Deployment
1. **Migrations**: Check the **Deploy Logs**. You should see the pre-deploy release command succeed:
   ```text
   INFO [alembic.runtime.migration] Running upgrade -> ... (head)
   ```
2. **Health Check**: Once deployed, visit your service URL at `/health`:
   ```bash
   curl https://<your-service>.up.railway.app/health
   ```
   Expected response:
   ```json
   {
     "status": "healthy",
     "service": "fussion-backend",
     "version": "0.1.0",
     "database": {
       "status": "connected"
     }
   }
   ```
3. **Swagger Docs**: Interactive API documentation is available at `https://<your-service>.up.railway.app/docs`.

---

## Connecting the Studio Frontend

When deploying the Studio frontend service:
1. Provide the backend API URL as `API_URL` (or `NEXT_PUBLIC_API_URL`).
2. **Important**: Rebuild the Studio container if the backend domain changes, because Next.js bakes rewrites at build time.
3. Ensure the Studio's domain is added to `CORS_ORIGINS` on the backend service.
