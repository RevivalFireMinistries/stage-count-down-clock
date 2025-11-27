#!/usr/bin/env python3
# Migration script to add manual_override column to current_state table
import sqlite3

def migrate():
    conn = sqlite3.connect('church_timer.db')
    c = conn.cursor()
    
    # Check if column already exists
    c.execute("PRAGMA table_info(current_state)")
    columns = [row[1] for row in c.fetchall()]
    
    if 'manual_override' not in columns:
        print("Adding manual_override column to current_state table...")
        c.execute('ALTER TABLE current_state ADD COLUMN manual_override BOOLEAN DEFAULT FALSE')
        conn.commit()
        print("Migration completed successfully!")
    else:
        print("Column manual_override already exists, skipping migration.")
    
    conn.close()

if __name__ == '__main__':
    migrate()
