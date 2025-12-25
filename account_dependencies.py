#!/usr/bin/env python3
"""
Account Dependencies Discovery

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

from duplicate_check import find_existing_record
from record_utils import filter_record_data
def create_account_with_dependencies(prod_account_id, created_accounts, account_insertable_fields_info, created_contacts, contact_insertable_fields_info, sf_cli_source, sf_cli_target):

    # Circular dependency protection
    if not hasattr(create_account_with_dependencies, 'in_progress'):
        create_account_with_dependencies.in_progress = set()
    in_progress = create_account_with_dependencies.in_progress
    if prod_account_id in in_progress:
        print(f"[CIRCULAR] Account {prod_account_id} is already being created. Skipping to break cycle.")
        return None
    if prod_account_id in created_accounts:
        return created_accounts[prod_account_id]
    in_progress.add(prod_account_id)

    # Track contacts that need AccountId update after account creation
    if not hasattr(create_account_with_dependencies, 'contacts_to_update'):
        create_account_with_dependencies.contacts_to_update = []
    contacts_to_update = create_account_with_dependencies.contacts_to_update

    print(f"Fetching Account {prod_account_id} from source org...")
    prod_account_record = sf_cli_source.get_record('Account', prod_account_id)
    if not prod_account_record:
        print(f"Could not fetch Account {prod_account_id} from source org.")
        return None

    # Check for duplicate in sandbox using generic function
    existing_id = find_existing_record(sf_cli_target, 'Account', ['Name'], prod_account_record)
    if existing_id:
        print(f"Account with Name '{prod_account_record.get('Name')}' already exists in sandbox as {existing_id}. Skipping creation.")
        created_accounts[prod_account_id] = existing_id
        return existing_id

    # Recursively create all Account and Contact lookup dependencies first
    from create_contact_with_dependencies import create_contact_with_dependencies
    for field_name, field_info in account_insertable_fields_info.items():
        if field_info.get('type') == 'reference':
            ref_id = prod_account_record.get(field_name)
            if not ref_id:
                continue
            if field_info.get('referenceTo') == 'Account':
                if ref_id in created_accounts:
                    prod_account_record[field_name] = created_accounts[ref_id]
                else:
                    print(f"Account {prod_account_id} has Account lookup {field_name}={ref_id}. Ensuring referenced account is created first.")
                    ref_sandbox_id = create_account_with_dependencies(ref_id, created_accounts, account_insertable_fields_info, created_contacts, contact_insertable_fields_info, sf_cli_source, sf_cli_target)
                    if ref_sandbox_id:
                        prod_account_record[field_name] = ref_sandbox_id
                    else:
                        print(f"Warning: Could not create referenced account {ref_id} for {prod_account_id} field {field_name}.")
            elif field_info.get('referenceTo') == 'Contact':
                if ref_id in created_contacts:
                    prod_account_record[field_name] = created_contacts[ref_id]
                else:
                    print(f"Account {prod_account_id} has Contact lookup {field_name}={ref_id}. Ensuring referenced contact is created first.")
                    ref_sandbox_id = create_contact_with_dependencies(ref_id, created_contacts, contact_insertable_fields_info, sf_cli_source, sf_cli_target)
                    if ref_sandbox_id:
                        prod_account_record[field_name] = ref_sandbox_id
                        # If this contact was created before this account, schedule update after account creation
                        contacts_to_update.append({'contact_id': ref_id, 'account_field': 'AccountId', 'account_prod_id': prod_account_id})
                    else:
                        print(f"Warning: Could not create referenced contact {ref_id} for {prod_account_id} field {field_name}.")

    filtered_account_data = filter_record_data(prod_account_record, account_insertable_fields_info, sf_cli_target, 'Account')
    filtered_account_data.pop('Id', None)
    print(f"Creating Account in target sandbox")
    new_sandbox_account_id = sf_cli_target.create_record('Account', filtered_account_data)
    if new_sandbox_account_id:
        print(f"Created Account {prod_account_id} (Source) -> {new_sandbox_account_id} (Sandbox)")
        created_accounts[prod_account_id] = new_sandbox_account_id
        # Update any contacts that referenced this account
        for update in [u for u in contacts_to_update if u['account_prod_id'] == prod_account_id]:
            contact_sandbox_id = created_contacts.get(update['contact_id'])
            if contact_sandbox_id:
                print(f"Updating Contact {update['contact_id']} in sandbox to set {update['account_field']}={new_sandbox_account_id}")
                sf_cli_target.update_record('Contact', contact_sandbox_id, {update['account_field']: new_sandbox_account_id})
        # Remove processed updates
        create_account_with_dependencies.contacts_to_update = [u for u in contacts_to_update if u['account_prod_id'] != prod_account_id]
        in_progress.remove(prod_account_id)
        return new_sandbox_account_id
    else:
        print(f"Failed to create Account for {prod_account_id}")
        in_progress.remove(prod_account_id)
        return None
