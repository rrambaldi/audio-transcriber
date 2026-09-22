"""Drawing what a recording sounds like: the live trace and the still picture.

Two shapes, one reading. Both take loudness and put them through
:func:`options.level_percent` — decibels with the floor at -60 dBFS — because
a linear drawing of speech is a flat line with four bumps in it, and because
the level meter beside them is read on exactly that scale. Nothing here
decides anything: the numbers arrive measured, from the capture thread while a
recording is being made and from ``waveform.json`` afterwards.

The live one is drawn as separate columns and the still one as a filled shape,
and that difference is on purpose. The trace is a handful of readings arriving
one at a time, and columns say so; a whole recording is four hundred of them
across a couple of hundred pixels, where columns would be a grey smear.
"""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QPainter, QPainterPath

from .. import waveform
from .options import level_percent

#: The thinnest a column or a waist may be drawn, as a fraction of the half
#: height. Silence reads as a line through the middle — a statement — rather
#: than as a gap, which reads as something broken.
MIN_ARM = 0.04

#: Space between the live trace's columns, in pixels.
COLUMN_GAP = 1.0

#: Nothing is ever drawn thinner than this, in pixels. Silence has to be a
#: line somebody can see: drawn true to scale it rounds away to nothing, and a
#: quiet recording then looks like a broken one.
MIN_PX = 0.5


def arms(values, scale):
    """Half-heights, 0..1, one per reading: the drawing's only arithmetic."""
    return [max(MIN_ARM, level_percent(float(value) / scale) / 100.0)
            for value in values]


def draw_trace(painter, rect, values, colour, scale=1.0):
    """The last few seconds, oldest on the left, as one column per reading."""
    values = list(values or [])
    if not values or rect.width() <= 0:
        return
    step = rect.width() / len(values)
    width = max(1.0, step - COLUMN_GAP)
    middle = rect.center().y()
    reach = rect.height() / 2.0
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(colour)
    for index, arm in enumerate(arms(values, scale)):
        high = max(MIN_PX, arm * reach)
        painter.drawRect(QRectF(rect.left() + index * step, middle - high,
                                width, high * 2))
    painter.restore()


def wave_shape(rect, values, scale):
    """The outline of a whole recording: mirrored about the middle."""
    path = QPainterPath()
    values = list(values or [])
    if not values or rect.width() <= 0:
        return path
    step = rect.width() / len(values)
    middle = rect.center().y()
    reach = rect.height() / 2.0
    heights = [max(MIN_PX, arm * reach) for arm in arms(values, scale)]
    path.moveTo(QPointF(rect.left(), middle - heights[0]))
    for index, high in enumerate(heights):
        left = rect.left() + index * step
        path.lineTo(QPointF(left, middle - high))
        path.lineTo(QPointF(left + step, middle - high))
    for index in range(len(heights) - 1, -1, -1):
        left = rect.left() + index * step
        path.lineTo(QPointF(left + step, middle + heights[index]))
        path.lineTo(QPointF(left, middle + heights[index]))
    path.closeSubpath()
    return path


def draw_wave(painter, rect, values, colour, scale=waveform.SCALE):
    """A whole recording, filled, stretched to whatever ``rect`` is wide."""
    shape = wave_shape(rect, values, scale)
    if shape.isEmpty():
        return
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.fillPath(shape, colour)
    painter.restore()
