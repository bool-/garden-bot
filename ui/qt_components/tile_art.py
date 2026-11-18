"""
Garden tile art (design: "Garden tiles" artboard).

Each tile reads at a glance:
- soil / wood background, a tiny icon per plant family in the plant's colour
- growing: faint icon, a green fill rising from the bottom with maturity
- ripe: full colour icon with a soft glow
- Gold / Rainbow stamp: coloured border plus a G / R corner badge
- held for a stamp: orange ring; pet food: green diamond
- mutations: up to three coloured dots along the bottom
- eggs: egg icon coloured by rarity with a purple hatch-progress fill

Icons are rendered once per (icon, colour, size) from inline SVG and cached,
so painting a 276-cell map stays cheap.
"""

import zlib
from typing import Dict, Optional, Tuple

from PyQt6.QtCore import QByteArray, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PyQt6.QtSvg import QSvgRenderer

from automation import economy as eco

SOIL = QColor("#2E241C")
WOOD = QColor("#4A3B2C")
GROW_FILL = QColor(66, 190, 101, 56)
EGG_FILL = QColor(165, 110, 255, 56)
GOLD = QColor("#F1C21B")
RAINBOW = ["#FF8389", "#F1C21B", "#42BE65", "#4589FF", "#BE95FF"]
HELD = QColor("#FF832B")
FOOD = QColor("#42BE65")

ICONS = {
    "sunflower": "M12 9.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1",
    "flower": "M12 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4zM12 10c0-3 1-5 0-6-1 1 0 3 0 6zM14 12c3 0 5 1 6 0-1-1-3 0-6 0zM12 14c0 3-1 5 0 6 1-1 0-3 0-6zM10 12c-3 0-5-1-6 0 1 1 3 0 6 0z",
    "fruit": "M12 7c-4 0-6 3-6 6.5S8.5 20 12 20s6-3 6-6.5S16 7 12 7zM12 7c0-2 1-3 3-4M12 7c-1-1.5-3-2-4-1.5",
    "pod": "M6 18c2-6 6-10 12-12-1 6-5 11-12 12zM9 15l1.5-1.5M12 12l1.5-1.5",
    "succulent": "M12 20V12M12 12L6 6M12 12l6-6M12 14l-6-2M12 14l6-2M12 12V4",
    "stalk": "M10 21V3M14 21V8M10 14h4M14 14l3-3M10 9L7 6",
    "star": "M12 3l2.6 5.6 6 .7-4.5 4.1 1.2 6L12 16.6 6.7 19.4l1.2-6L3.4 9.3l6-.7z",
    "mushroom": "M4 11a8 8 0 0 1 16 0H4zM10 11v8h4v-8",
    "egg": "M12 3c-3.5 0-6 5-6 9a6 6 0 0 0 12 0c0-4-2.5-9-6-9z",
}

