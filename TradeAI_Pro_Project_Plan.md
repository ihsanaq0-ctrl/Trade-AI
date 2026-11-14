# **TradeAI Pro** 

Complete Project Plan & Technical Architecture 

An AI-Powered Forex Trading Platform with Automated Strategy Bots 

Prepared for: Ihsan Ullah 

Broker: Exness (MT5) | Stack: React, Supabase, FastAPI, MetaTrader5 Python 

## **Table of Contents** 

1. Executive Summary 

2. Project Vision & Goals 

3. Complete System Architecture 

4. Broker Connectivity: Two Paths Explained in Depth 

5. Technology Stack Breakdown 

6. Full Development Workflow 

7. Database Schema Overview 

8. The Five AI Trading Bot Strategies 

9. Backtesting Framework 

10. Phase-by-Phase Roadmap & Current Status 

11. Monetization & Licensing Plan 

12. Risk, Legal & Regulatory Considerations 

13. Recommended Next Steps 

## **1. Executive Summary** 

TradeAI Pro is a professional-grade forex trading platform, conceptually similar to MetaTrader 5, extended with a fully automated AI trading engine. The platform allows a user to connect their real broker account (Exness, MT5), choose from five distinct algorithmic trading strategies, configure risk parameters, and let the system open and close trades automatically without manual intervention. The long-term plan is to package this as a paid product, with a starting price point of $100, sold to retail forex traders who want algorithmic execution without writing code themselves. 

The project is being built with a zero-budget-first philosophy: every tool selected in the early phases (Supabase, Vercel, Railway, GitHub, the MetaTrader5 Python library) has a genuinely free tier suitable for development and early testing. Paid infrastructure (a Windows VPS, a cloud broker-bridge service, payment processing fees) is deferred until the product has real users and revenue to justify the cost. 

As of this document, the frontend web application is functionally complete across all core pages (Login/Register, Dashboard, Markets, AI Bots, Analytics, Accounts, Settings), Supabase authentication and database storage are working, and a Python FastAPI backend has been built and successfully connects to a local MetaTrader 5 terminal. The five trading strategies have been implemented in Python as a first working draft, along with a backtesting engine to evaluate them against real historical data. None of the strategies have yet been proven profitable — that validation step is the most important remaining piece of work before any bot should be allowed to trade live money. 

## **2. Project Vision & Goals** 

The core idea is to give a retail trader the experience of a professional algorithmic trading desk, packaged into a simple, guided web and mobile interface. Specifically: 

- Let a user connect their own broker account (starting with Exness/MT5) using familiar login credentials — no coding or manual setup required on their end. 

- Offer five distinct, pre-built AI trading strategies, each based on a recognizable retail trading methodology (Smart Money Concepts, ICT, Market Mirror Concept, Support & Resistance, and Price Action). 

- Allow full control over risk per bot: trading pair, timeframe, lot size, stop loss, take profit, maximum daily loss, and maximum concurrent trades. 

- Provide transparent analytics: win rate, profit factor, trade history, and an equity curve, so the user always knows how each bot is actually performing. 

- Package the whole platform as a one-time or subscription-paid product, priced from $100, targeting traders who want automation without needing to build it themselves. 

### **Explicit non-goals (for now)** 

To keep the project achievable, the following are intentionally out of scope for the first version: 

- Supporting every broker and platform (MT4, cTrader, proprietary broker platforms) — MT5 with Exness is the first and only target. 

- Guaranteeing profitability of any strategy — the platform provides tools and transparency, not investment promises. 

- Full institutional-grade infrastructure (co-located servers, FIX API execution) — that level of infrastructure is not economically justified at this stage. 

## **3. Complete System Architecture** 

The platform is composed of four cooperating layers. Understanding how they hand off responsibility to each other is essential context for both you and any developer or AI agent working on the codebase. 

### **Layer 1 — Frontend (React + Vite)** 

A single-page React application built with Vite, using React Router for navigation. It handles all visual interaction: login/registration, the trading dashboard, market price browsing with live charts, the AI bot control panel, analytics and trade history, broker account management, and user settings. It communicates with Supabase directly for authentication and data storage, and with the FastAPI backend for anything that requires talking to the broker (connecting an account, fetching live balances, placing trades). 

### **Layer 2 — Supabase (Auth + Database)** 

Supabase provides two services in this architecture: user authentication (email/password, with email verification enabled, and Google OAuth planned) and a Postgres database that stores user profiles and connected broker accounts. Row Level Security (RLS) policies ensure each user can only see and modify their own data — this is enforced at the database level, not just in the frontend, which matters for real security rather than security theater. 

