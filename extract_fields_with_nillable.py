#!/usr/bin/env python3
"""
Enhanced Field Extraction Script with Nillable Information

This script extracts insertable fields from Salesforce objects and includes
nillable status to help prevent accidentally removing required fields during migration.

Author: Ken Brill
Version: 1.0.1
Date: December 25, 2025
License: MIT License

Usage:
    python extract_fields_with_nillable.py -a <org-alias>
    python extract_fields_with_nillable.py  # Uses default org
"""

import os
import csv
import json
import subprocess
import argparse

def get_sobject_describe(object_name, alias=None):
    """
    Executes the 'sf sobject describe' command against a specific org alias
    and returns the parsed JSON.
    """
    try:
        command = ["sf", "sobject", "describe", "--sobject", object_name, "--json"]
        if alias:
            command.extend(["--target-org", alias])
            
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except FileNotFoundError:
        print("Error: 'sf' command not found. Make sure the Salesforce CLI is installed and in your PATH.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"Error executing 'sf sobject describe' for {object_name} on alias '{alias}':")
        print(e.stderr)
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not parse JSON output for {object_name} on alias '{alias}'.")
        return None

def get_insertable_fields(describe_json):
    """
    Parses the describe JSON to find all fields that are creatable.
    Now includes nillable status to identify required vs optional fields.
    """
    safe_fields = []
    if describe_json and describe_json.get("status") == 0:
        for field in describe_json["result"]["fields"]:
            if field.get("createable"):
                reference_to = ''
                if field.get('referenceTo') and len(field['referenceTo']) > 0:
                    # Taking the first reference, as a field can only point to one object at a time in this context
                    reference_to = field['referenceTo'][0]

                safe_fields.append({
                    'name': field['name'],
                    'type': field['type'],
                    'referenceTo': reference_to,
                    'nillable': field.get('nillable', True)  # True means field can be null (optional)
                })
    return safe_fields

def write_to_csv(fields, output_file):
    """
    Writes the list of fields to a CSV file, including nillable status.
    """
    if not fields:
        print(f"No insertable fields found to write to {output_file}.")
        return

    # Ensure the directory exists
    output_dir = os.path.dirname(output_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ['Field Name', 'Field Type', 'Reference To', 'Nillable']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        for field in fields:
            writer.writerow({
                'Field Name': field['name'], 
                'Field Type': field['type'],
                'Reference To': field.get('referenceTo', ''),
                'Nillable': str(field.get('nillable', True)).lower()  # Convert bool to lowercase string
            })
    
    # Count required fields for reporting
    required_fields = [f for f in fields if not f.get('nillable', True)]
    print(f"Successfully wrote {len(fields)} fields to {output_file}")
    print(f"  → {len(required_fields)} required fields (nillable=false)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract insertable fields from Salesforce SObjects with nillable information.")
    parser.add_argument('-a', '--alias', help='Salesforce org alias to run the command against.')
    args = parser.parse_args()

    objects_to_process = [
        'Account', 'Contact', 'Case', 'Opportunity', 'Order', 
        'Lead', 'Quote', 'QuoteLineItem', 'OrderItem',
        'Product2', 'Pricebook2', 'PricebookEntry'
    ]
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_base_dir = os.path.join(script_dir, 'fieldData')

    print("=" * 60)
    print("Enhanced Field Extraction with Nillable Information")
    print("=" * 60)
    if args.alias:
        print(f"Target Org: {args.alias}")
    else:
        print("Target Org: Default")
    print()

    for obj_name in objects_to_process:
        print(f"Processing: {obj_name}")
        
        describe_data = get_sobject_describe(obj_name, args.alias)
        if describe_data:
            insertable_fields = get_insertable_fields(describe_data)
            output_csv_file = os.path.join(output_base_dir, f'{obj_name.lower()}Fields.csv')
            write_to_csv(insertable_fields, output_csv_file)
        print()

    print("=" * 60)
    print("Field extraction complete!")
    print("=" * 60)
