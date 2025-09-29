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
2. On candle close → Extract volume and update volume history → `_calculate_and_display_rsi()`
3. RSI calculation → `_calculate_and_display_ha()`
4. Display both RSI values and HA candle color with emojis
5. Process signal detection with volume validation → `_process_signal_detection()`
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
- **Volume validation**: Configure `VOLUME_VALIDATION` in `SIGNAL_CONFIG` (enable/disable + lookback candles)
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

### Volume Validation Configuration
The bot includes **optional volume validation** to filter signals based on trading volume:

**Volume Logic**:
- **Validation Check**: Confirmation candle volume must exceed average volume of previous candles
- **Real Volume Data**: Uses actual kline volume data (not calculated values)
- **Automatic History**: Maintains rolling window of volume data for comparison
- **Fallback Behavior**: Allows signals if insufficient volume history available

**Configuration** (`SIGNAL_CONFIG.VOLUME_VALIDATION`):
```python
"VOLUME_VALIDATION": {
    "ENABLED": True,          # Enable/disable volume validation
    "LOOKBACK_CANDLES": 14,   # Number of previous candles for average calculation
}
```

**Volume Workflow**:
1. **History Update**: Each closed candle volume added to rolling history
2. **Validation Trigger**: During HA confirmation step, current volume compared to average
3. **Signal Impact**: Volume below average → Signal rejected, above average → Signal proceeds
4. **Logging**: Detailed volume comparison logged for monitoring

### Data Requirements
- **RSI calculations**: Requires 100 historical candles minimum
- **Heikin Ashi calculations**: Requires 50 historical candles
- **Volume validation**: Requires configurable lookback candles for average calculation (default: 14)
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

