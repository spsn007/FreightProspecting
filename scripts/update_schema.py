with open('src/backend/db/schema.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace triggers
old_triggers = """-- Outreach Logs Append-Only Protection Triggers (AUD-025)
CREATE TRIGGER IF NOT EXISTS trg_outreach_logs_no_update
BEFORE UPDATE ON outreach_logs
WHEN NOT EXISTS (
    SELECT 1 FROM settings 
    WHERE setting_key = 'allow_outreach_mutation' AND setting_value = 'true'
)
BEGIN
    SELECT RAISE(ABORT, 'outreach_logs is append-only: UPDATE operations are strictly prohibited.');
END;

CREATE TRIGGER IF NOT EXISTS trg_outreach_logs_no_delete
BEFORE DELETE ON outreach_logs
WHEN NOT EXISTS (
    SELECT 1 FROM settings 
    WHERE setting_key = 'allow_outreach_mutation' AND setting_value = 'true'
)
BEGIN
    SELECT RAISE(ABORT, 'outreach_logs is append-only: DELETE operations are strictly prohibited.');
END;"""

new_triggers = """-- Outreach Logs Append-Only Protection Triggers (AUD-025: Unconditional)
CREATE TRIGGER IF NOT EXISTS trg_outreach_logs_no_update
BEFORE UPDATE ON outreach_logs
BEGIN
    SELECT RAISE(ABORT, 'outreach_logs is append-only: UPDATE operations are strictly prohibited.');
END;

CREATE TRIGGER IF NOT EXISTS trg_outreach_logs_no_delete
BEFORE DELETE ON outreach_logs
BEGIN
    SELECT RAISE(ABORT, 'outreach_logs is append-only: DELETE operations are strictly prohibited.');
END;

-- Load Opportunities Rate & Margin Integrity Triggers (AUD-014)
CREATE TRIGGER IF NOT EXISTS trg_load_opps_validate_rates_insert
BEFORE INSERT ON load_opportunities
BEGIN
    SELECT RAISE(ABORT, 'shipper_target_rate cannot be negative')
    WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.shipper_target_rate < 0;
    
    SELECT RAISE(ABORT, 'carrier_target_cost cannot be negative')
    WHERE NEW.carrier_target_cost IS NOT NULL AND NEW.carrier_target_cost < 0;
END;

CREATE TRIGGER IF NOT EXISTS trg_load_opps_validate_rates_update
BEFORE UPDATE ON load_opportunities
BEGIN
    SELECT RAISE(ABORT, 'shipper_target_rate cannot be negative')
    WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.shipper_target_rate < 0;
    
    SELECT RAISE(ABORT, 'carrier_target_cost cannot be negative')
    WHERE NEW.carrier_target_cost IS NOT NULL AND NEW.carrier_target_cost < 0;
END;

CREATE TRIGGER IF NOT EXISTS trg_load_opps_validate_margin_insert
BEFORE INSERT ON load_opportunities
BEGIN
    SELECT RAISE(ABORT, 'gross_margin must be NULL when rates are missing')
    WHERE (NEW.shipper_target_rate IS NULL OR NEW.carrier_target_cost IS NULL)
      AND NEW.gross_margin IS NOT NULL;
      
    SELECT RAISE(ABORT, 'gross_margin does not match shipper_target_rate - carrier_target_cost')
    WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
      AND NEW.gross_margin IS NOT NULL
      AND ROUND(NEW.gross_margin, 2) != ROUND(NEW.shipper_target_rate - NEW.carrier_target_cost, 2);
END;

CREATE TRIGGER IF NOT EXISTS trg_load_opps_validate_margin_update
BEFORE UPDATE ON load_opportunities
BEGIN
    SELECT RAISE(ABORT, 'gross_margin must be NULL when rates are missing')
    WHERE (NEW.shipper_target_rate IS NULL OR NEW.carrier_target_cost IS NULL)
      AND NEW.gross_margin IS NOT NULL;
      
    SELECT RAISE(ABORT, 'gross_margin does not match shipper_target_rate - carrier_target_cost')
    WHERE NEW.shipper_target_rate IS NOT NULL AND NEW.carrier_target_cost IS NOT NULL
      AND NEW.gross_margin IS NOT NULL
      AND ROUND(NEW.gross_margin, 2) != ROUND(NEW.shipper_target_rate - NEW.carrier_target_cost, 2);
END;"""

assert old_triggers in content, 'Old triggers not found!'
content = content.replace(old_triggers, new_triggers)

# Replace SCHEMA_DDL DEFAULT CURRENT_TIMESTAMP with DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
ddl_marker = '"""\n\n# Default system settings'
assert ddl_marker in content, 'DDL end marker not found!'
ddl_part, rest = content.split(ddl_marker, 1)

canon_replacement = "DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))"
count = ddl_part.count('DEFAULT CURRENT_TIMESTAMP')
print(f'Replacing {count} occurrences of DEFAULT CURRENT_TIMESTAMP in SCHEMA_DDL')
ddl_part = ddl_part.replace('DEFAULT CURRENT_TIMESTAMP', canon_replacement)

# Update init_db to pass create_if_missing=True
old_init = 'with get_db_connection(db_path) as conn:'
new_init = 'with get_db_connection(db_path, create_if_missing=True) as conn:'
assert old_init in rest, 'old_init not found!'
rest = rest.replace(old_init, new_init)

content = ddl_part + ddl_marker + rest
with open('src/backend/db/schema.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Successfully updated src/backend/db/schema.py')
