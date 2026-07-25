param(
  [switch]$LoginOnly
)

# Aether Desktop AI — Deploy automático para Vercel
$ErrorActionPreference = "Stop"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ROOT

# 1. Login (se necessário)
$whoami = vercel whoami 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host "Fazendo login na Vercel..." -ForegroundColor Yellow
  vercel login
  if ($LASTEXITCODE -ne 0) { exit 1 }
}

if ($LoginOnly) {
  Write-Host "Login concluído. Execute novamente sem -LoginOnly para fazer o deploy." -ForegroundColor Green
  exit 0
}

# 2. Vincular projeto (cria se não existir)
Write-Host "Vinculando projeto..." -ForegroundColor Cyan
vercel link --yes 2>&1
if ($LASTEXITCODE -ne 0) {
  Write-Host "Primeiro deploy será feito com vercel --prod para criar o projeto." -ForegroundColor Cyan
}

# 3. Configurar variáveis de ambiente
Write-Host "Configurando variáveis de ambiente..." -ForegroundColor Cyan
$envVars = @(
  @("LLM_PROVIDER", "gemini"),
  @("GEMINI_API_KEY", "your-gemini-api-key-here"),
  @("ELEVENLABS_API_KEY", "your-elevenlabs-api-key-here"),
  @("JARVIS_AGENT_MODEL", "gemini-2.0-flash"),
  @("VERCEL", "1"),
  @("JARVIS_HOST", "0.0.0.0"),
  @("JARVIS_PORT", "8765"),
  @("AETHER_DESKTOP", "0")
)

foreach ($var in $envVars) {
  $key = $var[0]
  $value = $var[1]
  Write-Host "  $key = $value" -ForegroundColor Gray
  vercel env add $key production <<< "$value" 2>&1 | Out-Null
}
Write-Host "Variáveis configuradas." -ForegroundColor Green

# 4. Deploy
Write-Host "Fazendo deploy para produção..." -ForegroundColor Cyan
vercel --prod 2>&1
if ($LASTEXITCODE -eq 0) {
  Write-Host "Deploy concluído!" -ForegroundColor Green
} else {
  Write-Host "Falha no deploy. Verifique os erros acima." -ForegroundColor Red
}
