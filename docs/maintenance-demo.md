# Maintenance demo walkthrough

Start with **Report a repair** on the overview. The resident's linked home is shown automatically. Save an observed issue, then answer individual follow-up questions, attach an optional photo, or continue without one. Finish intake when ready; missing optional details do not delete or block the request.

Saved requests appear under **Your requests**. Opening a request puts its ID in the URL so refresh restores it. Duplicate report submissions with the same request key return the existing ticket. General updates are retained as messages without pretending to answer unrelated intake fields.

Use **Open manager queue** (demo only) or the **Maintenance queue** navigation item to switch to the fictional manager. Open a request, inspect its details or photos, and save a status with a resident-facing note. Return to the resident role and open the saved request to see the update. Dispatch and visit arrangements remain manual.

Emergency keywords in the description, location, safety concerns, or a follow-up immediately show safety guidance and stop ordinary intake questions. The website does not call emergency services or dispatch a contractor. Classification uses conservative reviewed rules, not diagnosis or an AI model.

Demo photos accept JPEG, PNG, and HEIC/HEIF up to 20 MiB. The existing fixture scanner checks bytes, decodes images, and produces metadata-stripped derivatives. It is not a production malware service. Only the isolated fictional sample enables it. Railway stores the media at `/data/media` on the API volume; the local Compose sample uses the `grok-property-sample-media` volume. Production photo acceptance stays disabled until a production scanner is configured. Use only fictional, non-sensitive images in the public demo.

Validation includes tenant and organization isolation, linked-home selection, report retries, blank input, specific versus general follow-ups, emergency detection, saved status history, photo processing, and migration upgrade/downgrade. The packaged-demo browser test covers resident submission, photo upload and download, reload, manager update, resident visibility, mobile overflow, and serious/critical accessibility checks.
