#!/usr/bin/env python3
"""
Contact Creation with Dependencies

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

import os
from duplicate_check import find_existing_record
from record_utils import filter_record_data, check_record_exists

def create_contact_with_dependencies(prod_contact_id, created_contacts, contact_insertable_fields_info, sf_cli_source, sf_cli_target, created_accounts):

    # Circular dependency protection
    if not hasattr(create_contact_with_dependencies, 'in_progress'):
        create_contact_with_dependencies.in_progress = set()
    in_progress = create_contact_with_dependencies.in_progress
    if prod_contact_id in in_progress:
        print(f"[CIRCULAR] Contact {prod_contact_id} is already being created. Skipping to break cycle.")
        return None
    if prod_contact_id in created_contacts:
        return created_contacts[prod_contact_id]
    in_progress.add(prod_contact_id)

    print(f"Fetching Contact {prod_contact_id} from source org...")
    prod_contact_record = sf_cli_source.get_record('Contact', prod_contact_id)
    if not prod_contact_record:
        print(f"Could not fetch Contact {prod_contact_id} from source org.")
        return None

    # Step 1: Extract lookup fields and create record WITHOUT lookups
    from populate_sandbox import create_account_with_dependencies, load_insertable_fields
    script_dir = os.path.dirname(os.path.abspath(__file__))
    account_insertable_fields_info = load_insertable_fields('Account', script_dir)

    lookup_fields_to_populate = {}
    for field_name, field_info in list(contact_insertable_fields_info.items()):
        if field_info.get('type') == 'reference':
            ref_id = prod_contact_record.get(field_name)
            if ref_id:
                lookup_fields_to_populate[field_name] = {
                    'ref_id': ref_id,
                    'ref_to': field_info.get('referenceTo')
                }
                # Remove lookup from record data for initial creation
                prod_contact_record.pop(field_name, None)

    # Create the Contact first WITHOUT lookup fields
    filtered_contact_data = filter_record_data(prod_contact_record, contact_insertable_fields_info, sf_cli_target, 'Contact')
    filtered_contact_data.pop('Id', None)
    print(f"Creating Contact in target sandbox (without lookups)")
    new_sandbox_contact_id = sf_cli_target.create_record('Contact', filtered_contact_data)
    if not new_sandbox_contact_id:
        in_progress.remove(prod_contact_id)
        raise RuntimeError(f"Failed to create Contact for {prod_contact_id}")
    print(f"Created Contact {prod_contact_id} (Source) -> {new_sandbox_contact_id} (Sandbox)")
    created_contacts[prod_contact_id] = new_sandbox_contact_id

    # Step 2: Create all dependent records referenced in lookups
    from create_account_with_dependencies import create_account_with_dependencies
    lookup_updates = {}
    for field_name, lookup_info in lookup_fields_to_populate.items():
        ref_id = lookup_info['ref_id']
        ref_to = lookup_info['ref_to']
        
        if ref_to == 'Contact':
            if ref_id in created_contacts:
                lookup_updates[field_name] = created_contacts[ref_id]
            else:
                print(f"Contact {prod_contact_id} has Contact lookup {field_name}={ref_id}. Creating referenced contact.")
                ref_sandbox_id = create_contact_with_dependencies(ref_id, created_contacts, contact_insertable_fields_info, sf_cli_source, sf_cli_target, created_accounts)
                if ref_sandbox_id:
                    lookup_updates[field_name] = ref_sandbox_id
                else:
                    print(f"Warning: Could not create referenced contact {ref_id} for {prod_contact_id} field {field_name}.")
        elif ref_to == 'Account':
            if ref_id in created_accounts:
                lookup_updates[field_name] = created_accounts[ref_id]
            else:
                print(f"Contact {prod_contact_id} has Account lookup {field_name}={ref_id}. Creating referenced account.")
                ref_sandbox_id = create_account_with_dependencies(ref_id, created_accounts, account_insertable_fields_info, created_contacts, contact_insertable_fields_info, sf_cli_source, sf_cli_target)
                if ref_sandbox_id:
                    lookup_updates[field_name] = ref_sandbox_id
                else:
                    print(f"Warning: Could not create referenced account {ref_id} for {prod_contact_id} field {field_name}.")
        elif ref_to == 'User':
            # Check if User exists in sandbox (with caching)
            if check_record_exists(sf_cli_target, 'User', ref_id):
                lookup_updates[field_name] = ref_id
            else:
                print(f"Warning: User {ref_id} referenced in field {field_name} for Contact {prod_contact_id} does not exist in sandbox.")

    # Step 3: Update the Contact with all lookup field values
    if lookup_updates:
        print(f"Updating Contact {new_sandbox_contact_id} with lookup fields: {list(lookup_updates.keys())}")
        sf_cli_target.update_record('Contact', new_sandbox_contact_id, lookup_updates)
    in_progress.remove(prod_contact_id)
    return new_sandbox_contact_id