### **Layer 3 — FastAPI Backend (Python)** 

A Python backend built with FastAPI exposes a REST API that the frontend calls whenever it needs to interact with a real broker account: connecting an account, fetching account info and open positions, and opening or closing trades. This layer is also where the AI bot engine will eventually live — a scheduler that periodically fetches fresh candle data, feeds it into the active strategy bots, and executes any resulting trade signals automatically. 

### **Layer 4 — Broker Connectivity (MT5)** 

This is the layer responsible for actually talking to Exness. It is covered in full detail in the next section, since there are two genuinely different ways to implement it with very different cost and scalability trade-offs. 

## **4. Broker Connectivity: Two Paths Explained in Depth** 

This is the single most important architectural decision in the whole project, because it determines both your near-term cost and your ability to scale to many users later. There are two genuinely different ways to bridge your application to a real MT5 broker account. 

### **Path A — Broker** → **MT5 Terminal** → **TradeAI App** 

This is the approach currently implemented. The free, open-source **MetaTrader5** Python library is used on the backend. It does not talk to the broker over the internet directly — instead, it communicates with a MetaTrader 5 desktop terminal application that must be installed and running (and logged into the broker account) on the same machine as the Python backend. 

#### **How it works, step by step:** 

- The user enters their MT5 login, password, and server name into the TradeAI Pro Accounts page. 

- The FastAPI backend calls `mt5.initialize()` to start the local MT5 terminal process. 

- The backend calls `mt5.login()` with the user's credentials, which authenticates against the broker's MT5 server through the terminal. 

- Once logged in, the Python library can read account balance, equity, and open positions, and can send new trade orders — all routed through the terminal to the broker. 

#### **Real constraints of this approach:** 

- **Cost:** Genuinely free. No subscription, no per-account fee, no API billing. 

- **Infrastructure requirement:** A machine (initially your own PC, eventually a Windows VPS) must be running the MT5 terminal 24/7 for the bots to trade continuously. 

- **Single-session limitation:** The MetaTrader5 Python library is generally built around controlling one logged-in terminal session at a time. For your own personal use, this is not a problem. For a multi-user SaaS product where many different customers each connect their own separate broker account, this becomes the central scaling bottleneck — you would need one MT5 terminal instance running per user (or per small batch of users) on your server, which consumes real memory and CPU per account. 

- **Practical ceiling:** This architecture is well suited for you personally, for a small beta group, or for a desktop/local-installation product where each user runs the whole stack (including their own MT5 terminal) on their own machine. It is not well suited to a centralized cloud SaaS with hundreds of simultaneous users. 

### **Path B — Broker** → **TradeAI App Directly (No Local Terminal)** 

This is the architecture that was originally attempted using MetaAPI, and it is the better long-term design for a true multi-user cloud SaaS product — but it comes with an unavoidable, honest catch: **the MT5 protocol itself is proprietary to MetaQuotes** . Brokers do not expose a public, free API that lets an 

outside application connect directly the way a REST API for, say, a weather service would. There is no free version of this path — every practical way to achieve it costs money or requires running a terminal somewhere regardless. 

#### **The three real ways to achieve Path B:** 

- **A paid cloud bridge service (e.g. MetaAPI):** These companies run MT5 terminals in their own cloud infrastructure on your behalf and expose a clean REST/WebSocket API to you. This is the cleanest architecture, but it requires payment even to deploy a demo account, as was discovered during initial testing. 

- **The broker's own institutional API:** Some large brokers offer FIX API or REST API access, but this is typically reserved for institutional or high-volume accounts, and Exness does not currently offer this to ordinary retail users. 

- **A custom Expert Advisor (EA) bridge:** You can write an MT5 Expert Advisor (in MQL5) that runs inside a terminal and pushes account/price data out to your backend via HTTP webhook, and receives trade instructions back the same way. This still requires an MT5 terminal to be running somewhere — it does not eliminate the terminal requirement, it just automates the connection between that terminal and your backend, and requires MQL5 programming in addition to Python. 

### **Recommendation** 

Stay on **Path A** for development, personal use, and an initial small beta group. It is free, it is already working, and it is sufficient to prove out the strategies and the product experience. Revisit **Path B** — specifically, budgeting for a paid bridge service — once the product has real, paying users and the monthly bridge cost is comfortably justified by revenue. Building Path B prematurely would mean paying ongoing infrastructure costs before there is any income to offset them. 

## **5. Technology Stack Breakdown** 

