#!/usr/bin/env python3
"""
Bulk Account Creation - Phase 1

Author: Ken Brill
Version: 1.2.0
Date: January 2026
License: MIT License

Phase 1 bulk account creation using topological sorting and wave-based
bulk API operations. Significantly faster than one-at-a-time creation.
"""
import csv
import json
import logging
import subprocess
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Any, Tuple
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from sandcastle_pkg.utils.record_utils import filter_record_data, replace_lookups_with_dummies
from sandcastle_pkg.utils.csv_utils import write_record_to_csv

console = Console()
logger = logging.getLogger(__name__)


def build_account_dependency_graph(
    all_accounts: Dict[str, Dict],
    account_fields: Dict[str, Dict]
) -> Tuple[Dict[str, Set[str]], Set[str]]:
    """
    Build a dependency graph for accounts based on Account lookup fields.

    Args:
        all_accounts: Dict mapping account ID to record data
        account_fields: Field metadata for Account object

    Returns:
        Tuple of (dependencies dict, account_lookup_field_names set)
        - dependencies: {account_id: set of account_ids this account depends on}
        - account_lookup_fields: set of field names that are Account lookups
    """
    # Find all Account lookup fields
    account_lookup_fields = set()
    for field_name, field_info in account_fields.items():
        if field_info.get('type') in ['reference', 'hierarchy'] and field_info.get('referenceTo') == 'Account':
            account_lookup_fields.add(field_name)

    # Build dependency graph
    dependencies = {}
    for account_id, record in all_accounts.items():
        deps = set()
        for field_name in account_lookup_fields:
            ref_id = record.get(field_name)
            if ref_id and not isinstance(ref_id, dict):
                # Only add as dependency if the referenced account is in our set
                if ref_id in all_accounts and ref_id != account_id:
                    deps.add(ref_id)
        dependencies[account_id] = deps

    return dependencies, account_lookup_fields


def topological_sort_accounts(dependencies: Dict[str, Set[str]]) -> List[List[str]]:
    """
    Perform topological sort on accounts, grouping them into waves.
    Wave 0: accounts with no dependencies
    Wave 1: accounts depending only on Wave 0
    etc.

    Args:
        dependencies: {account_id: set of account_ids this account depends on}

    Returns:
        List of waves, where each wave is a list of account IDs that can be created together
    """
    waves = []
    remaining = dict(dependencies)  # Copy so we don't modify original
    created = set()

    while remaining:
        # Find all accounts whose dependencies have been satisfied
        ready = []
        for account_id, deps in remaining.items():
            unsatisfied = deps - created
            if not unsatisfied:
                ready.append(account_id)

        if not ready:
            # Circular dependency detected - break it by taking accounts with fewest dependencies
            min_deps = min(len(deps - created) for deps in remaining.values())
            ready = [aid for aid, deps in remaining.items() if len(deps - created) == min_deps]
            logger.warning(f"Circular dependency detected, breaking cycle with {len(ready)} account(s)")

        # Add this wave
        waves.append(ready)

        # Remove from remaining and mark as created
        for account_id in ready:
            del remaining[account_id]
            created.add(account_id)

    return waves


def prepare_account_for_bulk(
    record: Dict,
    account_fields: Dict,
    created_accounts: Dict[str, str],
    dummy_records: Dict,
    sf_cli_source,
    sf_cli_target,
    account_lookup_fields: Set[str]
) -> Tuple[Dict, Dict]:
    """
    Prepare a single account record for bulk creation.

    Args:
        record: Original production account record
        account_fields: Field metadata
        created_accounts: Mapping of prod_id -> sandbox_id for already created accounts
        dummy_records: Dictionary of dummy record IDs
        sf_cli_source: Source org CLI
        sf_cli_target: Target org CLI
        account_lookup_fields: Set of field names that are Account lookups

    Returns:
        Tuple of (prepared record for creation, original record for CSV)
    """
    original_record = record.copy()

    # Replace lookups with dummies/mappings
    created_mappings = {'Account': created_accounts}
    record_with_dummies = replace_lookups_with_dummies(
        record,
        account_fields,
        dummy_records,
        created_mappings,
        sf_cli_source,
        sf_cli_target,
        'Account'
    )

    # Filter to insertable fields and validate picklists
    filtered_data = filter_record_data(
        record_with_dummies,
        account_fields,
        sf_cli_target,
        'Account'
    )
    filtered_data.pop('Id', None)  # Remove production Id

    return filtered_data, original_record


