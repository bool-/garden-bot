"""Shopping: buy every restock (seed/egg stalls; tool shop only what's needed)."""

from .common import *  # noqa: F401,F403
from .common import _now_ms  # noqa: F401


class ShoppingMixin:
    # ------------------------------------------------------------------ shop
    def _tool_needed(self, s, tool_id) -> bool:
        """Tool shop: only what the bot actually uses (config tools_to_buy), plus
        a Shovel if the account somehow has none."""
        if tool_id in self.tools_to_buy:
            return True
        if tool_id == "Shovel":
            return not any(i.get("toolId") == "Shovel" for i in s["items"])
        return False

    @staticmethod
    def _owned_decor(s) -> set:
        owned = {i.get("decorId") for i in s["items"] if i.get("decorId")}
        garden = (s["data"].get("garden") or {})
        for objs in (garden.get("tileObjects") or {}, garden.get("boardwalkTileObjects") or {}):
            owned |= {o.get("decorId") for o in objs.values() if o and o.get("decorId")}
        return owned

    def _shopping_list(self, s) -> Dict[str, List[Tuple[dict, int]]]:
        wanted: Dict[str, List[Tuple[dict, int]]] = {}
        coins = s["coins"]
        for shop_key in self.shops:
            shop = s["shops"].get(shop_key) or {}
            restock = shop.get("restockId")
            if not restock:
                continue
            mine = s["purchases"].get(shop_key) or {}
            bought = (mine.get("purchases") or {}) if mine.get("restockId") == restock else {}
            for entry in shop.get("inventory") or []:
                if not entry:
                    continue
                key = entry.get("species") or entry.get("eggId") or entry.get("toolId") or entry.get("decorId")
                left = int(entry.get("initialStock", 0)) - int(bought.get(key, 0))
                if left <= 0:
                    continue
                if entry.get("itemType") == "Decor":
                    continue  # buildings: one-time purchases, never bought automatically
                if shop_key == "tool" and not self._tool_needed(s, key):
                    continue
                if (shop_key, key) in self._unbuyable or (shop_key, restock) in self._bought_restocks:
                    continue
                if (shop_key == "seed" and eco.CROPS.get(key, {}).get("webUnavailable")) or (
                        shop_key == "egg" and eco.EGGS.get(key, {}).get("webUnavailable")):
                    continue  # not sold to web clients; the server would reject it
                if shop_key == "seed":
                    price = eco.CROPS.get(key, {}).get("seedPrice", 0)
                    affordable = int((coins - self.min_coins) // price) if price else left
                    left = min(left, max(0, affordable))
                    if left <= 0:
                        continue
                    coins -= price * left
                elif coins < max(self.min_coins, 1_000_000):
                    continue  # eggs/tools only once the account has some money
                item = {k: v for k, v in entry.items() if k != "initialStock"}
                wanted.setdefault(shop_key, []).append((item, left))
        return wanted

    @staticmethod
    def _load_unbuyable() -> set:
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                saved = json.load(f).get("unbuyable", [])
        except (OSError, ValueError):
            return set()
        now = time.time()
        return {(shop, key) for shop, key, at in saved if now - at < REJECTION_TTL_S}

    def _learn_rejections(self):
        learned = False
        while self.client.rejected_commands:
            cmd = self.client.rejected_commands.pop()
            if cmd.get("type") == "PurchaseShopItem":
                item = cmd.get("item") or {}
                key = item.get("species") or item.get("eggId") or item.get("toolId") or item.get("decorId")
                if (cmd.get("shop"), key) not in self._unbuyable:
                    self._unbuyable.add((cmd.get("shop"), key))
                    learned = True
        if learned:
            try:
                try:
                    with open(STATE_FILE, encoding="utf-8") as f:
                        state = json.load(f)
                except (OSError, ValueError):
                    state = {}
                known = {(s_, k) for s_, k, _ in state.get("unbuyable", [])}
                now = time.time()
                state["unbuyable"] = [x for x in state.get("unbuyable", []) if now - x[2] < REJECTION_TTL_S] + [
                    [s_, k, now] for s_, k in self._unbuyable if (s_, k) not in known
                ]
                with open(STATE_FILE, "w", encoding="utf-8") as f:
                    json.dump(state, f, indent=2)
            except OSError:
                pass

    async def shop_if_restocked(self, s) -> bool:
        if not self.shops:
            return False
        self._learn_rejections()
        wanted = self._shopping_list(s)
        if not wanted:
            return False
        for k in wanted:  # one trip per restock per stall, even if the server lags
            self._bought_restocks.add((k, (s["shops"].get(k) or {}).get("restockId")))

        stall_seed = eco.STALLS["seed"]["stand"]
        await teleport(self.client, self.gs,
                       random.randint(*stall_seed["x"]), random.randint(*stall_seed["y"]))
        order = [k for k in ("seed", "egg", "tool", "decor") if k in wanted]
        total = 0
        for shop_key in order:
            stand = eco.STALLS[shop_key]["stand"]
            here = current_position(self.gs)
            if not (here and stand["x"][0] <= here[0] <= stand["x"][1] and stand["y"][0] <= here[1] <= stand["y"][1]):
                await walk_to(self.client, self.gs, random.randint(*stand["x"]), random.randint(*stand["y"]))
                await asyncio.sleep(random.uniform(0.3, 0.8))
            await self._send({"scopePath": SCOPE, "type": "SetPlayerInteraction", "interaction": shop_key})
            await asyncio.sleep(random.uniform(0.9, 1.8))
            for item, count in wanted[shop_key]:
                for _ in range(count):
                    if not self.client.is_connected:
                        return True
                    await self.client.send_command(
                        {"type": "PurchaseShopItem", "shop": shop_key, "viewMode": "grid", "item": item}
                    )
                    total += 1
                    await asyncio.sleep(random.uniform(0.25, 0.75))
                    self._learn_rejections()
                    key = item.get("species") or item.get("eggId") or item.get("toolId") or item.get("decorId")
                    if (shop_key, key) in self._unbuyable:
                        break  # refused: don't keep trying it this trip
                await asyncio.sleep(random.uniform(0.3, 0.9))
            await self._send({"scopePath": SCOPE, "type": "SetPlayerInteraction", "interaction": None})
            await asyncio.sleep(random.uniform(0.4, 1.0))
        self._log(f"restock: bought {total} item(s) from {', '.join(order)}")
        await go_home(self.client, self.gs)
        return True
