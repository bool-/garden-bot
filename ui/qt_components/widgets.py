"""
Carbon-style building blocks: flat buttons, toggle, number stepper,
sparkline, data tables with inline bars, KPI tiles and page scaffolding.
"""

from typing import Callable, List, Optional, Sequence

from PyQt6.QtCore import QPointF, QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .theme import Carbon as C, body_font, font, heading_font, label_font, mono_font, title_font, parse_number


# ------------------------------------------------------------------ labels

def make_label(text: str = "", fnt=None, color: str = C.TEXT_PRIMARY, wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    lab.setFont(fnt or body_font())
    lab.setStyleSheet(f"color: {color};")
    lab.setWordWrap(wrap)
    return lab


def set_color(label: QLabel, color: str):
    if label.property("_color") != color:
        label.setProperty("_color", color)
        label.setStyleSheet(f"color: {color};")


def set_text(label: QLabel, text: str):
    if label.text() != text:
        label.setText(text)


def rule(vertical: bool = False) -> QFrame:
    """1px #393939 separator"""
    line = QFrame()
    line.setObjectName("rule")
    if vertical:
        line.setFixedWidth(1)
    else:
        line.setFixedHeight(1)
    return line


def heading(text: str) -> QLabel:
    return make_label(text, heading_font())


class Page(QWidget):
    """Padded page: 20px light title, helper paragraph, then content."""

    def __init__(self, title: str, helper: str = ""):
        super().__init__()
        self.setObjectName("page")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(C.S5, C.S4, C.S5, C.S4)
        self.outer.setSpacing(C.S4)
        head = QVBoxLayout()
        head.setSpacing(C.S1)
        self.title_label = make_label(title, title_font())
        self.title_label.setFixedHeight(28)
        head.addWidget(self.title_label)
        self.helper_label = make_label(helper, body_font(), C.TEXT_SECONDARY, wrap=True)
        self.helper_label.setVisible(bool(helper))
        head.addWidget(self.helper_label)
        self.outer.addLayout(head)

    def set_helper(self, text: str):
        set_text(self.helper_label, text)
        self.helper_label.setVisible(bool(text))


def section_head(title: str, note: str = "") -> (QWidget, QLabel):
    """h2 on the left, a 12px note on the right (baseline aligned)."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, C.S2)
    lay.setSpacing(C.S3)
    lay.addWidget(heading(title), 0, Qt.AlignmentFlag.AlignBottom)
    lay.addStretch(1)
    note_label = make_label(note, label_font(), C.TEXT_SECONDARY)
    lay.addWidget(note_label, 0, Qt.AlignmentFlag.AlignBottom)
    return w, note_label


# ------------------------------------------------------------------ buttons

class FlatButton(QAbstractButton):
    """Square, borderless button painted by hand.

    text on the left, optional hint (shortcut) in mono; `justify` puts the
    hint at the far right (Pause ... Space). `marker` draws Carbon's selected
    indicator: 'bottom' (3px tab underline) or 'left' (3px side nav bar).
    """

    def __init__(self, text: str = "", hint: str = "", *, bg: Optional[str] = None,
                 hover: Optional[str] = None, fg: str = C.TEXT_PRIMARY, hint_color: str = C.TEXT_HELPER,
                 sel_bg: Optional[str] = None, sel_fg: Optional[str] = None, marker: Optional[str] = None,
                 justify: bool = False, left_rule: bool = False, align_left: bool = True,
                 pad: int = 16, gap: int = 8, fnt=None, hint_font=None, height: Optional[int] = None):
        super().__init__()
        self._text, self._hint = text, hint
        self.bg, self.hover_bg, self.fg = bg, hover, fg
        self.hint_color = hint_color
        self.sel_bg, self.sel_fg, self.marker = sel_bg, sel_fg, marker
        self.justify, self.left_rule, self.align_left = justify, left_rule, align_left
        self.pad, self.gap = pad, gap
        self.setFont(fnt or body_font())
        self.hint_font = hint_font or mono_font(12)
        self.selected = False
        self._min_w = 0
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        if height:
            self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding if not height else QSizePolicy.Policy.Fixed)

    def setText(self, text: str):  # noqa: N802 (Qt naming)
        if text != self._text:
            self._text = text
            self.updateGeometry()
            self.update()

    def text(self):  # noqa: D401
        return self._text

    def set_hint(self, hint: str):
        if hint != self._hint:
            self._hint = hint
            self.updateGeometry()
            self.update()

    def set_selected(self, on: bool):
        if on != self.selected:
            self.selected = on
            self.update()

    def set_colors(self, bg=None, hover=None, fg=None):
        self.bg, self.hover_bg = bg, hover
        if fg:
            self.fg = fg
        self.update()

    def set_min_width(self, w: int):
        self._min_w = w
        self.updateGeometry()

    def sizeHint(self):  # noqa: N802
        fm = QFontMetrics(self.font())
        w = self.pad * 2 + fm.horizontalAdvance(self._text)
        if self._hint:
            w += self.gap + QFontMetrics(self.hint_font).horizontalAdvance(self._hint)
        return QSize(max(w, self._min_w), max(fm.height() + 8, 32))

    def minimumSizeHint(self):  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, _ev):  # noqa: N802
        p = QPainter(self)
        r = self.rect()
        enabled = self.isEnabled()
        bg = self.sel_bg if (self.selected and self.sel_bg) else self.bg
        if enabled and self.underMouse() and self.hover_bg and not self.selected:
            bg = self.hover_bg
        if enabled and self.isDown() and self.hover_bg:
            bg = self.hover_bg
        if bg:
            p.fillRect(r, QColor(bg))
        if self.left_rule:
            p.fillRect(QRect(0, 0, 1, r.height()), QColor(C.BORDER_SUBTLE))
        fg = (self.sel_fg if (self.selected and self.sel_fg) else self.fg) if enabled else C.TEXT_PLACEHOLDER
        p.setFont(self.font())
        p.setPen(QColor(fg))
        fm = QFontMetrics(self.font())
        tw = fm.horizontalAdvance(self._text)
        hint_w = QFontMetrics(self.hint_font).horizontalAdvance(self._hint) if self._hint else 0
        if self.align_left or self.justify:
            x = self.pad
        else:
            x = (r.width() - tw - (self.gap + hint_w if self._hint else 0)) // 2
        p.drawText(QRect(x, 0, tw + 2, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._text)
        if self._hint:
            p.setFont(self.hint_font)
            hc = QColor(self.hint_color if enabled else C.TEXT_PLACEHOLDER)
            p.setPen(hc)
            hx = (r.width() - self.pad - hint_w) if self.justify else (x + tw + self.gap)
            # sit the mono hint on the text baseline
            p.drawText(QRect(hx, 0, hint_w + 2, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self._hint)
        if self.selected and self.marker == "bottom":
            p.fillRect(QRect(0, r.height() - 3, r.width(), 3), QColor(C.INTERACTIVE))
        elif self.selected and self.marker == "left":
            p.fillRect(QRect(0, 0, 3, r.height()), QColor(C.INTERACTIVE))
        p.end()

    def enterEvent(self, ev):  # noqa: N802
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):  # noqa: N802
        self.update()
        super().leaveEvent(ev)


def secondary_button(text: str, height: int = 40) -> FlatButton:
    return FlatButton(text, bg=C.LAYER_02, hover=C.LAYER_HOVER_02, height=height)


# ------------------------------------------------------------------ toggle

class Toggle(QWidget):
    """Carbon toggle: 48x24 track, 18px knob, On/Off text."""

    toggled = pyqtSignal(bool)

    def __init__(self, checked: bool = False):
        super().__init__()
        self._on = bool(checked)
        self.setFixedSize(48 + 8 + 24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFont(body_font())

    def isChecked(self) -> bool:  # noqa: N802
        return self._on

    def setChecked(self, on: bool):  # noqa: N802
        on = bool(on)
        if on != self._on:
            self._on = on
            self.update()

    def mouseReleaseEvent(self, ev):  # noqa: N802
        if self.isEnabled() and ev.button() == Qt.MouseButton.LeftButton:
            self._on = not self._on
            self.update()
            self.toggled.emit(self._on)

    def paintEvent(self, _ev):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        track = QRectF(0, 0, 48, 24)
        color = C.TOGGLE_ON if self._on else C.TOGGLE_OFF
        if not self.isEnabled():
            color = C.LAYER_02
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(color))
        p.drawRoundedRect(track, 12, 12)
        knob_x = 48 - 3 - 18 if self._on else 3
        p.setBrush(QColor(C.TEXT_ON_COLOR if self.isEnabled() else C.TEXT_PLACEHOLDER))
        p.drawEllipse(QRectF(knob_x, 3, 18, 18))
        p.setPen(QColor(C.TEXT_SECONDARY))
        p.setFont(self.font())
        p.drawText(QRect(56, 0, 24, 24), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   "On" if self._on else "Off")
        p.end()


# ------------------------------------------------------------------ stepper

class NumberStepper(QFrame):
    """Carbon number input: value field (editable, accepts 100K / 1.5M),
    then - and + buttons. Emits valueChanged(float) on every commit."""

    valueChanged = pyqtSignal(float)

    def __init__(self, step: float, lo: float, hi: float, fmt: Callable[[float], str]):
        super().__init__()
        self.setObjectName("stepper")
        self.step, self.lo, self.hi, self.fmt = step, lo, hi, fmt
        self._value = lo
        self.setFixedHeight(40)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 1)
        lay.setSpacing(0)
        self.edit = QLineEdit()
        self.edit.setFont(mono_font(14))
        self.edit.setMinimumWidth(112)
        self.edit.setFixedWidth(128)
        self.edit.setFixedHeight(39)
        self.edit.editingFinished.connect(self._commit_text)
        lay.addWidget(self.edit)
        self.dec = FlatButton("−", hover=C.LAYER_HOVER_01, left_rule=True, align_left=False, pad=0,
                              fnt=font(16), height=39)
        self.inc = FlatButton("+", hover=C.LAYER_HOVER_01, left_rule=True, align_left=False, pad=0,
                              fnt=font(16), height=39)
        for b in (self.dec, self.inc):
            b.setFixedWidth(40)
            lay.addWidget(b)
        self.dec.clicked.connect(lambda: self._set(self._value - self.step, emit=True))
        self.inc.clicked.connect(lambda: self._set(self._value + self.step, emit=True))
        self._render()

    def value(self) -> float:
        return self._value

    def setValue(self, v: float):  # noqa: N802
        if not self.edit.hasFocus():
            self._set(v, emit=False)

    def _set(self, v: float, emit: bool):
        v = max(self.lo, min(self.hi, float(v)))
        changed = v != self._value
        self._value = v
        self._render()
        if emit and changed:
            self.valueChanged.emit(v)

    def _render(self):
        text = self.fmt(self._value)
        if self.edit.text() != text:
            self.edit.setText(text)

    def _commit_text(self):
        v = parse_number(self.edit.text())
        if v is None:
            self._render()
            return
        self._set(v, emit=True)
        self.edit.clearFocus()

    def setEnabled(self, on: bool):  # noqa: N802
        super().setEnabled(on)
        self.edit.setEnabled(on)


# ------------------------------------------------------------------ sparkline

class Sparkline(QWidget):
    def __init__(self, color: str = C.MONEY, w: int = 120, h: int = 32):
        super().__init__()
        self.color = color
        self.values: List[float] = []
        self._w = w
        self.setFixedHeight(h)
        self.setMinimumWidth(24)
        self.setMaximumWidth(w)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self):  # noqa: N802
        return QSize(self._w, self.height())

    def set_values(self, values: Sequence[float]):
        values = list(values)
        if values != self.values:
            self.values = values
            self.update()

    def paintEvent(self, _ev):  # noqa: N802
        if len(self.values) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lo, hi = min(self.values), max(self.values)
        span = (hi - lo) or 1
        w, h = self.width(), self.height()
        n = len(self.values) - 1
        pts = QPolygonF([
            QPointF(i * w / n, (h - 2) - (v - lo) / span * (h - 4) if hi != lo else h / 2)
            for i, v in enumerate(self.values)
        ])
        pen = QPen(QColor(self.color), 1.5)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        p.setPen(pen)
        p.drawPolyline(pts)
        p.end()


# ------------------------------------------------------------------ KPI tile

class KpiTile(QWidget):
    """layer-01 tile: 12px label, mono value, 12px sub line."""

    def __init__(self, label: str, value_px: int = 20):
        super().__init__()
        self.setObjectName("tile")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(C.S3, C.S3, C.S3, C.S3)
        lay.setSpacing(C.S1)
        self.label = make_label(label, label_font(), C.TEXT_SECONDARY)
        lay.addWidget(self.label)
        self.value = make_label("-", mono_font(value_px))
        self.value.setFixedHeight(28 if value_px <= 20 else 36)
        lay.addWidget(self.value)
        self.sub = make_label("", label_font(), C.TEXT_SECONDARY)
        lay.addWidget(self.sub)
        lay.addStretch(1)

    def set(self, value: str, sub: Optional[str] = None, sub_color: str = C.TEXT_SECONDARY,
            value_color: str = C.TEXT_PRIMARY):
        set_text(self.value, value)
        set_color(self.value, value_color)
        if sub is not None:
            set_text(self.sub, sub)
            set_color(self.sub, sub_color)
        self.sub.setVisible(sub is not None)


def gap_grid(widgets: Sequence[QWidget], stretches: Optional[Sequence[int]] = None) -> QWidget:
    """Row of tiles separated by 1px #393939 gaps."""
    grid = QWidget()
    grid.setObjectName("gapGrid")
    grid.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    lay = QHBoxLayout(grid)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(1)
    for i, w in enumerate(widgets):
        lay.addWidget(w, (stretches or [1] * len(widgets))[i])
    return grid


# ------------------------------------------------------------------ tables

BAR_ROLE = Qt.ItemDataRole.UserRole + 1  # (fraction, color, text, bar_width or 0 = fill)


class BarDelegate(QStyledItemDelegate):
    """Draws every cell: background and bottom rule from the stylesheet, then
    the text (elided, per-column padding) or an 8px bar (fixed width or
    filling the cell) with optional mono text after it."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        text = opt.text
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget else None
        if style:
            style.drawControl(style.ControlElement.CE_ItemViewItem, opt, painter, widget)
        pads = getattr(widget, "pads", None)
        left, right = pads[index.column()] if pads and index.column() < len(pads) else (16, 16)
        rect = option.rect.adjusted(left, 0, -right, -1)
        data = index.data(BAR_ROLE)
        painter.save()
        if data:
            frac, color, label, width = data
            bar_w = width or (rect.width() - (0 if not label else 64))
            y = rect.center().y() - 3
            painter.fillRect(QRect(rect.left(), y, bar_w, 8), QColor(C.LAYER_02))
            painter.fillRect(QRect(rect.left(), y, int(bar_w * max(0.0, min(1.0, frac))), 8), QColor(color))
            if label:
                painter.setFont(mono_font(12))
                painter.setPen(QColor(C.ERROR if color == C.ERROR else C.TEXT_SECONDARY))
                painter.drawText(QRect(rect.left() + bar_w + 8, rect.top(), max(0, rect.width() - bar_w - 8), rect.height()),
                                 Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
        elif text:
            painter.setFont(opt.font)
            fg = index.data(Qt.ItemDataRole.ForegroundRole)
            painter.setPen(fg.color() if hasattr(fg, "color") else QColor(C.TEXT_PRIMARY))
            elided = QFontMetrics(opt.font).elidedText(text, Qt.TextElideMode.ElideRight, rect.width())
            painter.drawText(rect, int(opt.displayAlignment.value) | int(Qt.AlignmentFlag.AlignVCenter.value), elided)
        painter.restore()


class CarbonHeader(QHeaderView):
    """#393939 header row with per-column padding, semibold text."""

    def paintSection(self, painter, rect, logical):  # noqa: N802
        painter.save()
        painter.fillRect(rect, QColor(C.LAYER_02))
        table = self.parent()
        pads = getattr(table, "pads", None)
        left, right = pads[logical] if pads and logical < len(pads) else (16, 16)
        item = table.horizontalHeaderItem(logical) if table is not None else None
        text = item.text() if item else ""
        align = Qt.AlignmentFlag(item.textAlignment()) if item else Qt.AlignmentFlag.AlignLeft
        painter.setFont(heading_font())
        painter.setPen(QColor(C.TEXT_PRIMARY))
        r = rect.adjusted(left, 0, -right, 0)
        painter.drawText(r, int((align | Qt.AlignmentFlag.AlignVCenter).value),
                         QFontMetrics(heading_font()).elidedText(text, Qt.TextElideMode.ElideRight, r.width()))
        painter.restore()


class Cell:
    """One table cell. color/mono/bold/align, or a bar=(frac, color, text, width)."""

    __slots__ = ("text", "color", "mono", "bold", "right", "bar", "px", "tip", "data")

    def __init__(self, text="", color=None, mono=False, bold=False, right=False, bar=None, px=None,
                 tip=None, data=None):
        self.text, self.color, self.mono, self.bold, self.right = str(text), color, mono, bold, right
        self.bar, self.px, self.tip, self.data = bar, px, tip, data

    def key(self):
        return (self.text, self.color, self.mono, self.bold, self.right, self.bar, self.px, self.tip)


class CarbonTable(QTableWidget):
    """Carbon data table: 32px #393939 header, layer-01 rows with 1px rules.

    columns: list of (title, mode[, (left_pad, right_pad)]) where mode is
    'stretch', 'fit' or an int pixel width; a title starting with '>' is
    right aligned. rowbg: 'layer' (#262626 rows) or 'none' (rules only).
    """

    def __init__(self, columns, row_height: int = 32, header: bool = True, rowbg: str = "layer",
                 selectable: bool = False, fit_height: bool = True):
        super().__init__(0, len(columns))
        self.columns = columns
        self.pads = [tuple(c[2]) if len(c) > 2 else (16, 16) for c in columns]
        self.row_height = row_height
        self.fit_height = fit_height
        self._sig = None
        self.setProperty("rowbg", rowbg)
        self.setProperty("selectable", "true" if selectable else "false")
        self.setFont(body_font())
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection if selectable
                              else QAbstractItemView.SelectionMode.NoSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(selectable)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.verticalHeader().setDefaultSectionSize(row_height)
        self.verticalHeader().setMinimumSectionSize(row_height)
        self.setHorizontalHeader(CarbonHeader(Qt.Orientation.Horizontal, self))
        hh = self.horizontalHeader()
        hh.setVisible(header)
        hh.setFixedHeight(32)
        hh.setFont(heading_font())
        hh.setHighlightSections(False)
        hh.setSectionsClickable(False)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.setItemDelegate(BarDelegate(self))
        for i, col in enumerate(columns):
            title, mode = col[0], col[1]
            right = title.startswith(">")
            item = QTableWidgetItem(title.lstrip(">"))
            item.setTextAlignment((Qt.AlignmentFlag.AlignRight if right else Qt.AlignmentFlag.AlignLeft)
                                  | Qt.AlignmentFlag.AlignVCenter)
            self.setHorizontalHeaderItem(i, item)
            if mode == "stretch":
                hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            elif mode == "fit":
                hh.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
            else:
                hh.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
                self.setColumnWidth(i, int(mode))
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed if fit_height else QSizePolicy.Policy.Expanding)
        self._fit()

    def _fit(self):
        if self.fit_height:
            h = (32 if self.horizontalHeader().isVisible() else 0) + self.rowCount() * self.row_height
            self.setFixedHeight(max(h, 1))

    def set_rows(self, rows: List[List[Cell]], empty: Optional[str] = None) -> bool:
        """Replace the rows when they changed. Returns True when repainted."""
        is_empty = not rows and bool(empty)
        if is_empty:
            rows = [[Cell(empty, color=C.TEXT_HELPER)] + [Cell("") for _ in range(self.columnCount() - 1)]]
        sig = tuple(tuple(c.key() for c in r) for r in rows)
        if sig == self._sig:
            return False
        self._sig = sig
        sel = self.currentRow()
        self.setUpdatesEnabled(False)
        self.clearSpans()
        self.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, cell in enumerate(row):
                item = self.item(r, c)
                if item is None:
                    item = QTableWidgetItem()
                    self.setItem(r, c, item)
                item.setText("" if cell.bar else cell.text)
                f = mono_font(14) if cell.mono else body_font()
                if cell.px:
                    f.setPixelSize(cell.px)
                if cell.bold:
                    f.setWeight(heading_font().weight())
                item.setFont(f)
                item.setForeground(QColor(cell.color or C.TEXT_PRIMARY))
                item.setTextAlignment((Qt.AlignmentFlag.AlignRight if cell.right else Qt.AlignmentFlag.AlignLeft)
                                      | Qt.AlignmentFlag.AlignVCenter)
                item.setData(BAR_ROLE, cell.bar)
                item.setData(Qt.ItemDataRole.UserRole, cell.data)
                item.setToolTip(cell.tip or "")
        if is_empty and self.columnCount() > 1:
            self.setSpan(0, 0, 1, self.columnCount())
        self._fit()
        if not is_empty and 0 <= sel < len(rows) and self.selectionMode() != QAbstractItemView.SelectionMode.NoSelection:
            self.selectRow(sel)
        self.setUpdatesEnabled(True)
        return True

    def row_data(self, row: int, col: int = 0):
        item = self.item(row, col)
        return item.data(Qt.ItemDataRole.UserRole) if item else None
