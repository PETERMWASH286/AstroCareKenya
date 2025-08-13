# Configuration
$env:FLASK_APP = "app:create_app"
$env:FLASK_ENV = "development"
$mysqlUser = "root"
$mysqlPass = "pass"
$centralDb = "astrocare_db"
$flaskCmd = "flask"

# Step 1: Get list of DB URIs
$dbUris = & mysql -N -B -u"$mysqlUser" -p"$mysqlPass" "$centralDb" -e "SELECT db_uri FROM hospitals"

# Step 2: Loop over each URI and apply migrations
foreach ($uri in $dbUris) {
    Write-Host "Migrating $uri ..."
    $env:DATABASE_URL = $uri

    & $flaskCmd db stamp head
    & $flaskCmd db migrate -m "Auto-migration for $uri"
    & $flaskCmd db upgrade

    Write-Host "Migration completed for $uri"
    Write-Host ""
}

# Step 3: Cleanup environment variables
Remove-Item Env:\FLASK_APP, Env:\FLASK_ENV, Env:\DATABASE_URL

Write-Host "All tenant migrations completed successfully!"
