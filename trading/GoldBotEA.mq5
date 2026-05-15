#property strict

#include <Trade/Trade.mqh>

input string SignalServerURL = "http://127.0.0.1:8080";
input string Symbol_ = "";
input int    PollSeconds = 60;
input double LotOverride = 0.0;
input double MinLotSize = 0.01;
input double MaxLotSize = 0.02;
input double RiskPerTradePct = 1.0;
input double MaxMarginUsagePct = 20.0;
input int    MarketClosedRetrySeconds = 300;
input bool   EnableTrading = false;
input ulong  MagicNumber = 20260418;

// Trailing Stop Settings
input bool   EnableTrailingStop = true;
input double TrailingStartPips = 35.0; // Pips in profit before trailing activates
input double TrailingDistancePips = 15.0; // Distance to trail the price

CTrade trade;
string activeSymbol = "";
datetime lastPoll = 0;
datetime nextRetryAt = 0;

string activeSignalId = "";
string activeSignalAction = "";
double activeSignalConfidence = 0.0;
double activeSignalEntryPrice = 0.0;
double activeSignalStopLoss = 0.0;
double activeSignalTakeProfit = 0.0;
double activeSignalLot = 0.0;
ulong lastReportedExitDeal = 0;

string TrimValue(string value)
{
   StringTrimLeft(value);
   StringTrimRight(value);
   return value;
}

string JsonField(string json, string field)
{
   string needle = "\"" + field + "\"";
   int keyPos = StringFind(json, needle);
   if(keyPos < 0)
      return "";

   int colonPos = StringFind(json, ":", keyPos);
   if(colonPos < 0)
      return "";

   int start = colonPos + 1;
   int len = StringLen(json);
   while(start < len)
   {
      ushort ch = StringGetCharacter(json, start);
      if(ch != ' ' && ch != '\t' && ch != '\r' && ch != '\n')
         break;
      start++;
   }

   if(start >= len)
      return "";

   if(StringGetCharacter(json, start) == '"')
   {
      start++;
      int endQuote = StringFind(json, "\"", start);
      if(endQuote < 0)
         return "";
      return StringSubstr(json, start, endQuote - start);
   }

   int end = start;
   while(end < len)
   {
      ushort ch = StringGetCharacter(json, end);
      if(ch == ',' || ch == '}')
         break;
      end++;
   }
   return TrimValue(StringSubstr(json, start, end - start));
}

string JsonEscape(string value)
{
   StringReplace(value, "\\", "\\\\");
   StringReplace(value, "\"", "\\\"");
   StringReplace(value, "\n", " ");
   StringReplace(value, "\r", " ");
   return value;
}

bool PostJson(string url, string payload)
{
   char data[];
   char result[];
   string headers = "Content-Type: application/json\r\n";
   string response_headers = "";
   int bytesWritten = StringToCharArray(payload, data, 0, -1, CP_UTF8);
   if(bytesWritten > 0)
      ArrayResize(data, bytesWritten - 1);
   else
      ArrayResize(data, 0);

   ResetLastError();
   int status = WebRequest("POST", url, headers, 5000, data, result, response_headers);
   if(status == -1)
   {
      Print("PostJson WebRequest failed. Error=", GetLastError(), " URL=", url);
      return false;
   }

   if(status < 200 || status >= 300)
   {
      Print("PostJson HTTP status=", status, " URL=", url, " payload=", payload);
      return false;
   }

   return true;
}

string FetchSignal()
{
   string url = SignalServerURL + "/signal/" + activeSymbol;
   char result[];
   string headers = "";
   char data[];
   string response_headers = "";
   ResetLastError();

   int status = WebRequest("GET", url, headers, 5000, data, result, response_headers);
   if(status == -1)
   {
      Print("FetchSignal WebRequest failed. Error=", GetLastError(), " URL=", url);
      return "";
   }

   if(status < 200 || status >= 300)
   {
      Print("FetchSignal HTTP status=", status, " URL=", url);
      return "";
   }

   return CharArrayToString(result);
}

bool HasOpenPosition()
{
   for(int i = 0; i < PositionsTotal(); i++)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;

      string symbol = PositionGetString(POSITION_SYMBOL);
      long magic = PositionGetInteger(POSITION_MAGIC);
      if(symbol == activeSymbol && (ulong)magic == MagicNumber)
         return true;
   }
   return false;
}

