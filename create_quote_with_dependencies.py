#!/usr/bin/env python3
"""
Quote Creation with Dependencies

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

import logging

def create_quote_with_dependencies(sf_cli_target, quote_data, created_quotes, created_opportunities):
    """
    Create a Quote in Salesforce, ensuring the related Opportunity exists and deduping by source ID.
    """
    source_id = quote_data.get('Source_Id__c')
    if not source_id:
        logging.error('Quote missing Source_Id__c, skipping.')
        return None
    if source_id in created_quotes:
        logging.info(f"Quote with Source_Id__c {source_id} already created.")
        return created_quotes[source_id]
    # Ensure Opportunity exists
    opp_source_id = quote_data.get('Opportunity_Source_Id__c')
    if opp_source_id and opp_source_id in created_opportunities:
        quote_data['OpportunityId'] = created_opportunities[opp_source_id]
    else:
        logging.error(f"Opportunity for Quote {source_id} not found, skipping.")
        return None
    # TODO: Insert Quote using Salesforce CLI or API
    # fake_id = '0Q0xx00000FakeQuoteId'  # Replace with real insert logic
    fake_id = f'0Q0xx00000FakeQuoteId{source_id[-4:]}'
    created_quotes[source_id] = fake_id
    logging.info(f"Created Quote {source_id} as {fake_id}")
    return fake_id
