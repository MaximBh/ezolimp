# EzOlimp

Local setup for the EzOlimp frontend/backend with Ollama (`deepseek-r1:8b`).

## Why One Model File Is Not In Git

One Ollama blob is intentionally not committed:

`.ollama/models/blobs/sha256-e6a7edc1a4d7d9b2de136a221a57336b76316cfe53a252aeba814496c5ae439d`

Reason: GitHub rejects this object due size limits.

## Restore The Missing Model File

Run one of these installers from the project root:

- Windows: `install_model.bat`
- Linux/macOS: `bash install_model.sh`

Both scripts:

- set `OLLAMA_MODELS` to `<project>/.ollama/models`
- run `ollama pull deepseek-r1:8b`
- restore the missing blob locally

## Run The Project

- Windows: `start.bat`
- Linux/macOS: `bash run.sh`

Default ports:

- backend: `http://127.0.0.1:8001`
- frontend: `http://127.0.0.1:3000`
- Ollama API: `http://localhost:11434`

The local launch scripts bind the web servers to loopback. For a public Ubuntu deployment, serve the frontend and API from one HTTPS origin through Nginx; do not expose Uvicorn or the development frontend port directly. Production startup requires `APP_ENV=production`, an HTTPS `PUBLIC_ORIGIN`, and an explicit `CORS_ALLOWED_ORIGINS` list containing that origin. The application rejects wildcard or HTTP origins in production.

Before first startup, place a random `JWT_SECRET` of at least 32 bytes in the private application environment file outside the project: `%LOCALAPPDATA%\EzOlimp\ezolimp.env` on Windows, or `$XDG_CONFIG_HOME/ezolimp/ezolimp.env` (default `~/.config/ezolimp/ezolimp.env`) on Linux/macOS. You can generate a value with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. The application refuses to start without a valid secret. `EZOLIMP_ENV_FILE` can select another private file path.

## Public Ubuntu deployment

Production templates and a step-by-step Ubuntu deployment guide are in [`deploy/ubuntu/README.md`](deploy/ubuntu/README.md). They use a dedicated `ezolimp` service account, systemd sandboxing and resource caps, one Uvicorn worker, SQLite/cache directories outside the code checkout, a loopback-only backend, and Nginx TLS termination with WebSocket forwarding. One worker is required because PvP match state is currently held in process memory.

1. Install the project read-only at `/opt/ezolimp`, create its virtual environment, and install `requirements.lock`. Keep the code owned by root or a deployment account, not the runtime service user.
2. Create the service account and writable state directories: `/var/lib/ezolimp` and `/var/cache/ezolimp`, owned by `ezolimp:ezolimp`. If you are migrating an existing SQLite database, copy it into `/var/lib/ezolimp/olimpiada.db` while the old application is stopped; preserve a backup first.
3. Copy `deploy/ubuntu/ezolimp.env.example` to `/etc/ezolimp/ezolimp.env`. Replace `example.com` with the real HTTPS hostname and set `JWT_SECRET` from `openssl rand -base64 48`. Restrict the environment file to root and the service group (mode `0640`); never commit it.
4. Obtain a certificate for the real domain, install the Nginx template as a site, replace the sample hostname and certificate paths, and run `nginx -t`. Expose only ports 80/443 publicly; keep port 8001 private to loopback.
5. Install `deploy/ubuntu/ezolimp.service` as `/etc/systemd/system/ezolimp.service`, then run `systemctl daemon-reload`, `systemctl enable --now ezolimp`, and `systemctl enable --now nginx`. Check `systemctl status ezolimp` and `curl -fsS https://<domain>/healthz`.

The Nginx template redirects HTTP to HTTPS, adds HSTS, caps ordinary request bodies at 2 MiB, permits the 45 MiB admin import, and forwards WebSockets and trusted proxy headers. Browser JWTs are issued as HttpOnly, Secure production cookies and are no longer stored in `localStorage`; users must sign in again after upgrading. Configure the host firewall to allow SSH and ports 80/443 only. Do not run multiple Uvicorn workers until PvP state and rate limits move to shared storage.
