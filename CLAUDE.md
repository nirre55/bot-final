# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

**Active Strategy**: ONE_OR_MORE (1RR hedge system)
**Symbol**: LINKUSDC @ 5m timeframe
**Risk**: 3% of balance per trade
**Entry Point**: `python trading_bot.py`
**Logs**: `logs/trading_bot.log`
**Shutdown**: Single Ctrl+C for graceful shutdown

## Project Overview

Python-based **Binance futures trading bot** using real-time WebSocket streams for RSI and Heikin Ashi indicators. The bot implements a modular service-oriented architecture focused on the **ONE_OR_MORE strategy** with guaranteed 1:1 Risk-Reward ratio.

## Core Architecture

### Layered Design
- **`trading_bot.py`**: Main orchestrator coordinating all services
- **Strategy Layer** (`strategies/`): ONE_OR_MORE strategy implementation and management
- **Service Layer** (`core/`): Business logic (RSI, HA, Signal, Trading, OneOrMoreService)
- **Indicator Layer** (`indicators/`): Pure RSI and Heikin Ashi calculations
- **API Layer** (`api/`): Binance REST API communication
- **WebSocket Layer** (`websocket/`): Dual streams (klines + User Data Stream)

### Signal Processing Flow
1. WebSocket kline data → `_handle_kline_message()`
2. Candle close → RSI calculation → HA calculation
3. Signal detection (3-step: RSI + HA + Volume)
4. Strategy execution → `StrategyManager.execute_signal()`
5. ONE_OR_MORE workflow → Signal + Hedge + Dual TP + Cross-stops
6. Real-time order execution via User Data Stream

## Setup and Running

```bash
# Python 3.12+ recommended
pip install pandas numpy requests websockets python-dotenv

# Create .env with Binance API credentials
# BINANCE_API_KEY=your_api_key
# BINANCE_SECRET_KEY=your_secret_key

# Run the bot
python trading_bot.py
```

## ONE_OR_MORE Strategy (Primary Strategy)

### Overview
Advanced 1RR system with automatic hedge and guaranteed 1:1 Risk-Reward ratio through mathematical TP placement.

### Core Workflow
1. **Signal detected** → Market order execution
2. **Hedge creation** → STOP order at support/resistance (2x quantity)
3. **TP calculation** → 1RR system based on distance to hedge
4. **Dual TP creation** → Signal TP + Hedge TP (after hedge execution)
5. **Cross-stop protection** → Lock in 1RR when one TP hits
6. **WebSocket monitoring** → Real-time execution detection
7. **Automatic cleanup** → Cancel all related orders when closed

### Key Features
- ✅ **Automatic Hedge** at market structure levels
- ✅ **Guaranteed 1:1 RR** through mathematical TP placement
- ✅ **Dual TP System** for signal and hedge positions
- ✅ **Cross-Stop Protection** to secure 1RR
- ✅ **Trading Hours Restriction** (configurable window)
- ✅ **Multiple Cycles Allowed** (unlike ALL_OR_NOTHING)
- ✅ **WebSocket Integration** for instant detection

### Risk-Reward Logic (Asymmetric Mode)

**Phase 1: Signal executed, hedge waiting**
```
Signal LONG @ 100.0 ✅
Hedge SHORT @ 98.0 (STOP order, waiting)
Distance = 2.0

TP Signal = 100.0 + (2.0 × 1.0) = 102.0 (1.0RR)
TP Hedge = NOT YET CREATED
```

**Phase 2: Hedge executed → TP Update**
```
Hedge SHORT @ 98.0 EXECUTED ✅

Action 1: UPDATE TP Signal (closer for security)
  Old TP: 102.0 → Cancelled
  New TP: 100.0 + (2.0 × 0.5) = 101.0 (0.5RR)

Action 2: CREATE TP Hedge (farther for profit)
  New TP: 98.0 - (2.0 × 1.5) = 95.0 (1.5RR)

Result: TP Signal @ 101.0 + TP Hedge @ 95.0
```

