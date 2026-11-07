# Fixture sample on this computer

This bundle builds the merged app and a private Postgres database named `grok_demo_sample`. It is not a production deployment. Payment, messaging, and calendar outbound stay off. The screening ratio and tour schedule are fixture labels, not organization rules.

Docker Desktop must be running its Linux engine before you start. The scripts do not change Docker contexts or other projects.

```powershell
Set-Location <this-folder>
.\Start-GrokDemo.ps1
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000/v1/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000/
```

Open http://127.0.0.1:3000/ and choose a fictional role. The first build downloads images and compiles the app. Expect several minutes, about 2 GB of image disk, and about 1 GB of memory while it is running.

`.\Stop-GrokDemo.ps1` stops this project and keeps the sample volume. `.\Reset-GrokDemo.ps1` deletes only that volume and seeds it again. The generated `.env` stays on this computer and is not part of the zip.
