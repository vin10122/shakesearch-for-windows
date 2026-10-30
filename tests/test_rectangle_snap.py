import unittest

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QColor, QPen, QPolygonF
from PySide6.QtCore import QPointF

from rectangle_snap import find_rectangle


class RectangleDetectionTests(unittest.TestCase):
    def image(self, scale=1, rounded=False):
        image = QImage(800 * scale, 600 * scale, QImage.Format.Format_RGBA8888)
        image.fill(QColor('#242b36'))
        painter = QPainter(image)
        painter.scale(scale, scale)
        painter.setPen(QPen(QColor('#8493a5'), 2))
        painter.setBrush(QColor('#404b5a'))
        if rounded:
            painter.drawRoundedRect(QRectF(150, 140, 360, 240), 15, 15)
        else:
            painter.drawRect(QRectF(150, 140, 360, 240))
        # Adjacent and nested rectangles must not steal the selection.
        painter.drawRect(QRectF(550, 140, 190, 240))
        painter.drawRect(QRectF(220, 200, 160, 100))
        painter.end()
        return image

    def assert_target(self, box):
        self.assertIsNotNone(box)
        for actual, expected in zip((box.left(), box.top(), box.right(), box.bottom()), (150, 140, 510, 380)):
            self.assertAlmostEqual(actual, expected, delta=4)

    def test_oversized_circle_bounds_snap_to_card(self):
        self.assert_target(find_rectangle(self.image(), QRectF(126, 122, 412, 282), (800, 600)))

    def test_imperfect_selection_inside_card_snaps_outward(self):
        self.assert_target(find_rectangle(self.image(), QRectF(170, 156, 320, 205), (800, 600)))

    def test_rounded_card_and_high_dpi(self):
        self.assert_target(find_rectangle(self.image(2, rounded=True), QRectF(130, 125, 400, 270), (800, 600)))

    def test_no_edges_preserves_free_selection(self):
        image = QImage(800, 600, QImage.Format.Format_RGBA8888)
        image.fill(QColor('#444444'))
        self.assertIsNone(find_rectangle(image, QRectF(120, 100, 300, 220), (800, 600)))

    def test_nearby_unrelated_card_is_not_selected(self):
        self.assertIsNone(find_rectangle(self.image(), QRectF(20, 25, 80, 75), (800, 600)))

    def test_rotated_shape_is_not_treated_as_axis_aligned_rectangle(self):
        image = QImage(800, 600, QImage.Format.Format_RGBA8888)
        image.fill(QColor('#222222'))
        painter = QPainter(image)
        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawPolygon(QPolygonF([QPointF(160, 200), QPointF(360, 110),
                                       QPointF(450, 310), QPointF(250, 400)]))
        painter.end()
        self.assertIsNone(find_rectangle(image, QRectF(140, 90, 330, 330), (800, 600)))
