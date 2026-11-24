//+------------------------------------------------------------------+
//|                                          PipStep_Reversal_EA.mq5 |
//|  BuyStop + SellStop pair -> step trailing SL -> reverse on SL.   |
//|  No take profit. Tick based (attach to M1 chart as requested).   |
//+------------------------------------------------------------------+
#property copyright "Ihsan Ullah"
#property version   "1.00"
#property strict

#include <Trade\Trade.mqh>

//------------------------------- INPUTS ----------------------------
input group "=== Entry / SL / Trail (all in pips) ==="
input double InpLots          = 0.01;   // Lot size
input double InpEntryPips     = 10.0;   // BuyStop / SellStop distance from price
input double InpSLPips        = 10.0;   // Initial SL distance from entry
input double InpStepPips      = 10.0;   // Trail step (profit step and SL step)
input double InpPipPrice      = 0.0;    // Pip size in PRICE units (0 = auto, see Experts log)

input group "=== Safety ==="
input double InpMaxSpreadPips = 0.0;    // Skip placing/reversing if spread above this (0 = off)
input double InpDeviationPips = 3.0;    // Max slippage for market orders (pips)
input double InpDailyLossPct  = 10.0;   // Daily loss stop (% of day-start equity)
input double InpDailyProfitPct= 20.0;   // Daily profit target (% of day-start equity)
input int    InpRetryCooldownSec = 15;  // Wait after a failed order (doubles on every failure)
input int    InpMaxBackoffSec = 1800;   // Longest wait between retries
input bool   InpDeleteOnRemove= true;   // Delete pending orders when EA is removed

input group "=== Identity ==="
input long   InpMagic         = 26110401; // Magic number
input string InpComment       = "PIPSTEP";// Order comment
input bool   InpShowPanel     = true;     // Show status panel on chart

//------------------------------- STATE -----------------------------
enum ENUM_STATE { ST_ARMED = 0, ST_IN_TRADE = 1, ST_NEED_REVERSAL = 2, ST_HALTED = 3 };

CTrade     trade;
ENUM_STATE g_state      = ST_ARMED;
double     g_pip        = 0.0;
int        g_dir        = 0;          // direction of current/last position (+1 buy, -1 sell)
int        g_nextDir    = 0;          // direction of the pending reversal
double     g_open       = 0.0;
ulong      g_posId      = 0;
datetime   g_closeStart = 0;

datetime   g_nextTry    = 0;          // earliest time for next order request
datetime   g_nextModify = 0;          // earliest time for next SL modify
datetime   g_nextClean  = 0;          // earliest time for next pending cleanup
int        g_fails      = 0;

int        g_dayKey     = 0;
double     g_dayEq      = 0.0;

int        g_reversals  = 0;
string     g_msg        = "";
datetime   g_msgTime    = 0;
datetime   g_lastPanel  = 0;

//------------------------------- HELPERS ---------------------------
void SetMsg(const string s)
  {
   if(s != g_msg || TimeCurrent() - g_msgTime >= 60)
     {
      Print("[PIPSTEP] ", s);
      g_msgTime = TimeCurrent();
     }
   g_msg = s;
  }

double NormPrice(const double p)
  {
   double ts = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   if(ts > 0.0) return NormalizeDouble(MathRound(p / ts) * ts, _Digits);
   return NormalizeDouble(p, _Digits);
  }

double MinStopDist()
  {
   long sl = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_STOPS_LEVEL);
   long fr = SymbolInfoInteger(_Symbol, SYMBOL_TRADE_FREEZE_LEVEL);
   return (double)MathMax(sl, fr) * _Point;
  }

double DetectPip()
  {
   if(InpPipPrice > 0.0) return InpPipPrice;
   string s = _Symbol;
   StringToUpper(s);
   if(StringFind(s, "XAU") >= 0 || StringFind(s, "XAG") >= 0 ||
      StringFind(s, "GOLD") >= 0 || StringFind(s, "SILVER") >= 0)
      return 0.10;                       // metals: 1 pip = 0.10 (10 pips = $1.00)
   if(_Digits == 3 || _Digits == 5)
      return 10.0 * _Point;              // normal forex pip
   return _Point;                        // 2/4 digit symbols
  }

double NormLots()
  {
   double step = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   double vmin = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double vmax = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double lots = InpLots;
   if(step > 0.0) lots = MathFloor(lots / step + 1e-9) * step;
   lots = MathMax(vmin, MathMin(vmax, lots));
   int dg = (step > 0.0) ? (int)MathRound(-MathLog10(step)) : 2;
   if(dg < 0) dg = 0;
   return NormalizeDouble(lots, dg);
  }

