#!/usr/bin/env python3
"""
Duplicate Record Detection

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License

Module for checking duplicates in Salesforce target org.
"""

def find_existing_record(sf_cli_target, object_name, unique_fields, record):
    """
    Checks for an existing record in the target org by unique fields.
    Args:
        sf_cli_target: SalesforceCLI instance for the target org.
        object_name (str): Salesforce object name (e.g., 'Account', 'Contact').
        unique_fields (list): List of field names to use for uniqueness (e.g., ['Name'] or ['FirstName', 'LastName']).
        record (dict): The record data from the source org.
    Returns:
        str or None: The Id of the existing record if found, else None.
    """
    if not unique_fields or not record:
        return None
    # Build WHERE clause
    where_clauses = []
    for field in unique_fields:
        value = record.get(field)
        if value is None:
            return None  # Can't check if any unique field is missing
        # Escape single quotes for SOQL
        value = str(value).replace("'", "\\'")
        where_clauses.append(f"{field} = '{value}'")
    where_str = ' AND '.join(where_clauses)
    query = f"SELECT Id FROM {object_name} WHERE {where_str} LIMIT 1"
    existing = sf_cli_target.query_records(query)
    if existing and len(existing) > 0:
        return existing[0]['Id']
    return None
