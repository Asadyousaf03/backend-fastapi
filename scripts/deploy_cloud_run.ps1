# Deploy genomic AST API + worker job to Cloud Run.
# Usage (after image is built):
#   .\scripts\deploy_cloud_run.ps1

$ErrorActionPreference = "Stop"
$PROJECT = if ($env:GOOGLE_CLOUD_PROJECT) { $env:GOOGLE_CLOUD_PROJECT } else { "genomic-ast-hack" }
$REGION = if ($env:GOOGLE_CLOUD_REGION) { $env:GOOGLE_CLOUD_REGION } else { "us-central1" }
$IMAGE = "$REGION-docker.pkg.dev/$PROJECT/genomic-ast/api:latest"
$SERVICE = "genomic-ast-api"
$JOB = "genomic-ast-worker"
$ROOT = Split-Path -Parent $PSScriptRoot

Write-Host "Deploying service $SERVICE ..."
gcloud run deploy $SERVICE `
  --image $IMAGE `
  --region $REGION `
  --project $PROJECT `
  --platform managed `
  --allow-unauthenticated `
  --port 8080 `
  --cpu 2 `
  --memory 2Gi `
  --timeout 300 `
  --concurrency 20 `
  --min-instances 0 `
  --max-instances 3 `
  --env-vars-file "$ROOT\deploy\cloudrun-api.env.yaml" `
  --set-secrets "DATABASE_URL=DATABASE_URL:latest,S3_ACCESS_KEY=S3_ACCESS_KEY:latest,S3_SECRET_KEY=S3_SECRET_KEY:latest,S3_ENDPOINT_URL=S3_ENDPOINT_URL:latest"

$URL = gcloud run services describe $SERVICE --region $REGION --project $PROJECT --format="value(status.url)"
Write-Host "Service URL: $URL"

Write-Host "Updating PUBLIC_API_BASE ..."
gcloud run services update $SERVICE `
  --region $REGION `
  --project $PROJECT `
  --update-env-vars "PUBLIC_API_BASE=$URL" | Out-Null

Write-Host "Deploying job $JOB ..."
$exists = $false
cmd /c "gcloud run jobs describe $JOB --region $REGION --project $PROJECT 1>nul 2>nul"
if ($LASTEXITCODE -eq 0) { $exists = $true }

$jobEnv = Get-Content "$ROOT\deploy\cloudrun-job.env.yaml" -Raw
if ($jobEnv -notmatch "PUBLIC_API_BASE") {
  $jobEnv = $jobEnv.TrimEnd() + "`nPUBLIC_API_BASE: `"$URL`"`n"
} else {
  $jobEnv = $jobEnv -replace 'PUBLIC_API_BASE:.*', "PUBLIC_API_BASE: `"$URL`""
}
$tmpJobEnv = Join-Path $env:TEMP "cloudrun-job.env.yaml"
Set-Content -Path $tmpJobEnv -Value $jobEnv -NoNewline

if (-not $exists) {
  gcloud run jobs create $JOB `
    --image $IMAGE `
    --region $REGION `
    --project $PROJECT `
    --task-timeout 3600 `
    --max-retries 1 `
    --cpu 4 `
    --memory 8Gi `
    --command "python3" `
    --args "scripts/run_cloud_job.py" `
    --env-vars-file $tmpJobEnv `
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,S3_ACCESS_KEY=S3_ACCESS_KEY:latest,S3_SECRET_KEY=S3_SECRET_KEY:latest,S3_ENDPOINT_URL=S3_ENDPOINT_URL:latest"
} else {
  gcloud run jobs update $JOB `
    --image $IMAGE `
    --region $REGION `
    --project $PROJECT `
    --task-timeout 3600 `
    --max-retries 1 `
    --cpu 4 `
    --memory 8Gi `
    --command "python3" `
    --args "scripts/run_cloud_job.py" `
    --env-vars-file $tmpJobEnv `
    --set-secrets "DATABASE_URL=DATABASE_URL:latest,S3_ACCESS_KEY=S3_ACCESS_KEY:latest,S3_SECRET_KEY=S3_SECRET_KEY:latest,S3_ENDPOINT_URL=S3_ENDPOINT_URL:latest"
}

$PROJECT_NUMBER = gcloud projects describe $PROJECT --format="value(projectNumber)"
$SA = "$PROJECT_NUMBER-compute@developer.gserviceaccount.com"
gcloud run jobs add-iam-policy-binding $JOB `
  --region $REGION `
  --project $PROJECT `
  --member "serviceAccount:$SA" `
  --role "roles/run.invoker" `
  --quiet | Out-Null

Write-Host ""
Write-Host "DONE"
Write-Host "API:  $URL"
Write-Host "Health: $URL/health"
Write-Host "Ready:  $URL/ready"
Write-Host "Set Vercel NEXT_PUBLIC_API_URL=$URL"
