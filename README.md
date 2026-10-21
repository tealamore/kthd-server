# JITAI backend

Small Flask + SQLite API with three endpoints: save consent, handle an
intervention opportunity (server picks the arm), and record the reward.

## Run locally

```bash
pip install -r requirements.txt
python wsgi.py                      # http://localhost:8000
python -m unittest discover tests   # 13 tests
```

The database file is created at `data/jitai.db` (change with `DATABASE_PATH`).

## Run with Docker and test from your phone

Needs Docker Desktop (Windows/Mac) or Docker Engine (Linux).

```bash
docker compose up --build        # add -d to run in the background
```

The server runs at `http://localhost:8000` with API key `devkey` and admin
key `devadmin`. To use other keys:
`JITAI_API_KEY=abc ADMIN_KEY=xyz docker compose up --build`
(in Windows PowerShell, set them with `$env:JITAI_API_KEY="abc"` first).

The database is kept in a Docker volume, so it survives restarts and
rebuilds. Useful commands:

```bash
docker compose logs -f                                  # watch requests
docker compose run --rm api python -m unittest discover tests
curl -H "X-Admin-Key: devadmin" http://localhost:8000/admin/backup -o backup.db
docker compose down -v                                  # stop AND wipe the database
```

### Point your phone at it

1. **Find your PC's local IP address.**
   - Windows: run `ipconfig` and look for *IPv4 Address* under your Wi-Fi
     adapter (e.g. `192.168.1.23`).
   - Mac: `ipconfig getifaddr en0`
   - Linux: `hostname -I`
2. **Test it from the phone's browser:** open
   `http://192.168.1.23:8000/health`. You should see `{"status": "ok"}`.
3. **Set the app's server URL** to `http://192.168.1.23:8000` and send
   `X-API-Key: devkey`.

If step 2 doesn't load:
- **Firewall.** Windows may ask to allow Docker the first time. Allow it
  on *Private* networks. If you missed the prompt, allow inbound TCP port
  8000 in Windows Defender Firewall. Also make sure Windows thinks your
  Wi-Fi is a *Private* network, not *Public*.
- **Wrong network.** The phone has to be on the same Wi-Fi as the PC, not
  mobile data, a guest network, or a VPN.
- **University or office Wi-Fi** (eduroam and similar) often blocks devices
  from talking to each other. Use a home network, or the tunnel below.
- **The IP changed.** Home routers can hand out a new IP after a reboot.
  Re-check step 1.

### Plain HTTP and your app

This local setup is `http://`, not `https://`, and phones block plain HTTP
in apps by default:
- **Android** (9+): allow cleartext traffic for debug builds only, e.g.
  `android:usesCleartextTraffic="true"` in a debug manifest or a
  network-security config. Keep it out of release builds.
- **iOS**: App Transport Security may block it. Add an ATS exception for
  development (e.g. `NSAllowsLocalNetworking`). iOS 14+ also asks the user
  for *Local Network* permission (`NSLocalNetworkUsageDescription`).

To skip all of this, or if your Wi-Fi blocks local traffic, use a free
HTTPS tunnel instead:
```bash
cloudflared tunnel --url http://localhost:8000
```
It prints an `https://….trycloudflare.com` URL that works from any phone on
any network while the command is running. Install `cloudflared` from
Cloudflare first. Anyone with that URL can reach your server, so keep the
API key set.

## Settings (environment variables)

| Variable        | Default         | Meaning |
|-----------------|-----------------|---------|
| `DATABASE_PATH` | `data/jitai.db` | Where the SQLite file lives. Must be on a persistent disk in production. |
| `JITAI_API_KEY` | *(empty)*       | If set, every request except `/health` and `/admin/*` needs header `X-API-Key: <value>`. Set it in production. |
| `ADMIN_KEY`     | *(empty)*       | Turns on `GET /admin/backup` (header `X-Admin-Key: <value>`). Keep it off the phone. |
| `SQLITE_JOURNAL_MODE` | `DELETE`  | Leave as is on PythonAnywhere (network disk). `WAL` is only safe on a local disk. |
| `PORT`          | `8000`          | Port for `python wsgi.py`. |

## API

All bodies are JSON. Timestamps (`occurred_at`) are optional ISO-8601 strings
from the phone. The server also stamps its own `received_at` in UTC.

### `POST /consent`
```json
{ "participant_id": "p1", "consented": true, "consent_version": "v1.0",
  "occurred_at": "2026-10-21T09:00:00-04:00" }
```
→ `201` with `consent_id`. Each call adds a row and nothing is overwritten.
To record a withdrawal, send `"consented": false`. The participant's latest
row decides whether they can get decisions.

### `POST /opportunity`
```json
{ "participant_id": "p1",
  "context": { "steps_last_hour": 120, "location": "home" },
  "available": true,
  "client_decision_id": "a-uuid-generated-on-the-phone",
  "occurred_at": "2026-10-21T10:00:00Z" }
```
→ `201`
```json
{ "decision_id": "…", "arm": "intervention", "probability": 0.5,
  "available": true, "policy_version": "uniform-v1", "received_at": "…" }
```
- `context` can hold anything. It's stored as JSON.
- `available: false` means the phone shouldn't randomize, for example while
  the user is driving. You get the control arm with probability 1.
