# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based **Binance futures trading bot** that connects to real-time WebSocket streams to calculate RSI and Heikin Ashi indicators. The bot displays trading signals when candles close, using a modular service-oriented architecture with single responsibility principles.

## Core Architecture

### Service-Oriented Design
The bot follows a **layered architecture** where each component has a single responsibility:

- **`trading_bot.py`**: Main orchestrator that coordinates all services and handles WebSocket message processing
- **Strategy Layer** (`strategies/`): Trading strategy implementations and management (StrategyManager, CascadeMaster, Accumulator)
- **Service Layer** (`core/`): Business logic orchestration (RSIService, HAService, SignalService, TradingService, CascadeService, AccumulatorService)  
- **Indicator Layer** (`indicators/`): Pure calculation logic (RSI, Heikin Ashi)
- **API Layer** (`api/`): External service communication (Binance REST API, market data)
- **WebSocket Layer** (`websocket/`): Dual WebSocket streams (klines + User Data Stream) with auto-reconnection

### Key Integration Pattern
The bot triggers calculations **only on candle close events** detected through WebSocket kline streams:
1. WebSocket receives kline data → `_handle_kline_message()`
2. On candle close → `_calculate_and_display_rsi()` 
3. RSI calculation → `_calculate_and_display_ha()`
4. Display both RSI values and HA candle color with emojis
5. Process signal detection → `_process_signal_detection()`
6. Execute trade via strategy manager → `StrategyManager.execute_signal()`
7. Strategy-specific execution:
   - **CASCADE_MASTER**: Full trading system (hedge + cascade + TP)
   - **ACCUMULATOR**: Simple orders with accumulation logic
8. Real-time order execution detection via User Data Stream → `UserDataStreamManager`

## Common Commands

### Setup and Running
```bash
# Install dependencies
pip install pandas numpy requests websockets python-dotenv

# Create .env file with Binance API credentials
# BINANCE_API_KEY=your_api_key  
# BINANCE_SECRET_KEY=your_secret_key

# Run the bot
python trading_bot.py
```

### Configuration
- **Trading parameters**: Modify `config.py` (symbol, timeframe, RSI thresholds)
- **RSI calculation mode**: Set `RSI_ON_HA` in `SIGNAL_CONFIG` (True for HA-based RSI, False for normal RSI)
- **Quantity system**: Configure `TRADING_CONFIG` with dual parameters (quantity mode + progression mode)
- **Logging levels**: Adjust `LOGGING_CONFIG` in `config.py`
- **Reconnection settings**: Configure `RECONNECTION_CONFIG` for WebSocket resilience
- **Hedging system**: Configure `HEDGING_CONFIG` for automatic hedge orders
- **Cascade trading**: Configure `CASCADE_CONFIG` for advanced cascade system

## Key Technical Details

### RSI Configuration
The bot calculates **multiple RSI periods** with different sensitivity thresholds:
- RSI period 3 candles: 10/90 thresholds (highly sensitive)
- RSI period 5 candles: 20/80 thresholds (standard)  
- RSI period 7 candles: 30/70 thresholds (less sensitive)

**RSI Calculation Methods**:
- **Normal RSI** (`RSI_ON_HA: False`): RSI calculated on regular candle close prices
- **Heikin Ashi RSI** (`RSI_ON_HA: True`): RSI calculated on Heikin Ashi close prices for smoother signals

### Data Requirements
- **RSI calculations**: Requires 100 historical candles minimum
- **Heikin Ashi calculations**: Requires 50 historical candles
- **WebSocket stream**: `{symbol}@kline_{timeframe}` format
- **Hedging analysis**: Configurable lookback candles for high/low detection

### WebSocket Connection Management
The bot uses **dual WebSocket streams** for maximum responsiveness:

**Kline Stream** (`websocket_manager.py`):
- **Purpose**: Real-time price data and candle close detection
- **Auto-reconnection**: Up to 100 attempts with 30-second delays
- **Connection health**: 3600-second timeout monitoring
- **Target**: `wss://fstream.binance.com/ws/{symbol}@kline_{timeframe}`

