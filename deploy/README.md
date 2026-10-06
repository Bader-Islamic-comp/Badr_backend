# Reviewer demo server (Docker)

Runs this API on your own computer so the Badr Android app on your phone can
connect to it. It is the **adult-operated synthetic development demo**
([development boundary](../doc/development-boundary.md)): synthetic data that resets
on restart, no grounded answers or model, no speech. Enter only synthetic text.

## You need

- Docker Desktop (Windows/macOS) or Docker Engine with the Compose plugin (Linux).
- The phone and the computer on the **same private Wi-Fi/LAN**. Not a public or
  guest network: anyone on that network who learns the token can use the demo.
- An APK that has the parent-area *Development service* form
  (see `Badr_android_app/doc/reviewer-release.md`, *Which APK can connect*).

## Start

From this repository's root:

```bash
bash deploy/start-demo.sh                                       # Linux / macOS
powershell -ExecutionPolicy Bypass -File deploy\start-demo.ps1  # Windows
```

The script:

1. creates a random operator token in `deploy/demo.env` (git-ignored) the first time,
2. finds this computer's private Wi-Fi/LAN address (10/8, 172.16/12 or 192.168/16)
   and refuses to continue if there is none,
3. builds and starts the container with the port published **only on that address**,
4. waits for `/health/live` and prints the address and token.

Then, on the phone: **open the app → parent area → Development service**, enter
the printed *Server address* (for example `http://192.168.1.20:8000`) and
*Operator token*, and tap **Connect**. Quests, Style and Talk then use the server.
The app keeps the token in memory only; enter it again after relaunching.

Options:

| Need | Linux / macOS | Windows |
|------|---------------|---------|
| Emulator or this computer only (`127.0.0.1`) | `--local` | `-Local` |
| A fresh token | `--new-token` | `-NewToken` |
| A specific address | `DEMO_BIND=192.168.1.20 bash deploy/start-demo.sh` | `$env:DEMO_BIND='192.168.1.20'` first |
| Another port | `DEMO_PORT=8010 …` | `$env:DEMO_PORT='8010'` first |

With `--local`, an Android emulator uses `http://10.0.2.2:8000`, and a USB phone
can use `http://127.0.0.1:8000` after `adb reverse tcp:8000 tcp:8000`.

## Stop

```bash
docker compose down
```

## If the phone cannot connect

- Check the phone's browser can open `http://<address>:8000/health/live` and
  shows `{"status":"ok"}`.
- **Windows:** allow Docker Desktop (or the port) through Windows Defender
  Firewall for **private** networks only, and make sure the Wi-Fi profile is
  *Private*, not *Public*.
- Some routers isolate clients ("AP/client isolation"); use another network or
  the `--local` + `adb reverse` route.
- `docker compose logs api` shows startup errors. Access logs are off on purpose.

## What the container does and does not do

- Image: `python:3.10-slim`, only `pyproject.toml`, `constraints-dev.txt` and
  `src/` are copied. No corpus, model, token or private data is baked in.
- Runs as an unprivileged user, read-only filesystem, all capabilities dropped,
  `no-new-privileges`, one worker, `--no-access-log`.
- `COMPANION_DEMO_MODE=true` and `COMPANION_RAG_ENABLED=false` are fixed in the
  compose file; the API refuses to start without a 24+ character token.
- **Do not** publish the port to the internet, port-forward it on a router, or
  put it behind a public tunnel. The token is a local operator guard, not
  authentication.
- The speech service (Dua-a_stt) is not part of this setup: it needs an NVIDIA
  GPU, private model weights and data, and F5-TTS is licensed non-commercial.