double NormalizeLotSize(string symbol, double requested)
{
   double brokerMinLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
   double maxLot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
   double step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

   if(step <= 0.0)
      step = 0.01;

   if(brokerMinLot <= 0.0)
      brokerMinLot = step;

   double minLot = MathMax(brokerMinLot, MinLotSize);

   double normalized = MathFloor(requested / step) * step;
   if(normalized < minLot)
      normalized = minLot;
   if(MaxLotSize > 0.0 && normalized > MaxLotSize)
      normalized = MaxLotSize;
   else if(maxLot > 0.0 && normalized > maxLot)
      normalized = maxLot;

   int digits = 0;
   double probe = step;
   while(digits < 8 && MathRound(probe) != probe)
   {
      probe *= 10.0;
      digits++;
   }

   return NormalizeDouble(normalized, digits);
}

double CalculateRiskBasedLot(string symbol, ENUM_ORDER_TYPE orderType, double entryPrice, double stopLossPrice)
{
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(balance <= 0.0)
      return 0.0;

   double riskAmount = balance * (RiskPerTradePct / 100.0);
   double priceDistance = MathAbs(entryPrice - stopLossPrice);
   double tickSize = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);

   if(riskAmount <= 0.0 || priceDistance <= 0.0 || tickSize <= 0.0 || tickValue <= 0.0)
      return 0.0;

   double lossPerLot = (priceDistance / tickSize) * tickValue;
   if(lossPerLot <= 0.0)
      return 0.0;

   double riskLot = riskAmount / lossPerLot;
   double marginPerLot = 0.0;
   if(!OrderCalcMargin(orderType, symbol, 1.0, entryPrice, marginPerLot))
      marginPerLot = 0.0;

   if(marginPerLot > 0.0 && MaxMarginUsagePct > 0.0)
   {
      double maxMargin = balance * (MaxMarginUsagePct / 100.0);
      double marginLot = maxMargin / marginPerLot;
      if(marginLot > 0.0)
         riskLot = MathMin(riskLot, marginLot);
   }

   return NormalizeLotSize(symbol, riskLot);
}

bool ReportLivePrice(string symbol, double price)
{
   string payload = StringFormat("{\"ticker\":\"%s\",\"price\":%.5f}", JsonEscape(symbol), price);
   return PostJson(SignalServerURL + "/price/update", payload);
}

bool ReportExecutionOpen(string signalId, string action, double confidence, double entryPrice, double stopLoss, double takeProfit, double lot, ulong orderTicket, ulong dealTicket)
{
   string payload = StringFormat(
      "{\"signal_id\":\"%s\",\"ticker\":\"%s\",\"action\":\"%s\",\"confidence\":%.5f,\"entry_price\":%.5f,\"sl\":%.5f,\"tp\":%.5f,\"lot\":%.4f,\"order_ticket\":\"%s\",\"deal_ticket\":\"%s\"}",
      JsonEscape(signalId),
      JsonEscape(activeSymbol),
      JsonEscape(action),
      confidence,
      entryPrice,
      stopLoss,
      takeProfit,
      lot,
      JsonEscape(IntegerToString((long)orderTicket)),
      JsonEscape(IntegerToString((long)dealTicket))
   );
   bool ok = PostJson(SignalServerURL + "/execution/open", payload);
   if(ok) Print("Execution report sent to Python for signal ", signalId);
   return ok;
}

bool FindLatestClosedDeal(double &closePrice, double &profit, ulong &dealTicket)
{
   datetime from = TimeCurrent() - (14 * 24 * 60 * 60);
   if(!HistorySelect(from, TimeCurrent()))
      return false;

   int total = HistoryDealsTotal();
   for(int i = total - 1; i >= 0; i--)
   {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0 || ticket == lastReportedExitDeal)
         continue;

      string symbol = HistoryDealGetString(ticket, DEAL_SYMBOL);
      long magic = (long)HistoryDealGetInteger(ticket, DEAL_MAGIC);
      long entry = (long)HistoryDealGetInteger(ticket, DEAL_ENTRY);

      if(symbol != activeSymbol || (ulong)magic != MagicNumber || entry != DEAL_ENTRY_OUT)
         continue;

      closePrice = HistoryDealGetDouble(ticket, DEAL_PRICE);
      profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
      dealTicket = ticket;
      return true;
   }

   return false;
}

bool ReportExecutionClose(string signalId, double closePrice, double profit, ulong dealTicket)
{
   string result = "breakeven";
   if(profit > 0.0)
      result = "win";
   else if(profit < 0.0)
      result = "loss";

   string payload = StringFormat(
      "{\"signal_id\":\"%s\",\"ticker\":\"%s\",\"close_price\":%.5f,\"profit\":%.2f,\"result\":\"%s\",\"deal_ticket\":\"%s\"}",
      JsonEscape(signalId),
      JsonEscape(activeSymbol),
      closePrice,
      profit,
      JsonEscape(result),
      JsonEscape(IntegerToString((long)dealTicket))
   );
   return PostJson(SignalServerURL + "/execution/close", payload);
}

