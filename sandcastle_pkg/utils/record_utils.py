#!/usr/bin/env python3
"""
Record Utilities

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

import os
import csv
from rich.console import Console
from sandcastle_pkg.utils.picklist_utils import get_valid_picklist_values

console = Console()

# Global cache for record existence checks to avoid repeated queries
_record_existence_cache = {}

def check_record_exists(sf_cli, object_type, record_id):
    """
    Check if a record exists in the target org, with caching to avoid repeated queries.
    
    Args:
        sf_cli: Salesforce CLI instance
        object_type: Salesforce object type (e.g., 'User', 'Account', 'Contact')
        record_id: Record ID to check
        
    Returns:
        bool: True if record exists, False otherwise
    """
    cache_key = f"{object_type}:{record_id}"
    
    # Check cache first
    if cache_key in _record_existence_cache:
        return _record_existence_cache[cache_key]
    
    # Query the org
    try:
        query = f"SELECT Id FROM {object_type} WHERE Id = '{record_id}' LIMIT 1"
        result = sf_cli.query_records(query)
        exists = result and len(result) > 0
        
        # Cache the result
        _record_existence_cache[cache_key] = exists
        return exists
    except Exception as e:
        print(f"Error checking {object_type} {record_id}: {e}")
        # Cache negative result to avoid repeated failures
        _record_existence_cache[cache_key] = False
        return False

def replace_lookups_with_dummies(record, insertable_fields_info, dummy_records, created_mappings=None, sf_cli_source=None, sf_cli_target=None, sobject_type=None):
    """
    Replaces lookup fields with appropriate values:
    - Use real sandbox IDs if the referenced record was already created
    - Use dummy IDs for required lookups if referenced record doesn't exist yet
    - Remove optional lookups to avoid validation errors (Phase 2 will restore)
    - Map RecordTypeId by DeveloperName (except for Opportunities which use bypass in Phase 1)
    
    Args:
        record: The Salesforce record to modify
        insertable_fields_info: Field metadata dictionary
        dummy_records: Dictionary mapping object types to dummy record IDs
        created_mappings: Optional dict of created_* mappings by object type
        sf_cli_source: Source org CLI (for RecordType mapping)
        sf_cli_target: Target org CLI (for RecordType mapping)
        sobject_type: Object type (e.g., 'Account', 'Opportunity') - used to exclude Opportunity from RecordType mapping
        
    Returns:
        dict: Record with lookups properly set
    """
    modified_record = record.copy()
    created_mappings = created_mappings or {}
    
    for field_name, field_info in insertable_fields_info.items():
        if field_info['type'] == 'reference' and field_info['referenceTo']:
            referenced_object = field_info['referenceTo']
            
            # If the field exists in the record and has a value, replace it
            if field_name in modified_record and modified_record[field_name]:
                prod_lookup_id = modified_record[field_name]
                
                # Skip if it's a dict (relationship field)
                if isinstance(prod_lookup_id, dict):
                    continue
                
                # List of required lookup fields that MUST have a value in Phase 1
                required_lookups = ['AccountId', 'OpportunityId', 'QuoteId', 'OrderId', 
                                  'AccountFromId', 'AccountToId',  # Required for AccountRelationship
                                  'OwnerId']  # Required on most objects
                
                # Special handling for RecordType: Map by DeveloperName (except Opportunities)
                # Opportunities use a bypass RecordTypeId in Phase 1 to avoid triggering flows
                if referenced_object == 'RecordType' and field_name == 'RecordTypeId':
                    # Skip RecordType mapping for Opportunities - they use bypass in Phase 1
                    if sobject_type == 'Opportunity':
                        print(f"  [SKIP] RecordTypeId for Opportunity - will use bypass value, restore in Phase 2")
                        del modified_record[field_name]
                    # For all other objects, map RecordType by DeveloperName
                    elif sf_cli_source and sf_cli_target and sobject_type:
                        try:
                            rt_info = sf_cli_source.get_record_type_info_by_id(prod_lookup_id)
                            if rt_info and 'DeveloperName' in rt_info:
                                dev_name = rt_info['DeveloperName']
                                sandbox_rt_id = sf_cli_target.get_record_type_id(sobject_type, dev_name)
                                if sandbox_rt_id:
                                    modified_record[field_name] = sandbox_rt_id
                                    console.print(f"  [cyan][MAP] RecordType {dev_name}: {prod_lookup_id} → {sandbox_rt_id}[/cyan]")
                                else:
                                    print(f"  [WARN] RecordType '{dev_name}' not found in sandbox, removing field")
                                    del modified_record[field_name]
                            else:
                                print(f"  [WARN] Could not get RecordType info for {prod_lookup_id}, removing field")
                                del modified_record[field_name]
                        except Exception as e:
                            print(f"  [ERROR] RecordType mapping failed: {e}, removing field")
                            del modified_record[field_name]
                    else:
                        # No CLI provided, remove RecordType (will use default)
                        console.print(f"  [yellow][REMOVE] RecordTypeId (no CLI provided), will use default RecordType[/yellow]")
                        del modified_record[field_name]
                    continue
                
                # Special handling for User lookups
                # Keep all User lookups from production (users exist in sandbox with same IDs)
                if referenced_object == 'User':
                    console.print(f"  [green][KEEP] Keeping User lookup {field_name} = {prod_lookup_id} from production (users exist in sandbox)[/green]")
                    # Keep the production User lookup as-is
                # Special handling for OwnerId - keep production value if no mapping available
                # OwnerId can reference User, Group, or other objects - keep as-is from production
                elif field_name == 'OwnerId':
                    console.print(f"  [green][KEEP] Keeping {field_name} = {prod_lookup_id} from production (Owner lookups typically exist in sandbox)[/green]")
                    # Keep the production OwnerId as-is
                # For REQUIRED lookups only, try to use mapping or dummy
                elif field_name in required_lookups:
                    if referenced_object in created_mappings:
                        created_dict = created_mappings[referenced_object]
                        if prod_lookup_id in created_dict:
                            sandbox_lookup_id = created_dict[prod_lookup_id]
                            modified_record[field_name] = sandbox_lookup_id
                            console.print(f"  [cyan][MAP] Using real {field_name}: {prod_lookup_id} → {sandbox_lookup_id}[/cyan]")
                        elif referenced_object in dummy_records:
                            # Required field but record not created yet - use dummy
                            modified_record[field_name] = dummy_records[referenced_object]
                            print(f"  [DUMMY] Replaced {field_name} ({prod_lookup_id}) with dummy {referenced_object}")
                        else:
                            print(f"  [ERROR] Required {field_name} has no mapping or dummy available")
                    elif referenced_object in dummy_records:
                        # Required field without mapping - use dummy
                        modified_record[field_name] = dummy_records[referenced_object]
                        print(f"  [DUMMY] Replaced {field_name} ({prod_lookup_id}) with dummy {referenced_object}")
                    else:
                        print(f"  [ERROR] Required {field_name} has no dummy available")
                # For ALL optional lookups, remove them to avoid lookup filter issues
                # Phase 2 will restore them with real production values
                else:
                    # SAFETY CHECK: Verify this is actually a nillable field before removing
                    field_info = field_metadata.get(field_name, {})
                    is_nillable = field_info.get('nillable', True)  # Default to True for safety
                    
                    if not is_nillable:
                        console.print(f"  [red][WARNING] {field_name} is marked as REQUIRED (nillable=false) but treating as optional lookup. Will remove and restore in Phase 2.[/red]")
                        console.print(f"  [red]  → If this causes errors, this field may need special handling like PricebookEntryId[/red]")
                    else:
                        console.print(f"  [yellow][REMOVE] Removing optional lookup {field_name}, will restore in Phase 2[/yellow]")
                    
                    del modified_record[field_name]
            # If the field doesn't exist but is required, add dummy
            elif field_name not in modified_record and referenced_object in dummy_records:
                # Common required lookups
                if field_name in ['AccountId', 'OpportunityId', 'QuoteId', 'OrderId']:
                    modified_record[field_name] = dummy_records[referenced_object]
                    print(f"  [DUMMY] Added required {field_name} with dummy {referenced_object}")
    
    return modified_record

def load_insertable_fields(object_name, script_dir):
    """
    Loads insertable field names, their types, and reference information
    from the generated CSV file.
    Returns a dictionary of {field_name: {'type': field_type, 'referenceTo': reference_object, 'nillable': bool}}.
    """
    field_data_path = os.path.join(script_dir, 'fieldData', f'{object_name.lower()}Fields.csv')
    insertable_fields_info = {}
    if os.path.exists(field_data_path):
        with open(field_data_path, 'r', newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                field_name = row['Field Name']
                field_type = row['Field Type']
                reference_to = row.get('Reference To', '')
                # Get nillable status (defaults to True if not present for backward compatibility)
                nillable = row.get('Nillable', 'true').lower() == 'true'
                insertable_fields_info[field_name] = {
                    'type': field_type,
                    'referenceTo': reference_to,
                    'nillable': nillable
                }
    else:
        print(f"Warning: Field data CSV not found for {object_name} at {field_data_path}.")
    return insertable_fields_info
def filter_record_data(record, insertable_fields_info, sf_cli_target, sobject_type=None):
    """
    Filters a Salesforce record to include only insertable fields and handles special cases.
    For lookup fields, it checks if the referenced record exists in the target sandbox.
    SAFETY: Detects required fields (nillable=false) and warns before removal.
    
    Args:
        record: The Salesforce record to filter
        insertable_fields_info: Field metadata dictionary (includes 'nillable' status)
        sf_cli_target: Target Salesforce CLI instance
        sobject_type: The Salesforce object type (e.g., 'Account', 'Contact'). If not provided, 
                      will try to extract from record attributes.
    """
    console.print(f"[dim][FILTER FUNCTION V2] Called with sobject_type={sobject_type}, record has {len(record)} fields[/dim]")
    # Determine the sobject type
    if not sobject_type:
        sobject_type = record.get('attributes', {}).get('type') or record.get('sobjectType')
    
    # Fields that should never be copied (process/workflow driven fields)
    excluded_fields = {
        'Accept_as_Affiliate__c',  # Requires executive contact - process driven
        'Force_NetSuite_Sync__c',  # Never sync NetSuite integration field to sandbox
    }
    
    # System-managed required fields that are safe to exclude (auto-populated by Salesforce)
    system_managed_required = {
        'CreatedById', 'LastModifiedById', 'SystemModstamp', 'CreatedDate', 'LastModifiedDate',
        'IsDeleted', 'LastActivityDate', 'LastViewedDate', 'LastReferencedDate'
    }
    
    # User lookup fields that should be preserved - only OwnerId can be set
    # CreatedById and LastModifiedById are system-managed and cannot be set
    user_lookup_fields = {'OwnerId'}
    
    # Fallback user ID that always exists in sandbox
    fallback_user_id = '0052E00000MrqyAQAR'
    
    filtered_data = {}
    for field_name, value in record.items():
        # Preserve OwnerId only if the user exists in sandbox, otherwise use fallback
        if field_name in user_lookup_fields and value and not isinstance(value, dict):
            # Check if the user exists in the sandbox
            if check_record_exists(sf_cli_target, 'User', value):
                filtered_data[field_name] = value
                console.print(f"  [green][PRESERVE] {field_name} = {value} (User exists in sandbox)[/green]")
            else:
                filtered_data[field_name] = fallback_user_id
                console.print(f"  [red][FALLBACK] {field_name} = {fallback_user_id} (Original user {value} not found in sandbox)[/red]")
            continue
        
        # Check if field is in our metadata before processing
        field_type_info = insertable_fields_info.get(field_name)
        is_required = field_type_info.get('nillable') == False if field_type_info else False
        
        # Exclude system fields, relationship fields, process fields, and fields not in our insertable list
        if (field_name == 'attributes' or 
        
            field_name in excluded_fields or
            field_name not in insertable_fields_info):
            # SAFETY CHECK: Warn if we're excluding a required field (unless system-managed)
            if is_required and field_name not in system_managed_required and field_name not in {'attributes'}:
                console.print(f"  [bold red]⚠ WARNING: Excluding REQUIRED field '{field_name}' (nillable=false)[/bold red]")
                console.print(f"    Reason: {_get_exclusion_reason(field_name, excluded_fields, insertable_fields_info)}")
            continue
        field_type_info = insertable_fields_info.get(field_name)
        if not field_type_info:
            continue
        field_type = field_type_info['type']
        
        # Debug output for Product_Types_Quoted__c
        # if field_name == 'Product_Types_Quoted__c':
        #     print(f"[DEBUG] Processing Product_Types_Quoted__c: value='{value}', type='{field_type}'")
        #     print(f"[DEBUG] value is not None: {value is not None}")
        #     print(f"[DEBUG] isinstance(value, str): {isinstance(value, str)}")
        #     print(f"[DEBUG] isinstance(value, dict): {isinstance(value, dict)}")
        #     if isinstance(value, dict):
        #         print(f"[DEBUG] value dict content: {value}")
        
        # Handle lookup fields
        if field_type == 'reference':
            referenc# SAFETY CHECK: Warn if removing a required lookup
                    if is_required:
                        console.print(f"  [bold yellow]⚠ REQUIRED LOOKUP: '{field_name}' (→{referenced_object}) not found. Will need dummy or Phase 2 update.[/bold yellow]")
                    else:
                        ed_object = field_type_info['referenceTo']
            if referenced_object and value:
                query =\
                    f"SELECT Id FROM {referenced_object} WHERE Id = '{value}' LIMIT 1"
                existing_referenced_record = sf_cli_target.query_records(query)
                if existing_referenced_record and len(existing_referenced_record) > 0:
                    filtered_data[field_name] = value
                else:
                    print(f"  DEBUG: Skipping lookup field '{field_name}' (value: {value}) because referenced record in {referenced_object} does not exist in target sandbox.")
            continue
        if isinstance(value, dict) and 'Id' in value:
            if field_name == 'RecordTypeId':
                filtered_data[field_name] = value['Id']
            elif field_name == 'OwnerId':
                filtered_data[field_name] = value['Id']
            else:
                filtered_data[field_name] = value['Id']
        elif value is not None:
            if field_name == 'Product_Types_Quoted__c':
                console.print(f"[magenta][DEBUG] Product_Types_Quoted__c: Entered 'value is not None' block[/magenta]")
            # If this is an email field, append '.invalid' to the value
            if 'email' in field_name.lower() and isinstance(value, str) and not value.endswith('.invalid'):
                if field_name == 'Product_Types_Quoted__c':
                    console.print(f"[magenta][DEBUG] Product_Types_Quoted__c: Taking EMAIL branch[/magenta]")
                filtered_data[field_name] = value + '.invalid'
            # Handle picklist fields: check if value is valid, else set to 'Other' or remove
            elif field_type == 'picklist' and isinstance(value, str):
                if field_name == 'Product_Types_Quoted__c' or field_name == 'Primary_Team__c':
                    console.print(f"[magenta][DEBUG] {field_name}: Taking PICKLIST branch, value='{value}'[/magenta]")
                try:
                    # Try to get valid picklist values for this field
                    valid_if is_required:
                            # SAFETY: For required picklists, use first valid value instead of removing
                            default_value = next(iter(valid_values)) if valid_values else None
                            if default_value:
                                console.print(f"  [bold yellow]⚠ REQUIRED PICKLIST: '{field_name}' value '{value}' invalid. Using '{default_value}'.[/bold yellow]")
                                filtered_data[field_name] = default_value
                            else:
                                console.print(f"  [bold red]⚠ ERROR: REQUIRED picklist '{field_name}' has no valid values. Removing (may cause insert failure).[/bold red]")
                                continue
                        elvalues = get_valid_picklist_values(sf_cli_target, sobject_type, field_name) if sobject_type else set()
                    if valid_values and value not in valid_values:
                        # Special handling for required picklist fields
                        if field_name == 'StageName':
                            # SAFETY: For required fields, keep value; for optional, remove
                            if is_required:
                                console.print(f"  [bold yellow]⚠ REQUIRED PICKLIST: '{field_name}' cannot be validated. Keeping original value '{value}'.[/bold yellow]")
                                filtered_data[field_name] = value
                            else:
                                # For all other picklists, remove if we can't validate
                                print(f"[PICKLIST REMOVAL] Field '{field_name}': Could not retrieve valid picklist values. Removing field to prevent errors.")
                                print(f"[PICKLIST REPLACEMENT] Field '{field_name}': '{value}' is not valid. Using default '{default_stage}'.")
                            filtered_data[field_name] = default_stage
                        # Prefer 'Other' if available, else remove field (for non-required fields)
                        elif 'Other' in valid_values:
                            print(f"[PICKLIST REPLACEMENT] Field '{field_name}': '{value}' is not valid. Replacing with 'Other'.")
                            filtered_data[field_name] = 'Other'
                        else:
                            print(f"[PICKLIST REMOVAL] Field '{field_name}': '{value}' is not valid and no 'Other' value available. Removing field from record.")
                            continue
                    elif valid_values:
                        # Value is valid
                        filtered_data[field_name] = value
                    else:
                        # Could not get valid values, remove field to be safe (unless it's StageName)
                        if field_name == 'StageName':
                            # For StageName, use the current value if we can't validate
                            print(f"[PICKLIST PASSTHROUGH] Field '{field_name}': Could not retrieve valid values. Keeping original value '{value}'.")
                            filtered_data[field_name] = value
                        else:
                            # For all other picklists, remove if we can't validate
                            print(f"[PICKLIST REMOVAL] Field '{field_name}': Could not retrieve valid picklist values. Removing field to prevent errors.")
                            continue
                except Exception as e:
                    print(f"[PICKLIST ERROR] Field '{field_name}': Error retrieving picklist values: {str(e)}. Removing field.")
                    continue
            # Handle multi-select picklist fields (semicolon-separated values)
            elif field_type == 'multipicklist' and isinstance(value, str):
                if field_name == 'Product_Types_Quoted__c':
                    console.print(f"[magenta][DEBUG] Product_Types_Quoted__c: Taking MULTIPICKLIST branch[/magenta]")
                try:
                    valid_values = get_valid_picklist_values(sf_cli_target, sobject_type, field_name) if sobject_type else set()
                    if valid_values:
                        # Split by semicolon, filter valid values
                        selected_values = [v.strip() for v in value.split(';')]
                        valid_selected = [v for v in selected_values if v in valid_values]
                        
                        if valid_selected:
                            result_value = ';'.join(valid_selected)
                            
                            # Check if the result exceeds typical multipicklist field limit (255 chars)
                            if len(result_value) > 255:
                                # Truncate by removing values from the end until it fits
                            # SAFETY: Warn if removing required multipicklist
                            if is_required:
                                console.print(f"  [bold red]⚠ ERROR: REQUIRED multipicklist '{field_name}' has no valid values. Removing (may cause insert failure).[/bold red]")
                            else:
                                    truncated_values = []
                                current_length = 0
                                for v in valid_selected:
                                    # Account for semicolon separator
                                    needed_length = len(v) + (1 if truncated_values else 0)
                                    if current_length + needed_length <= 255:
                                        truncated_values.append(v)
                                        current_length += needed_length
                                    else:
                                        break
                                result_value = ';'.join(truncated_values)
                                print(f"[MULTIPICKLIST TRUNCATE] Field '{field_name}': Value too long ({len(';'.join(valid_selected))} chars). Truncated to {len(result_value)} chars. Kept {len(truncated_values)}/{len(valid_selected)} values.")
                            
                            filtered_data[field_name] = result_value
                            invalid_values = [v for v in selected_values if v not in valid_values]
                            if invalid_values:
                                print(f"[MULTIPICKLIST FILTER] Field '{field_name}': Removed invalid values {invalid_values}. Kept: {len(valid_selected)} valid values.")
                        else:
                            print(f"[MULTIPICKLIST REMOVAL] Field '{field_name}': No valid values found in '{value}'. Removing field from record.")
    
    # Final safety check: Report any required fields that are missing from the filtered data
    for field_name, field_info in insertable_fields_info.items():
        if field_info.get('nillable') == False and field_name not in filtered_data:
            # Skip system-managed fields and relationship fields
            if field_name not in system_managed_required and not field_name.endswith('__r'):
                # Check if field was in original record
                if field_name in record:
                    console.print(f"  [bold red]⚠ REQUIRED FIELD REMOVED: '{field_name}' was in source but filtered out[/bold red]")
                elif field_info.get('type') not in ['reference']:  # Lookups handled by Phase 1/2
                    console.print(f"  [dim yellow]ℹ Required field '{field_name}' missing from source record (may use default)[/dim yellow]")
    
    return filtered_data


def _get_exclusion_reason(field_name, excluded_fields, insertable_fields_info):
    """Helper to explain why a field was excluded"""
    if field_name == 'attributes':
        return "System metadata field"
    elif field_name.endswith('__r'):
        return "Relationship field (not insertable)"
    elif field_name in excluded_fields:
        return "In excluded_fields list (process/workflow driven)"
    elif field_name not in insertable_fields_info:
        return "Not in insertable_fields_info (not createable or not in metadata)"
    return "Unknown reason"    continue
                    else:
                        # If we can't get valid values, remove the field to be safe
                        print(f"[MULTIPICKLIST REMOVAL] Field '{field_name}': Could not retrieve valid picklist values. Removing field to prevent errors.")
                        continue
                except Exception as e:
                    print(f"[MULTIPICKLIST ERROR] Field '{field_name}': Error retrieving picklist values: {str(e)}. Removing field.")
                    continue
            # Handle boolean fields - convert string 'True'/'False' to actual booleans
            elif field_type == 'boolean' and isinstance(value, str):
                if value == 'True':
                    filtered_data[field_name] = True
                elif value == 'False':
                    filtered_data[field_name] = False
                else:
                    # Invalid boolean string, skip field
                    print(f"[BOOLEAN ERROR] Field '{field_name}': Invalid boolean string '{value}'. Removing field.")
                    continue
            else:
                if field_name == 'Product_Types_Quoted__c':
                    console.print(f"[magenta][DEBUG] Product_Types_Quoted__c: Taking ELSE branch - adding field as-is[/magenta]")
                filtered_data[field_name] = value
    return filtered_data