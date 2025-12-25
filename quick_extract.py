#!/usr/bin/env python3
import subprocess
import json
import csv

objects = ['QuoteLineItem', 'OrderItem', 'Product2', 'PricebookEntry', 'Pricebook2']

for obj in objects:
    print(f'Extracting {obj}...')
    result = subprocess.run(['sf', 'sobject', 'describe', '--sobject', obj, '--json', '--target-org', 'KBRILL2'], 
                          capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    
    fields = []
    for field in data['result']['fields']:
        if field.get('createable'):
            ref = field['referenceTo'][0] if field.get('referenceTo') else ''
            fields.append({
                'Field Name': field['name'],
                'Field Type': field['type'],
                'Reference To': ref,
                'Nillable': str(field.get('nillable', True)).lower()
            })
    
    filename = f'fieldData/{obj.lower()}Fields.csv'
    with open(filename, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['Field Name', 'Field Type', 'Reference To', 'Nillable'])
        writer.writeheader()
        writer.writerows(fields)
    
    required = len([f for f in fields if f['Nillable'] == 'false'])
    print(f'  → Wrote {len(fields)} fields ({required} required)')

print('Done!')