void ResetActiveSignalState()
{
   activeSignalId = "";
   activeSignalAction = "";
   activeSignalConfidence = 0.0;
   activeSignalEntryPrice = 0.0;
   activeSignalStopLoss = 0.0;
   activeSignalTakeProfit = 0.0;
   activeSignalLot = 0.0;
}

void TryReportClosedTrade()
{
   if(activeSignalId == "" || HasOpenPosition())
      return;

   double closePrice = 0.0;
   double profit = 0.0;
   ulong closeDeal = 0;
   if(!FindLatestClosedDeal(closePrice, profit, closeDeal))
      return;

   if(ReportExecutionClose(activeSignalId, closePrice, profit, closeDeal))
   {
      lastReportedExitDeal = closeDeal;
      Print("Reported closed trade for signal ", activeSignalId, " profit=", DoubleToString(profit, 2));
      ResetActiveSignalState();
   }
}

int OnInit()
{
   activeSymbol = (Symbol_ == "" ? Symbol() : Symbol_);
   trade.SetExpertMagicNumber(MagicNumber);
   trade.SetDeviationInPoints(20);
   EventSetTimer(MathMax(1, PollSeconds));
   Print("GoldBotEA initialized for ", activeSymbol, " polling ", SignalServerURL);
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void ProcessSignal()
{
   TryReportClosedTrade();

   datetime now = TimeCurrent();
   if(nextRetryAt > 0 && now < nextRetryAt)
      return;
   if(now - lastPoll < PollSeconds)
      return;
   lastPoll = now;
   
   // Send live price to server so Python stays synced with Broker
   double currentPrice = SymbolInfoDouble(activeSymbol, SYMBOL_BID);
   if(currentPrice > 0) ReportLivePrice(activeSymbol, currentPrice);

   string json = FetchSignal();
   if(json == "")
      return;

   string signalId = JsonField(json, "signal_id");
   string action = JsonField(json, "action");
   StringToUpper(action);
   double confidence = StringToDouble(JsonField(json, "confidence"));
   double plannedEntry = StringToDouble(JsonField(json, "entry_price"));
   double sl = StringToDouble(JsonField(json, "sl"));
   double tp = StringToDouble(JsonField(json, "tp"));
   double lot = StringToDouble(JsonField(json, "lot"));
   string comment = StringFormat("GoldBot %.0f%%", confidence * 100.0);

   if(LotOverride > 0.0)
      lot = LotOverride;

   if(!EnableTrading)
   {
      Print("Trading disabled");
      return;
   }

   if(HasOpenPosition())
   {
      Print("Position open, skipping");
      return;
   }

   bool ok = false;
   double executedEntryPrice = plannedEntry;
   if(action == "BUY")
   {
      double ask = SymbolInfoDouble(activeSymbol, SYMBOL_ASK);
      executedEntryPrice = ask;
      
      // FIX: Calculate relative SL/TP to avoid 10016 invalid stops due to Yahoo/Broker price mismatch
      double symPoint = SymbolInfoDouble(activeSymbol, SYMBOL_POINT);
      int symDigits = (int)SymbolInfoInteger(activeSymbol, SYMBOL_DIGITS);
      double useSL = ask - (300 * symPoint); // 30 pips SL
      double useTP = ask + (600 * symPoint); // 60 pips TP
      
      double requestedLot = lot;
      if(LotOverride > 0.0)
         requestedLot = LotOverride;
      else
      {
         requestedLot = CalculateRiskBasedLot(activeSymbol, ORDER_TYPE_BUY, ask, useSL);
         if(requestedLot <= 0.0)
            requestedLot = lot;
      }
      requestedLot = NormalizeLotSize(activeSymbol, requestedLot);
      Print("Using lot=", DoubleToString(requestedLot, 8), " ask=", DoubleToString(ask, symDigits), " sl=", DoubleToString(useSL, symDigits));
      lot = requestedLot;
      ok = trade.Buy(lot, activeSymbol, ask, useSL, useTP, comment);
      sl = useSL; tp = useTP; // Update for reporting
   }
   else if(action == "SELL")
   {
      double bid = SymbolInfoDouble(activeSymbol, SYMBOL_BID);
      executedEntryPrice = bid;
      
      // FIX: Calculate relative SL/TP using distances from Python signal to avoid 10016 invalid stops due to price mismatch
      double symPoint = SymbolInfoDouble(activeSymbol, SYMBOL_POINT);
      int symDigits = (int)SymbolInfoInteger(activeSymbol, SYMBOL_DIGITS);
      
      double pythonStopDistance = sl - plannedEntry;
      double pythonTargetDistance = plannedEntry - tp;
      if (pythonStopDistance <= 0) pythonStopDistance = 300 * symPoint; // Fallback
      if (pythonTargetDistance <= 0) pythonTargetDistance = 600 * symPoint; // Fallback
      
      double useSL = NormalizeDouble(bid + pythonStopDistance, symDigits);
      double useTP = NormalizeDouble(bid - pythonTargetDistance, symDigits);
      
      double requestedLot = lot;
      if(LotOverride > 0.0)
         requestedLot = LotOverride;
      else
      {
         requestedLot = CalculateRiskBasedLot(activeSymbol, ORDER_TYPE_SELL, bid, useSL);
         if(requestedLot <= 0.0)
            requestedLot = lot;
      }
      requestedLot = NormalizeLotSize(activeSymbol, requestedLot);
      Print("Using lot=", DoubleToString(requestedLot, 8), " bid=", DoubleToString(bid, symDigits), " sl=", DoubleToString(useSL, symDigits));
      lot = requestedLot;
      ok = trade.Sell(lot, activeSymbol, bid, useSL, useTP, comment);
      sl = useSL; tp = useTP; // Update for reporting
   }
   else
   {
      Print("No actionable signal: ", json);
      return;
   }

   Print("Trade result action=", action,
         " success=", ok,
         " retcode=", trade.ResultRetcode(),
         " order=", trade.ResultOrder(),
         " deal=", trade.ResultDeal());

   if(!ok && trade.ResultRetcode() == 10018)
   {
      nextRetryAt = now + MathMax(60, MarketClosedRetrySeconds);
      Print("Market closed for ", activeSymbol, ". Next retry after ", TimeToString(nextRetryAt, TIME_MINUTES | TIME_SECONDS));
   }
   else if(ok)
   {
      nextRetryAt = 0;
      activeSignalId = signalId;
      activeSignalAction = action;
      activeSignalConfidence = confidence;
      activeSignalEntryPrice = executedEntryPrice;
      activeSignalStopLoss = sl;
      activeSignalTakeProfit = tp;
      activeSignalLot = lot;
      ReportExecutionOpen(signalId, action, confidence, executedEntryPrice, sl, tp, lot, trade.ResultOrder(), trade.ResultDeal());
   }
}

void ManageTrailingStop()
{
   if(!EnableTrailingStop || !HasOpenPosition()) return;
   
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0) continue;
      if(!PositionSelectByTicket(ticket)) continue;
      
      string posSymbol = PositionGetString(POSITION_SYMBOL);
      long posMagic = PositionGetInteger(POSITION_MAGIC);
      if(posSymbol != activeSymbol || (ulong)posMagic != MagicNumber) continue;
      
      double currentPrice = 0.0;
      long posType = PositionGetInteger(POSITION_TYPE);
      double openPrice = PositionGetDouble(POSITION_PRICE_OPEN);
      double currentSL = PositionGetDouble(POSITION_SL);
      double currentTP = PositionGetDouble(POSITION_TP);
      
      // Calculate real pip size
      double symPoint = SymbolInfoDouble(posSymbol, SYMBOL_POINT);
      int symDigits = (int)SymbolInfoInteger(posSymbol, SYMBOL_DIGITS);
      double pipSize = (symDigits == 3 || symDigits == 5) ? symPoint * 10.0 : symPoint;
      if(posSymbol == "XAUUSD" || posSymbol == "GOLD") pipSize = 0.1; 
      
      double trailStart = TrailingStartPips * pipSize;
      double trailDist = TrailingDistancePips * pipSize;
      
      if(posType == POSITION_TYPE_BUY)
      {
         currentPrice = SymbolInfoDouble(posSymbol, SYMBOL_BID);
         if(currentPrice - openPrice >= trailStart)
         {
            double newSL = NormalizeDouble(currentPrice - trailDist, symDigits);
            if(currentSL < newSL || currentSL == 0.0)
            {
               trade.PositionModify(ticket, newSL, currentTP);
            }
         }
      }
      else if(posType == POSITION_TYPE_SELL)
      {
         currentPrice = SymbolInfoDouble(posSymbol, SYMBOL_ASK);
         if(openPrice - currentPrice >= trailStart)
         {
            double newSL = NormalizeDouble(currentPrice + trailDist, symDigits);
            if(currentSL > newSL || currentSL == 0.0)
            {
               trade.PositionModify(ticket, newSL, currentTP);
            }
         }
      }
   }
}

void OnTick()
{
   ManageTrailingStop();
   ProcessSignal();
}

void OnTimer()
{
   ManageTrailingStop();
   ProcessSignal();
}
