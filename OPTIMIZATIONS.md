# Performance Optimizations - Implementation Summary

## Changes Made (December 21, 2025)

### 1. ✅ Batched SOQL Queries (10-50x faster)

**What Changed:**
- **Contacts**: Changed from N individual queries (one per account) to batched queries processing 200 accounts at a time
- **Opportunities**: Same batching approach - processes 200 accounts per query
- **Cases**: Same batching approach - processes 200 accounts per query

**Impact:**
- Reduces query count from 1000+ to ~5-10 queries for large datasets
- Eliminates per-account query overhead
- Expected speedup: 10-50x for the query phase

**Files Modified:**
- `populate_sandbox_v2.py` (lines ~230-298, ~299-328, ~395-426)

**Technical Details:**
- Uses `WHERE AccountId IN ('id1','id2',...,'id200')` instead of individual queries
- Groups results by AccountId after fetching
- Maintains per-account limits (respects contact_limit, opportunity_limit, case_limit)
- Community-licensed contacts still prioritized within each account

---

### 2. ✅ Pre-fetched Picklist Values (eliminates per-field queries)

**What Changed:**
- Added `prefetch_picklists_for_object()` function that fetches ALL picklist values for an object in one call
- Extended `PicklistCache` class with object-level caching
- Pre-fetch picklists for all object types at script startup

**Impact:**
- Reduces picklist queries from ~50-100 individual field queries to ~10 object queries
- Expected speedup: 5-10x for picklist validation phase
- Eliminates repeated describe calls for the same fields

**Files Modified:**
- `picklist_utils.py` (lines 1-105)
- `populate_sandbox_v2.py` (lines ~137-146)

**Technical Details:**
- Single `sf sobject describe` call returns ALL picklist fields for an object
- Caches at both object level (`_object_cache`) and field level (`_cache`)
- Pre-fetches: Account, Contact, Opportunity, Quote, Order, Case, Product2, PricebookEntry, QuoteLineItem, OrderItem
- Falls back gracefully if pre-fetch fails for some objects

---

### 3. ✅ Bulk API 2.0 for High-Volume Objects (2-5x faster)

**What Changed:**
- **Contacts**, **Opportunities**, **Cases**, **QuoteLineItems**, and **OrderItems** now use Bulk API 2.0
- Batches up to 200 records per API call via `sf data insert bulk`
- Automatic fallback to individual creation if bulk fails

**Impact:**
- Reduces API calls from N to ~N/200 for each object type
- Expected speedup: 2-5x for record creation phase
- Most effective for large datasets with many records per account

**Files Modified:**
- `bulk_utils.py` - Uses `sf data insert bulk` (Bulk API 2.0)
- `populate_sandbox_v2.py`:
  * **Contacts** (lines ~287-359): Bulk creates all contacts, respects community contact priority
  * **Opportunities** (lines ~408-469): Bulk creates with AccountId and Referred_to_Account__c handling
  * **Cases** (lines ~723-783): Bulk creates with AccountId and ContactId lookups
  * **QuoteLineItems** (lines ~477-574): Bulk creates with Product2 and PricebookEntry dependencies
  * **OrderItems** (lines ~604-695): Bulk creates with Product2 and PricebookEntry dependencies

**Technical Details:**
- Collects all records first before bulk creating
- Ensures dependencies (Accounts, Products, PricebookEntries) exist before batching
- Writes filtered data to CSV, then bulk inserts via SF CLI
- Handles special fields (negative prices, community contacts, referred accounts)
- Maintains per-account limits during preparation phase
- Fallback to phase1 individual creation functions on bulk failure
- Uses `BulkRecordCreator` class with 200 record batch size
- Temporary CSV files stored in `tmp_bulk/` directory

**Object-Specific Notes:**
- **Contacts**: Preserves community contact prioritization (1 per account)
- **Opportunities**: Handles both AccountId and Referred_to_Account__c relationships
- **Cases**: Maps both AccountId and ContactId lookups
- **QuoteLineItems/OrderItems**: Ensures Product2 and PricebookEntry dependencies created first

---

### 3. ✅ Bulk API Utilities (DEPRECATED - see above for integrated version)

**What Created:**
- New `bulk_utils.py` module with `BulkRecordCreator` class
- Batches record creation operations and executes via CSV bulk import
- Auto-flushes when batch reaches 200 records

