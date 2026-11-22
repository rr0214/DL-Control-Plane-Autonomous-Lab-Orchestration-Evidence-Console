# Deploy to Render

The repo has a Render Blueprint (`render.yaml`) that creates three web services on the Starter plan:

| Service | What it runs | Public URL |
|---|---|---|
| `sdl-console-rr` | Next.js console | https://sdl-console-rr.onrender.com |
| `sdl-api-rr` | FastAPI backend, SQLite on a disk | https://sdl-api-rr.onrender.com |
| `sdl-phoenix-rr` | Arize Phoenix trace viewer, on a disk | https://sdl-phoenix-rr.onrender.com |

**Cost:** about $21 a month for the three Starter services ($7 each), plus about $0.50 a month for the two 1 GB disks. Check Render's pricing page for current numbers.

## Before you start

* A Render account connected to GitHub, with access to this repo.
* The `deploy` branch pushed to GitHub.
* Your Anthropic API key.
* A shared password for the demo. Anyone who opens the console is asked for it once per browser tab.

## Click steps

1. Go to https://dashboard.render.com and click **New**, then **Blueprint**.
2. Under **Connect a repository**, pick `DL-Control-Plane-Autonomous-Lab-Orchestration-Evidence-Console`. If it is not listed, click **Configure GitHub** and give Render access to it.
3. Set **Branch** to `deploy`. Give the Blueprint a name, for example `sdl-control-plane`.
4. Render reads `render.yaml` and lists the three services and two disks. Check the names are `sdl-api-rr`, `sdl-console-rr` and `sdl-phoenix-rr`.
5. Render asks for the two secret values:
   * `ANTHROPIC_API_KEY`: paste your key.
   * `SDL_ACCESS_PASSWORD`: type the shared password.
6. Click **Apply** (or **Deploy Blueprint**). The first deploy takes about 5 to 10 minutes. The backend is ready when its health check at `/health` passes.
7. Open each service in the dashboard and check that the URL at the top matches the table above.
8. Open https://sdl-console-rr.onrender.com, enter the password, and click **Plan next batch** to make one live run.

### If a URL is different

Render adds a short suffix when a name is already taken, for example `sdl-api-rr-x7k2.onrender.com`. If that happens, open the service, go to **Environment**, and fix the value that points at it:

* Backend URL changed: update `NEXT_PUBLIC_API_URL` on `sdl-console-rr`, then click **Manual Deploy**, then **Deploy latest commit** (the console bakes this value in when it builds).
* Console URL changed: update `SDL_ALLOWED_ORIGINS` on `sdl-api-rr`.
* Phoenix URL changed: update `PHOENIX_COLLECTOR_ENDPOINT` and `PHOENIX_PUBLIC_URL` on `sdl-api-rr`, and
  `NEXT_PUBLIC_PHOENIX_URL` on `sdl-console-rr`, then **Manual Deploy**, **Deploy latest commit** on the console (the
  header's **Phoenix traces** link is baked in when it builds). Set `NEXT_PUBLIC_PHOENIX_URL` to an empty value to
  hide that link.

### If traces do not show up

The backend checks for Phoenix once, when it starts. If Phoenix was still starting at that moment, tracing stays off and the app keeps working without it. Open `sdl-api-rr`, click **Manual Deploy**, then **Restart service**.

## Seed Phoenix with the 20 test cases

This runs the 20 front-half cases on your own machine and sends their traces to the hosted Phoenix, then scores them with the two code checks. It needs `ANTHROPIC_API_KEY` in your local `.env`. Values set on the command line win over `.env`.

```bash
cd backend
export PHOENIX_COLLECTOR_ENDPOINT=https://sdl-phoenix-rr.onrender.com
export PHOENIX_PUBLIC_URL=https://sdl-phoenix-rr.onrender.com
.venv/bin/python -m app.front_half_runner
.venv/bin/python -m app.front_half_evals
```

The traces land in the Phoenix project `sdl-front-half`, with the check results attached as annotations.

**Cost:** about $0.20 in Claude calls. The last run made 21 calls for about $0.18. The 5 impossible-target cases stop before any AI call. The runner stops if spend reaches $2 (change it with `--max-usd`).

Optional, free (no AI calls): `.venv/bin/python -m app.seed_phoenix` with the same two variables set adds the six curated example traces.

## Things to know

* **Phoenix has no password.** Anyone with the Phoenix URL can read the traces, which include prompts and AI replies. Only demo data goes there. Turning on Phoenix's own login is a later step and would also need an API key for the backend.
* **The shared password protects the API**, not the page itself. Every API route except `/health` needs it, including `/docs`.
* **Daily run limit.** The backend accepts at most `SDL_DAILY_RUN_LIMIT` plan runs per day (25 in `render.yaml`), counted in UTC and reset at midnight UTC. Each run can call Claude, about $0.01 to $0.02, so 25 runs cost at most about $0.50 a day. After that, **Plan next batch** shows "Daily run limit reached" until the next day. Reviews and releases are not counted. To change it, edit `SDL_DAILY_RUN_LIMIT` on `sdl-api-rr` under **Environment** (0 turns the limit off). The count lives on the backend's disk, so restarts and **Reset Demo** do not clear it.
* Secrets stay in the Render dashboard. They are never written to `render.yaml` or the repo.
* Local use is unchanged. With no `SDL_ACCESS_PASSWORD`, `SDL_ALLOWED_ORIGINS`, `PHOENIX_PUBLIC_URL` or `SDL_DAILY_RUN_LIMIT` set, `./start.sh` works as before. With no `NEXT_PUBLIC_PHOENIX_URL`, the header's **Phoenix traces** link points at the local Phoenix (`http://localhost:6006`).