The bot implements **three distinct trading strategies** with automatic switching via configuration:

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
- `"ALL_OR_NOTHING"` - Risk management strategy with automatic Stop Loss + fixed TP

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
    "TP_PERCENT": 0.003,       # 0.3% TP from average price
    "MAX_ACCUMULATIONS": 20,   # Max positions per side (updated from 10)
    "PRICE_OFFSET": 0.001,     # 0.1% trigger offset
}
```

### ALL_OR_NOTHING Strategy (Risk Management)
**Risk-controlled strategy** with automatic Stop Loss and fixed Take Profit:

**Workflow**:
1. **Signal detected** → Check existing positions for same side
2. **Position validation** → If no existing position for this side, proceed
3. **Market order execution** → Entry at market price
4. **Stop Loss creation** → Automatic SL with retry mechanism (5 attempts max)
5. **Take Profit creation** → Fixed TP with retry mechanism (5 attempts max)
6. **WebSocket monitoring** → Real-time SL/TP execution detection
7. **Cross-cancellation** → When SL/TP touched, cancel corresponding order
8. **Position reset** → Ready for new signals after SL/TP execution

**Features**:
- ❌ **No hedge orders** (uses SL for risk management)
- ❌ **No cascade system** (single position per side)
- ✅ **Single position per side** (max 1 LONG + 1 SHORT simultaneously)
- ✅ **Position blocking** (ignore signals if same side position exists)
- ✅ **Automatic Stop Loss** based on market structure with distance-based risk calculation
- ✅ **Fixed Take Profit** percentage from entry
- ✅ **Cross-cancellation** SL↔TP when either is executed
- ✅ **Retry mechanism** for order creation failures (5 attempts)
- ✅ **Real-time monitoring** via User Data Stream

**Stop Loss Logic**:
- **LONG SL**: LOW minimum of last 5 candles - 0.5% offset (updated from 0.1%)
- **SHORT SL**: HIGH maximum of last 5 candles + 0.5% offset (updated from 0.1%)
- **Automatic calculation**: Uses actual candle HIGH/LOW data
- **Market-based**: SL levels follow natural support/resistance

**Take Profit Logic**:
- **LONG TP**: Entry price + 0.3% (updated from 0.5%)
- **SHORT TP**: Entry price - 0.3% (updated from 0.5%)
- **Fixed percentage**: Consistent profit target regardless of market conditions

**Configuration**:
```python
ALL_OR_NOTHING_CONFIG = {
    "ENABLED": True,
    "SL_LOOKBACK_CANDLES": 5,    # Candles for HIGH/LOW analysis
    "SL_OFFSET_PERCENT": 0.005,  # 0.5% SL offset from HIGH/LOW (updated from 0.1%)
    "TP_PERCENT": 0.003,         # 0.3% TP from entry price (only if dynamic RSI disabled)
    "PRICE_OFFSET": 0.001,       # 0.1% trigger offset for orders
    "DYNAMIC_RSI_EXIT": {
        "ENABLED": True,         # Enable/disable dynamic RSI-based exit
        "MONITOR_FREQUENCY": "candle_close",  # Monitor on each candle close
        "EXIT_TYPE": "MARKET",   # Exit order type (MARKET for immediate execution)
        "CANCEL_FIXED_ORDERS": True,  # Cancel SL after RSI exit (TP not created in dynamic mode)
    }
}
```

**Cross-Cancellation Logic**:
- **When SL executed**: Automatically cancel corresponding TP order for same side
- **When TP executed**: Automatically cancel corresponding SL order for same side
- **Independent sides**: LONG and SHORT positions managed separately
- **Examples**:
  - SL LONG touched → Cancel TP LONG (SHORT position/orders unaffected)
  - TP SHORT touched → Cancel SL SHORT (LONG position/orders unaffected)

**Position Management**:
- **Single position limit**: Maximum 1 position per side (1 LONG + 1 SHORT max)
- **Signal blocking**: New signals ignored if position already exists for same side
- **Position reset**: After SL/TP execution, ready to accept new signals for that side
- **Order creation retry**: Up to 5 attempts for SL and TP creation, system stops if all fail

### **Dynamic RSI-Based Exit Feature**

The ALL_OR_NOTHING strategy includes an advanced **Dynamic Take Profit** system based on RSI momentum:

**Dynamic Exit Logic**:
- **LONG Position** → Exit when **ALL RSI periods are OVERBOUGHT** (RSI_3≥90 AND RSI_5≥80 AND RSI_7≥70)
- **SHORT Position** → Exit when **ALL RSI periods are OVERSOLD** (RSI_3≤10 AND RSI_5≤20 AND RSI_7≤30)

**Key Features**:
- **Replaces Fixed TP**: When enabled, NO fixed TP is created (only SL for protection)
- **Real-time Monitoring**: Checks RSI conditions on every closed candle
- **Market Order Exit**: Immediate MARKET order when conditions are met
- **Automatic SL Cancellation**: SL cancelled after successful RSI exit

**Workflow with Dynamic RSI Exit**:
```
1. Signal LONG detected → Position created + SL created (NO fixed TP)
2. Real-time RSI monitoring on each candle close
3. Candle closes with: RSI_3=91, RSI_5=82, RSI_7=72
4. 🎯 ALL CONDITIONS MET → Immediate MARKET SELL order
5. ✅ Position closed + SL automatically cancelled
6. 🔄 Ready for new signals
```

**Configuration Options**:
- **ENABLED**: `True` = Dynamic RSI exit, `False` = Fixed TP at 0.3%
- **MONITOR_FREQUENCY**: Always "candle_close" for optimal timing
- **EXIT_TYPE**: "MARKET" for immediate execution
- **CANCEL_FIXED_ORDERS**: Auto-cancel SL after RSI exit

**Risk Profile**:
- **Adaptive**: Exit based on market momentum rather than fixed percentage
- **Market-driven**: Follows RSI overbought/oversold conditions
- **SL Protection**: Maintains stop-loss for risk management
- **No Fixed Ceiling**: Can capture larger moves when momentum persists
- **Risk-controlled**: Distance-based position sizing to SL level

## Trading Signal System

### 3-Step Sequential Signal Logic
The bot implements a **sequential signal detection system** requiring three distinct validations:

**Step 1: RSI Condition**
- **LONG Signal**: All 3 RSI periods (3, 5, 7) must be **OVERSOLD** simultaneously
- **SHORT Signal**: All 3 RSI periods (3, 5, 7) must be **OVERBOUGHT** simultaneously
- **RSI Source**: Calculated on regular candle prices or Heikin Ashi prices depending on `RSI_ON_HA` setting

**Step 2: HA Confirmation** (after RSI condition is met)
- **LONG Confirmation**: Green HA candle after RSI oversold
- **SHORT Confirmation**: Red HA candle after RSI overbought

**Step 3: Volume Validation** (during HA confirmation)
- **Volume Check**: Confirmation candle volume must be **greater than** average volume of last X candles (default: 14)
- **Real Volume**: Uses actual candle volume data, not Heikin Ashi volume
- **Configurable**: Can be enabled/disabled and lookback period adjustable

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
    "INITIAL_QUANTITY": 1,  # Your desired starting quantity (updated to 1)
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
    "QUANTITY_MODE": "PERCENTAGE",  # Risk percentage of balance (CURRENT CONFIG)
    "INITIAL_QUANTITY": 1,  # Ignored in this mode
    "BALANCE_PERCENTAGE": 0.2,  # 20% of balance at risk (CURRENT: updated from 1%)
    "PROGRESSION_MODE": "STEP",  # How cascade progresses
}
```
- **Advanced risk management**: Calculates quantity based on percentage of available balance
- **Dynamic balance detection**: Automatically uses the correct quote asset (USDC for LINKUSDC, USDT for ETHUSDT, etc.)
- **Formula**: `Quantity = (Balance × Percentage) ÷ Distance_to_SL_with_offset`
- **Risk control**: You risk exactly the specified percentage on the distance to Stop Loss level
- **Fallback safety**: If balance is insufficient or unavailable, automatically falls back to minimum quantity

