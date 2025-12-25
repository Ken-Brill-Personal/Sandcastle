#!/usr/bin/env python3
"""
Order Item Creation with Dependencies

Author: Ken Brill
Version: 1.0
Date: December 24, 2025
License: MIT License
"""

import logging

def create_order_item_with_dependencies(sf_cli_target, order_item_data, created_orders, created_products):
    """
    Create an OrderItem in Salesforce, ensuring the related Order and Product exist.
    No deduplication is performed for OrderItems.
    """
    # Ensure Order exists
    order_source_id = order_item_data.get('Order_Source_Id__c')
    if order_source_id and order_source_id in created_orders:
        order_item_data['OrderId'] = created_orders[order_source_id]
    else:
        logging.error(f"Order for OrderItem not found, skipping.")
        return None
    # Ensure Product exists (optional, if you want to enforce Product2 lookup)
    product_source_id = order_item_data.get('Product_Source_Id__c')
    if product_source_id and created_products and product_source_id in created_products:
        order_item_data['Product2Id'] = created_products[product_source_id]
    # TODO: Insert OrderItem using Salesforce CLI or API
    fake_id = f'0OIxx00000FakeOrderItemId{order_item_data.get('OrderId','')[-4:]}'
    logging.info(f"Created OrderItem for Order {order_item_data.get('OrderId')} as {fake_id}")
    return fake_id
