# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Architecture Overview

This is a Python-based Binance futures trading bot with WebSocket connectivity and technical indicator analysis.

### Core Components

- **`trading_bot.py`**: Main bot class with WebSocket connection, balance retrieval, and automatic reconnection logic
- **`config.py`**: Centralized configuration management for API credentials, reconnection settings, signal parameters, and logging
- **`indicators/`**: Technical analysis modules with static calculation methods
  - `rsi.py`: RSI calculation with multiple periods and EMA-based smoothing
  - `heikin_ashi.py`: Heikin Ashi candle transformations
- **`.env`**: API credentials and trading configuration (not tracked in git)

### Key Architecture Patterns

- **Configuration-driven**: All settings centralized in `config.py` with environment variable loading
- **Logging integration**: Comprehensive logging system with file rotation and configurable levels
- **Reconnection resilience**: WebSocket auto-reconnection with exponential backoff and timeout handling
- **Modular indicators**: Self-contained indicator classes with static methods for stateless calculations

## Development Commands

### Setup and Installation

```bash
pip install -r requirements.txt
```

### Running the Bot

```bash
python trading_bot.py
```

### Configuration

- Copy and configure `.env` file with Binance API credentials
- Adjust settings in `config.py` for symbol, timeframes, and reconnection parameters
- Modify `LOGGING_CONFIG` for log levels and output destinations

### Debugging

- Logs are written to `logs/trading_bot.log` with automatic rotation
- Set `LOGGING_CONFIG["LEVEL"]` to "DEBUG" for detailed flow information
- Use `INFO` level for operational events, `WARNING` for handled exceptions, `ERROR` for failures

## Code Standards

### Project Rules

- Principle KISS: Keep It Simple, Stupid
- One responsibility per file
- Maximum 80 lines per function
- Self-documenting code with explicit variable/function names
- Always fix Pylance errors/warnings immediately
- No `type: ignore` without justification comments
- Comprehensive logging at appropriate levels (DEBUG for flow, INFO for operations, WARNING for exceptions, ERROR for failures)

### Technical Indicators Structure

- Static methods for stateless calculations
- Pandas Series input/output for vectorized operations
- Multiple period calculations in single calls
- Classification methods for trading signal interpretation

### WebSocket Connection Management

- Connection state tracking with `is_running` flag
- Automatic reconnection with configurable attempts and delays
- Timeout-based connection health monitoring
- Comprehensive error handling for network issues

## Configuration Management

All configuration is centralized in `config.py`:

- **Trading parameters**: Symbol, timeframe, WebSocket URLs
- **Reconnection settings**: Max attempts, delays, timeouts
- **Signal thresholds**: RSI oversold/overbought levels for different periods
- **Logging configuration**: Levels, formats, file rotation settings

Environment variables are loaded via `python-dotenv` from `.env` file for sensitive data like API keys.

## Development Rules & Standards

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
