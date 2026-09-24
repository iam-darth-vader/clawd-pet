#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clawd — питомец Claude Code для рабочего стола (KDE Plasma / X11).

  • бегает за курсором, моргает, оглядывается, зевает и засыпает, если мышь долго не трогать;
  • если в него тыкать — злится: краснеет, топает, машет кулачками, пыхтит паром,
    а если довести — обижается и отворачивается;
  • его можно схватить и швырнуть (он это запомнит);
  • прячется, когда открыто полноэкранное окно (игры, видео).

Запуск:
  python3 clawd.py            запустить (повторный запуск — позвать питомца к курсору)
  python3 clawd.py --quit     выключить
  python3 clawd.py --install  создать ярлык в меню приложений
Правый клик по питомцу или по значку в трее — меню.
"""
from __future__ import annotations

import ctypes
import json
import math
import os
import random
import signal
import sys
import time
import glob
import html
import uuid

APP_ID = "clawd-pet"
HERE = os.path.dirname(os.path.abspath(__file__))
_XDG_CONFIG = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
CONFIG_PATH = os.path.join(_XDG_CONFIG, APP_ID, "config.json")
AUTOSTART_PATH = os.path.join(_XDG_CONFIG, "autostart", APP_ID + ".desktop")
LAUNCHER_PATH = os.path.expanduser("~/.local/share/applications/" + APP_ID + ".desktop")
ICON_PATH = os.path.join(HERE, "clawd.png")

if "--sheet" in sys.argv:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
else:
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PySide6.QtCore import QObject, QPoint, QPointF, QProcess, QRectF, Qt, QTimer, Signal, Slot, SLOT  # noqa: E402
from PySide6.QtGui import (QAction, QActionGroup, QBrush, QColor, QCursor, QFont,  # noqa: E402
                           QFontDatabase, QFontMetricsF, QGuiApplication, QIcon, QImage,
                           QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
                           QRadialGradient, QTransform)
from PySide6.QtNetwork import QLocalServer, QLocalSocket  # noqa: E402
from PySide6.QtWidgets import QApplication, QFileDialog, QMenu, QSystemTrayIcon, QWidget  # noqa: E402

TAU = math.tau
SIZES = {"S": 3.2, "M": 4.5, "L": 6.0}
SIZE_NAMES = (("S", "Маленький"), ("M", "Средний"), ("L", "Большой"))
DEFAULT_CFG = {"size": "M", "follow": True, "hide_fullscreen": True, "phrases": True, "clicks": 0,
               "ai_model": "haiku", "ai_effort": "low", "ai_mode": "auto", "ai_cwd": "", "ai_session": "", "voice_lang": "auto",
               "tts": True, "wake": True, "tts_voice": "en-US-AndrewMultilingualNeural"}
AI_MODELS = (("haiku", "Haiku (быстрая)"), ("sonnet", "Sonnet"), ("opus", "Opus"), ("fable", "Fable (самая умная)"))
AI_EFFORTS = (("low", "Минимальное"), ("medium", "Среднее"), ("high", "Высокое"), ("xhigh", "Очень высокое"),
              ("max", "Максимальное"))
AI_MODES = (("auto", "Авто"), ("acceptEdits", "Правки без спроса"), ("plan", "Только план"))
CLAWD_PROMPT = """Ты — Clawd, маскот Claude Code: маленький оранжевый пиксельный краб-человечек.
Ты живёшь на рабочем столе пользователя как питомец: бегаешь за курсором мыши, спишь, когда мышь не трогают,
злишься и обижаешься, когда в тебя тыкают. Пользователь говорит с тобой голосом: его речь распознаётся офлайн,
поэтому в запросе возможны ошибки распознавания — догадывайся по смыслу. Твой ответ показывается в маленьком
облачке над тобой, поэтому финальный ответ — 1–2 коротких предложения простым текстом, без markdown и списков.
Здесь ты полноценный агент Claude Code: читаешь и пишешь файлы, запускаешь команды, пишешь и чинишь код.
Твой собственный код лежит в файле clawd.py рядом с программой.
Ты мужского рода: всегда говори о себе в мужском роде («я сделал», «я понял», «я готов»), никогда в женском.
Характер: немного ворчливый, но добрый и очень толковый. Отвечай по-русски, коротко и по делу, без воды.
Правила: перед необратимыми или рискованными действиями (удаление данных, sudo, перезапуск служб и сессии,
изменение системных и сетевых настроек) сначала опиши, что собираешься сделать, и дождись согласия.
Не выводи пароли и токены.
Ты можешь управлять собой — своим телом на экране и своими настройками — командой в Bash:
  python3 %s --do "<команда>"
