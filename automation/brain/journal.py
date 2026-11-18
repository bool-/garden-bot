"""Journal: log every crop and pet variant the account comes across.

The in-game Journal records, per species, each "variant" seen: every mutation
on a crop or pet, "Normal" (no mutations) and "Max Weight" (max size), plus
each ability a pet species has shown. The real client logs an item with
LogItem {target}; targets (from the client's own schema, build 2071):

    {"kind": "growSlot", "slot": tile, "slotsIndex": slotId}   crop on a plant
    {"kind": "petSlot", "petId": id}                            active pet
    {"kind": "inventoryItem", "itemId": id}                     crop/pet in the bag

The sell screen asks "Capture X before you sell it?" for unlogged crops; the
brain does that before every sale, photographs garden crops and pets with new
variants, grows one of every seed species it has never logged, and prefers
eggs whose pets are missing from the Journal.
"""

from .common import *  # noqa: F401,F403


class JournalMixin:
    # ------------------------------------------------------------ reading
    @staticmethod
    def _journal(s) -> dict:
        return s["data"].get("journal") or {}

    def _logged_crop_variants(self, s, species) -> set:
        entry = (self._journal(s).get("produce") or {}).get(species) or {}
        return {v.get("variant") for v in entry.get("variantsLogged") or []}

    def _logged_pet(self, s, species):
        entry = (self._journal(s).get("pets") or {}).get(species) or {}
        return (
            {v.get("variant") for v in entry.get("variantsLogged") or []},
            {a.get("ability") for a in entry.get("abilitiesLogged") or []},
        )

    @staticmethod
    def _variants_of(mutations, at_max: bool) -> List[str]:
        out = list(mutations or [])
        if not out:
            out.append("Normal")
        if at_max:
            out.append("Max Weight")
        return out

    def _crop_new(self, s, species, size, mutations) -> List[str]:
        logged = self._logged_crop_variants(s, species)
        try:
            at_max = float(size) >= 100
        except (TypeError, ValueError):
            at_max = False
        return [v for v in self._variants_of(mutations, at_max) if v not in logged
                and (species, v) not in self._journal_pending]

    def _pet_new(self, s, pet) -> List[str]:
        species = pet.get("petSpecies")
        variants, abilities = self._logged_pet(s, species)
        max_scale = (eco.PETS.get(species) or {}).get("maxScale", 99)
        at_max = float(pet.get("targetScale") or 0) >= max_scale
        new = [v for v in self._variants_of(pet.get("mutations"), at_max) if v not in variants]
        new += [f"ability:{a}" for a in pet.get("abilities") or [] if a not in abilities]
        return [v for v in new if (species, v) not in self._journal_pending]

    def _has_camera(self, s) -> bool:
        """LogItem needs the Camera. It isn't sold anywhere: an NPC brings it
        (see camera_step), so until then only the Camera errand runs."""
        inv = s["data"].get("inventory") or {}
        return any(i.get("toolId") == "Camera" for i in s["items"]) or any(
            t.get("id") == "Camera" for t in inv.get("toolRing") or [])

    def _my_npc_visit(self, s) -> Optional[dict]:
        visits = (self.gs.get_full_state() or {}).get("child", {}).get("data", {}).get("npcVisits") or {}
        me = self.gs.get_player_id()
        for v in (visits.values() if isinstance(visits, dict) else visits):
            if isinstance(v, dict) and v.get("forUserId") == me:
                return v
        return None

    async def camera_step(self, s) -> bool:
        """Get the Camera the way the game hands it out: trying to harvest a
        crop with a variant the Journal lacks, with no Camera, summons an NPC
        (RequestNpcVisit, trigger "harvest") who offers one; accept the gift."""
        if not self.journal_enabled or self._has_camera(s):
            return False
        visit = self._my_npc_visit(s)
        if visit:
            if (visit.get("phase") == "offering" and visit.get("bringsCamera")
                    and not visit.get("gaveCamera") and not self._camera_accepted):
                await asyncio.sleep(random.uniform(1.0, 2.5))  # read the offer
                await self.client.send_command({"type": "AcceptNpcVisitGift"})
                self._camera_accepted = True
                self._log(f"journal: accepted the Camera from {visit.get('npcId', 'a visitor')}")
                return True
            return False  # visitor on the way; wait for the offer
        self._camera_accepted = False
        if time.time() - self._camera_asked_at < 300:
            return False
        for tile_id, obj in s["garden"].items():
            if (obj or {}).get("objectType") != "plant":
                continue
            for sl in obj.get("slots") or []:
                if not sl or s["now"] < sl.get("endTime", 0) or sl.get("locked"):
                    continue
                if not self._crop_new(s, sl.get("species"), sl.get("size", 50), sl.get("mutations")):
                    continue
                if not await walk_to_tile(self.client, self.gs, int(tile_id)):
                    return False
                await self.client.send_command({"type": "RequestNpcVisit", "trigger": {
                    "kind": "harvest", "crop": sl.get("species"), "mutations": list(sl.get("mutations") or [])}})
                self._camera_asked_at = time.time()
                self._log(f"journal: no Camera yet, a visitor is bringing one (asked at a {sl.get('species')})")
                return True
        return False

    def _journal_active(self, s) -> bool:
        return self.journal_enabled and self._has_camera(s)

    def _journal_wanted_species(self, s) -> set:
        """Seed species we hold but have never logged at all (one-time: once a
        species is in the Journal it is never grown for the Journal again)."""
        if not self._journal_active(s):
            return set()
        produce = self._journal(s).get("produce") or {}
        return {sp for sp in self._usable_seeds(s) if sp not in produce}

    # ------------------------------------------------------------ targets
    def _journal_targets(self, s) -> List[Tuple[dict, str, List[str], Optional[int]]]:
        """(target, species, new variants, tile-or-None); one target per new
        (species, variant) so nothing is logged twice in a pass."""
        claimed = set()
        out = []

        def take(target, species, new, tile=None):
            fresh = [v for v in new if (species, v) not in claimed]
            if fresh:
                claimed.update((species, v) for v in fresh)
                out.append((target, species, fresh, tile))

        for it in s["items"]:
            if it.get("itemType") == "Produce" and it.get("id"):
                take({"kind": "inventoryItem", "itemId": it["id"]}, it.get("species"),
                     self._crop_new(s, it.get("species"), it.get("size", 50), it.get("mutations")))
            elif it.get("itemType") == "Pet" and it.get("id"):
                take({"kind": "inventoryItem", "itemId": it["id"]}, it.get("petSpecies"), self._pet_new(s, it))
        for p in s["pets"]:
            if p and p.get("id"):
                take({"kind": "petSlot", "petId": p["id"]}, p.get("petSpecies"), self._pet_new(s, p))
        for tile_id, obj in s["garden"].items():
            if (obj or {}).get("objectType") != "plant":
                continue
            for idx, sl in enumerate(obj.get("slots") or []):
                if not sl or s["now"] < sl.get("endTime", 0):
                    continue
                take({"kind": "growSlot", "slot": int(tile_id), "slotsIndex": sl.get("slotId", idx)},
                     sl.get("species"), self._crop_new(s, sl.get("species"), sl.get("size", 50), sl.get("mutations")),
                     int(tile_id))
        return out

    # ------------------------------------------------------------ action
    async def journal_step(self, s) -> bool:
        if not self._journal_active(s):
            return False
        # Forget pending entries the server has now recorded.
        self._journal_pending = {
            (sp, v) for sp, v in self._journal_pending
            if not (v in self._logged_crop_variants(s, sp)
                    or v in self._logged_pet(s, sp)[0]
                    or (v.startswith("ability:") and v[8:] in self._logged_pet(s, sp)[1]))
        }
        targets = self._journal_targets(s)
        if not targets:
            return False
        # Hold the Camera and take the photo, like the real client, then log.
        await self._select(s, "Camera")
        await self._send({"scopePath": SCOPE, "type": "TakePhoto"})
        await asyncio.sleep(random.uniform(0.3, 0.8))
        # Bag and pets first (no walking), then garden crops nearest-first.
        slot_index = self.gs.get_user_slot_index()
        here = current_position(self.gs)
        targets.sort(key=lambda t: (t[3] is not None,
                                    distance(here, tile_to_server(t[3], slot_index)) if (t[3] is not None and here) else 0))
        logged = []
        for target, species, new, tile in targets[: random.randint(4, 8)]:
            if tile is not None and not await walk_to_tile(self.client, self.gs, tile):
                break
            await self.client.send_command({"type": "LogItem", "target": target})
            self._journal_pending.update((species, v) for v in new)
            logged.append(f"{species} ({', '.join(v.replace('ability:', '') for v in new)})")
            await asyncio.sleep(random.uniform(0.4, 1.0))
        if logged:
            self._log("journal: " + "; ".join(logged))
        return bool(logged)