bool MarginOk(const int d, const double lots, const double price)
  {
   double margin = 0.0;
   ENUM_ORDER_TYPE ot = (d > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(!OrderCalcMargin(ot, _Symbol, lots, price, margin)) return false;
   return (margin <= AccountInfoDouble(ACCOUNT_MARGIN_FREE) * 0.9);
  }

bool SelectMyPosition()
  {
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic)
         return true;
     }
   return false;
  }

void CountPendings(int &nBuy, int &nSell)
  {
   nBuy = 0;
   nSell = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol || OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      long ty = OrderGetInteger(ORDER_TYPE);
      if(ty == ORDER_TYPE_BUY_STOP)  nBuy++;
      if(ty == ORDER_TYPE_SELL_STOP) nSell++;
     }
  }

void DeleteMyPendings()
  {
   for(int i = OrdersTotal() - 1; i >= 0; i--)
     {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != _Symbol || OrderGetInteger(ORDER_MAGIC) != InpMagic) continue;
      long ty = OrderGetInteger(ORDER_TYPE);
      if(ty != ORDER_TYPE_BUY_STOP && ty != ORDER_TYPE_SELL_STOP) continue;
      if(!trade.OrderDelete(t))
         SetMsg("Delete pending failed: " + IntegerToString((int)trade.ResultRetcode()) + " " + trade.ResultRetcodeDescription());
     }
  }

void CloseAllMine()
  {
   ulong dev = (ulong)MathMax(1.0, MathRound(InpDeviationPips * g_pip / _Point));
   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) == _Symbol && PositionGetInteger(POSITION_MAGIC) == InpMagic)
        {
         if(!trade.PositionClose(t, dev))
            SetMsg("Close failed: " + IntegerToString((int)trade.ResultRetcode()) + " " + trade.ResultRetcodeDescription());
        }
     }
  }

//------------------------------- SEND CONTROL ----------------------
// Central gate: stops the EA from hammering the server.
bool CanSend()
  {
   if(TimeCurrent() < g_nextTry) return false;

   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED))
     {
      SetMsg("Algo trading is OFF in terminal or EA settings. No orders sent.");
      g_nextTry = TimeCurrent() + 30;
      return false;
     }
   if(!AccountInfoInteger(ACCOUNT_TRADE_ALLOWED) || !AccountInfoInteger(ACCOUNT_TRADE_EXPERT))
     {
      SetMsg("Broker has disabled trading/EA trading on this account (account flags). No orders sent.");
      g_nextTry = TimeCurrent() + 60;
      return false;
     }
   if(SymbolInfoInteger(_Symbol, SYMBOL_TRADE_MODE) != SYMBOL_TRADE_MODE_FULL)
     {
      SetMsg("Symbol trading is not fully enabled right now (market closed?).");
      g_nextTry = TimeCurrent() + 30;
      return false;
     }
   if(InpMaxSpreadPips > 0.0)
     {
      MqlTick t;
      if(!SymbolInfoTick(_Symbol, t)) return false;
      if((t.ask - t.bid) > InpMaxSpreadPips * g_pip)
        {
         SetMsg("Spread above limit, waiting.");
         return false;
        }
     }
   return true;
  }

void OnSendOk()
  {
   g_fails = 0;
   g_nextTry = 0;
  }

void OnSendFail(const uint rc, const string desc)
  {
   g_fails++;
   int wait = InpRetryCooldownSec;
   for(int i = 1; i < g_fails && wait < InpMaxBackoffSec; i++) wait *= 2;
   wait = MathMin(wait, InpMaxBackoffSec);
   // server/client says trading is disabled: do not retry for at least 10 minutes
   if(rc == 10026 || rc == 10027 || rc == 10017)
      wait = MathMax(wait, 600);
   g_nextTry = TimeCurrent() + wait;
   SetMsg(StringFormat("Order failed rc=%u (%s). Next try in %d s.", rc, desc, wait));
  }

bool RetOk(const uint rc)
  {
   return (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL);
  }

