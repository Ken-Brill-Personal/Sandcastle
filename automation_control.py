#!/usr/bin/env python3
"""
Automation Control Utilities

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License

Controls Salesforce automation (Flows and Triggers) during data migration.
Flows can be paused/reactivated via Tooling API.
Triggers require bypass logic in the code (checking a custom setting/permission).
"""
import json


def pause_all_flows(sf_cli_target):
    """
    Pauses all active Flows in the target org.
    Returns a list of Flow IDs that were paused (to reactivate later).
    
    Note: Some flows cannot be paused via Tooling API due to metadata requirements.
    These will be skipped with a warning.
    """
    print("\n--- Pausing Active Flows ---")
    paused_flows = []
    
    try:
        # Query all active Flow versions
        query = """
            SELECT Id, Definition.DeveloperName, Status, ProcessType 
            FROM Flow 
            WHERE Status = 'Active' 
            AND (ProcessType = 'Flow' 
                 OR ProcessType = 'AutoLaunchedFlow' 
                 OR ProcessType = 'Workflow'
                 OR ProcessType = 'InvocableProcess')
        """
        
        # Use Tooling API query
        result = sf_cli_target._execute_sf_command([
            'data', 'query',
            '--query', query,
            '--use-tooling-api'
        ])
        
        if result and result.get('result', {}).get('records'):
            flows = result['result']['records']
            print(f"Found {len(flows)} active flows")
            print(f"⚠️  This may take several minutes. Press Ctrl+C to skip flow pausing.\n")
            
            success_count = 0
            skip_count = 0
            
            for idx, flow in enumerate(flows, 1):
                flow_id = flow['Id']
                flow_name = flow.get('Definition', {}).get('DeveloperName', 'Unknown')
                
                # Show progress every 10 flows
                if idx % 10 == 0:
                    print(f"  Progress: {idx}/{len(flows)} flows processed ({success_count} paused, {skip_count} skipped)...")
                
                try:
                    # Update Flow to Obsolete status (pauses it)
                    update_result = sf_cli_target._execute_sf_command([
                        'data', 'update', 'record',
                        '--sobject', 'Flow',
                        '--record-id', flow_id,
                        '--values', 'Status=Obsolete',
                        '--use-tooling-api'
                    ])
                    
                    if update_result and update_result.get('status') == 0:
                        paused_flows.append({
                            'id': flow_id,
                            'name': flow_name,
                            'processType': flow.get('ProcessType')
                        })
                        success_count += 1
                    else:
                        skip_count += 1
                        
                except Exception as e:
                    error_msg = str(e)
                    # Skip flows that can't be paused via Tooling API
                    if 'InteractionDefinitionVersion' in error_msg or 'valid Metadata field' in error_msg:
                        skip_count += 1
                    else:
                        print(f"  ✗ Error pausing {flow_name}: {e}")
                        skip_count += 1
            
            print(f"\n{'='*80}")
            print(f"✓ Successfully paused {success_count} flows")
            if skip_count > 0:
                print(f"⚠️  Skipped {skip_count} flows (cannot be paused via Tooling API)")
            
            # Check if ALL flows were skipped
            if success_count == 0 and skip_count > 0:
                print(f"\n{'='*80}")
                print(f"⚠️  WARNING: ALL flows were skipped - flow pausing may not be possible")
                print(f"⚠️  via Tooling API in this org. Consider using --skip-flows flag.")
                print(f"⚠️  Migration will continue, but flows will remain active.")
                print(f"{'='*80}\n")
            
            print(f"{'='*80}\n")
        else:
            print("No active flows found")
            
    except KeyboardInterrupt:
        print(f"\n\n⚠️  Flow pausing interrupted by user")
        print(f"   Paused {len(paused_flows)} flows before interruption")
        print(f"   These will still be reactivated at the end")
        raise  # Re-raise to be caught by main script
    except Exception as e:
        print(f"Error querying flows: {e}")
    
    return paused_flows


