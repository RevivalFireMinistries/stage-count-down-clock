#!/usr/bin/env python3
"""
Migration script for Church Timer database
Adds missing columns to existing tables
"""
import sqlite3
import sys

def get_table_columns(cursor, table_name):
    """Get list of columns for a table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]

def migrate():
    try:
        conn = sqlite3.connect('church_timer.db')
        c = conn.cursor()
        
        print("=" * 70)
        print("Church Timer Database Migration")
        print("=" * 70)
        print()
        
        migrations_applied = []
        
        # Migration 1: Add day_of_week to programs table
        print("Checking programs table...")
        programs_columns = get_table_columns(c, 'programs')
        
        if 'day_of_week' not in programs_columns:
            print("  → Adding day_of_week column...")
            c.execute('ALTER TABLE programs ADD COLUMN day_of_week TEXT')
            migrations_applied.append("Added day_of_week to programs")
        else:
            print("  ✓ day_of_week column already exists")
        
        if 'auto_start' not in programs_columns:
            print("  → Adding auto_start column...")
            c.execute('ALTER TABLE programs ADD COLUMN auto_start BOOLEAN DEFAULT FALSE')
            migrations_applied.append("Added auto_start to programs")
        else:
            print("  ✓ auto_start column already exists")
        
        if 'scheduled_start_time' not in programs_columns:
            print("  → Adding scheduled_start_time column...")
            c.execute('ALTER TABLE programs ADD COLUMN scheduled_start_time TEXT')
            migrations_applied.append("Added scheduled_start_time to programs")
        else:
            print("  ✓ scheduled_start_time column already exists")
        
        # Migration 2: Add manual_override to current_state table
        print("\nChecking current_state table...")
        current_state_columns = get_table_columns(c, 'current_state')
        
        if 'manual_override' not in current_state_columns:
            print("  → Adding manual_override column...")
            c.execute('ALTER TABLE current_state ADD COLUMN manual_override BOOLEAN DEFAULT FALSE')
            migrations_applied.append("Added manual_override to current_state")
        else:
            print("  ✓ manual_override column already exists")
        
        # Migration 3: Ensure current_state has all required columns
        required_current_state_columns = {
            'current_program_id': 'INTEGER',
            'current_schedule_id': 'INTEGER',
            'is_running': 'BOOLEAN DEFAULT FALSE',
            'is_paused': 'BOOLEAN DEFAULT FALSE',
            'start_time': 'TIMESTAMP',
            'paused_at': 'TIMESTAMP'
        }
        
        for col_name, col_type in required_current_state_columns.items():
            if col_name not in current_state_columns:
                print(f"  → Adding {col_name} column...")
                c.execute(f'ALTER TABLE current_state ADD COLUMN {col_name} {col_type}')
                migrations_applied.append(f"Added {col_name} to current_state")
        
        # Migration 4: Check activities table
        print("\nChecking activities table...")
        activities_columns = get_table_columns(c, 'activities')
        
        if 'default_duration' not in activities_columns:
            print("  → Adding default_duration column...")
            c.execute('ALTER TABLE activities ADD COLUMN default_duration INTEGER DEFAULT 5')
            migrations_applied.append("Added default_duration to activities")
        else:
            print("  ✓ default_duration column already exists")
        
        if 'description' not in activities_columns:
            print("  → Adding description column...")
            c.execute('ALTER TABLE activities ADD COLUMN description TEXT')
            migrations_applied.append("Added description to activities")
        else:
            print("  ✓ description column already exists")
        
        # Migration 5: Check program_schedules table
        print("\nChecking program_schedules table...")
        schedule_columns = get_table_columns(c, 'program_schedules')
        
        if 'sort_order' not in schedule_columns:
            print("  → Adding sort_order column...")
            c.execute('ALTER TABLE program_schedules ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0')
            
            # Update sort_order for existing records
            c.execute('''
                SELECT id, program_id 
                FROM program_schedules 
                ORDER BY program_id, id
            ''')
            records = c.fetchall()
            
            current_program = None
            order = 0
            for rec_id, program_id in records:
                if program_id != current_program:
                    current_program = program_id
                    order = 0
                c.execute('UPDATE program_schedules SET sort_order = ? WHERE id = ?', (order, rec_id))
                order += 1
            
            migrations_applied.append("Added sort_order to program_schedules")
        else:
            print("  ✓ sort_order column already exists")
        
        # Commit all changes
        conn.commit()
        
        print()
        print("=" * 70)
        if migrations_applied:
            print("✅ Migration completed successfully!")
            print()
            print("Applied migrations:")
            for migration in migrations_applied:
                print(f"  • {migration}")
        else:
            print("✅ Database schema is up to date - no migrations needed")
        print("=" * 70)
        
        # Display final schema
        print()
        print("Final database schema:")
        print("-" * 70)
        
        tables = ['programs', 'activities', 'program_schedules', 'current_state']
        for table in tables:
            print(f"\n{table}:")
            columns = get_table_columns(c, table)
            for col in columns:
                print(f"  • {col}")
        
        conn.close()
        return True
        
    except Exception as e:
        print()
        print("=" * 70)
        print(f"❌ Migration failed: {e}")
        print("=" * 70)
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = migrate()
    sys.exit(0 if success else 1)
