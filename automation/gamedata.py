"""
Self-updating game data.

The bot's economics (crop prices, pet diets and hunger caps, eggs, mutation
multipliers, market stall zones) come from the magicgarden.gg web client
itself. Builds ship several times a day, so instead of a hand-maintained table
this module reads the current build's JavaScript, extracts the tables and
rewrites data/game_data.json whenever the build changes.

Safety: a fresh extraction only replaces the file when it looks complete
(enough crops, pets, mutations, eggs and every stall the bot uses); otherwise
the last good file is kept and the bot carries on with it.

Run by hand:  python -m automation.gamedata [ROOM]
"""

import json
import os
import re
import sys
import time
import urllib.request
from typing import Dict, Optional

from utils.constants import USER_AGENT

BUNDLED_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "game_data.json")
# Where the live copy is kept. The server sets GAME_DATA_PATH to its writable
# state dir; locally it is the bundled file. Missing -> seeded from bundled.
DATA_PATH = os.environ.get("GAME_DATA_PATH") or BUNDLED_PATH
SITE = "https://magicgarden.gg"
MAX_CHUNKS = 250


# ------------------------------------------------------------------ fetching
def _get(url: str, room: str, accept: str = "*/*") -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": accept,
        "Referer": f"{SITE}/r/{room}",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def current_build(room: str) -> Optional[str]:
    html = _get(f"{SITE}/r/{room}", room, "text/html")
    m = re.search(r"/version/([A-Za-z0-9._-]+)/assets/", html)
    return m.group(1) if m else None


def _crawl(room: str) -> Dict[str, str]:
    """Every JS chunk reachable from the room page's entry script."""
    html = _get(f"{SITE}/r/{room}", room, "text/html")
    entries = re.findall(r'src="(/version/[^"]+?/assets/[\w.-]+\.js)"', html)
    if not entries:
        raise RuntimeError("no entry scripts on the room page")
    base = SITE + entries[-1].rsplit("/", 1)[0] + "/"
    queue = [e.rsplit("/", 1)[1] for e in entries]
    seen: Dict[str, str] = {}
    while queue and len(seen) < MAX_CHUNKS:
        name = queue.pop()
        if name in seen:
            continue
        try:
            body = _get(base + name, room)
        except Exception:
            continue
        seen[name] = body
        for dep in re.findall(r"""["'`](?:\./|assets/)([\w.-]+\.js)["'`]""", body):
            if dep not in seen:
                queue.append(dep)
    return seen


# ---------------------------------------------------------------- extraction
def _num(x: str) -> float:
    v = float(x)
    return int(v) if v.is_integer() else v


def _weights(body: str) -> Dict[str, float]:
    out = {}
    for part in body.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            try:
                out[k.strip()] = _num(v)
            except ValueError:
                pass
    return out


