#!/usr/bin/env python3
"""Verify database migration and schema."""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, inspect
from app.config import settings


def verify_migration():
    """Verify that all tables and constraints exist."""
    print("Verifying database migration...")
    print(f"Database URL: {settings.database_url_sync}")

    # Create engine
    engine = create_engine(settings.database_url_sync)
    inspector = inspect(engine)

    # Expected tables
    expected_tables = {
        'tenants',
        'users',
        'oauth_tokens',
        'google_ads_accounts',
        'performance_thresholds',
        'report_schedules',
        'report_history',
        'keyword_candidates',
        'approval_requests',
    }

    # Get actual tables
    actual_tables = set(inspector.get_table_names())

    print("\n=== Table Verification ===")
    missing_tables = expected_tables - actual_tables
    extra_tables = actual_tables - expected_tables

    if missing_tables:
        print(f"❌ Missing tables: {missing_tables}")
        return False
    else:
        print(f"✅ All {len(expected_tables)} tables exist")

    if extra_tables:
        print(f"⚠️  Extra tables: {extra_tables}")

    # Verify foreign keys
    print("\n=== Foreign Key Verification ===")
    fk_checks = {
        'users': [('tenant_id', 'tenants')],
        'oauth_tokens': [('tenant_id', 'tenants')],
        'google_ads_accounts': [('tenant_id', 'tenants')],
        'performance_thresholds': [('tenant_id', 'tenants')],
        'report_schedules': [('tenant_id', 'tenants')],
        'report_history': [('tenant_id', 'tenants')],
        'keyword_candidates': [('tenant_id', 'tenants')],
        'approval_requests': [('keyword_candidate_id', 'keyword_candidates')],
    }

    all_fks_valid = True
    for table_name, expected_fks in fk_checks.items():
        foreign_keys = inspector.get_foreign_keys(table_name)
        fk_map = {fk['constrained_columns'][0]: fk['referred_table'] for fk in foreign_keys}

        for column, referenced_table in expected_fks:
            if column in fk_map and fk_map[column] == referenced_table:
                print(f"✅ {table_name}.{column} → {referenced_table}")
            else:
                print(f"❌ Missing FK: {table_name}.{column} → {referenced_table}")
                all_fks_valid = False

    # Verify indexes
    print("\n=== Index Verification ===")
    critical_indexes = {
        'tenants': ['ix_tenants_workspace_id'],
        'users': ['ix_users_tenant_id', 'ix_users_slack_user_id'],
        'keyword_candidates': ['ix_keyword_candidates_tenant_id', 'ix_keyword_candidates_detected_at'],
        'approval_requests': ['ix_approval_requests_keyword_candidate_id', 'ix_approval_requests_expires_at'],
    }

    all_indexes_valid = True
    for table_name, expected_idx_names in critical_indexes.items():
        indexes = inspector.get_indexes(table_name)
        actual_idx_names = {idx['name'] for idx in indexes}

        for idx_name in expected_idx_names:
            if idx_name in actual_idx_names:
                print(f"✅ {table_name}: {idx_name}")
            else:
                print(f"❌ Missing index: {table_name}.{idx_name}")
                all_indexes_valid = False

    # Verify column types
    print("\n=== Column Type Verification ===")
    enum_checks = {
        'oauth_tokens': [('provider', 'oauthprovider')],
        'keyword_candidates': [('status', 'keywordstatus')],
        'approval_requests': [('action', 'approvalaction')],
        'report_schedules': [('frequency', 'reportfrequency')],
    }

    all_enums_valid = True
    for table_name, expected_enums in enum_checks.items():
        columns = inspector.get_columns(table_name)
        col_map = {col['name']: col for col in columns}

        for column, enum_type in expected_enums:
            if column in col_map:
                col_type = str(col_map[column]['type']).lower()
                # Check if enum type is in the column type string
                if enum_type.lower() in col_type or 'enum' in col_type:
                    print(f"✅ {table_name}.{column}: enum type")
                else:
                    print(f"⚠️  {table_name}.{column}: type is {col_type} (expected enum)")
            else:
                print(f"❌ Missing column: {table_name}.{column}")
                all_enums_valid = False

    # Summary
    print("\n=== Summary ===")
    if not missing_tables and all_fks_valid and all_indexes_valid and all_enums_valid:
        print("✅ Migration verification PASSED")
        print("Database schema is correctly configured.")
        return True
    else:
        print("❌ Migration verification FAILED")
        print("Please review the errors above and run migration again.")
        return False


def test_connection():
    """Test database connection."""
    print("\n=== Connection Test ===")
    try:
        engine = create_engine(settings.database_url_sync)
        with engine.connect() as conn:
            result = conn.execute("SELECT version();")
            version = result.fetchone()[0]
            print("✅ Connected to database")
            print(f"Database version: {version}")
            return True
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        return False


def main():
    """Main verification script."""
    print("=" * 60)
    print("SEM-Agent Database Migration Verification")
    print("=" * 60)

    # Test connection first
    if not test_connection():
        print("\n❌ Cannot verify migration - database connection failed")
        print("Please check your DATABASE_URL configuration and ensure PostgreSQL is running.")
        sys.exit(1)

    # Verify migration
    if verify_migration():
        print("\n✅ All checks passed!")
        sys.exit(0)
    else:
        print("\n❌ Verification failed!")
        sys.exit(1)


if __name__ == "__main__":
    main()