**Phase 3: One TP hits → Cross-stop**
```
If TP Signal @ 101.0 hits:
  → Close signal (+1.0 profit = 0.5RR)
  → Create STOP to close hedge @ 98.0 (breakeven)

If TP Hedge @ 95.0 hits:
  → Close hedge (+6.0 profit = 1.5RR from 2x qty)
  → Create STOP to close signal @ 100.0 (breakeven)
```

### Configuration

```python
# In config.py
STRATEGY_CONFIG = {
    "STRATEGY_TYPE": "ONE_OR_MORE"
}

ONE_OR_MORE_CONFIG = {
    "ENABLED": True,
    "SL_LOOKBACK_CANDLES": 5,           # Candles for hedge placement
    "SL_OFFSET_PERCENT": 0.00001,       # 0.001% offset for hedge
    "HEDGE_QUANTITY_MULTIPLIER": 2,     # 2x quantity for hedge
    "RR_RATIO": 1.0,                    # Initial TP ratio before hedge
    "TP_SAFETY_OFFSET_PERCENT": 0.0002, # 0.02% safety offset
    "MIN_DISTANCE_PERCENT": 0.002,      # 0.2% minimum distance
    "SMALL_DISTANCE_OFFSET_PERCENT": 0.0015,
    "ASYMMETRIC_TP": {
        "ENABLED": True,                # Asymmetric mode ON
        "RR_RATIO_SIGNAL_AFTER_HEDGE": 0.5,   # 0.5RR after hedge
        "RR_RATIO_HEDGE_AFTER_HEDGE": 1.5,    # 1.5RR after hedge
    },
    "TRADING_HOURS": {
        "ENABLED": True,
        "START_HOUR": 5,                # 5am start
        "END_HOUR": 21,                 # 9pm end
        "TIMEZONE": "America/New_York",
    },
    "LOSS_RECOVERY": {
        "ENABLED": True,                # NEW: Loss recovery system
        "MAX_TIME_BETWEEN_TRADES": 30,  # Max 30 sec between 2 trades
    },
}
```

### Hedge Placement Logic
- **LONG Signal**: Hedge SHORT at LOW of last 5 candles - 0.001% offset
- **SHORT Signal**: Hedge LONG at HIGH of last 5 candles + 0.001% offset
- **Quantity**: 2x signal quantity
- **Market-based**: Uses actual candle HIGH/LOW for natural levels

### Order Types
- **Signal**: MARKET order (immediate entry)
- **Hedge**: STOP_MARKET order (at calculated level)
- **TP Orders**: TAKE_PROFIT orders (limit with trigger)
- **Cross-Stop**: STOP_MARKET orders (after first TP hit)

### Trading Hours Restriction
- **Time Window**: Define hours for signal execution (e.g., 5am-9pm)
- **Timezone Support**: Configurable (America/New_York, Europe/Paris, UTC)
- **Signal Blocking**: Rejects signals outside hours
- **Position Preservation**: Active positions remain after end time

Examples:
- Signal at 4:00am → ⏰ Blocked (before 5am)
- Signal at 20:30 → ✅ Executed (before 9pm)
- Signal at 21:15 → ⏰ Blocked (after 9pm)

### Loss Recovery System (COMPLETE)

**Automatic loss recovery** - Detects worst-case scenarios and automatically increases risk on next trade.

**Trigger condition (worst case):**
1. Hedge executed
2. TP signal executed after hedge
3. Result: Loss on cycle

**How it works:**
1. **End of cycle** → Fetch last 2 closed positions from Binance API (`/fapi/v1/income`)
2. **Check timing** → If close time < 30 seconds apart
3. **Calculate PNL** → Sum `income` (realized PNL) from both positions
4. **If negative** → Store loss amount in `loss_recovery.json`
5. **Next signal** → Override to FIXED mode with calculated quantity
6. **Recovery success** → Reset to normal mode

