from __future__ import annotations

import math


def _cv2():
    import cv2
    return cv2


def orient_image(image):
    try:
        from PIL import ImageOps
        return ImageOps.exif_transpose(image)
    except Exception:
        return image


def assess_image_quality(image) -> dict[str, float]:
    """Measure source quality independently from OCR model confidence."""
    import numpy as np

    cv2 = _cv2()
    arr = np.array(orient_image(image).convert("RGB"))
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return {
        "blur_variance": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "contrast_std": float(gray.std()),
        "skew_angle": float(_angle_hough(gray) or 0.0),
    }


def perspective_correct(arr):
    cv2 = _cv2()
    import numpy as np
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY) if arr.ndim == 3 else arr
    edges = cv2.Canny(gray, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    h, w = gray.shape[:2]
    area = h * w
    for cnt in sorted(contours, key=cv2.contourArea, reverse=True)[:10]:
        peri = cv2.arcLength(cnt, True)
        poly = cv2.approxPolyDP(cnt, 0.02 * peri, True)
        if len(poly) != 4 or cv2.contourArea(poly) < 0.25 * area:
            continue
        pts = poly.reshape(4, 2).astype("float32")
        s = pts.sum(axis=1); d = np.diff(pts, axis=1).ravel()
        tl, br = pts[s.argmin()], pts[s.argmax()]
        tr, bl = pts[d.argmin()], pts[d.argmax()]
        width = int(max(np.linalg.norm(br-bl), np.linalg.norm(tr-tl)))
        height = int(max(np.linalg.norm(tr-br), np.linalg.norm(tl-bl)))
        if width < 50 or height < 50:
            continue
        ratio = width / max(height, 1)
        if not 0.45 <= ratio <= 2.5:
            continue
        # A screenshot or flatbed scan often has a decorative border box that is
        # itself a straight, axis-aligned rectangle (not a skewed document edge).
        # Warping to that box crops the outer margin and everything text sitting
        # near it, cutting off the start of every line. Only treat this as a
        # perspective-correction target when the corners are actually skewed
        # relative to an axis-aligned rectangle; an already-square box needs no
        # correction and is left untouched.
        max_axis_deviation = max(
            abs(tl[0] - bl[0]), abs(tr[0] - br[0]), abs(tl[1] - tr[1]), abs(bl[1] - br[1])
        )
        if max_axis_deviation < 0.01 * max(width, height):
            continue
        dst = np.array([[0,0],[width-1,0],[width-1,height-1],[0,height-1]], dtype="float32")
        m = cv2.getPerspectiveTransform(np.array([tl,tr,br,bl], dtype="float32"), dst)
        return cv2.warpPerspective(arr, m, (width, height), borderMode=cv2.BORDER_REPLICATE)
    return arr


def _angle_hough(gray) -> float | None:
    import numpy as np

    cv2 = _cv2()
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80, minLineLength=max(40, gray.shape[1]//5), maxLineGap=20)
    if lines is None:
        return None
    angles=[]
    for x1,y1,x2,y2 in lines[:,0]:
        a=math.degrees(math.atan2(y2-y1, x2-x1))
        if abs(a) <= 15: angles.append(a)
    return float(np.median(angles)) if angles else None


def deskew(arr, max_angle: float = 15.0, dead_zone: float = 0.3):
    # Only Hough-on-edges measures skew correctly for a page of several separate
    # text lines: it derives the angle from actual line segments (glyph strokes,
    # rules), so parallel lines of text agree on one angle. minAreaRect used to be
    # averaged in here too, but it fits the smallest rectangle around every dark
    # pixel on the whole page at once — for scattered multi-line text that
    # rectangle is just the page's own bounding box, so it reports a meaningless
    # angle (seen returning exactly 90.0 on an unrotated multi-line scan). That
    # bogus value pulled the median to 45 deg. and this function then rotated a
    # perfectly upright scan by the clamped max_angle, shifting every line
    # further right than the last and clipping the start of each one.
    cv2 = _cv2() 
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY) if arr.ndim == 3 else arr
    angle = _angle_hough(gray)
    if angle is None or not math.isfinite(angle):
        return arr
    angle=max(-max_angle, min(max_angle, angle))
    if abs(angle) < dead_zone: return arr
    h,w=gray.shape[:2]; center=(w/2,h/2)
    m=cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(arr, m, (w,h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def preprocess_for_deep(image, *, clahe: bool = False):
    import numpy as np
    image=orient_image(image).convert("RGB")
    arr=np.array(image)
    arr=perspective_correct(arr)
    arr=deskew(arr)
    if clahe:
        cv2=_cv2(); lab=cv2.cvtColor(arr, cv2.COLOR_RGB2LAB)
        lightness,a,b=cv2.split(lab)
        lightness=cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8)).apply(lightness)
        arr=cv2.cvtColor(cv2.merge((lightness,a,b)), cv2.COLOR_LAB2RGB)
    return arr


def preprocess_for_tesseract(image):
    arr=preprocess_for_deep(image)
    from skimage.filters import threshold_sauvola

    cv2=_cv2()
    gray=cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    gray=cv2.fastNlMeansDenoising(gray, None, 8, 7, 21)
    th=threshold_sauvola(gray, window_size=25, k=0.2)
    return (gray > th).astype("uint8") * 255
