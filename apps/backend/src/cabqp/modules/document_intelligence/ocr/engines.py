from __future__ import annotations

import os
import threading
from io import BytesIO
from pathlib import Path

from PIL import Image

from .base import BBox, OcrLine
from .preprocess import assess_image_quality, preprocess_for_deep

_LOCK = threading.Lock()
_CACHE: dict[str, object] = {}

# The vendored VietOCR checkout (apps/backend/vendor/vietocr) ships the upstream YAML configs.
# Reading them from disk keeps model construction offline: Cfg.load_config_from_name()
# fetches both the base and the architecture config over HTTP from vocr.vn, which a
# worker must never depend on at request time.
_VIETOCR_CONFIG_NAMES = {
    'vgg_transformer': 'vgg-transformer.yml',
    'vgg_seq2seq': 'vgg-seq2seq.yml',
    'resnet_transformer': 'resnet-transformer.yml',
    'resnet_fpn_transformer': 'resnet_fpn_transformer.yml',
    'vgg_convseq2seq': 'vgg-convseq2seq.yml',
}


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


def _vietocr_config_dir() -> Path:
    override = os.getenv('VIETOCR_CONFIG_DIR')
    if override:
        return Path(override)
    # <repo>/vendor/vietocr/config, resolved through the installed package so an
    # editable install from the vendored checkout and a wheel both work.
    import vietocr

    candidate = Path(vietocr.__file__).resolve().parent.parent / 'config'
    if candidate.is_dir():
        return candidate
    # A non-editable install lands the package in site-packages without the repo's
    # config/ directory beside it; the deployment then has to point VIETOCR_CONFIG_DIR
    # at the vendored checkout (the Docker image sets it to /opt/vietocr/config).
    raise FileNotFoundError(
        'VietOCR config directory not found; set VIETOCR_CONFIG_DIR to the vendored '
        'checkout\'s config/ directory (apps/backend/vendor/vietocr/config)'
    )


def _vietocr_predictor():
    from cabqp.shared.settings import get_settings

    with _LOCK:
        if 'vietocr' not in _CACHE:
            import yaml
            from vietocr.tool.config import Cfg
            from vietocr.tool.predictor import Predictor

            settings = get_settings()
            config_dir = _vietocr_config_dir()
            arch = settings.vietocr_architecture
            try:
                arch_file = _VIETOCR_CONFIG_NAMES[arch]
            except KeyError:
                raise ValueError(f'Unsupported VietOCR architecture: {arch}') from None
            merged: dict = {}
            for name in ('base.yml', arch_file):
                with (config_dir / name).open(encoding='utf-8') as handle:
                    merged.update(yaml.safe_load(handle))
            cfg = Cfg(merged)
            # The vgg backbone's `pretrained` flag pulls torchvision's ImageNet weights
            # over the network; the recognizer checkpoint below already carries them.
            cfg['cnn']['pretrained'] = False
            cfg['device'] = settings.vietocr_device
            cfg['predictor']['beamsearch'] = settings.vietocr_beamsearch
            cfg['weights'] = _vietocr_weights(cfg['weights'])
            _CACHE['vietocr'] = Predictor(cfg)
    return _CACHE['vietocr']


def _vietocr_weights(default_uri: str) -> str:
    """Resolve the recognizer checkpoint, preferring a baked local file.

    A worker should never reach vocr.vn mid-request: the Docker image bakes the
    checkpoint and `VIETOCR_WEIGHTS` points at it. Outside Docker the file is
    downloaded once into the cache directory and reused.
    """
    local = Path(os.getenv('VIETOCR_WEIGHTS') or _vietocr_cache_dir() / 'vgg_transformer.pth')
    if local.exists():
        return str(local)
    if os.getenv('VIETOCR_DOWNLOAD_ENABLED', 'true').casefold() in {'0', 'false', 'no', 'off'}:
        raise FileNotFoundError(f'VietOCR weights missing and download disabled: {local}')
    return _download_vietocr_weights(default_uri, local)