**Price Distance Calculation** (ALL_OR_NOTHING Strategy):
- **LONG Signal**: `Distance = Signal_Price - (SL_Level - SL_Offset)`
- **SHORT Signal**: `Distance = (SL_Level + SL_Offset) - Signal_Price`
- **SL Level LONG**: LOW minimum of last 5 candles (support level)
- **SL Level SHORT**: HIGH maximum of last 5 candles (resistance level)

**Example Calculation LONG** (Current LINKUSDC Config):
```
Balance USDC: 100.0
Risk Percentage: 20.0% = 20.0 USDC at risk
Signal Price: 24.50 USDC
SL Level: 24.30 USDC (LOW of last 5 candles)
SL with Offset: 24.30 - (24.30 × 0.005) = 24.1785 USDC
Distance: 24.50 - 24.1785 = 0.3215 USDC
Calculated Quantity: 20.0 ÷ 0.3215 = 62.2 LINK
```

**Example Calculation SHORT** (Current LINKUSDC Config):
```
Balance USDC: 100.0
Risk Percentage: 20.0% = 20.0 USDC at risk
Signal Price: 24.50 USDC
SL Level: 24.70 USDC (HIGH of last 5 candles)
SL with Offset: 24.70 + (24.70 × 0.005) = 24.8235 USDC
Distance: 24.8235 - 24.50 = 0.3235 USDC
Calculated Quantity: 20.0 ÷ 0.3235 = 61.8 LINK
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

**Example DOUBLE progression** (LINKUSDC):
```
Signal LONG: 10 LINK
Hedge SHORT: 20 LINK (2x signal)
Cascade LONG: 30 LINK (to reach net 40 LONG vs 20 SHORT)
Cascade SHORT: 60 LINK (to reach net 80 SHORT vs 40 LONG)
Cascade LONG: 120 LINK (to reach net 160 LONG vs 80 SHORT)
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

