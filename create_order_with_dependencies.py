#!/usr/bin/env python3
"""
Order Creation with Dependencies

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

import logging

def create_order_with_dependencies(sf_cli_target, order_data, created_orders, created_quotes):
    """
    Create an Order in Salesforce, ensuring the related Quote exists and deduping by source ID.
    """
    source_id = order_data.get('Source_Id__c')
    if not source_id:
        logging.error('Order missing Source_Id__c, skipping.')
        return None
    if source_id in created_orders:
        logging.info(f"Order with Source_Id__c {source_id} already created.")
        return created_orders[source_id]
    # Ensure Quote exists
    quote_source_id = order_data.get('Quote_Source_Id__c')
    if quote_source_id and quote_source_id in created_quotes:
        order_data['QuoteId'] = created_quotes[quote_source_id]
    else:
        logging.error(f"Quote for Order {source_id} not found, skipping.")
        return None
    # TODO: Insert Order using Salesforce CLI or API
    # fake_id = '801xx00000FakeOrderId'  # Replace with real insert logic
    fake_id = f'801xx00000FakeOrderId{source_id[-4:]}'
    created_orders[source_id] = fake_id
    logging.info(f"Created Order {source_id} as {fake_id}")
    return fake_id
