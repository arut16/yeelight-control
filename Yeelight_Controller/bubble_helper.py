#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import argparse
from PyQt5.QtWidgets import QApplication, QWidget, QGraphicsOpacityEffect
from PyQt5.QtCore import (
    Qt, QTimer, QRectF,
    QPropertyAnimation, QEasingCurve,
    QSequentialAnimationGroup, QPauseAnimation
)
from PyQt5.QtGui import QPainter, QPainterPath, QColor, QFont, QPen


class SpeechBubble(QWidget):
    """
    Bulle type BD, au-dessus du plein écran, non-focus, curseur masqué,
    fade-in/out via QGraphicsOpacityEffect (fiable même si windowOpacity est ignoré).
    """
    def __init__(self, x, y, w, h, text,
                 hold_ms=4000, tailx=None,
                 fadein_ms=1500, fadeout_ms=1500,
                 parent=None):
        super().__init__(parent)

        # ---- Config visuelle
        self.text = text
        self.w, self.h = int(w), int(h)        # corps (hors queue)
        self.tail_w = 18
        self.tail_h = 12
        self.radius = 12
        self.bg = QColor("#fff9c4")            # jaune très pâle
        self.border = QColor(0, 0, 0, 80)      # contour léger
        self.shadow = QColor(0, 0, 0, 60)      # ombre
        self.tailx = float(tailx) if tailx is not None else (self.w / 2.0)

        # Durées
        self.fadein_ms = int(fadein_ms)
        self.fadeout_ms = int(fadeout_ms)
        self.hold_ms = int(hold_ms)

        # ---- Fenêtre : non intrusive, au-dessus même du plein écran
        self.setAttribute(Qt.WA_TranslucentBackground, True)  # nécessite picom pour découpe/ombre
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.X11BypassWindowManagerHint  # au-dessus du plein écran
            | Qt.Tool                         # hors barre des tâches
            | Qt.NoDropShadowWindowHint
        )
        self.setCursor(Qt.BlankCursor)  # curseur invisible au survol

        # Taille totale = corps + queue
        self.resize(self.w, self.h + self.tail_h)
        self.move(int(x), int(y))

        # ---- Opacité via effet (fiable)
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.0)  # départ transparent
        self.setGraphicsEffect(self.opacity_effect)

        self._setup_animations()

    # Empêcher toute interaction
    def mousePressEvent(self, e):  pass
    def mouseReleaseEvent(self, e): pass
    def mouseMoveEvent(self, e):    pass
    def wheelEvent(self, e):        pass
    def enterEvent(self, e):        pass
    def leaveEvent(self, e):        pass

    def _setup_animations(self):
        # Fade-in (effet)
        self.fade_in = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.fade_in.setDuration(self.fadein_ms)
        self.fade_in.setStartValue(0.0)
        self.fade_in.setEndValue(1.0)
        self.fade_in.setEasingCurve(QEasingCurve.OutCubic)

        # Pause (pleinement visible)
        self.pause = QPauseAnimation(self.hold_ms, self)

        # Fade-out (effet)
        self.fade_out = QPropertyAnimation(self.opacity_effect, b"opacity", self)
        self.fade_out.setDuration(self.fadeout_ms)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.setEasingCurve(QEasingCurve.InCubic)

        # Chaîne d’animations
        self.seq = QSequentialAnimationGroup(self)
        self.seq.addAnimation(self.fade_in)
        self.seq.addAnimation(self.pause)
        self.seq.addAnimation(self.fade_out)
        self.seq.finished.connect(self.close)

    def showEvent(self, e):
        self.seq.start()
        return super().showEvent(e)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        body_rect = QRectF(0, 0, self.w, self.h)

        # Chemin : rectangle arrondi + queue triangulaire
        path = QPainterPath()
        path.addRoundedRect(body_rect, self.radius, self.radius)

        # Position horizontale de la queue (clamp pour rester dans la bulle)
        tri_center_x = max(self.radius + 6, min(self.w - (self.radius + 6), float(self.tailx)))

        tail = QPainterPath()
        tail.moveTo(tri_center_x - self.tail_w / 2.0, self.h)
        tail.lineTo(tri_center_x + self.tail_w / 2.0, self.h)
        tail.lineTo(tri_center_x, self.h + self.tail_h)
        tail.closeSubpath()
        path.addPath(tail)

        # Ombre douce (léger décalage)
        p.setPen(Qt.NoPen)
        p.setBrush(self.shadow)
        p.translate(0, 2)
        p.drawPath(path)
        p.translate(0, -2)

        # Remplissage + bord
        p.setBrush(self.bg)
        p.setPen(QPen(self.border, 1))
        p.drawPath(path)

        # Texte centré
        p.setPen(Qt.black)
        f = QFont("Arial", 11); f.setBold(True)
        p.setFont(f)
        text_rect = QRectF(12, 8, self.w - 24, self.h - 16)
        p.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, self.text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--x", type=int, required=True, help="Position écran X de la bulle")
    ap.add_argument("--y", type=int, required=True, help="Position écran Y de la bulle")
    ap.add_argument("--w", type=int, default=360, help="Largeur du corps (hors queue)")
    ap.add_argument("--h", type=int, default=58, help="Hauteur du corps (hors queue)")
    ap.add_argument("--ms", type=int, default=10000, help="Durée d’affichage PLEINEMENT visible (pause) en ms")
    ap.add_argument("--text", type=str, default="Mise à jour effectuée avec succès !", help="Texte de la bulle")
    ap.add_argument("--tailx", type=float, default=None, help="X interne (dans la bulle) de la pointe")
    ap.add_argument("--fadein", type=int, default=3000, help="Durée du fondu d’entrée (ms)")
    ap.add_argument("--fadeout", type=int, default=3000, help="Durée du fondu de sortie (ms)")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    bubble = SpeechBubble(
        x=args.x, y=args.y, w=args.w, h=args.h, text=args.text,
        hold_ms=args.ms, tailx=args.tailx,
        fadein_ms=args.fadein, fadeout_ms=args.fadeout
    )
    bubble.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()