**Example STEP progression** (LINKUSDC):
```
Signal LONG: 10 LINK (step = 10)
Hedge SHORT: 20 LINK
Cascade LONG: 10 LINK (to reach net 20 LONG vs 20 SHORT)
Cascade SHORT: 10 LINK (to reach net 30 SHORT vs 30 LONG)
Cascade LONG: 10 LINK (to reach net 40 LONG vs 30 SHORT)
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

### Current Configuration (2025-09-23 Update)
- **Active Strategy**: `ALL_OR_NOTHING` (risk management with SL/TP)
- **Symbol**: `LINKUSDC` on 1-minute timeframe ⬆️ *Updated from BTCUSDC/5m*
- **SL Configuration**: 0.5% offset from HIGH/LOW levels ⬆️ *Updated from 0.1%*
- **TP Percentage**: 0.3% from entry price ⬆️ *Updated from 0.5%*
- **Max Accumulations**: 20 positions per side (ACCUMULATOR) ⬆️ *Updated from 15*
- **Balance Risk**: 20% of balance in PERCENTAGE mode ⬆️ *Updated from 1%*
- **Volume Validation**: Disabled ⬆️ *Updated from enabled*
- **RSI Periods**: 3/5/7 with thresholds 10/20/30 - 90/80/70
- **Recovery System**: ✅ Automatic TP recovery for missing TPs
- **Shutdown System**: ✅ Enhanced 3-level graceful shutdown

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
5. **WebSocket Integration**: AccumulatorService now receives real-time TP execution events
6. **Automatic Recovery**: Bot restores ACCUMULATOR state on restart (positions + TPs + counters)
7. **Pylance Corrections**: Added `get_open_orders()` method to BinanceAPIClient
8. **Enhanced Shutdown**: Implemented 3-level graceful shutdown system with resource cleanup
9. **Automatic TP Recovery**: Missing TPs automatically recreated during position recovery
10. **Process Cleanup**: Zombie process elimination - clean shutdown without manual intervention
11. **CRITICAL: TP Preservation**: Fixed bot cancelling active TPs during shutdown - TPs now preserved for position closure

### Take Profit Orders
Both strategies use **TAKE_PROFIT** order type (limit orders with trigger):
- **Order Type**: `"TAKE_PROFIT"` (not MARKET orders)
- **Stop Price**: Trigger level with small offset (±0.1%)  
- **Limit Price**: Exact TP target price
- **Execution**: Triggered when price reaches stop, executes at limit price

### Validated Features ✅
- ✅ **Strategy switching** between CASCADE_MASTER, ACCUMULATOR, and ALL_OR_NOTHING
- ✅ **ACCUMULATOR**: Simple orders without hedge/cascade systems
- ✅ **CASCADE_MASTER**: Full hedge + cascade + advanced TP preserved
- ✅ **ALL_OR_NOTHING**: Risk management with automatic SL + fixed TP
- ✅ **Take Profit**: All strategies use proper TAKE_PROFIT limit orders
- ✅ **Configuration**: Real-time strategy selection via config changes
- ✅ **Error Handling**: Comprehensive logging and error recovery
- ✅ **WebSocket Detection**: Real-time TP execution detection for ACCUMULATOR
- ✅ **Automatic Recovery**: State restoration on bot restart
- ✅ **Automatic TP Recovery**: Missing TPs automatically recreated during startup
- ✅ **Enhanced Shutdown**: 3-level graceful shutdown with complete resource cleanup
- ✅ **TP Preservation**: Critical fix - TPs no longer cancelled during shutdown, positions remain protected
- ✅ **Process Management**: Zero zombie processes, clean file unlocking
- ✅ **Production Ready**: Robust architecture for live trading with improved reliability

## Advanced Features (2025-09-10 Update)

### WebSocket Integration for ACCUMULATOR Strategy

The ACCUMULATOR strategy now features **real-time TP execution detection** through WebSocket integration:

**Architecture Flow**:
```
TP Executed on Binance → WebSocket Event → UserDataStreamManager 
→ Routes to AccumulatorService → Instant Reset → Ready for New Signals
```

**Key Benefits**:
- **Zero Latency**: Instant detection vs. polling-based systems
- **Automatic Reset**: Accumulation counters reset immediately after TP execution
- **Consistent State**: No risk of incorrect TP quantities on new signals
- **Production Reliability**: Robust error handling and fallback mechanisms

**Implementation**:
```python
# In user_data_manager.py - Routes WebSocket events to ACCUMULATOR
if self.trading_bot.strategy_manager.current_strategy_type == "ACCUMULATOR":
    accumulator_service.handle_order_execution_from_websocket(execution_data)

# In accumulator_service.py - Processes TP execution events
def handle_order_execution_from_websocket(self, order_data):
    if order_data.get("X") == "FILLED":
        if self.active_tp_long and order_data.get("i") == self.active_tp_long["orderId"]:
            self._reset_accumulation_side(AccumulatorSide.LONG)
```

### Automatic Recovery System

**Problem Solved**: Bot restart with active ACCUMULATOR positions previously lost tracking state.

**Solution**: Comprehensive recovery system that automatically restores:
- ✅ **Position Quantities**: Retrieves actual position sizes from Binance API
- ✅ **Accumulation Counters**: Estimates based on position quantity / minimum order size
- ✅ **Active TPs**: Matches open TAKE_PROFIT orders to positions
- ✅ **WebSocket Tracking**: Immediately operational for TP execution detection

**Recovery Process**:
```python
def _recover_existing_state(self):
    # 1. Get existing positions from Binance
    positions = self.binance_client.get_position_info(symbol)
    
    # 2. Get open orders (potential TPs)  
    open_orders = self.binance_client.get_open_orders(symbol)
    
    # 3. Restore state for each active position
    for position in positions:
        if abs(position_amt) > 0:
            self._restore_position_state(position, open_orders)
            
    # 4. Resume WebSocket tracking immediately
```

**Example Recovery**:
```
Before Restart:
- LONG: 5 accumulations (0.005 BTC) + TP active
- SHORT: 3 accumulations (0.003 BTC) + TP active