|**Layer**|**Technology**|**Purpose**|**Cost**|
|---|---|---|---|
|Frontend|React + Vite|Web application UI|Free|
|Routing|React Router|Page navigation|Free|
|Charts|lightweight-charts, Recharts|Candlestick + analytics charts|Free|
|Icons|lucide-react|UI iconography|Free|
|Auth + DB|Supabase|User accounts, broker account storage|Free tier|
|Backend|Python + FastAPI|REST API, bot engine|Free|
|Broker link|MetaTrader5 (Python)|Local MT5 terminal connection|Free|
|Strategy logic|pandas, numpy|Candle analysis, signal generation|Free|
|Version control|Git + GitHub|Source code storage|Free|
|Hosting (frontend)|Vercel|Deploys the web app|Free tier|
|Hosting (backend)|Railway|Deploys the Python API|Free tier|
|Payments|Gumroad|Sells the product, Pakistan-supported|Per-sale fee only|



## **6. Full Development Workflow** 

This section describes the end-to-end journey of a single trade, from the moment a user connects their account to the moment a bot places an order — tying together every layer described above. 

#### **Step 1 — Registration & Login** 

The user registers with an email and password on the TradeAI Pro web app. Supabase Auth creates the account and sends a verification email. Once verified, the user logs in and a session is established; the React app listens for this session and unlocks the protected dashboard routes. 

#### **Step 2 — Connect a broker account** 

From the Accounts page, the user enters an account nickname, their broker name (Exness), MT5 login number, password, and server name. The frontend sends this to the FastAPI backend's `/account/connect` endpoint. 

#### **Step 3 — Backend authenticates with MT5** 

The backend calls the MetaTrader5 Python library to initialize a connection to the locally running MT5 terminal and log in with the supplied credentials. On success, it retrieves balance, equity, and other account details and returns them to the frontend, which saves a record (excluding the plaintext password in the database) into the Supabase `accounts` table. 

#### **Step 4 — Selecting a strategy bot** 

On the AI Bots page, the user selects one of the five strategies (Smart Money, Mirror, Classic, Full Confluence, or Scalp Mode) and configures pair, timeframe, lot size, stop loss, take profit, and risk limits, then presses Start. 

#### **Step 5 — The bot engine runs continuously** 

A scheduler process (planned, not yet built) wakes up on every new candle close for the selected timeframe, pulls the latest OHLCV data from MT5 via the backend, and feeds it into the selected strategy's `generate_signal()` function. 

#### **Step 6 — Trade execution** 

If the strategy returns a valid signal, the backend sends a market order to MT5 via `/trade/open` , which is routed through the terminal to the Exness broker server and executed on the live or demo account. 

#### **Step 7 — Monitoring & analytics** 

Open positions and closed trade history are pulled back from MT5 and displayed on the Dashboard and Analytics pages — currently these pages show placeholder/sample data and are pending a final wiring step to replace it with live data from the backend and Supabase. 

## **7. Database Schema Overview** 

### **users table** 

|**Column**|**Type**|**Notes**|
|---|---|---|
|id|uuid|Matches Supabase auth.users id|
|name|text|Full name|
|email|text|Login email|
|plan|text|Subscription tier, default 'free'|
|created_at|timestamptz|Account creation time|



### **accounts table** 

|**Column**|**Type**|**Notes**|
|---|---|---|
|id|uuid|Primary key|
|user_id|uuid|References auth.users, RLS-protected|
|nickname / broker / login / server|text|Account identification|
|type|text|'Live' or 'Demo'|
|color|text|UI color tag|
|balance / equity / profit|numeric|Synced from MT5|
|connected|boolean|Live connection status|
|metaapi_id|text|Reserved for a future Path B bridge integration|



Row Level Security is enabled on both tables: a policy restricts every read and write on `accounts` to rows where `auth.uid() = user_id` , meaning no user can ever see or modify another user's connected broker accounts, even if they tried to manipulate frontend requests directly. 

## **8. The Five AI Trading Bot Strategies** 

Each bot is implemented as an independent Python class that accepts historical candle data (OHLCV: open, high, low, close, volume) and returns either a trade signal (direction, entry, stop loss, take profit) or nothing, if no valid setup currently exists. Below is a full explanation of the logic behind each one. 

Important honest note: these are discretionary, human-designed chart-reading concepts translated into rigid code rules. They do not have a single universally agreed definition, and none of them carry peer-reviewed statistical proof of an edge. Treat every strategy below as a hypothesis to be backtested, not a proven system. 

### **Bot 1 — Smart Money Mode (SMC + ICT) (Medium risk)** 

