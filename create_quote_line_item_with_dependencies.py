#!/usr/bin/env python3
"""
Quote Line Item Creation with Dependencies

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

import logging

def create_quote_line_item_with_dependencies(sf_cli_target, qli_data, created_qlis, created_quotes, created_products):
    """
    Create a QuoteLineItem in Salesforce, ensuring the related Quote and Product exist and deduping by source ID.
    """
    source_id = qli_data.get('Source_Id__c')
    if not source_id:
        logging.error('QuoteLineItem missing Source_Id__c, skipping.')
        return None
    if source_id in created_qlis:
        logging.info(f"QuoteLineItem with Source_Id__c {source_id} already created.")
        return created_qlis[source_id]
    # Ensure Quote exists
    quote_source_id = qli_data.get('Quote_Source_Id__c')
    if quote_source_id and quote_source_id in created_quotes:
        qli_data['QuoteId'] = created_quotes[quote_source_id]
    else:
        logging.error(f"Quote for QuoteLineItem {source_id} not found, skipping.")
        return None
    # Ensure Product exists (optional, if you want to enforce Product2 lookup)
    product_source_id = qli_data.get('Product_Source_Id__c')
    if product_source_id and created_products and product_source_id in created_products:
        qli_data['Product2Id'] = created_products[product_source_id]
    # TODO: Insert QuoteLineItem using Salesforce CLI or API
    fake_id = f'0QLxx00000FakeQLIId{source_id[-4:]}'
    created_qlis[source_id] = fake_id
    logging.info(f"Created QuoteLineItem {source_id} as {fake_id}")
    return fake_id
