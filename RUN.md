# How to Run — Trade-AI

## Prerequisites

- **Node.js** >= 18 (for frontend)
- **Python** >= 3.12 (for backend — **Python 3.14 won't work**, packages don't have wheels yet)
- **MetaTrader 5** installed and logged into your Exness account
- A terminal at the project root: `cd "e:\ihsan\Ihsans_Projects\Trading BOT\trading-app"`

---

## 1. Frontend (React + Vite)

```bash
# Install dependencies (first time only)
npm install

# Start the Vite dev server (default: http://localhost:5173)
npm run dev
```

Other frontend commands:
| Command | Description |
|---|---|
| `npm run build` | Production build → `dist/` |
| `npm run preview` | Preview the production build locally |
| `npm run lint` | Run oxlint |

The frontend now sends API calls to `/api/...` and Vite proxies those requests to `http://127.0.0.1:8002` during development.

---

## 2. Backend (FastAPI + MT5)

Open a **separate terminal**.

```bash
# Navigate to the backend folder
cd backend

# (Recommended) Create and activate a virtual environment
python -m venv .venv

# Activate (choose one for your shell):
source .venv/Scripts/activate    # Git Bash
# .venv\Scripts\activate         # PowerShell / cmd.exe

# Install dependencies (first time only)
pip install -r requirements.txt

# Make sure MT5 desktop is open and logged into your Exness account
# The backend connects to your local MT5 terminal to get live data and trade.

# Start the FastAPI server (default: http://localhost:8002)
uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```

API docs at [http://127.0.0.1:8002/docs](http://127.0.0.1:8002/docs) (Swagger UI)

### Docker alternative (for backend only, won't connect to local MT5)

```bash
cd backend
docker build -t tradeai-api .
docker run -p 8002:8002 tradeai-api
```

---

## 3. Run Both Simultaneously

| Terminal | Command | URL |
|---|---|---|
| **Terminal 1** (project root) | `npm run dev` | http://localhost:5173 |
| **Terminal 2** (`backend/`) | `uvicorn main:app --host 0.0.0.0 --port 8002 --reload` | http://localhost:8002 |

**Important:** MT5 Desktop must be open and logged in before starting the backend (it connects to your local terminal).

---

## 4. Environment Variables

Create `backend/.env` with:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-or-service-role-key
SUPABASE_JWT_SECRET=your-supabase-jwt-secret
CORS_ORIGINS=http://localhost:5173
# Leave VITE_API_BASE_URL unset for the default Vite proxy path.
# Set it to http://127.0.0.1:8002 only if you want to bypass the proxy.
LOG_LEVEL=INFO
```

These values are already set in the file — just make sure it exists.

---

## 5. Backtesting the Strategies

```bash
cd backend

# Quick test: 1 symbol, 1 timeframe, 30 days
python backtest.py --symbol EURUSDm --timeframe H1 --days 30

# Full multi-symbol, multi-timeframe comparison
python multi_backtest.py --symbols EURUSDm,GBPUSDm,XAUUSDm --timeframes H1,H4 --days 60 --output results.csv
```

**Make sure MT5 Desktop is logged in** before running backtests — otherwise it falls back to synthetic data (which has no real patterns and all bots will correctly return 0 trades).

---

## 6. Deploying a Bot (Live Trading)

1. Log into **MT5 Desktop** with your Exness account
2. Start the **backend** (`uvicorn main:app`)
3. Start the **frontend** (`npm run dev`)
4. Go to http://localhost:5173/bot
5. Click a strategy → configure pair/timeframe/risk → **Start**
6. The scheduler runs the strategy loop on every new candle and executes trades via MT5

To stop a bot: click **Stop** on the bot card.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `"MetaTrader5 not installed"` | Run `pip install MetaTrader5` in the backend venv |
| `"Terminal: Authorization failed"` | MT5 Desktop isn't open or not logged in — open MT5 and log into your account |
| `"Symbol EURUSD not found"` | Your broker uses different symbol names (e.g. `EURUSDm`). The backend auto-resolves this |
| `"Failed to fetch"` on login | Supabase project was paused — restore it at https://supabase.com/dashboard |
| Backend crashes on startup | Make sure `backend/.env` exists with the values from section 4 above |
| Python version errors | Use Python 3.12, NOT 3.14 (`py -3.12 -m venv .venv` on Windows) |

---

## Quick launcher (Windows)

A convenience double-clickable launcher is provided: [run_launcher.py](/E:/ihsan/Ihsans_Projects/Trading BOT/trading-app/run_launcher.py). A packaged Windows executable can be created at `dist/run.exe` (see below). The launcher does the following when run on Windows:

- Ensures Python 3.12+ is present.
- Installs Python requirements from `backend/requirements.txt` (or `backend/requirements_full.txt`) using pip.
- Runs `npm install` in the project root (requires Node.js/npm in PATH).
- Starts the backend (uvicorn) and frontend (Vite dev server) in separate console windows.
- Opens the frontend in the default browser (http://localhost:5173). If the frontend is unreachable, opens backend docs at http://localhost:8002/docs.

If Node.js/npm is not available the launcher will prompt you to install Node.js and will still attempt to start the backend.

### How to create a packaged run.exe (optional)

1. From a command prompt with Python available, install build tooling:

```powershell
cd "e:\ihsan\Ihsans_Projects\Trading BOT\trading-app"
py -3.12 -m pip install -r backend\requirements_full.txt
py -3.12 -m pip install pyinstaller
py -3.12 -m PyInstaller --onefile run_launcher.py --name run
```

2. The packaged executable will be at `dist\run.exe`. Double-click it to launch the app. The packaged exe bundles the Python runtime and the launcher but it does not embed Node.js or MetaTrader5; Node.js must still be installed on the machine for the frontend to run, and MetaTrader5 must be installed and logged in for live trading.

Notes:
- Building the exe on Windows is recommended to be done using the same Python version you intend to run the backend with (3.12).
- The launcher cannot install MetaTrader5 desktop or Node.js; it automates Python package installs and starts the two servers.
