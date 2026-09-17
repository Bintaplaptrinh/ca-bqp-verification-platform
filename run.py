from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from pipelines.registry_ingestion.crawler import crawl_source
from pipelines.registry_ingestion.extractors import extract_candidates
from pipelines.registry_ingestion.builder import build_registry, publish_approved
from pipelines.registry_ingestion.coverage import write_coverage
from pipelines.synthetic_data.service import run as run_synthetic
from pipelines.synthetic_data.documents import generate as generate_documents


def _load_raw_pages(source_dir: Path) -> list[dict]:
    """Read back raw pages a previous crawl already saved for one source."""
    if not source_dir.exists():
        return []
    pages = []
    for f in sorted(source_dir.glob("*.json")):
        try:
            pages.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return pages


def main():
    parser = argparse.ArgumentParser(
        description="CA/BQP public-registry + synthetic dataset single-config E2E runner"
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument(
        "--only-source",
        action="append",
        dest="only_sources",
        default=None,
        help=(
            "Crawl only this source_id (repeatable). Raw pages already saved "
            "for other sources are kept and still used in candidate extraction."
        ),
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Ignore previously crawled raw pages and re-crawl every source from scratch.",
    )
    parser.add_argument(
        "--skip-synthetic",
        action="store_true",
        help="Stop after publishing the registry; skip synthetic dataset + document generation.",
    )
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    config = yaml.safe_load(
        (project_root / args.config).read_text(encoding="utf-8")
    )

    registry_cfg = config["registry"]
    raw_root = project_root / config["paths"]["raw_sources"]
    candidates_root = project_root / config["paths"]["extracted_candidates"]
    published_path = project_root / config["paths"]["registry_published"]
    coverage_path = project_root / config["paths"]["coverage_report"]
    synthetic_out = project_root / config["paths"]["synthetic_output"]
    documents_out = project_root / config["paths"]["documents_output"]

    print("[1/6] Crawling official BCA/BQP public sources...")
    all_pages = []
    crawler_failed_sources = []
    only_sources = set(args.only_sources) if args.only_sources else None
    resume = not args.no_resume

    if registry_cfg["crawler"].get("enabled", True):
        for source in registry_cfg.get("sources", []):
            source_id = source["source_id"]
            if only_sources and source_id not in only_sources:
                # Not re-crawling this source this run: reuse whatever raw
                # pages it already has on disk so candidate extraction still
                # sees the full picture, not just the source(s) just crawled.
                pages = _load_raw_pages(raw_root / source_id)
                print(f"      {source_id}: skipped (reusing {len(pages)} saved pages)")
                all_pages.extend(pages)
                continue
            try:
                pages = crawl_source(
                    source,
                    registry_cfg["crawler"],
                    raw_root,
                    resume=resume,
                )
                all_pages.extend(pages)
                print(
                    f"      {source_id}: "
                    f"{len(pages)} fetched pages"
                )
            except Exception as exc:
                crawler_failed_sources.append({
                    "source_id": source_id,
                    "error": str(exc),
                })
                print(
                    f"      WARNING {source_id}: {exc}"
                )

    print("[2/6] Extracting and corroborating unit candidates...")
    candidates = extract_candidates(
        all_pages,
        registry_cfg["extraction"],
    )
    candidates_root.mkdir(parents=True, exist_ok=True)
    with (candidates_root / "candidates.json").open("w", encoding="utf-8") as f:
        json.dump(candidates, f, ensure_ascii=False)
    print(f"      {len(candidates)} raw unit mentions")

    print("[3/6] Merging curated fallback + publishing strict-approved Registry...")
    registry_all = build_registry(
        candidates,
        project_root,
        registry_cfg,
    )
    approved = publish_approved(
        registry_all,
        published_path,
    )
    if approved.empty:
        raise RuntimeError(
            "No APPROVED registry units after crawl/fallback merge."
        )
    print(
        f"      APPROVED={len(approved)} | "
        f"PENDING_QA={len(registry_all)-len(approved)}"
    )

    print("[4/6] Writing coverage report...")
    coverage = write_coverage(
        approved,
        registry_cfg["coverage_targets"],
        coverage_path,
    )

    print("[5/6] Generating synthetic dataset from APPROVED Registry...")
    manifest = None
    if args.skip_synthetic:
        print("      skipped (--skip-synthetic)")
    elif config["synthetic"].get("enabled", True):
        manifest = run_synthetic(
            approved,
            config,
            synthetic_out,
        )

    print("[6/6] Optional document generation...")
    if (
        not args.skip_synthetic
        and config["synthetic"].get("enabled", True)
        and config["documents"].get("enabled", False)
    ):
        generate_documents(
            synthetic_out / "synthetic_records.csv",
            documents_out,
            int(config["documents"]["limit"]),
            int(config["documents"]["batch_size"]),
        )
    else:
        print("      disabled")

    final = {
        "crawler_failed_sources": crawler_failed_sources,
        "crawled_pages": len(all_pages),
        "raw_unit_mentions": len(candidates),
        "registry_candidates": len(registry_all),
        "registry_approved": len(approved),
        "registry_pending_qa": len(registry_all) - len(approved),
        "coverage_report": coverage,
        "synthetic_manifest": manifest,
    }

    print("\nDONE")
    print(json.dumps(final, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