# Plant family -> icon. Anything unlisted is a flower.
FAMILY = {
    "sunflower": {"Sunflower", "Marigold"},
    "star": {"Starweaver", "DawnCelestial", "MoonCelestial", "ThunderCelestial", "Dawnbreaker",
             "Emberbloom", "Embercrown", "Witchfire"},
    "mushroom": {"Mushroom", "Milkcap", "ThunderCelestialShroomPlant", "GhostPlant", "Foxfire"},
    "fruit": {"PassionFruit", "Watermelon", "Pumpkin", "Apple", "Pear", "Peach", "Persimmon", "Lemon",
              "Grape", "Lychee", "DragonFruit", "Cacao", "Coconut", "Strawberry", "Blueberry", "Tomato",
              "Date", "PricklyPear", "Eggplant", "Squash", "Ube", "Beet", "Carrot", "Cabbage", "Banana"},
    "pod": {"FavaBean", "Pepper", "Habanero", "Leek", "Corn", "Cardoon"},
    "succulent": {"Aloe", "Cactus", "Echeveria", "BurrosTail", "Clover", "FourLeafClover"},
    "stalk": {"Bamboo", "PineTree", "Cattail", "VariegatedCattail", "Lavender", "Saffron"},
}
COLORS = {
    "Sunflower": "#F1C21B", "Marigold": "#FF9F43", "Starweaver": "#BE95FF", "DawnCelestial": "#FF7EB6",
    "MoonCelestial": "#A6C8FF", "ThunderCelestial": "#D4BBFF", "PassionFruit": "#FF832B",
    "Watermelon": "#42BE65", "FavaBean": "#6FDC8C", "Aloe": "#3DDBD9", "Lily": "#F4F4F4",
    "Bamboo": "#A7F0BA", "Chrysanthemum": "#FF8389", "Mushroom": "#D4BBFF", "Carrot": "#FF832B",
    "Daffodil": "#FDDC69", "Cactus": "#6FDC8C", "Pumpkin": "#FF832B", "Lemon": "#FDDC69",
}
PALETTE = ["#FF8389", "#FF832B", "#F1C21B", "#6FDC8C", "#3DDBD9", "#78A9FF", "#BE95FF", "#FF7EB6"]
MUTATION_COLORS = {
    "Frozen": "#82CFFF", "Chilled": "#BAE6FF", "Wet": "#4589FF", "Ambershine": "#FF9F43",
    "Ambercharged": "#FF832B", "Dawnlit": "#FF7EB6", "Dawncharged": "#FF3D96",
    "Thunderstruck": "#D4BBFF", "Thundercharged": "#A56EFF",
}
EGG_COLORS = {"CommonEgg": "#E0E0E0", "UncommonEgg": "#6FDC8C", "RareEgg": "#4589FF",
              "LegendaryEgg": "#FF832B", "MythicalEgg": "#BE95FF"}

_icon_cache: Dict[Tuple[str, str, int], QPixmap] = {}


def family(species: Optional[str]) -> str:
    for fam, names in FAMILY.items():
        if species in names:
            return fam
    return "flower"


def species_color(species: Optional[str]) -> str:
    if species in COLORS:
        return COLORS[species]
    return PALETTE[zlib.crc32((species or "").encode()) % len(PALETTE)]


def icon_pixmap(name: str, color: str, size: int) -> QPixmap:
    key = (name, color, size)
    pm = _icon_cache.get(key)
    if pm is None:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
               f'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="{ICONS[name]}"/></svg>')
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        QSvgRenderer(QByteArray(svg.encode())).render(painter)
        painter.end()
        _icon_cache[key] = pm
    return pm


# ------------------------------------------------------------------ model
def describe(obj: Optional[dict], now_ms: int, hold_min: int, food: set) -> dict:
    """What to draw for one garden tile object."""
    if not obj:
        return {"kind": "empty"}
    kind = obj.get("objectType")
    if kind == "egg":
        egg = obj.get("eggId")
        start = obj.get("plantedAt")
        ready = obj.get("maturedAt")
        if ready is None and start is not None:
            ready = start + eco.egg_hatch_seconds(egg) * 1000
        ripe = ready is not None and now_ms >= ready
        grown = 1.0 if ripe else _frac(start, ready, now_ms)
        return {"kind": "egg", "egg": egg, "ripe": ripe, "grown": grown}
    if kind != "plant":
        return {"kind": "empty"}
    slots = [s for s in obj.get("slots") or [] if s]
    if not slots:
        return {"kind": "empty"}
    species = obj.get("species") or slots[0].get("species")

    def rank(s):
        ripe = now_ms >= (s.get("endTime") or 0)
        return (eco.has_growth_mutation(s.get("mutations")), ripe, len(s.get("mutations") or []))

    best = max(slots, key=rank)
    ripe = now_ms >= (best.get("endTime") or 0)
    muts = best.get("mutations") or []
    stamp = "rainbow" if "Rainbow" in muts else ("gold" if "Gold" in muts else None)
    others = [m for m in muts if m not in ("Gold", "Rainbow")]
    return {
        "kind": "plant", "species": species, "ripe": ripe,
        "grown": 1.0 if ripe else _frac(best.get("startTime"), best.get("endTime"), now_ms),
        "stamp": stamp if ripe or stamp else None,
        "held": ripe and not stamp and eco.base_price(species) >= hold_min and species not in food,
        "food": species in food,
        "muts": others,
    }


