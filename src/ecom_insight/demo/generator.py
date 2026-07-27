from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from ecom_insight.demo.domains import generate_domain_tables
from ecom_insight.demo.models import DemoConfig
from ecom_insight.demo.profile import load_reference_profile
from ecom_insight.demo.validation import validate_generated_data


@dataclass(frozen=True, slots=True)
class DemoGenerationResult:
    output_root: Path
    manifest_path: Path
    verification_path: Path
    row_counts: dict[str, int]
    scenario_count: int
    all_scenarios_verified: bool
    reference_profile_used: bool


def _write_json(path: Path, payload: Any, *, pretty: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )
    path.write_text(serialized + "\n", encoding="utf-8")


def _schema_payload() -> dict[str, Any]:
    return {
        "schema_version": "1",
        "data_origin": "fully_synthetic",
        "rate_unit": "decimal_0_to_1",
        "amount_unit": "CNY_yuan",
        "grain": {
            "shop_daily": "date x shop",
            "product_daily": "date x shop x product",
            "channel_daily": "date x shop x channel",
            "search_term_daily": "date x shop x search term",
            "inventory_daily": "snapshot date x shop x product x SKU x warehouse",
            "financial_daily": "date x shop x merchant",
            "anomaly_labels": "controlled injected scenario",
        },
        "join_keys": {
            "shop": ["date", "shop_id"],
            "product_inventory": ["date/snapshot_date", "shop_id", "product_id"],
            "scenario": ["scenario_ids/scenario_id"],
        },
        "important_constraints": [
            "paid_amount approximately equals paid_users x avg_order_value",
            "paid_users <= click_users <= exposure_users",
            "product paid amount sums to shop paid amount",
            "channel paid amount and exposure sum to shop totals",
            "search term totals reconcile to natural search channel totals",
            "settlement_amount = income_total - expense_total + settlement_adjustment",
        ],
    }


class DemoDataGenerator:
    def __init__(
        self,
        config_path: Path,
        output_root: Path,
        reference_database: Path | None = None,
    ) -> None:
        self.config_path = config_path
        self.output_root = output_root
        self.reference_database = reference_database

    def generate(self) -> DemoGenerationResult:
        config = DemoConfig.load(self.config_path)
        profile = load_reference_profile(self.reference_database)
        tables = generate_domain_tables(config, profile)
        verifications = validate_generated_data(config, tables)
        self.output_root.mkdir(parents=True, exist_ok=True)

        for table_name, rows in tables.as_dict().items():
            _write_json(self.output_root / f"{table_name}.json", rows)
        verification_payload = [
            verification.model_dump(mode="json") for verification in verifications
        ]
        verification_path = self.output_root / "scenario_verification.json"
        _write_json(verification_path, verification_payload, pretty=True)
        _write_json(self.output_root / "schema.json", _schema_payload(), pretty=True)

        row_counts = {table_name: len(rows) for table_name, rows in tables.as_dict().items()}
        end_date = config.start_date + timedelta(days=config.days - 1)
        manifest = {
            "schema_version": "1",
            "dataset_version": config.dataset_version,
            "synthetic": True,
            "data_origin": "fully_synthetic",
            "contains_real_records": False,
            "contains_direct_identifiers": False,
            "currency": "CNY",
            "amount_unit": "yuan",
            "rate_unit": "decimal_0_to_1",
            "seed": config.seed,
            "date_range": {
                "start": config.start_date.isoformat(),
                "end": end_date.isoformat(),
                "days": config.days,
            },
            "row_counts": row_counts,
            "scenario_count": len(config.scenarios),
            "scenario_ids": [scenario.scenario_id for scenario in config.scenarios],
            "scenario_verification": {
                "passed": sum(item.passed for item in verifications),
                "failed": sum(not item.passed for item in verifications),
            },
            "reference_profile": {
                "used": profile.reference_used,
                "source": "local_sanitized_phase2_warehouse"
                if profile.reference_used
                else "safe_ecommerce_defaults",
                "usage": "bounded non-identifying rate medians only",
                "fields": list(profile.reference_fields),
                "real_amounts_copied": False,
                "real_entity_ids_copied": False,
            },
            "generation_policy": {
                "bitwise_reproducible_for_same_config_and_reference_profile": True,
                "missing_values_are_not_implicitly_zero_filled": True,
                "cross_domain_totals_are_reconciled": True,
                "controlled_anomalies_have_ground_truth_labels": True,
                "evaluation_must_report_real_and_synthetic_results_separately": True,
            },
        }
        manifest_path = self.output_root / "manifest.json"
        _write_json(manifest_path, manifest, pretty=True)
        return DemoGenerationResult(
            output_root=self.output_root,
            manifest_path=manifest_path,
            verification_path=verification_path,
            row_counts=row_counts,
            scenario_count=len(config.scenarios),
            all_scenarios_verified=all(item.passed for item in verifications),
            reference_profile_used=profile.reference_used,
        )
