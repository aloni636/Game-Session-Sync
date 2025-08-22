# Game Session Sync
A Windows scheduled task which monitors screenshots & screen recordings, aggregates them into sessions, and uploads them to Google Drive and Notion.

# Setup
1. Generally follow [PyDrive2 authentication quick guide](https://docs.iterative.ai/PyDrive2/quickstart/#authentication).

1. Configure OAuth in *Google Auth Platform / Data acces* to have `./auth/drive.file` scope, **not** `./auth/drive`. Scope `./auth/drive.file` is a restricted version of `./auth/drive` and **doesn't require verification of the application**.

1. Publish the application in *Google Auth Platform / Audience* to **Production**. This will extend the lifespan of the access tokens.


## Dev Worflows
- Poetry for dependency management
- Interactive notebook can be used by running `poetry install --with notebook`
- Production/test environments are configured by using `.env` (prod) and `dev.env` (debugging)

# Architecture
- Internal processing datetime timezone format is **UTC**.
- One client is allowed at the time, because it is a personal tracker.
- The Notion DB is used for state management. On Notion write failure files will be **re-scanned** with Google Drive, **but not reuploaded**.
- Batch ETL is used uploading. **Stream based processing** coupled with USN Journal queries and full re-scans fallbacks was considered but a continuous watchdog process for a sparse producer (*me*) with latency tolerances of 1+ hours is **unnecessary**.

## TODOs
- [X] Handle Notion side upsert for sessions in progress.
    - Sessions on average are more than 1 hour, so **upserting** every 1 hour will populate an entry fresh to be edited **before the session ends**.
- [ ] Use `watchdog` and periodic validation for a more robust sync guarantees.