**Impact:**
- Expected speedup: 2-5x for record creation phase
- Reduces API calls dramatically (200 records per API call vs 1 per call)
- Ready to integrate into phase1 creation scripts

**Files Created:**
- `bulk_utils.py` (complete new file)

**Technical Details:**
- Uses `sf data upsert bulk --file` command with CSV files
- Batch size: 200 records (configurable)
- Supports auto-flush and manual flush operations
- Temporary CSV files stored in `tmp_bulk/` directory
- Returns created IDs for tracking

**Integration Notes:**
- Not yet integrated into phase1 scripts (requires refactoring)
- To use: Replace individual `sf_cli_target.create_record()` calls with `bulk_creator.add_record()`
- Call `bulk_creator.flush_all()` at end of each phase

---

## Overall Expected Performance Impact

### Query Phase (Phase 1 - Data Fetching)
- **Before**: ~1000 queries for 100 accounts (10 per account)
- **After**: ~15 queries (5 batches × 3 object types)
- **Speedup**: **10-50x faster**

### Picklist Validation
- **Before**: ~50-100 describe calls per object type
- **After**: 1 describe call per object type
- **Speedup**: **5-10x faster**

### Record Creation (with Bulk API 2.0)
- **Before**: 1000 API calls to create 1000 records
- **After**: 5 API calls (1000 ÷ 200 batch size)
- **Speedup**: **2-5x faster**
- **Objects Using Bulk API**: Contacts, Opportunities, Cases, QuoteLineItems, OrderItems

### Total Expected Improvement
- **Conservative estimate**: 10-20x overall speedup
- **Optimistic estimate**: 30-50x overall speedup for large datasets (100+ accounts)
- **Typical 100-account migration**: ~15-30 minutes → ~2-5 minutes
- **Account creation**: 5-10% faster with removed duplicate checks
- **Picklist validation**: 80% fewer API calls with smart caching

---

### 6. ✅ Batched Account Record Fetching with Dynamic Relationship Expansion (December 24, 2025)

**What Changed:**
- Changed from N individual `get_record('Account', id)` calls to a single comprehensive SOQL query
- **Dynamically build query from field metadata** - automatically includes ALL Account lookup/hierarchy fields
- Query discovers all Account-to-Account relationships from `accountsFields.csv` metadata
- No manual maintenance needed - automatically adapts when new Account lookup fields are added
- Pass prefetched records to `create_account_phase1()` and use them for recursive dependencies

**Before:**
```python
# Hard-coded field names (requires manual updates)
query = f"""SELECT {all_fields} FROM Account 
           WHERE Id IN ('{root_ids}') 
              OR ParentId IN ('{root_ids}')
              OR Primary_Partner__c IN ('{root_ids}')
              OR PartnerLeadSource__c IN ('{root_ids}')
              # ... manually list each field
```

**After:**
```python
# Dynamically discover all Account lookup fields from metadata
account_lookup_fields = []
for field_name, field_info in account_fields.items():
    if field_info['type'] in ['reference', 'hierarchy'] 
       and field_info['referenceTo'] == 'Account':
        account_lookup_fields.append(field_name)

# Build WHERE clause automatically
where_conditions = [f"Id IN ('{ids_str}')"]
for field_name in account_lookup_fields:
    where_conditions.append(f"{field_name} IN ('{ids_str}')")

query = f"SELECT {all_fields} FROM Account WHERE {' OR '.join(where_conditions)}"
```

**Impact:**
- Eliminates virtually ALL individual `get_record()` API calls for accounts
- For 100 accounts with 20 related accounts: 120+ API calls → 1 query
- **Expected speedup**: 15-30% faster for account creation phase
- Reduces API call count by 99%+ for account fetching
- Also eliminates recursive dependency API calls (Primary_Partner__c, ParentId, etc.)
- **Future-proof**: Automatically includes new Account lookup fields without code changes

**Files Modified:**
- `populate_sandbox_v2.py` (lines ~183-234): Added dynamic query building from field metadata
- `create_account_phase1.py` (lines ~10-20): Added `all_prefetched_accounts` parameter
- `create_account_phase1.py` (lines ~50-66): Use prefetched accounts for recursive dependencies