**User Data Stream** (`user_data_manager.py`):
- **Purpose**: Real-time order execution detection for cascade system
- **Listen Key**: Automatic creation, refresh (30min), and cleanup
- **Events**: `ORDER_TRADE_UPDATE`, `ACCOUNT_UPDATE`
- **Target**: `wss://fstream.binance.com/ws/{listenKey}`
- **Instant Detection**: Hedge and cascade order executions in real-time

## Logging System

Comprehensive logging with file rotation:
- **Location**: `logs/trading_bot.log`
- **Rotation**: 1MB max size, 3 backup files
- **Module-specific loggers**: Each component uses `get_module_logger()`
- **Format**: Timestamp | Level | Module.Function | Message

## Trading Strategies

The bot implements **two distinct trading strategies** with automatic switching via configuration:

### Strategy Selection
```python
# In config.py - Current configuration
STRATEGY_CONFIG = {
    "STRATEGY_TYPE": "ACCUMULATOR",  # Currently active strategy
}
```

**Available Strategies**:
- `"CASCADE_MASTER"` - Advanced strategy with hedge + cascade + dynamic TP
- `"ACCUMULATOR"` - Simple strategy with position accumulation + fixed TP

**Strategy Switching**: Change `STRATEGY_TYPE` in config and restart the bot.

### CASCADE_MASTER Strategy (Advanced)
**Full-featured strategy** with hedge protection and cascade trading:

**Workflow**:
1. **Signal detected** → Market order execution
2. **Hedge creation** → Stop order at support/resistance 
3. **TP system** → Dynamic take profit levels with linear progression
4. **Cascade trading** → Alternating orders with increasing quantities
5. **Real-time management** → WebSocket-driven execution detection

**Features**:
- ✅ **Hedge orders** for risk management
- ✅ **Cascade system** with up to 10 orders
- ✅ **Advanced TP** with position-based increments
- ✅ **Real-time execution** via User Data Stream

### ACCUMULATOR Strategy (Simple)
**Position accumulation** with average price management:

**Workflow**:
1. **Signal detected** → Market order execution (same quantity)
2. **Price averaging** → Retrieve average position price via API
3. **TP update** → Single TP at ±0.3% from average price
4. **Accumulation** → Repeat process for multiple signals (max 10)
5. **Independent sides** → LONG and SHORT positions in parallel

**Features**:
- ❌ **No hedge orders** (direct exposure)
- ❌ **No cascade system** (simple accumulation)
- ✅ **Simple TP** at fixed percentage from average
- ✅ **Position averaging** via Binance API

**Configuration**:
```python
ACCUMULATOR_CONFIG = {
    "ENABLED": True,
    "TP_PERCENT": 0.003,       # 0.3% TP from average price (updated)
    "MAX_ACCUMULATIONS": 10,   # Max positions per side
    "PRICE_OFFSET": 0.001,     # 0.1% trigger offset
}
```

## Trading Signal System

### 2-Step Sequential Signal Logic
The bot implements a **sequential signal detection system** requiring two distinct phases:

**Step 1: RSI Condition**
- **LONG Signal**: All 3 RSI periods (3, 5, 7) must be **OVERSOLD** simultaneously
- **SHORT Signal**: All 3 RSI periods (3, 5, 7) must be **OVERBOUGHT** simultaneously
- **RSI Source**: Calculated on regular candle prices or Heikin Ashi prices depending on `RSI_ON_HA` setting

**Step 2: HA Confirmation** (after RSI condition is met)
- **LONG Confirmation**: Green HA candle after RSI oversold
- **SHORT Confirmation**: Red HA candle after RSI overbought

### Signal State Machine
- **WAITING**: Monitoring for RSI conditions
- **RSI_CONDITION_MET**: RSI satisfied, waiting for HA confirmation
- **SIGNAL_CONFIRMED**: Complete signal validated and ready for trading

**Important**: The two steps must be **sequential**, not simultaneous. Once HA confirmation is received, the signal remains valid even if RSI values exit oversold/overbought zones.

### Signal Blocking Logic
The bot implements **comprehensive signal blocking** to prevent conflicting trades:

