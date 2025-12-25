#!/usr/bin/env python3
"""
Field Metadata Extraction Utilities

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

import os
import csv
import xml.etree.ElementTree as ET

def is_safe_to_insert(field_file_path):
    """
    Checks if a Salesforce field is safe to insert based on its metadata.
    Excludes formula fields, summary fields, autonumber fields, and specific standard fields.
    """
    try:
        tree = ET.parse(field_file_path)
        root = tree.getroot()
        
        # Namespace for finding tags
        namespace = {'sf': 'http://soap.sforce.com/2006/04/metadata'}

        # 1. Exclude formula fields
        if root.find('sf:formula', namespace) is not None:
            return False

        # 2. Exclude summary fields
        if root.find('sf:summaryForeignKey', namespace) is not None:
            return False

        field_type_element = root.find('sf:type', namespace)
        if field_type_element is not None:
            # 3. Exclude AutoNumber fields
            if field_type_element.text == 'AutoNumber':
                return False
            # 4. Exclude Geolocation fields (often have special considerations)
            if field_type_element.text == 'Location':
                return False

        # 5. Exclude known non-insertable standard fields by name
        fullName_element = root.find('sf:fullName', namespace)
        if fullName_element is not None:
            field_name = fullName_element.text
            # It's better to check for standard fields that are known to be non-insertable
            # This is a basic list, a more comprehensive one might be needed for a real-world scenario
            non_insertable_standard_fields = [
                'Id', 'IsDeleted', 'CreatedDate', 'CreatedById', 'LastModifiedDate', 
                'LastModifiedById', 'SystemModstamp', 'LastActivityDate', 'LastViewedDate',
                'LastReferencedDate', 'OwnerId'
            ]
            if field_name in non_insertable_standard_fields:
                return False

        return True
    except ET.ParseError:
        print(f"Warning: Could not parse XML file: {field_file_path}")
        return False

def extract_safe_fields(fields_directory):
    """
    Extracts field names, types, and reference-to objects (for Lookups) 
    that are safe for insertion from .field-meta.xml files.
    """
    safe_fields = []
    for filename in os.listdir(fields_directory):
        if filename.endswith('.field-meta.xml'):
            file_path = os.path.join(fields_directory, filename)
            if is_safe_to_insert(file_path):
                try:
                    tree = ET.parse(file_path)
                    root = tree.getroot()
                    namespace = {'sf': 'http://soap.sforce.com/2006/04/metadata'}
                    
                    fullName_element = root.find('sf:fullName', namespace)
                    type_element = root.find('sf:type', namespace)
                    
                    if fullName_element is not None and type_element is not None:
                        field_data = {
                            'name': fullName_element.text,
                            'type': type_element.text,
                            'referenceTo': '' # Default to empty string
                        }
                        
                        if type_element.text == 'Lookup':
                            referenceTo_element = root.find('sf:referenceTo', namespace)
                            if referenceTo_element is not None:
                                field_data['referenceTo'] = referenceTo_element.text

                        safe_fields.append(field_data)
                except ET.ParseError:
                    # Warning already printed in is_safe_to_insert
                    continue
    return safe_fields

def write_to_csv(fields, output_file):
    """
    Writes the list of fields to a CSV file.
    """
    if not fields:
        print("No safe fields found to write to CSV.")
        return

    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ['Field Name', 'Field Type', 'Reference To']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')

        writer.writeheader()
        for field in fields:
            writer.writerow({
                'Field Name': field['name'], 
                'Field Type': field['type'],
                'Reference To': field.get('referenceTo', '')
            })
    print(f"Successfully wrote {len(fields)} fields to {output_file}")


if __name__ == "__main__":
    # Correctly navigate up one level from 'populateDemoData' to the project root
    project_root = os.path.dirname(os.path.abspath(__file__))
    fields_dir = os.path.join(project_root, '..', 'KBRILL', 'force-app', 'main', 'default', 'objects', 'Account', 'fields')
    output_csv_file = os.path.join(project_root, 'fieldData', 'accountsFields.csv')

    # Normalize the path to resolve '..'
    fields_dir = os.path.normpath(fields_dir)

    if not os.path.isdir(fields_dir):
        print(f"Error: Directory not found at {fields_dir}")
    else:
        safe_account_fields = extract_safe_fields(fields_dir)
        write_to_csv(safe_account_fields, output_csv_file)