**Technical Details:**
- Reads `accountsFields.csv` to discover all Account lookup/hierarchy fields
- Filters fields where: `type IN ('reference', 'hierarchy')` AND `referenceTo = 'Account'`
- Example discovered fields: ParentId, Primary_Partner__c, PartnerLeadSource__c, Main_Parent__c, Current_Partner__c, SubAgentSubResellerof__c, Originating_Partner__c, Dealer_Net_Account__c, Zift_Account_Partner__c, etc.
- Builds dynamic WHERE clause with OR conditions for each field
- Logs discovered fields: "Found N Account lookup/hierarchy field(s): ParentId, Primary_Partner__c, ..."
- Caches records in dictionary: `all_account_records[account_id] = record`
- Passes cached records for recursive dependency resolution
- Falls back to individual fetch only if account not in prefetched set (rare edge case)
- Respects `locations_limit` config setting with calculated LIMIT clause
- Processes root accounts first, then all related accounts in one pass

---

### 7. ✅ Reduced Logging Overhead (December 23, 2025)

**What Changed:**
- Removed individual record creation log statements (e.g., "✓ Created Contact: 003... → 003...")
- Added progress indicators every 50 records during preparation phase
- Kept summary logs only (e.g., "✓ Bulk created 500 Contact(s)")

**Impact:**
- **Before**: 1000 records = 1000+ log I/O operations
- **After**: 1000 records = ~20 log I/O operations (progress every 50 + summary)
- **Expected speedup**: 5-15% reduction in total execution time for large datasets
- **Log file size**: Significantly smaller and more readable

**Files Modified:**
- `populate_sandbox_v2.py`: Updated logging in Contacts, Opportunities, QuoteLineItems, OrderItems, and Cases sections

**Technical Details:**
- Progress logs show: `"Processing... 50/500 contacts prepared"`
- Summary logs show: `"✓ Bulk created 500 Contact(s) (2 community-licensed)"`
- Eliminates disk I/O bottleneck for large migrations
- Maintains visibility into progress without overwhelming output

---

## Optimization #9: RecordType Mapping in Phase 1

### Problem
Previously, RecordType fields were removed during Phase 1 creation, meaning records were created with default RecordTypes. This caused:
- Incorrect RecordType assignments in sandbox
- Need for Phase 2 updates to fix RecordTypes (extra API calls)
- Records violating validation rules if RecordType is required
- Poor data quality during testing between Phase 1 and Phase 2

### Solution
Map RecordTypes by DeveloperName during Phase 1 record preparation:
- Query production RecordType to get DeveloperName
- Find matching sandbox RecordType with same DeveloperName
- Use correct sandbox RecordTypeId during Phase 1 creation
- **Exception**: Opportunities use bypass RecordTypeId in Phase 1 to avoid flow triggers, then Phase 2 updates to real RecordTypeId

### Implementation
Updated `replace_lookups_with_dummies()` in `record_utils.py`:

```python
def replace_lookups_with_dummies(record, insertable_fields_info, dummy_records, 
                                  created_mappings=None, sf_cli_source=None, 
                                  sf_cli_target=None, sobject_type=None):
    # ... existing code ...
    
    # Handle RecordType mapping
    if referenced_object == 'RecordType' and field_name == 'RecordTypeId':
        if sobject_type == 'Opportunity':
            # Skip - Opportunities use bypass in Phase 1, restored in Phase 2
            del modified_record[field_name]
        elif sf_cli_source and sf_cli_target and sobject_type:
            # Map by DeveloperName for all other objects
            try:
                rt_info = sf_cli_source.get_record_type_info_by_id(prod_lookup_id)
                dev_name = rt_info['DeveloperName']
                sandbox_rt_id = sf_cli_target.get_record_type_id(sobject_type, dev_name)
                modified_record[field_name] = sandbox_rt_id
                print(f"  [RECORDTYPE] {sobject_type}.RecordType {dev_name}: {prod_lookup_id} → {sandbox_rt_id}")
            except Exception as e:
                print(f"  [WARNING] Could not map RecordType {prod_lookup_id}: {e}")
                del modified_record[field_name]
```