**Example workflow with accumulation:**
```
Cycle 1 (Loss):
  Signal SHORT @ 23.29 (8.27 qty)
  Hedge LONG @ 23.35 executed
  TP Signal @ 23.27 executed
  Trade1 PNL: -0.5$, Trade2 PNL: -2.5$
  Total: -3.0$ → Recovery = 3.0$ (stored in JSON)

Cycle 2 (Loss aussi):
  Signal LONG @ 24.50 (normal qty)
  Hedge SHORT @ 24.30 executed
  TP Signal @ 24.52 executed
  Trade1 PNL: -1.0$, Trade2 PNL: -1.5$
  Total: -2.5$ → Recovery = 3.0 + 2.5 = 5.5$ ✅ ACCUMULATION

Cycle 3 (Recovery partielle):
  Signal SHORT @ 23.20
  Hedge @ 23.40 (distance = 0.20)
  Normal mode: 2% × 100$ = 2.0$ risk
  Check: 2.0$ < 5.5$ → Recovery needed
  Quantity: 5.5 / 0.20 = 27.5 (FIXED mode override)
  TP hit → Profit +3.0$
  Recovery: 5.5 - 3.0 = 2.5$ (reste à récupérer) 🟡

Cycle 4 (Auto-reset si risque normal suffisant):
  Signal LONG @ 24.60
  Hedge @ 24.40 (distance = 0.20)
  Normal mode: 2% × 100$ = 2.0$ risk
  Check: 2.0$ < 0.3$ → FALSE! 2.0$ > 0.3$ ✅
  → Auto-reset recovery à 0$ (pas besoin d'override)
  Quantity: Normal (2.0$ risk via PERCENTAGE mode)

Cycle 5 (Recovery complète):
  Signal LONG @ 24.60
  Hedge @ 24.40 (distance = 0.20)
  Normal mode: 2% × 100$ = 2.0$ risk
  Check: 2.0$ < 2.5$ → Recovery needed
  Quantity: 2.5 / 0.20 = 12.5 (FIXED mode override)
  TP hit → Profit +2.5$
  Recovery: 2.5 - 2.5 = 0$ ✅ RESET COMPLET

Cycle 6 (Normal):
  Back to PERCENTAGE mode (3% risk)
```

**Configuration:**
```python
"LOSS_RECOVERY": {
    "ENABLED": True,                    # Activate/deactivate recovery
    "MAX_TIME_BETWEEN_TRADES": 30,     # Max seconds between trades
}
```

**Implementation details:**
- **API Endpoint**: `/fapi/v1/income` with `incomeType=REALIZED_PNL`
- **Data Source**: Closed positions (not individual trades) for accurate PNL
- **Grouping Logic**: Trades grouped by timestamp to consolidate positions
- **Position Detection**: Handles partial fills (multiple trades per position)
- **Storage**: `loss_recovery.json` file (auto-created)
- **Loading**: Automatic on bot startup
- **Accumulation**: Multiple consecutive losses are accumulated
- **Partial recovery**: Profit deducted from recovery amount
- **Complete recovery**: When recovery reaches 0$, back to normal mode
- **Override logic**: `_get_trade_quantity_with_recovery()` method
- **Fallback**: If recovery calculation fails, uses normal mode

**Key Features:**
- ✅ **Loss Accumulation**: 3$ + 2.5$ = 5.5$ total recovery
- ✅ **Partial Recovery**: 5.5$ - 3.0$ = 2.5$ remaining
- ✅ **Complete Recovery**: 2.5$ - 2.5$ = 0$ reset
- ✅ **Auto Reset**: If normal risk ≥ recovery, auto-reset (no override needed)
- ✅ **Persistent State**: Survives bot restarts via JSON
- ✅ **Smart Quantity**: Always calculates exact amount needed