After Restart with Recovery:
- ✅ LONG: 5 accumulations restored + TP tracking resumed  
- ✅ SHORT: 3 accumulations restored + TP tracking resumed
- ✅ WebSocket: Immediate TP execution detection operational
- ✅ New signals: Respect accumulation limits (5+new ≤ 10)
```

### Robust Error Resolution

**Issue**: Original problem with incorrect TP quantities after execution.

**Root Cause**: ACCUMULATOR system didn't detect TP executions, leading to:
- Stale accumulation state
- Wrong TP quantities on position updates
- Failed order cancellations (orders already executed)

**Comprehensive Fix**:
1. **WebSocket Integration**: Instant TP execution detection
2. **State Management**: Automatic reset after TP execution  
3. **Recovery System**: Handles bot restarts gracefully
4. **API Enhancement**: Added `get_open_orders()` for complete order management

**Result**: Zero instances of incorrect TP quantities in testing.

## Production Deployment Guide

### Strategy Configuration

**Switch to ACCUMULATOR Strategy**:
```python
# In config.py
STRATEGY_CONFIG = {
    "STRATEGY_TYPE": "ACCUMULATOR"  # Simple accumulation strategy
}

ACCUMULATOR_CONFIG = {
    "ENABLED": True,
    "TP_PERCENT": 0.003,        # 0.3% TP from average price
    "MAX_ACCUMULATIONS": 20,    # Max positions per side (updated)
    "PRICE_OFFSET": 0.001,      # 0.1% trigger offset
}
```

**Switch to ALL_OR_NOTHING Strategy** (Current Active):
```python
# In config.py
STRATEGY_CONFIG = {
    "STRATEGY_TYPE": "ALL_OR_NOTHING"  # Risk management with SL/TP (CURRENT)
}

ALL_OR_NOTHING_CONFIG = {
    "ENABLED": True,
    "SL_LOOKBACK_CANDLES": 5,     # Candles for SL calculation
    "SL_OFFSET_PERCENT": 0.005,   # 0.5% SL offset (current)
    "TP_PERCENT": 0.003,          # 0.3% TP from entry (current)
    "PRICE_OFFSET": 0.001,        # 0.1% trigger offset
}
```

**Switch back to CASCADE_MASTER**:
```python
# In config.py
STRATEGY_CONFIG = {
    "STRATEGY_TYPE": "CASCADE_MASTER"  # Full hedge + cascade system
}
```

### Monitoring Commands

**Check Strategy Status**:
```python
# In trading_bot logs, look for:
# "📊 Strategy active: ACCUMULATOR" 
# "🔄 Position LONG restored: 0.005 BTC, 5 accumulations"
# "✅ TP LONG found: ID 123456 for 0.005 BTC"
```

**Monitor Recovery Process**:
```bash
# Watch for recovery logs on startup:
grep "recovery" logs/trading_bot.log | tail -10
```

**Track WebSocket Events**:
```bash  
# Monitor TP execution detection:
grep "TP.*executed.*WebSocket" logs/trading_bot.log | tail -5
```

### Troubleshooting

**If Recovery Fails**:
1. Check API connectivity to Binance
2. Verify positions exist with `get_position_info()`
3. Ensure open orders match position quantities
4. Review logs for specific error messages

**If WebSocket Not Detecting TPs**:
1. Verify User Data Stream is active
2. Check `trading_bot_reference` is set correctly
3. Confirm ACCUMULATOR strategy is active
4. Validate order IDs match between TP creation and execution

**Manual Reset** (Emergency):
```bash
# Stop bot, close all positions manually on Binance, restart bot
# Recovery system will detect empty positions and start clean
```

### Enhanced Shutdown System (2025-09-12 Update)

The bot now features a **comprehensive shutdown system** that resolves process cleanup issues:

**Problem Solved**: Previously, Ctrl+C left zombie processes that blocked log file deletion and required manual `taskkill` commands.

**Enhanced Shutdown Features**:
- ✅ **Graceful 3-level shutdown**: Progressive signals (graceful → forceful → brutal)
- ✅ **Resource cleanup**: WebSockets, Listen Keys, Strategy Manager automatically cleaned
- ✅ **Timeout protection**: 10-second timeout prevents hanging shutdowns
- ✅ **File unlock**: Log files immediately unlocked after bot shutdown
- ✅ **Zero zombie processes**: No manual process killing required

**Shutdown Process**:
```
Ctrl+C (Signal 1) → Graceful cleanup with _cleanup_resources()
Ctrl+C (Signal 2) → Force WebSocket shutdown
Ctrl+C (Signal 3) → Brutal process termination (os._exit)
```

**Centralized Cleanup** (`_cleanup_resources()`):
1. **WebSocket Shutdown**: Both kline and User Data streams properly closed
2. **Binance Cleanup**: Listen key closed server-side via `close_listen_key()`
3. **Strategy Cleanup**: All strategy managers and services cleaned
4. **Timeout Safety**: 0.5s wait for graceful connection closure

**Benefits**:
- **User Experience**: Single Ctrl+C properly shuts down the bot
- **Development**: Log files immediately deletable without manual intervention
- **Production**: Robust shutdown prevents resource leaks
- **Reliability**: Timeout prevents infinite hanging on network issues

### Automatic TP Recovery System (2025-09-12 Update)

The ACCUMULATOR strategy now includes **automatic Take Profit recovery** for missing TPs:

**Problem Solved**: Bot restarts with existing positions but missing TPs (manually deleted or expired) previously required manual TP recreation.

**Automatic Recovery Features**:
- ✅ **Missing TP Detection**: Automatically detects positions without corresponding TPs
- ✅ **Smart TP Creation**: Calculates TP price based on position average price + configured percentage
- ✅ **Seamless Integration**: Works within existing recovery system without additional configuration
- ✅ **WebSocket Ready**: Newly created TPs immediately tracked for execution detection

**Recovery Logic**:
```python
# During position recovery
if position_exists and not tp_found:
    tp_price = entry_price * (1 ± TP_PERCENT)  # ± based on LONG/SHORT
    auto_create_tp(side, quantity, tp_price)