//------------------------------- ORDERS ----------------------------
bool PlacePair()
  {
   if(!CanSend()) return false;
   MqlTick t;
   if(!SymbolInfoTick(_Symbol, t)) return false;

   double spread = t.ask - t.bid;
   double dist   = InpEntryPips * g_pip;
   double sld    = InpSLPips * g_pip;
   double minD   = MinStopDist() + spread;
   if(dist < minD) dist = minD + _Point;
   if(sld  < minD) sld  = minD + _Point;

   double lots  = NormLots();
   double buyP  = NormPrice(t.ask + dist);
   double sellP = NormPrice(t.bid - dist);
   double buySL = NormPrice(buyP - sld);
   double selSL = NormPrice(sellP + sld);

   if(!MarginOk(1, lots, buyP) || !MarginOk(-1, lots, sellP))
     {
      g_nextTry = TimeCurrent() + 60;
      SetMsg("Not enough free margin for the pair.");
      return false;
     }

   bool ok1 = trade.BuyStop(lots, buyP, _Symbol, buySL, 0.0, ORDER_TIME_GTC, 0, InpComment);
   uint rc1 = trade.ResultRetcode();
   if(!(ok1 && RetOk(rc1)))
     {
      OnSendFail(rc1, trade.ResultRetcodeDescription());
      return false;
     }
   ulong buyTicket = trade.ResultOrder();

   bool ok2 = trade.SellStop(lots, sellP, _Symbol, selSL, 0.0, ORDER_TIME_GTC, 0, InpComment);
   uint rc2 = trade.ResultRetcode();
   if(!(ok2 && RetOk(rc2)))
     {
      trade.OrderDelete(buyTicket);      // keep the pair symmetric
      OnSendFail(rc2, trade.ResultRetcodeDescription());
      return false;
     }

   OnSendOk();
   SetMsg(StringFormat("Pair placed: BuyStop %.3f  SellStop %.3f", buyP, sellP));
   return true;
  }

bool OpenMarket(const int d)
  {
   if(!CanSend()) return false;
   MqlTick t;
   if(!SymbolInfoTick(_Symbol, t)) return false;

   double price  = (d > 0) ? t.ask : t.bid;
   double spread = t.ask - t.bid;
   double sld    = InpSLPips * g_pip;
   double minD   = MinStopDist() + spread;
   if(sld < minD) sld = minD + _Point;
   double sl     = NormPrice(price - d * sld);
   double lots   = NormLots();

   if(!MarginOk(d, lots, price))
     {
      g_nextTry = TimeCurrent() + 60;
      SetMsg("Not enough free margin for reversal.");
      return false;
     }

   trade.SetDeviationInPoints((ulong)MathMax(1.0, MathRound(InpDeviationPips * g_pip / _Point)));
   bool ok = (d > 0) ? trade.Buy(lots, _Symbol, price, sl, 0.0, InpComment)
                     : trade.Sell(lots, _Symbol, price, sl, 0.0, InpComment);
   uint rc = trade.ResultRetcode();
   if(ok && RetOk(rc))
     {
      OnSendOk();
      return true;
     }
   OnSendFail(rc, trade.ResultRetcodeDescription());
   return false;
  }

//------------------------------- TRAILING --------------------------
bool ModifySL(const ulong tk, const int dir, const double newSLraw)
  {
   if(TimeCurrent() < g_nextModify) return false;
   double sl = PositionGetDouble(POSITION_SL);
   double tp = PositionGetDouble(POSITION_TP);
   double newSL = NormPrice(newSLraw);
   MqlTick t;
   if(!SymbolInfoTick(_Symbol, t)) return false;
   double minD = MinStopDist();
   if(dir > 0)
     {
      if(sl != 0.0 && newSL <= sl) return false;
      if(newSL > t.bid - minD) return false;
     }
   else
     {
      if(sl != 0.0 && newSL >= sl) return false;
      if(newSL < t.ask + minD) return false;
     }
   if(!trade.PositionModify(tk, newSL, tp))
     {
      g_nextModify = TimeCurrent() + 5;      // no hammering on rejection
      SetMsg("SL modify rejected: " + IntegerToString((int)trade.ResultRetcode()) + " " + trade.ResultRetcodeDescription());
      return false;
     }
   return true;
  }

void TrailStop()
  {
   if(!SelectMyPosition()) return;
   ulong tk    = (ulong)PositionGetInteger(POSITION_TICKET);
   int dir     = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   double open = PositionGetDouble(POSITION_PRICE_OPEN);
   double sl   = PositionGetDouble(POSITION_SL);
   MqlTick t;
   if(!SymbolInfoTick(_Symbol, t)) return;

   // safety: if the position somehow has no SL, set the initial one
   if(sl == 0.0)
     {
      ModifySL(tk, dir, open - dir * InpSLPips * g_pip);
      return;
     }

   double profit = (dir > 0) ? (t.bid - open) : (open - t.ask);   // price units
   double stepD  = InpStepPips * g_pip;
   if(stepD <= 0.0) return;
   int steps = (int)MathFloor(profit / stepD + 1e-9);
   if(steps < 1) return;

   // steps=1 -> SL at entry, steps=2 -> entry + 1 step, steps=3 -> entry + 2 steps ...
   double desired = open + dir * (steps - 1) * stepD;
   ModifySL(tk, dir, desired);
  }

