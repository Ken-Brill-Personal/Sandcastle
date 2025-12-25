#!/usr/bin/env python3
"""
Account Creation with Dependencies

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

from duplicate_check import find_existing_record
from record_utils import filter_record_data, check_record_exists

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
        in_progress.remove(prod_account_id)
        return None

    # Step 1: Extract lookup fields and create record WITHOUT lookups
    lookup_fields_to_populate = {}
    for field_name, field_info in list(account_insertable_fields_info.items()):
        if field_info.get('type') == 'reference':
            ref_id = prod_account_record.get(field_name)
            if ref_id:
                lookup_fields_to_populate[field_name] = {
                    'ref_id': ref_id,
                    'ref_to': field_info.get('referenceTo')
                }
                # Remove lookup from record data for initial creation
                prod_account_record.pop(field_name, None)

    # TEMPORARY FIX: Remove Product_Types_Quoted__c if it contains "Unknown" value
    if 'Product_Types_Quoted__c' in prod_account_record:
        value = prod_account_record['Product_Types_Quoted__c']
        if value and isinstance(value, str) and 'Unknown' in value:
            print(f"[TEMP FIX] Removing Product_Types_Quoted__c field due to invalid 'Unknown' value")
            prod_account_record.pop('Product_Types_Quoted__c', None)
    
    # Create the Account first WITHOUT lookup fields
    if 'Product_Types_Quoted__c' in prod_account_record:
        print(f"[DEBUG PRE-FILTER] Product_Types_Quoted__c value: '{prod_account_record['Product_Types_Quoted__c']}'")
    else:
        print(f"[DEBUG PRE-FILTER] Product_Types_Quoted__c NOT in record")
    filtered_account_data = filter_record_data(prod_account_record, account_insertable_fields_info, sf_cli_target, 'Account')
    if 'Product_Types_Quoted__c' in filtered_account_data:
        print(f"[DEBUG POST-FILTER] Product_Types_Quoted__c value: '{filtered_account_data['Product_Types_Quoted__c']}'")
    else:
        print(f"[DEBUG POST-FILTER] Product_Types_Quoted__c NOT in filtered data")
    filtered_account_data.pop('Id', None)
    
    print(f"Creating Account in target sandbox (without lookups)")
    try:
        new_sandbox_account_id = sf_cli_target.create_record('Account', filtered_account_data)
    except Exception as create_error:
        # Handle creation errors (flows, validation rules, permissions, etc.)
        print(f"Warning: Account creation failed with error: {str(create_error)}")
        new_sandbox_account_id = None
    
    if not new_sandbox_account_id:
        # Check if this was a duplicate error or flow error - try to find the existing record
        # The error message often contains "duplicate value found... with id: 001xxxxx"
        in_progress.remove(prod_account_id)
        
        # Try to find existing account by name as fallback
        account_name = prod_account_record.get('Name', '').replace("'", "\\'")
        name_query = f"SELECT Id FROM Account WHERE Name = '{account_name}' LIMIT 1"
        existing_by_name = sf_cli_target.query_records(name_query)
        if existing_by_name and len(existing_by_name) > 0:
            existing_id = existing_by_name[0]['Id']
            print(f"Account {prod_account_id} appears to already exist in sandbox as {existing_id} (found by Name). Using existing record.")
            created_accounts[prod_account_id] = existing_id
            
            # Try to update it with Source_Id__c for future runs
            try:
                sf_cli_target.update_record('Account', existing_id, {'Source_Id__c': prod_account_id})
                print(f"Updated existing account {existing_id} with Source_Id__c = {prod_account_id}")
            except Exception as e:
                print(f"Warning: Could not update existing account with Source_Id__c: {str(e)}")
            
            return existing_id
        
        # If we can't find existing account, log and skip this account
        print(f"WARNING: Could not create or find Account {prod_account_id} ({account_name}). Skipping.")
        return None
    print(f"Created Account {prod_account_id} (Source) -> {new_sandbox_account_id} (Sandbox)")
    created_accounts[prod_account_id] = new_sandbox_account_id

    # Step 2: Create all dependent records referenced in lookups
    from create_contact_with_dependencies import create_contact_with_dependencies
    lookup_updates = {}
    for field_name, lookup_info in lookup_fields_to_populate.items():
        ref_id = lookup_info['ref_id']
        ref_to = lookup_info['ref_to']
        
        if ref_to == 'Account':
            if ref_id in created_accounts:
                lookup_updates[field_name] = created_accounts[ref_id]
            else:
                print(f"Account {prod_account_id} has Account lookup {field_name}={ref_id}. Creating referenced account.")
                ref_sandbox_id = create_account_with_dependencies(ref_id, created_accounts, account_insertable_fields_info, created_contacts, contact_insertable_fields_info, sf_cli_source, sf_cli_target)
                if ref_sandbox_id:
                    lookup_updates[field_name] = ref_sandbox_id
                else:
                    print(f"Warning: Could not create referenced account {ref_id} for {prod_account_id} field {field_name}.")
        elif ref_to == 'Contact':
            if ref_id in created_contacts:
                lookup_updates[field_name] = created_contacts[ref_id]
            else:
                print(f"Account {prod_account_id} has Contact lookup {field_name}={ref_id}. Creating referenced contact.")
                ref_sandbox_id = create_contact_with_dependencies(ref_id, created_contacts, contact_insertable_fields_info, sf_cli_source, sf_cli_target, created_accounts)
                if ref_sandbox_id:
                    lookup_updates[field_name] = ref_sandbox_id
                else:
                    print(f"Warning: Could not create referenced contact {ref_id} for {prod_account_id} field {field_name}.")
        elif ref_to == 'User':
            # Check if User exists in sandbox (with caching)
            if check_record_exists(sf_cli_target, 'User', ref_id):
                lookup_updates[field_name] = ref_id
            else:
                print(f"Warning: User {ref_id} referenced in field {field_name} for Account {prod_account_id} does not exist in sandbox.")

    # Step 3: Update the Account with all lookup field values
    if lookup_updates:
        print(f"Updating Account {new_sandbox_account_id} with lookup fields: {list(lookup_updates.keys())}")
        try:
            sf_cli_target.update_record('Account', new_sandbox_account_id, lookup_updates)
            print(f"Successfully updated Account {new_sandbox_account_id} with lookups")
        except Exception as e:
            error_msg = str(e)
            print(f"Warning: Could not update Account {new_sandbox_account_id} with all lookup fields: {error_msg}")
            
            # Try to update fields one by one to identify which one causes the problem
            if 'Hierarchy Constraint Violation' in error_msg or 'duplicate value' in error_msg:
                print("Attempting to update lookup fields individually...")
                for field_name, field_value in lookup_updates.items():
                    try:
                        sf_cli_target.update_record('Account', new_sandbox_account_id, {field_name: field_value})
                        print(f"  Successfully updated {field_name}")
                    except Exception as field_error:
                        print(f"  Skipping {field_name}: {str(field_error)}")
    
    in_progress.remove(prod_account_id)
    return new_sandbox_account_id
