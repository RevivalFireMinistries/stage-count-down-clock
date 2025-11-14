# app.py
from flask import Flask, render_template, request, jsonify
import sqlite3
from datetime import datetime, timedelta
import threading
import time

# Create the Flask app FIRST
app = Flask(__name__)

# Global state
# Global state
current_timer = {
    'current_activity': '',
    'time_remaining': '00:00',
    'is_running': False,
    'is_paused': False,
    'total_duration': 0,
    'end_time': None,
    'waiting_for_start': False,
    'scheduled_start_time': '',
    'waiting_program_name': ''
}
live_schedule_override = None  # Will store the live reordered schedule

def init_database():
    conn = sqlite3.connect('church_timer.db')
    return conn

def get_current_state():
    conn = init_database()
    c = conn.cursor()
    c.execute('''
        SELECT cs.is_running, cs.is_paused, cs.start_time, 
               a.name, ps.duration_minutes, ps.id
        FROM current_state cs
        LEFT JOIN program_schedules ps ON cs.current_schedule_id = ps.id
        LEFT JOIN activities a ON ps.activity_id = a.id
        WHERE cs.id = 1
    ''')
    result = c.fetchone()
    conn.close()
    return result

def update_timer_display():
    while True:
        state = get_current_state()
        if state and state[0] and not state[1]:  # Running and not paused
            start_time = datetime.fromisoformat(state[2])
            duration = state[4] * 60  # Convert to seconds
            end_time = start_time + timedelta(seconds=duration)
            now = datetime.now()
            
            if now < end_time:
                remaining = end_time - now
                total_seconds = int(remaining.total_seconds())
                
                # Convert to hours:minutes:seconds format
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                seconds = total_seconds % 60
                
                # Always show hours:minutes:seconds format with leading zeros
                current_timer['time_remaining'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                
                current_timer['current_activity'] = state[3]
                current_timer['is_running'] = True
                current_timer['is_paused'] = False
            else:
                # Move to next item
                move_to_next_item()
        time.sleep(1)

# Start timer thread
timer_thread = threading.Thread(target=update_timer_display, daemon=True)
timer_thread.start()

# Helper functions for smart start
def calculate_current_activity(program_id):
    """Calculate which activity should be current based on scheduled start time"""
    conn = init_database()
    c = conn.cursor()
    
    # Get program start time
    c.execute('SELECT scheduled_start_time FROM programs WHERE id = ?', (program_id,))
    result = c.fetchone()
    if not result or not result[0]:
        conn.close()
        return None
    
    scheduled_start_str = result[0]
    
    # Get all schedule items for this program
    c.execute('''
        SELECT ps.id, ps.duration_minutes, ps.sort_order
        FROM program_schedules ps
        WHERE ps.program_id = ?
        ORDER BY ps.sort_order
    ''', (program_id,))
    schedule_items = c.fetchall()
    
    # Calculate current time and scheduled start time
    now = datetime.now()
    try:
        # Parse scheduled start time (e.g., "09:30")
        scheduled_hour, scheduled_minute = map(int, scheduled_start_str.split(':'))
        scheduled_start = now.replace(hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0)
    except ValueError:
        conn.close()
        return None
    
    # If current time is before scheduled start, return first activity
    if now < scheduled_start:
        conn.close()
        return schedule_items[0][0] if schedule_items else None
    
    # Calculate elapsed time since scheduled start
    elapsed_time = now - scheduled_start
    elapsed_minutes = elapsed_time.total_seconds() / 60
    
    # Find current activity based on elapsed time
    current_time = elapsed_minutes
    current_schedule_id = None
    
    for schedule_id, duration, sort_order in schedule_items:
        if current_time <= duration:
            current_schedule_id = schedule_id
            break
        current_time -= duration
    
    # If we've passed all activities, return the last one
    if not current_schedule_id and schedule_items:
        current_schedule_id = schedule_items[-1][0]
    
    conn.close()
    return current_schedule_id

def move_to_next_item():
    conn = init_database()
    c = conn.cursor()
    
    c.execute('SELECT current_program_id, current_schedule_id FROM current_state WHERE id = 1')
    result = c.fetchone()
    
    if result and result[0]:
        program_id, current_schedule_id = result
        
        # Get next schedule item
        c.execute('''
            SELECT ps.id FROM program_schedules ps 
            WHERE ps.program_id = ? AND ps.sort_order > 
                (SELECT sort_order FROM program_schedules WHERE id = ?)
            ORDER BY ps.sort_order LIMIT 1
        ''', (program_id, current_schedule_id))
        
        next_schedule = c.fetchone()
        
        if next_schedule:
            c.execute('''
                UPDATE current_state 
                SET current_schedule_id = ?, start_time = ?, is_paused = FALSE
                WHERE id = 1
            ''', (next_schedule[0], datetime.now().isoformat()))
        else:
            # End of program
            c.execute('UPDATE current_state SET is_running = FALSE WHERE id = 1')
        
        conn.commit()
    
    conn.close()
def get_current_schedule():
    """Get the current schedule, using live override if available"""
    if live_schedule_override:
        return live_schedule_override
    
    # Otherwise get from database
    conn = init_database()
    c = conn.cursor()
    c.execute('SELECT current_program_id FROM current_state WHERE id = 1')
    result = c.fetchone()
    
    if result and result[0]:
        program_id = result[0]
        c.execute('''
            SELECT ps.id, a.name, ps.duration_minutes, ps.sort_order, ps.activity_id
            FROM program_schedules ps
            JOIN activities a ON ps.activity_id = a.id
            WHERE ps.program_id = ?
            ORDER BY ps.sort_order
        ''', (program_id,))
        schedule = [{'id': row[0], 'activity_name': row[1], 'duration_minutes': row[2], 
                    'sort_order': row[3], 'activity_id': row[4]} for row in c.fetchall()]
        conn.close()
        return schedule
    
    conn.close()
    return []

# Add new endpoint for live schedule reordering
@app.route('/api/live_schedule/reorder', methods=['POST'])
def reorder_live_schedule():
    """Reorder the live schedule without persisting to database"""
    global live_schedule_override
    
    data = request.json
    schedule_order = data.get('order', [])  # List of schedule IDs in new order
    
    if not schedule_order:
        return jsonify({'error': 'No schedule items provided'}), 400
    
    # Get current schedule
    current_schedule = get_current_schedule()
    
    # Create a lookup dictionary
    schedule_dict = {item['id']: item for item in current_schedule}
    
    # Reorder based on provided order
    live_schedule_override = []
    for new_order, schedule_id in enumerate(schedule_order):
        if schedule_id in schedule_dict:
            item = schedule_dict[schedule_id].copy()
            item['sort_order'] = new_order
            live_schedule_override.append(item)
    
    return jsonify({'status': 'success', 'message': 'Live schedule reordered'})

# Add endpoint to get live schedule with current activity highlighted
@app.route('/api/live_schedule')
def get_live_schedule():
    """Get the current live schedule with current activity marked"""
    conn = init_database()
    c = conn.cursor()
    
    # Get current state
    c.execute('''
        SELECT current_program_id, current_schedule_id, is_running
        FROM current_state WHERE id = 1
    ''')
    state = c.fetchone()
    
    if not state or not state[0]:
        conn.close()
        return jsonify({'schedule': [], 'current_schedule_id': None, 'is_running': False})
    
    program_id, current_schedule_id, is_running = state
    
    # Get schedule (use live override if available)
    schedule = get_current_schedule()
    
    conn.close()
    
    return jsonify({
        'schedule': schedule,
        'current_schedule_id': current_schedule_id,
        'is_running': is_running
    })


# Update move_to_next_item to use live schedule
def move_to_next_item():
    conn = init_database()
    c = conn.cursor()
    
    c.execute('SELECT current_program_id, current_schedule_id FROM current_state WHERE id = 1')
    result = c.fetchone()
    
    if result and result[0]:
        program_id, current_schedule_id = result
        
        # Get current schedule (with live override if available)
        schedule = get_current_schedule()
        
        # Find current item index
        current_index = None
        for i, item in enumerate(schedule):
            if item['id'] == current_schedule_id:
                current_index = i
                break
        
        if current_index is not None and current_index < len(schedule) - 1:
            # Move to next item
            next_item = schedule[current_index + 1]
            c.execute('''
                UPDATE current_state 
                SET current_schedule_id = ?, start_time = ?, is_paused = FALSE
                WHERE id = 1
            ''', (next_item['id'], datetime.now().isoformat()))
        else:
            # End of program
            c.execute('UPDATE current_state SET is_running = FALSE WHERE id = 1')
        
        conn.commit()
    
    conn.close()    

# Routes - NOW they can use the @app.route decorator
@app.route('/')
def kiosk_display():
    return render_template('kiosk.html')

@app.route('/admin')
def admin_portal():
    return render_template('admin.html')

# API Routes for Timer Control
@app.route('/api/start_program', methods=['POST'])
def start_program():
    program_id = request.json.get('program_id')
    
    conn = init_database()
    c = conn.cursor()
    
    # Get first schedule item
    c.execute('''
        SELECT ps.id FROM program_schedules ps 
        WHERE ps.program_id = ? 
        ORDER BY ps.sort_order LIMIT 1
    ''', (program_id,))
    first_schedule = c.fetchone()
    
    if first_schedule:
        c.execute('''
            UPDATE current_state 
            SET current_program_id = ?, current_schedule_id = ?, 
                is_running = TRUE, is_paused = FALSE, start_time = ?
            WHERE id = 1
        ''', (program_id, first_schedule[0], datetime.now().isoformat()))
        
        conn.commit()
    
    conn.close()
    return jsonify({'status': 'success'})

# In app.py, update the start_program_smart function:

@app.route('/api/start_program_smart', methods=['POST'])
def start_program_smart():
    """Start program and automatically jump to current activity based on scheduled time"""
    program_id = request.json.get('program_id')
    
    conn = init_database()
    c = conn.cursor()
    
    # Get program details including scheduled start time
    c.execute('SELECT name, scheduled_start_time FROM programs WHERE id = ?', (program_id,))
    program = c.fetchone()
    
    if not program:
        conn.close()
        return jsonify({'error': 'Program not found'}), 404
    
    program_name, scheduled_start_str = program
    
    # Parse scheduled start time
    try:
        scheduled_hour, scheduled_minute = map(int, scheduled_start_str.split(':'))
        now = datetime.now()
        scheduled_start = now.replace(hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0)
    except ValueError:
        conn.close()
        return jsonify({'error': 'Invalid scheduled start time format'}), 400
    
    # Check if current time is before scheduled start
    if now < scheduled_start:
        # SET THE WAITING STATE IN current_timer
        current_timer['waiting_for_start'] = True
        current_timer['scheduled_start_time'] = scheduled_start_str
        current_timer['waiting_program_name'] = program_name
        current_timer['is_running'] = False
        current_timer['is_paused'] = False
        
        conn.close()
        return jsonify({
            'status': 'waiting',
            'message': f'Service starts at {scheduled_start_str}',
            'scheduled_start': scheduled_start_str,
            'program_name': program_name
        })
    
    # Clear waiting state when starting
    current_timer['waiting_for_start'] = False
    current_timer['scheduled_start_time'] = ''
    current_timer['waiting_program_name'] = ''
    
    # If we're at or after scheduled start time, proceed with normal smart start
    current_schedule_id = calculate_current_activity(program_id)
    
    if current_schedule_id:
        # Get the duration of the current activity for timer calculation
        c.execute('SELECT duration_minutes FROM program_schedules WHERE id = ?', (current_schedule_id,))
        duration_result = c.fetchone()
        current_duration = duration_result[0] if duration_result else 5
        
        # Calculate when this activity started based on scheduled program start
        activity_start_time = scheduled_start
        
        # Calculate elapsed time to find when current activity started
        c.execute('''
            SELECT ps.sort_order, ps.duration_minutes 
            FROM program_schedules ps 
            WHERE ps.program_id = ? 
            ORDER BY ps.sort_order
        ''', (program_id,))
        all_activities = c.fetchall()
        
        for sort_order, duration in all_activities:
            c.execute('SELECT id FROM program_schedules WHERE program_id = ? AND sort_order = ?', 
                     (program_id, sort_order))
            schedule_id = c.fetchone()[0]
            
            if schedule_id == current_schedule_id:
                break
            activity_start_time += timedelta(minutes=duration)
        
        c.execute('''
            UPDATE current_state 
            SET current_program_id = ?, current_schedule_id = ?, 
                is_running = TRUE, is_paused = FALSE, start_time = ?
            WHERE id = 1
        ''', (program_id, current_schedule_id, activity_start_time.isoformat()))
    else:
        # Fallback: start from beginning
        c.execute('''
            SELECT ps.id FROM program_schedules ps 
            WHERE ps.program_id = ? 
            ORDER BY ps.sort_order LIMIT 1
        ''', (program_id,))
        first_schedule = c.fetchone()
        
        if first_schedule:
            c.execute('''
                UPDATE current_state 
                SET current_program_id = ?, current_schedule_id = ?, 
                    is_running = TRUE, is_paused = FALSE, start_time = ?
                WHERE id = 1
            ''', (program_id, first_schedule[0], scheduled_start.isoformat()))
    
    conn.commit()
    conn.close()
    return jsonify({'status': 'started', 'message': 'Program started successfully'})
    
@app.route('/api/pause_timer', methods=['POST'])
def pause_timer():
    conn = init_database()
    c = conn.cursor()
    
    c.execute('UPDATE current_state SET is_paused = TRUE, paused_at = ? WHERE id = 1', 
              (datetime.now().isoformat(),))
    conn.commit()
    conn.close()
    
    current_timer['is_paused'] = True
    return jsonify({'status': 'success'})

@app.route('/api/resume_timer', methods=['POST'])
def resume_timer():
    conn = init_database()
    c = conn.cursor()
    
    c.execute('SELECT start_time, paused_at FROM current_state WHERE id = 1')
    result = c.fetchone()
    
    if result and result[1]:
        start_time = datetime.fromisoformat(result[0])
        paused_at = datetime.fromisoformat(result[1])
        paused_duration = datetime.now() - paused_at
        new_start_time = start_time + paused_duration
        
        c.execute('''
            UPDATE current_state 
            SET is_paused = FALSE, start_time = ?, paused_at = NULL 
            WHERE id = 1
        ''', (new_start_time.isoformat(),))
        
        conn.commit()
    
    conn.close()
    current_timer['is_paused'] = False
    return jsonify({'status': 'success'})

@app.route('/api/stop_timer', methods=['POST'])
def stop_timer():
    global live_schedule_override
    
    conn = init_database()
    c = conn.cursor()
    
    c.execute('UPDATE current_state SET is_running = FALSE, is_paused = FALSE WHERE id = 1')
    conn.commit()
    conn.close()
    
    # Clear live override when stopping
    live_schedule_override = None
    
    current_timer.update({
        'is_running': False,
        'is_paused': False,
        'time_remaining': '00:00',
        'current_activity': ''
    })
    return jsonify({'status': 'success'})

@app.route('/api/next_item', methods=['POST'])
def next_item():
    move_to_next_item()
    return jsonify({'status': 'success'})

# API Routes for Program Management
@app.route('/api/programs')
def get_programs():
    conn = init_database()
    c = conn.cursor()
    
    c.execute('''
        SELECT p.id, p.name, p.description, p.scheduled_start_time,
               COUNT(ps.id) as activity_count
        FROM programs p
        LEFT JOIN program_schedules ps ON p.id = ps.program_id
        GROUP BY p.id
        ORDER BY p.name
    ''')
    programs = [{'id': row[0], 'name': row[1], 'description': row[2], 
                'scheduled_start_time': row[3], 'activity_count': row[4]} 
               for row in c.fetchall()]
    
    conn.close()
    return jsonify(programs)

@app.route('/api/programs/<int:program_id>')
def get_program(program_id):
    conn = init_database()
    c = conn.cursor()
    
    # Get program details including scheduled_start_time
    c.execute('SELECT id, name, description, scheduled_start_time FROM programs WHERE id = ?', (program_id,))
    program = c.fetchone()
    
    if not program:
        conn.close()
        return jsonify({'error': 'Program not found'}), 404
    
    # Get program schedule
    c.execute('''
        SELECT ps.id, a.name, a.id as activity_id, ps.duration_minutes, ps.sort_order
        FROM program_schedules ps
        JOIN activities a ON ps.activity_id = a.id
        WHERE ps.program_id = ?
        ORDER BY ps.sort_order
    ''', (program_id,))
    
    schedule = [{'id': row[0], 'activity_name': row[1], 'activity_id': row[2], 
                 'duration_minutes': row[3], 'sort_order': row[4]} 
                for row in c.fetchall()]
    
    conn.close()
    return jsonify({
        'id': program[0],
        'name': program[1],
        'description': program[2],
        'scheduled_start_time': program[3],
        'schedule': schedule
    })

@app.route('/api/programs', methods=['POST'])
def create_program():
    data = request.json
    name = data.get('name')
    description = data.get('description', '')
    scheduled_start_time = data.get('scheduled_start_time', '')
    
    if not name:
        return jsonify({'error': 'Program name is required'}), 400
    
    conn = init_database()
    c = conn.cursor()
    
    try:
        c.execute('INSERT INTO programs (name, description, scheduled_start_time) VALUES (?, ?, ?)', 
                 (name, description, scheduled_start_time))
        program_id = c.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'program_id': program_id})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Program name already exists'}), 400

