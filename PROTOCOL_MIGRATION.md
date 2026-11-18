# Protocol migration — magicgarden.gg v2036 (2026-11-14)

The bot was written against an older magicgarden.gg build (`d9f1402`) and had
**completely stopped working** — the server rejected that release at
authentication with `409 VersionExpired`, so it could never connect, and the
action/message protocol had also changed substantially underneath it.

This migration was derived from the **live v2036 client**: static analysis of
the shipped JS bundle, plus live WebSocket frame capture from a real signed-in
game session (capturing the exact bytes the real client sends for each action).

---

## Headline change: the `QuinoaCommand` envelope

In v2036 **every discrete game action is wrapped in a `QuinoaCommand`** carrying
a per-connection monotonic `commandSequence` (starts at 1) and a fresh
`requestId` UUID. The bot used to send raw actions like
`{"type":"HarvestCrop",...}`; those are now ignored/rejected.

Captured real-client examples:
```json
{"scopePath":["Room","Quinoa"],"type":"QuinoaCommand","requestId":"<uuid4>","commandSequence":1,
 "command":{"type":"PurchaseShopItem","shop":"seed","viewMode":"grid","item":{"itemType":"Seed","species":"Carrot"}}}

{"scopePath":["Room","Quinoa"],"type":"QuinoaCommand","requestId":"<uuid4>","commandSequence":3,
 "command":{"type":"HarvestCrop","slot":17,"slotsIndex":0,"cropItemId":"<uuid4>"},"successorItemId":"Aloe"}
```
Implemented as `MagicGardenClient.send_command(command, **extra)` in
`network/client.py` (sequence resets to 0 on each connect). Continuous state
updates (`PlayerPosition`) are still sent **raw** via `send()` and must NOT be
wrapped.

---

## ✅ Fixed and verified — connection + behavior

| Area | Old (broken) | New (v2036) | File |
|------|--------------|-------------|------|
| Build version | `GAME_VERSION="d9f1402"` → `409 VersionExpired` | `"2036"` → `200 {"isAuthenticated":false}` | `utils/constants.py` |
| Connect handshake | `VoteForGame` + `SetSelectedGame` (removed) | `{"type":"SocketOpened"}` on open; server replies `Welcome` | `network/client.py` |
| Keepalive | matched bare `"ping"` | server sends `ping:<n>`; reply plain `pong` (prefix match) | `network/client.py` |
| Incremental state | `PartialState`, top-level `patches` | `RoomFrame`, patches under `state.patches` | `network/protocol.py` |
| Bot tell | self-sent `{"type":"Ping"}` every 2s | real client never does this (only pongs); removed | `network/client.py` |

**Refresh the version** when auth starts 409'ing: load `https://magicgarden.gg/`
and read the build id from the `<script src="/version/<id>/...">` tag (numeric,
e.g. `2036`).

Captured connect sequence:
```
→ {"type":"SocketOpened"}
→ {"scopePath":["Room","Quinoa"],"type":"SetPlayerInteraction","interaction":"seed"}   (optional tool-select)
← Welcome (fullState: data.players + child[Quinoa].data.userSlots…)
← QuinoaPlayerTimelineSnapshot, Config
← RoomFrame … (repeats)
↔ "ping:<n>" / "pong"
```

---

## ✅ Fixed and verified — actions (all wrapped in QuinoaCommand)

State **reading** is unchanged in v2036 (garden `tileObjects[id].slots[i]`,
`shops.<key>.inventory`, `petSlots[i]`, `inventory.items[]` all have the same
shape), so the bot's find/scan logic still works. Only the **sending** changed.

| Action | New command (inside QuinoaCommand) | Notes | File |
|--------|-----------------------------------|-------|------|
| Harvest | `{HarvestCrop, slot, slotsIndex, cropItemId}` + top-level `successorItemId` | `cropItemId` is a **client-generated uuid4** (it becomes the Produce item's inventory `id` — verified); `successorItemId` = replant species, omitted to not replant | `automation/harvest.py`, `ui/qt_gui.py` |
| Plant | `{PlantSeed, slot, species}` | unchanged fields | `automation/harvest.py`, `ui/qt_gui.py` |
| Sell | `{SellAllCrops}` | — | `automation/harvest.py` |
| Buy seed | `{PurchaseShopItem, shop:"seed", viewMode:"grid", item:{itemType:"Seed", species}}` | was `PurchaseSeed`; **captured exactly** | `automation/shop.py`, `ui/qt_components/shop_panel.py` |
| Buy egg | `{PurchaseShopItem, shop:"egg", viewMode:"grid", item:{itemType:"Egg", eggId}}` | was `PurchaseEgg` | `automation/shop.py` |
| Buy tool/decor (UI) | `{PurchaseShopItem, shop, viewMode:"grid", item:{itemType, toolId|decorId}}` | was `BuyShopItem` | `ui/qt_components/shop_panel.py` |
| Feed pet | `{FeedPet, petItemId, cropItemId}` | `petItemId`=`petSlots[i].id`, `cropItemId`=Produce item `id`; fields unchanged, now wrapped | `automation/pets.py` |
| Hatch egg | `{HatchEgg, slot}` | unchanged, now wrapped | `ui/qt_gui.py` |
| Grow egg | `{GrowEgg, slot, eggId}` | was `PlantEgg` | `ui/qt_gui.py` |

`shop` is the shop key from `child.data.shops` (`seed`/`egg`/`tool`/`decor`/…).
`PurchaseShopItem` and `HarvestCrop` shapes were captured verbatim from the real
client; the rest use the same (captured) QuinoaCommand wrapper with inner fields
confirmed against the bundle schemas and the live state structure.

---

## ❌ Removed: client-pushed pet movement

Old `PetPositions` (bulk client-pushed pet coordinates) **no longer exists**.
Pet movement is now **entirely server-driven**: the server publishes each pet's
motion path at `petSlotInfos[id].motion = {path:[{x,y}…], stepDurationMs,
startedAtMs, source:"wander"}`. A real player cannot push pet positions, so
emulating it is both impossible and a detection tell. `initialize_pets()` and
`move_pets_randomly()` in `automation/pets.py` are now no-ops; pets wander on
their own. (Pet *feeding* still works and is unchanged except for the wrapper.)

---

## Capture method (for future protocol refreshes)
In the built-in browser, sign into the account, then in the page console:
patch `WebSocket.prototype.send` to log outgoing frames and add a `message`
listener to `MagicCircle_RoomConnection.currentWebSocket` for incoming; call
`MagicCircle_RoomConnection.reconnect()` to capture a fresh `Welcome`. Perform
each UI action once and read the logged `QuinoaCommand` frames. The full live
game state is reachable via the `Welcome.fullState` captured this way.
