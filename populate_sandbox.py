#!/usr/bin/env python3
"""
Legacy Populate Sandbox Script

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

import os
import json
import argparse
from salesforce_cli import SalesforceCLI
from record_utils import load_insertable_fields
from delete_existing_records import delete_existing_records
from dummy_records import create_dummy_records
from csv_utils import clear_migration_csvs
from create_account_phase1 import create_account_phase1
from create_contact_phase1 import create_contact_phase1
from create_opportunity_phase1 import create_opportunity_phase1
from create_other_objects_phase1 import (
    create_quote_phase1, create_quote_line_item_phase1,
    create_order_phase1, create_order_item_phase1, create_case_phase1
)
from update_lookups_phase2 import update_lookups_phase2



def main():
    parser = argparse.ArgumentParser(description="Populate Salesforce sandbox with demo data from production (Two-Phase Approach).")
    parser.add_argument('-s', '--source-alias', help='Salesforce org alias for the production/source org.')
    parser.add_argument('-t', '--target-alias', help='Salesforce org alias for the sandbox/target org.')
    parser.add_argument('--no-delete', action='store_true', help='Skip the deletion of existing records in the sandbox.')
    args = parser.parse_args()
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'config.json')
    config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
    else:
        print(f"Error: config.json not found at {config_path}. This file is required.")
        return

    # Determine source org alias
    source_org_alias = args.source_alias
    if not source_org_alias and "source_prod_alias" in config:
        source_org_alias = config["source_prod_alias"]
    if not source_org_alias:
        print("Error: Source org alias not provided. Use --source-alias or configure 'source_prod_alias' in config.json.")
        return

    # Determine target org alias
    target_org_alias = args.target_alias
    if not target_org_alias and "target_sandbox_alias" in config:
        target_org_alias = config["target_sandbox_alias"]
    if not target_org_alias:
        print("Error: Target org alias not provided. Use --target-alias or configure 'target_sandbox_alias' in config.json.")
        return

    # Initialize SalesforceCLI for source and target orgs
    sf_cli_source = SalesforceCLI(target_org=source_org_alias)
    sf_cli_target = SalesforceCLI(target_org=target_org_alias)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, 'config.json')

    config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
    else:
        print(f"Error: config.json not found at {config_path}. This file is required.")
        return

    # Determine source org alias
    source_org_alias = args.source_alias
    if not source_org_alias and "source_prod_alias" in config:
        source_org_alias = config["source_prod_alias"]
    if not source_org_alias:
        print("Error: Source org alias not provided. Use --source-alias or configure 'source_prod_alias' in config.json.")
        return

    # Determine target org alias
    target_org_alias = args.target_alias
    if not target_org_alias and "target_sandbox_alias" in config:
        target_org_alias = config["target_sandbox_alias"]
    if not target_org_alias:
        print("Error: Target org alias not provided. Use --target-alias or configure 'target_sandbox_alias' in config.json.")
        return

    # Initialize SalesforceCLI for source and target orgs
    sf_cli_source = SalesforceCLI(target_org=source_org_alias)
    sf_cli_target = SalesforceCLI(target_org=target_org_alias)

    print(f"Connecting to Source Org: {source_org_alias}")
    print(f"Connecting to Target Org: {target_org_alias}")

    try:
        # Safety check: Ensure target is a sandbox
        if not sf_cli_target.is_sandbox():
            print(f"\nERROR: The target Salesforce org '{target_org_alias}' is NOT a sandbox. Aborting operation to prevent data loss in production.")
            return

        # Safety check: Ensure source is NOT the target sandbox (to prevent accidental overwrite/loops)
        # Compare instance URLs to be more robust than just aliases
        source_org_info = sf_cli_source.get_org_info()
        target_org_info = sf_cli_target.get_org_info()

        if source_org_info and target_org_info and source_org_info['instanceUrl'] == target_org_info['instanceUrl']:
            print(f"\nERROR: The source org '{source_org_alias}' and target org '{target_org_alias}' are the SAME. Aborting operation.")
            print("Please ensure you specify different source and target orgs.")
            return
        
        # Additional safety: Warn if source is also a sandbox, but allow if different from target
        if sf_cli_source.is_sandbox():
            print(f"Warning: The source org '{source_org_alias}' is also a sandbox. Proceeding as it is different from the target.")
        else:
            print(f"Source org '{source_org_alias}' is a production org (or non-sandbox).")


        print(f"Successfully connected to sandbox org: {target_org_alias}")
        print(f"Successfully connected to source org: {source_org_alias}")

        # --- Delete existing records ---
        delete_existing_records(sf_cli_target, args, target_org_alias)

        # --- Clear previous migration CSV files ---
        print("\n--- Clearing previous migration CSVs ---")
        clear_migration_csvs(script_dir)

        # --- Create Dummy Records for Phase 1 ---
        dummy_records = create_dummy_records(sf_cli_target)

        # --- Load field metadata ---
        print("\n--- Loading field metadata ---")
        account_insertable_fields_info = load_insertable_fields('Account', script_dir)
        contact_insertable_fields_info = load_insertable_fields('Contact', script_dir)
        opportunity_insertable_fields_info = load_insertable_fields('Opportunity', script_dir)
        
        if not account_insertable_fields_info:
            print("Error: No insertable Account fields found. Cannot proceed.")
            return

        # Initialize tracking dictionaries
        created_accounts = {}
        created_contacts = {}
        created_opportunities = {}
        created_quotes = {}
        created_qlis = {}
        created_orders = {}
        created_order_items = {}
        created_cases = {}

        # ========== PHASE 1: CREATE ALL RECORDS WITH DUMMY LOOKUPS ==========
        print("\n" + "="*80)
        print("PHASE 1: CREATING RECORDS WITH DUMMY LOOKUPS")
        print("="*80)


        # Main entry for processing accounts
        if "Accounts" not in config or not config["Accounts"]:
            print("No Account IDs found in config.json to process.")
            return
        
        print(f"\n--- Phase 1: Root Accounts ---")
        for prod_account_id in config["Accounts"]:
            create_account_phase1(
                prod_account_id, created_accounts, account_insertable_fields_info,
                sf_cli_source, sf_cli_target, dummy_records, script_dir
            )
        
        # Create child accounts (locations)
        print(f"\n--- Phase 1: Location Accounts ---")
        locations_limit = config.get("locations_limit", 10)
        if locations_limit == 0:
            print("Skipping locations (locations_limit is 0)")
        else:
            for prod_account_id in list(created_accounts.keys()):
                if locations_limit == -1:
                    location_query = f"SELECT Id FROM Account WHERE ParentId = '{prod_account_id}' ORDER BY CreatedDate DESC"
                else:
                    location_query = f"SELECT Id FROM Account WHERE ParentId = '{prod_account_id}' ORDER BY CreatedDate DESC LIMIT {locations_limit}"
                child_accounts = sf_cli_source.query_records(location_query)
                for child in child_accounts:
                    child_account_id = child['Id']
                    if child_account_id not in created_accounts:
                        create_account_phase1(
                            child_account_id, created_accounts, account_insertable_fields_info,
                            sf_cli_source, sf_cli_target, dummy_records, script_dir
                        )
        
        # Create contacts
        print(f"\n--- Phase 1: Contacts ---")
        contact_limit = config.get('contact_limit', 10)
        if contact_limit == 0:
            print("Skipping contacts (contact_limit is 0)")
        else:
            for prod_account_id in list(config["Accounts"]):
                if contact_limit == -1:
                    contact_query = f"SELECT Id FROM Contact WHERE AccountId = '{prod_account_id}' ORDER BY CreatedDate DESC"
                else:
                    contact_query = f"SELECT Id FROM Contact WHERE AccountId = '{prod_account_id}' ORDER BY CreatedDate DESC LIMIT {contact_limit}"
                related_contacts = sf_cli_source.query_records(contact_query)
                for contact in related_contacts:
                    prod_contact_id = contact['Id']
                    if prod_contact_id not in created_contacts:
                        create_contact_phase1(
                            prod_contact_id, created_contacts, contact_insertable_fields_info,
                            sf_cli_source, sf_cli_target, dummy_records, script_dir
                        )
        
        # Create opportunities
        print(f"\n--- Phase 1: Opportunities ---")
        opportunity_limit = config.get('opportunity_limit', 10)
        if opportunity_limit == 0:
            print("Skipping opportunities (opportunity_limit is 0)")
        else:
            for prod_account_id in list(config["Accounts"]):
                if opportunity_limit == -1:
                    opportunity_query = f"SELECT Id FROM Opportunity WHERE AccountId = '{prod_account_id}' ORDER BY CreatedDate DESC"
                else:
                    opportunity_query = f"SELECT Id FROM Opportunity WHERE AccountId = '{prod_account_id}' ORDER BY CreatedDate DESC LIMIT {opportunity_limit}"
                related_opps = sf_cli_source.query_records(opportunity_query)
                for opp in related_opps:
                    prod_opp_id = opp['Id']
                    if prod_opp_id not in created_opportunities:
                        create_opportunity_phase1(
                            prod_opp_id, created_opportunities, opportunity_insertable_fields_info,
                            sf_cli_source, sf_cli_target, dummy_records, script_dir
                        )
                                    opp_record,
                                    created_opportunities,
                                    created_accounts,
                                    config,
                                    sf_cli_source,
                                    created_contacts,
                                    contact_insertable_fields_info
                                )
                                count += 1
                    else:
                        print(f"No related opportunities found for account {prod_account_id} in the source org.")

            # --- Create Quotes related to created Opportunities ---
            print("\n--- Creating Quotes related to created Opportunities ---")
            quote_limit = config.get('quote_limit', 10)
            # Handle special limit values: -1 = all records, 0 = no records
            if quote_limit == 0:
                print("Skipping quotes (quote_limit is 0)")
            else:
                for prod_opp_id in list(created_opportunities.keys()):
                    if quote_limit == -1:
                        quote_query = f"SELECT Id, OpportunityId FROM Quote WHERE OpportunityId = '{prod_opp_id}' ORDER BY CreatedDate DESC"
                    else:
                        quote_query = f"SELECT Id, OpportunityId FROM Quote WHERE OpportunityId = '{prod_opp_id}' ORDER BY CreatedDate DESC LIMIT {quote_limit}"
                    related_quotes = sf_cli_source.query_records(quote_query)
                    if related_quotes:
                        count = 0
                        for quote in related_quotes:
                            if quote_limit != -1 and count >= quote_limit:
                                break
                            prod_quote_id = quote['Id']
                            if prod_quote_id not in created_quotes:
                                # Fetch full Quote record
                                quote_record = sf_cli_source.get_record('Quote', prod_quote_id)
                                if not quote_record:
                                    continue
                                # Add Source_Id__c and Opportunity_Source_Id__c for dependency
                                quote_record['Source_Id__c'] = prod_quote_id
                                quote_record['Opportunity_Source_Id__c'] = quote_record.get('OpportunityId')
                                create_quote_with_dependencies(
                                    sf_cli_target,
                                    quote_record,
                                    created_quotes,
                                    created_opportunities
                                )
                                count += 1
                    else:
                        print(f"No related quotes found for opportunity {prod_opp_id} in the source org.")

            # --- Create QuoteLineItems related to created Quotes ---
            print("\n--- Creating QuoteLineItems related to created Quotes ---")
            qli_limit = config.get('quote_line_item_limit', 20)
            # Handle special limit values: -1 = all records, 0 = no records
            if qli_limit == 0:
                print("Skipping quote line items (quote_line_item_limit is 0)")
            else:
                # If you want to enforce Product2 lookups, you can add a created_products dictionary and logic
                created_products = None  # Placeholder, implement if needed
                for prod_quote_id in list(created_quotes.keys()):
                    if qli_limit == -1:
                        qli_query = f"SELECT Id, QuoteId FROM QuoteLineItem WHERE QuoteId = '{prod_quote_id}' ORDER BY CreatedDate DESC"
                    else:
                        qli_query = f"SELECT Id, QuoteId FROM QuoteLineItem WHERE QuoteId = '{prod_quote_id}' ORDER BY CreatedDate DESC LIMIT {qli_limit}"
                    related_qlis = sf_cli_source.query_records(qli_query)
                    if related_qlis:
                        count = 0
                        for qli in related_qlis:
                            if qli_limit != -1 and count >= qli_limit:
                                break
                            prod_qli_id = qli['Id']
                            if prod_qli_id not in created_qlis:
                                # Fetch full QLI record
                                qli_record = sf_cli_source.get_record('QuoteLineItem', prod_qli_id)
                                if not qli_record:
                                    continue
                                # Add Source_Id__c and Quote_Source_Id__c for dependency
                                qli_record['Source_Id__c'] = prod_qli_id
                                qli_record['Quote_Source_Id__c'] = qli_record.get('QuoteId')
                                create_quote_line_item_with_dependencies(
                                    sf_cli_target,
                                    qli_record,
                                    created_qlis,
                                    created_quotes,
                                    created_products
                                )
                            count += 1
                else:
                    print(f"No related QuoteLineItems found for quote {prod_quote_id} in the source org.")


            # --- Create Orders related to created Quotes ---
            print("\n--- Creating Orders related to created Quotes ---")
            order_limit = config.get('order_limit', 10)
            for prod_quote_id in list(created_quotes.keys()):
                order_query = f"SELECT Id, QuoteId FROM Order WHERE QuoteId = '{prod_quote_id}' LIMIT {order_limit}"
                related_orders = sf_cli_source.query_records(order_query)
                if related_orders:
                    count = 0
                    for order in related_orders:
                        if count >= order_limit:
                            break
                        prod_order_id = order['Id']
                        if prod_order_id not in created_orders:
                            # Fetch full Order record
                            order_record = sf_cli_source.get_record('Order', prod_order_id)
                            if not order_record:
                                continue
                            # Add Source_Id__c and Quote_Source_Id__c for dependency
                            order_record['Source_Id__c'] = prod_order_id
                            order_record['Quote_Source_Id__c'] = order_record.get('QuoteId')
                            create_order_with_dependencies(
                                sf_cli_target,
                                order_record,
                                created_orders,
                                created_quotes
                            )
                            count += 1
                else:
                    print(f"No related orders found for quote {prod_quote_id} in the source org.")

            # --- Create OrderItems related to created Orders ---
            print("\n--- Creating OrderItems related to created Orders ---")
            order_item_limit = config.get('order_item_limit', 20)
            created_products = None  # Placeholder, implement if needed
            for prod_order_id in list(created_orders.keys()):
                order_item_query = f"SELECT Id, OrderId FROM OrderItem WHERE OrderId = '{prod_order_id}' LIMIT {order_item_limit}"
                related_order_items = sf_cli_source.query_records(order_item_query)
                if related_order_items:
                    count = 0
                    for order_item in related_order_items:
                        if count >= order_item_limit:
                            break
                        prod_order_item_id = order_item['Id']
                        # Fetch full OrderItem record
                        order_item_record = sf_cli_source.get_record('OrderItem', prod_order_item_id)
                        if not order_item_record:
                            continue
                        # Add Order_Source_Id__c for dependency
                        order_item_record['Order_Source_Id__c'] = order_item_record.get('OrderId')
                        create_order_item_with_dependencies(
                            sf_cli_target,
                            order_item_record,
                            created_orders,
                            created_products
                        )
                        count += 1
                else:
                    print(f"No related OrderItems found for order {prod_order_id} in the source org.")

            # After all accounts, locations, and contacts are created, find and create all related cases
            print("\n--- Creating Cases related to created Accounts ---")
            case_limit = config.get('case_limit', 5)
            case_insertable_fields_info = load_insertable_fields('Case', script_dir)
            from create_case_with_dependencies import create_case_with_dependencies
            for prod_account_id in list(created_accounts.keys()):
                case_query = f"SELECT Id FROM Case WHERE AccountId = '{prod_account_id}' LIMIT {case_limit}"
                related_cases = sf_cli_source.query_records(case_query)
                if related_cases:
                    count = 0
                    for case in related_cases:
                        if count >= case_limit:
                            break
                        prod_case_id = case['Id']
                        if prod_case_id not in created_cases:
                            create_case_with_dependencies(
                                prod_case_id,
                                created_cases,
                                case_insertable_fields_info,
                                created_accounts,
                                created_contacts,
                                sf_cli_source,
                                sf_cli_target
                            )
                            count += 1
                else:
                    print(f"No related cases found for account {prod_account_id} in the source org.")
        else:
            print("No Account IDs found in config.json to process.")
        
        # Print summary statistics based on what was actually created
        print("\n" + "="*80)
        print("MIGRATION SUMMARY")
        print("="*80)
        
        summary_data = [
            ('Accounts', len(created_accounts)),
            ('Contacts', len(created_contacts)),
            ('Opportunities', len(created_opportunities)),
            ('Quotes', len(created_quotes)),
            ('Quote Line Items', len(created_qlis)),
            ('Orders', len(created_orders)),
            ('Cases', len(created_cases)),
        ]
        
        total_records = 0
        for obj_type, count in summary_data:
            if count > 0:
                print(f"  {obj_type:<20} {count:>6} record(s)")
                total_records += count
        
        print(f"  {'-'*28}")
        print(f"  {'TOTAL':<20} {total_records:>6} record(s)")
        print("="*80)
        print("\nNote: This count includes both newly created and existing records that were found/reused.")
        print("Check the output above for specific warnings and errors about records that failed to create.")
        print("="*80)

    except RuntimeError as e:
        print(f"CLI Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    else:
        print("\nAll done! Data population script completed successfully.")




if __name__ == "__main__":
    main()