```

**Example Recovery**:
```
Position Found: LONG 0.003 BTC @ 115,251.9
TP Search: ❌ No TP found in open orders
Auto Recovery: ✅ TP created @ 115,597.6 (0.3% above entry)
Result: Position fully restored with WebSocket tracking active
```

**Configuration**: Uses existing `ACCUMULATOR_CONFIG.TP_PERCENT` (default: 0.3%)

**Safety**: Only creates TPs for positions without existing TPs - never duplicates

### Critical TP Preservation Fix (2025-09-12 Update)

**CRITICAL ISSUE RESOLVED**: Le bot annulait incorrectement les ordres Take Profit lors de l'arrêt, empêchant la fermeture des positions existantes.

**Problem**: *"y'a un probleme lorsque le bot ce fermé il cancel les TP en attente"*

**Root Cause**: Les méthodes `cleanup()` dans `accumulator_service.py` et `tp_service.py` appelaient `_cancel_tp_order()` pour les TPs actifs lors de l'arrêt gracieux du bot.

**Critical Fix Applied**:

**accumulator_service.py:482** - Méthode `cleanup()` modifiée :
```python
# AVANT (PROBLÉMATIQUE)
if self.active_tp_long:
    self._cancel_tp_order(self.active_tp_long)  # ❌ ANNULE LE TP

# APRÈS (CORRIGÉ) 
if self.active_tp_long:
    self.logger.info(f"⚠️ TP LONG préservé lors de l'arrêt: {self.active_tp_long.get('orderId')}")
```

**tp_service.py:448** - Même correction appliquée pour `tp_service.cleanup()`

**New Method**: `_reset_accumulation_side_without_tp_cancel()` 
- Réinitialise les compteurs d'accumulation SANS toucher aux TPs actifs
- Préserve les références TP pour le recovery au redémarrage

**Validation Test Results**:
```bash
📊 État avant arrêt:
   TP LONG actif: True  - ID: 25589003361  
   TP SHORT actif: True - ID: 25589012359

🛑 Déclenchement de l'arrêt gracieux...
⚠️ TP LONG préservé lors de l'arrêt: 25589003361  
⚠️ TP SHORT préservé lors de l'arrêt: 25589012359
✅ Accumulation LONG réinitialisée (TP préservé)
✅ Accumulation SHORT réinitialisée (TP préservé)
```

**Impact Résolu**:
- ✅ **TPs préservés** : Les ordres restent actifs sur Binance après arrêt du bot
- ✅ **Positions protégées** : Les positions peuvent être fermées par leurs TPs
- ✅ **Recovery fonctionnel** : Au redémarrage, le recovery retrouve les TPs automatiquement  
- ✅ **Production ready** : Système maintenant sûr pour utilisation en production

**Files Modified**:
- `core/accumulator_service.py` - Méthode cleanup() et nouvelle méthode de reset sans TP cancel
- `core/tp_service.py` - Méthode cleanup() avec préservation des TPs