- `403` means the participant hasn't consented or has withdrawn.
- `client_decision_id` is optional but recommended. If the phone retries
  after a timeout, sending the same id gives back the same decision (`200`)
  without a second randomization.
- **Save `decision_id` on the phone.** You need it to send the reward.

### `POST /reward`
```json
{ "decision_id": "…", "reward": 1.0, "occurred_at": "…" }
```
→ `201`. Send this for every decision, whatever arm was picked (including
`no_intervention` and unavailable decisions). `404` means an unknown
decision. `409` means a reward was already recorded for it.

### `GET /health`
→ `{"status": "ok"}`. Doesn't need the API key.

### `GET /admin/backup`
Downloads a consistent copy of the whole database, safe even while the app
is writing. Needs header `X-Admin-Key`. If `ADMIN_KEY` isn't set, the
endpoint is off (`404`).
```bash
curl -H "X-Admin-Key: YOUR_ADMIN_KEY" https://YOURNAME.pythonanywhere.com/admin/backup -o backup.db
```

## Changing arms or the policy

Edit `app/policy.py`. `ARMS` holds the arm names and their probabilities.
`choose_arm()` makes the pick and `update()` runs after each reward, which is
where a bandit learning step goes. Every decision stores the probability and
`POLICY_VERSION`, so you can still analyze the data after changing the policy.

## Getting the data out

```bash
python export_csv.py data/jitai.db decisions.csv
```
This gives one row per decision with its reward. Context fields become
`ctx_*` columns.

## Deploying to PythonAnywhere

Below, replace `YOURNAME` with your PythonAnywhere username.

1. **Make two secret keys** on your own computer, running this twice:
   `python -c "import secrets; print(secrets.token_urlsafe(32))"`.
   The first is the API key, which goes in the phone app. The second is the
   admin key, which only you keep.
2. **Upload the code.** On the **Files** tab, upload `jitai-backend.zip`
   into `/home/YOURNAME/`.
3. **Unzip it and install the packages.** Open a **Bash console** from the
   Consoles tab and run:
   ```bash
   unzip jitai-backend.zip
   mkdir -p ~/jitai-data
   mkvirtualenv --python=python3.13 jitai
   pip install -r ~/jitai-backend/requirements.txt
   cd ~/jitai-backend && python -m unittest discover tests
   ```
   (If 3.13 isn't offered, use the newest Python 3.10 or later and pick that
   same version in step 4.)
4. **Create the web app.** On the **Web** tab, click *Add a new web app* →
   *Manual configuration* → Python 3.13. Don't pick "Flask"; that option
   generates a starter app you don't need.
5. **Point it at the virtualenv.** On the Web tab, under *Virtualenv*,
   enter `jitai`.
6. **Edit the WSGI file.** On the Web tab, click the *WSGI configuration
   file* link, delete **everything** in it, and paste:
   ```python
   import os, sys

   os.environ["DATABASE_PATH"] = "/home/YOURNAME/jitai-data/jitai.db"
   os.environ["JITAI_API_KEY"] = "PASTE_API_KEY_HERE"
   os.environ["ADMIN_KEY"] = "PASTE_ADMIN_KEY_HERE"

   sys.path.insert(0, "/home/YOURNAME/jitai-backend")
   from wsgi import app as application
   ```
   Save it.
7. **Turn on HTTPS only.** On the Web tab, switch on *Force HTTPS*.
8. **Reload and check.** Click the green *Reload* button, then open
   `https://YOURNAME.pythonanywhere.com/health`. It should show
   `{"status": "ok"}`. If it doesn't, the *Error log* link on the Web tab
   shows why.

Point the phone app at `https://YOURNAME.pythonanywhere.com` and send
`X-API-Key` on every request.

### During the study

- **The day the study starts:** on the Web tab, click *Run until 1 month
  from today*. Free web apps stop after a month without this.
- **Every day:** download a backup with the curl command under
  `GET /admin/backup` and keep the copies. Run `export_csv.py` on a
  downloaded copy, not the live file.
- **Don't open the live database file from a PythonAnywhere console while
  the study is running.** Consoles run on different machines from the web
  app, and SQLite on a shared network drive is where locking problems
  come from. Use the backup endpoint instead.
- **After changing code or the WSGI file:** click *Reload* on the Web tab.

### Other hosts

On a host with a local persistent disk (Railway or Fly.io with a volume, or
a VM), set `DATABASE_PATH` to a path on that disk, optionally set
`SQLITE_JOURNAL_MODE=WAL`, and start with
`gunicorn -w 2 -b 0.0.0.0:$PORT wsgi:app`. Hosts that wipe the disk on
restart (Cloud Run, Render free) will lose the database.