**Current status:**
- ✅ Detection implemented
- ✅ PNL calculation working
- ✅ JSON persistence working
- ✅ FIXED mode override working
- ✅ Loss accumulation working
- ✅ Partial/complete recovery working
- ⏳ Margin insufficient handling (divide by 2) - TODO

## Signal Detection System

### 3-Step Sequential Logic
**Step 1: RSI Condition**
- **LONG**: All RSI periods (3, 5, 7) OVERSOLD simultaneously
- **SHORT**: All RSI periods (3, 5, 7) OVERBOUGHT simultaneously

**Step 2: HA Confirmation**
- **LONG**: Green HA candle after RSI oversold
- **SHORT**: Red HA candle after RSI overbought

**Step 3: Volume Validation** (optional)
- Current volume > average of last X candles (default: 14)
- Can be enabled/disabled in `SIGNAL_CONFIG`

### RSI Configuration
- **Period 3**: 10/90 thresholds (highly sensitive)
- **Period 5**: 20/80 thresholds (standard)
- **Period 7**: 30/70 thresholds (less sensitive)
- **Source**: HA-based RSI or normal RSI (configurable)

## Quantity System

### Current Configuration (PERCENTAGE Mode)
```python
TRADING_CONFIG = {
    "QUANTITY_MODE": "PERCENTAGE",     # Risk-based sizing
    "BALANCE_PERCENTAGE": 0.03,        # 3% of balance at risk
    "PROGRESSION_MODE": "STEP",        # Linear progression
}
```

### PERCENTAGE Mode Formula
```
Quantity = (Balance × Risk%) ÷ Distance_to_Hedge
```

**Example LONG** (LINKUSDC):
```
Balance: 100 USDC
Risk: 3% = 3 USDC
Signal Price: 24.50
Hedge Level: 24.30 (LOW - offset)
Distance: 0.20
Quantity: 3 ÷ 0.20 = 15 LINK
```

### Alternative Modes
- **MINIMUM**: Use symbol's minimum quantity (conservative)
- **FIXED**: Use custom fixed quantity
- **PERCENTAGE**: Risk percentage of balance (current)

## WebSocket Architecture

### Dual Stream Design
**Stream 1: Market Data** (`websocket_manager.py`)
- Purpose: Kline data for RSI/HA calculations
- Auto-reconnection: 100 attempts, 30s delays
- Target: `wss://fstream.binance.com/ws/{symbol}@kline_{timeframe}`

**Stream 2: User Data** (`user_data_manager.py`)
- Purpose: Order execution events
- Events: `ORDER_TRADE_UPDATE`, `ACCOUNT_UPDATE`
- Listen Key: Auto-create, refresh (30min), cleanup
- Target: `wss://fstream.binance.com/ws/{listenKey}`

### Event Processing
```
ORDER_TRADE_UPDATE (FILLED) → Route to OneOrMoreService
├── Signal Execution → Create Hedge + TP Signal
├── Hedge Execution → Update TP Signal + Create TP Hedge
└── TP Execution → Create Cross-Stop for other position
```

## Data Requirements
- **RSI**: 100 historical candles minimum
- **Heikin Ashi**: 50 historical candles
- **Volume validation**: Configurable lookback (default: 14)
- **Hedge analysis**: Configurable lookback (default: 5)

## Logging System
- **Location**: `logs/trading_bot.log`
- **Rotation**: 1MB max, 3 backups
- **Format**: Timestamp | Level | Module.Function | Message
- **Levels**: DEBUG (flow), INFO (actions), WARNING (abnormal), ERROR (exceptions)

## Code Quality Standards

### Architecture
- **KISS Principle**: Keep It Simple, Stupid
- **Single Responsibility**: One responsibility per file/function
- **Max Function Size**: 80 lines (split if longer)
- **No Over-engineering**: Simple solutions preferred

### Python Standards
- **PEP8 Strict**: Rigorous adherence
- **Type Hints**: Mandatory on all functions/methods/variables
- **No Unused Variables**: Variables must be used
- **Import Cleanup**: Remove unused imports
- **Pylance Compliance**: Fix all errors/warnings immediately

