# Fixture sample on this computer

This bundle builds the merged app and a private Postgres database named `grok_demo_sample`. It is not a production deployment. Payment, messaging, and calendar outbound stay off. The screening ratio and tour schedule are fixture labels, not organization rules.

Docker Desktop must be running its Linux engine before you start. The scripts do not change Docker contexts or other projects.

On Windows, double-click `Start-Demo.cmd` to build/start the sample and open your browser. It works from the repository root or the extracted bundle. Use `docs/DEMO_WALKTHROUGH.md` in the extracted bundle or repository root for a rehearsable 8–10 minute demo. The five home-screen buttons open Accounting, Prospect, Tenant, Manager, and Owner directly.

```powershell
Set-Location <this-folder>
.\Start-GrokDemo.ps1
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000/v1/health
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:3000/
```

Open http://127.0.0.1:3000/ and choose a fictional role. The first build downloads images and compiles the app. Expect several minutes, about 2 GB of image disk, and about 1 GB of memory while it is running.

`.\Stop-GrokDemo.ps1` stops this project and keeps the sample volume. `.\Reset-GrokDemo.ps1` deletes only that volume and seeds it again. The generated `.env` stays on this computer and is not part of the zip.

On a Mac, from this folder:

```bash
/bin/bash start-macos.sh
curl -sf http://127.0.0.1:3000/v1/health
curl -sf http://127.0.0.1:3000/
```

`/bin/bash stop-macos.sh` stops this project and keeps the sample volume and `.env`. `/bin/bash reset-macos.sh` is separate and destructive: it deletes only this project's containers and `grok-property-sample-pg` volume, then starts again. Starting does not reset. If `.env` already exists, the start script keeps it and does not print it. The pinned images publish linux/arm64 manifests. This bundle was not run on Apple silicon here.