**Cascade Active Block**: New signals are blocked while cascade trading is active
- Check: `cascade_service.is_cascade_active()`
- Purpose: Prevent multiple concurrent cascade cycles

**TP Active Block**: New signals are blocked while Take Profit orders are active
- Check: `tp_service.get_tp_status()` for active LONG or SHORT TPs
- Purpose: Prevent new signals until current TPs are reached or cancelled
- **Critical**: Ensures system waits for TP resolution before starting new trading cycles

### Heikin Ashi Display
- **Green 🟢**: Bullish HA candle (HA_close > HA_open)
- **Red 🔴**: Bearish HA candle (HA_close < HA_open)  
- **White ⚪**: Doji HA candle (HA_close = HA_open)

## Advanced Trading Features

### Automated Hedging System
The bot includes **automatic hedge order creation** after each signal execution:

**Hedge Logic**:
- **LONG signal** → Creates SHORT hedge with stop at recent highest price
- **SHORT signal** → Creates LONG hedge with stop at recent lowest price
- **Quantity**: Configurable multiplier (default: 2x original order size)
- **Analysis period**: Configurable lookback candles for high/low detection

**Hedge Configuration** (`HEDGING_CONFIG`):
- `ENABLED`: Enable/disable automatic hedging
- `LOOKBACK_CANDLES`: Number of candles for high/low analysis
- `QUANTITY_MULTIPLIER`: Size multiplier for hedge orders

### Cascade Trading System
The bot features an **advanced real-time cascade trading system** with instant WebSocket order execution detection:

**Cascade Logic** (100% WebSocket-driven):
- **Step 1**: Signal triggers initial order + hedge (as above)
- **Step 2**: User Data Stream detects hedge execution → **Instantly** create opposite cascade order
- **Step 3**: Each cascade execution → **Instantly** create next alternating order
- **Formula**: `Next quantity = (2 × Triggered quantity) - Existing quantity same side`
- **Speed**: Sub-second reaction time vs previous 30-second polling

**Example Sequence**:
```
Signal LONG: BUY 0.001 @ 111200 → Hedge: SELL 0.002 @ 111000
Hedge executes → LONG 0.003 @ 111200 (stop)
LONG executes → SHORT 0.006 @ 111000 (stop)  
SHORT executes → LONG 0.012 @ 111200 (stop)
... continues alternating with increasing quantities
```

**Cascade Configuration** (`CASCADE_CONFIG`):
- `ENABLED`: Enable/disable cascade trading system
- `MAX_ORDERS`: Maximum number of cascade orders (default: 4)
- `RETRY_ATTEMPTS`: Retry count for failed orders (excluding insufficient funds)
- `RETRY_DELAY_SECONDS`: Delay between retry attempts

### Take Profit (TP) System
The bot includes **automatic Take Profit management** with dynamic price adjustments:

**TP Logic** (New Linear System):
- **Distance Calculation**: `distance = |initial_price - hedge_price|`
- **Linear Multiplier**: Position count × base multiplier (1x, 2x, 3x, 4x...)
- **TP LONG**: `initial_price + (distance × position_count) × (1 + 0.1%)`
- **TP SHORT**: `hedge_price - (distance × position_count) × (1 - 0.1%)`
- **Position Progression**: Signal=1x, Hedge=2x, Cascade1=3x, Cascade2=4x...
- **Parallel Management**: Separate TP orders for LONG and SHORT positions with same position count

**TP Configuration** (`TP_CONFIG`):
- `ENABLED`: Enable/disable automatic TP system
- `BASE_MULTIPLIER`: Base distance multiplier (default: 1.0, grows linearly)
- `POSITION_INCREMENT`: Percentage increment applied to final TP price (default: 0.001 = 0.1%)
- `PRICE_OFFSET`: Offset between stop price and limit price for trigger (default: 0.001 = 0.1%)

**TP Updates**:
- **After signal execution**: Creates initial TP for signal side (position count = 1)
- **After hedge execution**: Creates TP for hedge side (position count = 2) 
- **After cascade execution**: Updates both TPs with incremented position count (3x, 4x...)
- **Cross-side updates**: Each cascade execution updates both LONG and SHORT TPs with same position count
- **Single increment per cascade**: Position count incremented only once per cascade, shared by both TPs

