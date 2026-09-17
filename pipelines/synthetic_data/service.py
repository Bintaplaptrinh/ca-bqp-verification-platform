from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yaml

from .annotations import build_annotations
from .noise import mutate_unit, transform_text, strip_accents
from .policy_engine import evaluate
from .profiles import (
    SURNAMES, MIDDLES, GIVEN, POSITIONS, SUBJECT_GROUPS,
    EMPLOYMENT, TEMPLATES, HISTORY_TEMPLATES,
)
from .writers import Writers


COLUMNS = [
    "record_id","subject_id","full_name","personal_code","birth_year",
    "position","subject_group","employment_status","assessment_date",
    "template_id","input_channel","document_type","requires_ocr",
    "canonical_unit_id","canonical_unit_name","organization_type",
    "noise_type","scenario_type","raw_text","expected_current_unit_id",
    "expected_resolution_status","conflicting_unit_name",
    "synthetic_service_years","synthetic_pay_grade",
    "synthetic_pay_coefficient","synthetic_base_salary_million_vnd",
    "synthetic_allowance_million_vnd","synthetic_total_income_million_vnd",
    "salary_status","eligibility_status","policy_id","policy_version",
    "policy_reason_code","taxonomy_version","source_kind","split",
    "registry_version",
]


def _weighted_choice(rng, weights: dict):
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def _name(rng):
    return f"{rng.choice(SURNAMES)} {rng.choice(MIDDLES)} {rng.choice(GIVEN)}"


def _assessment_date(rng):
    start = date(2025,1,1)
    end = date(2026,12,31)
    return (start + timedelta(days=rng.randint(0,(end-start).days))).isoformat()


def _unit_splits(units, cfg):
    ids = [u["unit_id"] for u in units]
    rng = random.Random(cfg["seed"] + 991)
    rng.shuffle(ids)
    train_n = int(len(ids) * cfg["split"]["train"])
    val_n = int(len(ids) * cfg["split"]["val"])
    result = {}
    for i, unit_id in enumerate(ids):
        result[unit_id] = "train" if i < train_n else ("val" if i < train_n + val_n else "test")
    return result


def _transform_mentions(name, code, position, current, former, noise_type):
    if noise_type == "NO_ACCENT":
        fn = strip_accents
        return fn(name), fn(code), fn(position), fn(current), fn(former) if former else None
    if noise_type == "LOWERCASE":
        return name.lower(), code.lower(), position.lower(), current.lower(), former.lower() if former else None
    if noise_type == "OCR_LIKE":
        fn = lambda x: strip_accents(x).replace("rn","m").replace("cl","d")
        return fn(name), fn(code), fn(position), fn(current), fn(former) if former else None
    return name, code, position, current, former


def _salary(rng, org, status):
    years = rng.randint(0,35)
    grade = rng.choice(["G1","G2","G3","G4","G5"])
    coeff = round(rng.uniform(1.5,8.0),2)
    if status != "APPLICABLE":
        return years, grade, coeff, "", "", ""
    base = rng.uniform(8,34) if org in {"BCA","BQP"} else rng.uniform(6,28)
    allowance = rng.uniform(0,10) if org in {"BCA","BQP"} else rng.uniform(0,5)
    return years, grade, coeff, round(base,2), round(allowance,2), round(base+allowance,2)