//------------------------------- POSITION EVENTS -------------------
void HandleNewPosition()
  {
   g_posId = (ulong)PositionGetInteger(POSITION_IDENTIFIER);
   g_dir   = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
   g_open  = PositionGetDouble(POSITION_PRICE_OPEN);
   g_state = ST_IN_TRADE;
   g_closeStart = 0;
   DeleteMyPendings();
   SetMsg(StringFormat("Position opened: %s at %.3f", (g_dir > 0 ? "BUY" : "SELL"), g_open));
  }

bool GetCloseReason(const ulong posId, long &reason)
  {
   if(posId == 0) return false;
   if(!HistorySelectByPosition(posId)) return false;
   int n = HistoryDealsTotal();
   for(int i = n - 1; i >= 0; i--)
     {
      ulong tk = HistoryDealGetTicket(i);
      if(tk == 0) continue;
      long en = HistoryDealGetInteger(tk, DEAL_ENTRY);
      if(en == DEAL_ENTRY_OUT || en == DEAL_ENTRY_OUT_BY)
        {
         reason = HistoryDealGetInteger(tk, DEAL_REASON);
         return true;
        }
     }
   return false;
  }

// returns true once the close has been classified
bool HandleClosed()
  {
   if(g_closeStart == 0) g_closeStart = TimeCurrent();
   long reason = -1;
   bool found = GetCloseReason(g_posId, reason);
   if(!found && TimeCurrent() - g_closeStart < 3) return false;   // history may lag a moment
   g_closeStart = 0;

   if(found && reason == DEAL_REASON_SL)
     {
      g_nextDir = -g_dir;
      g_state   = ST_NEED_REVERSAL;
      g_reversals++;
      SetMsg(StringFormat("SL hit. Reversing to %s.", (g_nextDir > 0 ? "BUY" : "SELL")));
     }
   else
     {
      g_state = ST_ARMED;
      SetMsg("Position closed by something other than SL (manual/stop-out/EA). Re-arming pending pair.");
     }
   return true;
  }

void EnsurePendings()
  {
   int nb, ns;
   CountPendings(nb, ns);
   if(nb == 1 && ns == 1) return;
   if(nb + ns > 0)
     {
      DeleteMyPendings();       // wrong set -> clean, pair is re-placed next tick
      return;
     }
   PlacePair();
  }

//------------------------------- DAILY RISK ------------------------
void UpdateDay()
  {
   MqlDateTime s;
   TimeToStruct(TimeCurrent(), s);
   int key = s.year * 10000 + s.mon * 100 + s.day;
   if(key != g_dayKey)
     {
      g_dayKey = key;
      g_dayEq  = AccountInfoDouble(ACCOUNT_EQUITY);
      if(g_state == ST_HALTED)
        {
         g_state = ST_ARMED;
         SetMsg("New server day: trading resumed.");
        }
     }
  }

void ManageDailyRisk()
  {
   if(g_state == ST_HALTED || g_dayEq <= 0.0) return;
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double pl = (eq - g_dayEq) / g_dayEq * 100.0;
   if(pl <= -InpDailyLossPct || pl >= InpDailyProfitPct)
     {
      CloseAllMine();
      DeleteMyPendings();
      g_state = ST_HALTED;
      SetMsg(StringFormat("Daily limit reached (%.2f%%). All closed, halted until next server day.", pl));
     }
  }