def bulk_create_accounts_wave(
    sf_cli_target,
    sobject: str,
    records: List[Dict[str, Any]],
    prod_ids: List[str]
) -> Dict[str, str]:
    """
    Create accounts in bulk using Bulk API 2.0.

    Args:
        sf_cli_target: Target org CLI
        sobject: Object type ('Account')
        records: List of prepared record data
        prod_ids: Corresponding production IDs (same order as records)

    Returns:
        Dict mapping production IDs to sandbox IDs for successfully created records
    """
    if not records:
        return {}

    # Create temp directory for CSV
    temp_dir = Path(__file__).parent.parent / 'utils' / 'tmp_bulk'
    temp_dir.mkdir(exist_ok=True)

    # Get all unique field names
    all_fields = set()
    for record in records:
        all_fields.update(record.keys())

    field_list = sorted(all_fields)

    # Sanitize records: remove embedded newlines
    sanitized_records = []
    for record in records:
        sanitized = {}
        for key, value in record.items():
            if isinstance(value, str):
                sanitized[key] = value.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
            elif value is None:
                sanitized[key] = ''
            else:
                sanitized[key] = value
        sanitized_records.append(sanitized)

    # Write CSV
    csv_file = temp_dir / f'bulk_create_{sobject}_{len(records)}.csv'
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=field_list)
        writer.writeheader()
        writer.writerows(sanitized_records)

    # Convert to CRLF (Salesforce requirement)
    with open(csv_file, 'rb') as f:
        content = f.read()
    content = content.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
    with open(csv_file, 'wb') as f:
        f.write(content)

    # Execute bulk import
    logs_dir = Path(__file__).parent.parent / 'utils' / 'logs'
    logs_dir.mkdir(exist_ok=True)

    command = [
        'sf', 'data', 'import', 'bulk',
        '--sobject', sobject,
        '--file', str(csv_file),
        '--line-ending', 'CRLF',
        '--target-org', sf_cli_target.target_org,
        '--wait', '10',
        '--json'
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
            cwd=str(logs_dir)
        )
    except subprocess.TimeoutExpired:
        logger.error("Bulk create timed out after 10 minutes")
        csv_file.unlink(missing_ok=True)
        return {}

    # Parse response and get created IDs
    created_mapping = {}

    if result.returncode == 0:
        try:
            response = json.loads(result.stdout)
            if response.get('status') == 0:
                result_data = response.get('result', {})

                # Read success file to get created IDs
                success_file = result_data.get('successFilePath')
                if success_file and Path(success_file).exists():
                    with open(success_file, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for idx, row in enumerate(reader):
                            sf_id = row.get('sf__Id') or row.get('Id')
                            if sf_id and idx < len(prod_ids):
                                created_mapping[prod_ids[idx]] = sf_id

                job_info = result_data.get('jobInfo', {})
                num_processed = job_info.get('numberRecordsProcessed', len(created_mapping))
                num_failed = job_info.get('numberRecordsFailed', 0)

                if num_failed > 0:
                    # Log failures
                    failed_file = result_data.get('failedFilePath')
                    if failed_file and Path(failed_file).exists():
                        with open(failed_file, 'r', encoding='utf-8') as f:
                            reader = csv.DictReader(f)
                            for row in reader:
                                error = row.get('sf__Error', 'Unknown error')
                                logger.warning(f"Bulk create failed for record: {error}")

                logger.info(f"Bulk created {len(created_mapping)}/{len(records)} {sobject} records")
        except json.JSONDecodeError:
            logger.warning("Could not parse bulk create response")
    else:
        # Handle failure - try to get partial results
        error_msg = result.stderr or result.stdout
        logger.warning(f"Bulk create returned non-zero: {error_msg[:500]}")

        try:
            response = json.loads(result.stdout) if result.stdout else {}
            job_id = response.get('data', {}).get('jobId') or response.get('result', {}).get('jobInfo', {}).get('id')

            if job_id:
                # Try to get results from the job
                results_cmd = [
                    'sf', 'data', 'bulk', 'results',
                    '--job-id', job_id,
                    '--target-org', sf_cli_target.target_org,
                    '--json'
                ]
                results_run = subprocess.run(results_cmd, capture_output=True, text=True, timeout=60, check=False)

                if results_run.returncode == 0:
                    results_response = json.loads(results_run.stdout)
                    if results_response.get('status') == 0:
                        result_data = results_response.get('result', {})
                        success_file = result_data.get('successFilePath')

                        if success_file and Path(success_file).exists():
                            with open(success_file, 'r', encoding='utf-8') as f:
                                reader = csv.DictReader(f)
                                for idx, row in enumerate(reader):
                                    sf_id = row.get('sf__Id') or row.get('Id')
                                    if sf_id and idx < len(prod_ids):
                                        created_mapping[prod_ids[idx]] = sf_id

                            logger.info(f"Retrieved {len(created_mapping)} successful IDs from partial results")
        except Exception as e:
            logger.warning(f"Could not retrieve partial results: {e}")

    # Clean up temp file
    csv_file.unlink(missing_ok=True)

    return created_mapping


def create_accounts_bulk_phase1(
    config: Dict,
    account_fields: Dict,
    sf_cli_source,
    sf_cli_target,
    dummy_records: Dict,
    script_dir: Path,
    batch_size: int = 200
) -> Dict[str, str]:
    """
    Phase 1: Create all accounts using bulk API with topological sorting.

    This is significantly faster than one-at-a-time creation while still
    handling account-to-account dependencies correctly.

    Args:
        config: Configuration dictionary
        account_fields: Field metadata for Account
        sf_cli_source: Source org CLI
        sf_cli_target: Target org CLI
        dummy_records: Dictionary of dummy record IDs
        script_dir: Script directory for CSV storage
        batch_size: Number of records per bulk batch (default 200)

    Returns:
        Dictionary mapping production Account IDs to sandbox IDs
    """
    created_accounts = {}

    console.print()
    logging.info("\n--- Phase 1: Accounts (Bulk Creation) ---")

    # Step 1: Fetch all accounts
    root_account_ids = list(config["Accounts"])

    if len(root_account_ids) > 50:
        logging.warning(f"  Warning: {len(root_account_ids)} root accounts may cause slow queries")

    ids_str = "','".join(root_account_ids)

    # Build field list
    field_names = [name for name in account_fields.keys() if name not in ['Id']]
    fields_str = 'Id, ' + ', '.join(field_names) if field_names else 'Id'

    # Find Account lookup fields for WHERE clause
    account_lookup_fields = []
    for field_name, field_info in account_fields.items():
        if field_info.get('type') in ['reference', 'hierarchy'] and field_info.get('referenceTo') == 'Account':
            account_lookup_fields.append(field_name)

    # Build query
    where_conditions = [f"Id IN ('{ids_str}')"]
    for field_name in account_lookup_fields:
        where_conditions.append(f"{field_name} IN ('{ids_str}')")
    where_clause = " OR ".join(where_conditions)

    locations_limit = config.get("locations_limit", 10)
    if locations_limit == -1:
        limit_clause = ""
    else:
        calculated_limit = min(locations_limit * len(root_account_ids) * 10, 10000)
        limit_clause = f" LIMIT {calculated_limit}"

    logging.info(f"  Found {len(account_lookup_fields)} Account lookup/hierarchy field(s)")
    logging.info(f"  Querying all accounts related to {len(root_account_ids)} root account(s)")

    query = f"""SELECT {fields_str} FROM Account WHERE {where_clause} {limit_clause}"""

    all_account_records = {}
    batch_records = sf_cli_source.query_records(query) or []
    for record in batch_records:
        all_account_records[record['Id']] = record

    total_accounts = len(all_account_records)
    logging.info(f"  Fetched {total_accounts} account record(s) in one query")

    if total_accounts == 0:
        return created_accounts

    # Step 2: Build dependency graph and sort into waves
    console.print(f"  [cyan]Building dependency graph...[/cyan]")
    dependencies, lookup_fields = build_account_dependency_graph(all_account_records, account_fields)

    console.print(f"  [cyan]Sorting accounts by dependencies...[/cyan]")
    waves = topological_sort_accounts(dependencies)

    logging.info(f"  Sorted {total_accounts} accounts into {len(waves)} wave(s)")
    for i, wave in enumerate(waves):
        logging.info(f"    Wave {i+1}: {len(wave)} account(s)")

    # Step 3: Process each wave
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        overall_task = progress.add_task(f"[cyan]Creating {total_accounts} accounts in {len(waves)} waves", total=total_accounts)

        for wave_num, wave in enumerate(waves, 1):
            wave_desc = f"Wave {wave_num}/{len(waves)}: {len(wave)} accounts"
            progress.update(overall_task, description=f"[cyan]{wave_desc}")

            # Process wave in batches
            for batch_start in range(0, len(wave), batch_size):
                batch = wave[batch_start:batch_start + batch_size]

                # Prepare records for this batch
                prepared_records = []
                original_records = {}
                prod_ids = []

                for prod_account_id in batch:
                    record = all_account_records[prod_account_id]

                    try:
                        prepared, original = prepare_account_for_bulk(
                            record,
                            account_fields,
                            created_accounts,
                            dummy_records,
                            sf_cli_source,
                            sf_cli_target,
                            lookup_fields
                        )

                        prepared_records.append(prepared)
                        original_records[prod_account_id] = original
                        prod_ids.append(prod_account_id)
                    except Exception as e:
                        logger.warning(f"Failed to prepare account {prod_account_id}: {e}")

                if not prepared_records:
                    continue

                # Bulk create this batch
                batch_results = bulk_create_accounts_wave(
                    sf_cli_target,
                    'Account',
                    prepared_records,
                    prod_ids
                )

                # Update mappings and write CSVs
                for prod_id, sandbox_id in batch_results.items():
                    created_accounts[prod_id] = sandbox_id

                    # Write to CSV for Phase 2
                    if prod_id in original_records:
                        write_record_to_csv('Account', prod_id, sandbox_id, original_records[prod_id], script_dir)

                progress.advance(overall_task, len(batch))

                # Log batch results
                success_count = len(batch_results)
                fail_count = len(batch) - success_count
                if fail_count > 0:
                    logger.warning(f"  Batch: {success_count} created, {fail_count} failed")

    # Summary
    console.print()
    console.print(f"[green]Bulk created {len(created_accounts)}/{total_accounts} Account record(s)[/green]")

    return created_accounts
