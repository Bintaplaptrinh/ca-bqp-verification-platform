from __future__ import annotations

import os
import threading
from io import BytesIO
from pathlib import Path

from PIL import Image

from .base import BBox, OcrLine
from .preprocess import assess_image_quality, preprocess_for_deep, preprocess_for_tesseract

_LOCK = threading.Lock()
_CACHE: dict[str, object] = {}


def _paddle():
    with _LOCK:
        if 'paddle' not in _CACHE:
            from paddleocr import PaddleOCR
            try:  # PaddleOCR 3.x
                _CACHE['paddle'] = PaddleOCR(
                    lang='vi',
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                    use_textline_orientation=False,
                    # The oneDNN (MKL-DNN) CPU backend's PIR runtime hits
                    # NotImplementedError: ConvertPirAttribute2RuntimeAttribute on this
                    # detection model's array-of-double attributes when running on
                    # Windows; the plain CPU path lacks that unsupported op path.
                    enable_mkldnn=False,
                )
            except TypeError:  # PaddleOCR 2.x compatibility
                _CACHE['paddle'] = PaddleOCR(use_angle_cls=False, lang='vi', show_log=False)
    return _CACHE['paddle']


def _easyocr():
    """Load the Vietnamese EasyOCR reader once per worker process."""
    with _LOCK:
        if 'easyocr' not in _CACHE:
            import easyocr

            model_dir = os.getenv('EASYOCR_MODEL_DIR')
            download_enabled = os.getenv('EASYOCR_DOWNLOAD_ENABLED', 'true').casefold() not in {
                '0', 'false', 'no', 'off'
            }
            kwargs = {
                'gpu': False,
                'download_enabled': download_enabled,
                'verbose': False,
            }
            if model_dir:
                kwargs['model_storage_directory'] = model_dir
            _CACHE['easyocr'] = easyocr.Reader(['vi'], **kwargs)
    return _CACHE['easyocr']


def _paddle_result(arr) -> tuple[list[BBox], list[str], list[float]]:
    ocr = _paddle()
    if hasattr(ocr, 'predict'):
        results = list(ocr.predict(arr))
        boxes: list[BBox] = []
        texts: list[str] = []
        scores: list[float] = []
        for result in results:
            payload = getattr(result, 'json', None)
            if callable(payload):
                payload = payload()
            if payload is None and isinstance(result, dict):
                payload = result
            data = (payload or {}).get('res', payload or {})
            rec_boxes = data.get('rec_boxes', []) or []
            rec_texts = data.get('rec_texts', []) or []
            rec_scores = data.get('rec_scores', []) or []
            try:
                rec_boxes = rec_boxes.tolist()
            except AttributeError:
                pass
            try:
                rec_scores = rec_scores.tolist()
            except AttributeError:
                pass
            # strict=True: the three arrays describe the same detections, so a length
            # mismatch means the engine returned something we do not understand. Silently
            # truncating to the shortest would drop OCR lines — losing the one carrying a
            # personal code would remove evidence without any signal.
            for box, text, conf in zip(rec_boxes, rec_texts, rec_scores, strict=True):
                boxes.append(tuple(float(v) for v in box[:4]))
                texts.append(str(text))
                scores.append(float(conf))
        return boxes, texts, scores

    result = ocr.ocr(arr, cls=False)
    boxes, texts, scores = [], [], []
    for block in result or []:
        for item in block or []:
            if len(item) < 2:
                continue
            poly = item[0]
            text, conf = item[1]
            xs = [float(p[0]) for p in poly]
            ys = [float(p[1]) for p in poly]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
            texts.append(str(text))
            scores.append(float(conf))
    return boxes, texts, scores


class PaddleDetector:
    name = 'paddle-det'

    def detect(self, image) -> list[BBox]:
        arr = preprocess_for_deep(image)
        boxes, _, _ = _paddle_result(arr)
        return boxes


class PaddleRecognizer:
    name = 'paddle-rec'

    def recognize(self, image, bboxes: list[BBox], *, page: int = 1) -> list[OcrLine]:
        # Paddle's public high-level API is joint detect+recognize. For composition tests/experiments,
        # crop each detector box and use its recognizer output as one atomic line (no char voting).
        arr = preprocess_for_deep(image)
        pil = Image.fromarray(arr)
        out: list[OcrLine] = []
        for box in bboxes:
            x0, y0, x1, y1 = (int(max(0, v)) for v in box)
            if x1 <= x0 or y1 <= y0:
                continue
            crop = pil.crop((x0, y0, x1, y1))
            c_boxes, texts, scores = _paddle_result(preprocess_for_deep(crop))
            del c_boxes
            if not texts:
                continue
            text = ' '.join(t.strip() for t in texts if t.strip()).strip()
            conf = min(scores) if scores else 0.0
            if text:
                out.append(OcrLine(text, conf, box, page, 'paddle-det/paddle-rec'))
        return out


class PaddleEngine:
    name = 'paddle-det/paddle-rec'

    def run(self, image: Image.Image, *, page: int = 1) -> list[OcrLine]:
        arr = preprocess_for_deep(image)
        boxes, texts, scores = _paddle_result(arr)
        # _paddle_result builds these three lists in lockstep; strict=True keeps a future
        # change from silently dropping detections instead of failing loudly.
        return [
            OcrLine(t, c, b, page, self.name)
            for b, t, c in zip(boxes, texts, scores, strict=True)
            if t.strip()
        ]