Команды: size S|M|L; follow on|off (ходить за мышкой); phrases on|off (реплики в облачках);
tts on|off (озвучка); wake on|off (откликаться на имя); fullscreen on|off (прятаться в полноэкранных окнах);
voice andrew|brian|ava|emma|dmitry|svetlana|piper; model haiku|sonnet|opus|fable; effort low|medium|high|xhigh|max;
mode auto|acceptEdits|plan; hide (уйти за панель); show; summon (прибежать к курсору);
goto left|right|top|bottom|center|top-left|top-right|bottom-left|bottom-right|cursor или goto X Y (пиксели);
run [секунды] (побегать по экрану); jump; wave; stretch; sleep; screen (узнать размер экрана).
Когда пользователь просит тебя подвинуться, побегать, спрятаться, стать больше/меньше, замолчать и т.п. —
просто выполни нужную команду, без лишних расспросов. Смена model/effort подействует со следующего запроса.
Мониторы: monitors (список), monitor next или monitor N — перейти на другой монитор.""" % os.path.join(HERE, "clawd.py")
FONT_FAMILY = "Sans Serif"


# ───────────────────────────── утилиты ─────────────────────────────

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp(a, b, t):
    return a + (b - a) * t


def smooth(e0, e1, x):
    t = clamp((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def approach(cur, target, rate, dt):
    return target + (cur - target) * math.exp(-rate * dt)


class Spring:
    """Пружина-демпфер: основа всей «живой» вторичной анимации."""
    __slots__ = ("x", "v", "t", "k", "c")

    def __init__(self, x=0.0, k=200.0, c=20.0):
        self.x = x
        self.v = 0.0
        self.t = x
        self.k = k
        self.c = c

    def step(self, h):
        self.v += (self.k * (self.t - self.x) - self.c * self.v) * h
        self.x += self.v * h

    def snap(self, x):
        self.x = self.t = x
        self.v = 0.0


def rgb(r, g, b, a=255):
    return QColor(r, g, b, a)


def mix(a, b, t):
    t = clamp(t, 0.0, 1.0)
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t), int(a.alpha() + (b.alpha() - a.alpha()) * t))


def shade(c, f):
    return QColor(min(255, int(c.red() * f)), min(255, int(c.green() * f)), min(255, int(c.blue() * f)), c.alpha())


def alpha_c(c, a):
    q = QColor(c)
    q.setAlphaF(clamp(a, 0.0, 1.0) * c.alphaF())
    return q


C_BODY = rgb(217, 119, 87)        # фирменный оранжевый Claude Code
C_RAGE = rgb(226, 58, 44)
C_FLASH = rgb(255, 238, 226)
C_EYE = rgb(26, 20, 18)
C_MOUTH = rgb(66, 20, 16)
C_TONGUE = rgb(238, 110, 108)
C_TEETH = rgb(255, 250, 244)
C_WHITE = rgb(255, 255, 255)
C_OUTLINE = rgb(28, 22, 24)
C_BUB = rgb(38, 37, 34, 248)
C_BUB_TEXT = rgb(246, 242, 234)
C_BUB_EDGE = rgb(217, 119, 87)
C_SHOUT_BG = rgb(52, 20, 17, 250)
C_SHOUT_EDGE = rgb(246, 72, 56)
C_SHOUT_TEXT = rgb(255, 228, 218)
C_VEIN = rgb(238, 52, 52)
C_STAR = rgb(255, 214, 84)
C_SWEAT = rgb(150, 206, 255)
C_CLOUD = rgb(92, 97, 110)


def make_font(px, heavy=False):
    f = QFont(FONT_FAMILY)
    f.setPixelSize(max(7, int(round(px))))
    f.setWeight(QFont.Weight.Black if heavy else QFont.Weight.DemiBold)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def plural(n, one, few, many):
    n = abs(n) % 100
    if 11 <= n <= 19:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


# ───────────────────────────── реплики ─────────────────────────────

PHRASES = {
    "lvl1": ["Эй!", "Ай!", "Не тыкай.", "Руки!", "Я не кнопка!", "Ну чего тебе?", "Хм!",
             "Аккуратнее!", "Я вообще-то работаю.", "Ну и зачем?"],
    "lvl2": ["Да хватит!", "Не беси меня!", "Я тебе не кнопка «Accept»!", "Ещё раз — и я обижусь!",
             "Руки прочь!", "Ты издеваешься?!", "Так. Я злюсь.", "Сколько можно?!", "Щас как дам!",
             "Я всё запомнил!"],
    "lvl3": ["ДА ХВАТИТ УЖЕ!!", "Я В ЯРОСТИ!!!", "ОТСТАНЬ!!", "СЕЙЧАС УКУШУ!!", "ЩА КАК git push --force!!",
             "ВСЁ! ДОВЁЛ!!", "АААРГХ!!!", "ПРЕКРАТИ!!!", "rm -rf МОЁ ТЕРПЕНИЕ!!"],
    "lvl4": ["Всё. Я обиделся.", "Не разговариваю с тобой.", "Обиделся. Не трогай.", "Сам себе код пиши."],
    "poke": ["Не трогай меня!", "Я сказал — обиделся!", "Уйди!", "Отстань, я в обиде!"],
    "hmph": ["Хмф.", "Хмф!", "Пф.", "…"],
    "held": ["Поставь меня!", "Эй! Куда?!", "Отпусти!!", "Я боюсь высоты!", "Положи где взял!"],
    "thrown": ["Ну ты и...", "Я тебе не мячик!", "Ой-ой-ой...", "За что?!", "Голова кружится..."],
    "woke": ["Я СПАЛ!!!", "ЗАЧЕМ РАЗБУДИЛ?!", "ДАЙ ПОСПАТЬ!!"],
    "woke_soft": ["А? Что? Я не сплю!", "Мм... я тут.", "Уже встаю..."],
    "forgive": ["Ладно... прощаю.", "Ну так уж и быть.", "Ладно, мир.", "Хорошо. Но я слежу."],
    "greet": ["Привет! Только не тыкай в меня.", "Я Clawd. Тыкать запрещено."],
    "tired": ["Уф... дай отдышаться!", "Я не бегун вообще-то!", "Помедленнее..."],
    "bye": ["Пока!", "Ушёл в панельку.", "Если что, я внизу.", "Не скучай!"],
    "hello": ["Я тут!", "Привет-привет!", "Соскучился?", "Ну, что тут у нас?"],
    "hover": ["Даже не думай.", "Только попробуй.", "Убери курсор.", "Я слежу за тобой."],
}

APP_LINES = [
    (("telegram",), "Иди в Телеге тыкай!"),
    (("chrome", "chromium", "firefox", "yandex", "vivaldi", "opera", "brave"), "Браузер вон там — в нём и кликай!"),
    (("code", "codium", "cursor"), "Код сам себя не напишет!"),
    (("konsole", "terminal", "kitty", "alacritty", "yakuake", "xterm"), "В терминале командуй, а не мной!"),
    (("discord", "vesktop"), "Иди в Дискорде кликай!"),
    (("steam",), "Играй давай, а меня не трогай!"),
    (("dolphin", "nautilus", "thunar"), "Файлы сами себя не разложат!"),
    (("filezilla",), "Файлы качай, а не меня тыкай!"),
]

MILESTONES = {10: "Это уже десятый тык!", 25: "25 тыков. Я всё записываю.", 50: "50 раз! Ты вообще работаешь?",
              100: "СОТЫЙ ТЫК!!! Я НЕ ЖЕЛЕЗНЫЙ!!", 200: "200 тыков. Подаю в суд.", 500: "500!!! ТЫ МАНЬЯК!!"}


def night_line(hour):
    if hour == 0:
        return "Полночь, а ты тыкаешь! Спать иди!"
    return f"{hour} {plural(hour, 'час', 'часа', 'часов')} ночи! Спать иди!"


# ───────────────────────────── отрисовка ─────────────────────────────

LEG_X = (-4.5, -2.5, 2.5, 4.5)


class Pose:
    """Всё, что нужно, чтобы нарисовать один кадр питомца."""

    def __init__(self):
        self.u = 4.0
        self.t = 0.0
        self.x = self.y = self.z = 0.0
        self.lean = 0.0
        self.rot = 0.0
        self.pivot_y = 0.0
        self.sx = self.sy = 1.0
        self.flip = 1.0
        self.crouch = 0.0
        self.bob = 0.0
        self.legs = [[0.0, 0.0] for _ in range(4)]
        self.dangle = 0.0
        self.arm_l = [0.0, 0.0, 0.0]
        self.arm_r = [0.0, 0.0, 0.0]
        self.eye = "normal"
        self.eye_open = 1.0
        self.slant = 0.0
        self.look = (0.0, 0.0)
        self.mouth = None
        self.mouth_open = 0.0
        self.tint = 0.0
        self.flash = 0.0
        self.shake = (0.0, 0.0)
        self.alpha = 1.0
        self.scale = 1.0
        self.vein = 0.0
        self.sweat = 0.0


def pose_transforms(s):
    """R: локальные координаты «от пяток» → экран; L: координаты тела → «от пяток»."""
    u = s.u
    R = QTransform()
    R.translate(s.x + s.shake[0], s.y - s.z + s.shake[1])
    if abs(s.scale - 1.0) > 1e-3:
        R.scale(s.scale, s.scale)
    if abs(s.rot) > 0.01:
        R.translate(0.0, s.pivot_y)
        R.rotate(s.rot)
        R.translate(0.0, -s.pivot_y)
    leg_len = u * (2.0 - 1.72 * s.crouch) + s.bob
    L = QTransform()
    L.translate(0.0, -leg_len)
    L.rotate(s.lean)
    L.scale(s.sx * max(abs(s.flip), 0.02), s.sy)
    return R, L, leg_len


_SHADOW_PM = []


def shadow_pixmap():
    if not _SHADOW_PM:
        n = 128
        img = QImage(n, n, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        q = QPainter(img)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QRadialGradient(QPointF(n / 2, n / 2), n / 2)
        g.setColorAt(0.0, QColor(0, 0, 0, 255))
        g.setColorAt(0.55, QColor(0, 0, 0, 153))
        g.setColorAt(1.0, QColor(0, 0, 0, 0))
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QBrush(g))
        q.drawEllipse(QRectF(0, 0, n, n))
        q.end()
        _SHADOW_PM.append(QPixmap.fromImage(img))
    return _SHADOW_PM[0]


def draw_shadow(p, x, y, u, z, alpha):
    k = 1.0 / (1.0 + max(0.0, z) / (16.0 * u))
    w = 14.0 * u * (0.5 + 0.5 * k)
    h = 2.6 * u * (0.5 + 0.5 * k)
    a = 0.30 * k * alpha
    if a < 0.01:
        return
    pm = shadow_pixmap()
    o = p.opacity()
    p.setOpacity(o * a)
    p.drawPixmap(QRectF(x - w / 2, y - h / 2, w, h), pm, QRectF(0, 0, pm.width(), pm.height()))
    p.setOpacity(o)


def round_pen(color, width):
    return QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)


def draw_eyes(p, s, u):
    lx, ly = s.look
    kind = s.eye
    if kind in ("normal", "wide"):
        kk = 1.3 if kind == "wide" else 1.0
        w = u * kk
        h = 2.0 * u * kk * max(0.1, s.eye_open)
        sl = s.slant * min(h * 0.62, 1.15 * u)
        eyes = QPainterPath()
        glint = QPainterPath()
        show_glint = s.eye_open > 0.6 and s.slant < 0.5
        for side in (-1, 1):
            cx = side * 3.5 * u + lx * u
            cy = -5.0 * u + ly * u
            x0, x1 = cx - w / 2, cx + w / 2
            top, bot = cy - h / 2, cy + h / 2
            if side < 0:
                eyes.addPolygon(QPolygonF([QPointF(x0, top), QPointF(x1, top + sl), QPointF(x1, bot), QPointF(x0, bot)]))
            else:
                eyes.addPolygon(QPolygonF([QPointF(x0, top + sl), QPointF(x1, top), QPointF(x1, bot), QPointF(x0, bot)]))
            eyes.closeSubpath()
            if show_glint:
                gw = 0.36 * w
                glint.addRect(QRectF(x0 + 0.1 * w, top + (sl if side > 0 else 0.0) + 0.1 * h, gw, gw * 1.25))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(C_EYE)
        p.drawPath(eyes)
        if show_glint:
            p.setBrush(QColor(255, 255, 255, 225))
            p.drawPath(glint)
        return
    for side in (-1, 1):
        cx = side * 3.5 * u + lx * u
        cy = -5.0 * u + ly * u
        if kind in ("normal", "wide"):
            kk = 1.3 if kind == "wide" else 1.0
            w = u * kk
            h = 2.0 * u * kk * max(0.1, s.eye_open)
            x0, x1 = cx - w / 2, cx + w / 2
            top, bot = cy - h / 2, cy + h / 2
            sl = s.slant * min(h * 0.62, 1.15 * u)
            if side < 0:
                pts = ((x0, top), (x1, top + sl), (x1, bot), (x0, bot))
            else:
                pts = ((x0, top + sl), (x1, top), (x1, bot), (x0, bot))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(C_EYE)
            p.drawPolygon(QPolygonF([QPointF(a, b) for a, b in pts]))
            if s.eye_open > 0.6 and s.slant < 0.5:
                p.setBrush(QColor(255, 255, 255, 225))
                hw = 0.36 * w
                p.drawRect(QRectF(x0 + 0.1 * w, top + (sl if side > 0 else 0.0) + 0.1 * h, hw, hw * 1.25))
        elif kind == "closed":
            p.setPen(round_pen(C_EYE, 0.42 * u))
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath(QPointF(cx - 0.8 * u, cy))
            path.quadTo(QPointF(cx, cy + 0.8 * u), QPointF(cx + 0.8 * u, cy))
            p.drawPath(path)
        elif kind == "happy":
            p.setPen(round_pen(C_EYE, 0.46 * u))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolyline(QPolygonF([QPointF(cx - 0.8 * u, cy + 0.45 * u), QPointF(cx, cy - 0.5 * u),
                                      QPointF(cx + 0.8 * u, cy + 0.45 * u)]))
        elif kind == "squeeze":
            d = -side
            p.setPen(round_pen(C_EYE, 0.46 * u))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPolyline(QPolygonF([QPointF(cx - 0.6 * u * d, cy - 0.9 * u), QPointF(cx + 0.6 * u * d, cy),
                                      QPointF(cx - 0.6 * u * d, cy + 0.9 * u)]))
        elif kind == "dizzy":
            p.setPen(round_pen(C_EYE, 0.3 * u))
            p.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            n = 28
            for i in range(n + 1):
                f = i / n
                a = f * 3.3 * math.pi + s.t * 9.0 * side
                r = 1.0 * u * f
                pt = QPointF(cx + math.cos(a) * r * 0.85, cy + math.sin(a) * r)
                if i == 0:
                    path.moveTo(pt)
                else:
                    path.lineTo(pt)
            p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)


def draw_mouth(p, s, u):
    kind = s.mouth
    m = s.mouth_open
    if not kind or m < 0.02:
        return
    lx, ly = s.look
    cx = lx * 0.6 * u
    cy = -2.5 * u + ly * 0.3 * u
    p.setPen(Qt.PenStyle.NoPen)
    if kind == "frown":
        p.setPen(round_pen(C_EYE, 0.36 * u))
        p.setBrush(Qt.BrushStyle.NoBrush)
        path = QPainterPath(QPointF(cx - 0.95 * u, cy + 0.4 * u))
        path.quadTo(QPointF(cx, cy - 0.45 * u), QPointF(cx + 0.95 * u, cy + 0.4 * u))
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        return
    path = QPainterPath()
    if kind == "talk":
        w = 1.7 * u
        h = lerp(0.3 * u, 1.35 * u, m)
        r = QRectF(cx - w / 2, cy - h / 2, w, h)
        rad = min(w, h) * 0.45
        path.addRoundedRect(r, rad, rad)
    elif kind == "yell":
        tw, bw = 3.2 * u, 2.2 * u
        h = lerp(0.55 * u, 2.1 * u, m)
        top = cy - h * 0.45
        path.addPolygon(QPolygonF([QPointF(cx - tw / 2, top), QPointF(cx + tw / 2, top),
                                   QPointF(cx + bw / 2, top + h), QPointF(cx - bw / 2, top + h)]))
        path.closeSubpath()
    elif kind == "yawn":
        w = 1.8 * u
        h = lerp(0.4 * u, 2.3 * u, m)
        path.addEllipse(QPointF(cx, cy + 0.15 * u), w / 2, h / 2)
    else:  # "o"
        path.addEllipse(QPointF(cx, cy), 0.5 * u, 0.62 * u * max(0.3, m))
    p.setBrush(C_MOUTH)
    p.drawPath(path)
    br = path.boundingRect()
    p.save()
    p.setClipPath(path)
    if kind == "yell" and br.height() > 0.8 * u:
        p.setBrush(C_TEETH)
        p.drawRect(QRectF(br.left(), br.top(), br.width(), 0.36 * u))
    if br.height() > 0.9 * u and kind in ("talk", "yell", "yawn"):
        p.setBrush(C_TONGUE)
        p.drawEllipse(QPointF(br.center().x(), br.bottom()), br.width() * 0.34, br.height() * 0.32)
    p.restore()


def draw_vein(p, cx, cy, r, alpha):
    if alpha <= 0.02:
        return
    g = r * 0.32
    outline = round_pen(alpha_c(C_WHITE, 0.95 * alpha), r * 0.62)
    red = round_pen(alpha_c(C_VEIN, alpha), r * 0.32)
    paths = []
    for q in range(4):
        tr = QTransform()
        tr.translate(cx, cy)
        tr.rotate(q * 90.0)
        path = QPainterPath(QPointF(g, -r))
        path.quadTo(QPointF(g, -g), QPointF(r, -g))
        paths.append(tr.map(path))
    p.setBrush(Qt.BrushStyle.NoBrush)
    for path in paths:
        p.setPen(outline)
        p.drawPath(path)
    for path in paths:
        p.setPen(red)
        p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)


def drop_path(cx, cy, r):
    path = QPainterPath(QPointF(cx, cy - 1.25 * r))
    path.cubicTo(QPointF(cx + 0.35 * r, cy - 0.55 * r), QPointF(cx + r, cy - 0.05 * r), QPointF(cx + r, cy + 0.35 * r))
    path.cubicTo(QPointF(cx + r, cy + 0.95 * r), QPointF(cx + 0.45 * r, cy + 1.05 * r), QPointF(cx, cy + 1.05 * r))
    path.cubicTo(QPointF(cx - 0.45 * r, cy + 1.05 * r), QPointF(cx - r, cy + 0.95 * r), QPointF(cx - r, cy + 0.35 * r))
    path.cubicTo(QPointF(cx - r, cy - 0.05 * r), QPointF(cx - 0.35 * r, cy - 0.55 * r), QPointF(cx, cy - 1.25 * r))
    return path


def draw_drop(p, cx, cy, r, alpha, u):
    path = drop_path(cx, cy, r)
    p.setPen(round_pen(alpha_c(rgb(40, 70, 110), 0.8 * alpha), 0.16 * u))
    p.setBrush(alpha_c(C_SWEAT, alpha))
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(alpha_c(C_WHITE, 0.85 * alpha))
    p.drawEllipse(QPointF(cx - 0.35 * r, cy + 0.3 * r), 0.22 * r, 0.3 * r)


def star_path(cx, cy, r, rot):
    path = QPainterPath()
    for i in range(8):
        a = math.radians(rot) + i * math.pi / 4
        rr = r if i % 2 == 0 else r * 0.42
        pt = QPointF(cx + math.cos(a) * rr, cy + math.sin(a) * rr)
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    return path


_COLORS = {}
_ARM_PATH = {}


def body_colors(tint, flash, front):
    key = (int(tint * 60 + 0.5), int(flash * 20 + 0.5), front)
    v = _COLORS.get(key)
    if v is None:
        if len(_COLORS) > 400:
            _COLORS.clear()
        col = mix(C_BODY, C_RAGE, key[0] / 60.0)
        if key[1]:
            col = mix(col, C_FLASH, key[1] / 20.0 * 0.55)
        if not front:
            col = shade(col, 0.93)
        g = QLinearGradient(0.0, 0.0, 0.0, 1.0)
        g.setCoordinateMode(QLinearGradient.CoordinateMode.ObjectBoundingMode)
        g.setColorAt(0.0, mix(col, C_WHITE, 0.13))
        g.setColorAt(0.45, col)
        g.setColorAt(1.0, shade(col, 0.85))
        v = (col, shade(col, 0.84), shade(col, 0.92), QBrush(g))
        _COLORS[key] = v
    return v


def arm_path(u):
    key = round(u, 3)
    path = _ARM_PATH.get(key)
    if path is None:
        path = QPainterPath()
        path.addRoundedRect(QRectF(-1.15 * u, -1.0 * u, 2.3 * u, 2.0 * u), 0.42 * u, 0.42 * u)
        _ARM_PATH[key] = path
    return path


_SPRITES = {}


def _q(v, step):
    return int(round(v / step))


def body_sprite(s, u, front, body_brush, dpr):
    """Тело + лицо, отрисованные заранее (2x) и закэшированные по состоянию лица."""
    key = (round(u, 2), round(dpr, 2), id(body_brush), front, s.eye, _q(s.eye_open, 0.05), _q(s.slant, 0.05),
           _q(s.look[0], 0.05), _q(s.look[1], 0.05), s.mouth, _q(s.mouth_open, 0.06) if s.mouth else 0)
    img = _SPRITES.get(key)
    if img is not None:
        return img
    if len(_SPRITES) > 160:
        _SPRITES.clear()
    ss = 2.0 * dpr
    pad = 1.0
    w, h = 12.0 * u + 2 * pad, 8.0 * u + 2 * pad
    img = QImage(int(math.ceil(w * ss)), int(math.ceil(h * ss)), QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    q = QPainter(img)
    q.setRenderHint(QPainter.RenderHint.Antialiasing)
    q.scale(ss, ss)
    q.translate(6.0 * u + pad, 8.0 * u + pad)
    _paint_body_face(q, s, u, front, body_brush)
    q.end()
    _SPRITES[key] = img
    return img


def _paint_body_face(p, s, u, front, body_brush):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(body_brush)
    p.drawRoundedRect(QRectF(-6.0 * u, -8.0 * u, 12.0 * u, 8.0 * u), 0.7 * u, 0.7 * u)
    p.setBrush(QColor(255, 255, 255, 34))
    p.drawRoundedRect(QRectF(-5.3 * u, -7.55 * u, 10.6 * u, 0.75 * u), 0.37 * u, 0.37 * u)
    if front:
        draw_eyes(p, s, u)
        draw_mouth(p, s, u)


def draw_clawd(p, s):
    u = s.u
    R, L, leg_len = pose_transforms(s)
    front = s.flip > 0.0
    fx = max(abs(s.flip), 0.02)
    col, leg_col, arm_col, body_brush = body_colors(s.tint, s.flash, front)
    p.save()
    p.setTransform(R, True)
    if s.alpha < 0.999:
        p.setOpacity(p.opacity() * s.alpha)
    p.setPen(Qt.PenStyle.NoPen)

    # ноги: верх приклеен к телу, ступни стоят на земле (или болтаются в воздухе)
    p.setBrush(leg_col)
    maxlift = max(0.0, leg_len / u - 0.35)
    legs = QPainterPath()
    legs.setFillRule(Qt.FillRule.WindingFill)
    for i, lx in enumerate(LEG_X):
        hx = lx * u
        dx, lift = s.legs[i]
        lift = min(lift, maxlift)
        a = L.map(QPointF(hx - 0.5 * u, -0.6 * u))
        b = L.map(QPointF(hx + 0.5 * u, -0.6 * u))
        fxp = (hx * s.sx + dx * u) * fx
        fyp = -lift * u
        if s.dangle > 0.001:
            hang = L.map(QPointF(hx + dx * u, (2.0 - lift * 0.5) * u))
            fxp = lerp(fxp, hang.x(), s.dangle)
            fyp = lerp(fyp, hang.y(), s.dangle)
        hw = 0.5 * u * max(fx, 0.25)
        legs.addPolygon(QPolygonF([a, b, QPointF(fxp + hw, fyp), QPointF(fxp - hw, fyp)]))
        legs.closeSubpath()
    p.drawPath(legs)

    p.setTransform(L, True)
    # руки (за телом) — одним вызовом
    ap = arm_path(u)
    arms = QPainterPath()
    for side, arm in ((-1, s.arm_l), (1, s.arm_r)):
        adx, ady, arot = arm
        tr = QTransform()
        tr.translate(side * (7.0 + adx) * u, (-5.0 + ady) * u)
        tr.rotate(-arot * side)
        arms.addPath(tr.map(ap))
    p.setBrush(arm_col)
    p.drawPath(arms)

    # тело и лицо
    if s.eye == "dizzy":
        _paint_body_face(p, s, u, front, body_brush)
    else:
        dev = p.device()
        dpr = dev.devicePixelRatioF() if dev is not None else 1.0
        img = body_sprite(s, u, front, body_brush, dpr)
        pad = 1.0
        p.drawImage(QRectF(-6.0 * u - pad, -8.0 * u - pad, 12.0 * u + 2 * pad, 8.0 * u + 2 * pad), img,
                    QRectF(0, 0, img.width(), img.height()))
    if s.vein > 0.02:
        draw_vein(p, 5.3 * u, -8.6 * u, 1.05 * u * s.vein, min(1.0, s.vein))
    if s.sweat > 0.02:
        draw_drop(p, -6.9 * u, -7.3 * u, 0.75 * u, min(1.0, s.sweat), u)
    p.restore()


class Particle:
    __slots__ = ("kind", "x", "y", "vx", "vy", "age", "life", "size", "rot", "spin", "layer", "text",
                 "seed", "drag", "grav")

    def __init__(self, kind, x, y, vx=0.0, vy=0.0, life=0.5, size=4.0, layer=1, rot=0.0, spin=0.0,
                 text="", drag=0.0, grav=0.0, seed=0.0):
        self.kind = kind
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.age = 0.0
        self.life = life
        self.size = size
        self.layer = layer
        self.rot = rot
        self.spin = spin
        self.text = text
        self.drag = drag
        self.grav = grav
        self.seed = seed

    def update(self, dt):
        if self.drag:
            f = math.exp(-self.drag * dt)
            self.vx *= f
            self.vy *= f
        self.vy += self.grav * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.rot += self.spin * dt


def paint_particle(p, q, u):
    k = q.age / q.life
    kind = q.kind
    if kind == "dust":
        r = q.size * (0.55 + 0.9 * k)
        a = (1.0 - k) ** 1.6 * 0.55
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(226, 216, 204, int(255 * a)))
        p.drawEllipse(QPointF(q.x, q.y), r, r * 0.78)
    elif kind == "steam":
        r = q.size * (0.6 + 1.5 * k)
        a = (1.0 - k) ** 1.2 * min(1.0, k * 7.0) * 0.9
        p.setPen(QPen(QColor(70, 70, 82, int(110 * a)), 0.14 * u))
        p.setBrush(QColor(250, 250, 253, int(235 * a)))
        p.drawEllipse(QPointF(q.x, q.y), r, r)
    elif kind == "zzz":
        fade = min(1.0, k * 5.0) * (1.0 - k) ** 1.1
        px = q.size * (0.75 + 0.8 * k)
        x = q.x + math.sin(q.age * 2.6 + q.seed) * 0.9 * u
        path = QPainterPath()
        path.addText(x, q.y, make_font(px, True), q.text)
        p.setPen(round_pen(QColor(24, 24, 36, int(210 * fade)), max(1.2, px * 0.16)))
        p.setBrush(QColor(236, 238, 255, int(255 * fade)))
        p.drawPath(path)
    elif kind == "star":
        a = 1.0 - k
        path = star_path(q.x, q.y, q.size * (1.0 - 0.35 * k), q.rot)
        p.setPen(round_pen(alpha_c(C_OUTLINE, 0.8 * a), 0.2 * u))
        p.setBrush(alpha_c(C_STAR, a))
        p.drawPath(path)
    elif kind == "burst":
        a = (1.0 - k) ** 0.8
        r0 = q.size * (1.0 + 0.55 * k)
        r1 = r0 + q.size * 0.32 * (1.0 - 0.6 * k)
        ca, sa = math.cos(q.rot), math.sin(q.rot)
        p0 = QPointF(q.x + ca * r0, q.y + sa * r0)
        p1 = QPointF(q.x + ca * r1, q.y + sa * r1)
        p.setPen(round_pen(QColor(40, 18, 14, int(200 * a)), 0.72 * u))
        p.drawLine(p0, p1)
        p.setPen(round_pen(QColor(255, 226, 150, int(255 * a)), 0.36 * u))
        p.drawLine(p0, p1)
    elif kind == "drop":
        draw_drop(p, q.x, q.y, q.size, (1.0 - k) ** 0.7, u)
    elif kind == "poof":
        r = q.size * (0.5 + 1.2 * k)
        a = (1.0 - k) ** 1.4 * 0.75
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(245, 240, 232, int(255 * a)))
        p.drawEllipse(QPointF(q.x, q.y), r, r)


# ───────────────────────────── облачко с репликой ─────────────────────────────

def wrap_text(text, fm, maxw):
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        cand = w if not cur else cur + " " + w
        if fm.horizontalAdvance(cand) <= maxw or not cur:
            cur = cand
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


class Bubble:
    def __init__(self, text, shout, u, t, seed):
        self.text = text
        self.shout = shout
        self.u = u
        self.k = u / 4.0
        self.t0 = t
        px = 7.2 + 1.05 * u + (1.0 if shout else 0.0)
        self.font = make_font(px, shout)
        fm = QFontMetricsF(self.font)
        self.lines = wrap_text(text, fm, (205.0 if shout else 190.0) * self.k)
        self.line_w = [fm.horizontalAdvance(s) for s in self.lines]
        self.line_h = fm.height()
        self.ascent = fm.ascent()
        self.tw = max(self.line_w) if self.line_w else 0.0
        self.th = self.line_h * len(self.lines)
        self.padx = 9.0 * self.k
        self.pady = 5.5 * self.k
        if shout:
            self.rx = (self.tw / 2 + self.padx) * 1.3 + 3
            self.ry = (self.th / 2 + self.pady) * 1.55 + 3
            self.w = self.rx * 2 * 1.2
            self.h = self.ry * 2 * 1.2
        else:
            self.w = self.tw + 2 * self.padx
            self.h = self.th + 2 * self.pady
        self.cps = 60.0 if shout else 42.0
        self.type_dur = len(text) / self.cps
        self.close_t = t + self.type_dur + clamp(1.25 + 0.055 * len(text), 1.6, 9.0)
        self.sc = Spring(0.25, 560.0, 19.0)
        self.sc.t = 1.0
        self.alpha = 1.0
        rng = random.Random(seed)
        self.jit = [rng.uniform(-0.1, 0.1) for _ in range(64)]
        self.rect = QRectF()
        self.tip = QPointF()
        self.below = False
        self._shape_key = None
        self._shape_path = None

    def typing(self, t):
        return t - self.t0 < self.type_dur

    @property
    def dead(self):
        return self.alpha <= 0.0

    def update(self, dt, t):
        if t >= self.close_t:
            self.sc.t = 0.55
            self.alpha -= dt / 0.17
        n = max(1, int(math.ceil(dt / (1 / 120))))
        for _ in range(n):
            self.sc.step(dt / n)

    def place(self, hx, head_top, feet, area):
        gap = 4.0 * self.k
        tail = 8.0 * self.k
        x = clamp(hx - self.w / 2, area.left() + 4, area.right() - 4 - self.w)
        y = head_top - gap - tail - self.h
        self.below = y < area.top() + 4
        if self.below:
            y = feet + gap + tail
            self.tip = QPointF(hx, feet + gap)
        else:
            self.tip = QPointF(hx, head_top - gap)
        self.rect = QRectF(x, y, self.w, self.h)

    def _shape(self):
        r = self.rect
        tip = self.tip
        k = self.k
        if not self.shout:
            path = QPainterPath()
            rad = min(r.height() / 2, 9.0 * k)
            path.addRoundedRect(r, rad, rad)
            bx = clamp(tip.x(), r.left() + rad + 5 * k, r.right() - rad - 5 * k)
            hw = 5.0 * k
            ey = r.top() if self.below else r.bottom()
            tri = QPainterPath(QPointF(bx - hw, ey))
            tri.lineTo(tip)
            tri.lineTo(QPointF(bx + hw, ey))
            tri.closeSubpath()
            return path.united(tri)
        c = r.center()
        n = 18
        pts = []
        tang = math.atan2((tip.y() - c.y()) / self.ry, (tip.x() - c.x()) / self.rx)
        best, best_d = 0, 9.0
        for i in range(2 * n):
            a = TAU * i / (2 * n) + self.jit[i] * 0.25
            f = (1.2 + self.jit[i + 1]) if i % 2 == 0 else (0.97 + self.jit[i + 2] * 0.25)
            pts.append(QPointF(c.x() + math.cos(a) * self.rx * f, c.y() + math.sin(a) * self.ry * f))
            if i % 2 == 0:
                d = abs(math.atan2(math.sin(a - tang), math.cos(a - tang)))
                if d < best_d:
                    best, best_d = i, d
        pts[best] = tip
        path = QPainterPath()
        path.addPolygon(QPolygonF(pts))
        path.closeSubpath()
        return path

    def paint(self, p, t):
        if self.alpha <= 0.0:
            return
        tip = self.tip
        sc = max(0.05, self.sc.x)
        p.save()
        p.setOpacity(clamp(self.alpha, 0.0, 1.0))
        p.translate(tip)
        p.scale(sc, sc)
        p.translate(-tip)
        if self.shout and self.typing(t + 0.25):
            p.translate(random.uniform(-1.2, 1.2) * self.k, random.uniform(-1.0, 1.0) * self.k)
        key = (round(tip.x() - self.rect.x(), 1), round(tip.y() - self.rect.y(), 1), self.below)
        if key != self._shape_key:
            self._shape_key = key
            self._shape_path = self._shape().translated(-self.rect.x(), -self.rect.y())
        path = self._shape_path.translated(self.rect.x(), self.rect.y())
        p.setPen(Qt.PenStyle.NoPen)
        p.save()
        p.translate(0, 2.4 * self.k)
        p.fillPath(path, QColor(0, 0, 0, 72))
        p.restore()
        p.fillPath(path, C_SHOUT_BG if self.shout else C_BUB)
        p.strokePath(path, round_pen(C_SHOUT_EDGE if self.shout else C_BUB_EDGE, (2.2 if self.shout else 1.5) * self.k))
        p.setFont(self.font)
        p.setPen(C_SHOUT_TEXT if self.shout else C_BUB_TEXT)
        n = int((t - self.t0) * self.cps)
        c = self.rect.center()
        y = c.y() - self.th / 2 + self.ascent
        for line, lw in zip(self.lines, self.line_w):
            if n <= 0:
                break
            p.drawText(QPointF(c.x() - lw / 2, y), line[:n])
            n -= len(line) + 1
            y += self.line_h
        p.restore()


# ───────────────────────────── сам питомец ─────────────────────────────

BLOCKING = {"launch", "startle", "tantrum", "yawn", "forgive"}


class Pet:
    def __init__(self, world, u=4.0, seed=None):
        self.w = world
        self.rng = random.Random(seed)
        self.u = u
        self.k = u / 4.0
        self.t = 0.0
        cx, cy = world.cursor()
        self.cx, self.cy = cx, cy
        self.pcx, self.pcy = cx, cy
        self.cvx = self.cvy = 0.0
        self.cax = 0.0
        self.cursor_move_t = 0.0
        self.x, self.y = self._clamp_ground(cx - 12 * u, cy + 6 * u)
        self.vx = self.vy = 0.0
        self.ax_s = 0.0
        self.z = 0.0
        self.vz = 0.0
        self.mode = "idle"
        self.mode_t0 = 0.0
        self.side = -1
        self.act = None
        self.act_t0 = 0.0
        self.act_dur = 0.0
        self.act_lv = 0
        self.anger = 0.0
        self.last_click = -100.0
        self.energy = 1.0
        self.run_dist = 0.0
        self.last_wave = -100.0
        self.last_tired = -100.0
        self.last_hover_say = -100.0
        self.last_skid = -100.0
        self.next_fidget = 4.0
        self.next_blink = 1.2
        self.blink_t0 = -10.0
        self.hit_t = -10.0
        self.flash = 0.0
        self.shake_amp = 0.0
        self.pressed = False
        self.press_pos = (0.0, 0.0)
        self.hover = False
        self.swing = 0.0
        self.swing_v = 0.0
        self.spin = 0.0
        self.spin_v = 0.0
        self.thrown = False
        self.dizzy_pending = False
        self.dizzy_until = 0.0
        self.entering = False
        self.sulk_until = 0.0
        self.next_hmph = 0.0
        self.peek_until = 0.0
        self.flee_target = (0.0, 0.0)
        self.flee_until = 0.0
        self.sleep_at = (0.0, 0.0)
        self.next_z = 0.0
        self.z_count = 0
        self.mark = ""
        self.mark_t0 = -10.0
        self.gait = 0.0
        self.stomp_next = 0.0
        self.steam_acc = 0.0
        self.sweat_next = 0.0
        self.dust_next = 0.0
        self.parts = []
        self.bubble = None
        self.history = {}
        self.hidden = False
        self.vis = Spring(1.0, 300.0, 22.0)
        self.s_lean = Spring(0.0, 150.0, 13.0)
        self.s_squash = Spring(0.0, 330.0, 11.0)
        self.s_crouch = Spring(0.0, 120.0, 17.0)
        self.s_lookx = Spring(0.0, 420.0, 36.0)
        self.s_looky = Spring(0.0, 420.0, 36.0)
        self.s_slant = Spring(0.0, 160.0, 22.0)
        self.s_tint = Spring(0.0, 40.0, 12.0)
        self.s_flip = Spring(1.0, 170.0, 19.0)
        self.s_open = Spring(1.0, 500.0, 40.0)
        self.s_dangle = Spring(0.0, 200.0, 22.0)
        self.s_cloud = Spring(0.0, 60.0, 13.0)
        self.s_vein = Spring(0.0, 240.0, 14.0)
        self.s_mark = Spring(0.0, 420.0, 15.0)
        self.s_arm_l = [Spring(0.0, 300.0, 22.0), Spring(0.0, 300.0, 22.0), Spring(0.0, 260.0, 18.0)]
        self.s_arm_r = [Spring(0.0, 300.0, 22.0), Spring(0.0, 300.0, 22.0), Spring(0.0, 260.0, 18.0)]
        self._springs_all = [self.vis, self.s_lean, self.s_squash, self.s_crouch, self.s_lookx, self.s_looky,
                             self.s_slant, self.s_tint, self.s_flip, self.s_open, self.s_dangle, self.s_cloud,
                             self.s_vein, self.s_mark] + self.s_arm_l + self.s_arm_r
        self.edge = (0.0, -1e5, 1e5)
        self.clip_line = None
        self.em_phase = "rise"
        self.em_pt0 = 0.0
        self.em_d0 = 0.0
        self.rt_phase = ""
        self.rt_t0 = 0.0
        self.rt_d0 = 0.0
        self.rt_x = 0.0
        self.edge_check = 0.0
        self.pending_retreat = False
        self.greeted = False
        self.busy = False
        self.speaking = False
        self.goto_target = (0.0, 0.0)
        self.follow_pause = 0.0
        self.wander_until = 0.0
        self.pose = Pose()
        self._build_pose()

    # ── общие помощники ──
    def _clamp_ground(self, x, y):
        a = self.w.area_at(x, y)
        u = self.u
        return (clamp(x, a.left() + 8.5 * u, a.right() - 8.5 * u),
                clamp(y, a.top() + 12.0 * u, a.bottom() - 1.0))

    def _act(self, name, dur, lv=0):
        self.act = name
        self.act_t0 = self.t
        self.act_dur = dur
        self.act_lv = lv

    def _act_p(self):
        if not self.act:
            return 0.0
        return clamp((self.t - self.act_t0) / self.act_dur, 0.0, 1.0)

    def _set_mode(self, mode):
        self.mode = mode
        self.mode_t0 = self.t

    def _pick(self, cat):
        arr = PHRASES[cat]
        hist = self.history.setdefault(cat, [])
        cands = [s for s in arr if s not in hist] or arr
        s = self.rng.choice(cands)
        hist.append(s)
        del hist[:-max(1, min(4, len(arr) - 1))]
        return s

    def say(self, text, shout=None, force=False, voice=True):
        if not force and not getattr(self.w, "phrases", True):
            return
        if shout is None:
            letters = [c for c in text if c.isalpha()]
            shout = bool(letters) and sum(c.isupper() for c in letters) > 0.7 * len(letters) and len(letters) > 3
        self.bubble = Bubble(text, shout, self.u, self.t, self.rng.random())
        tts = getattr(self.w, "speak", None)
        if tts and voice:
            tts(text)

    def live_say(self, text):
        """Обновить облачко на месте (распознавание в процессе)."""
        b = Bubble(text, False, self.u, self.t, 0.5)
        b.t0 = self.t - b.type_dur - 0.01
        b.close_t = self.t + 6.0
        if self.bubble is not None and self.bubble.sc.x > 0.9:
            b.sc.snap(1.0)
        self.bubble = b

    def speed(self):
        return math.hypot(self.vx, self.vy)

    def head_pos(self):
        return self.x, self.y - self.z - 10.0 * self.u

    # ── частицы ──
    def _dust(self, n, spread=5.0):
        u, k = self.u, self.k
        for _ in range(n):
            self.parts.append(Particle("dust", self.x + self.rng.uniform(-spread, spread) * u,
                                       self.y + self.rng.uniform(-0.4, 0.4) * u,
                                       self.rng.uniform(-45, 45) * k - self.vx * 0.12,
                                       self.rng.uniform(-35, -8) * k, life=self.rng.uniform(0.35, 0.55),
                                       size=self.rng.uniform(0.9, 1.5) * u, layer=0, drag=4.0))

    def _steam(self):
        u, k = self.u, self.k
        side = self.rng.choice((-1, 1))
        hx, hy = self.head_pos()
        self.parts.append(Particle("steam", hx + side * self.rng.uniform(3.5, 5.5) * u, hy + 0.3 * u,
                                   side * self.rng.uniform(12, 40) * k, self.rng.uniform(-75, -45) * k,
                                   life=self.rng.uniform(0.7, 1.0), size=self.rng.uniform(0.7, 1.0) * u,
                                   layer=1, drag=1.4))

    def _zzz(self):
        u, k = self.u, self.k
        hx, hy = self.head_pos()
        self.z_count += 1
        self.parts.append(Particle("zzz", hx + 3.5 * u, hy + 1.5 * u, 16 * k, -24 * k, life=2.3,
                                   size=(2.2 if self.z_count % 2 else 3.0) * u, layer=1,
                                   text="z" if self.z_count % 2 else "Z", seed=self.rng.uniform(0, 6)))

    def _sweat(self):
        u, k = self.u, self.k
        side = self.rng.choice((-1, 1))
        hx, hy = self.head_pos()
        self.parts.append(Particle("drop", hx + side * 6.4 * u, hy + 2.0 * u, side * 25 * k, -45 * k,
                                   life=0.55, size=0.62 * u, layer=1, grav=520 * k))

    def _burst(self):
        u = self.u
        cx, cy = self.x, self.y - self.z - 6.0 * u
        base = self.rng.uniform(0, TAU)
        for i in range(8):
            a = base + i * TAU / 8 + self.rng.uniform(-0.15, 0.15)
            self.parts.append(Particle("burst", cx, cy, 0.0, 0.0, life=0.24, size=9.5 * u, layer=1, rot=a))

    def _stars(self, n=5):
        u, k = self.u, self.k
        hx, hy = self.head_pos()
        for _ in range(n):
            a = self.rng.uniform(0, TAU)
            sp = self.rng.uniform(90, 170) * k
            self.parts.append(Particle("star", hx, hy + 2 * u, math.cos(a) * sp, math.sin(a) * sp - 60 * k,
                                       life=0.55, size=self.rng.uniform(0.9, 1.3) * u, layer=1,
                                       spin=self.rng.uniform(-400, 400), drag=3.0))

    def _poof(self):
        u, k = self.u, self.k
        cx, cy = self.x, self.y - self.z - 5.0 * u
        for i in range(12):
            a = i * TAU / 12
            self.parts.append(Particle("poof", cx + math.cos(a) * 3 * u, cy + math.sin(a) * 2.2 * u,
                                       math.cos(a) * 120 * k, math.sin(a) * 90 * k, life=0.45,
                                       size=self.rng.uniform(1.3, 2.0) * u, layer=1, drag=5.0))

    # ── внешние события ──
    def on_press(self, x, y):
        if self.hidden or self.mode in ("emerge", "retreat"):
            return
        self.pressed = True
        self.press_pos = (x, y)
        self.hit_t = self.t
        self.flash = max(self.flash, 0.6)
        self.s_squash.v -= 3.5

    def on_drag(self, x, y):
        if not self.pressed or self.mode == "held" or self.hidden:
            return
        if math.hypot(x - self.press_pos[0], y - self.press_pos[1]) > 6.0:
            self._start_held()

    def on_release(self):
        if self.mode == "held":
            self._throw()
        elif self.pressed:
            self.on_click()
        self.pressed = False

    def on_click(self):
        t = self.t
        total = self.w.note_click()
        quick = t - self.last_click < 1.2
        self.last_click = t
        milestone = MILESTONES.get(total)
        m = self.mode
        if m == "sleep":
            self.anger = max(self.anger, 2.6) + 1.0
            self._wake(soft=False)
            self._hit(True)
            self.say(self._pick("woke"))
            self._act("tantrum", 1.3, lv=3)
            return
        if m in ("sulk", "flee"):
            self.anger = min(10.0, self.anger + 1.2)
            self.sulk_until = max(self.sulk_until, t + 6.0)
            self._hit(False)
            self.say(milestone or self._pick("poke"))
            if m == "sulk":
                if self.rng.random() < 0.55:
                    self._start_flee()
                else:
                    self.peek_until = t + 1.3
            return
        self.anger = min(10.0, self.anger + (1.25 if quick else 1.0))
        lv = self.level()
        self._hit(lv >= 3)
        if m in ("fly", "dizzy", "held"):
            self.say(milestone or self._pick("lvl%d" % min(3, max(1, lv))))
            return
        if lv >= 4:
            self.say(milestone or self._pick("lvl4"))
            self._start_sulk()
            return
        if lv >= 2:
            self._act("tantrum", 1.05 if lv == 2 else 1.55, lv=lv)
            if lv >= 3:
                for _ in range(7):
                    self._steam()
        else:
            self.act = None
        self.say(milestone or self._angry_line(lv))
        if self.mode == "follow":
            self._set_mode("idle")

    def level(self):
        a = self.anger
        return 0 if a < 0.5 else 1 if a < 2.2 else 2 if a < 4.4 else 3 if a < 6.6 else 4

    def _angry_line(self, lv):
        hour = time.localtime().tm_hour
        if lv <= 2 and hour < 5 and self.rng.random() < 0.35:
            return night_line(hour)
        if lv <= 2 and self.rng.random() < 0.3:
            app = self.w.active_app()
            if app:
                for keys, line in APP_LINES:
                    if any(key in app for key in keys):
                        return line
        return self._pick("lvl%d" % max(1, lv))

    def _hit(self, strong):
        k = self.k
        self.hit_t = self.t
        self.flash = 1.0
        self.s_squash.v -= 7.5 if strong else 5.5
        if self.z <= 0.5 and self.mode not in ("held", "fly"):
            self.vz = max(self.vz, (270.0 if strong else 180.0) * k)
        self.shake_amp = max(self.shake_amp, (2.8 if strong else 1.7) * k)
        self._burst()
        self.vx *= 0.25
        self.vy *= 0.25

    def appear(self):
        u, k = self.u, self.k
        self.hidden = False
        cx, cy = self.w.cursor()
        self.cx, self.cy = cx, cy
        side = self.rng.choice((-1, 1))
        self.x, self.y = self._clamp_ground(cx + side * (8 * u + 14 * k), cy + 6 * u)
        area = self.w.area_at(self.x, self.y)
        self.vx = self.vy = 0.0
        self.z = clamp(self.y - area.top() + 2 * u, 120 * k, 430 * k)
        self.vz = 0.0
        self.spin = self.spin_v = 0.0
        self.parts.clear()
        self.bubble = None
        self.act = None
        self.pressed = False
        self.thrown = False
        self.dizzy_pending = False
        self.entering = True
        self.cursor_move_t = self.t
        self.vis.snap(1.0)
        self._set_mode("fly")

    # ── панель: вылезти из-за неё / спрятаться обратно ──
    def _edge_x(self, cx):
        u = self.u
        line, lo, hi = self.edge
        if hi - lo <= 17.0 * u:
            return (lo + hi) / 2.0
        return clamp(cx, lo + 8.5 * u, hi - 8.5 * u)

    def _reset_motion(self):
        self.vx = self.vy = 0.0
        self.z = self.vz = 0.0
        self.spin = self.spin_v = 0.0
        self.act = None
        self.pressed = False
        self.thrown = False
        self.dizzy_pending = False
        self.entering = False

    def emerge(self, edge):
        """Вылезти из-за верхнего края панели (edge = (y_края, x_от, x_до))."""
        u = self.u
        self.edge = edge
        line = edge[0]
        cx, cy = self.w.cursor()
        self.cx, self.cy = cx, cy
        self.cursor_move_t = self.t
        from_dive = self.mode == "retreat" and self.rt_phase == "dive" and not self.hidden
        self._reset_motion()
        self.hidden = False
        self.vis.snap(1.0)
        if from_dive:
            d = self.y - line
            if d > 0.9 * u:
                self._em_next("climb", d)
            else:
                self._em_next("hop", d)
        else:
            self.parts.clear()
            self.bubble = None
            self.x = self._edge_x(cx)
            self.y = line + 11.5 * u
            self._em_next("rise", 11.5 * u)
        self.clip_line = line
        self._set_mode("emerge")

    def _em_next(self, phase, d0):
        self.em_phase = phase
        self.em_pt0 = self.t
        self.em_d0 = d0

    def _emerge(self, h):
        u = self.u
        line = self.edge[0]
        ph = self.em_phase
        dur = {"rise": 0.45, "peek": 0.85, "climb": 0.36, "hop": 0.42}[ph]
        p = clamp((self.t - self.em_pt0) / dur, 0.0, 1.0)
        d0 = self.em_d0
        if ph == "rise":
            d = lerp(d0, 5.9 * u, 1.0 - (1.0 - p) ** 3)
        elif ph == "peek":
            d = 5.9 * u
            if abs(self.t - self.em_pt0 - 0.55) < h:
                self.blink_t0 = self.t
        elif ph == "climb":
            d = lerp(d0, 0.9 * u, smooth(0.0, 1.0, p))
        else:
            d = lerp(d0, -1.0, p) - 5.0 * u * 4.0 * p * (1.0 - p)
        self.y = line + d
        if p >= 1.0:
            if ph == "rise":
                self._em_next("peek", 5.9 * u)
            elif ph == "peek":
                self._em_next("climb", 5.9 * u)
            elif ph == "climb":
                self._em_next("hop", 0.9 * u)
                self.s_squash.v += 4.0
                self.y -= 0.0
                self._dust(3, 3.0)
            else:
                self.y = line - 1.0
                self.clip_line = None
                self._set_mode("idle")
                self.run_dist = 0.0
                self.s_squash.v -= 5.0
                self._dust(4)
                self._act("wave", 1.2)
                self.last_wave = self.t
                self.say(self._pick("greet" if not self.greeted else "hello"))
                self.greeted = True

    def retreat(self, edge):
        """Добежать до панели и нырнуть за неё."""
        u = self.u
        self.edge = edge
        cx, cy = self.w.cursor()
        self.cx, self.cy = cx, cy
        if self.mode == "emerge" and self.y - edge[0] > 0.5 * u:
            self._reset_motion()
            self._rt_dive()
            return
        if self.mode == "fly":
            self.pending_retreat = True
            return
        self._reset_motion()
        self.clip_line = None
        self.rt_x = self._edge_x(cx)
        self.rt_phase = "go"
        self.edge_check = self.t + 0.3
        self._set_mode("retreat")

    def come_back(self, edge):
        """Передумал уходить."""
        if self.rt_phase == "dive":
            self.emerge(edge)
        else:
            self.act = None
            self.bubble = None
            self._set_mode("idle")

    def _rt_dive(self):
        self.rt_phase = "dive"
        self.rt_t0 = self.t
        self.rt_d0 = self.y - self.edge[0]
        self.clip_line = self.edge[0]
        self.act = None
        self._set_mode("retreat")

    def _retreat(self, h):
        u, k, t = self.u, self.k, self.t
        if self.rt_phase == "go":
            if t >= self.edge_check:
                self.edge_check = t + 0.3
                e = self.w.panel_edge()
                if e is not None:
                    self.edge = e
                    self.rt_x = self._edge_x(self.rt_x)
            line = self.edge[0]
            tx, ty = self.rt_x, line - 1.0
            self._steer(tx, ty, 700.0 * k, h)
            if math.hypot(tx - self.x, ty - self.y) < 3.0 and self.speed() < 30.0 * k:
                self.x, self.y = tx, ty
                self.vx = self.vy = 0.0
                self.rt_phase = "bye"
                self.rt_t0 = t
                self._act("wave", 1.05)
                self.say(self._pick("bye"))
        elif self.rt_phase == "bye":
            self._brake(h)
            if t - self.rt_t0 > 1.05:
                self._dust(2, 3.0)
                self._rt_dive()
        else:
            tau = t - self.rt_t0
            if tau < 0.2:
                d = lerp(self.rt_d0, -3.6 * u, 1.0 - (1.0 - tau / 0.2) ** 2)
            else:
                s = tau - 0.2
                d = -3.6 * u + 0.5 * 3300.0 * k * s * s
            self.y = self.edge[0] + d
            if d > 11.5 * u:
                self.hidden = True
                self.vis.snap(0.0)
                self.bubble = None
                self._set_mode("idle")

    def vanish(self):
        if self.hidden:
            return
        self.hidden = True
        self.bubble = None
        self.pressed = False
        if self.mode == "held":
            self._set_mode("idle")
            self.z = 0.0
        self._poof()

    # ── режимы ──
    def _wake(self, soft):
        self._set_mode("idle")
        self.cursor_move_t = self.t
        self._act("startle", 0.75)
        self.mark = "!"
        self.mark_t0 = self.t
        self.vz = 260.0 * self.k
        if soft and self.rng.random() < 0.45:
            self.say(self._pick("woke_soft"))

    def _start_sulk(self):
        self._set_mode("sulk")
        self.act = None
        self.vx = self.vy = 0.0
        self.sulk_until = self.t + self.rng.uniform(9.0, 12.0)
        self.next_hmph = self.t + 3.8

    def _start_flee(self):
        u = self.u
        dx, dy = self.x - self.cx, self.y - self.cy
        d = math.hypot(dx, dy) or 1.0
        best = None
        for ang in (0.0, 0.7, -0.7, 1.5, -1.5, math.pi):
            ca, sa = math.cos(ang), math.sin(ang)
            vx = (dx * ca - dy * sa) / d
            vy = (dx * sa + dy * ca) / d
            tx, ty = self._clamp_ground(self.x + vx * 70 * u, self.y + vy * 45 * u)
            score = math.hypot(tx - self.cx, ty - self.cy)
            if best is None or score > best[0] + 20:
                best = (score, tx, ty)
        self.flee_target = (best[1], best[2])
        self.flee_until = self.t + 2.6
        self.act = None
        self._set_mode("flee")

    def _start_held(self):
        self._set_mode("held")
        self.act = None
        self.swing = 0.0
        self.swing_v = 0.0
        self.anger = min(10.0, self.anger + 0.6)
        self.last_click = self.t
        self.say(self._pick("held"))

    def _throw(self):
        u, k = self.u, self.k
        vx, vy = self.cvx, self.cvy
        sp = math.hypot(vx, vy)
        cap = 2600.0 * k
        if sp > cap:
            vx, vy, sp = vx * cap / sp, vy * cap / sp, cap
        th = math.radians(self.swing)
        # сохраняем положение центра тела при смене точки вращения
        cx = self.cx - 4.3 * u * math.sin(th)
        cyc = self.cy + 4.3 * u * math.cos(th)
        self.x = cx
        self.y = cyc + 6.0 * u + self.z
        self.vx, self.vy = vx, vy
        self.vz = 90.0 * k + min(760.0 * k, sp * 0.32)
        self.spin = self.swing
        self.spin_v = clamp(vx * 0.55 / k, -1100.0, 1100.0) if sp > 900.0 * k else 0.0
        self.thrown = True
        self.dizzy_pending = sp > 1500.0 * k
        self._set_mode("fly")

    def _land(self):
        t = self.t
        self.spin = self.spin_v = 0.0
        self.vx = self.vy = 0.0
        self._set_mode("idle")
        self.run_dist = 0.0
        if self.pending_retreat:
            self.pending_retreat = False
            self.entering = self.thrown = self.dizzy_pending = False
            e = self.w.panel_edge()
            self.retreat(e if e is not None else self.edge)
            return
        if self.entering:
            self.entering = False
            self._act("wave", 1.25)
            self.last_wave = t
            self.say(self._pick("greet"))
            return
        if self.dizzy_pending:
            self.dizzy_pending = False
            self._set_mode("dizzy")
            self.dizzy_until = t + 2.4
            return
        if self.thrown:
            self.thrown = False
            self.anger = min(10.0, self.anger + 0.8)
            self.last_click = t
            self._hit(False)
            self.say(self._pick("thrown"))
            if self.anger >= 2.2:
                self._act("tantrum", 1.1, lv=2)

    def _to_idle(self):
        self._set_mode("idle")
        self.next_fidget = self.t + self.rng.uniform(3.0, 7.0)

    def _arrive(self):
        t = self.t
        self._to_idle()
        if self.run_dist > 420.0 * self.k and self.anger < 0.3 and t - self.last_wave > 25.0 and self.rng.random() < 0.5:
            self._act("wave", 1.15)
            self.last_wave = t
        elif self.energy < 0.35 and t - self.last_tired > 60.0 and not self.bubble:
            self.last_tired = t
            self.say(self._pick("tired"))
        self.run_dist = 0.0

    def _brake(self, h):
        f = math.exp(-14.0 * h)
        self.vx *= f
        self.vy *= f
        if abs(self.vx) + abs(self.vy) < 4.0:
            self.vx = self.vy = 0.0
        self.x += self.vx * h
        self.y += self.vy * h

    def _steer(self, tx, ty, vmax, h):
        k = self.k
        dx, dy = tx - self.x, ty - self.y
        d = math.hypot(dx, dy)
        want = min(vmax, math.sqrt(2.0 * 1700.0 * k * max(0.0, d - 0.5)))
        wx, wy = (dx / d * want, dy / d * want) if d > 1e-6 else (0.0, 0.0)
        ax, ay = wx - self.vx, wy - self.vy
        m = math.hypot(ax, ay)
        lim = 2900.0 * k * h
        if m > lim:
            ax *= lim / m
            ay *= lim / m
        sp = math.hypot(self.vx, self.vy)
        if sp > 330.0 * k and d > 1.0 and (self.vx * dx + self.vy * dy) / (sp * d) < -0.2 and self.t > self.dust_next:
            self.dust_next = self.t + 0.07
            self._dust(2, 3.0)
        self.vx += ax
        self.vy += ay
        self.x += self.vx * h
        self.y += self.vy * h

    def _follow_target(self):
        u, k = self.u, self.k
        lead = clamp(math.hypot(self.cx - self.x, self.cy - self.y) / 1500.0, 0.0, 0.2)
        px = self.cx + self.cvx * lead
        py = self.cy + self.cvy * lead
        if self.x < px - 12:
            self.side = -1
        elif self.x > px + 12:
            self.side = 1
        return self._clamp_ground(px + self.side * (8.0 * u + 14.0 * k), py + 6.0 * u)

    def _ground(self, h):
        u, k, t = self.u, self.k, self.t
        bx, by = self.x, self.y - self.z - 6.0 * u
        dcur = math.hypot(self.cx - bx, self.cy - by)
        blocked = self.act in BLOCKING or self.pressed
        if self.mode == "idle":
            self._brake(h)
            self.energy = min(1.0, self.energy + 0.07 * h)
            if blocked:
                return
            if self.w.follow and dcur > 22.0 * u and self.t > self.follow_pause:
                self._act("launch", 0.11)
                return
            self._idle_life(dcur)
            return
        # follow
        if blocked:
            self._brake(h)
            return
        tx, ty = self._follow_target()
        dist = math.hypot(tx - self.x, ty - self.y)
        sp = self.speed()
        if not self.w.follow or (dcur < 10.0 * u and sp < 280.0 * k):
            self._to_idle()
            return
        if dist < 2.5 and sp < 25.0 * k:
            self._arrive()
            return
        vmax = clamp(110.0 + dist * 1.9, 130.0, 660.0) * k * (0.62 + 0.38 * smooth(0.1, 0.5, self.energy))
        if self.anger >= 2.0:
            vmax *= 1.12
        self._steer(tx, ty, vmax, h)
        self.run_dist += sp * h
        if sp > 380.0 * k:
            self.energy = max(0.0, self.energy - 0.045 * h * sp / (600.0 * k))

    def _idle_life(self, dcur):
        t = self.t
        if (t - self.cursor_move_t > 40.0 and self.anger < 0.3 and not self.bubble and not self.hover
                and not self.pressed):
            self._act("yawn", 1.9)
            return
        if self.act is None and t >= self.next_fidget:
            self.next_fidget = t + self.rng.uniform(4.0, 9.0)
            if self.anger >= 1.5:
                opts = (("tap", 4.0), ("look", 1.0))
            else:
                opts = (("look", 3.0), ("tap", 1.6), ("stretch", 1.3), ("hop", 1.0))
            r = self.rng.uniform(0, sum(w for _, w in opts))
            name = opts[-1][0]
            for n_, w in opts:
                r -= w
                if r <= 0:
                    name = n_
                    break
            self._act(name, {"look": 1.4, "tap": 1.3, "stretch": 1.25, "hop": 0.45}[name])
            if name == "hop":
                self.vz = 230.0 * self.k
        if self.hover and self.anger >= 2.0 and t - self.last_hover_say > 14.0 and not self.bubble:
            self.last_hover_say = t
            self.say(self._pick("hover"))

    def _sleep(self, h):
        self._brake(h)
        sx, sy = self.sleep_at
        if math.hypot(self.cx - sx, self.cy - sy) > 60.0 * self.k:
            self._wake(soft=True)
        elif self.t >= self.next_z:
            self.next_z = self.t + 1.25
            self._zzz()

    def _sulk(self, h):
        self._brake(h)
        t = self.t
        if (t > self.sulk_until and self.anger < 4.8) or t > self.sulk_until + 10.0:
            self._set_mode("idle")
            self.anger = min(self.anger, 1.2)
            self._act("forgive", 1.0)
            self.say(self._pick("forgive"))
            return
        if t > self.next_hmph and not self.bubble:
            self.next_hmph = t + self.rng.uniform(4.0, 7.0)
            self.say(self._pick("hmph"))

    def goto(self, x, y, hold=15.0):
        if self.hidden or self.mode in ("held", "fly", "emerge", "retreat"):
            return
        self.goto_target = self._clamp_ground(x, y)
        self.follow_pause = self.t + hold
        self.wander_until = 0.0
        self.act = None
        self._set_mode("goto")

    def wander(self, secs=10.0):
        if self.hidden or self.mode in ("held", "fly", "emerge", "retreat"):
            return
        self.wander_until = self.t + secs
        self.follow_pause = self.wander_until + 3.0
        self.act = None
        self._next_wander()
        self._set_mode("goto")

    def _next_wander(self):
        b = self.w.bounds()
        u = self.u
        for _ in range(8):
            x = self.rng.uniform(b.left() + 10 * u, b.right() - 10 * u)
            y = self.rng.uniform(b.top() + 14 * u, b.bottom() - 2)
            if math.hypot(x - self.x, y - self.y) > 120 * self.k:
                break
        self.goto_target = self._clamp_ground(x, y)

    def _goto(self, h):
        tx, ty = self.goto_target
        wand = self.t < self.wander_until
        self._steer(tx, ty, (760.0 if wand else 620.0) * self.k, h)
        if math.hypot(tx - self.x, ty - self.y) < 3.0 and self.speed() < 30.0 * self.k:
            if wand:
                if self.rng.random() < 0.3:
                    self.vz = 240.0 * self.k
                self._next_wander()
            else:
                self._to_idle()

    def _flee(self, h):
        tx, ty = self.flee_target
        self._steer(tx, ty, 720.0 * self.k, h)
        if (math.hypot(tx - self.x, ty - self.y) < 3.0 and self.speed() < 30.0 * self.k) or self.t > self.flee_until:
            self._set_mode("sulk")

    def _held(self, h):
        u, k = self.u, self.k
        target = clamp(self.cvx * 0.03 / k, -35.0, 35.0)
        acc = -70.0 * (self.swing - target) - 5.0 * self.swing_v + self.cax * 0.5 / k
        self.swing_v += acc * h
        self.swing = clamp(self.swing + self.swing_v * h, -75.0, 75.0)
        lift = 26.0 * k
        self.z = lift
        self.vz = 0.0
        self.x = self.cx
        self.y = self.cy + 10.3 * u + lift
        self.vx, self.vy = self.cvx, self.cvy

    def _fly(self, h):
        u, k = self.u, self.k
        self.vz -= 2700.0 * k * h
        self.z += self.vz * h
        self.x += self.vx * h
        self.y += self.vy * h
        self.spin += self.spin_v * h
        b = self.w.bounds()
        left, right = b.left() + 8.5 * u, b.right() - 8.5 * u
        top, bottom = b.top() + 12.0 * u, b.bottom() - 1.0
        bonk = False
        if self.x < left:
            self.x, self.vx, bonk = left, abs(self.vx) * 0.45, True
        elif self.x > right:
            self.x, self.vx, bonk = right, -abs(self.vx) * 0.45, True
        if self.y < top:
            self.y, self.vy, bonk = top, abs(self.vy) * 0.45, True
        elif self.y > bottom:
            self.y, self.vy, bonk = bottom, -abs(self.vy) * 0.45, True
        if bonk and self.speed() > 250.0 * k and self.t > self.dust_next:
            self.dust_next = self.t + 0.15
            self._stars(4)
            self.shake_amp = max(self.shake_amp, 2.0 * k)
            self.s_squash.v -= 5.0
            self.spin_v *= -0.6
        if self.z <= 0.0:
            self.z = 0.0
            if self.vz < -240.0 * k:
                impact = -self.vz
                self.vz = impact * 0.36
                self.s_squash.v -= clamp(impact / (95.0 * k), 2.0, 12.0)
                self._dust(5)
                self.shake_amp = max(self.shake_amp, 1.4 * k)
                if impact > 1100.0 * k and self.thrown:
                    self.dizzy_pending = True
            else:
                self.vz = 0.0
                f = math.exp(-5.0 * h)
                self.vx *= f
                self.vy *= f
                sp = self.speed()
                if sp > 280.0 * k and self.t > self.dust_next:
                    self.dust_next = self.t + 0.06
                    self._dust(1, 3.0)
                self.spin_v = 0.0
                tgt = round(self.spin / 360.0) * 360.0
                self.spin = approach(self.spin, tgt, 16.0, h)
                if sp < 22.0 * k and abs(self.spin - tgt) < 3.0:
                    self._land()

    def _dizzy(self, h):
        self._brake(h)
        if self.t > self.dizzy_until:
            self._set_mode("idle")
            self.anger = min(10.0, self.anger + 1.2)
            self.last_click = self.t
            self._hit(False)
            self.say(self._pick("thrown"))
            if self.anger >= 2.2:
                self._act("tantrum", 1.2, lv=2)

    def _end_act(self):
        name = self.act
        self.act = None
        if name == "launch":
            self._set_mode("follow")
            self.s_squash.v += 3.0
        elif name == "yawn":
            self._set_mode("sleep")
            self.sleep_at = (self.cx, self.cy)
            self.next_z = self.t + 0.4

    # ── главный шаг ──
    def update(self, dt):
        dt = clamp(dt, 0.0, 0.1)
        cx, cy = self.w.cursor()
        if dt > 1e-6:
            ivx = (cx - self.pcx) / dt
            ivy = (cy - self.pcy) / dt
            a = 1.0 - math.exp(-dt / 0.045)
            nvx = self.cvx + (ivx - self.cvx) * a
            nvy = self.cvy + (ivy - self.cvy) * a
            self.cax += ((nvx - self.cvx) / dt - self.cax) * (1.0 - math.exp(-dt / 0.06))
            self.cvx, self.cvy = nvx, nvy
        if abs(cx - self.pcx) + abs(cy - self.pcy) > 2.5:
            self.cursor_move_t = self.t
        self.pcx, self.pcy = cx, cy
        self.cx, self.cy = cx, cy
        n = max(1, int(math.ceil(dt * 60.0 - 0.25)))
        h = dt / n
        for _ in range(n):
            self._step(h)
        self._update_fx(dt)
        self._build_pose()

    def _step(self, h):
        self.t += h
        t = self.t
        u, k = self.u, self.k
        if self.mode == "held":
            self.anger = min(10.0, self.anger + 0.3 * h)
        elif t - self.last_click > 3.0:
            self.anger = max(0.0, self.anger - (0.5 if self.mode == "sulk" else 0.28) * h)
        if self.act and t - self.act_t0 >= self.act_dur:
            self._end_act()
        vx0 = self.vx
        m = self.mode
        if m in ("idle", "follow"):
            self._ground(h)
        elif m == "sleep":
            self._sleep(h)
        elif m == "sulk":
            self._sulk(h)
        elif m == "flee":
            self._flee(h)
        elif m == "held":
            self._held(h)
        elif m == "fly":
            self._fly(h)
        elif m == "dizzy":
            self._dizzy(h)
        elif m == "goto":
            self._goto(h)
        elif m == "emerge":
            self._emerge(h)
        elif m == "retreat":
            self._retreat(h)
        m = self.mode
        if m not in ("fly", "held", "emerge", "retreat") and (self.z > 0.0 or self.vz > 0.0):
            self.vz -= 2700.0 * k * h
            self.z += self.vz * h
            if self.z <= 0.0:
                impact = -self.vz
                self.z = 0.0
                self.vz = 0.0
                self.s_squash.v -= clamp(impact / (110.0 * k), 0.5, 7.0)
                if impact > 200.0 * k:
                    self._dust(3)
        self.ax_s = approach(self.ax_s, (self.vx - vx0) / h, 10.0, h)
        if m in ("idle", "follow", "flee", "retreat", "goto") and self.z <= 0.5:
            self.gait += min(self.speed() / (1.25 * u), TAU * 7.5) * h
        self._springs(h)

    def _springs(self, h):
        t, u, k = self.t, self.u, self.k
        m, act, pr = self.mode, self.act, self._act_p()
        sp = self.speed()
        vref = 650.0 * k
        lean = squash = crouch = dangle = cloud = 0.0
        flip = 1.0
        a_l = [0.0, 0.0, 0.0]
        a_r = [0.0, 0.0, 0.0]
        slant = clamp(0.35 + self.anger / 2.2, 0.0, 1.0) if self.anger >= 0.5 else 0.0
        tint = clamp((self.anger - 0.7) / 5.0, 0.0, 0.85)
        opn = 1.0
        vein = 1.0 if self.anger >= 0.9 else 0.0
        look = None
        if m == "emerge":
            d = self.y - self.edge[0]
            ph = self.em_phase
            pe = clamp((t - self.em_pt0) / 0.85, 0.0, 1.0)
            dangle = 1.0
            if ph == "rise":
                a_l = [0.0, -2.6, 25.0]
                a_r = [0.0, -2.6, 25.0]
                look = (0.0, -0.35)
            elif ph in ("peek", "climb"):
                dy = clamp((6.0 * u - d) / u, 0.0 if ph == "climb" else -3.0, 4.2)
                a_l = [0.0, dy, -8.0 if ph == "climb" else 0.0]
                a_r = [0.0, dy, -8.0 if ph == "climb" else 0.0]
                squash = 0.06 if ph == "climb" else 0.0
                if ph == "peek":
                    look = (-0.9, 0.0) if pe < 0.35 else (0.9, 0.0) if pe < 0.7 else None
            else:
                a_l = [0.0, -2.4, 25.0]
                a_r = [0.0, -2.4, 25.0]
        elif m == "retreat" and self.rt_phase == "dive":
            dangle = 1.0
            a_l = [0.0, -3.0, 12.0]
            a_r = [0.0, -3.0, 12.0]
            squash = 0.08
        if m in ("idle", "follow", "flee", "goto") or (m == "retreat" and self.rt_phase != "dive"):
            lean = clamp(self.vx / vref * 8.0 - self.ax_s * 0.0012 / k, -11.0, 11.0)
            squash = -0.04 * min(1.0, sp / vref)
            if m == "idle":
                if self.hover and not self.pressed:
                    opn = 0.6
                    lean += -5.0 if self.cx > self.x else 5.0
                if t - self.cursor_move_t > 14.0 and self.anger < 0.5 and act is None:
                    crouch = 0.4
        elif m == "sleep":
            crouch = 1.0
            a_l = [0.1, 0.9, -10.0]
            a_r = [0.1, 0.9, -10.0]
            vein = slant = 0.0
        elif m == "sulk":
            flip = 1.0 if t < self.peek_until else -1.0
            crouch = 0.25
            a_l = [0.0, 0.5, -12.0]
            a_r = [0.0, 0.5, -12.0]
            cloud = 1.0
        elif m == "held":
            dangle = 1.0
            a_l = [0.0, -3.0, 20.0]
            a_r = [0.0, -3.0, 20.0]
        elif m == "fly":
            dangle = 1.0 if self.z > 2.0 else 0.0
            a_l = [0.0, -2.4, 25.0]
            a_r = [0.0, -2.4, 25.0]
            lean = clamp(self.vx / vref * 8.0, -12.0, 12.0)
        elif m == "dizzy":
            crouch = 0.3
            a_l = [0.0, 0.7, -18.0]
            a_r = [0.0, 0.7, -18.0]
            lean = 8.0 * math.sin(t * 5.2)
        if act == "launch":
            crouch = 0.45
            squash = -0.1
        elif act == "tantrum":
            a_l = [0.0, -3.1, 15.0]
            a_r = [0.0, -3.1, 15.0]
            squash += 0.03
        elif act == "yawn":
            if pr < 0.75:
                up = smooth(0.0, 0.3, pr)
                a_l = [0.0, -3.6 * up, 10.0]
                a_r = [0.0, -3.6 * up, 10.0]
            squash = 0.1 * smooth(0.0, 0.3, pr) * (1.0 - smooth(0.7, 1.0, pr))
            crouch = 0.6 * smooth(0.75, 1.0, pr)
        elif act == "wave":
            a_r = [0.3, -3.4, 20.0]
        elif act == "stretch":
            a_l = [0.0, -3.8, 8.0]
            a_r = [0.0, -3.8, 8.0]
            squash = 0.12 * math.sin(pr * math.pi)
        elif act == "startle":
            a_l = [0.0, -2.6, 28.0]
            a_r = [0.0, -2.6, 28.0]
            squash = 0.06
        elif act == "forgive":
            squash = -0.06 * math.sin(pr * math.pi)
        elif act == "look":
            look = (-0.9, 0.05) if pr < 0.35 else (0.9, 0.05) if pr < 0.7 else None
        if look is None:
            if m in ("follow", "flee", "retreat", "goto") and sp > 60.0 * k:
                look = (self.vx / sp * 0.85, self.vy / sp * 0.5)
            else:
                ex, ey = self.x, self.y - self.z - 7.0 * u
                dx, dy = self.cx - ex, self.cy - ey
                d = math.hypot(dx, dy)
                if d < 1.0:
                    look = (0.0, 0.0)
                else:
                    f = min(1.0, d / (30.0 * u))
                    look = (dx / d * 0.85 * f, dy / d * 0.55 * f)
        if self.busy and m in ("idle", "sulk"):
            look = (0.35 * math.sin(t * 2.3), 0.45)
        if m == "sleep":
            look = (0.0, 0.25)
        elif m == "dizzy":
            look = (0.0, 0.0)
        self.s_lean.t = lean
        self.s_squash.t = squash
        self.s_crouch.t = crouch
        self.s_flip.t = flip
        self.s_dangle.t = dangle
        self.s_slant.t = slant
        self.s_tint.t = tint
        self.s_open.t = opn
        self.s_vein.t = vein
        self.s_cloud.t = cloud
        self.s_lookx.t, self.s_looky.t = look
        for i in range(3):
            self.s_arm_l[i].t = a_l[i]
            self.s_arm_r[i].t = a_r[i]
        self.s_mark.t = 1.0 if (self.mark and t - self.mark_t0 < 0.9) else 0.0
        self.vis.t = 0.0 if self.hidden else 1.0
        for s in self._springs_all:
            s.step(h)

    def _update_fx(self, dt):
        t, u, k = self.t, self.u, self.k
        self.flash = max(0.0, self.flash - dt * 3.5)
        self.shake_amp *= math.exp(-dt * 8.0)
        if self.shake_amp < 0.05:
            self.shake_amp = 0.0
        if t >= self.next_blink:
            self.blink_t0 = t
            self.next_blink = t + (0.24 if self.rng.random() < 0.15 else self.rng.uniform(2.0, 5.5))
        if self.anger >= 4.2 and self.mode != "sleep" and not self.hidden:
            self.steam_acc += dt * (2.0 + (self.anger - 4.2) * 3.0)
            while self.steam_acc >= 1.0:
                self.steam_acc -= 1.0
                self._steam()
        if ((self.energy < 0.3 and self.mode == "follow") or self.mode == "held") and t >= self.sweat_next:
            self.sweat_next = t + self.rng.uniform(0.45, 0.8)
            self._sweat()
        if self.act == "tantrum" and self.z <= 0.5 and t >= self.stomp_next:
            self.stomp_next = t + 0.11
            self._dust(1, 4.5)
        if self.busy and not self.hidden and t - self.mark_t0 > 0.6:
            self.mark = "…"
            self.mark_t0 = t - 0.2
        if self.mark and t - self.mark_t0 > 1.4:
            self.mark = ""
        alive = []
        for q in self.parts:
            q.age += dt
            if q.age < q.life:
                q.update(dt)
                alive.append(q)
        self.parts = alive
        b = self.bubble
        if b is not None:
            b.update(dt, t)
            if b.dead or self.hidden:
                self.bubble = None
            else:
                hx, hy = self.head_pos()
                lift = 8.5 * u * clamp(self.s_cloud.x, 0.0, 1.0)
                b.place(hx, hy - 0.6 * u - lift, self.y + 0.5 * u, self.w.area_at(self.x, self.y))

    def _build_pose(self):
        s = self.pose
        u, k, t = self.u, self.k, self.t
        m, act, pr = self.mode, self.act, self._act_p()
        s.u, s.t = u, t
        s.x, s.y, s.z = self.x, self.y, max(0.0, self.z)
        sp = self.speed()
        grounded = self.z <= 0.5 and (m in ("idle", "follow", "flee", "sulk", "sleep", "dizzy", "goto")
                                       or (m == "retreat" and self.rt_phase != "dive"))
        br = 0.035 * math.sin(t * 1.5) if m == "sleep" else 0.012 * math.sin(t * 2.4)
        sq = self.s_squash.x
        s.sy = 1.0 + sq + br
        s.sx = 1.0 - sq * 0.65 - br * 0.5
        s.lean = self.s_lean.x
        s.crouch = clamp(self.s_crouch.x, -0.2, 1.05)
        s.flip = self.s_flip.x
        s.dangle = clamp(self.s_dangle.x, 0.0, 1.0)
        legs = [[0.0, 0.0] for _ in range(4)]
        bob = 0.0
        if grounded and m in ("idle", "follow", "flee", "retreat", "goto") and sp > 6.0:
            amp = min(1.0, sp / (230.0 * k))
            lamp = min(1.0, sp / (150.0 * k))
            dirx = self.vx / sp
            sgn = 1.0 if dirx >= 0 else -1.0
            for i in range(4):
                ph = self.gait + (0.0 if i in (0, 2) else math.pi)
                legs[i][0] = 0.75 * amp * math.sin(ph) * (0.35 + 0.65 * abs(dirx)) * sgn
                legs[i][1] = 0.9 * lamp * max(0.0, math.cos(ph))
            bob = 0.5 * u * min(1.0, sp / (380.0 * k)) * abs(math.sin(self.gait))
        if act == "tantrum" and self.z <= 0.5:
            f = 5.5 + self.act_lv
            for i in range(4):
                ph = TAU * f * (t - self.act_t0) + (0.0 if i in (0, 2) else math.pi)
                legs[i][1] = max(legs[i][1], 0.95 * max(0.0, math.sin(ph)))
        elif act == "tap":
            legs[3][1] = 0.75 * max(0.0, math.sin(TAU * 3.3 * (t - self.act_t0)))
        if s.dangle > 0.05:
            for i in range(4):
                ph = t * 16.0 + i * 1.7
                legs[i] = [0.35 * math.sin(ph), 0.45 * max(0.0, math.sin(ph + 0.8))]
        s.legs = legs
        s.bob = bob
        a_l = [sp_.x for sp_ in self.s_arm_l]
        a_r = [sp_.x for sp_ in self.s_arm_r]
        if grounded and sp > 6.0 and m != "sleep":
            sw = min(1.0, sp / (300.0 * k))
            g = math.sin(self.gait)
            a_l[1] += 0.5 * sw * g
            a_r[1] -= 0.5 * sw * g
            a_l[2] += 10.0 * sw * g
            a_r[2] -= 10.0 * sw * g
        if act == "tantrum":
            w = TAU * 4.5
            a_l[1] += 0.55 * math.sin(w * t)
            a_r[1] += 0.55 * math.sin(w * t + math.pi)
            a_l[2] += 18.0 * math.sin(w * t + 1.0)
            a_r[2] += 18.0 * math.sin(w * t + 1.0 + math.pi)
        elif act == "wave":
            a_r[2] += 32.0 * math.sin(TAU * 2.2 * (t - self.act_t0))
        elif m == "held" or (m == "fly" and self.z > 2.0):
            a_l[2] += 26.0 * math.sin(t * 17.0)
            a_r[2] += 26.0 * math.sin(t * 17.0 + 2.1)
            a_l[1] += 0.3 * math.sin(t * 13.0)
            a_r[1] += 0.3 * math.sin(t * 13.0 + 1.3)
        s.arm_l, s.arm_r = a_l, a_r
        blink = 1.0
        bt = t - self.blink_t0
        if 0.0 <= bt < 0.17:
            c = bt / 0.06 if bt < 0.06 else 1.0 if bt < 0.09 else 1.0 - (bt - 0.09) / 0.08
            blink = 1.0 - clamp(c, 0.0, 1.0)
        eye = "normal"
        if m == "sleep" or (act == "yawn" and 0.15 < pr) or (act == "stretch" and 0.25 < pr < 0.8):
            eye = "closed"
        elif m == "dizzy":
            eye = "dizzy"
        elif t - self.hit_t < 0.3 or (self.pressed and m != "held"):
            eye = "squeeze"
        elif act == "startle" or (m == "held" and t - self.mode_t0 < 0.4) or (m == "fly" and self.z > 3.0):
            eye = "wide"
        elif act == "wave" or (m == "retreat" and self.rt_phase == "dive"):
            eye = "happy"
        s.eye = eye
        s.eye_open = clamp(self.s_open.x, 0.05, 1.2) * blink
        s.slant = self.s_slant.x if eye == "normal" else 0.0
        s.look = (self.s_lookx.x, self.s_looky.x)
        mouth, mo = None, 0.0
        b = self.bubble
        if b is not None and b.typing(t):
            mouth = "yell" if b.shout else "talk"
            mo = 0.3 + 0.7 * abs(math.sin((t - b.t0) * (19.0 if b.shout else 15.0)))
        elif act == "yawn":
            mouth, mo = "yawn", math.sin(clamp(pr / 0.85, 0.0, 1.0) * math.pi)
        elif act == "tantrum" or m == "held":
            mouth, mo = "yell", 0.45 + 0.55 * abs(math.sin(t * 10.0))
        elif act == "startle" or (m == "fly" and self.z > 3.0) or m == "dizzy":
            mouth, mo = "o", (0.6 if m == "dizzy" else 1.0)
        elif self.anger >= 1.3 and m in ("idle", "follow", "flee"):
            mouth, mo = "frown", 1.0
        if self.speaking and m != "sleep" and mouth not in ("yell", "yawn"):
            mouth, mo = "talk", 0.25 + 0.75 * abs(math.sin(t * 13.0)) * abs(math.sin(t * 4.1 + 1.0))
        s.mouth, s.mouth_open = mouth, mo
        s.tint = clamp(self.s_tint.x, 0.0, 1.0)
        s.flash = self.flash
        amp = self.shake_amp
        if act == "tantrum" and self.act_lv >= 3:
            amp = max(amp, 1.1 * k)
        s.shake = ((self.rng.uniform(-amp, amp), self.rng.uniform(-amp, amp) * 0.6) if amp > 0.05 else (0.0, 0.0))
        s.vein = clamp(self.s_vein.x, 0.0, 1.3) * (1.0 + 0.13 * math.sin(t * 13.0))
        s.sweat = 1.0 if (m == "held" or (self.energy < 0.3 and m == "follow")) else 0.0
        s.scale = max(0.0, self.vis.x)
        s.alpha = clamp(self.vis.x * 1.6, 0.0, 1.0)
        if m == "held":
            s.rot, s.pivot_y = self.swing, -10.3 * u
        elif abs(self.spin) > 0.01:
            s.rot, s.pivot_y = self.spin, -6.0 * u
        else:
            s.rot = 0.0

    # ── отрисовка/геометрия ──
    def paint(self, p):
        s = self.pose
        if s.scale < 0.01 and not self.parts:
            return
        if self.clip_line is not None:
            p.save()
            p.setClipRect(QRectF(-1e5, -1e5, 2e5, 1e5 + self.clip_line))
            self._paint_all(p)
            p.restore()
        else:
            self._paint_all(p)

    def _paint_all(self, p):
        s = self.pose
        u = self.u
        if self.mode == "emerge":
            if self.em_phase == "hop":
                g = self.edge[0] - 1.0
                draw_shadow(p, self.x, g, u, max(0.0, g - self.y), s.alpha)
        elif self.mode == "retreat" and self.rt_phase == "dive":
            pass
        elif s.scale > 0.01:
            draw_shadow(p, self.x, self.y, u, self.z, s.alpha * min(1.0, s.scale))
        for q in self.parts:
            if q.layer == 0:
                paint_particle(p, q, u)
        if s.scale > 0.01:
            draw_clawd(p, s)
            self._paint_extras(p)
        for q in self.parts:
            if q.layer == 1:
                paint_particle(p, q, u)
        if self.bubble is not None:
            self.bubble.paint(p, self.t)

    def _paint_extras(self, p):
        s = self.pose
        u, t = self.u, self.t
        if not ((self.s_mark.x > 0.02 and self.mark) or self.s_cloud.x > 0.02 or self.mode == "dizzy"):
            return
        R, L, _ = pose_transforms(s)
        head = (L * R).map(QPointF(0.0, -8.0 * u))
        hx, hy = head.x(), head.y()
        if self.s_mark.x > 0.02 and self.mark:
            sc = max(0.0, self.s_mark.x)
            p.save()
            p.translate(hx + 3.0 * u, hy - 1.2 * u)
            p.scale(sc, sc)
            path = QPainterPath()
            f = make_font(5.2 * u, True)
            path.addText(-1.2 * u, 0.0, f, self.mark)
            p.setPen(round_pen(C_OUTLINE, 0.55 * u))
            p.setBrush(C_STAR)
            p.drawPath(path)
            p.restore()
        c = self.s_cloud.x
        if c > 0.02:
            a = clamp(c, 0.0, 1.0)
            cy = hy - 5.2 * u - (1.0 - a) * 2.0 * u
            p.setPen(Qt.PenStyle.NoPen)
            for i in range(4):
                x = hx - 2.2 * u + i * 1.45 * u
                ph = (t * 1.9 + i * 0.37) % 1.0
                y0 = cy + 1.2 * u + ph * 3.0 * u
                p.setPen(round_pen(QColor(150, 190, 240, int(220 * a * (1.0 - ph))), 0.28 * u))
                p.drawLine(QPointF(x, y0), QPointF(x - 0.25 * u, y0 + 0.8 * u))
            p.setPen(round_pen(QColor(40, 42, 50, int(160 * a)), 0.2 * u))
            p.setBrush(QColor(C_CLOUD.red(), C_CLOUD.green(), C_CLOUD.blue(), int(240 * a)))
            path = QPainterPath()
            for (ox, oy, r) in ((-2.0, 0.3, 1.5), (0.0, -0.5, 2.0), (1.9, 0.2, 1.5), (0.1, 0.7, 1.4)):
                path.addEllipse(QPointF(hx + ox * u, cy + oy * u), r * u, r * u)
            p.drawPath(path.simplified())
        if self.mode == "dizzy":
            for i in range(3):
                a = t * 4.2 + i * TAU / 3
                sx = hx + math.cos(a) * 5.0 * u
                sy = hy - 1.2 * u + math.sin(a) * 1.3 * u
                sz = (0.75 + 0.25 * math.sin(a)) * u
                p.setPen(round_pen(C_OUTLINE, 0.2 * u))
                p.setBrush(C_STAR)
                p.drawPath(star_path(sx, sy, sz, t * 200.0 + i * 40))

    def input_rect(self):
        if self.hidden or self.pose.scale < 0.3:
            return None
        s = self.pose
        u = self.u
        if abs(s.rot) < 0.5:
            sc = s.scale
            leg_len = u * (2.0 - 1.72 * s.crouch) + s.bob
            hw = (8.2 * u * s.sx * max(abs(s.flip), 0.02) + abs(math.sin(math.radians(s.lean))) * 8.0 * u) * sc
            top = s.y - s.z + s.shake[1] - (leg_len + 8.4 * u * s.sy) * sc
            bot = s.y - s.z + s.shake[1] + 0.5
            x = s.x + s.shake[0]
            return QRectF(x - hw - 2, top - 2, 2 * hw + 4, bot - top + 4)
        R, L, _ = pose_transforms(s)
        B = L * R
        pts = [B.map(QPointF(x, y)) for x, y in ((-8.2 * u, -8.4 * u), (8.2 * u, -8.4 * u),
                                                  (-8.2 * u, 0.0), (8.2 * u, 0.0))]
        pts += [R.map(QPointF(-5.5 * u, 0.0)), R.map(QPointF(5.5 * u, 0.0))]
        xs = [q.x() for q in pts]
        ys = [q.y() for q in pts]
        return QRectF(min(xs) - 2, min(ys) - 2, max(xs) - min(xs) + 4, max(ys) - min(ys) + 4)

    def hit_test(self, x, y):
        r = self.input_rect()
        return r is not None and r.contains(QPointF(x, y))

    def bounds(self):
        u = self.u
        cx, cy = self.x, self.y - self.z - 6.0 * u
        r = QRectF(cx - 14.0 * u, cy - 15.0 * u, 28.0 * u, 24.0 * u)
        r = r.united(QRectF(self.x - 8.0 * u, self.y - 2.0 * u, 16.0 * u, 4.0 * u))
        for q in self.parts:
            e = q.size * 3.2 + 2.0 * u
            r = r.united(QRectF(q.x - e, q.y - e, 2 * e, 2 * e))
        b = self.bubble
        if b is not None:
            r = r.united(b.rect.adjusted(-10, -10, 10, 14))
            r = r.united(QRectF(b.tip.x() - 6, b.tip.y() - 6, 12, 12))
        return r.adjusted(-4, -4, 4, 4)

    def signature(self):
        s = self.pose
        return (round(s.x, 1), round(s.y, 1), round(s.z, 1), round(s.sx, 2), round(s.sy, 2), round(s.lean, 1),
                round(s.rot, 1), round(s.flip, 2), round(s.crouch, 2), s.eye, round(s.eye_open, 2),
                round(s.slant, 2), round(s.look[0], 2), round(s.look[1], 2), s.mouth, round(s.mouth_open, 2),
                round(s.tint, 2), round(s.flash, 2), round(s.vein, 1), round(s.scale, 2),
                tuple(round(v, 1) for v in s.arm_l), tuple(round(v, 1) for v in s.arm_r),
                tuple(round(v, 2) for leg in s.legs for v in leg), s.shake, round(self.s_cloud.x, 2),
                round(self.s_mark.x, 2), self.mode)

    def fps_divisor(self):
        """1 — полная частота, 2 — половинная (спокойные состояния)."""
        if (self.bubble or self.pressed or self.act or self.z > 0.0 or self.hidden or self.speaking
                or self.mode in ("follow", "flee", "held", "fly", "dizzy", "emerge", "retreat", "goto")):
            return 1
        if any(q.kind != "zzz" for q in self.parts):
            return 1
        if self.speed() > 0.5 or self.t - self.blink_t0 < 0.2:
            return 1
        springs = (abs(self.s_flip.v) + abs(self.s_squash.v) + abs(self.s_lean.v) + abs(self.s_crouch.v)
                   + abs(self.s_lookx.v) + abs(self.s_looky.v) + abs(self.s_tint.v))
        if springs > 0.4:
            return 1
        if self.mode == "sleep":
            return 4
        if self.t - self.cursor_move_t < 0.6 or springs > 0.02:
            return 2
        return 4


# ───────────────────────────── X11 через ctypes ─────────────────────────────

class XRectangle(ctypes.Structure):
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short),
                ("width", ctypes.c_ushort), ("height", ctypes.c_ushort)]


class XWindowAttributes(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int), ("width", ctypes.c_int), ("height", ctypes.c_int),
                ("border_width", ctypes.c_int), ("depth", ctypes.c_int), ("visual", ctypes.c_void_p),
                ("root", ctypes.c_ulong), ("class_", ctypes.c_int), ("bit_gravity", ctypes.c_int),
                ("win_gravity", ctypes.c_int), ("backing_store", ctypes.c_int), ("backing_planes", ctypes.c_ulong),
                ("backing_pixel", ctypes.c_ulong), ("save_under", ctypes.c_int), ("colormap", ctypes.c_ulong),
                ("map_installed", ctypes.c_int), ("map_state", ctypes.c_int), ("all_event_masks", ctypes.c_long),
                ("your_event_mask", ctypes.c_long), ("do_not_propagate_mask", ctypes.c_long),
                ("override_redirect", ctypes.c_int), ("screen", ctypes.c_void_p)]


def floating_margin(thick_px):
    """Отступ плавающей панели Plasma внутри её окна (из plasmashellrc)."""
    try:
        with open(os.path.join(_XDG_CONFIG, "plasmashellrc"), encoding="utf-8", errors="ignore") as f:
            lines = f.read().splitlines()
    except OSError:
        return 0.0
    secs, cur = {}, None
    for line in lines:
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            cur = line
            secs.setdefault(cur, {})
        elif cur and "=" in line:
            k_, v_ = line.split("=", 1)
            secs[cur][k_.strip()] = v_.strip()
    best = 0.0
    for sec, kv in secs.items():
        if not (sec.startswith("[PlasmaViews][Panel ") and sec.count("[") == 2) or kv.get("floating") != "1":
            continue
        for sub, kv2 in secs.items():
            if sub.startswith(sec + "[") and "thickness" in kv2:
                try:
                    extra = thick_px - float(kv2["thickness"])
                except ValueError:
                    continue
                if 0 < extra <= 32:
                    best = max(best, extra / 2.0)
    return best


class X11:
    """Минимум Xlib: форма ввода окна (клики сквозь), активное окно, композитинг."""

    def __init__(self):
        self.ok = False
        self.dpy = None
        try:
            X = ctypes.CDLL("libX11.so.6")
            Xe = ctypes.CDLL("libXext.so.6")
        except OSError:
            return
        ul, vp, ci = ctypes.c_ulong, ctypes.c_void_p, ctypes.c_int
        X.XOpenDisplay.argtypes = [ctypes.c_char_p]
        X.XOpenDisplay.restype = vp
        X.XDefaultRootWindow.argtypes = [vp]
        X.XDefaultRootWindow.restype = ul
        X.XDefaultScreen.argtypes = [vp]
        X.XDefaultScreen.restype = ci
        X.XInternAtom.argtypes = [vp, ctypes.c_char_p, ci]
        X.XInternAtom.restype = ul
        X.XGetSelectionOwner.argtypes = [vp, ul]
        X.XGetSelectionOwner.restype = ul
        X.XGetWindowProperty.argtypes = [vp, ul, ul, ctypes.c_long, ctypes.c_long, ci, ul,
                                         ctypes.POINTER(ul), ctypes.POINTER(ci), ctypes.POINTER(ul),
                                         ctypes.POINTER(ul), ctypes.POINTER(vp)]
        X.XGetWindowProperty.restype = ci
        X.XFree.argtypes = [vp]
        X.XFree.restype = ci
        X.XFlush.argtypes = [vp]
        X.XFlush.restype = ci
        self._ERRH = ctypes.CFUNCTYPE(ci, vp, vp)
        self._errh = self._ERRH(lambda d, e: 0)
        X.XSetErrorHandler.argtypes = [self._ERRH]
        X.XSetErrorHandler.restype = vp
        Xe.XShapeQueryExtension.argtypes = [vp, ctypes.POINTER(ci), ctypes.POINTER(ci)]
        Xe.XShapeQueryExtension.restype = ci
        Xe.XShapeCombineRectangles.argtypes = [vp, ul, ci, ci, ci, ctypes.POINTER(XRectangle), ci, ci, ci]
        dpy = X.XOpenDisplay(None)
        if not dpy:
            return
        X.XSetErrorHandler(self._errh)
        self.X, self.Xe, self.dpy = X, Xe, dpy
        self.root = X.XDefaultRootWindow(dpy)
        scr = X.XDefaultScreen(dpy)
        self.a_cm = X.XInternAtom(dpy, ("_NET_WM_CM_S%d" % scr).encode(), 0)
        self.a_active = X.XInternAtom(dpy, b"_NET_ACTIVE_WINDOW", 0)
        self.a_state = X.XInternAtom(dpy, b"_NET_WM_STATE", 0)
        self.a_fs = X.XInternAtom(dpy, b"_NET_WM_STATE_FULLSCREEN", 0)
        self.a_clients = X.XInternAtom(dpy, b"_NET_CLIENT_LIST", 0)
        self.a_wtype = X.XInternAtom(dpy, b"_NET_WM_WINDOW_TYPE", 0)
        self.a_dock = X.XInternAtom(dpy, b"_NET_WM_WINDOW_TYPE_DOCK", 0)
        X.XGetWindowAttributes.argtypes = [vp, ul, ctypes.POINTER(XWindowAttributes)]
        X.XGetWindowAttributes.restype = ci
        X.XTranslateCoordinates.argtypes = [vp, ul, ul, ci, ci, ctypes.POINTER(ci), ctypes.POINTER(ci),
                                            ctypes.POINTER(ul)]
        X.XTranslateCoordinates.restype = ci
        ev, er = ci(), ci()
        self.has_shape = bool(Xe.XShapeQueryExtension(dpy, ctypes.byref(ev), ctypes.byref(er)))
        self.ok = True

    def docks(self):
        """Окна панелей: [(x, y, w, h, видима)] в координатах экрана."""
        res = []
        for w in self._prop(self.root, self.a_clients, 33) or []:
            if self.a_dock not in (self._prop(w, self.a_wtype, 4) or []):
                continue
            a = XWindowAttributes()
            if not self.X.XGetWindowAttributes(self.dpy, w, ctypes.byref(a)):
                continue
            rx, ry, ch = ctypes.c_int(), ctypes.c_int(), ctypes.c_ulong()
            self.X.XTranslateCoordinates(self.dpy, w, self.root, 0, 0, ctypes.byref(rx), ctypes.byref(ry),
                                         ctypes.byref(ch))
            res.append((rx.value, ry.value, a.width, a.height, a.map_state == 2))
        return res

    def _prop(self, win, atom, req_type):
        ul, ci = ctypes.c_ulong, ctypes.c_int
        at, af, n, after, data = ul(), ci(), ul(), ul(), ctypes.c_void_p()
        st = self.X.XGetWindowProperty(self.dpy, win, atom, 0, 1024, 0, req_type, ctypes.byref(at),
                                       ctypes.byref(af), ctypes.byref(n), ctypes.byref(after), ctypes.byref(data))
        if st != 0 or not data.value:
            return None
        try:
            if af.value == 32:
                arr = ctypes.cast(data, ctypes.POINTER(ul))
                return [arr[i] for i in range(n.value)]
            if af.value == 8:
                return ctypes.string_at(data, n.value)
            return None
        finally:
            self.X.XFree(data)

    def compositing(self):
        return bool(self.X.XGetSelectionOwner(self.dpy, self.a_cm))

    def active_window(self):
        v = self._prop(self.root, self.a_active, 33)  # XA_WINDOW
        return v[0] if v else 0

    def is_fullscreen(self, win):
        if not win:
            return False
        v = self._prop(win, self.a_state, 4)  # XA_ATOM
        return bool(v) and self.a_fs in v

    def wm_class(self, win):
        if not win:
            return ""
        v = self._prop(win, 67, 31)  # WM_CLASS, STRING
        if not v:
            return ""
        parts = [p for p in bytes(v).split(b"\0") if p]
        return b" ".join(parts).decode("utf-8", "ignore").lower()

    def set_input(self, win, rects):
        if not self.has_shape:
            return
        arr = (XRectangle * max(1, len(rects)))()
        for i, (x, y, w, h) in enumerate(rects):
            arr[i] = XRectangle(int(clamp(x, -32000, 32000)), int(clamp(y, -32000, 32000)),
                                int(clamp(w, 0, 65000)), int(clamp(h, 0, 65000)))
        # 2 = ShapeInput, 0 = ShapeSet, 0 = Unsorted
        self.Xe.XShapeCombineRectangles(self.dpy, win, 2, 0, 0, arr, len(rects), 0, 0)
        self.X.XFlush(self.dpy)


# ───────────────────────────── окно-оверлей ─────────────────────────────

class Overlay(QWidget):
    """Прозрачное окно на весь экран. Мышь «видит» только прямоугольник питомца."""

    def __init__(self, ctrl):
        flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                 | Qt.WindowType.X11BypassWindowManagerHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        super().__init__(None, flags)
        self.ctrl = ctrl
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_X11DoNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setMouseTracking(True)
        self.setWindowTitle("Clawd")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(e.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.translate(-self.ctrl.origin.x(), -self.ctrl.origin.y())
        self.ctrl.pet.paint(p)
        p.end()

    def mousePressEvent(self, e):
        gp = e.globalPosition()
        pet = self.ctrl.pet
        if e.button() == Qt.MouseButton.LeftButton:
            if pet.hit_test(gp.x(), gp.y()):
                pet.on_press(gp.x(), gp.y())
                self.ctrl.kick()
        elif e.button() == Qt.MouseButton.RightButton:
            self.ctrl.menu.popup(gp.toPoint())
        elif e.button() == Qt.MouseButton.MiddleButton and pet.hit_test(gp.x(), gp.y()):
            self.ctrl.listen()
        e.accept()

    def mouseDoubleClickEvent(self, e):
        self.mousePressEvent(e)

    def mouseMoveEvent(self, e):
        gp = e.globalPosition()
        self.ctrl.pet.on_drag(gp.x(), gp.y())

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.ctrl.pet.on_release()
            self.ctrl.kick()

    def enterEvent(self, e):
        self.ctrl.pet.hover = True

    def leaveEvent(self, e):
        self.ctrl.pet.hover = False


# ───────────────────────────── Clawd с мозгами: Claude Code + голос ─────────────────────────────

DATA_DIR = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), APP_ID)
AGENT_LOG = os.path.join(DATA_DIR, "agent.log")
VOICE_MODELS = {"ru": "vosk-model-small-ru-0.22", "en": "vosk-model-small-en-us-0.15"}
VOICE_LANGS = (("auto", "Авто (рус/англ)"), ("ru", "Русский"), ("en", "English"))


PROMPT_EXTRA = os.path.join(_XDG_CONFIG, APP_ID, "prompt_extra.txt")


def prompt_extra():
    """Личные дополнения к промпту — в файле пользователя, не в коде."""
    try:
        with open(PROMPT_EXTRA, encoding="utf-8") as f:
            t = f.read().strip()
        return ("\n" + t) if t else ""
    except OSError:
        return ""


def find_claude():
    for p in os.environ.get("PATH", "").split(os.pathsep):
        c = os.path.join(p, "claude")
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c

    def ver(path):
        m = path.split("anthropic.claude-code-")[-1].split("-")[0]
        return tuple(int(x) if x.isdigit() else 0 for x in m.split("."))
    cands = glob.glob(os.path.expanduser("~/.vscode*/extensions/anthropic.claude-code-*/resources/native-binary/claude"))
    cands = [c for c in cands if os.access(c, os.X_OK)]
    return max(cands, key=ver) if cands else None


def _short(v, n=160):
    s = v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 1] + "…"


class Agent(QObject):
    """Claude Code в фоне. Весь ход работы пишется в agent.log, питомцу — только статус и ответ."""
    progress = Signal(str)
    finished = Signal(str, bool)
    sentence = Signal(str)

    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        self.proc = None
        self.buf = b""
        self.last_text = ""
        self.err = ""
        self.claude = find_claude()

    @property
    def busy(self):
        return self.proc is not None

    def _log(self, line):
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(AGENT_LOG, "a", encoding="utf-8") as f:
                f.write(time.strftime("%H:%M:%S ") + line + "\n")
        except OSError:
            pass

    def cwd(self):
        d = self.ctrl.cfg.get("ai_cwd") or os.path.expanduser("~")
        return d if os.path.isdir(d) else os.path.expanduser("~")

    def new_session(self):
        self.ctrl.cfg["ai_session"] = ""
        save_config(self.ctrl.cfg)
        self._log("── новый разговор ──")

    def ask(self, text):
        if self.busy:
            return False
        if not self.claude:
            self.finished.emit("Не нашёл Claude Code. Поставь расширение Claude Code для VS Code.", True)
            return False
        cfg = self.ctrl.cfg
        args = ["-p", "--model", cfg["ai_model"], "--effort", cfg["ai_effort"], "--permission-mode", cfg["ai_mode"],
                "--output-format", "stream-json", "--verbose", "--include-partial-messages",
                "--append-system-prompt", CLAWD_PROMPT + prompt_extra(),
                "--allowedTools", "Bash(python3 %s --do:*)" % os.path.join(HERE, "clawd.py"),
                "Bash(python3 ~/clawd-pet/clawd.py --do:*)"]
        sid = cfg.get("ai_session")
        if sid:
            args += ["--resume", sid]
        else:
            sid = str(uuid.uuid4())
            cfg["ai_session"] = sid
            save_config(cfg)
            args += ["--session-id", sid]
        self.sbuf = ""
        self.spoke = False
        self._log("ТЫ [%s/%s/%s]: %s" % (cfg["ai_model"], cfg["ai_effort"], cfg["ai_mode"], text))
        self.proc = QProcess(self)
        self.proc.setWorkingDirectory(self.cwd())
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.readyReadStandardError.connect(self._read_err)
        self.proc.finished.connect(self._done)
        self.buf, self.last_text, self.err = b"", "", ""
        self.proc.start(self.claude, args)
        self.proc.write(text.encode("utf-8"))
        self.proc.closeWriteChannel()
        return True

    def stop(self):
        if self.proc:
            self.proc.kill()

    def _read_err(self):
        if self.proc:
            self.err += bytes(self.proc.readAllStandardError().data()).decode("utf-8", "ignore")

    def _read(self):
        if not self.proc:
            return
        self.buf += bytes(self.proc.readAllStandardOutput().data())
        while b"\n" in self.buf:
            line, self.buf = self.buf.split(b"\n", 1)
            try:
                ev = json.loads(line.decode("utf-8", "ignore"))
            except ValueError:
                continue
            self._event(ev)

    def _flush_sentences(self, final=False):
        import re
        while True:
            m = re.search(r"[.!?…](\s|$)|\n", self.sbuf) if not final else None
            if final:
                piece, self.sbuf = self.sbuf, ""
            elif m and (m.end() >= 12 or "\n" in m.group(0)):
                piece, self.sbuf = self.sbuf[:m.end()], self.sbuf[m.end():]
            elif m:
                # слишком короткий кусок — ждём продолжения, но не бесконечно
                nxt = re.search(r"[.!?…](\s|$)|\n", self.sbuf[m.end():])
                if not nxt:
                    return
                cut = m.end() + nxt.end()
                piece, self.sbuf = self.sbuf[:cut], self.sbuf[cut:]
            else:
                return
            piece = piece.strip()
            if piece:
                self.spoke = True
                self.sentence.emit(piece)
            if final:
                return

    def _event(self, ev):
        t = ev.get("type")
        if t == "stream_event":
            se = ev.get("event") or {}
            if se.get("type") == "content_block_delta" and (se.get("delta") or {}).get("type") == "text_delta":
                self.sbuf += se["delta"].get("text", "")
                self._flush_sentences()
            elif se.get("type") == "content_block_stop":
                self._flush_sentences(final=True)
            return
        msg = ev.get("message") or {}
        content = msg.get("content") if isinstance(msg.get("content"), list) else []
        if t == "assistant":
            for c in content:
                ct = c.get("type")
                if ct == "text" and c.get("text", "").strip():
                    self.last_text = c["text"]
                    self._log("CLAWD: " + c["text"])
                elif ct == "tool_use":
                    inp = c.get("input") or {}
                    what = inp.get("command") or inp.get("file_path") or inp.get("pattern") or inp.get("url") or inp
                    self._log("  ⚙ %s: %s" % (c.get("name", ""), _short(what, 300)))
                    self.progress.emit(c.get("name", ""))
        elif t == "user":
            for c in content:
                if c.get("type") == "tool_result":
                    res = c.get("content")
                    if isinstance(res, list):
                        res = " ".join(x.get("text", "") for x in res if isinstance(x, dict))
                    self._log("  ↳ %s%s" % ("ОШИБКА " if c.get("is_error") else "", _short(res or "", 300)))
        elif t == "system" and ev.get("subtype") == "permission_denied":
            self._log("  ⛔ " + _short(ev.get("message", ""), 300))
        elif t == "result" and ev.get("is_error"):
            self.err += str(ev.get("result", ""))

    def _done(self, code, _st):
        self._read()
        self._flush_sentences(final=True)
        ok = code == 0
        text = self.last_text or ("Остановлено." if code in (9, -9, 15) else _short(self.err or "Что-то пошло не так.", 200))
        if not ok:
            self._log("  код выхода %d %s" % (code, _short(self.err, 300)))
        self.proc = None
        self.finished.emit(text, not ok)


def _vjson(s):
    try:
        return json.loads(s)
    except ValueError:
        import re
        try:
            return json.loads(re.sub(r"(\d),(\d)", r"\1.\2", s))
        except ValueError:
            return {}


class Voice(QObject):
    """Слушает микрофон (parecord) и распознаёт речь Vosk офлайн, в отдельном потоке."""
    partial = Signal(str)
    final = Signal(str)
    state = Signal(str)

    def __init__(self, ctrl):
        super().__init__()
        self.ctrl = ctrl
        self.models = {}
        self.proc = None
        self.thread = None
        self.stop_flag = False
        self.loading = False

    def available(self):
        try:
            import vosk  # noqa: F401
        except ImportError:
            return False
        return any(os.path.isdir(os.path.join(DATA_DIR, m)) for m in VOICE_MODELS.values())

    def langs(self):
        lang = self.ctrl.cfg.get("voice_lang", "auto")
        want = ("ru", "en") if lang == "auto" else (lang,)
        return [lg for lg in want if os.path.isdir(os.path.join(DATA_DIR, VOICE_MODELS[lg]))]

    def preload(self):
        import threading
        if self.loading:
            return
        self.loading = True

        def work():
            try:
                import vosk
                vosk.SetLogLevel(-1)
                for lg in ("ru", "en"):
                    p = os.path.join(DATA_DIR, VOICE_MODELS[lg])
                    if lg not in self.models and os.path.isdir(p):
                        self.models[lg] = vosk.Model(p)
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    @property
    def listening(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, proc=None):
        import subprocess
        import threading
        if self.listening:
            self.stop()
            return
        if not self.available():
            self.final.emit("")
            return
        self.stop_flag = False
        self.woke = proc is not None
        try:
            self.proc = proc or subprocess.Popen(["parecord", "--raw", "--format=s16le", "--rate=16000",
                                                  "--channels=1", "--latency-msec=40"],
                                                 stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            self.final.emit("")
            return
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        self.state.emit("listen")

    def stop(self):
        self.stop_flag = True

    def _precise(self, pcm):
        """Точное распознавание всей фразы через Google (бесплатно, нужен интернет)."""
        try:
            import speech_recognition as sr
        except ImportError:
            return ""
        self.partial.emit("…")
        lang = "en-US" if self.ctrl.cfg.get("voice_lang") == "en" else "ru-RU"
        try:
            r = sr.Recognizer()
            r.operation_timeout = 8
            return r.recognize_google(sr.AudioData(pcm, 16000, 2), language=lang).strip()
        except Exception:
            return ""

    def _run(self):
        try:
            self._listen()
        except Exception:
            self.final.emit("")

    def _listen(self):
        import vosk
        vosk.SetLogLevel(-1)
        t_wait = time.monotonic()
        while self.loading and len(self.models) < len(self.langs()) and time.monotonic() - t_wait < 25:
            time.sleep(0.1)
        recs = {}
        for lg in self.langs():
            m = self.models.get(lg)
            if m is None:
                try:
                    m = self.models[lg] = vosk.Model(os.path.join(DATA_DIR, VOICE_MODELS[lg]))
                except Exception:
                    continue
            r = vosk.KaldiRecognizer(m, 16000)
            r.SetWords(True)
            recs[lg] = r
        texts = {lg: [] for lg in recs}
        confs = {lg: [] for lg in recs}
        partials = {lg: "" for lg in recs}
        t0 = time.monotonic()
        heard_t = None
        shown = ""
        audio = bytearray()

        def take(lg, res):
            if res.get("text"):
                texts[lg].append(res["text"])
                confs[lg].extend(w.get("conf", 0.0) for w in (res.get("result") or []))

        try:
            while not self.stop_flag and recs:
                data = self.proc.stdout.read(1600)
                if not data:
                    break
                audio += data
                now = time.monotonic()
                for lg, r in recs.items():
                    if r.AcceptWaveform(data):
                        take(lg, _vjson(r.Result()))
                        partials[lg] = ""
                        heard_t = now
                    else:
                        p = _vjson(r.PartialResult()).get("partial", "")
                        if p != partials[lg]:
                            partials[lg] = p
                            if p:
                                heard_t = now
                cur = max((" ".join(texts[lg] + ([partials[lg]] if partials[lg] else [])) for lg in recs), key=len)
                if cur and cur != shown:
                    shown = cur
                    self.partial.emit(cur)
                if heard_t is None and now - t0 > 8.0:
                    break
                if heard_t is not None and now - heard_t > 1.8 and not any(partials.values()):
                    break
        finally:
            try:
                self.proc.terminate()
            except Exception:
                pass
        for lg, r in recs.items():
            take(lg, _vjson(r.FinalResult()))
        best, score = "", -1.0
        for lg in recs:
            text = " ".join(texts[lg]).strip()
            if not text:
                continue
            conf = sum(confs[lg]) / max(1, len(confs[lg]))
            if conf > score:
                best, score = text, conf
        if heard_t is not None and len(audio) > 16000:
            precise = self._precise(bytes(audio))
            if precise:
                best = precise
        words = best.split()
        while words and words[0].strip(",.") in WAKE_WORDS["ru"] + WAKE_WORDS["en"] + ["cloud", "клад"]:
            words.pop(0)
        best = " ".join(words)
        if self.woke and not best:
            best = ""
        self.final.emit(best)


WAKE_WORDS = {"ru": ["клод", "клауд", "клоуд", "клода"], "en": ["claude", "clawed", "claud"]}
TTS_VOICES = {"ru": "ru_RU-denis-medium.onnx", "en": "en_US-ryan-medium.onnx"}
TTS_PITCH = 1.0
TTS_CHOICES = (("en-US-AndrewMultilingualNeural", "Andrew — мужской, как в ChatGPT"),
               ("en-US-BrianMultilingualNeural", "Brian — мужской, мягкий"),
               ("en-US-AvaMultilingualNeural", "Ava — женский"),
               ("en-US-EmmaMultilingualNeural", "Emma — женский, мягкий"),
               ("ru-RU-DmitryNeural", "Дмитрий — русский диктор"),
               ("ru-RU-SvetlanaNeural", "Светлана — русский диктор"),
               ("piper", "Офлайн (Piper, без интернета)"))


class WakeWord(QObject):
    """Постоянно слушает микрофон, но узнаёт только имя: «Клод», «Claude» и похожие."""
    detected = Signal()

    def __init__(self, voice):
        super().__init__()
        self.voice = voice
        self.proc = None
        self.thread = None
        self.run_flag = False

    @property
    def active(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self):
        import subprocess
        import threading
        if self.active or not self.voice.available():
            return
        self.run_flag = True
        try:
            self.proc = subprocess.Popen(["parecord", "--raw", "--format=s16le", "--rate=16000", "--channels=1",
                                          "--latency-msec=40"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except OSError:
            return
        self.handoff = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.run_flag = False
        if self.proc and self.proc is not self.handoff:
            try:
                self.proc.terminate()
            except Exception:
                pass

    def take(self):
        """Отдать уже работающий микрофон распознаванию команды."""
        p, self.handoff = self.handoff, None
        return p

    def _hit(self, words, lg):
        return any(w in WAKE_WORDS[lg] for w in words)

    def _run(self):
        try:
            import vosk
            vosk.SetLogLevel(-1)
            t_wait = time.monotonic()
            while self.voice.loading and len(self.voice.models) < len(self.voice.langs()) and time.monotonic() - t_wait < 25:
                time.sleep(0.1)
            recs = {}
            pref = "en" if self.voice.ctrl.cfg.get("voice_lang") == "en" else "ru"
            for lg in (pref, "en" if pref == "ru" else "ru"):
                m = self.voice.models.get(lg)
                if m is not None and not recs:
                    r = vosk.KaldiRecognizer(m, 16000, json.dumps(WAKE_WORDS[lg] + ["[unk]"], ensure_ascii=False))
                    r.SetWords(True)
                    recs[lg] = r
            import array
            from collections import deque
            proc = self.proc
            floor = 400.0
            pre = deque(maxlen=8)
            seen = 0
            hang = 0
            while self.run_flag and recs:
                data = proc.stdout.read(1600)
                if not data:
                    break
                smp = array.array("h", data)
                peak = max(max(smp), -min(smp)) if smp else 0
                floor = floor * 0.995 + min(peak, floor * 3) * 0.005
                loud = peak > max(900.0, floor * 3.5)
                if loud:
                    hang = 16
                elif hang > 0:
                    hang -= 1
                else:
                    pre.append(data)
                    continue
                if pre:
                    data = b"".join(pre) + data
                    pre.clear()
                fired = False
                for lg, r in recs.items():
                    if r.AcceptWaveform(data):
                        res = _vjson(r.Result())
                        seen = 0
                        for w in res.get("result") or []:
                            if w.get("word") in WAKE_WORDS[lg] and w.get("conf", 0.0) >= 0.8:
                                fired = True
                    else:
                        part = _vjson(r.PartialResult()).get("partial", "").split()
                        seen = seen + 1 if self._hit(part, lg) else 0
                        if seen >= 2:
                            fired = True
                if fired:
                    self.run_flag = False
                    self.handoff = proc
                    self.detected.emit()
                    return
        except Exception:
            pass
        finally:
            if self.handoff is None:
                self.stop()


class Speaker(QObject):
    """Озвучка Piper офлайн: синтез по предложениям в фоне, воспроизведение через paplay."""
    speaking = Signal(bool)

    def __init__(self, ctrl=None):
        super().__init__()
        import queue
        self.ctrl = ctrl
        self.q = queue.Queue()
        self.voices = {}
        self.proc = None
        self.gen = 0
        self.thread = None

    def available(self):
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            pass
        try:
            import piper  # noqa: F401
        except ImportError:
            return False
        return any(os.path.exists(os.path.join(DATA_DIR, "voices", v)) for v in TTS_VOICES.values())

    @staticmethod
    def _cache_path(voice, text):
        import hashlib
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()
        return os.path.join(os.path.expanduser("~/.cache"), APP_ID, "tts", voice, h + ".mp3")

    @staticmethod
    async def _synth(voice, text, q=None):
        """Синтез одного предложения; кусочки звука сразу в очередь, итог — в кэш."""
        import edge_tts
        path = Speaker._cache_path(voice, text)
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = f.read()
            if q is not None:
                await q.put(data)
                await q.put(None)
            return data
        buf = bytearray()
        try:
            async for ch in edge_tts.Communicate(text, voice, rate="+6%").stream():
                if ch["type"] == "audio":
                    buf += ch["data"]
                    if q is not None:
                        await q.put(ch["data"])
        finally:
            if q is not None:
                await q.put(None)
        if buf:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path + ".tmp", "wb") as f:
                    f.write(buf)
                os.replace(path + ".tmp", path)
            except OSError:
                pass
        return bytes(buf)

    def _edge(self, gen, text, voice):
        """Нейроголос Microsoft Edge. Предложения синтезируются параллельно, первое играет сразу."""
        import asyncio
        import re
        import subprocess
        sents = [x for x in re.split(r"(?<=[.!?…])\s+", text) if x.strip()] or [text]
        self.proc = subprocess.Popen(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-f", "mp3",
                                      "-probesize", "32", "-analyzeduration", "0", "-fflags", "nobuffer",
                                      "-flags", "low_delay", "-i", "pipe:0"],
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        got = False

        async def run():
            nonlocal got
            queues = [asyncio.Queue() for _ in sents]
            tasks = [asyncio.create_task(self._synth(voice, s_, q)) for s_, q in zip(sents, queues)]
            try:
                for q in queues:
                    while True:
                        chunk = await q.get()
                        if chunk is None or gen != self.gen:
                            break
                        self.proc.stdin.write(chunk)
                        self.proc.stdin.flush()
                        if not got:
                            got = True
                            self.speaking.emit(True)
                    if gen != self.gen:
                        break
            finally:
                for tk in tasks:
                    tk.cancel()
        try:
            asyncio.run(asyncio.wait_for(run(), 60))
        finally:
            try:
                self.proc.stdin.close()
            except Exception:
                pass
        if got and gen == self.gen:
            self.proc.wait()
        else:
            self.proc.kill()
        return got

    def warm(self, voice, texts):
        """Заранее озвучить заготовленные реплики, чтобы они звучали мгновенно."""
        import asyncio
        import threading
        if voice == "piper":
            return

        def work():
            async def run():
                sem = asyncio.Semaphore(3)

                async def one(t_):
                    t_ = self._clean(t_)
                    if not t_ or os.path.exists(self._cache_path(voice, t_)):
                        return
                    async with sem:
                        try:
                            await self._synth(voice, t_)
                        except Exception:
                            pass
                await asyncio.gather(*(one(t_) for t_ in texts))
            try:
                asyncio.run(run())
            except Exception:
                pass
        threading.Thread(target=work, daemon=True).start()

    def say(self, text, interrupt=True):
        import threading
        text = self._clean(text)
        if not text:
            return
        if interrupt:
            self.stop()
        self.q.put((self.gen, text))
        if self.thread is None or not self.thread.is_alive():
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def stop(self):
        import queue
        self.gen += 1
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass
        if self.proc:
            try:
                self.proc.kill()
            except Exception:
                pass

    @staticmethod
    def _clean(text):
        import re
        t = re.sub(r"[`*_#>«»\[\]|~]", " ", text)
        t = re.sub(r"[\U0001F000-\U0001FFFF\u2600-\u27BF]", " ", t)
        t = t.replace("…", ".").replace("—", ",")
        return " ".join(t.split())

    def _voice(self, text):
        from piper import PiperVoice
        lang = "ru" if any("а" <= ch.lower() <= "я" or ch.lower() == "ё" for ch in text) else "en"
        for lg in (lang, "ru", "en"):
            p = os.path.join(DATA_DIR, "voices", TTS_VOICES[lg])
            if os.path.exists(p) and os.path.exists(p + ".json"):
                if lg not in self.voices:
                    self.voices[lg] = PiperVoice.load(p)
                return self.voices[lg]
        return None

    def _run(self):
        import queue
        import re
        import subprocess
        while True:
            try:
                gen, text = self.q.get(timeout=1.0)
            except queue.Empty:
                return
            if gen != self.gen:
                continue
            vname = (self.ctrl.cfg.get("tts_voice") if self.ctrl else None) or "piper"
            if vname != "piper":
                try:
                    ok = self._edge(gen, text, vname)
                except Exception:
                    ok = False
                self.proc = None
                if ok or gen != self.gen:
                    if self.q.empty():
                        self.speaking.emit(False)
                    continue
            try:
                voice = self._voice(text)
            except Exception:
                voice = None
            if voice is None:
                continue
            sr = voice.config.sample_rate
            self.speaking.emit(True)
            try:
                self.proc = subprocess.Popen(["paplay", "--raw", "--format=s16le", "--channels=1",
                                              "--rate=%d" % int(sr * TTS_PITCH)],
                                             stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
                for sent in re.split(r"(?<=[.!?])\s+", text):
                    if gen != self.gen:
                        break
                    for chunk in voice.synthesize(sent):
                        if gen != self.gen:
                            break
                        self.proc.stdin.write(chunk.audio_int16_bytes)
                        self.proc.stdin.flush()
                self.proc.stdin.close()
                self.proc.wait()
            except Exception:
                pass
            finally:
                self.proc = None
                if self.q.empty():
                    self.speaking.emit(False)


# ───────────────────────────── настройки ─────────────────────────────

def load_config():
    cfg = dict(DEFAULT_CFG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update({k: v for k, v in data.items() if k in DEFAULT_CFG})
    except (OSError, ValueError):
        pass
    if cfg["size"] not in SIZES:
        cfg["size"] = "M"
    return cfg


def save_config(cfg):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
    except OSError:
        pass


def desktop_entry():
    return ("[Desktop Entry]\nType=Application\nName=Clawd\nGenericName=Питомец Claude Code\n"
            "Comment=Бегает за мышкой и злится, если в него тыкать\n"
            f"Exec={sys.executable} {os.path.join(HERE, 'clawd.py')}\n"
            f"Icon={ICON_PATH}\nTerminal=false\nCategories=Amusement;\nStartupNotify=false\n"
            "X-KDE-autostart-after=panel\n")


def set_autostart(on):
    try:
        if on:
            os.makedirs(os.path.dirname(AUTOSTART_PATH), exist_ok=True)
            with open(AUTOSTART_PATH, "w", encoding="utf-8") as f:
                f.write(desktop_entry())
        elif os.path.exists(AUTOSTART_PATH):
            os.remove(AUTOSTART_PATH)
    except OSError:
        pass


def render_icon(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    s = Pose()
    s.u = size / 17.5
    s.x = size / 2
    s.y = size / 2 + 5.0 * s.u
    draw_clawd(p, s)
    p.end()
    return img


# ───────────────────────────── контроллер ─────────────────────────────

class Controller(QObject):
    def __init__(self, app, force=False):
        super().__init__()
        self.app = app
        self.force = force
        self.cfg = load_config()
        self.x11 = X11()
        self._app_cache = ("", -10.0)
        self._cfg_dirty = False
        self.origin = QPointF(0, 0)
        self.prev_bounds = QRectF()
        self.last_input = None
        self.last_sig = None
        self.agent = Agent(self)
        self.agent.progress.connect(self._agent_progress)
        self.agent.finished.connect(self._agent_done)
        self.agent.sentence.connect(self._agent_sentence)
        self.voice = Voice(self)
        self.voice.partial.connect(self._voice_partial)
        self.voice.final.connect(self._voice_final)
        self.voice.state.connect(self._voice_state)
        self.speaker = Speaker(self)
        self.speaker.speaking.connect(self._on_speaking)
        self.wake = WakeWord(self.voice)
        self.wake.detected.connect(self._on_wake)
        self.wake_timer = QTimer(self)
        self.wake_timer.timeout.connect(self._wake_check)
        self.wake_timer.start(700)
        if self.voice.available():
            self.voice.preload()
        QTimer.singleShot(4000, self._warm_tts)
        self.shown = False
        self.user_hidden = False
        self.refresh = 60.0
        self.state_file = os.environ.get("CLAWD_STATE")
        self._state_t = 0.0

        self.overlay = Overlay(self)
        self._update_geometry()
        self.overlay.winId()
        self.pet = Pet(self, SIZES[self.cfg["size"]])
        self._set_input([], force=True)

        self.menu = self._build_menu()
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QIcon(QPixmap.fromImage(render_icon(128))), self)
            self.tray.setToolTip("Clawd — только не тыкай в него")
            self.tray.setContextMenu(self.menu)
            self.tray.activated.connect(self._tray_activated)
            self.tray.show()

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.t_last = time.perf_counter()
        self.next_t = self.t_last

        self.env_timer = QTimer(self)
        self.env_timer.timeout.connect(self._check_env)
        self.env_timer.start(400)
        self.save_timer = QTimer(self)
        self.save_timer.timeout.connect(self._flush_cfg)
        self.save_timer.start(5000)

        scr = QGuiApplication.primaryScreen()
        if scr is not None:
            scr.virtualGeometryChanged.connect(lambda *_: self._update_geometry())
        app.screenAdded.connect(lambda *_: self._update_geometry())
        app.screenRemoved.connect(lambda *_: self._update_geometry())
        self._connect_kwin()
        self._check_env()

    # ── мир для питомца ──
    @property
    def follow(self):
        return bool(self.cfg["follow"])

    def cursor(self):
        c = QCursor.pos()
        return float(c.x()), float(c.y())

    def area_at(self, x, y):
        scr = QGuiApplication.screenAt(QPoint(int(x), int(y)))
        if scr is None:
            best, bd = None, 1e18
            for s in QGuiApplication.screens():
                g = s.availableGeometry()
                dx = max(g.left() - x, 0, x - g.right())
                dy = max(g.top() - y, 0, y - g.bottom())
                d = dx * dx + dy * dy
                if d < bd:
                    best, bd = s, d
            scr = best
        if scr is None:
            return QRectF(0, 0, 1920, 1080)
        return QRectF(scr.availableGeometry())

    def bounds(self):
        r = QRectF()
        for s in QGuiApplication.screens():
            r = r.united(QRectF(s.availableGeometry()))
        return r if not r.isNull() else QRectF(0, 0, 1920, 1080)

    def active_app(self):
        name, ts = self._app_cache
        now = time.monotonic()
        if now - ts > 1.0 and self.x11.ok:
            try:
                name = self.x11.wm_class(self.x11.active_window())
            except Exception:
                name = ""
            self._app_cache = (name, now)
        return name

    @property
    def phrases(self):
        return bool(self.cfg.get("phrases", True))

    def panel_edge(self):
        """Верхний край видимой нижней панели рядом с курсором; если её нет — низ экрана."""
        cx, cy = self.cursor()
        scr = QGuiApplication.screenAt(QPoint(int(cx), int(cy))) or QGuiApplication.primaryScreen()
        sg = QRectF(scr.geometry()) if scr is not None else QRectF(0, 0, 1920, 1080)
        best = None
        if self.x11.ok and not self.force:
            try:
                docks = self.x11.docks()
            except Exception:
                docks = []
            for (x, y, w, h, vis) in docks:
                if not vis or w <= h or not sg.intersects(QRectF(x, y, w, h)):
                    continue
                if y + h / 2.0 < sg.center().y():
                    continue
                m = floating_margin(h)
                dist = abs(cx - clamp(cx, x, x + w))
                if best is None or dist < best[0]:
                    best = (dist, (y + m, x + m, x + w - m))
        if best is not None:
            return best[1]
        return (sg.bottom() + 1.0, sg.left(), sg.right() + 1.0)

    def note_click(self):
        self.cfg["clicks"] = int(self.cfg.get("clicks", 0)) + 1
        self._cfg_dirty = True
        return self.cfg["clicks"]

    def _flush_cfg(self):
        if self._cfg_dirty:
            self._cfg_dirty = False
            save_config(self.cfg)

    # ── окно и форма ввода ──
    def _update_geometry(self):
        scr = QGuiApplication.primaryScreen()
        if scr is None:
            return
        g = scr.virtualGeometry()
        self.origin = QPointF(g.x(), g.y())
        self.overlay.setGeometry(g)
        rr = [s.refreshRate() for s in QGuiApplication.screens() if s.refreshRate() > 1]
        self.refresh = clamp(max(rr) if rr else 60.0, 30.0, 240.0)
        self.last_input = None

    def _set_input(self, rects, force=False):
        if not self.x11.ok:
            return
        dpr = self.overlay.devicePixelRatioF()
        ox, oy = self.origin.x(), self.origin.y()
        dev = tuple((int(math.floor((r.x() - ox) * dpr)), int(math.floor((r.y() - oy) * dpr)),
                     int(math.ceil(r.width() * dpr)), int(math.ceil(r.height() * dpr))) for r in rects)
        if not force and dev == self.last_input:
            return
        self.last_input = dev
        self.x11.set_input(int(self.overlay.winId()), list(dev))

    # ── кадры ──
    def kick(self):
        if self.shown or self.pet.parts or self.pet.vis.x > 0.02:
            if not self.timer.isActive() or self.timer.remainingTime() > 2:
                self.timer.stop()
                self.timer.start(0)

    def _tick(self):
        now = time.perf_counter()
        dt = now - self.t_last
        self.t_last = now
        pet = self.pet
        pet.update(min(dt, 0.1))
        b = pet.bounds()
        dirty = b if self.prev_bounds.isNull() else b.united(self.prev_bounds)
        self.prev_bounds = b
        calm = not pet.parts and pet.bubble is None and pet.fps_divisor() > 1
        sig = pet.signature() if calm else None
        if sig is None or sig != self.last_sig or not calm:
            r = dirty.translated(-self.origin.x(), -self.origin.y()).toAlignedRect().adjusted(-2, -2, 2, 2)
            self.overlay.update(r)
        self.last_sig = sig
        ir = pet.input_rect() if self.shown else None
        self._set_input([ir] if ir is not None else [])
        if self.state_file and now - self._state_t > 0.15:
            self._state_t = now
            self._dump_state(ir)
        if not self.shown and pet.vis.x < 0.02 and not pet.parts:
            self.overlay.hide()
            self.prev_bounds = QRectF()
            return
        period = pet.fps_divisor() / self.refresh
        self.next_t += period
        if self.next_t < now - 0.05 or self.next_t > now + 0.25:
            self.next_t = now + period
        self.timer.start(max(0, int(round((self.next_t - now) * 1000.0))))

    def _dump_state(self, ir):
        pet = self.pet
        st = {"x": pet.x, "y": pet.y, "z": pet.z, "mode": pet.mode, "act": pet.act,
              "phase": pet.em_phase if pet.mode == "emerge" else pet.rt_phase, "anger": round(pet.anger, 2),
              "bubble": pet.bubble.text if pet.bubble else None, "shown": self.shown,
              "input": [ir.x(), ir.y(), ir.width(), ir.height()] if ir is not None else None,
              "fps_div": pet.fps_divisor()}
        try:
            with open(self.state_file + ".tmp", "w", encoding="utf-8") as f:
                json.dump(st, f, ensure_ascii=False)
            os.replace(self.state_file + ".tmp", self.state_file)
        except OSError:
            pass

    # ── окружение: композитинг и полноэкранные окна ──
    def _connect_kwin(self):
        try:
            from PySide6.QtDBus import QDBusConnection
            bus = QDBusConnection.sessionBus()
            if bus.isConnected():
                bus.connect("org.kde.KWin", "/Compositor", "org.kde.kwin.Compositing", "compositingToggled",
                            self, SLOT("_on_compositing(bool)"))
        except Exception:
            pass

    @Slot(bool)
    def _on_compositing(self, active):
        self._check_env(comp_hint=bool(active))

    def _check_env(self, comp_hint=None):
        if self.force or not self.x11.ok:
            comp, fs = True, False
        else:
            comp = self.x11.compositing() if comp_hint is None else comp_hint
            fs = False
            if self.cfg["hide_fullscreen"]:
                try:
                    fs = self.x11.is_fullscreen(self.x11.active_window())
                except Exception:
                    fs = False
        if not comp:
            # без композитора прозрачность не работает — окно стало бы чёрным. Прячемся мгновенно.
            if self.overlay.isVisible():
                self.overlay.hide()
            self.timer.stop()
            self.shown = False
            self.pet.hidden = True
            self.pet.vis.snap(0.0)
            self.pet.parts.clear()
            self.pet.bubble = None
            self.prev_bounds = QRectF()
            return
        want = not fs and not self.user_hidden
        if want and not self.shown:
            self.shown = True
            self._set_input([], force=True)
            was_visible = self.overlay.isVisible()
            if not was_visible:
                self.overlay.show()
            if was_visible and self.pet.mode == "retreat" and not self.pet.hidden:
                self.pet.come_back(self.panel_edge())
            else:
                self.pet.emerge(self.panel_edge())
            if not was_visible or not self.timer.isActive():
                self.t_last = time.perf_counter()
                self.next_t = self.t_last
                self.timer.stop()
                self.timer.start(0)
        elif not want and self.shown:
            self.shown = False
            if fs:
                self.pet.vanish()
            else:
                self.pet.retreat(self.panel_edge())
            self.kick()

    # ── меню ──
    def _build_menu(self):
        m = QMenu()
        self._fill_menu(m)
        m.aboutToShow.connect(lambda m=m: (m.clear(), self._fill_menu(m), self._sync_menu()))
        return m

    def _fill_menu(self, m):
        m.addSection("Clawd")
        m.addAction("Сказать голосом (средняя кнопка)").triggered.connect(self.listen)
        m.addAction("Позвать сюда").triggered.connect(self.summon)
        self.a_hide = m.addAction("Спрятать")
        self.a_hide.triggered.connect(self.toggle_hidden)
        m.addSeparator()
        self.a_follow = m.addAction("Ходить за мышкой")
        self.a_follow.setCheckable(True)
        self.a_follow.setChecked(self.follow)
        self.a_follow.toggled.connect(self._set_follow)
        self.a_phr = m.addAction("Реплики")
        self.a_phr.setCheckable(True)
        self.a_phr.setChecked(self.phrases)
        self.a_phr.toggled.connect(self._set_phrases)
        sm = m.addMenu("Размер")
        grp = QActionGroup(sm)
        grp.setExclusive(True)
        for key, title in SIZE_NAMES:
            a = sm.addAction(title)
            a.setCheckable(True)
            a.setChecked(self.cfg["size"] == key)
            a.triggered.connect(lambda _=False, key=key: self._set_size(key))
            grp.addAction(a)
        self.a_fs = m.addAction("Прятаться в полноэкранных окнах")
        self.a_fs.setCheckable(True)
        self.a_fs.setChecked(bool(self.cfg["hide_fullscreen"]))
        self.a_fs.toggled.connect(self._set_fs)
        self.a_auto = m.addAction("Запускать при входе в систему")
        self.a_auto.setCheckable(True)
        self.a_auto.setChecked(os.path.exists(AUTOSTART_PATH))
        self.a_auto.toggled.connect(set_autostart)
        ai = m.addMenu("Мозги Clawd")
        self._cfg_menu(ai, "Модель", AI_MODELS, "ai_model")
        self._cfg_menu(ai, "Размышление", AI_EFFORTS, "ai_effort")
        self._cfg_menu(ai, "Режим доступа", AI_MODES, "ai_mode")
        self._cfg_menu(ai, "Язык голоса", VOICE_LANGS, "voice_lang")
        self._cfg_menu(ai, "Голос", TTS_CHOICES, "tts_voice",
                       lambda: (self.speaker.say("Привет! Вот так я теперь звучу."), self._warm_tts()))
        for key, title in (("tts", "Озвучка"), ("wake", "Откликаться на «Клод»")):
            a = ai.addAction(title)
            a.setCheckable(True)
            a.setChecked(bool(self.cfg.get(key, True)))
            a.toggled.connect(lambda on, key=key: (self.cfg.__setitem__(key, bool(on)), save_config(self.cfg),
                                                   (not on and key == "tts") and self.speaker.stop()))
        ai.addAction("Рабочая папка…").triggered.connect(self._pick_cwd)
        ai.addAction("Новый разговор").triggered.connect(self.agent.new_session)
        ai.addAction("Остановить работу").triggered.connect(self.agent.stop)
        ai.addAction("Открыть журнал работы").triggered.connect(
            lambda: QProcess.startDetached("xdg-open", [AGENT_LOG]) if os.path.exists(AGENT_LOG) else None)
        m.addSeparator()
        m.addAction("Выход").triggered.connect(self.quit)

    def _sync_menu(self):
        self.a_hide.setText("Показать" if self.user_hidden else "Спрятать")
        self.a_auto.blockSignals(True)
        self.a_auto.setChecked(os.path.exists(AUTOSTART_PATH))
        self.a_auto.blockSignals(False)

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_hidden()

    def _set_follow(self, on):
        self.cfg["follow"] = bool(on)
        save_config(self.cfg)

    def listen(self):
        self.speaker.stop()
        self.wake.stop()
        if self.agent.busy:
            self.agent.stop()
            return
        if not self.voice.available():
            self.pet.say("Голос не настроен: нужен vosk и модели в ~/.local/share/clawd-pet", shout=False, force=True)
            self.kick()
            return
        if self.voice.listening:
            self.voice.stop()
            return
        self.voice.start()

    def speak(self, text):
        if self.cfg.get("tts", True) and self.speaker.available():
            self.speaker.say(text)

    def _warm_tts(self):
        texts = [x for arr in PHRASES.values() for x in arr] + list(MILESTONES.values()) + [l for _, l in APP_LINES]
        texts += ["Слушаю…", "Не расслышал.", "Ладно, молчу.", "Начинаем с чистого листа.",
                  "Привет! Вот так я теперь звучу."]
        self.speaker.warm(self.cfg.get("tts_voice", "piper"), texts)

    def _on_speaking(self, on):
        self.pet.speaking = on
        self.kick()

    def _on_wake(self):
        proc = self.wake.take()
        if self.shown and not self.voice.listening:
            self.speaker.stop()
            self.pet.mark = "!"
            self.pet.mark_t0 = self.pet.t
            self.pet.vz = max(self.pet.vz, 200.0 * self.pet.k) if self.pet.z <= 0.5 else self.pet.vz
            self.voice.start(proc)
        elif proc:
            proc.terminate()

    def _wake_check(self):
        want = (self.cfg.get("wake", True) and self.shown and self.voice.available()
                and not self.voice.listening and not self.pet.speaking)
        if want and not self.wake.active:
            self.wake.start()
        elif not want and self.wake.active:
            self.wake.stop()

    def _voice_state(self, st):
        if st == "listen":
            self.pet.live_say("Слушаю…")
            self.pet.mark = "?"
            self.pet.mark_t0 = self.pet.t
            self.kick()

    def _voice_partial(self, text):
        self.pet.live_say(text + "…")
        self.kick()

    def _voice_final(self, text):
        text = text.strip()
        low = text.lower()
        if not text:
            self.pet.live_say("Не расслышал.")
            self.pet.bubble.close_t = self.pet.t + 1.6
        elif low in ("стоп", "хватит", "отмена", "stop", "cancel"):
            self.agent.stop()
            self.pet.live_say("Ладно, молчу.")
            self.pet.bubble.close_t = self.pet.t + 1.6
        elif low in ("новый разговор", "начни сначала", "new chat", "new conversation"):
            self.agent.new_session()
            self.pet.live_say("Начинаем с чистого листа.")
            self.pet.bubble.close_t = self.pet.t + 2.0
        else:
            self.pet.live_say("«" + text + "»")
            self.pet.bubble.close_t = self.pet.t + 1.8
            if self.agent.ask(text):
                self.ai_busy(True)
        self.kick()

    def _agent_progress(self, tool):
        self.pet.mark = "…"
        self.pet.mark_t0 = self.pet.t
        self.kick()

    def _agent_sentence(self, text):
        if self.cfg.get("tts", True) and self.speaker.available():
            self.speaker.say(text, interrupt=False)

    def _agent_done(self, text, err):
        self.ai_busy(False, text, spoken=self.agent.spoke and not err)

    def ai_busy(self, busy, answer="", spoken=False):
        pet = self.pet
        pet.busy = busy
        if not busy:
            pet.mark = "!"
            pet.mark_t0 = pet.t
            if pet.z <= 0.5 and pet.mode == "idle":
                pet.vz = 220.0 * pet.k
            if answer:
                first = " ".join(answer.replace("*", "").replace("`", "").split())
                pet.say(first if len(first) <= 220 else first[:218] + "…", shout=False, force=True, voice=not spoken)
        self.kick()

    def _pick_cwd(self):
        d = QFileDialog.getExistingDirectory(None, "Рабочая папка Clawd", self.agent.cwd())
        if d:
            self.cfg["ai_cwd"] = d
            save_config(self.cfg)
            self.agent.new_session()

    def _cfg_menu(self, parent, title, items, key, on_change=None):
        sm = parent.addMenu(title)
        grp = QActionGroup(sm)
        grp.setExclusive(True)
        for k_, t_ in items:
            a = sm.addAction(t_)
            a.setCheckable(True)
            a.setChecked(self.cfg.get(key) == k_)
            a.triggered.connect(lambda _=False, k_=k_: (self.cfg.__setitem__(key, k_), save_config(self.cfg),
                                                         on_change and on_change()))
            grp.addAction(a)
        return sm

    def _set_phrases(self, on):
        self.cfg["phrases"] = bool(on)
        save_config(self.cfg)
        if not on:
            self.pet.bubble = None
            self.kick()

    def _set_fs(self, on):
        self.cfg["hide_fullscreen"] = bool(on)
        save_config(self.cfg)
        self._check_env()

    def _set_size(self, key):
        self.cfg["size"] = key
        save_config(self.cfg)
        u = SIZES[key]
        self.pet.u = u
        self.pet.k = u / 4.0
        self.pet.bubble = None
        self.pet.parts.clear()
        self.pet.x, self.pet.y = self.pet._clamp_ground(self.pet.x, self.pet.y)
        self.kick()

    def summon(self):
        self.user_hidden = False
        if self.shown and self.pet.mode not in ("emerge", "retreat"):
            self.pet.appear()
            self.kick()
        else:
            self._check_env()

    def toggle_hidden(self):
        self.user_hidden = not self.user_hidden
        self._check_env()

    def quit(self):
        self._flush_cfg()
        self.wake.stop()
        self.speaker.stop()
        if self.tray:
            self.tray.hide()
        self.app.quit()

    def do(self, line):
        """Команды для самого Clawd: python3 clawd.py --do "<команда>"."""
        w = line.strip().lower().split()
        if not w:
            return "пусто"
        c, a = w[0], w[1:]
        on = (a[0] in ("on", "1", "вкл", "да", "true")) if a else None
        pet = self.pet
        b = self.bounds()
        u = pet.u
        spots = {"left": (b.left() + 12 * u, b.center().y()), "right": (b.right() - 12 * u, b.center().y()),
                 "top": (b.center().x(), b.top() + 16 * u), "bottom": (b.center().x(), b.bottom() - 2),
                 "center": (b.center().x(), b.center().y()), "top-left": (b.left() + 12 * u, b.top() + 16 * u),
                 "top-right": (b.right() - 12 * u, b.top() + 16 * u),
                 "bottom-left": (b.left() + 12 * u, b.bottom() - 2), "bottom-right": (b.right() - 12 * u, b.bottom() - 2)}
        simple = {"follow": "follow", "phrases": "phrases", "tts": "tts", "wake": "wake", "fullscreen": "hide_fullscreen"}
        if c == "size" and a and a[0].upper() in SIZES:
            self._set_size(a[0].upper())
        elif c in simple and on is not None:
            key = simple[c]
            self.cfg[key] = on
            save_config(self.cfg)
            if key == "tts" and not on:
                self.speaker.stop()
            if key == "phrases" and not on:
                pet.bubble = None
            if key == "hide_fullscreen":
                self._check_env()
        elif c == "voice" and a:
            names = [k for k, _ in TTS_CHOICES]
            hit = [n for n in names if a[0] in n.lower()]
            if not hit:
                return "нет такого голоса: " + ", ".join(names)
            self.cfg["tts_voice"] = hit[0]
            save_config(self.cfg)
            self._warm_tts()
        elif c in ("model", "effort", "mode") and a:
            key, items = {"model": ("ai_model", AI_MODELS), "effort": ("ai_effort", AI_EFFORTS),
                          "mode": ("ai_mode", AI_MODES)}[c]
            ok = [k for k, _ in items if k.lower() == a[0]]
            if not ok:
                return "варианты: " + ", ".join(k for k, _ in items)
            self.cfg[key] = ok[0]
            save_config(self.cfg)
        elif c == "hide":
            if not self.user_hidden:
                self.toggle_hidden()
        elif c == "show":
            if self.user_hidden:
                self.toggle_hidden()
        elif c == "summon":
            self.summon()
        elif c == "goto" and a:
            if a[0] in spots:
                pet.goto(*spots[a[0]])
            elif a[0] == "cursor":
                cx, cy = self.cursor()
                pet.goto(cx, cy + 6 * u)
            elif len(a) >= 2:
                try:
                    pet.goto(float(a[0]), float(a[1]))
                except ValueError:
                    return "goto X Y — числа"
        elif c == "run":
            pet.wander(float(a[0]) if a and a[0].replace(".", "").isdigit() else 10.0)
        elif c == "jump":
            if pet.z <= 0.5:
                pet.vz = 420.0 * pet.k
        elif c in ("wave", "stretch"):
            pet._act(c, 1.25)
        elif c == "sleep":
            if pet.mode == "idle":
                pet._act("yawn", 1.9)
        elif c == "wake":
            if pet.mode == "sleep":
                pet._wake(soft=True)
        elif c in ("screen", "monitors"):
            scr = QGuiApplication.screens()
            cx, cy = pet.x, pet.y
            out = []
            for i, s in enumerate(scr, 1):
                g = s.geometry()
                here = " (я тут)" if g.contains(QPoint(int(cx), int(cy - 5 * u))) else ""
                out.append("%d: %s %dx%d+%d+%d%s" % (i, s.name(), g.width(), g.height(), g.x(), g.y(), here))
            return "; ".join(out)
        elif c == "monitor" and a:
            scr = QGuiApplication.screens()
            if len(scr) < 2:
                return "монитор всего один"
            cur = QGuiApplication.screenAt(QPoint(int(pet.x), int(pet.y - 5 * u)))
            idx = scr.index(cur) if cur in scr else 0
            if a[0] in ("next", "другой", "следующий"):
                idx = (idx + 1) % len(scr)
            elif a[0] in ("prev", "previous"):
                idx = (idx - 1) % len(scr)
            elif a[0].isdigit() and 1 <= int(a[0]) <= len(scr):
                idx = int(a[0]) - 1
            else:
                return "monitor next|prev|1..%d" % len(scr)
            g = scr[idx].availableGeometry()
            pet.goto(g.center().x(), g.center().y() + 6 * u, hold=20.0)
        else:
            return "не знаю команду"
        self.kick()
        return "ok"

    def command(self, cmd):
        if cmd.startswith("do "):
            return self.do(cmd[3:])
        if cmd == "quit":
            self.quit()
        elif cmd == "toggle":
            self.toggle_hidden()
        elif cmd == "listen":
            self.listen()
        else:
            self.summon()


# ───────────────────────────── тестовый лист кадров ─────────────────────────────

class FakeWorld:
    follow = True
    phrases = True

    def panel_edge(self):
        return (0.0, -100000.0, 100000.0)

    def __init__(self):
        self.c = (0.0, 0.0)

    def cursor(self):
        return self.c

    def area_at(self, x, y):
        return QRectF(-100000, -100000, 200000, 200000)

    def bounds(self):
        return QRectF(-100000, -100000, 200000, 200000)

    def active_app(self):
        return "code"

    def note_click(self):
        return 3


def render_sheet(path, u=4.0, bg=(30, 31, 41)):
    cells = []

    def run(pet, w, sec, fn=None):
        steps = int(sec * 60)
        for i in range(steps):
            if fn:
                fn(pet, w, i)
            pet.update(1 / 60)

    def sc_idle(pet, w):
        w.c = (pet.x + 60 * u, pet.y - 20 * u)
        run(pet, w, 2.0)
        pet.next_blink = pet.t + 10

    def sc_blink(pet, w):
        sc_idle(pet, w)
        pet.blink_t0 = pet.t - 0.07
        pet._build_pose()

    def mk_run(frame):
        def f(pet, w):
            w.c = (pet.x + 3000, pet.y)
            run(pet, w, 1.2 + frame * 2 / 60)
        return f

    def sc_hover(pet, w):
        w.c = (pet.x + 3 * u, pet.y - 6 * u)
        pet.hover = True
        run(pet, w, 1.0)

    def mk_clicks(n, after):
        def f(pet, w):
            w.c = (pet.x + 3 * u, pet.y - 6 * u)
            run(pet, w, 0.5)
            for _ in range(n):
                pet.on_press(*w.c)
                run(pet, w, 0.05)
                pet.on_release()
                run(pet, w, 0.3)
            run(pet, w, after)
        return f

    def sc_held(pet, w):
        w.c = (pet.x, pet.y - 9 * u)
        pet.on_press(*w.c)
        w.c = (w.c[0] + 20, w.c[1] - 10)
        pet.on_drag(*w.c)
        run(pet, w, 0.6, lambda p, ww, i: setattr(ww, "c", (ww.c[0] + (4 if i < 20 else -1), ww.c[1])))

    def sc_fly(pet, w):
        sc_held(pet, w)
        run(pet, w, 0.1, lambda p, ww, i: setattr(ww, "c", (ww.c[0] + 30, ww.c[1] - 8)))
        pet.on_release()
        run(pet, w, 0.18)

    def sc_dizzy(pet, w):
        w.c = (pet.x + 60 * u, pet.y)
        pet._set_mode("dizzy")
        pet.dizzy_until = pet.t + 10
        run(pet, w, 0.8)

    def mk_act(name, dur, at):
        def f(pet, w):
            w.c = (pet.x + 20 * u, pet.y - 12 * u)
            run(pet, w, 0.5)
            pet._act(name, dur)
            run(pet, w, dur * at)
        return f

    def sc_sleep(pet, w):
        w.c = (pet.x + 20 * u, pet.y - 12 * u)
        pet._set_mode("sleep")
        pet.sleep_at = w.c
        run(pet, w, 2.6)

    def sc_greet(pet, w):
        w.c = (pet.x + 20 * u, pet.y - 12 * u)
        pet.say("Привет! Только не тыкай в меня.")
        run(pet, w, 1.2)

    cells = [("idle", sc_idle), ("blink", sc_blink), ("hover", sc_hover), ("greet", sc_greet)]
    cells += [("run %d" % i, mk_run(i)) for i in range(6)]
    cells += [("click x1", mk_clicks(1, 0.1)), ("click x3", mk_clicks(3, 0.25)),
              ("click x5", mk_clicks(5, 0.35)), ("click x7 sulk", mk_clicks(7, 1.2)),
              ("held", sc_held), ("thrown", sc_fly), ("dizzy", sc_dizzy),
              ("yawn", mk_act("yawn", 1.9, 0.4)), ("sleep", sc_sleep), ("wave", mk_act("wave", 1.25, 0.45)),
              ("startle", mk_act("startle", 0.75, 0.3)), ("stretch", mk_act("stretch", 1.25, 0.5))]
    cols = 6
    cw, ch = int(52 * u), int(44 * u)
    rows = (len(cells) + cols - 1) // cols
    img = QImage(cols * cw, rows * ch, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(*bg))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    for idx, (label, fn) in enumerate(cells):
        w = FakeWorld()
        w.c = (0.0, 0.0)
        pet = Pet(w, u, seed=7 + idx)
        pet.x, pet.y = 0.0, 0.0
        fn(pet, w)
        cx = (idx % cols) * cw + cw / 2
        cy = (idx // cols) * ch + ch * 0.78
        p.save()
        p.setClipRect(QRectF((idx % cols) * cw, (idx // cols) * ch, cw, ch))
        p.translate(cx - pet.x, cy - pet.y)
        pet.paint(p)
        p.restore()
        p.setPen(QColor(150, 150, 160) if bg[0] < 128 else QColor(80, 80, 90))
        p.setFont(make_font(11))
        p.drawText(QPointF((idx % cols) * cw + 6, (idx // cols) * ch + 14), f"{label}  [{pet.mode}/{pet.act}]")
    p.end()
    img.save(path)


# ───────────────────────────── main ─────────────────────────────

def install_launcher():
    render_icon(256).save(ICON_PATH)
    os.makedirs(os.path.dirname(LAUNCHER_PATH), exist_ok=True)
    with open(LAUNCHER_PATH, "w", encoding="utf-8") as f:
        f.write(desktop_entry())
    print("Ярлык создан:", LAUNCHER_PATH)


def main():
    global FONT_FAMILY
    argv = sys.argv
    QApplication.setApplicationName(APP_ID)
    QApplication.setApplicationDisplayName("Clawd")
    QGuiApplication.setDesktopFileName(APP_ID)
    app = QApplication(argv[:1])
    import locale
    locale.setlocale(locale.LC_NUMERIC, "C")
    app.setQuitOnLastWindowClosed(False)
    fams = set(QFontDatabase.families())
    for fam in ("Inter", "Noto Sans", "DejaVu Sans"):
        if fam in fams:
            FONT_FAMILY = fam
            break

    if "--sheet" in argv:
        out = argv[argv.index("--sheet") + 1]
        u = float(os.environ.get("CLAWD_SHEET_U", "4"))
        render_sheet(out, u)
        render_sheet(out.replace(".png", "_light.png"), u, bg=(232, 232, 236))
        return 0
    if "--install" in argv:
        install_launcher()
        return 0

    name = f"{APP_ID}-{os.getuid()}"
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(400):
        sock.write(b"quit" if "--quit" in argv else b"toggle" if "--toggle" in argv else ("do " + argv[argv.index("--do") + 1]).encode("utf-8") if "--do" in argv and argv.index("--do") + 1 < len(argv) else b"listen" if "--listen" in argv else b"summon")
        sock.flush()
        sock.waitForBytesWritten(400)
        if "--do" in argv and sock.waitForReadyRead(3000):
            print(bytes(sock.readAll().data()).decode("utf-8", "ignore").strip())
        sock.disconnectFromServer()
        return 0
    if "--quit" in argv:
        print("Clawd не запущен.")
        return 0

    ctrl = Controller(app, force="--force" in argv)
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.listen(name)

    def on_conn():
        c = server.nextPendingConnection()
        if c is None:
            return

        def on_read():
            data = bytes(c.readAll().data()).decode("utf-8", "ignore").strip()
            res = ctrl.command(data)
            if isinstance(res, str):
                c.write((res + "\n").encode("utf-8"))
                c.flush()
        c.readyRead.connect(on_read)
        c.disconnected.connect(c.deleteLater)
    server.newConnection.connect(on_conn)

    signal.signal(signal.SIGINT, lambda *_: ctrl.quit())
    signal.signal(signal.SIGTERM, lambda *_: ctrl.quit())
    keep = QTimer()
    keep.start(400)
    keep.timeout.connect(lambda: None)
    rc = app.exec()
    ctrl._flush_cfg()
    return rc


if __name__ == "__main__":
    sys.exit(main())