**TP Order Structure** (Corrected Logic):
- **Limit Price**: Exact TP value calculated by the system (where you want to sell/buy)
- **Stop Price**: Trigger price with slight offset from limit price for order activation
  - **LONG TP** (SELL order): `stop = limit × (1 - 0.1%)` (trigger below limit)
  - **SHORT TP** (BUY order): `stop = limit × (1 + 0.1%)` (trigger above limit)

**TP Reference Price Logic**:
- **Signal side TP**: Uses initial signal execution price as reference
- **Hedge side TP**: Uses hedge stop price as reference
- **Example**: Signal LONG @50000, Hedge SHORT @49800
  - **TP LONG** (signal side): Based on 50000 (signal price)
  - **TP SHORT** (hedge side): Based on 49800 (hedge price)

**Complete TP Update Cycle Example**:
Signal LONG @50000, Hedge SHORT @49800, Distance=200:

1. **Signal execution** (pos=1): 
   - TP LONG = (50000 + 200×1) × 1.001 = 50250.2
2. **Hedge execution** (pos=2):
   - TP LONG = (50000 + 200×2) × 1.001 = 50450.4
   - TP SHORT = (49800 - 200×2) × 0.999 = 49350.6
3. **Cascade 1** (pos=3):
   - TP LONG = (50000 + 200×3) × 1.001 = 50650.6
   - TP SHORT = (49800 - 200×3) × 0.999 = 49150.8
4. **Cascade 2** (pos=4):
   - TP LONG = (50000 + 200×4) × 1.001 = 50850.8
   - TP SHORT = (49800 - 200×4) × 0.999 = 48951.0

**WebSocket Implementation**:
- **Event Detection**: `ORDER_TRADE_UPDATE` with `o.X = "FILLED"` status
- **Real-time Processing**: `_process_hedge_execution_async()` and `_process_cascade_execution_async()`
- **Price Recovery**: Automatic retrieval of initial order prices via API
- **State Management**: Instant CASCADE state updates (WAITING_HEDGE → ACTIVE → STOPPED)

**Key Features**:
- **Permanent Stop Levels**: Uses execution prices of first two orders as reference points
- **Signal Blocking**: Prevents new signals while cascade is active
- **Real-time Monitoring**: Instant cascade status display with position tracking
- **Automatic Termination**: Stops at MAX_ORDERS limit or on critical errors
- **Zero Latency**: WebSocket-driven execution detection (vs. polling-based systems)
- **Robust Error Handling**: Advanced retry system with insufficient funds detection

### Cascade Error Robustness
The cascade system includes **advanced error handling** for production reliability:

**Error Classification**:
- **Insufficient Funds**: `"Margin is insufficient"` errors → Stop cascade, wait for TP execution
- **Temporary Errors**: Network, API rate limits → Automatic retry with exponential backoff
- **Permanent Errors**: Invalid symbols, account issues → Stop cascade after max attempts

**Cascade States**:
- `INACTIVE`: No cascade running, ready for new signals
- `WAITING_HEDGE`: Waiting for initial hedge order execution
- `ACTIVE`: Cascade running, creating alternating orders
- `WAITING_TP`: Insufficient funds detected, waiting for TP to free capital
- `STOPPED`: Cascade terminated (max orders, persistent errors, manual stop)

**Retry Logic** (Using `RECONNECTION_CONFIG`):
- **Max Attempts**: 100 retries for non-insufficient-funds errors
- **Delay**: 30 seconds between retry attempts
- **Insufficient Funds**: No retry, immediate transition to `WAITING_TP` state
- **TP Execution**: Resets system from `WAITING_TP` back to `INACTIVE` for new cycle

**Error Logging**:
- Detailed error classification with error type and message
- Position context logging (current LONG/SHORT quantities)
- Retry attempt tracking with countdown display

