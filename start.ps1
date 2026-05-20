Write-Host "=== Запуск Telegram Mini App ===" -ForegroundColor Cyan

# 1. Запускаем FastAPI сервер
Write-Host "[1/3] Запускаю FastAPI сервер..." -ForegroundColor Yellow
$server = Start-Process -NoNewWindow -FilePath "python" -ArgumentList "-m uvicorn main:app --host 127.0.0.1 --port 8000" -WorkingDirectory "C:\telegram-mini-app" -PassThru
Start-Sleep -Seconds 2
Write-Host "[OK] Сервер запущен на http://127.0.0.1:8000" -ForegroundColor Green

# 2. Запускаем ngrok
Write-Host "[2/3] Запускаю ngrok туннель..." -ForegroundColor Yellow
$ngrok = Start-Process -NoNewWindow -FilePath "C:\telegram-mini-app\ngrok.exe" -ArgumentList "http 8000 --log=stdout" -WorkingDirectory "C:\telegram-mini-app" -PassThru
Start-Sleep -Seconds 4

# 3. Получаем публичный URL ngrok
try {
    $api = Invoke-RestMethod -Uri "http://127.0.0.1:4040/api/tunnels" -ErrorAction Stop
    $ngrokUrl = $api.tunnels[0].public_url
    Write-Host "[OK] ngrok URL: $ngrokUrl" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Не удалось получить URL от ngrok. Проверь, не занят ли порт 4040." -ForegroundColor Red
    $ngrokUrl = "http://localhost:8000"
}

# 4. Обновляем .env
Write-Host "[3/3] Обновляю APP_URL в .env..." -ForegroundColor Yellow
$envContent = Get-Content "C:\telegram-mini-app\.env" -Raw
$envContent = $envContent -replace 'APP_URL=.*', "APP_URL=$ngrokUrl"
Set-Content "C:\telegram-mini-app\.env" -Value $envContent
Write-Host "[OK] APP_URL = $ngrokUrl" -ForegroundColor Green

Write-Host "`n=== Готово! ===" -ForegroundColor Cyan
Write-Host "Ссылка для Mini App (нужно указать в BotFather):" -ForegroundColor White
Write-Host "$ngrokUrl" -ForegroundColor Magenta
Write-Host "`nТеперь в другом терминале запусти бота:" -ForegroundColor Yellow
Write-Host "cd C:\telegram-mini-app && python bot.py" -ForegroundColor White
Write-Host "`nНажми любую клавишу чтобы остановить сервер и ngrok..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

# Останавливаем процессы
Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
Stop-Process -Id $ngrok.Id -Force -ErrorAction SilentlyContinue
Write-Host "Всё остановлено." -ForegroundColor Cyan
