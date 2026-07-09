#!/usr/bin/env pwsh
# deploy.ps1 — Copia o código para a VM e reinicia o serviço via Docker

$VM       = "memoria-vm-2"
$ZONE     = "southamerica-east1-a"
$PROJECT  = "memoria-499818"
$REMOTE   = "/opt/licita-radar"

Write-Host "==> [1/4] Copiando codigo para a VM..." -ForegroundColor Cyan

# Cria pasta destino na VM
gcloud compute ssh $VM --zone $ZONE --project $PROJECT `
    --command "sudo mkdir -p $REMOTE && sudo chown -R `$USER:$USER $REMOTE"

# Copia arquivos (exclui venv, __pycache__, .git)
$FILES = @("licita", "requirements.txt", "Dockerfile", ".dockerignore")
foreach ($f in $FILES) {
    gcloud compute scp --recurse --zone $ZONE --project $PROJECT `
        ".\$f" "${VM}:${REMOTE}/"
    Write-Host "   -> $f enviado" -ForegroundColor Green
}

Write-Host "==> [2/4] Build da imagem Docker na VM..." -ForegroundColor Cyan
gcloud compute ssh $VM --zone $ZONE --project $PROJECT `
    --command "cd $REMOTE && sudo docker build -t licita-radar:latest ."

Write-Host "==> [3/4] Parando container antigo (se existir)..." -ForegroundColor Cyan
gcloud compute ssh $VM --zone $ZONE --project $PROJECT `
    --command "sudo docker rm -f licita-radar 2>/dev/null || true"

Write-Host "==> [4/4] Iniciando novo container..." -ForegroundColor Cyan
gcloud compute ssh $VM --zone $ZONE --project $PROJECT `
    --command @"
sudo docker run -d \
  --name licita-radar \
  --restart unless-stopped \
  -p 8080:8080 \
  -e PORT=8080 \
  -e ENVIRONMENT=production \
  licita-radar:latest
"@

Write-Host ""
Write-Host "✅ Deploy concluido!" -ForegroundColor Green
Write-Host "   API: http://35.247.217.66:8080/docs" -ForegroundColor Yellow
Write-Host "   Health: http://35.247.217.66:8080/health" -ForegroundColor Yellow