### Position Management
- **Hedge Mode**: Uses Binance hedge mode with position sides (LONG/SHORT)
- **Order Types**: MARKET orders for signals, STOP_MARKET orders for hedges and cascade
- **Price Recovery**: Retrieves execution prices via API for accuracy
- **Quantity Management**: Flexible dual-parameter system (quantity calculation + progression mode) with dynamic balance detection

## Trading Quantity Configuration

The bot supports a flexible quantity system with two independent parameters:

### Quantity Calculation Modes

**QUANTITY_MODE**: Determines how the initial trading quantity is calculated

#### Minimum Quantity Mode
```python
TRADING_CONFIG: Dict[str, Any] = {
    "QUANTITY_MODE": "MINIMUM",  # Use symbol's minimum quantity
    "INITIAL_QUANTITY": 0.002,  # Ignored in this mode
    "BALANCE_PERCENTAGE": 0.01,  # Ignored in this mode
    "PROGRESSION_MODE": "STEP",  # How cascade progresses
}
```
- Uses the symbol's minimum trading quantity from Binance
- Automatically complies with symbol's lot size requirements
- Conservative approach ensuring all trades are valid

#### Fixed Quantity Mode
```python
TRADING_CONFIG: Dict[str, Any] = {
    "QUANTITY_MODE": "FIXED",  # Use custom fixed quantity
    "INITIAL_QUANTITY": 0.002,  # Your desired starting quantity
    "BALANCE_PERCENTAGE": 0.01,  # Ignored in this mode
    "PROGRESSION_MODE": "STEP",  # How cascade progresses
}
```
- Uses a custom fixed quantity as starting amount
- Still respects symbol's step size for proper formatting
- Allows for larger initial positions and custom risk management

#### Percentage-Based Quantity Mode (Advanced Risk Management)
```python
TRADING_CONFIG: Dict[str, Any] = {
    "QUANTITY_MODE": "PERCENTAGE",  # Risk percentage of balance
    "INITIAL_QUANTITY": 0.002,  # Ignored in this mode
    "BALANCE_PERCENTAGE": 0.01,  # 1% of balance at risk
    "PROGRESSION_MODE": "STEP",  # How cascade progresses
}
```
- **Advanced risk management**: Calculates quantity based on percentage of available balance
- **Dynamic balance detection**: Automatically uses the correct quote asset (USDC for BTCUSDC, USDT for ETHUSDT, etc.)
- **Formula**: `Quantity = (Balance × Percentage) ÷ |Signal_Price - Hedge_Price|`
- **Risk control**: You risk exactly the specified percentage on the price difference between signal and hedge
- **Fallback safety**: If balance is insufficient or unavailable, automatically falls back to minimum quantity

**Price Difference Calculation**:
- **Signal LONG**: Hedge price = LOW minimum of last 5 candles (support level)
- **Signal SHORT**: Hedge price = HIGH maximum of last 5 candles (resistance level)
- **Logic**: Risk is calculated on the distance to the natural stop-loss level

**Example Calculation**:
```
Balance USDC: 100.0
Risk Percentage: 1.0% = 1.0 USDC at risk
Signal Price: 110,860.0 USDC
Hedge Price: 110,790.0 USDC (resistance for SHORT signal)
Price Difference: 70.0 USDC
Calculated Quantity: 1.0 ÷ 70.0 = 0.0143 BTC
```

### Cascade Progression Modes

**PROGRESSION_MODE**: Determines how cascade order quantities progress

#### Double Progression (Exponential Growth)
```python
"PROGRESSION_MODE": "DOUBLE"
```
- **Logic**: Each cascade order doubles the position to maintain alternating advantage
- **Formula**: `Next_Order = (2 × Triggered_Quantity) - Existing_Same_Side`
- **Growth pattern**: 0.01 → 0.02 → 0.04 → 0.08 → 0.16...
- **Advantages**: Rapid position scaling, higher profit potential
- **Risk**: Exponential capital requirement

**Example DOUBLE progression**:
```
Signal LONG: 0.01 BTC
Hedge SHORT: 0.02 BTC (2x signal)
Cascade LONG: 0.03 BTC (to reach net 0.04 LONG vs 0.02 SHORT)
Cascade SHORT: 0.06 BTC (to reach net 0.08 SHORT vs 0.04 LONG)
Cascade LONG: 0.12 BTC (to reach net 0.16 LONG vs 0.08 SHORT)
```