@app.route('/api/programs/<int:program_id>', methods=['PUT'])
def update_program(program_id):
    data = request.json
    name = data.get('name')
    description = data.get('description', '')
    scheduled_start_time = data.get('scheduled_start_time', '')
    
    conn = init_database()
    c = conn.cursor()
    
    c.execute('UPDATE programs SET name = ?, description = ?, scheduled_start_time = ? WHERE id = ?', 
             (name, description, scheduled_start_time, program_id))
    
    if c.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Program not found'}), 404
    
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

@app.route('/api/programs/<int:program_id>', methods=['DELETE'])
def delete_program(program_id):
    conn = init_database()
    c = conn.cursor()
    
    c.execute('DELETE FROM programs WHERE id = ?', (program_id,))
    
    if c.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Program not found'}), 404
    
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})

# API Routes for Activity Management
@app.route('/api/activities')
def get_activities():
    conn = init_database()
    c = conn.cursor()
    
    c.execute('SELECT id, name, default_duration, description FROM activities ORDER BY name')
    activities = [{'id': row[0], 'name': row[1], 'default_duration': row[2], 'description': row[3]} 
                  for row in c.fetchall()]
    
    conn.close()
    return jsonify(activities)

@app.route('/api/activities', methods=['POST'])
def create_activity():
    data = request.json
    name = data.get('name')
    default_duration = data.get('default_duration', 5)
    description = data.get('description', '')
    
    if not name:
        return jsonify({'error': 'Activity name is required'}), 400
    
    conn = init_database()
    c = conn.cursor()
    
    try:
        c.execute('INSERT INTO activities (name, default_duration, description) VALUES (?, ?, ?)', 
                 (name, default_duration, description))
        activity_id = c.lastrowid
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'activity_id': activity_id})
    except sqlite3.IntegrityError:
        conn.close()
        return jsonify({'error': 'Activity name already exists'}), 400

