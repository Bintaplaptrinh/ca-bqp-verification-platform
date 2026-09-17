from __future__ import annotations

import argparse
import csv
from pathlib import Path

from cabqp.modules.document_intelligence.extraction import extract
from cabqp.shared.normalization import normalize_text
from cabqp.shared.settings import get_settings

from .common import write_report


def _eq(a, b) -> bool:
    return normalize_text(str(a or '')) == normalize_text(str(b or ''))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--records', required=True, help='CSV with raw_text and ground-truth fields')
    p.add_argument('--out-dir', default='docs/architecture')
    args = p.parse_args()
    tp = fp = fn = 0
    relation_tp = relation_fp = relation_fn = 0
    details = []
    with Path(args.records).open(encoding='utf-8-sig', newline='') as f:
        records = list(csv.DictReader(f))
    for row in records:
        ex = extract(row.get('raw_text', ''))
        pairs = [
            ('PERSON', ex.subject_name, row.get('full_name') or row.get('subject_name')),
            ('POSITION', ex.position, row.get('position')),
            ('UNIT', ex.current_unit, row.get('canonical_unit_name') or row.get('unit_name') or row.get('current_unit')),
        ]
        for label, pred, gold in pairs:
            if not gold:
                continue
            if _eq(pred, gold):
                tp += 1
            else:
                fp += int(bool(pred)); fn += 1
                details.append({'record_id': row.get('record_id'), 'field': label, 'pred': pred, 'gold': gold})
        gold_unit = row.get('canonical_unit_name') or row.get('unit_name') or row.get('current_unit')
        if gold_unit:
            if _eq(ex.current_unit, gold_unit) and ex.relation_confidence >= 0.7:
                relation_tp += 1
            else:
                relation_fp += int(bool(ex.current_unit)); relation_fn += 1
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    rel_p = relation_tp / max(1, relation_tp + relation_fp)
    rel_r = relation_tp / max(1, relation_tp + relation_fn)
    payload = {
        'benchmark': 'extraction_f1',
        'threshold_version': get_settings().threshold_version,
        'entity_f1': 2 * precision * recall / max(1e-12, precision + recall),
        'current_work_unit_relation_f1': 2 * rel_p * rel_r / max(1e-12, rel_p + rel_r),
        'target_current_work_unit_relation_f1': 0.95,
        'errors': details[:100],
    }
    print(write_report('extraction_f1', payload, args.out_dir))


if __name__ == '__main__':
    main()