This strategy tries to trade in the direction institutional ('smart money') order flow is believed to move. It first determines market structure by comparing recent swing highs and lows: a sequence of higher highs and higher lows signals an uptrend, lower highs and lower lows signal a downtrend. It then looks for a Break of Structure (BOS) — a candle that closes beyond the most recent swing point in the trend direction, confirming momentum. Working backward from that break, it identifies the Order Block: the last opposite-colored candle before the breakout move, which is treated as the zone where large institutional orders were likely placed. The bot waits for price to retrace back into that Order Block zone before entering, with a stop loss just beyond the zone and a take profit at the next major liquidity point (an untouched swing high or low). A minimum risk-to-reward filter (3:1 by default) ensures the bot only takes trades where the potential reward clearly outweighs the risk. 

### **Bot 2 — Mirror Mode (MMC + Price Action) (Medium risk)** 

This strategy is based on the idea that price often repeats the size and duration of its own prior moves — a kind of self-similarity or symmetry. The bot identifies the most recently completed price swing (from one confirmed turning point to the next), measures how large that move was in price and how many candles it took, and projects a 'mirror' of the same size and duration from the end point. It also calculates the 50% equilibrium (midpoint) of the swing as a secondary zone of interest. The bot only acts once price reaches either the mirror projection zone or the equilibrium zone, and even then only if a confirming Price Action candle appears — a Pin Bar (long rejection wick) or an Engulfing candle. Without that candle confirmation, no trade is taken, regardless of how well price aligns with the projected zone. This is the most speculative of the five concepts and should be treated with extra skepticism during backtesting. 

### **Bot 3 — Classic Mode (SNR + Price Action) (Low risk)** 

The most traditional and well-established of the five approaches. The bot scans historical swing highs and lows, groups nearby price levels into clusters (zones), and counts how many times price has touched each zone — more touches indicate a stronger, more respected level. It also identifies 'flip zones', where an old resistance level that was broken is now expected to act as new support (and vice versa). A trade is only considered when current price is sitting inside one of these validated zones, and even then only with a confirming rejection candle (Pin Bar, Engulfing, or a clear Doji for context). Because support and resistance trading has decades of precedent among both retail and institutional traders, this is a 

reasonable strategy to prioritize first in backtesting. 

### **Bot 4 — Full Confluence Mode (Low risk (fewer trades))** 

Rather than introducing new logic, this strategy combines Bots 1, 2, and 3 internally and adds two further filters: it only operates during ICT 'Kill Zone' hours (London 2AM-5AM EST and New York 7AM-10AM EST, historically higher-volume trading windows), and it checks that a simple 'daily bias' (derived from where today's session opened relative to yesterday's price range) agrees with the trade direction. A trade signal only fires when the Smart Money, Classic, and Mirror bots all agree on direction simultaneously, the timing is inside a Kill Zone, and the daily bias does not contradict the trade. This bot is deliberately built to trade far less often than the others — the trade-off is fewer signals in exchange for each one being backed by multiple independent forms of confirmation. It is not guaranteed to be more accurate simply because it demands more agreement; that must still be measured. 

### **Bot 5 — Scalp Mode (ICT Kill Zones + Price Action) (High risk)** 

Designed for fast, short-duration trades, active only during the London and New York Kill Zone hours. At the start of a session, the bot watches for a 'Judas Swing' — an initial fast move in one direction that is designed to trap early traders, typically followed by a sharp reversal. Once identified, the bot calculates a Fibonacci retracement of that swing and waits for price to pull back into the 62%-79% zone, known in ICT terminology as the Optimal Trade Entry (OTE). A quick Price Action confirmation candle on a fast timeframe (M1 or M5) triggers entry, with a tight stop loss and a comparatively small take profit target, and a hard cap on the number of trades allowed per session to prevent overtrading. 

## **9. Backtesting Framework** 

Before any strategy is allowed to trade real money, it must be tested against real historical price data to measure whether it has any actual statistical edge. A backtesting engine has been built for exactly this purpose, with the following design: 

- **Walk-forward simulation:** at every step, the engine only shows each bot data up to the current point in history — never future candles — which avoids look-ahead bias and mirrors how the bot would behave in real, live conditions. 

- **Trade simulation:** once a bot fires a signal, the engine steps forward candle-by-candle to determine whether stop loss or take profit is hit first, and records the outcome. 

- **Metrics reported per strategy:** total trades, win rate, profit factor (gross profit divided by gross loss), average risk-to-reward achieved, and maximum drawdown, all measured in R-multiples (units of risk) so results are independent of lot size and account balance. 

- **Cross-symbol and cross-period testing:** the same strategy should be tested across multiple pairs (EURUSD, GBPUSD, XAUUSD) and multiple date ranges — a strategy that only performs well on one pair over one period is far more likely to be overfit or lucky than genuinely repeatable. 