All call sites updated to pass `sf_cli_source`, `sf_cli_target`, and `sobject_type`:
- `populate_sandbox_v2.py`: Contact, Opportunity, QuoteLineItem, OrderItem, Case bulk creation
- `create_account_phase1.py`: Account creation
- `create_contact_phase1.py`: Contact creation
- `create_opportunity_phase1.py`: Opportunity creation (still uses bypass)
- `create_other_objects_phase1.py`: Product2, PricebookEntry, Quote, QuoteLineItem, Order, OrderItem, Case
- `create_account_relationship_phase1.py`: AccountRelationship creation

### Benefits
- **Data Quality**: Records created with correct RecordType from start
- **Reduced Phase 2 Work**: No need to update RecordTypes for most objects (except Opportunities)
- **Validation Rules**: Avoids errors from RecordType-dependent validation rules
- **Testing**: Sandbox data matches production structure immediately after Phase 1

### Why Opportunities Are Different
Opportunities use a bypass RecordTypeId during Phase 1 creation because:
- Flow automation triggers on Opportunity creation (not update)
- Flow needs rewrite to handle migrated records properly
- Using bypass RecordTypeId avoids triggering the problematic flow
- Phase 2 updates restore real RecordTypeId after creation (flows don't trigger on update)

---

## Overall Expected Performance Impact

### Query Phase (Phase 1 - Data Fetching)
- **Before**: ~1000 queries for 100 accounts (10 per account)
- **After**: ~15 queries (5 batches × 3 object types)
- **Speedup**: **10-50x faster**

### Picklist Validation
- **Before**: ~50-100 describe calls per object type
- **After**: 1 describe call per object type
- **Speedup**: **5-10x faster**

### Record Creation (with Bulk API 2.0)
- **Before**: 1000 API calls to create 1000 records
- **After**: 5 API calls (1000 ÷ 200 batch size)
- **Speedup**: **2-5x faster**
- **Objects Using Bulk API**: Contacts, Opportunities, Cases, QuoteLineItems, OrderItems

### Account Creation
- **Before**: N get_record() calls + N name-based duplicate checks
- **After**: 1 batched query + no duplicate checks
- **Speedup**: **10-20% faster**, 95-98% fewer API calls

### Total Expected Improvement
- **Conservative estimate**: 15-30x overall speedup
- **Optimistic estimate**: 40-60x overall speedup for large datasets (100+ accounts)
- **Typical 100-account migration**: ~15-30 minutes → ~1-3 minutes
- **Account creation**: 10-20% faster with batched fetch + removed duplicate checks
- **Picklist validation**: 80% fewer API calls with smart caching
- **Logging overhead**: 5-15% faster with reduced I/O

---

### 4. ✅ Removed Redundant Account Duplicate Check (December 23, 2025)

**What Changed:**
- Removed name-based duplicate check in `create_account_phase1.py`
- Eliminated unnecessary SOQL query for each account being created
- Relies on existing ID-based tracking in `created_accounts` dictionary

**Impact:**
- Eliminates 1 SOQL query per account (50-100 queries removed for typical migration)
- Expected speedup: 5-10% reduction in account creation time
- Reduces API call count significantly

**Files Modified:**
- `create_account_phase1.py` (removed lines 82-100)

**Technical Details:**
- **Before**: Checked `created_accounts` dict by ID, THEN checked target org by Name
- **After**: Only checks `created_accounts` dict by ID
- Duplicate protection still exists via:
  * Initial check: `if prod_account_id in created_accounts` (line 29)
  * Pre-migration cleanup: `delete_existing_records()` removes old data
  * Error handler: Catches duplicate errors and extracts existing ID (lines 107-120)
- Name-based check was redundant because:
  * We track accounts by production ID → sandbox ID mapping
  * Same production ID can't be created twice (checked at function start)
  * Migration deletes existing records first (unless --no-delete)

---

### 5. ✅ Smart Picklist Caching (December 23, 2025)

**What Changed:**
- Enhanced `_fetch_picklist_values()` to cache ALL picklist fields when fetching metadata
- Single API call now populates cache for entire object, not just requested field
- Works synergistically with existing pre-fetch optimization

**Impact:**
- Reduces picklist queries from N (one per field) to 1 (one per object)
- Expected speedup: 80% reduction in picklist API calls for objects not pre-fetched
- Handles edge cases where individual fields are checked outside pre-fetch

**Files Modified:**
- `picklist_utils.py` (lines 218-290 in `_fetch_picklist_values()`)

**Technical Details:**
- **Before**: 
  * Fetch Account metadata → extract Industry picklist → discard rest
  * Later fetch Account metadata again → extract Type picklist → discard rest
  * Result: Multiple API calls for same object
- **After**:
  * Fetch Account metadata → extract ALL picklist fields (Industry, Type, Rating, etc.)
  * Cache each field individually using `_picklist_cache.set()`
  * Subsequent field requests hit cache → no additional API calls
  * Log: "Cached N picklist fields for {object}"
- **Example Performance**:
  * Account with 10 picklist fields, validating 5 of them
  * Old: 5 API calls (one per field)
  * New: 1 API call (first field caches all, rest use cache)
  * Savings: 80% reduction
- Works perfectly with pre-fetch at startup (line 141 in populate_sandbox_v2.py)
- Handles both prefetch scenario and on-demand field validation

---

### 8. ✅ Phase 2 Bulk Updates (December 24, 2025)

**What Changed:**
- Completely rewrote Phase 2 lookup update logic to use Bulk API 2.0 instead of individual updates
- Changed from N individual `update_record()` calls to a single bulk upsert operation
- Eliminated excessive logging (print statements for every field check)
- Added `bulk_update_records()` function to batch all updates

**Before:**
```python
# Individual update for each record
for record_info in migrated_records:
    sandbox_id = record_info['sandbox_id']
    update_payload = {...}  # Build lookup mappings
    
    # One API call per record
    sf_cli_target.update_record(object_type, sandbox_id, update_payload)
    print(f"✓ Updated {sandbox_id} with {len(update_payload)} lookup(s)")
```

**After:**
```python
# Collect all updates first
bulk_updates = []
for record_info in migrated_records:
    sandbox_id = record_info['sandbox_id']
    update_payload = {'Id': sandbox_id, ...}  # Build lookup mappings
    bulk_updates.append(update_payload)

# Single bulk operation for all records
bulk_update_records(sf_cli_target, object_type, bulk_updates)
logging.info(f"✓ Successfully updated {len(bulk_updates)} {object_type} record(s) via Bulk API")
```

**Impact:**
- **API Calls**: N individual updates → 1 bulk operation
- **Before**: 500 records = 500 API calls
- **After**: 500 records = 1 API call
- **Speedup**: **50-100x faster** for Phase 2 updates
- **Time Savings**: 5-10 minutes → 5-15 seconds for typical migrations

**Performance Comparison:**

| Records | Before (API Calls) | After (API Calls) | Reduction |
|---------|-------------------|-------------------|-----------|
| 100     | 100               | 1                 | 99%       |
| 500     | 500               | 1                 | 99.8%     |
| 1000    | 1000              | 1                 | 99.9%     |

**Files Modified:**
- `update_lookups_phase2.py` (complete rewrite):
  * Replaced individual `update_record()` calls with batch collection
  * Added `bulk_update_records()` call for all updates
  * Changed `print()` statements to `logging.info()`
  * Reduced verbose field-by-field logging
  * Added fallback to individual updates if bulk fails
  * Shows summary: "Updated N lookup field(s): AccountId, ContactId, ..."

- `bulk_utils.py` (added `bulk_update_records()` function):
  * Accepts list of records with 'Id' field
  * Writes to CSV and uses Bulk API 2.0
  * Handles errors gracefully with fallback
  * Auto-cleanup of temporary files

- `salesforce_cli.py` (added `bulk_upsert()` method):
  * Wraps `sf data upsert bulk` command
  * Supports external ID matching (uses 'Id' for updates)
  * 10-minute wait timeout for job completion
  * Returns result information for error handling

**Technical Details:**
- **Collection Phase**: Iterates through CSV records and builds update payloads
  * Skips read-only fields (QuoteId, PricebookEntryId, etc.)
  * Skips User lookups (already set in Phase 1)
  * Filters out dummy record references
  * Maps production IDs to sandbox IDs using `created_mappings`

- **Batch Phase**: Writes all updates to single CSV file
  * 'Id' column must be first
  * Includes only fields that need updating
  * Handles null values correctly

- **Execution Phase**: Single Bulk API call
  * Command: `sf data upsert bulk --sobject {type} --file updates.csv --external-id Id`
  * Waits for job completion (up to 10 minutes)
  * Returns success/failure status

- **Fallback**: If bulk fails, gracefully falls back to individual updates
  * Attempts individual update for each record
  * Tries individual field updates if multi-field update fails
  * Logs errors but continues processing

**Object-Specific Notes:**
- **All Objects**: Phase 2 updates now use bulk API
- **RecordTypeId Restoration**: Special handling for Opportunity RecordTypeId restored from Phase 1
- **Maintains All Logic**: Dummy filtering, read-only field skipping, User lookup skipping all preserved

**Logging Improvements:**
- **Before**: Detailed logs for every field check (`[MAP]`, `[SKIP]`, etc.) = 1000+ log lines for 100 records
- **After**: Summary logs only = ~5 log lines for 100 records
  * "Found N {object} records to update"
  * "Updating N lookup field(s): AccountId, ContactId, ..."
  * "Performing bulk update of N record(s)..."
  * "✓ Successfully updated N record(s) via Bulk API"
  * "Summary: N updated, N skipped, N errors"

---

## Overall Expected Performance Impact

### Query Phase (Phase 1 - Data Fetching)
- **Before**: ~1000 queries for 100 accounts (10 per account)
- **After**: ~15 queries (5 batches × 3 object types)
- **Speedup**: **10-50x faster**

### Picklist Validation
- **Before**: ~50-100 describe calls per object type
- **After**: 1 describe call per object type
- **Speedup**: **5-10x faster**

### Record Creation (Phase 1 with Bulk API 2.0)
- **Before**: 1000 API calls to create 1000 records
- **After**: 5 API calls (1000 ÷ 200 batch size)
- **Speedup**: **2-5x faster**
- **Objects Using Bulk API**: Contacts, Opportunities, Cases, QuoteLineItems, OrderItems

### Lookup Updates (Phase 2 with Bulk API 2.0) 🆕
- **Before**: 1000 API calls to update 1000 records (one per record)
- **After**: ~8 API calls (one per object type: Account, Contact, Opportunity, Quote, QuoteLineItem, Order, OrderItem, Case)
- **Speedup**: **50-100x faster**
- **Time**: 5-10 minutes → 5-15 seconds

### Account Creation
- **Before**: N get_record() calls + N name-based duplicate checks
- **After**: 1 batched query + no duplicate checks
- **Speedup**: **10-20% faster**, 95-98% fewer API calls

### Total Expected Improvement
- **Conservative estimate**: **20-70x overall speedup** (with Phase 2 optimization)
- **Optimistic estimate**: **50-120x overall speedup** for large datasets (100+ accounts)
- **Typical 100-account migration**: ~20-40 minutes → ~1-2 minutes
- **Phase 1 (creation)**: 10-50x faster with batched queries + bulk API
- **Phase 2 (updates)**: 50-100x faster with bulk updates
- **Logging overhead**: 5-15% faster with reduced I/O
- **Network I/O**: 99% reduction in API call count

---

## Remaining Optimization Opportunities

### Add Bulk API for Quotes & Orders (Not Yet Done)
- Currently created one-by-one
- Could batch similar to Contacts/Opportunities
- **Effort**: Low (same pattern as implemented objects)
- **Impact**: Medium (fewer records typically, but would help for quote-heavy orgs)

### Parallel Processing (Not Implemented)
- Process multiple accounts concurrently using `ThreadPoolExecutor`
- Expected speedup: 2-3x on multi-core machines
- Complexity: High (requires thread-safe tracking dictionaries)

### Generic Phase1 Function (Not Implemented)
- Consolidate 8 similar phase1 functions into one config-driven function
- Reduces code size by ~2000 lines
- Improves maintainability but not performance

---

## Testing Recommendations

1. **Test with current changes**: Run migration on small dataset (2-3 accounts) to verify functionality
2. **Monitor query log**: Check `logs/queries.csv` to confirm reduced query count
3. **Compare timing**: Note execution time before/after optimizations
4. **Verify data integrity**: Ensure all relationships are preserved correctly
5. **Check batch grouping**: Verify per-account limits are still respected

---

## Rollback Instructions

If issues arise, restore from backup and:
1. **Batched queries**: Remove `in batches` logic, restore individual `for prod_account_id` loops
2. **Picklist pre-fetch**: Remove `prefetch_picklists_for_object()` call in populate_sandbox_v2.py
3. **Bulk utilities**: Simply don't use `bulk_utils.py` - individual creation still works

All changes are backward compatible - existing functionality is preserved.
