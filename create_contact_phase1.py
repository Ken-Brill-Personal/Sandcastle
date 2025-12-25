#!/usr/bin/env python3
"""
Contact Creation - Phase 1

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License

Phase 1: Creates Contact with dummy lookups.
No dependency resolution - just create and save to CSV.
"""
from rich.console import Console
from record_utils import filter_record_data, replace_lookups_with_dummies
from csv_utils import write_record_to_csv

console = Console()


def create_contact_phase1(prod_contact_id, created_contacts, contact_insertable_fields_info,
                         sf_cli_source, sf_cli_target, dummy_records, script_dir, created_accounts=None):
    """
    Phase 1: Create Contact with dummy AccountId, save to CSV for Phase 2 update.
    
    Args:
        prod_contact_id: Production Contact ID
        created_contacts: Dictionary mapping prod_id -> sandbox_id
        contact_insertable_fields_info: Field metadata
        sf_cli_source: Source org CLI
        sf_cli_target: Target org CLI
        dummy_records: Dictionary of dummy record IDs by object type
        script_dir: Script directory for CSV storage
        
    Returns:
        str: Sandbox Contact ID or None
    """
    # Skip if already created
    if prod_contact_id in created_contacts:
        console.print(f"  [dim]Contact {prod_contact_id} already created as {created_contacts[prod_contact_id]}[/dim]")
        return created_contacts[prod_contact_id]
    
    console.rule(f"[bold cyan][PHASE 1] Creating Contact {prod_contact_id}")
    
    # Fetch from source
    prod_contact_record = sf_cli_source.get_record('Contact', prod_contact_id)
    if not prod_contact_record:
        console.print(f"  [red]✗ Could not fetch Contact {prod_contact_id} from source org[/red]")
        return None
    
    # Save original record for CSV
    original_record = prod_contact_record.copy()
    
    # Replace lookups with dummy IDs (especially AccountId)
    record_with_dummies = replace_lookups_with_dummies(
        prod_contact_record,
        contact_insertable_fields_info,
        dummy_records,
        None,
        sf_cli_source,
        sf_cli_target,
        'Contact'
    )
    
    # Filter to insertable fields and validate picklists
    filtered_data = filter_record_data(
        record_with_dummies,
        contact_insertable_fields_info,
        sf_cli_target,
        'Contact'
    )
    filtered_data.pop('Id', None)
    
    # Create in sandbox
    try:
        sandbox_contact_id = sf_cli_target.create_record('Contact', filtered_data)
        if sandbox_contact_id:
            console.print(f"  [green]✓ Created Contact: {prod_contact_id} → {sandbox_contact_id}[/green]")
            created_contacts[prod_contact_id] = sandbox_contact_id
            
            # Save to CSV for Phase 2
            write_record_to_csv('Contact', prod_contact_id, sandbox_contact_id, original_record, script_dir)
            
            return sandbox_contact_id
        else:
            console.print(f"  [red]✗ Failed to create Contact {prod_contact_id}[/red]")
            return None
            
    except Exception as e:
        error_msg = str(e)
        console.print(f"  [red]✗ Error creating Contact {prod_contact_id}: {error_msg}[/red]")
        
        # Check for duplicate
        if "duplicate value found" in error_msg and "with id:" in error_msg:
            import re
            match = re.search(r'with id:\s*([a-zA-Z0-9]{15,18})', error_msg)
            if match:
                existing_id = match.group(1)
                console.print(f"  [blue]ℹ Found existing Contact {existing_id}, using it[/blue]")
                created_contacts[prod_contact_id] = existing_id
                
                # Save to CSV for Phase 2
                write_record_to_csv('Contact', prod_contact_id, existing_id, original_record, script_dir)
                
                return existing_id
        
        return None