def generate_main_dataset(registry: pd.DataFrame, config: dict, out_dir: Path):
    cfg = config["synthetic"]
    policy_cfg = config["policy"]
    rng = random.Random(cfg["seed"])
    units = registry.to_dict("records")
    split_of = _unit_splits(units, cfg)

    pools = defaultdict(list)
    for u in units:
        pools[split_of[u["unit_id"]]].append(u)

    counters = Counter()
    idx = 1
    writer = Writers(out_dir, COLUMNS)

    for unit in units:
        split = split_of[unit["unit_id"]]
        pool = pools[split]
        candidates = [x for x in pool if x["unit_id"] != unit["unit_id"]] or [unit]

        for local_idx in range(cfg["records_per_unit"]):
            history = (local_idx / cfg["records_per_unit"]) < cfg["history_ratio"]
            scenario = "MULTI_ORG_HISTORY" if history else "MATCHED"
            former = rng.choice(candidates)

            name = _name(rng)
            code = f"SYN-{unit['organization_type']}-{idx:08d}"
            position = rng.choice(POSITIONS[unit["organization_type"]])
            group = rng.choice(SUBJECT_GROUPS[unit["organization_type"]])
            employment = rng.choice(EMPLOYMENT)
            assessment_date = _assessment_date(rng)
            noise_type = _weighted_choice(rng, cfg["noise_weights"])
            unit_input = mutate_unit(unit["canonical_name"], noise_type, rng)
            doc_type = _weighted_choice(rng, cfg["document_type_weights"])
            requires_ocr = doc_type in {"PDF_SCAN","IMAGE"}

            template_id, template = rng.choice(HISTORY_TEMPLATES if history else TEMPLATES)
            text = template.format(
                name=name, code=code, unit=unit_input,
                position=position, former=former["canonical_name"],
            )
            text = transform_text(text, noise_type)

            person_m, code_m, position_m, current_m, former_m = _transform_mentions(
                name, code, position, unit_input,
                former["canonical_name"] if history else None,
                noise_type,
            )
            if noise_type in {"TYPO_UNIT","ABBREVIATION"}:
                current_m = unit_input

            entities, relations = build_annotations(
                text, person_m, code_m, position_m, current_m, former_m
            )

            facts = {
                "organization_type": unit["organization_type"],
                "subject_group": group,
                "employment_status": employment,
                "assessment_date": assessment_date,
            }
            decision = evaluate(facts, policy_cfg)
            years, grade, coeff, base, allowance, total = _salary(
                rng, unit["organization_type"], decision["salary_status"]
            )

            row = {
                "record_id": f"REC-{idx:08d}",
                "subject_id": f"SUB-{idx:08d}",
                "full_name": name,
                "personal_code": code,
                "birth_year": rng.randint(1965,2005),
                "position": position,
                "subject_group": group,
                "employment_status": employment,
                "assessment_date": assessment_date,
                "template_id": template_id,
                "input_channel": "STRUCTURED" if doc_type == "XLSX_ROW" else "UNSTRUCTURED",
                "document_type": doc_type,
                "requires_ocr": requires_ocr,
                "canonical_unit_id": unit["unit_id"],
                "canonical_unit_name": unit["canonical_name"],
                "organization_type": unit["organization_type"],
                "noise_type": noise_type,
                "scenario_type": scenario,
                "raw_text": text,
                "expected_current_unit_id": unit["unit_id"],
                "expected_resolution_status": "MATCHED",
                "conflicting_unit_name": "",
                "synthetic_service_years": years,
                "synthetic_pay_grade": grade,
                "synthetic_pay_coefficient": coeff,
                "synthetic_base_salary_million_vnd": base,
                "synthetic_allowance_million_vnd": allowance,
                "synthetic_total_income_million_vnd": total,
                "salary_status": decision["salary_status"],
                "eligibility_status": decision["eligibility_status"],
                "policy_id": decision["policy_id"],
                "policy_version": policy_cfg["snapshot_version"],
                "policy_reason_code": decision["policy_reason_code"],
                "taxonomy_version": policy_cfg["taxonomy_version"],
                "source_kind": "SYNTHETIC_DEMO",
                "split": split,
                "registry_version": unit["registry_version"],
            }
            writer.write(row, entities, relations)
            counters[unit["organization_type"]] += 1
            counters[scenario] += 1
            idx += 1

    writer.close()
    return counters


