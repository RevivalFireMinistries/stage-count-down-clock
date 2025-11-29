# database.py
import sqlite3
from datetime import datetime
import os

def get_table_columns(cursor, table_name):
    """Get list of columns for a table"""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]

def run_migrations(conn):
    """Run all necessary migrations to update schema"""
    c = conn.cursor()
    migrations_run = []
    
    try:
        # Migration 1: Add columns to programs table
        programs_columns = get_table_columns(c, 'programs')
        
        if 'day_of_week' not in programs_columns:
            print("Running migration: Adding day_of_week to programs...")
            c.execute('ALTER TABLE programs ADD COLUMN day_of_week TEXT')
            migrations_run.append("day_of_week")
        
        if 'auto_start' not in programs_columns:
            print("Running migration: Adding auto_start to programs...")
            c.execute('ALTER TABLE programs ADD COLUMN auto_start BOOLEAN DEFAULT FALSE')
            migrations_run.append("auto_start")
        
        if 'scheduled_start_time' not in programs_columns:
            print("Running migration: Adding scheduled_start_time to programs...")
            c.execute('ALTER TABLE programs ADD COLUMN scheduled_start_time TEXT')
            migrations_run.append("scheduled_start_time")
        
        # Migration 2: Add columns to current_state table
        current_state_columns = get_table_columns(c, 'current_state')
        
        if 'manual_override' not in current_state_columns:
            print("Running migration: Adding manual_override to current_state...")
            c.execute('ALTER TABLE current_state ADD COLUMN manual_override BOOLEAN DEFAULT FALSE')
            migrations_run.append("manual_override")
        
        # Migration 3: Add columns to activities table
        activities_columns = get_table_columns(c, 'activities')
        
        if 'default_duration' not in activities_columns:
            print("Running migration: Adding default_duration to activities...")
            c.execute('ALTER TABLE activities ADD COLUMN default_duration INTEGER DEFAULT 5')
            migrations_run.append("default_duration")
        
        if 'description' not in activities_columns:
            print("Running migration: Adding description to activities...")
            c.execute('ALTER TABLE activities ADD COLUMN description TEXT')
            migrations_run.append("description")
        
        # Migration 4: Add sort_order to program_schedules
        schedule_columns = get_table_columns(c, 'program_schedules')
        
        if 'sort_order' not in schedule_columns:
            print("Running migration: Adding sort_order to program_schedules...")
            c.execute('ALTER TABLE program_schedules ADD COLUMN sort_order INTEGER NOT NULL DEFAULT 0')
            
            # Update sort_order for existing records
            c.execute('SELECT id, program_id FROM program_schedules ORDER BY program_id, id')
            records = c.fetchall()
            
            current_program = None
            order = 0
            for rec_id, program_id in records:
                if program_id != current_program:
                    current_program = program_id
                    order = 0
                c.execute('UPDATE program_schedules SET sort_order = ? WHERE id = ?', (order, rec_id))
                order += 1
            
            migrations_run.append("sort_order")
        
        if migrations_run:
            print(f"Migrations completed: {', '.join(migrations_run)}")
        
        conn.commit()
        
    except Exception as e:
        print(f"Migration error: {e}")
        # Don't fail - the tables might already have the columns

def init_db():
    conn = sqlite3.connect('church_timer.db')
    c = conn.cursor()
    
    # Only create tables if they don't exist - DON'T drop existing tables
    c.execute('''
        CREATE TABLE IF NOT EXISTS programs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            scheduled_start_time TEXT,
            day_of_week TEXT,
            auto_start BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            default_duration INTEGER DEFAULT 5,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS program_schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            program_id INTEGER NOT NULL,
            activity_id INTEGER NOT NULL,
            duration_minutes INTEGER NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (program_id) REFERENCES programs (id) ON DELETE CASCADE,
            FOREIGN KEY (activity_id) REFERENCES activities (id) ON DELETE CASCADE,
            UNIQUE(program_id, activity_id),
            UNIQUE(program_id, sort_order)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS current_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_program_id INTEGER,
            current_schedule_id INTEGER,
            is_running BOOLEAN DEFAULT FALSE,
            is_paused BOOLEAN DEFAULT FALSE,
            start_time TIMESTAMP,
            paused_at TIMESTAMP,
            manual_override BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (current_program_id) REFERENCES programs (id),
            FOREIGN KEY (current_schedule_id) REFERENCES program_schedules (id)
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS stage_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            duration_seconds INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP NOT NULL,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # Run migrations for existing tables
    run_migrations(conn)
    
    # Only insert default data if tables are empty
    c.execute('SELECT COUNT(*) FROM activities')
    if c.fetchone()[0] == 0:
        # Insert default activities only if table is empty
        default_activities = [
            ('Prayer', 15, 'Prayer time'),
            ('Praise', 15, 'Praise and worship'),
            ('Announcements', 5, 'Church announcements'),
            ('Bible reading', 5, 'Scripture reading'),
            ('Worship', 15, 'Worship session'),
            ('Word', 60, 'Sermon/Message'),
            ('Admin/close', 5, 'Administration and closing')
        ]
        
        for activity_name, duration, desc in default_activities:
            c.execute('INSERT INTO activities (name, default_duration, description) VALUES (?, ?, ?)', 
                     (activity_name, duration, desc))
    
    c.execute('SELECT COUNT(*) FROM programs')
    if c.fetchone()[0] == 0:
        # Insert default programs only if table is empty
        c.execute('INSERT INTO programs (name, description, scheduled_start_time, day_of_week, auto_start) VALUES (?, ?, ?, ?, ?)', 
                 ('Sunday Program', 'Regular Sunday service schedule', '09:30', 'Sunday', True))
        sunday_id = c.lastrowid
        
        sunday_schedule = [
            ('Prayer', 15),
            ('Praise', 15),
            ('Announcements', 5),
            ('Bible reading', 5),
            ('Worship', 15),
            ('Word', 60),
            ('Admin/close', 5)
        ]
        
        for i, (activity_name, duration) in enumerate(sunday_schedule):
            c.execute('SELECT id FROM activities WHERE name = ?', (activity_name,))
            activity_id = c.fetchone()[0]
            c.execute('''
                INSERT INTO program_schedules (program_id, activity_id, duration_minutes, sort_order)
                VALUES (?, ?, ?, ?)
            ''', (sunday_id, activity_id, duration, i))
        
        c.execute('INSERT INTO programs (name, description, scheduled_start_time, day_of_week, auto_start) VALUES (?, ?, ?, ?, ?)', 
                 ('Friday Service', 'Friday evening service', '18:00', 'Friday', True))
        friday_id = c.lastrowid
        
        friday_schedule = [
            ('Prayer', 80),
            ('Admin/close', 10)
        ]
        
        for i, (activity_name, duration) in enumerate(friday_schedule):
            c.execute('SELECT id FROM activities WHERE name = ?', (activity_name,))
            activity_id = c.fetchone()[0]
            c.execute('''
                INSERT INTO program_schedules (program_id, activity_id, duration_minutes, sort_order)
                VALUES (?, ?, ?, ?)
            ''', (friday_id, activity_id, duration, i))
    
    # Initialize current state only if it doesn't exist
    c.execute('SELECT COUNT(*) FROM current_state')
    if c.fetchone()[0] == 0:
        c.execute('INSERT INTO current_state (id) VALUES (1)')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully!")

if __name__ == '__main__':
    init_db()
