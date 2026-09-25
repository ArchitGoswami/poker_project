"""Best-effort card read from a webcam still. Voice and the card picker stay the sure path."""

from __future__ import annotations

from functools import lru_cache

from app.engine import RANKS, card_name

_MISSING = "Card scanning is unavailable in this install. Speak the card, or tap it below."


def recognize_card(image_bytes: bytes) -> dict:
    try:
        import cv2
        import numpy as np
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return {"ok": False, "error": _MISSING}
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        return {"ok": False, "error": "I couldn't read that image."}
    card = _extract_card(image, cv2, np)
    if card is None:
        return {"ok": False, "error": "I couldn't find a card. Hold one card upright on a plain background."}
    code, confidence = _classify(card, cv2, np, Image, ImageDraw, ImageFont)
    if not code or confidence < 0.28:
        return {
            "ok": False,
            "error": "I couldn't read the rank. Try more light, or tap the card below.",
            "confidence": round(float(confidence), 2),
        }
    return {"ok": True, "card": code, "confidence": round(float(confidence), 2), "name": card_name_from_code(code)}


def card_name_from_code(code: str) -> str:
    from app.engine import parse_card
    return card_name(parse_card(code))


def _extract_card(image, cv2, np):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 60, 160)
    contours, _hier = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_area = 0
    height, width = gray.shape[:2]
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < width * height * 0.04 or area <= best_area:
            continue
        peri = cv2.arcLength(contour, True)
        poly = cv2.approxPolyDP(contour, 0.02 * peri, True)
        if len(poly) != 4:
            continue
        rect = _order(poly.reshape(4, 2).astype("float32"), np)
        span_w = np.linalg.norm(rect[1] - rect[0])
        span_h = np.linalg.norm(rect[2] - rect[1])
        short, long = sorted((span_w, span_h))
        if short < 20 or not 1.2 <= long / short <= 1.8:
            continue
        best = rect
        best_area = area
    if best is None:
        return None
    destination = np.array([[0, 0], [199, 0], [199, 279], [0, 279]], dtype="float32")
    matrix = cv2.getPerspectiveTransform(best, destination)
    return cv2.warpPerspective(image, matrix, (200, 280))


def _order(points, np):
    ordered = np.zeros((4, 2), dtype="float32")
    total = points.sum(axis=1)
    ordered[0] = points[np.argmin(total)]
    ordered[2] = points[np.argmax(total)]
    diff = np.diff(points, axis=1)
    ordered[1] = points[np.argmin(diff)]
    ordered[3] = points[np.argmax(diff)]
    return ordered


def _classify(card, cv2, np, image_cls, draw_cls, font_cls) -> tuple[str | None, float]:
    corner = card[8:118, 8:78]
    rank_img = corner[0:62]
    suit_img = corner[62:110]
    rank, rank_score = _match_rank(rank_img, cv2, np, image_cls, draw_cls, font_cls)
    suit, suit_score = _match_suit(suit_img, cv2, np, image_cls, draw_cls)
    if rank is None or suit is None:
        return None, 0.0
    return rank + suit, (rank_score + suit_score) / 2


def _match_rank(region, cv2, np, image_cls, draw_cls, font_cls):
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (40, 52))
    best_rank = None
    best = -1.0
    for rank, template in _rank_templates(image_cls, draw_cls, font_cls).items():
        score = float(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)[0][0])
        if score > best:
            best = score
            best_rank = rank
    return best_rank, best


def _match_suit(region, cv2, np, image_cls, draw_cls):
    red = region[:, :, 2].astype("float32")
    blue = region[:, :, 0].astype("float32")
    green = region[:, :, 1].astype("float32")
    redish = float(np.mean((red > 90) & (red > green + 25) & (red > blue + 25)))
    family = ("h", "d") if redish > 0.08 else ("s", "c")
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (36, 36))
    best_suit = family[0]
    best = -1.0
    templates = _suit_templates(image_cls, draw_cls)
    for suit in family:
        score = float(cv2.matchTemplate(gray, templates[suit], cv2.TM_CCOEFF_NORMED)[0][0])
        if score > best:
            best = score
            best_suit = suit
    return best_suit, max(best, 0.35 if redish > 0.08 or redish < 0.03 else 0.1)


@lru_cache(maxsize=1)
def _rank_templates(image_cls, draw_cls, font_cls):
    font = font_cls.load_default()
    templates = {}
    for rank in RANKS:
        label = "10" if rank == "T" else rank
        image = image_cls.new("L", (40, 52), 255)
        draw = draw_cls.Draw(image)
        draw.text((6, 8), label, fill=0, font=font)
        import numpy as np
        templates[rank] = np.array(image)
    return templates


@lru_cache(maxsize=1)
def _suit_templates(image_cls, draw_cls):
    import numpy as np
    shapes = {
        "h": [(18, 8), (8, 16), (18, 32), (28, 16)],
        "d": [(18, 4), (30, 18), (18, 32), (6, 18)],
        "s": [(18, 4), (30, 16), (22, 16), (24, 32), (12, 32), (14, 16), (6, 16)],
        "c": [(18, 6), (8, 16), (18, 14), (28, 16), (18, 22), (24, 32), (12, 32)],
    }
    templates = {}
    for suit, points in shapes.items():
        image = image_cls.new("L", (36, 36), 255)
        draw = draw_cls.Draw(image)
        draw.polygon(points, fill=0)
        templates[suit] = np.array(image)
    return templates