def generate_hard_cases(registry: pd.DataFrame, config: dict, out_dir: Path):
    hard_cfg = config["synthetic"]["hard_cases"]
    if not hard_cfg.get("enabled", True):
        return {}

    rng = random.Random(config["synthetic"]["seed"] + 7001)
    units = registry.to_dict("records")
    out_path = out_dir / "hard_cases.jsonl"
    counts = Counter()

    with out_path.open("w", encoding="utf-8") as f:
        idx = 1
        for scenario in hard_cfg["types"]:
            for _ in range(hard_cfg["records_per_type"]):
                unit = rng.choice(units)
                name = _name(rng)
                code = f"HARD-{idx:08d}"
                if scenario == "UNKNOWN":
                    raw_unit = f"Đơn vị Chưa Có Trong Registry {idx:06d}"
                    text = f"{name}, mã {code}, hiện công tác tại {raw_unit}."
                    status = "NOT_FOUND"
                elif scenario == "AMBIGUOUS":
                    raw_unit = "Trung tâm Nghiệp vụ"
                    text = f"{name}, mã {code}, hiện công tác tại {raw_unit}."
                    status = "AMBIGUOUS"
                else:
                    other_org = "BQP" if unit["organization_type"] == "BCA" else "BCA"
                    other = rng.choice([x for x in units if x["organization_type"] == other_org])
                    raw_unit = unit["canonical_name"]
                    text = (
                        f"{name}, mã {code}, hiện công tác tại {raw_unit}. "
                        f"Nguồn khác lại ghi {other['canonical_name']}."
                    )
                    status = "CONFLICT"

                row = {
                    "hard_case_id": f"HARD-{idx:08d}",
                    "scenario_type": scenario,
                    "raw_text": text,
                    "unit_name_raw": raw_unit,
                    "organization_type": "UNKNOWN",
                    "expected_resolution_status": status,
                    "source_kind": "SYNTHETIC_DEMO",
                }
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
                counts[scenario] += 1
                idx += 1
    return counts


def internal_quality_gate(out_dir: Path, config: dict):
    df = pd.read_csv(out_dir / "synthetic_records.csv", dtype=str).fillna("")

    if config["quality"].get("fail_on_duplicate_record_id", True):
        if df["record_id"].duplicated().any():
            raise ValueError("Quality gate failed: duplicate record_id")

    if config["quality"].get("fail_on_unit_split_leakage", True):
        n = df.groupby("canonical_unit_id")["split"].nunique()
        if (n > 1).any():
            raise ValueError("Quality gate failed: canonical unit split leakage")

    if config["quality"].get("fail_on_not_found_as_other", True):
        bad = df[
            df["expected_resolution_status"].eq("NOT_FOUND")
            & df["organization_type"].eq("OTHER")
        ]
        if not bad.empty:
            raise ValueError("Quality gate failed: NOT_FOUND mapped to OTHER")


def write_policy_snapshot(config: dict, out_dir: Path):
    policy = {
        "policy_snapshot_version": config["policy"]["snapshot_version"],
        "taxonomy_version": config["policy"]["taxonomy_version"],
        "effective_from": config["policy"]["effective_from"],
        "effective_to": config["policy"]["effective_to"],
        "source_kind": "SYNTHETIC_DEMO",
        "warning": "Demo policy only; not real salary/benefit entitlement rules.",
    }
    (out_dir / "synthetic_policy_rules.yaml").write_text(
        yaml.safe_dump(policy, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def run(registry: pd.DataFrame, config: dict, out_dir: Path):
    if out_dir.exists():
        import shutil
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    main_counts = generate_main_dataset(registry, config, out_dir)
    hard_counts = generate_hard_cases(registry, config, out_dir)
    write_policy_snapshot(config, out_dir)
    internal_quality_gate(out_dir, config)

    records = len(registry) * config["synthetic"]["records_per_unit"]
    manifest = {
        "dataset_version": config["project"]["version"],
        "registry_version": config["registry"].get(
            "expected_registry_version",
            config["registry"].get("publish_version_prefix", "2026.09-auto"),
        ),
        "registry_units": len(registry),
        "main_records": records,
        "main_counts": dict(main_counts),
        "hard_case_counts": dict(hard_counts),
        "records_per_unit": config["synthetic"]["records_per_unit"],
        "seed": config["synthetic"]["seed"],
        "source_boundary": {
            "registry": "APPROVED organizational data",
            "person_and_business_data": "SYNTHETIC_DEMO",
        },
        "artifacts": [
            "synthetic_records.csv",
            "synthetic_records.jsonl",
            "extraction_annotations.jsonl",
            "relation_annotations.jsonl",
            "hard_cases.jsonl",
            "synthetic_policy_rules.yaml",
            "dataset_manifest.json",
        ],
    }
    (out_dir / "dataset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return manifest