#### Step Progression (Linear Growth)
```python
"PROGRESSION_MODE": "STEP"
```
- **Logic**: Each cascade order increments position by a fixed step size
- **Formula**: `Next_Order = (Current_Opposite + Step) - Current_Same_Side`
- **Growth pattern**: 0.01 → 0.02 → 0.03 → 0.04 → 0.05...
- **Step size**: Automatically determined from initial signal quantity
- **Advantages**: Controlled risk, predictable capital requirement
- **Risk**: Slower position scaling

**Example STEP progression**:
```
Signal LONG: 0.01 BTC (step = 0.01)
Hedge SHORT: 0.02 BTC
Cascade LONG: 0.01 BTC (to reach net 0.02 LONG vs 0.02 SHORT) 
Cascade SHORT: 0.01 BTC (to reach net 0.02 SHORT vs 0.03 LONG)
Cascade LONG: 0.01 BTC (to reach net 0.04 LONG vs 0.03 SHORT)
```

### Configuration Combinations

The two parameters work independently, allowing flexible strategies:

```python
# Conservative fixed-step strategy
"QUANTITY_MODE": "MINIMUM", "PROGRESSION_MODE": "STEP"

# Aggressive fixed-double strategy  
"QUANTITY_MODE": "FIXED", "PROGRESSION_MODE": "DOUBLE"

# Advanced risk-managed step strategy
"QUANTITY_MODE": "PERCENTAGE", "PROGRESSION_MODE": "STEP"

# High-risk percentage-double strategy
"QUANTITY_MODE": "PERCENTAGE", "PROGRESSION_MODE": "DOUBLE"
```

## WebSocket Architecture Details

### Dual Stream Design
The bot implements a **sophisticated dual WebSocket architecture** for maximum performance:

**Stream 1: Market Data** (`WebSocketManager`)
- **Purpose**: Kline data for technical analysis
- **Triggers**: RSI/HA calculations on candle close
- **Reconnection**: Robust with exponential backoff
- **Error Handling**: Comprehensive logging and recovery

**Stream 2: User Data** (`UserDataStreamManager`)  
- **Purpose**: Order execution events for trading automation
- **Events**: `ORDER_TRADE_UPDATE`, `ACCOUNT_UPDATE`
- **Authentication**: Listen Key lifecycle management
- **Processing**: Instant cascade triggers via `ORDER_TRADE_UPDATE`

### Event Processing Flow
```
ORDER_TRADE_UPDATE → Filter FILLED status → Identify order type → Route to handler
├── Hedge Order → _process_hedge_execution_async() → Create first cascade order
└── Cascade Order → _process_cascade_execution_async() → Create next cascade order
```

### Listen Key Management
- **Creation**: Automatic via `create_listen_key()` API call
- **Refresh**: Every 30 minutes via keep-alive mechanism  
- **Cleanup**: Proper closure on bot shutdown
- **Error Recovery**: Automatic recreation on connection failures

### Message Structure (Binance Futures)
Key fields from `ORDER_TRADE_UPDATE` events:
- `o.i`: Order ID for identification
- `o.X`: Order Status (`NEW`, `FILLED`, `CANCELED`, etc.)
- `o.x`: Execution Type (`NEW`, `TRADE`, `CANCELED`, etc.)
- `o.S`: Side (`BUY`/`SELL`)
- `o.z`: Cumulative filled quantity
- `o.L`: Last executed price
- `o.ps`: Position side (`LONG`/`SHORT`/`BOTH`)

## Architecture Principles

### Single Responsibility
- **Services** (`core/`): Orchestrate data retrieval + calculations
- **Indicators** (`indicators/`): Pure mathematical calculations
- **Clients** (`api/`): External API communication only

### Error Resilience
- WebSocket auto-reconnection with exponential backoff
- Comprehensive exception handling in all service methods
- Detailed error logging with stack traces
- Symbol information caching to reduce API calls