# API Routes for Program Schedule Management
@app.route('/api/programs/<int:program_id>/schedule', methods=['POST'])
def add_to_schedule(program_id):
    data = request.json
    activity_id = data.get('activity_id')
    duration_minutes = data.get('duration_minutes')
    
    if not activity_id or not duration_minutes:
        return jsonify({'error': 'Activity ID and duration are required'}), 400
    
    conn = init_database()
    c = conn.cursor()
    
    try:
        # Verify program exists
        c.execute('SELECT id FROM programs WHERE id = ?', (program_id,))
        if not c.fetchone():
            conn.close()
            return jsonify({'error': 'Program not found'}), 404
        
        # Verify activity exists
        c.execute('SELECT id FROM activities WHERE id = ?', (activity_id,))
        if not c.fetchone():
            conn.close()
            return jsonify({'error': 'Activity not found'}), 404
        
        # Check if activity is already in program
        c.execute('SELECT id FROM program_schedules WHERE program_id = ? AND activity_id = ?', 
                 (program_id, activity_id))
        if c.fetchone():
            conn.close()
            return jsonify({'error': 'This activity is already in the program schedule'}), 400
        
        # Get the next available sort_order
        c.execute('SELECT MAX(sort_order) FROM program_schedules WHERE program_id = ?', (program_id,))
        result = c.fetchone()
        next_order = 0 if result[0] is None else result[0] + 1
        
        # Insert the new schedule item
        c.execute('''
            INSERT INTO program_schedules (program_id, activity_id, duration_minutes, sort_order)
            VALUES (?, ?, ?, ?)
        ''', (program_id, activity_id, duration_minutes, next_order))
        
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
        
    except sqlite3.IntegrityError as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': 'Database constraint error. Please try again.'}), 400
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/api/programs/<int:program_id>/schedule/<int:schedule_id>', methods=['DELETE'])
def remove_from_schedule(program_id, schedule_id):
    conn = init_database()
    c = conn.cursor()
    
    c.execute('DELETE FROM program_schedules WHERE id = ? AND program_id = ?', 
             (schedule_id, program_id))
    
    if c.rowcount == 0:
        conn.close()
        return jsonify({'error': 'Schedule item not found'}), 404
    
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})
    
