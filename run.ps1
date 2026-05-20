# Start FastAPI server
$serverJob = Start-Job -Name "fastapi" -ScriptBlock {
    python -m uvicorn main:app --host 127.0.0.1 --port 8000
} -InitializationScript { Set-Location "C:\telegram-mini-app" }

Start-Sleep -Seconds 3

# Check server
try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -ErrorAction Stop
    Write-Host "[OK] FastAPI server: $($r.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "[FAIL] FastAPI server didn't start" -ForegroundColor Red
    exit 1
}

# Start ngrok
$ngrokProcess = Start-Process -FilePath "C:\telegram-mini-app\ngrok.exe" -ArgumentList "http 8000" -NoNewWindow -PassThru
Start-Sleep -Seconds 5

# Get public URL
try {
    $tunnels = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -UseBasicParsing -ErrorAction Stop
    $url = $tunnels.tunnels[0].public_url
    Write-Host "[OK] ngrok URL: $url" -ForegroundColor Green

    # Update .env
    $envContent = Get-Content "C:\telegram-mini-app\.env" -Raw
    $envContent = $envContent -replace 'APP_URL=.*', "APP_URL=$url"
    Set-Content "C:\telegram-mini-app\.env" -Value $envContent
    Write-Host "[OK] .env updated" -ForegroundColor Green

    Write-Host "`n=== YOUR MINI APP URL ===" -ForegroundColor Cyan
    Write-Host $url -ForegroundColor Magenta
    Write-Host "==========================" -ForegroundColor Cyan
    Write-Host "`n1. Send this URL to BotFather as Mini App URL"
    Write-Host "2. In another terminal run: python bot.py"
} catch {
    Write-Host "[FAIL] ngrok didn't start. Error: $_" -ForegroundColor Red
}

# Wait for key press to shut down
Write-Host "`nPress any key to stop..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

Stop-Process -Id $ngrokProcess.Id -Force -ErrorAction SilentlyContinue
Stop-Job -Name "fastapi" -ErrorAction SilentlyContinue | Remove-Job -Force
