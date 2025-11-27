# database.py
import sqlite3
from datetime import datetime
import os

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
            sort_order INTEGER NOT NULL,
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