### **How to interpret results** 

- A profit factor above roughly 1.3-1.5, combined with a reasonably large sample size (50 or more trades), is a meaningful signal worth further investigation. 

- A profit factor at or below 1.0 means the strategy loses money over the test period and should not be deployed live in its current form. 

- Fewer than roughly 30 trades in a backtest is not enough data to trust the reported win rate — the sample is too small to distinguish genuine edge from random variance. 

- It is normal, and expected, for some or even most of the five strategies to underperform in backtesting. That is useful information, not a failure of the code — it tells you where to focus improvement effort or which strategies to retire. 

## **10. Phase-by-Phase Roadmap & Current Status** 

|**Phase**|**Status**|**Contents**|
|---|---|---|
|1. Tools &amp; Accounts|Complete|Windsurf, Node.js, Python, Git, GitHub, Supabase, Vercel, Railway, MetaAPI, Exness,|
|2. Frontend UI|Complete|Login/Register, Dashboard, Markets (with live charts), AI Bots panel, Analytics, Accou|
|3. Auth &amp; Database|Complete|Supabase email/password auth with verification, users and accounts tables with Row|
|4. Broker Connection|In progress|FastAPI backend built; MetaTrader5 Python library integrated as the free connection p|
|5. Strategy Engine|Code delivered,|untested<br>All five bot classes implemented in Python; backtesting engine built; no strategy has y|
|6. Bot Scheduler|Not started|An automated loop to run active bots on every new candle and execute resulting trade|
|7. Live Analytics|Not started|Replace placeholder Analytics/Dashboard data with real trade history and equity curve|
|8. Payments|Not started|Gumroad checkout integration; unlock the app on successful purchase|
|9. Mobile/Desktop Packagi|ngNot started|Wrap the web app with Capacitor to ship Android, iOS, and Desktop builds from one c|



## **11. Monetization & Licensing Plan** 

The current plan is to sell TradeAI Pro as a paid product starting at $100, using Gumroad as the payment processor since it supports Pakistan and digital software products without the restrictions encountered with Stripe and Paddle during setup. 

- **Pricing model:** a one-time purchase unlocking the platform, with a possible future monthly subscription tier for ongoing bot access and updates. 

- **Licensing enforcement:** after successful Gumroad payment, a webhook updates the user's `plan` field in Supabase to a paid tier, which the frontend checks to unlock the Bot and Accounts pages. 

- **Trial strategy:** consider a limited free trial (e.g. Classic Mode only, or a capped number of days) to let prospective buyers see real bot behavior before purchasing, which builds trust given the product's nature. 

## **12. Risk, Legal & Regulatory Considerations** 

This section is general awareness, not legal advice. Consult a qualified lawyer in your jurisdiction before selling automated trading software commercially. 

- **No performance guarantees:** never market the bots as guaranteed to profit. Backtested or even live-forward results do not guarantee future performance, and forex trading carries genuine risk of loss. 

- **Financial services licensing:** in many countries, software that manages trades on a user's behalf can be interpreted as a financial service requiring licensing, especially if marketed as an investment product rather than a tool. Research the specific regulatory requirements in Pakistan and in any country where the product will be sold. 

- **Clear disclaimers:** every page of the product, and its marketing materials, should state plainly that this is not financial advice, that trading carries risk of loss, and that past or backtested performance does not guarantee future results. 

- **Credential security:** broker passwords are transmitted to connect accounts. These must never be stored in plaintext, should be encrypted at rest if stored at all, and ideally are used only transiently to establish a session rather than persisted long-term. 

## **13. Recommended Next Steps** 

In priority order, the most valuable next actions are: 

1. Finish testing the live MT5 terminal connection end-to-end with a real Exness account, confirming account info and open positions sync correctly. 

2. Run the backtesting engine against real historical data for all five strategies, across at least three symbols and multiple time periods, before writing any more strategy code. 

3. Based on backtest results, refine or discard underperforming strategies rather than assuming all five are equally viable. 

4. Build the bot scheduler that runs strategies automatically on live data and executes trades — only after backtesting gives a reasonable basis for trust. 

5. Replace placeholder data in the Dashboard and Analytics pages with real data sourced from Supabase and the MT5 connection. 

6. Integrate Gumroad payments and gate access to the Bots and Accounts pages behind a paid plan. 

7. Consult a lawyer regarding financial services regulations before any public commercial launch. 

This document reflects the project's status and plan as of the conversation it was generated from. It is a living plan and should be revisited as strategies are backtested and priorities shift. 

