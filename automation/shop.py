"""
Shop automation for Magic Garden bot.

Handles automatic purchasing of configured items from shops.
"""

import asyncio
from copy import deepcopy
from typing import Dict, Any

from game_state import GameState
from config import ShopConfig


async def check_and_buy_from_shop(
    client, game_state: GameState, config: ShopConfig
):
    """
    Check shop inventory and buy configured items if available.

    Args:
        client: MagicGardenClient instance
        game_state: Global game state
        config: Shop configuration
    """
    if not config or not config.enabled:
        return

    # Get player slot using GameState's method (handles locking internally)
    our_slot = game_state.get_player_slot()
    if not our_slot:
        return

    # Get full state (deepcopy) to extract shops data
    full_state = game_state["full_state"]
    if not full_state:
        return

    # Navigate to Quinoa game state to get shops
    if "child" not in full_state or full_state["child"].get("scope") != "Quinoa":
        return

    quinoa_state = full_state["child"].get("data", {})
    shops_data = quinoa_state.get("shops", {})

    slot_data = our_slot.get("data", {})
    current_coins = slot_data.get("coinsCount", 0)

    # Check coin limits
    min_coins = config.min_coins_to_keep
    print(f"\nChecking shops... (Balance: {current_coins:,} coins)")

    if current_coins <= min_coins:
        print(f"   Not enough coins (need to keep {min_coins:,})")
        return

    if not shops_data:
        print("   No shops available")
        return

    items_bought = 0
    total_items_in_stock = 0

    # Check seed shop
    seed_shop = shops_data.get("seed", {})
    seed_inventory = seed_shop.get("inventory", [])
    seeds_to_buy = []

    if seed_inventory:
        # Check if we have any seeds to buy
        for item in seed_inventory:
            if not item:
                continue

            species = item.get("species")
            stock = item.get("initialStock", 0)

            if stock > 0:
                total_items_in_stock += 1

                # Check if we want to buy this seed
                if config.seeds_enabled and species in config.seeds_to_buy:
                    print(f"   Found configured seed: {species} (Stock: {stock})")
                    seeds_to_buy.append({"species": species, "stock": stock})
                else:
                    if not config.seeds_enabled:
                        print(
                            f"   {species} (Seed) - seed buying disabled (Stock: {stock})"
                        )
                    else:
                        print(f"   {species} (Seed) - not in config (Stock: {stock})")

    # Check egg shop
    egg_shop = shops_data.get("egg", {})
    egg_inventory = egg_shop.get("inventory", [])
    eggs_to_buy = []

    if egg_inventory:
        for item in egg_inventory:
            if not item:
                continue

            egg_id = item.get("eggId")
            stock = item.get("initialStock", 0)

            if stock > 0:
                total_items_in_stock += 1

                # Check if we want to buy this egg
                if config.eggs_enabled and egg_id in config.eggs_to_buy:
                    print(f"   Found configured egg: {egg_id} (Stock: {stock})")
                    eggs_to_buy.append({"eggId": egg_id, "stock": stock})
                else:
                    if not config.eggs_enabled:
                        print(f"   {egg_id} (Egg) - egg buying disabled (Stock: {stock})")
                    else:
                        print(f"   {egg_id} (Egg) - not in config (Stock: {stock})")

    # Buy all configured seeds
    for seed_item in seeds_to_buy:
        species = seed_item["species"]
        stock = seed_item["stock"]

        print(f"   Purchasing {stock}x {species} seeds...")

        # Buy all available stock
        purchased_count = 0
        for i in range(stock):
            # Re-check balance before each purchase
            our_slot = game_state.get_player_slot()
            if our_slot:
                slot_data = our_slot.get("data", {})
                current_coins = slot_data.get("coinsCount", 0)

                if current_coins <= min_coins:
                    print(
                        f"   Stopped at {purchased_count}/{stock} {species} - balance {current_coins:,} at or below reserve {min_coins:,}"
                    )
                    break

            buy_message = {
                "type": "PurchaseSeed",
                "species": species,
                "scopePath": ["Room", "Quinoa"],
            }
            await client.send(buy_message)

            # Optimistically update shop count in game_state
            def update_seed_stock(full_state):
                if (
                    "child" in full_state
                    and full_state["child"].get("scope") == "Quinoa"
                ):
                    quinoa_state = full_state["child"].get("data", {})
                    shops = quinoa_state.get("shops", {})
                    seed_shop = shops.get("seed", {})
                    inventory = seed_shop.get("inventory", [])

                    for item in inventory:
                        if item and item.get("species") == species:
                            current_stock = item.get("initialStock", 0)
                            if current_stock > 0:
                                item["initialStock"] = current_stock - 1
                                if i == 0:  # Only print on first purchase
                                    print(
                                        f"   Optimistically updating {species} stock from {current_stock}"
                                    )
                            break

            game_state.update_full_state_locked(update_seed_stock)

            purchased_count += 1
            items_bought += 1
            await asyncio.sleep(0.1)  # Small delay between purchases

        if purchased_count == stock:
            print(f"   Bought {stock}x {species} seeds")
        elif purchased_count > 0:
            print(f"   Bought {purchased_count}x {species} seeds (stopped early)")

    # Buy all configured eggs
    for egg_item in eggs_to_buy:
        egg_id = egg_item["eggId"]
        stock = egg_item["stock"]

        print(f"   Purchasing {stock}x {egg_id}...")

        # Buy all available stock
        purchased_count = 0
        for i in range(stock):
            # Re-check balance before each purchase
            our_slot = game_state.get_player_slot()
            if our_slot:
                slot_data = our_slot.get("data", {})
                current_coins = slot_data.get("coinsCount", 0)

                if current_coins <= min_coins:
                    print(
                        f"   Stopped at {purchased_count}/{stock} {egg_id} - balance {current_coins:,} at or below reserve {min_coins:,}"
                    )
                    break

            buy_message = {
                "type": "PurchaseEgg",
                "eggId": egg_id,
                "scopePath": ["Room", "Quinoa"],
            }
            await client.send(buy_message)

            # Optimistically update shop count in game_state
            def update_egg_stock(full_state):
                if (
                    "child" in full_state
                    and full_state["child"].get("scope") == "Quinoa"
                ):
                    quinoa_state = full_state["child"].get("data", {})
                    shops = quinoa_state.get("shops", {})
                    egg_shop = shops.get("egg", {})
                    inventory = egg_shop.get("inventory", [])

                    for item in inventory:
                        if item and item.get("eggId") == egg_id:
                            current_stock = item.get("initialStock", 0)
                            if current_stock > 0:
                                item["initialStock"] = current_stock - 1
                                if i == 0:  # Only print on first purchase
                                    print(
                                        f"   Optimistically updating {egg_id} stock from {current_stock}"
                                    )
                            break

            game_state.update_full_state_locked(update_egg_stock)

            purchased_count += 1
            items_bought += 1
            await asyncio.sleep(0.1)  # Small delay between purchases

        if purchased_count == stock:
            print(f"   Bought {stock}x {egg_id}")
        elif purchased_count > 0:
            print(f"   Bought {purchased_count}x {egg_id} (stopped early)")

    # Summary
    if total_items_in_stock == 0:
        print("   All shops are out of stock")
    elif items_bought == 0:
        print(f"   Found {total_items_in_stock} items in stock, but none match config")
    else:
        print(
            f"   Purchased {items_bought} item(s) and returned to original position"
        )


async def run_shop_buyer(client, game_state: GameState, config: ShopConfig):
    """
    Shop auto-buy task that runs periodically.

    Args:
        client: MagicGardenClient instance
        game_state: Global game state
        config: Shop configuration
    """
    # Wait a bit before starting to allow game state to load
    await asyncio.sleep(10)

    # Get check interval from config
    interval = config.check_interval_seconds if config else 10

    while client.is_connected:
        await asyncio.sleep(interval)

        # Exit if disconnected
        if not client.is_connected:
            print("Shop buyer task exiting - connection lost")
            break

        try:
            await check_and_buy_from_shop(client, game_state, config)
        except RuntimeError as e:
            # Connection lost during send
            if "Not connected" in str(e):
                print("Shop buyer task exiting - connection lost")
                break
            raise
        except Exception as e:
            print(f"Error in shop buying task: {e}")
            # Continue on non-connection errors if still connected
            if not client.is_connected:
                print("Shop buyer task exiting - connection lost")
                break