def _vietocr_cache_dir() -> Path:
    base = os.getenv('XDG_CACHE_HOME') or str(Path.home() / '.cache')
    return Path(base) / 'cabqp' / 'vietocr'


def _download_vietocr_weights(uri: str, destination: Path) -> str:
    import requests

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + '.partial')
    with requests.get(uri, stream=True, timeout=120) as response:
        response.raise_for_status()
        with partial.open('wb') as handle:
            for chunk in response.iter_content(chunk_size=1 << 20):
                handle.write(chunk)
    # Rename only once the body is complete, so an interrupted download can never be
    # picked up as a valid checkpoint on the next run.
    partial.replace(destination)
    return str(destination)


class EasyOcrEngine:
    """Vietnamese detector/recognizer used as the production primary engine.

    EasyOCR preserves Vietnamese diacritics substantially better than a multilingual
    recognizer on the shipped scans. Low-contrast inputs receive CLAHE, while every
    input still goes through the shared perspective/deskew stage.
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


class EasyOcrDetector:
    """Text detection only (CRAFT), used to feed the VietOCR recognizer.

    VietOCR is a recognizer: it transcribes one cropped text line and has no detector
    of its own, so the fallback engine reuses EasyOCR's detection stage.
    """

    name = 'easyocr-det'

    def detect(self, image) -> list[BBox]:
        from cabqp.shared.settings import get_settings

        settings = get_settings()
        quality = assess_image_quality(image)
        arr = preprocess_for_deep(
            image,
            clahe=quality['contrast_std'] < settings.quality_image_contrast_std_min,
        )
        horizontal, free = _easyocr().detect(
            arr,
            text_threshold=settings.easyocr_text_threshold,
            low_text=settings.easyocr_low_text,
            link_threshold=settings.easyocr_link_threshold,
            canvas_size=settings.easyocr_canvas_size,
            mag_ratio=settings.easyocr_magnification,
        )
        boxes: list[BBox] = []
        for box in (horizontal or [[]])[0] or []:
            x_min, x_max, y_min, y_max = (float(v) for v in box)
            boxes.append((x_min, y_min, x_max, y_max))
        for polygon in (free or [[]])[0] or []:
            xs = [float(point[0]) for point in polygon]
            ys = [float(point[1]) for point in polygon]
            boxes.append((min(xs), min(ys), max(xs), max(ys)))
        return boxes


class VietOcrRecognizer:
    """VietOCR (pbcquoc/vietocr) transformer recognizer over detected line crops."""

    name = 'vietocr-rec'

    def __init__(self) -> None:
        self.predictor = _vietocr_predictor()

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
        width, height = pil.size
        out: list[OcrLine] = []
        for box in bboxes:
            x0, y0, x1, y1 = (int(round(v)) for v in box)
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(width, x1), min(height, y1)
            if x1 <= x0 or y1 <= y0:
                continue
            text, conf = self.recognize_crop(pil.crop((x0, y0, x1, y1)))
            if text.strip():
                out.append(OcrLine(text, conf, box, page, self.name))
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


class EasyDetectVietOcrEngine(ComposedOcrEngine):
    """The configured fallback: EasyOCR detection + VietOCR recognition."""

    def __init__(self) -> None:
        super().__init__(EasyOcrDetector(), VietOcrRecognizer())


def get_engine(detector: str | None = None, recognizer: str | None = None):
    from cabqp.shared.settings import get_settings

    s = get_settings()
    detector = (detector or s.ocr_detector).casefold()
    recognizer = (recognizer or s.ocr_recognizer).casefold()
    if detector == 'easyocr' and recognizer == 'easyocr':
        return EasyOcrEngine()
    if detector == 'easyocr' and recognizer == 'vietocr':
        return EasyDetectVietOcrEngine()
    raise ValueError(f'Unsupported OCR composition: {detector}/{recognizer}')


def image_from_bytes(content: bytes) -> Image.Image:
    return Image.open(BytesIO(content)).convert('RGB')
