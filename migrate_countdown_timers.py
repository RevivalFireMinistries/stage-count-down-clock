#!/usr/bin/env python3
"""
Migration script to add countdown_timers table for custom countdown timer feature
Run this script to update your existing database with the new countdown timer capability
"""

import sqlite3
import os

def migrate_database():
    """Add countdown_timers table to existing database"""
    db_file = 'church_timer.db'
    
    if not os.path.exists(db_file):
        print(f"Database file '{db_file}' not found!")
        print("Please run this script from the directory containing your database.")
        return False
    
    try:
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        
        # Check if table already exists
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='countdown_timers'")
        if c.fetchone():
            print("✓ countdown_timers table already exists")
            conn.close()
            return True
        
        print("Adding countdown_timers table...")
        
        # Create countdown_timers table
        c.execute('''
            CREATE TABLE countdown_timers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                target_time TIMESTAMP,
                duration_seconds INTEGER,
                timer_type TEXT NOT NULL CHECK(timer_type IN ('duration', 'target_time')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                is_active BOOLEAN DEFAULT FALSE
            )
        ''')
        
        conn.commit()
        conn.close()
        
        print("✓ Migration completed successfully!")
        print("\nNew features added:")
        print("  - Countdown to specific time (e.g., midnight)")
        print("  - Duration-based countdown timers")
        print("  - TIME UP display with flashing animation")
        print("  - Stops running programs when countdown starts")
        print("\nYou can now use the Countdown Timer feature in the admin dashboard!")
        
        return True
        
    except Exception as e:
        print(f"✗ Migration failed: {e}")
        return False

if __name__ == '__main__':
    print("=" * 60)
    print("Countdown Timer Migration Script")
    print("=" * 60)
    print()
    
    success = migrate_database()
    
    if not success:
        exit(1)
