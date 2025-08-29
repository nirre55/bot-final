# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based **Binance futures trading bot** that connects to real-time WebSocket streams to calculate RSI and Heikin Ashi indicators. The bot displays trading signals when candles close, using a modular service-oriented architecture with single responsibility principles.

## Core Architecture

### Service-Oriented Design
The bot follows a **layered architecture** where each component has a single responsibility:

- **`trading_bot.py`**: Main orchestrator that coordinates all services and handles WebSocket message processing
- **Service Layer** (`core/`): Business logic orchestration (RSIService, HAService, SignalService)  
- **Indicator Layer** (`indicators/`): Pure calculation logic (RSI, Heikin Ashi)
- **API Layer** (`api/`): External service communication (Binance REST API, market data)
- **WebSocket Layer** (`websocket/`): Real-time data streaming with auto-reconnection

### Key Integration Pattern
The bot triggers calculations **only on candle close events** detected through WebSocket kline streams:
1. WebSocket receives kline data → `_handle_kline_message()`
2. On candle close → `_calculate_and_display_rsi()` 
3. RSI calculation → `_calculate_and_display_ha()`
4. Display both RSI values and HA candle color with emojis
5. Process signal detection → `_process_signal_detection()`

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
- **Logging levels**: Adjust `LOGGING_CONFIG` in `config.py`
- **Reconnection settings**: Configure `RECONNECTION_CONFIG` for WebSocket resilience

## Key Technical Details

### RSI Configuration
The bot calculates **multiple RSI periods** with different sensitivity thresholds:
- RSI 3: 10/90 (highly sensitive)
- RSI 5: 20/80 (standard)  
- RSI 7: 30/70 (less sensitive)

### Data Requirements
- **RSI calculations**: Requires 100 historical candles
- **Heikin Ashi calculations**: Requires 50 historical candles
- **WebSocket stream**: `{symbol}@kline_{timeframe}` format

### WebSocket Connection Management
- **Auto-reconnection**: Up to 100 attempts with 30-second delays
- **Connection health**: 3600-second timeout monitoring
- **Target endpoint**: Binance USDⓈ-M Futures WebSocket (`wss://fstream.binance.com/ws/`)

## Logging System

Comprehensive logging with file rotation:
- **Location**: `logs/trading_bot.log`
- **Rotation**: 1MB max size, 3 backup files
- **Module-specific loggers**: Each component uses `get_module_logger()`
- **Format**: Timestamp | Level | Module.Function | Message

## Signal Detection Logic

### RSI Signals
Each RSI period has different thresholds for oversold/overbought detection configured in `SIGNAL_CONFIG`. The system displays all RSI values with color-coded indicators.

### Heikin Ashi Display
- **Green 🟢**: Bullish HA candle (HA_close > HA_open)
- **Red 🔴**: Bearish HA candle (HA_close < HA_open)  
- **White ⚪**: Doji HA candle (HA_close = HA_open)

## Trading Signal System

### 2-Step Sequential Signal Logic
The bot implements a **sequential signal detection system** requiring two distinct phases:

**Step 1: RSI Condition**
- **LONG Signal**: All 3 RSI periods (3, 5, 7) must be **OVERSOLD** simultaneously
- **SHORT Signal**: All 3 RSI periods (3, 5, 7) must be **OVERBOUGHT** simultaneously

**Step 2: HA Confirmation** (after RSI condition is met)
- **LONG Confirmation**: Green HA candle after RSI oversold
- **SHORT Confirmation**: Red HA candle after RSI overbought

### Signal State Machine
- **WAITING**: Monitoring for RSI conditions
- **RSI_CONDITION_MET**: RSI satisfied, waiting for HA confirmation
- **SIGNAL_CONFIRMED**: Complete signal validated and ready for trading

**Important**: The two steps must be **sequential**, not simultaneous. Once HA confirmation is received, the signal remains valid even if RSI values exit oversold/overbought zones.

## Architecture Principles

### Single Responsibility
- **Services** (`core/`): Orchestrate data retrieval + calculations
- **Indicators** (`indicators/`): Pure mathematical calculations
- **Clients** (`api/`): External API communication only

### Error Resilience
- WebSocket auto-reconnection with exponential backoff
- Comprehensive exception handling in all service methods
- Detailed error logging with stack traces

### Configuration-Driven
All operational parameters externalized to `config.py`:
- Trading symbols and timeframes
- API endpoints and WebSocket URLs
- Signal detection thresholds
- Logging and reconnection settings

When modifying the bot, maintain this separation of concerns and ensure all changes preserve the single-responsibility principle across modules.

### Architecture & Design
- **Principle KISS**: Keep It Simple, Stupid - always prefer the simplest solution
- **Single responsibility**: One responsibility per file AND per function
- **Function size**: Maximum 80 lines per function, split if longer
- **Avoid over-engineering**: No premature abstractions
- **Code simplicity**: Simple and readable code over complex solutions

### Code Quality Standards
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