def _frac(start, end, now) -> float:
    if not start or not end or end <= start:
        return 0.0
    return max(0.0, min(1.0, (now - start) / (end - start)))


# ------------------------------------------------------------------ paint
def paint_tile(p: QPainter, rect: QRectF, d: dict, walk: bool = False):
    s = rect.width()
    if walk:
        p.fillRect(rect, WOOD)
        return
    p.fillRect(rect, SOIL)
    kind = d.get("kind")
    if kind == "empty":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 18))
        p.drawEllipse(rect.center(), s * 0.04, s * 0.04)
        return

    if kind == "egg":
        color = EGG_COLORS.get(d.get("egg"), "#E0E0E0")
        icon, fill_color = "egg", EGG_FILL
    else:
        color = species_color(d.get("species"))
        icon, fill_color = family(d.get("species")), GROW_FILL

    ripe = d.get("ripe")
    if not ripe and d.get("grown", 0) > 0:
        h = s * d["grown"]
        p.fillRect(QRectF(rect.left(), rect.bottom() - h, s, h), fill_color)
    if ripe:  # soft glow behind the icon
        g = QRadialGradient(rect.center(), s * 0.55)
        glow = QColor(color)
        glow.setAlpha(70)
        g.setColorAt(0, glow)
        glow.setAlpha(0)
        g.setColorAt(1, glow)
        p.fillRect(rect, g)

    isz = max(8, int(s * 0.66))
    p.setOpacity(1.0 if ripe else 0.35 + 0.45 * d.get("grown", 0))
    p.drawPixmap(int(rect.center().x() - isz / 2), int(rect.center().y() - isz / 2), icon_pixmap(icon, color, isz))
    p.setOpacity(1.0)

    stamp = d.get("stamp")
    if stamp:
        pen = QPen(GOLD if stamp == "gold" else QColor("#BE95FF"), 2)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(rect.adjusted(1, 1, -1, -1))
        b = max(7.0, s * 0.3)
        badge = QRectF(rect.right() - b, rect.top(), b, b)
        if stamp == "gold":
            p.fillRect(badge, GOLD)
        else:
            stripe = b / len(RAINBOW)
            for i, c in enumerate(RAINBOW):
                p.fillRect(QRectF(badge.left(), badge.top() + i * stripe, b, stripe + 0.5), QColor(c))
        if b >= 9:
            f = QFont("Cascadia Mono")
            f.setPixelSize(int(b * 0.62))
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#161616"))
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, "G" if stamp == "gold" else "R")

    if d.get("held"):
        r = max(2.5, s * 0.08)
        p.setPen(QPen(HELD, max(1.5, s * 0.05)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(rect.right() - r - 3, rect.bottom() - r - 3), r, r)
    if d.get("food"):
        r = max(3.0, s * 0.09)
        cx, cy = rect.left() + r + 3, rect.top() + r + 3
        path = QPainterPath()
        path.moveTo(cx, cy - r)
        path.lineTo(cx + r, cy)
        path.lineTo(cx, cy + r)
        path.lineTo(cx - r, cy)
        path.closeSubpath()
        p.fillPath(path, FOOD)

    muts = d.get("muts") or []
    if muts:
        dot = max(3.0, s * 0.12)
        x = rect.left() + 3
        y = rect.bottom() - 3 - dot
        p.setPen(Qt.PenStyle.NoPen)
        for m in muts[:3]:
            p.setBrush(QColor(MUTATION_COLORS.get(m, "#C6C6C6")))
            p.drawEllipse(QRectF(x, y, dot, dot))
            x += dot + 2
