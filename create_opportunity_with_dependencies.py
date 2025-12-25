#!/usr/bin/env python3
"""
Opportunity Creation with Dependencies

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

import logging
import os
from record_utils import load_insertable_fields, filter_record_data, check_record_exists

# Cache for bypass RecordType ID lookup
_bypass_record_type_id = None

def get_bypass_record_type_id(sf_cli_target, config=None):
    """
    Get the bypass RecordType ID to use during Opportunity creation.
    Checks config first, then looks for 'Standard Opportunity' RecordType.
    """
    global _bypass_record_type_id
    
    if _bypass_record_type_id:
        return _bypass_record_type_id
    
    # Check if bypass RecordType ID is specified in config
    if config and 'opportunity_bypass_record_type_id' in config:
        _bypass_record_type_id = config['opportunity_bypass_record_type_id']
        print(f"Using bypass RecordType ID from config: {_bypass_record_type_id}")
        return _bypass_record_type_id
    
    # Query for 'Standard Opportunity' RecordType
    try:
        query = "SELECT Id FROM RecordType WHERE SobjectType='Opportunity' AND DeveloperName='StandardOpportunity' AND IsActive=true LIMIT 1"
        results = sf_cli_target.query_records(query)
        if results and len(results) > 0:
            _bypass_record_type_id = results[0]['Id']
            print(f"Using 'Standard Opportunity' RecordType as bypass: {_bypass_record_type_id}")
            return _bypass_record_type_id
    except Exception as e:
        print(f"Warning: Could not query for Standard Opportunity RecordType: {str(e)}")
    
    return None

def create_opportunity_with_dependencies(sf_cli_target, opportunity_data, created_opportunities, created_accounts, config=None, sf_cli_source=None, created_contacts=None, contact_insertable_fields_info=None):
    """
    Create an Opportunity in Salesforce, ensuring the related Account exists and deduping by source ID.
    Handles Contact and Related Opportunity lookups by creating dependencies first.
    """
    source_id = opportunity_data.get('Source_Id__c')
    if not source_id:
        print('ERROR: Opportunity missing Source_Id__c, skipping.')
        return None
    if source_id in created_opportunities:
        print(f"Opportunity with Source_Id__c {source_id} already created. Skipping.")
        return created_opportunities[source_id]
    
    # Ensure Account exists
    account_source_id = opportunity_data.get('Account_Source_Id__c')
    if account_source_id and account_source_id in created_accounts:
        opportunity_data['AccountId'] = created_accounts[account_source_id]
    else:
        print(f"ERROR: Account for Opportunity {source_id} not found, skipping.")
        return None
    
    # Create the Opportunity in Salesforce
    print(f"Creating Opportunity {source_id} in target sandbox...")
    
    # Load insertable fields metadata for Opportunity object
    script_dir = os.path.dirname(os.path.abspath(__file__))
    insertable_fields_info = load_insertable_fields('Opportunity', script_dir)
    
    # Step 1: Extract lookup fields that may need dependency creation
    lookup_fields_to_populate = {}
    for field_name, field_info in list(insertable_fields_info.items()):
        if field_info.get('type') == 'reference':
            ref_id = opportunity_data.get(field_name)
            if ref_id:
                lookup_fields_to_populate[field_name] = {
                    'ref_id': ref_id,
                    'ref_to': field_info.get('referenceTo')
                }
                # Remove lookup from record data for initial creation
                opportunity_data.pop(field_name, None)
    
    # Use the proper filter_record_data function to get only insertable fields
    cleaned_opp_data = filter_record_data(opportunity_data, insertable_fields_info, sf_cli_target, 'Opportunity')
    
    # Remove our custom tracking fields that don't exist in the sandbox
    for tracking_field in ['Source_Id__c', 'Account_Source_Id__c']:
        if tracking_field in cleaned_opp_data:
            del cleaned_opp_data[tracking_field]
    
    # Store the original RecordTypeId before creating with bypass RecordTypeId
    original_record_type_id = cleaned_opp_data.get('RecordTypeId')
    
    # Get bypass RecordTypeId to prevent flow from running during creation
    bypass_record_type_id = get_bypass_record_type_id(sf_cli_target, config)
    
    if bypass_record_type_id:
        cleaned_opp_data['RecordTypeId'] = bypass_record_type_id
        print(f"Creating Opportunity with bypass RecordTypeId: {bypass_record_type_id}")
    else:
        print(f"Warning: No bypass RecordType ID found. Creating with original RecordTypeId: {original_record_type_id}")
    
    new_opp_id = sf_cli_target.create_record('Opportunity', cleaned_opp_data)
    if not new_opp_id:
        print(f"ERROR: Failed to create Opportunity {source_id}")
        return None
    
    created_opportunities[source_id] = new_opp_id
    print(f"Created Opportunity {source_id} (Source) -> {new_opp_id} (Sandbox)")
    
    # Step 2: Handle lookup dependencies
    lookup_updates = {}
    
    for field_name, lookup_info in lookup_fields_to_populate.items():
        ref_id = lookup_info['ref_id']
        ref_to = lookup_info['ref_to']
        
        # Handle Contact lookups
        if ref_to == 'Contact' and sf_cli_source and created_contacts is not None and contact_insertable_fields_info:
            if ref_id in created_contacts:
                lookup_updates[field_name] = created_contacts[ref_id]
                print(f"  Lookup field '{field_name}': Contact {ref_id} already created as {created_contacts[ref_id]}")
            else:
                # Create the referenced contact
                print(f"  Lookup field '{field_name}': Creating referenced Contact {ref_id}")
                from create_contact_with_dependencies import create_contact_with_dependencies
                sandbox_contact_id = create_contact_with_dependencies(
                    ref_id,
                    created_contacts,
                    contact_insertable_fields_info,
                    sf_cli_source,
                    sf_cli_target,
                    created_accounts
                )
                if sandbox_contact_id:
                    lookup_updates[field_name] = sandbox_contact_id
                    print(f"  Created Contact {ref_id} -> {sandbox_contact_id} for lookup '{field_name}'")
                else:
                    print(f"  WARNING: Could not create Contact {ref_id} for lookup '{field_name}'")
        
        # Handle Related Opportunity lookups
        elif ref_to == 'Opportunity':
            if ref_id in created_opportunities:
                lookup_updates[field_name] = created_opportunities[ref_id]
                print(f"  Lookup field '{field_name}': Related Opportunity {ref_id} already created as {created_opportunities[ref_id]}")
            else:
                print(f"  Lookup field '{field_name}': Related Opportunity {ref_id} not yet created, skipping for now")
        
        # Handle other lookups - check if record exists (with caching)
        else:
            if check_record_exists(sf_cli_target, ref_to, ref_id):
                lookup_updates[field_name] = ref_id
                print(f"  Lookup field '{field_name}': {ref_to} {ref_id} exists in target")
            else:
                print(f"  Lookup field '{field_name}': {ref_to} {ref_id} does not exist in target, skipping")
    
    # Step 3: Update Opportunity with lookup fields and correct RecordTypeId
    updates_to_apply = {}
    
    # Add lookup fields
    if lookup_updates:
        updates_to_apply.update(lookup_updates)
    
    # Add correct RecordTypeId if needed
    if bypass_record_type_id and original_record_type_id and original_record_type_id != bypass_record_type_id:
        updates_to_apply['RecordTypeId'] = original_record_type_id
    
    if updates_to_apply:
        print(f"Updating Opportunity {new_opp_id} with lookup fields: {list(updates_to_apply.keys())}")
        try:
            sf_cli_target.update_record('Opportunity', new_opp_id, updates_to_apply)
            print(f"Successfully updated Opportunity {new_opp_id}")
        except Exception as e:
            print(f"Warning: Could not update Opportunity {new_opp_id}: {str(e)}")
    
    return new_opp_id
