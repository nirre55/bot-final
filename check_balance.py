#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os

if sys.platform == 'win32':
    os.system('chcp 65001 > nul')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

sys.path.insert(0, r'C:\Users\Oulmi\OneDrive\Bureau\DEV\bot-final')

from api.binance_client import BinanceAPIClient

client = BinanceAPIClient()
balance = client.get_account_balance()

if balance:
    for b in balance:
        if b.get('asset') == 'USDC':
            usdc_balance = float(b.get("availableBalance", 0))
            print(f"💰 Balance USDC actuelle: {usdc_balance:.4f} USDC")
            break
else:
    print("❌ Impossible de récupérer la balance")