//------------------------------- PANEL -----------------------------
void Panel()
  {
   if(!InpShowPanel) return;
   if(TimeCurrent() == g_lastPanel) return;
   g_lastPanel = TimeCurrent();

   string st = "ARMED (waiting for stop order to trigger)";
   if(g_state == ST_IN_TRADE)      st = "IN TRADE";
   if(g_state == ST_NEED_REVERSAL) st = "REVERSING";
   if(g_state == ST_HALTED)        st = "HALTED (daily limit)";

   string s = "=== PipStep Reversal EA ===\n";
   s += "Symbol: " + _Symbol + " | 1 pip = " + DoubleToString(g_pip, _Digits) + " | Lots: " + DoubleToString(NormLots(), 2) + "\n";
   s += "State: " + st + "\n";
   if(g_state == ST_IN_TRADE && SelectMyPosition())
     {
      MqlTick t;
      if(SymbolInfoTick(_Symbol, t))
        {
         int d = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? 1 : -1;
         double open = PositionGetDouble(POSITION_PRICE_OPEN);
         double p = ((d > 0) ? (t.bid - open) : (open - t.ask)) / g_pip;
         s += StringFormat("%s open %.3f | SL %.3f | Floating %.1f pips\n", (d > 0 ? "BUY" : "SELL"), open,
                           PositionGetDouble(POSITION_SL), p);
        }
     }
   double eq = AccountInfoDouble(ACCOUNT_EQUITY);
   double pl = (g_dayEq > 0.0) ? (eq - g_dayEq) / g_dayEq * 100.0 : 0.0;
   s += StringFormat("Reversals: %d | Day P/L: %.2f%% (stop -%.0f%% / target +%.0f%%)\n", g_reversals, pl, InpDailyLossPct, InpDailyProfitPct);
   s += "Last: " + g_msg;
   Comment(s);
  }

//------------------------------- EVENTS ----------------------------
int OnInit()
  {
   if(InpLots <= 0.0 || InpEntryPips <= 0.0 || InpSLPips <= 0.0 || InpStepPips <= 0.0)
     {
      Print("Lots, EntryPips, SLPips and StepPips must be > 0");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(InpDailyLossPct <= 0.0 || InpDailyProfitPct <= 0.0 || InpRetryCooldownSec < 1 || InpMaxBackoffSec < InpRetryCooldownSec)
     {
      Print("Invalid safety inputs");
      return INIT_PARAMETERS_INCORRECT;
     }
   if(!SymbolSelect(_Symbol, true)) { Print("Cannot select symbol"); return INIT_FAILED; }

   g_pip = DetectPip();
   if(g_pip <= 0.0) { Print("Pip size could not be determined. Set InpPipPrice."); return INIT_FAILED; }

   trade.SetExpertMagicNumber(InpMagic);
   trade.SetDeviationInPoints((ulong)MathMax(1.0, MathRound(InpDeviationPips * g_pip / _Point)));
   trade.SetTypeFillingBySymbol(_Symbol);
   trade.SetAsyncMode(false);

   MqlDateTime s;
   TimeToStruct(TimeCurrent(), s);
   g_dayKey = s.year * 10000 + s.mon * 100 + s.day;
   g_dayEq  = AccountInfoDouble(ACCOUNT_EQUITY);

   g_state = ST_ARMED;
   Print("[PIPSTEP] Started on ", _Symbol, ". 1 pip = ", DoubleToString(g_pip, _Digits),
         " price units, so ", DoubleToString(InpEntryPips, 1), " pips = ", DoubleToString(InpEntryPips * g_pip, _Digits));
   if(MathAbs(g_pip - 0.10) > 1e-9 && (StringFind(_Symbol, "BTC") >= 0 || StringFind(_Symbol, "ETH") >= 0 ||
      StringFind(_Symbol, "OIL") >= 0 || StringFind(_Symbol, "US30") >= 0 || StringFind(_Symbol, "NAS") >= 0))
      Print("[PIPSTEP] WARNING: pip size for this symbol is a guess. Set InpPipPrice yourself.");
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   if(InpDeleteOnRemove && (reason == REASON_REMOVE || reason == REASON_CHARTCLOSE || reason == REASON_CLOSE))
      DeleteMyPendings();
   Comment("");
  }

void OnTick()
  {
   UpdateDay();
   ManageDailyRisk();

   if(g_state == ST_HALTED)
     {
      Panel();
      return;
     }

   // 1) a position exists: manage it
   if(SelectMyPosition())
     {
      if(g_state != ST_IN_TRADE) HandleNewPosition();

      int nb, ns;
      CountPendings(nb, ns);
      if(nb + ns > 0 && TimeCurrent() >= g_nextClean)
        {
         g_nextClean = TimeCurrent() + 2;
         DeleteMyPendings();
        }
      TrailStop();
      Panel();
      return;
     }

   // 2) no position, but we had one: classify how it closed
   if(g_state == ST_IN_TRADE)
     {
      if(!HandleClosed())
        {
         Panel();
         return;
        }
     }

   // 3) SL was hit: open the opposite trade
   if(g_state == ST_NEED_REVERSAL)
     {
      if(OpenMarket(g_nextDir))
        {
         if(SelectMyPosition()) HandleNewPosition();
        }
      Panel();
      return;
     }

   // 4) start state: make sure BuyStop + SellStop exist
   EnsurePendings();
   Panel();
  }
//+------------------------------------------------------------------+
