# serve.ps1 - Servidor estático muy simple (localhost) para Web Serial
# Uso:  powershell -ExecutionPolicy Bypass -File .\serve.ps1 -Port 8000

param(
  [int]$Port = 8000
)

Add-Type -AssemblyName System.Net.HttpListener

$prefix = "http://localhost:$Port/"
$listener = New-Object System.Net.HttpListener
$listener.Prefixes.Add($prefix)
$listener.Start()
Write-Host "Servidor iniciado en $prefix (Ctrl+C para detener)"

# Raíz de archivos (donde ejecutas el script)
$root = Convert-Path "."

# Tipos MIME básicos
$mime = @{
  ".html" = "text/html; charset=utf-8"
  ".htm"  = "text/html; charset=utf-8"
  ".js"   = "text/javascript; charset=utf-8"
  ".mjs"  = "text/javascript; charset=utf-8"
  ".css"  = "text/css; charset=utf-8"
  ".png"  = "image/png"
  ".jpg"  = "image/jpeg"
  ".jpeg" = "image/jpeg"
  ".svg"  = "image/svg+xml"
  ".json" = "application/json; charset=utf-8"
  ".txt"  = "text/plain; charset=utf-8"
}

# Función para responder 404/500
function Send-Error([System.Net.HttpListenerResponse]$resp, [int]$code, [string]$msg) {
  $resp.StatusCode = $code
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($msg)
  $resp.OutputStream.Write($bytes, 0, $bytes.Length)
  $resp.Close()
}

try {
  while ($listener.IsListening) {
    $context = $listener.GetContext()

    # Normaliza ruta
    $urlPath = $context.Request.Url.AbsolutePath
    if ($urlPath -eq "/") { $urlPath = "/index.html" }
    $localPath = Join-Path $root ($urlPath.TrimStart("/") -replace "/", [IO.Path]::DirectorySeparatorChar)

    if (-not (Test-Path $localPath)) {
      Send-Error $context.Response 404 "404 Not Found"
      continue
    }

    try {
      $ext = [IO.Path]::GetExtension($localPath).ToLower()
      $contentType = $mime[$ext]
      if (-not $contentType) { $contentType = "application/octet-stream" }

      $bytes = [IO.File]::ReadAllBytes($localPath)
      $context.Response.StatusCode  = 200
      $context.Response.ContentType = $contentType
      $context.Response.ContentLength64 = $bytes.Length
      $context.Response.OutputStream.Write($bytes, 0, $bytes.Length)
      $context.Response.Close()
      Write-Host ("{0} 200 {1}" -f (Get-Date), $urlPath)
    }
    catch {
      Send-Error $context.Response 500 "500 Internal Server Error"
    }
  }
}
finally {
  $listener.Stop()
  $listener.Close()
}