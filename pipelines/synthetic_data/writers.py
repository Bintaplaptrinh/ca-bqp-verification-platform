from __future__ import annotations
import csv
import json
from pathlib import Path


class Writers:
    def __init__(self, out_dir: Path, columns: list[str]):
        out_dir.mkdir(parents=True, exist_ok=True)
        self.csv_file = (out_dir / "synthetic_records.csv").open("w", newline="", encoding="utf-8-sig")
        self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=columns)
        self.csv_writer.writeheader()
        self.jsonl_file = (out_dir / "synthetic_records.jsonl").open("w", encoding="utf-8")
        self.entities_file = (out_dir / "extraction_annotations.jsonl").open("w", encoding="utf-8")
        self.relations_file = (out_dir / "relation_annotations.jsonl").open("w", encoding="utf-8")

    def write(self, row, entities, relations):
        self.csv_writer.writerow(row)
        self.jsonl_file.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.entities_file.write(json.dumps({
            "record_id": row["record_id"],
            "text": row["raw_text"],
            "entities": entities,
        }, ensure_ascii=False) + "\n")
        self.relations_file.write(json.dumps({
            "record_id": row["record_id"],
            "relations": relations,
        }, ensure_ascii=False) + "\n")

    def close(self):
        self.csv_file.close()
        self.jsonl_file.close()
        self.entities_file.close()
        self.relations_file.close()
