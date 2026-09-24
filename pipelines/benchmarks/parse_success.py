from __future__ import annotations

import argparse
import csv
from pathlib import Path

from cabqp.modules.document_intelligence.parsers import parse_document
from cabqp.shared.settings import get_settings

from .common import write_report

OCR_KINDS = {'png_scan', 'image', 'pdf_scan'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', required=True)
    p.add_argument('--root', required=True)
    p.add_argument('--out-dir', default='docs/architecture')
    args = p.parse_args()
    with Path(args.manifest).open(encoding='utf-8-sig', newline='') as f:
        items = list(csv.DictReader(f))
    stats = {'structured': [0, 0], 'ocr': [0, 0]}
    failures = []
    for item in items:
        path = Path(args.root) / item['path']
        bucket = 'ocr' if item.get('document_type') in OCR_KINDS else 'structured'
        stats[bucket][1] += 1
        try:
            result = parse_document(path.name, path.read_bytes())
            ok = bool(result.text.strip()) and str(result.quality.get('gate_result', 'FAIL')).upper() == 'PASS'
        except Exception as exc:
            ok = False
            failures.append({'path': item['path'], 'error': type(exc).__name__})
        stats[bucket][0] += int(ok)
    payload = {
        'benchmark': 'parse_success',
        'threshold_version': get_settings().threshold_version,
        'structured': {'passed': stats['structured'][0], 'total': stats['structured'][1], 'rate': stats['structured'][0] / max(1, stats['structured'][1]), 'target': 0.99},
        'ocr': {'passed': stats['ocr'][0], 'total': stats['ocr'][1], 'rate': stats['ocr'][0] / max(1, stats['ocr'][1]), 'target': 0.95},
        'failures': failures[:100],
    }
    print(write_report('parse_success', payload, args.out_dir))


if __name__ == '__main__':
    main()
