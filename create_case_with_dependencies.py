#!/usr/bin/env python3
"""
Case Creation with Dependencies

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

from duplicate_check import find_existing_record
from record_utils import filter_record_data, check_record_exists


def create_case_with_dependencies(prod_case_id, created_cases, case_insertable_fields_info, created_accounts, created_contacts, sf_cli_source, sf_cli_target):
    """
    Create a Case in the sandbox, handling all Account, Contact, and User lookups.
    - created_cases: dict mapping prod_case_id to sandbox_case_id
    - created_accounts: dict mapping prod_account_id to sandbox_account_id
    - created_contacts: dict mapping prod_contact_id to sandbox_contact_id
    """
    from create_opportunity_with_dependencies import create_opportunity_with_dependencies
    # We'll need a persistent dictionary for created_opportunities
    if not hasattr(create_case_with_dependencies, '_created_opportunities'):
        create_case_with_dependencies._created_opportunities = {}
    created_opportunities = create_case_with_dependencies._created_opportunities
    # Circular dependency protection
    if not hasattr(create_case_with_dependencies, 'in_progress'):
        create_case_with_dependencies.in_progress = set()
    in_progress = create_case_with_dependencies.in_progress
    if prod_case_id in in_progress:
        print(f"[CIRCULAR] Case {prod_case_id} is already being created. Skipping to break cycle.")
        return None
    if prod_case_id in created_cases:
        return created_cases[prod_case_id]
    in_progress.add(prod_case_id)


    print(f"Fetching Case {prod_case_id} from source org...")
    prod_case_record = sf_cli_source.get_record('Case', prod_case_id)
    if not prod_case_record:
        print(f"Could not fetch Case {prod_case_id} from source org.")
        return None

    # If Primary_Team__c has a value, remove it (picklist values may not match sandbox)
    if prod_case_record.get('Primary_Team__c'):
        print(f"[TODO] Primary_Team__c is '{prod_case_record.get('Primary_Team__c')}' for this Case. Removing field. (Consider mapping/fixing this later.)")
        prod_case_record.pop('Primary_Team__c', None)

    # Only deduplicate by source Case ID (prod_case_id)
    # If already in created_cases, this function will have already returned above

    # Step 1: Extract lookup fields and setup for dependency creation
    from create_account_with_dependencies import create_account_with_dependencies
    from create_contact_with_dependencies import create_contact_with_dependencies
    from record_utils import load_insertable_fields
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    account_insertable_fields_info = load_insertable_fields('Account', script_dir)
    contact_insertable_fields_info = load_insertable_fields('Contact', script_dir)
    
    # In-memory cache for Group lookups and creations
    if not hasattr(create_case_with_dependencies, '_group_prod_cache'):
        create_case_with_dependencies._group_prod_cache = {}
    if not hasattr(create_case_with_dependencies, '_group_sandbox_cache'):
        create_case_with_dependencies._group_sandbox_cache = {}
    group_prod_cache = create_case_with_dependencies._group_prod_cache
    group_sandbox_cache = create_case_with_dependencies._group_sandbox_cache

    lookup_fields_to_populate = {}
    for field_name, field_info in list(case_insertable_fields_info.items()):
        if field_info.get('type') == 'reference':
            ref_id = prod_case_record.get(field_name)
            if ref_id:
                lookup_fields_to_populate[field_name] = {
                    'ref_id': ref_id,
                    'ref_to': field_info.get('referenceTo')
                }
                # Remove lookup from record data for initial creation
                prod_case_record.pop(field_name, None)

    # Create the Case first WITHOUT lookup fields
    filtered_case_data = filter_record_data(prod_case_record, case_insertable_fields_info, sf_cli_target, 'Case')
    filtered_case_data.pop('Id', None)
    print(f"Creating Case in target sandbox (without lookups)")
    new_sandbox_case_id = sf_cli_target.create_record('Case', filtered_case_data)
    if not new_sandbox_case_id:
        in_progress.remove(prod_case_id)
        raise RuntimeError(f"Failed to create Case for {prod_case_id}")
    print(f"Created Case {prod_case_id} (Source) -> {new_sandbox_case_id} (Sandbox)")
    created_cases[prod_case_id] = new_sandbox_case_id

    # Step 2: Create all dependent records referenced in lookups
    lookup_updates = {}
    for field_name, lookup_info in lookup_fields_to_populate.items():
        ref_id = lookup_info['ref_id']
        ref_to = lookup_info['ref_to']
        
        # Special handling for Connectivity_Opportunity__c
        if field_name == 'Connectivity_Opportunity__c' and ref_to == 'Opportunity':
            if check_record_exists(sf_cli_target, 'Opportunity', ref_id):
                lookup_updates[field_name] = ref_id
            elif ref_id in created_opportunities:
                lookup_updates[field_name] = created_opportunities[ref_id]
            else:
                opp_record = sf_cli_source.get_record('Opportunity', ref_id)
                if opp_record:
                    opp_record['Source_Id__c'] = ref_id
                    opp_record['Account_Source_Id__c'] = opp_record.get('AccountId')
                    new_opp_id = create_opportunity_with_dependencies(
                        sf_cli_target, opp_record, created_opportunities, created_accounts
                    )
                    if new_opp_id:
                        lookup_updates[field_name] = new_opp_id
                        print(f"Created missing Opportunity {ref_id} for Connectivity_Opportunity__c on Case {prod_case_id}.")
                    else:
                        print(f"Warning: Could not create Opportunity {ref_id} for Connectivity_Opportunity__c on Case {prod_case_id}.")
                else:
                    print(f"Warning: Opportunity {ref_id} referenced in Connectivity_Opportunity__c for Case {prod_case_id} does not exist in production.")
            continue
            
        if ref_to == 'Account':
            if ref_id in created_accounts:
                lookup_updates[field_name] = created_accounts[ref_id]
            else:
                print(f"Case {prod_case_id} references Account {ref_id}. Creating Account in sandbox.")
                sandbox_account_id = create_account_with_dependencies(
                    ref_id, created_accounts, account_insertable_fields_info,
                    {}, {}, sf_cli_source, sf_cli_target
                )
                if sandbox_account_id:
                    lookup_updates[field_name] = sandbox_account_id
                else:
                    print(f"Warning: Could not create referenced account {ref_id} for Case {prod_case_id} field {field_name}.")
        elif ref_to == 'Contact':
            if ref_id in created_contacts:
                lookup_updates[field_name] = created_contacts[ref_id]
            else:
                print(f"Case {prod_case_id} references Contact {ref_id}. Creating Contact in sandbox.")
                sandbox_contact_id = create_contact_with_dependencies(
                    ref_id, created_contacts, contact_insertable_fields_info,
                    sf_cli_source, sf_cli_target, created_accounts
                )
                if sandbox_contact_id:
                    lookup_updates[field_name] = sandbox_contact_id
        elif ref_to == 'User':
            # Check if User exists in sandbox (with caching)
            if check_record_exists(sf_cli_target, 'User', ref_id):
                lookup_updates[field_name] = ref_id
            else:
                print(f"Warning: User {ref_id} referenced in field {field_name} for Case {prod_case_id} does not exist in sandbox.")
        elif ref_to == 'Group':
            if ref_id in group_sandbox_cache:
                lookup_updates[field_name] = group_sandbox_cache[ref_id]
            else:
                if check_record_exists(sf_cli_target, 'Group', ref_id):
                    group_sandbox_cache[ref_id] = ref_id
                    lookup_updates[field_name] = ref_id
                else:
                    if ref_id in group_prod_cache:
                        group_prod = group_prod_cache[ref_id]
                    else:
                        try:
                            group_prod = sf_cli_source.get_record('Group', ref_id)
                            group_prod_cache[ref_id] = group_prod
                        except Exception as e:
                            print(f"Warning: Could not fetch Group {ref_id} from production: {e}")
                            group_prod = None
                            group_prod_cache[ref_id] = None
                    group_name = group_prod.get('Name') if group_prod else None
                    if group_name:
                        print(f"Case {prod_case_id} references Group {ref_id} ('{group_name}'). Creating Group in sandbox.")
                        group_data = {'Name': group_name, 'Type': group_prod.get('Type', 'Regular')}
                        new_group_id = sf_cli_target.create_record('Group', group_data)
                        if new_group_id:
                            group_sandbox_cache[ref_id] = new_group_id
                            lookup_updates[field_name] = new_group_id
                            print(f"Created Group '{group_name}' in sandbox with Id: {new_group_id}")
                        else:
                            print(f"Warning: Could not create Group '{group_name}' for Case {prod_case_id} field {field_name}.")
                    else:
                        print(f"Warning: Group {ref_id} referenced in field {field_name} for Case {prod_case_id} does not exist in sandbox and could not be found in production.")

    # Step 3: Update the Case with all lookup field values
    if lookup_updates:
        print(f"Updating Case {new_sandbox_case_id} with lookup fields: {list(lookup_updates.keys())}")
        sf_cli_target.update_record('Case', new_sandbox_case_id, lookup_updates)
    in_progress.remove(prod_case_id)
    return new_sandbox_case_id