def reactivate_flows(sf_cli_target, paused_flows):
    """
    Reactivates flows that were previously paused.
    
    Args:
        sf_cli_target: CLI instance for target org
        paused_flows: List of flow info dicts from pause_all_flows()
    """
    if not paused_flows:
        print("\nNo flows to reactivate")
        return
    
    print(f"\n--- Reactivating {len(paused_flows)} Flows ---")
    
    for flow_info in paused_flows:
        flow_id = flow_info['id']
        flow_name = flow_info['name']
        
        try:
            # Update Flow back to Active status
            update_result = sf_cli_target._execute_sf_command([
                'data', 'update', 'record',
                '--sobject', 'Flow',
                '--record-id', flow_id,
                '--values', 'Status=Active',
                '--use-tooling-api'
            ])
            
            if update_result and update_result.get('status') == 0:
                print(f"  ✓ Reactivated: {flow_name}")
            else:
                print(f"  ✗ Failed to reactivate: {flow_name}")
                
        except Exception as e:
            print(f"  ✗ Error reactivating {flow_name}: {e}")


def enable_trigger_bypass(sf_cli_target, bypass_setting_name='Bypass_Automation__c'):
    """
    Enables trigger bypass by setting a custom setting or permission.
    This only works if your triggers check this setting!
    
    Common patterns:
    - Custom Setting: Bypass_Automation__c with checkbox field Is_Bypassed__c
    - Custom Permission: Bypass_Triggers
    
    Args:
        sf_cli_target: CLI instance
        bypass_setting_name: API name of custom setting
    """
    print(f"\n--- Enabling Trigger Bypass ({bypass_setting_name}) ---")
    
    try:
        # Try to query if custom setting exists
        query = f"SELECT Id FROM {bypass_setting_name} WHERE SetupOwnerId = UserInfo.getUserId() LIMIT 1"
        existing = sf_cli_target.query_records(query)
        
        if existing and len(existing) > 0:
            # Update existing
            setting_id = existing[0]['Id']
            sf_cli_target._execute_sf_command([
                'data', 'update', 'record',
                '--sobject', bypass_setting_name,
                '--record-id', setting_id,
                '--values', 'Is_Bypassed__c=true'
            ])
            print(f"  ✓ Updated bypass setting: {setting_id}")
        else:
            # Create new
            result = sf_cli_target._execute_sf_command([
                'data', 'create', 'record',
                '--sobject', bypass_setting_name,
                '--values', 'Is_Bypassed__c=true'
            ])
            print(f"  ✓ Created bypass setting")
            
        return True
        
    except Exception as e:
        print(f"  ℹ Could not set trigger bypass (custom setting may not exist): {e}")
        print(f"  Note: Triggers must be coded to check this setting for bypass to work")
        return False


def disable_trigger_bypass(sf_cli_target, bypass_setting_name='Bypass_Automation__c'):
    """
    Disables trigger bypass by unsetting the custom setting.
    """
    print(f"\n--- Disabling Trigger Bypass ({bypass_setting_name}) ---")
    
    try:
        query = f"SELECT Id FROM {bypass_setting_name} LIMIT 1"
        existing = sf_cli_target.query_records(query)
        
        if existing and len(existing) > 0:
            setting_id = existing[0]['Id']
            sf_cli_target._execute_sf_command([
                'data', 'update', 'record',
                '--sobject', bypass_setting_name,
                '--record-id', setting_id,
                '--values', 'Is_Bypassed__c=false'
            ])
            print(f"  ✓ Disabled bypass setting")
        else:
            print(f"  ℹ No bypass setting found")
            
    except Exception as e:
        print(f"  ✗ Error disabling bypass: {e}")


def pause_validation_rules(sf_cli_target):
    """
    Note: Validation rules cannot be disabled via API.
    They must be deactivated via Metadata API deployment.
    This is a placeholder to document the limitation.
    """
    print("\n--- Validation Rules ---")
    print("  ℹ Validation rules cannot be disabled via API")
    print("  ℹ To disable: Use Metadata API or manually deactivate in Setup")
    return []
