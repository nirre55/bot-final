#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour mettre à jour balance_max après ajout de capital
"""
import sys
import os
import json
from datetime import datetime

if sys.platform == 'win32':
    os.system('chcp 65001 > nul')
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')  # type: ignore

sys.path.insert(0, r'C:\Users\Oulmi\OneDrive\Bureau\DEV\bot-final')

from api.binance_client import BinanceAPIClient

def update_balance_max():
    """Met à jour balance_max avec la balance actuelle après dépôt"""

    # Récupérer la balance actuelle
    client = BinanceAPIClient()
    balance = client.get_account_balance()

    if not balance:
        print("❌ Impossible de récupérer la balance")
        return

    # Trouver balance USDC
    current_balance = 0.0
    for b in balance:
        if b.get('asset') == 'USDC':
            current_balance = float(b.get("availableBalance", 0))
            break

    if current_balance == 0:
        print("❌ Balance USDC non trouvée")
        return

    # Lire le fichier JSON actuel
    recovery_file = "loss_recovery.json"

    if os.path.exists(recovery_file):
        with open(recovery_file, 'r') as f:
            data = json.load(f)
            old_balance_max = float(data.get("balance_max", 0))
            recovery_amount = float(data.get("recovery_amount", 0))
    else:
        old_balance_max = 0
        recovery_amount = 0

    print("=" * 80)
    print("MISE À JOUR BALANCE MAX APRÈS DÉPÔT")
    print("=" * 80)
    print(f"\n📊 État actuel:")
    print(f"   Balance actuelle: {current_balance:.4f} USDC")
    print(f"   Balance max (ancien): {old_balance_max:.4f} USDC")
    print(f"   Recovery actif: {recovery_amount:.4f} USDC")

    # Calculer la différence
    difference = current_balance - old_balance_max

    if difference > 0:
        print(f"\n💰 DÉPÔT DÉTECTÉ: +{difference:.4f} USDC")
        print(f"   → Mise à jour balance_max: {old_balance_max:.4f} → {current_balance:.4f} USDC")

        # Demander confirmation
        response = input(f"\n❓ Confirmer la mise à jour de balance_max à {current_balance:.4f} USDC? (oui/non): ")

        if response.lower() in ['oui', 'o', 'yes', 'y']:
            # Mettre à jour le fichier
            new_data = {
                "recovery_amount": 0.0,  # Reset recovery après dépôt
                "balance_max": current_balance,
                "timestamp": datetime.now().isoformat()
            }

            with open(recovery_file, 'w') as f:
                json.dump(new_data, f, indent=2)

            print(f"\n✅ Balance_max mise à jour: {current_balance:.4f} USDC")
            print(f"✅ Recovery reset à 0.0 USDC (nouveau capital)")
            print(f"💾 Fichier sauvegardé: {recovery_file}")
        else:
            print("\n❌ Mise à jour annulée")

    elif difference == 0:
        print(f"\n➖ Aucun changement détecté")
        print(f"   Balance actuelle = Balance max = {current_balance:.4f} USDC")

    else:
        print(f"\n⚠️ PERTE DÉTECTÉE: {difference:.4f} USDC")
        print(f"   La balance actuelle est inférieure à balance_max")
        print(f"   → Pas de mise à jour (utiliser le système de recovery normal)")

if __name__ == "__main__":
    update_balance_max()
