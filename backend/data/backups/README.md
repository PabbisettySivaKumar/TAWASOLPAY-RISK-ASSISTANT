# `data/backups/`

Automatic backups of the previous version of each CSV.

Every time a new file is uploaded to `data/raw/`, the existing file (if any)
is moved here with a timestamp suffix:

    assets.csv.bak-2026-05-13T09-30-15

This gives a simple audit trail and lets you roll back a bad upload manually.

The folder auto-prunes — only the **last 5 backups** per dataset are kept.
Older ones are deleted automatically by `src/api/upload.py`.

Not committed to Git (covered by `.gitignore`).