### Logging Standards
- **DEBUG**: Detailed function flow
- **INFO**: Important actions (start/end)
- **WARNING**: Abnormal but handled
- **ERROR**: Complete stack trace (`exc_info=True`)

## System Status

### Current Configuration (2025-10-05)
- **Strategy**: ONE_OR_MORE (active)
- **Symbol**: LINKUSDC @ 5m
- **Risk**: 3% of balance (PERCENTAGE mode)
- **Hedge Offset**: 0.001% from HIGH/LOW
- **TP System**: Asymmetric (0.5RR signal + 1.5RR hedge)
- **Trading Hours**: 5am-9pm EST (enabled)
- **Volume Validation**: Disabled
- **RSI**: HA-based calculation

### Production Features
- ✅ **Strategy Switching**: Change `STRATEGY_TYPE` in config + restart
- ✅ **WebSocket Detection**: Real-time order execution
- ✅ **Automatic Recovery**: State restoration on restart
- ✅ **Graceful Shutdown**: 3-level shutdown (Ctrl+C)
- ✅ **TP Preservation**: TPs not cancelled on shutdown
- ✅ **Zero Zombie Processes**: Clean file unlocking

### Other Available Strategies
Switch strategy via `config.py`:
- `CASCADE_MASTER`: Hedge + cascade + dynamic TP
- `ACCUMULATOR`: Simple accumulation + fixed TP
- `ALL_OR_NOTHING`: Single position + SL/TP + dynamic RSI exit
- `ONE_OR_MORE`: Current strategy (recommended)

## Troubleshooting

### If Strategy Not Working
1. Check `STRATEGY_CONFIG["STRATEGY_TYPE"]` = "ONE_OR_MORE"
2. Verify `ONE_OR_MORE_CONFIG["ENABLED"]` = True
3. Check logs for error messages
4. Verify API credentials in `.env`

### If No Signals Generated
1. Check RSI thresholds met (all 3 periods)
2. Verify HA confirmation candle appeared
3. Check volume validation (if enabled)
4. Verify trading hours (if enabled)

### If WebSocket Issues
1. Check connection to Binance
2. Verify Listen Key creation
3. Review logs for WebSocket errors
4. Check network connectivity

### Emergency Reset
```bash
# Stop bot (Ctrl+C)
# Close all positions manually on Binance
# Restart bot
python trading_bot.py
```

## Monitoring

### Check Strategy Status
```bash
# View logs
tail -f logs/trading_bot.log

# Search for strategy initialization
grep "Strategy active: ONE_OR_MORE" logs/trading_bot.log

# Monitor order executions
grep "ORDER_TRADE_UPDATE" logs/trading_bot.log | tail -20
```

### Track Positions
```bash
# View position recovery
grep "Position.*restored" logs/trading_bot.log

# Check TP creation
grep "TP.*created" logs/trading_bot.log | tail -10

# Monitor cross-stops
grep "cross-stop" logs/trading_bot.log
```

## Important Notes

### Configuration Changes
- Changes to `config.py` require bot restart
- Active positions preserved during restart
- TPs automatically recovered if missing

### Shutdown Behavior
- First Ctrl+C: Graceful shutdown with cleanup
- Second Ctrl+C: Force shutdown
- Third Ctrl+C: Brutal termination
- **TPs are PRESERVED** (not cancelled)

### Risk Management
- Position size calculated from balance and distance to hedge
- Maximum exposure: BALANCE_PERCENTAGE × Balance
- Hedge provides natural stop-loss at support/resistance
- Cross-stops guarantee 1RR when one TP hits

### Production Deployment
- Test on testnet first
- Start with small BALANCE_PERCENTAGE (1-3%)
- Monitor first few trades closely
- Enable trading hours restriction for safety
- Keep logs for analysis