@app.route('/api/set_waiting_state', methods=['POST'])
def set_waiting_state():
    """Set the waiting state for the kiosk display"""
    data = request.json
    global current_timer
    
    # You could store this in the database, but for simplicity we'll use a global
    # In a production app, you'd want to store this in the database
    current_timer['waiting_for_start'] = data.get('waiting', False)
    current_timer['scheduled_start_time'] = data.get('scheduled_start', '')
    current_timer['waiting_program_name'] = data.get('program_name', '')
    
    return jsonify({'status': 'success'})       

@app.route('/api/programs/<int:program_id>/schedule/reorder', methods=['POST'])
def reorder_schedule(program_id):
    data = request.json
    schedule_order = data.get('order', [])  # List of schedule IDs in new order
    
    if not schedule_order:
        return jsonify({'error': 'No schedule items provided'}), 400
    
    conn = init_database()
    c = conn.cursor()
    
    try:
        # Verify all schedule IDs belong to this program
        placeholders = ','.join('?' * len(schedule_order))
        c.execute(f'SELECT COUNT(*) FROM program_schedules WHERE id IN ({placeholders}) AND program_id = ?', 
                 schedule_order + [program_id])
        count = c.fetchone()[0]
        
        if count != len(schedule_order):
            conn.close()
            return jsonify({'error': 'Invalid schedule items provided'}), 400
        
        # Update sort orders sequentially
        for new_order, schedule_id in enumerate(schedule_order):
            c.execute('UPDATE program_schedules SET sort_order = ? WHERE id = ? AND program_id = ?',
                     (new_order, schedule_id, program_id))
        
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({'error': f'Error reordering schedule: {str(e)}'}), 500

@app.route('/api/timer_status')
def timer_status():
    # Include waiting state information in the response
    response_data = current_timer.copy()
    return jsonify(response_data)

if __name__ == '__main__':
    from database import init_db
    init_db()
    app.run(host='0.0.0.0', port=80, debug=False, threaded=True)
    
 