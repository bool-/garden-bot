"""Pet care: keep every pet fed, put the best pets on the team, sell the rest."""

from .common import *  # noqa: F401,F403
from .common import _now_ms  # noqa: F401


class PetsMixin:
    # ------------------------------------------------------------------ pets
    async def care_for_pets(self, s) -> bool:
        plan = self._food_plan(s)
        for pet in s["pets"]:
            if not pet:
                continue
            species = pet.get("petSpecies")
            info = eco.PETS.get(species)
            if not info:
                continue
            cap = info["hungerCap"]
            hunger = float(pet.get("hunger") or 0)
            deficit = cap - hunger
            starving = hunger < cap * 0.2
            diet = set(info["diet"])

            # 1) food already in the bag
            options = []
            for it in self._produce(s):
                if it.get("species") in diet:
                    v = eco.crop_value(it["species"], it.get("size", 50), it.get("mutations"))
                    options.append((v, "inv", it))
            # 2) ripe diet crops in the garden (cheap ones only; never stamped ones)
            for tile_id, obj in s["garden"].items():
                if (obj or {}).get("objectType") != "plant":
                    continue
                for idx, sl in enumerate(obj.get("slots") or []):
                    if not sl or sl.get("species") not in diet or s["now"] < sl.get("endTime", 0):
                        continue
                    if (int(tile_id), idx) in self._pending_harvest or eco.has_growth_mutation(sl.get("mutations")):
                        continue
                    v = eco.crop_value(sl["species"], sl.get("size", 50), sl.get("mutations"))
                    options.append((v, "garden", (int(tile_id), idx)))

            # Never feed something worth far more than a full bar.
            options = [o for o in options if o[0] <= max(cap * 2, 1)]
            if not options:
                continue
            fitting = [o for o in options if o[0] <= deficit]
            if fitting:
                choice = max(fitting, key=lambda o: o[0])
                # Only bother when a feed fills a meaningful chunk (or pet is starving).
                if not starving and choice[0] < min(deficit, cap) * 0.5:
                    continue
            elif starving:
                choice = min(options, key=lambda o: o[0])
            else:
                continue

            value, where, ref = choice
            if where == "inv":
                await self._select(s, ref["id"])
                crop_id = ref["id"]
            else:
                crop_id = await self._harvest_slot(s, *ref)
                if not crop_id:
                    return False
                await asyncio.sleep(random.uniform(0.6, 1.4))
            await self.client.send_command(
                {"type": "FeedPet", "petItemId": pet["id"], "cropItemId": crop_id},
                **({"successorItemId": nxt} if (nxt := self._next_item_id(s, crop_id)) else {}),
            )
            self._log(f"fed {species} ({int(hunger)}/{cap}) with {ref['species'] if where == 'inv' else 'fresh ' + plan.get(pet['id'], 'crop')} worth {value:,}")
            await asyncio.sleep(random.uniform(0.8, 2.0))
            return True
        return False

    # ------------------------------------------------------------------ pets
    def _inventory_pets(self, s) -> List[dict]:
        return [i for i in s["items"] if i.get("itemType") == "Pet" and i.get("id") not in s["locked"]]

    async def improve_team_step(self, s) -> bool:
        """Swap a better pet from the bag into the active team."""
        active = [p for p in s["pets"] if p and p.get("id") not in s["locked"]]
        bag = self._inventory_pets(s)
        if not active or not bag:
            return False
        best_new = max(bag, key=eco.pet_score)
        worst = min(active, key=eco.pet_score)
        if eco.pet_score(best_new) <= eco.pet_score(worst) * 1.05:
            return False
        await self.client.send_command(
            {"type": "SwapPet", "petSlotId": worst["id"], "petInventoryId": best_new["id"]}
        )
        self._log(
            f"team: swapped in {self._pet_label(best_new)} for {self._pet_label(worst)}"
        )
        await asyncio.sleep(random.uniform(1.0, 2.0))
        return True

    @staticmethod
    def _pet_label(p) -> str:
        muts = "/".join(p.get("mutations") or [])
        strength = eco.pet_max_strength(p.get("petSpecies"), p.get("targetScale"))
        return f"{(muts + ' ') if muts else ''}{p.get('petSpecies')} (size {float(p.get('targetScale') or 1):.2f}, max str {strength})"

    def _pets_to_sell(self, s) -> List[dict]:
        bag = self._inventory_pets(s)
        active = [p for p in s["pets"] if p]
        floor = min((eco.pet_score(p) for p in active), default=0)
        spares = sorted((p for p in bag if eco.is_granter(p)), key=eco.pet_score, reverse=True)
        keep = {p["id"] for p in spares[: self.spare_granters]}
        out = []
        for p in bag:
            if p["id"] in keep:
                continue
            if not self.sell_original_pets and p["id"] in (self._original_pets or set()):
                continue
            if eco.pet_score(p) > floor:  # about to be swapped in
                continue
            out.append(p)
        return out

    async def sell_pets_step(self, s) -> bool:
        sell = self._pets_to_sell(s)
        free = INVENTORY_CAPACITY - len(s["items"])
        if not sell or (len(sell) < self.sell_pets_at and free > 3):
            return False
        stand = eco.STALLS["sellPet"]["stand"]
        crop_stand = eco.STALLS["sellCrops"]["stand"]
        await teleport(self.client, self.gs, random.randint(*crop_stand["x"]), random.randint(*crop_stand["y"]))
        await walk_to(self.client, self.gs, random.randint(*stand["x"]), random.randint(*stand["y"]))
        await asyncio.sleep(random.uniform(0.5, 1.2))
        for p in sell:
            await self._select(s, p["id"])
            await self.client.send_command({"type": "SellPet", "itemId": p["id"]})
            await asyncio.sleep(random.uniform(0.6, 1.3))
        self._log(f"sold {len(sell)} pet(s): " + ", ".join(sorted({x.get('petSpecies') for x in sell})))
        await go_home(self.client, self.gs)
        return True