### Configuration-Driven
All operational parameters externalized to `config.py`:
- Trading symbols and timeframes
- API endpoints and WebSocket URLs
- Signal detection thresholds and RSI calculation mode
- Quantity system with dual parameters (calculation modes + progression modes)
- Logging and reconnection settings
- Hedging system parameters

When modifying the bot, maintain this separation of concerns and ensure all changes preserve the single-responsibility principle across modules.

## Code Quality Standards

### Architecture & Design
- **Principle KISS**: Keep It Simple, Stupid - always prefer the simplest solution
- **Single responsibility**: One responsibility per file AND per function
- **Function size**: Maximum 80 lines per function, split if longer
- **Avoid over-engineering**: No premature abstractions
- **Code simplicity**: Simple and readable code over complex solutions

### Python Standards
- **PEP8 strict**: Rigorous adherence to Python style conventions
- **Self-documenting code**: Explicit variable/function names
- **Type hints complete**: Mandatory type annotations on all functions, methods, and variables
- **Variable usage**: Variables must be used after declaration (no unused variables)
- **Import management**: Remove unused imports systematically
- **Consistent typing**: Type hints throughout each file

### Pylance Compliance
- **Immediate fixes**: Correct all Pylance errors/warnings immediately
- **Type ignore policy**: No `type: ignore` without justification comments

### Logging & Debugging Standards
- **Detailed logging in each module**: Every file must have comprehensive logging
- **DEBUG**: Detailed function flow information
- **INFO**: Important actions (start/end of operations)
- **WARNING**: Abnormal but handled situations
- **ERROR**: Complete stack trace for exceptions (use `exc_info=True`)
- **Format**: timestamp | level | module.function | detailed message

### Maintenance Rules
- **Test file cleanup**: Always remove temporary test files
- **Minimal abstractions**: Only add abstractions when truly necessary

## System Status & Recent Changes

### Current Configuration (2025-09-08)
- **Active Strategy**: `ACCUMULATOR` (simple accumulation strategy)
- **TP Percentage**: 0.3% from average position price
- **Max Accumulations**: 10 positions per side (LONG/SHORT)
- **Symbol**: `BTCUSDC` on 5-minute timeframe
- **RSI Periods**: 3/5/7 with thresholds 10/20/30 - 90/80/70

### Strategy System Architecture ✅
```
🏗️ Strategy Pattern Implementation
├── strategies/
│   ├── base_strategy.py           # Abstract strategy interface
│   ├── cascade_master_strategy.py # Advanced strategy (hedge+cascade+TP)
│   ├── accumulator_strategy.py    # Simple strategy (accumulation+TP)
│   ├── strategy_factory.py        # Strategy creation factory
│   └── strategy_manager.py        # Strategy orchestration manager
├── core/
│   └── accumulator_service.py     # Position accumulation service
└── trading_bot.py                 # Integrated with StrategyManager
```

### Recent Fixes ✅
1. **Strategy Integration**: Successfully integrated strategy pattern into main bot
2. **ACCUMULATOR Corrections**: Fixed `get_initial_trade_quantity()` calls with missing `symbol` parameter
3. **Configuration Updates**: TP percentage adjusted from 1% to 0.3% for better performance
4. **Strategy Switching**: Verified CASCADE_MASTER ↔ ACCUMULATOR switching works correctly

### Take Profit Orders
Both strategies use **TAKE_PROFIT** order type (limit orders with trigger):
- **Order Type**: `"TAKE_PROFIT"` (not MARKET orders)
- **Stop Price**: Trigger level with small offset (±0.1%)  
- **Limit Price**: Exact TP target price
- **Execution**: Triggered when price reaches stop, executes at limit price

### Validated Features ✅
- ✅ **Strategy switching** between CASCADE_MASTER and ACCUMULATOR
- ✅ **ACCUMULATOR**: Simple orders without hedge/cascade systems
- ✅ **CASCADE_MASTER**: Full hedge + cascade + advanced TP preserved
- ✅ **Take Profit**: Both strategies use proper TAKE_PROFIT limit orders
- ✅ **Configuration**: Real-time strategy selection via config changes
- ✅ **Error Handling**: Comprehensive logging and error recovery