def extract(sources: Dict[str, str]) -> dict:
    allsrc = "\n".join(sources.values())

    crops = {}
    keys = list(re.finditer(r"(\w+):\{name:`[^`]+`,seed:", allsrc))
    for i, m in enumerate(keys):
        end = keys[i + 1].start() if i + 1 < len(keys) else m.start() + 2500
        seg = allsrc[m.start(): min(end, m.start() + 4000)]

        def f(rx):
            r = re.search(rx, seg)
            return r.group(1) if r else None

        price, sell, size = f(r"coinPrice:([\d.e]+)"), f(r"baseSellPrice:([\d.e]+)"), f(r"maxSizeMultiplier:([\d.e]+)")
        if not (price and sell and size):
            continue
        crop = {
            "seedPrice": _num(price),
            "rarity": f(r"rarity:\w+\.(\w+)"),
            "harvestType": f(r"harvestType:\w+\.(\w+)"),
            "baseSellPrice": _num(sell),
            "maxSizeMultiplier": _num(size),
        }
        secs = f(r"secondsToMature:([\d.e]+)")
        if secs:
            crop["secondsToMature"] = _num(secs)
        surfaces = f(r"unavailableSurfaces:\[([^\]]*)\]")
        if surfaces and "web" in surfaces:
            crop["webUnavailable"] = True  # the web client can't buy its seed (server rejects it)
        crops[m.group(1)] = crop

    pets = {}
    pkeys = list(re.finditer(r"(\w+):\{name:`[^`]+`,coinsToFullyReplenishHunger:", allsrc))
    for i, m in enumerate(pkeys):
        end = pkeys[i + 1].start() if i + 1 < len(pkeys) else m.start() + 1500
        seg = allsrc[m.start(): min(end, m.start() + 1500)]

        def f(rx):
            r = re.search(rx, seg)
            return r.group(1) if r else None

        cap, diet = f(r"coinsToFullyReplenishHunger:([\d.e]+)"), f(r"diet:\[([^\]]*)\]")
        if not (cap and diet):
            continue
        hours, scale, sell = f(r"hoursToMature:([\d.]+)"), f(r"maxScale:([\d.]+)"), f(r"maturitySellPrice:([\d.e]+)")
        pets[m.group(1)] = {
            "hungerCap": _num(cap),
            "abilityWeights": _weights(f(r"innateAbilityWeights:\{([^}]*)\}") or ""),
            "maxScale": _num(scale) if scale else 2,
            "sell": _num(sell) if sell else 0,
            "hoursToMature": _num(hours) if hours else None,
            "rarity": f(r"rarity:\w+\.(\w+)"),
            "diet": [d.strip("` ") for d in diet.split(",") if d.strip("` ")],
        }

    mutations = {
        m.group(1): {"coinMultiplier": _num(m.group(3)), "group": m.group(4), "baseChance": _num(m.group(2))}
        for m in re.finditer(r"(\w+):\{name:`\w+`,baseChance:([\d.]+),coinMultiplier:([\d.]+),group:`(\w+)`", allsrc)
    }

    eggs = {}
    for m in re.finditer(
        r"(\w+Egg):\{sprite:[^,]+,name:`[^`]+`,coinPrice:([\d.e]+).{0,200}?secondsToHatch:([\d.e]+),"
        r"faunaSpawnWeights:\{([^}]*)\}",
        allsrc,
    ):
        eggs[m.group(1)] = {"price": _num(m.group(2)), "hatchS": _num(m.group(3)), "weights": _weights(m.group(4))}
        seg = allsrc[m.start(): m.start() + 600]
        surf = re.search(r"unavailableSurfaces:\[([^\]]*)\]", seg)
        if surf and "web" in surf.group(1):
            eggs[m.group(1)]["webUnavailable"] = True

    abilities = {}
    for m in re.finditer(
        r"(\w+):\{name:`([^`]+)`,trigger:`(\w+)`,(?:baseProbability:([\d.]+),)?baseParameters:\{([^}]*)\}", allsrc
    ):
        abilities[m.group(1)] = {"name": m.group(2), "trigger": m.group(3),
                                 "baseProbability": _num(m.group(4)) if m.group(4) else None}

    zones: Dict[str, dict] = {}
    for m in re.finditer(
        r"\{class:`(\w+)`,data:\[([\d,]+)\],height:\d+,id:\d+,locked:!0,name:`(\w+)`[^}]*?width:(\d+)", allsrc
    ):
        cls, data, name, width = m.group(1), m.group(2), m.group(3), int(m.group(4))
        cells = [(i % width, i // width) for i, v in enumerate(data.split(",")) if v not in ("0", "")]
        if not cells:
            continue
        xs, ys = [c[0] for c in cells], [c[1] for c in cells]
        box = {"x": [min(xs), max(xs)], "y": [min(ys), max(ys)]}
        zones.setdefault(name, {})["zone" if cls == "BuildingActivation" else "spawn"] = box

    def stall(name, interaction=None, stand_row=None):
        z = zones.get(name) or {}
        zone = z.get("zone")
        if not zone:
            return None
        stand = z.get("spawn") or {"x": zone["x"], "y": [stand_row(zone)] * 2 if stand_row else zone["y"]}
        out = {"zone": zone, "stand": stand}
        if interaction:
            out["interaction"] = interaction
        return out

    stalls = {
        "seed": stall("seedShop", "seed"),
        "egg": stall("eggShop", "egg"),
        "tool": stall("toolShop", "tool"),
        "decor": stall("decorShop", "decor"),
        "sellCrops": stall("sellCropsShop"),
        # no spawn layer for the pet stall: stand on its row nearest the crop stand
        "sellPet": stall("sellPetShop", stand_row=lambda z: z["y"][1]),
    }
    return {"crops": crops, "pets": pets, "mutations": mutations, "eggs": eggs,
            "abilities": abilities, "stalls": {k: v for k, v in stalls.items() if v}}


def _looks_complete(d: dict) -> bool:
    return (
        len(d.get("crops", {})) >= 40
        and len(d.get("pets", {})) >= 20
        and len(d.get("mutations", {})) >= 6
        and len(d.get("eggs", {})) >= 5
        and all(k in d.get("stalls", {}) for k in ("seed", "egg", "tool", "sellCrops", "sellPet"))
        and all(p.get("diet") for p in d["pets"].values())
    )


# ------------------------------------------------------------------- caching
def load() -> dict:
    for path in (DATA_PATH, BUNDLED_PATH):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return {}


def ensure_current(room: str, force: bool = False) -> dict:
    """Make data/game_data.json match the room's live build. Returns the data."""
    try:
        cached = load()
    except (OSError, ValueError):
        cached = {}
    try:
        build = current_build(room)
    except Exception as e:
        print(f"[gamedata] could not read the live build ({e}); using cached data")
        return cached
    if not force and build and cached.get("build") == build:
        return cached
    print(f"[gamedata] build {build} (cached: {cached.get('build')}) - extracting game tables...")
    try:
        fresh = extract(_crawl(room))
    except Exception as e:
        print(f"[gamedata] extraction failed ({e}); keeping cached data")
        return cached
    if not _looks_complete(fresh):
        counts = {k: len(v) for k, v in fresh.items()}
        print(f"[gamedata] extraction looked incomplete {counts}; keeping cached data")
        return cached
    fresh["build"] = build
    fresh["extractedAt"] = int(time.time())
    fresh["_source"] = ("Extracted automatically from the magicgarden.gg web client by automation/gamedata.py. "
                        "Do not hand-edit; it is rewritten on every new build.")
    try:
        tmp = DATA_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(fresh, f, indent=1)
        os.replace(tmp, DATA_PATH)
    except OSError as e:  # never take the bot down over a cache write
        print(f"[gamedata] could not save {DATA_PATH} ({e}); using the fresh tables in memory only")
        return fresh
    print(f"[gamedata] updated: {len(fresh['crops'])} crops, {len(fresh['pets'])} pets, "
          f"{len(fresh['eggs'])} eggs, {len(fresh['mutations'])} mutations")
    return fresh


if __name__ == "__main__":
    ensure_current(sys.argv[1] if len(sys.argv) > 1 else "MG1", force=True)
