#!/usr/bin/env python3
"""
EMERGENCY RECOVERY SCRIPT

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License

Reactivates all Flows that are in Obsolete status.
Run this if migration was interrupted before automation cleanup completed.

Usage:
    python3 reactivate_automation.py --target-alias YOUR_SANDBOX
"""
import argparse
from salesforce_cli import SalesforceCLI


def reactivate_all_obsolete_flows(sf_cli_target):
    """
    Reactivates all Flows that are currently in Obsolete status.
    This is useful if migration was interrupted.
    """
    print("\n" + "="*80)
    print("REACTIVATING ALL OBSOLETE FLOWS")
    print("="*80)
    
    try:
        # Query all Obsolete Flow versions
        query = """
            SELECT Id, Definition.DeveloperName, Status, ProcessType 
            FROM Flow 
            WHERE Status = 'Obsolete'
            AND (ProcessType = 'Flow' 
                 OR ProcessType = 'AutoLaunchedFlow' 
                 OR ProcessType = 'Workflow'
                 OR ProcessType = 'InvocableProcess')
        """
        
        result = sf_cli_target._execute_sf_command([
            'data', 'query',
            '--query', query,
            '--use-tooling-api'
        ])
        
        if result and result.get('result', {}).get('records'):
            flows = result['result']['records']
            print(f"\nFound {len(flows)} Obsolete flows to reactivate\n")
            
            success_count = 0
            fail_count = 0
            
            for flow in flows:
                flow_id = flow['Id']
                flow_name = flow.get('Definition', {}).get('DeveloperName', 'Unknown')
                process_type = flow.get('ProcessType', 'Unknown')
                
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
                        print(f"  ✓ Reactivated: {flow_name} ({process_type})")
                        success_count += 1
                    else:
                        print(f"  ✗ Failed to reactivate: {flow_name}")
                        fail_count += 1
                        
                except Exception as e:
                    print(f"  ✗ Error reactivating {flow_name}: {e}")
                    fail_count += 1
            
            print("\n" + "="*80)
            print(f"SUMMARY: {success_count} reactivated, {fail_count} failed")
            print("="*80)
        else:
            print("\n✓ No Obsolete flows found - all flows are already active")
            
    except Exception as e:
        print(f"\n✗ Error querying flows: {e}")
        return False
    
    return True


def disable_bypass_setting(sf_cli_target, bypass_setting_name='Bypass_Automation__c'):
    """
    Disables trigger bypass custom setting.
    """
    print("\n" + "="*80)
    print("DISABLING TRIGGER BYPASS SETTING")
    print("="*80)
    
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
            print(f"\n  ✓ Disabled bypass setting: {setting_id}")
        else:
            print(f"\n  ℹ No bypass setting found (may not be configured)")
            
    except Exception as e:
        print(f"\n  ℹ Could not disable bypass setting: {e}")
        print(f"  Note: This is normal if custom setting doesn't exist")


def main():
    parser = argparse.ArgumentParser(
        description="Emergency recovery: Reactivate all paused Flows and disable trigger bypass"
    )
    parser.add_argument(
        '--target-alias', 
        required=True,
        help='Salesforce org alias for the sandbox'
    )
    args = parser.parse_args()
    
    print("\n" + "="*80)
    print("AUTOMATION RECOVERY SCRIPT")
    print("="*80)
    print(f"Target Org: {args.target_alias}")
    
    # Initialize CLI
    sf_cli_target = SalesforceCLI(target_org=args.target_alias)
    
    # Check if it's a sandbox
    if not sf_cli_target.is_sandbox():
        print(f"\n✗ ERROR: Target '{args.target_alias}' is NOT a sandbox!")
        print("This script should only be run on sandbox orgs for safety.")
        return
    
    print("✓ Verified target is a sandbox\n")
    
    # Reactivate flows
    flows_success = reactivate_all_obsolete_flows(sf_cli_target)
    
    # Disable bypass
    disable_bypass_setting(sf_cli_target)
    
    print("\n" + "="*80)
    if flows_success:
        print("✓ RECOVERY COMPLETED SUCCESSFULLY")
    else:
        print("⚠️  RECOVERY COMPLETED WITH ERRORS")
        print("   Check output above and manually verify automation in Setup")
    print("="*80 + "\n")


if __name__ == "__main__":
    main()