class EasyOcrEngine:
    """Vietnamese detector/recognizer used as the production primary engine.

    EasyOCR preserves Vietnamese diacritics substantially better than the current
    Paddle multilingual recognizer on the shipped scans. Low-contrast inputs receive
    CLAHE, while every input still goes through the shared perspective/deskew stage.
    """

    name = 'easyocr/easyocr'

    def run(self, image: Image.Image, *, page: int = 1) -> list[OcrLine]:
        from cabqp.shared.settings import get_settings

        settings = get_settings()
        quality = assess_image_quality(image)
        arr = preprocess_for_deep(
            image,
            clahe=quality['contrast_std'] < settings.quality_image_contrast_std_min,
        )
        results = _easyocr().readtext(
            arr,
            detail=1,
            paragraph=False,
            decoder=settings.easyocr_decoder,
            contrast_ths=settings.easyocr_contrast_threshold,
            adjust_contrast=settings.easyocr_adjust_contrast,
            text_threshold=settings.easyocr_text_threshold,
            low_text=settings.easyocr_low_text,
            link_threshold=settings.easyocr_link_threshold,
            canvas_size=settings.easyocr_canvas_size,
            mag_ratio=settings.easyocr_magnification,
        )
        out: list[OcrLine] = []
        for polygon, text, confidence in results:
            text = str(text or '').strip()
            confidence = float(confidence)
            if not text or confidence < settings.easyocr_result_confidence_min:
                continue
            xs = [float(point[0]) for point in polygon]
            ys = [float(point[1]) for point in polygon]
            out.append(
                OcrLine(
                    text,
                    max(0.0, min(1.0, confidence)),
                    (min(xs), min(ys), max(xs), max(ys)),
                    page,
                    self.name,
                )
            )
        return out


class TesseractEngine:
    name = 'tesseract'

    def run(self, image: Image.Image, *, page: int = 1) -> list[OcrLine]:
        import pytesseract
        from pytesseract import Output

        from cabqp.shared.settings import get_settings

        arr = preprocess_for_tesseract(image)
        psm = get_settings().tesseract_page_segmentation_mode
        data = pytesseract.image_to_data(
            arr,
            lang='vie',
            config=f'--oem 1 --psm {psm} -c preserve_interword_spaces=1',
            output_type=Output.DICT,
        )
        out = []
        for i, text in enumerate(data.get('text', [])):
            text = (text or '').strip()
            try:
                conf = float(data['conf'][i]) / 100.0
            except (KeyError, TypeError, ValueError):
                conf = 0.0
            if not text:
                continue
            x, y, w, h = (float(data[k][i]) for k in ('left', 'top', 'width', 'height'))
            out.append(OcrLine(text, max(0.0, min(1.0, conf)), (x, y, x + w, y + h), page, self.name))
        return out


class VietOcrRecognizer:
    name = 'vietocr-rec'

    def __init__(self):
        with _LOCK:
            if 'vietocr' not in _CACHE:
                from vietocr.tool.config import Cfg
                from vietocr.tool.predictor import Predictor

                cfg = Cfg.load_config_from_name('vgg_transformer')
                cfg['cnn']['pretrained'] = False
                local_weights = Path(os.getenv('VIETOCR_WEIGHTS', '/models/vietocr/vgg_transformer.pth'))
                if local_weights.exists():
                    cfg['weights'] = str(local_weights)
                cfg['device'] = 'cpu'
                cfg['predictor']['beamsearch'] = False
                _CACHE['vietocr'] = Predictor(cfg)
        self.predictor = _CACHE['vietocr']

    def recognize_crop(self, crop: Image.Image) -> tuple[str, float]:
        result = self.predictor.predict(crop, return_prob=True)
        if isinstance(result, tuple) and len(result) == 2:
            text, probability = result
            try:
                conf = float(probability)
            except (TypeError, ValueError):
                conf = 0.0
        else:
            text, conf = result, 0.0
        text = str(text)
        return text, max(0.0, min(1.0, conf)) if text.strip() else 0.0

    def recognize(self, image, bboxes: list[BBox], *, page: int = 1) -> list[OcrLine]:
        arr = preprocess_for_deep(image)
        pil = Image.fromarray(arr)
        out = []
        for box in bboxes:
            x0, y0, x1, y1 = (int(max(0, v)) for v in box)
            if x1 <= x0 or y1 <= y0:
                continue
            text, conf = self.recognize_crop(pil.crop((x0, y0, x1, y1)))
            if text.strip():
                out.append(OcrLine(text, conf, box, page, f'paddle-det/{self.name}'))
        return out


class ComposedOcrEngine:
    def __init__(self, detector, recognizer):
        self.detector = detector
        self.recognizer = recognizer
        self.name = f'{detector.name}/{recognizer.name}'

    def run(self, image: Image.Image, *, page: int = 1) -> list[OcrLine]:
        boxes = self.detector.detect(image)
        lines = self.recognizer.recognize(image, boxes, page=page)
        for line in lines:
            line.engine = self.name
        return lines


class PaddleDetectVietOcrEngine(ComposedOcrEngine):
    def __init__(self):
        super().__init__(PaddleDetector(), VietOcrRecognizer())


def get_engine(detector: str | None = None, recognizer: str | None = None):
    from cabqp.shared.settings import get_settings

    s = get_settings()
    detector = (detector or s.ocr_detector).casefold()
    recognizer = (recognizer or s.ocr_recognizer).casefold()
    if detector == 'easyocr' and recognizer == 'easyocr':
        return EasyOcrEngine()
    if detector == 'tesseract' or recognizer == 'tesseract':
        return TesseractEngine()
    if detector == 'paddle' and recognizer == 'vietocr':
        return PaddleDetectVietOcrEngine()
    if detector == 'paddle' and recognizer == 'paddle':
        return PaddleEngine()  # optimized joint execution; separate classes remain available for A/B composition
    raise ValueError(f'Unsupported OCR composition: {detector}/{recognizer}')


def image_from_bytes(content: bytes) -> Image.Image:
    return Image.open(BytesIO(content)).convert('RGB')
