# app.py
from flask import Flask, render_template, request, jsonify
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
import threading
import time
import urllib.request
import json

# Create the Flask app FIRST
app = Flask(__name__, static_folder='static', static_url_path='/static')

# ─── Database connection management ───────────────────────────────────
# Use a context manager so connections are ALWAYS closed, even on exceptions.
# Enable WAL mode for better concurrent read performance on Pi.

_db_lock = threading.Lock()
_wal_initialized = False


@contextmanager
def get_db():
    """Context manager that guarantees connection cleanup."""
    global _wal_initialized
    conn = sqlite3.connect('church_timer.db', timeout=10)
    if not _wal_initialized:
        with _db_lock:
            if not _wal_initialized:
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('PRAGMA synchronous=NORMAL')
                _wal_initialized = True
    try:
        yield conn
    finally:
        conn.close()


def init_database():
    """Legacy wrapper — returns a raw connection. Prefer get_db() context manager."""
    conn = sqlite3.connect('church_timer.db', timeout=10)
    return conn


# ─── Global state ─────────────────────────────────────────────────────

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

# Program queue - ordered list of upcoming programs
program_queue = []  # [{'program_id', 'program_name', 'scheduled_start_time'}, ...]
queue_lock = threading.Lock()


def queue_add(program_id, program_name, scheduled_start_time):
    """Add a program to the queue if not already present, keep sorted by time."""
    with queue_lock:
        if any(item['program_id'] == program_id for item in program_queue):
            return
        program_queue.append({
            'program_id': program_id,
            'program_name': program_name,
            'scheduled_start_time': scheduled_start_time
        })
        program_queue.sort(key=lambda x: x['scheduled_start_time'])


def queue_remove(program_id):
    """Remove a specific program from the queue."""
    with queue_lock:
        program_queue[:] = [item for item in program_queue if item['program_id'] != program_id]


def queue_pop_next():
    """Pop and return the first item in the queue, or None."""
    with queue_lock:
        return program_queue.pop(0) if program_queue else None


def queue_peek_next():
    """Return the first item without removing, or None."""
    with queue_lock:
        return program_queue[0].copy() if program_queue else None


def queue_clear():
    """Clear the entire queue."""
    with queue_lock:
        program_queue.clear()


def queue_get_all():
    """Return a copy of the full queue."""
    with queue_lock:
        return [item.copy() for item in program_queue]


def update_waiting_from_queue():
    """Update the waiting state based on the front of the queue."""
    next_prog = queue_peek_next()
    if next_prog:
        current_timer['waiting_for_start'] = True
        current_timer['scheduled_start_time'] = next_prog['scheduled_start_time']
        current_timer['waiting_program_name'] = next_prog['program_name']
    else:
        current_timer['waiting_for_start'] = False
        current_timer['scheduled_start_time'] = ''
        current_timer['waiting_program_name'] = ''


# ─── Queue population with overlap resolution ────────────────────────

def get_program_end_time(start_time_str, total_minutes):
    """Calculate end time string from start time and total duration in minutes."""
    try:
        start = datetime.strptime(start_time_str, '%H:%M')
        end = start + timedelta(minutes=total_minutes)
        return end.strftime('%H:%M')
    except ValueError:
        return start_time_str


def programs_overlap(start_a, dur_a, start_b, dur_b):
    """Check if two programs overlap in time. Returns True if they overlap."""
    try:
        a_start = datetime.strptime(start_a, '%H:%M')
        a_end = a_start + timedelta(minutes=dur_a)
        b_start = datetime.strptime(start_b, '%H:%M')
        b_end = b_start + timedelta(minutes=dur_b)
        return a_start < b_end and b_start < a_end
    except ValueError:
        return False


def resolve_overlap(prog_a, prog_b):
    """Resolve overlap between two programs. Returns the winner.
    Rules: remote beats local. If same source, newer (higher id) wins."""
    a_source = prog_a['source'] or 'local'
    b_source = prog_b['source'] or 'local'

    if a_source != b_source:
        winner = prog_a if a_source == 'remote' else prog_b
        loser = prog_b if a_source == 'remote' else prog_a
    else:
        if prog_a['id'] >= prog_b['id']:
            winner, loser = prog_a, prog_b
        else:
            winner, loser = prog_b, prog_a

    print(f"[QUEUE] Overlap: '{winner['name']}' ({a_source}) beats '{loser['name']}' ({b_source})")
    return winner


def populate_queue_from_db():
    """Populate the program queue from today's auto-start programs, resolving overlaps."""
    current_day = datetime.now().strftime('%A')

    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT p.id, p.name, p.scheduled_start_time, p.source,
                   COALESCE(SUM(ps.duration_minutes), 0) as total_duration
            FROM programs p
            LEFT JOIN program_schedules ps ON ps.program_id = p.id
            WHERE p.day_of_week = ? AND p.auto_start = TRUE
            GROUP BY p.id
            ORDER BY p.scheduled_start_time, p.id
        ''', (current_day,))

        candidates = []
        for row in c.fetchall():
            candidates.append({
                'id': row[0],
                'name': row[1],
                'scheduled_start_time': row[2] or '00:00',
                'source': row[3],
                'duration': row[4] if row[4] > 0 else 5
            })

    # Resolve overlaps
    resolved = []
    for candidate in candidates:
        conflict_idx = None
        for i, existing in enumerate(resolved):
            if programs_overlap(
                candidate['scheduled_start_time'], candidate['duration'],
                existing['scheduled_start_time'], existing['duration']
            ):
                conflict_idx = i
                break

        if conflict_idx is not None:
            winner = resolve_overlap(candidate, resolved[conflict_idx])
            resolved[conflict_idx] = winner
        else:
            resolved.append(candidate)

    resolved.sort(key=lambda x: x['scheduled_start_time'])
    queue_clear()
    for prog in resolved:
        queue_add(prog['id'], prog['name'], prog['scheduled_start_time'])

    items = queue_get_all()
    if items:
        print(f"[QUEUE] Populated with {len(items)} programs: {[i['program_name'] for i in items]}")
    else:
        print("[QUEUE] No programs to queue for today")


# ─── Kiosk theme/font ────────────────────────────────────────────────

kiosk_theme = 'flip'
kiosk_font = 'inter'


def load_kiosk_settings():
    """Load persisted theme/font from database"""
    global kiosk_theme, kiosk_font
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT theme, font FROM kiosk_settings WHERE id = 1')
            row = c.fetchone()
            if row:
                kiosk_theme = row[0]
                kiosk_font = row[1]
                print(f"[SETTINGS] Loaded theme={kiosk_theme}, font={kiosk_font}")
    except Exception as e:
        print(f"[SETTINGS] Could not load settings: {e}")


def save_kiosk_settings():
    """Persist current theme/font to database"""
    try:
        with get_db() as conn:
            conn.execute('UPDATE kiosk_settings SET theme = ?, font = ? WHERE id = 1',
                         (kiosk_theme, kiosk_font))
            conn.commit()
    except Exception as e:
        print(f"[SETTINGS] Could not save settings: {e}")


# ─── Countdown timer state (in-memory, synced to DB on start/stop) ───

countdown_timer = {
    'is_active': False,
    'name': '',
    'target_time': None,
    'time_remaining': '',
    'is_expired': False,
    'timer_type': 'duration'
}

# Cached countdown target for the timer loop — avoids DB read every second
_countdown_target = None  # datetime or None
_countdown_lock = threading.Lock()


def _set_countdown_target(target_dt):
    """Set the cached countdown target time (thread-safe)."""
    global _countdown_target
    with _countdown_lock:
        _countdown_target = target_dt


def _get_countdown_target():
    """Get the cached countdown target time (thread-safe)."""
    with _countdown_lock:
        return _countdown_target


def _load_countdown_from_db():
    """Load active countdown from DB into memory (used at boot)."""
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT name, target_time, started_at, duration_seconds, timer_type
                FROM countdown_timers
                WHERE is_active = TRUE
                ORDER BY created_at DESC LIMIT 1
            ''')
            row = c.fetchone()
            if row:
                name, target_time_str, started_at_str, duration_seconds, timer_type = row
                if timer_type == 'target_time' and target_time_str:
                    target = datetime.fromisoformat(target_time_str)
                elif timer_type == 'duration' and started_at_str and duration_seconds:
                    started_at = datetime.fromisoformat(started_at_str)
                    target = started_at + timedelta(seconds=duration_seconds)
                else:
                    return
                countdown_timer['is_active'] = True
                countdown_timer['name'] = name
                countdown_timer['timer_type'] = timer_type
                _set_countdown_target(target)
    except Exception as e:
        print(f"[COUNTDOWN] Error loading from DB: {e}")


# ─── Core state helpers ───────────────────────────────────────────────

def get_current_state():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT cs.is_running, cs.is_paused, cs.start_time,
                   a.name, ps.duration_minutes, ps.id
            FROM current_state cs
            LEFT JOIN program_schedules ps ON cs.current_schedule_id = ps.id
            LEFT JOIN activities a ON ps.activity_id = a.id
            WHERE cs.id = 1
        ''')
        return c.fetchone()


# ─── Timer display thread (runs every 1s) ────────────────────────────

def update_timer_display():
    """Background thread — updates timer state every second.
    Uses in-memory countdown target to avoid DB reads."""
    while True:
        try:
            # --- Countdown timer (in-memory, no DB read) ---
            target = _get_countdown_target()
            if target and countdown_timer['is_active']:
                now = datetime.now()
                if now < target:
                    remaining = target - now
                    total_seconds = int(remaining.total_seconds())
                    hours = total_seconds // 3600
                    minutes = (total_seconds % 3600) // 60
                    seconds = total_seconds % 60
                    countdown_timer['time_remaining'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    countdown_timer['target_time'] = target.isoformat()
                    countdown_timer['is_expired'] = False
                else:
                    countdown_timer['time_remaining'] = "00:00:00"
                    countdown_timer['target_time'] = target.isoformat()
                    countdown_timer['is_expired'] = True
            else:
                # No countdown — update program timer
                countdown_timer['is_active'] = False
                countdown_timer['is_expired'] = False

                state = get_current_state()
                if state and state[0] and not state[1]:  # Running and not paused
                    start_time = datetime.fromisoformat(state[2])
                    duration = state[4] * 60
                    end_time = start_time + timedelta(seconds=duration)
                    now = datetime.now()

                    if now < end_time:
                        remaining = end_time - now
                        total_seconds = int(remaining.total_seconds())
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        seconds = total_seconds % 60
                        current_timer['time_remaining'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                        current_timer['current_activity'] = state[3]
                        current_timer['is_running'] = True
                        current_timer['is_paused'] = False
                    else:
                        move_to_next_item()
                elif current_timer['is_running']:
                    # DB says not running but in-memory still thinks so — reset
                    current_timer['is_running'] = False
                    current_timer['is_paused'] = False
                    current_timer['current_activity'] = ''
                    current_timer['time_remaining'] = '00:00'
                    current_timer['total_duration'] = 0
                    current_timer['end_time'] = None

        except Exception as e:
            print(f"[TIMER] Error in timer thread: {e}")

        time.sleep(1)


# ─── Queue processing ────────────────────────────────────────────────

def process_queue():
    """Check the front of the queue and start programs when their time arrives."""
    next_item = queue_peek_next()
    if not next_item:
        return

    now = datetime.now()
    current_time = now.strftime('%H:%M')
    program_id = next_item['program_id']
    program_name = next_item['program_name']
    scheduled_start = next_item['scheduled_start_time']

    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT is_running, manual_override FROM current_state WHERE id = 1')
        state = c.fetchone()

    if scheduled_start <= current_time:
        if scheduled_start == current_time:
            queue_pop_next()
            try:
                start_program_smart_internal(program_id)
                print(f"[QUEUE] Started program: {program_name}")
            except Exception as e:
                print(f"[QUEUE] Error starting {program_name}: {e}")
        elif not state or (not state[0] and not state[1]):
            queue_pop_next()
            try:
                start_program_smart_internal(program_id)
                print(f"[QUEUE] Late-started program: {program_name}")
            except Exception as e:
                print(f"[QUEUE] Error late-starting {program_name}: {e}")
    else:
        if not state or not state[0]:
            update_waiting_from_queue()


def _is_busy():
    """Return True if a program or countdown is actively running.
    Used by background threads to skip unnecessary work."""
    if countdown_timer.get('is_active') and not countdown_timer.get('is_expired'):
        return True
    if current_timer.get('is_running'):
        return True
    return False


def auto_start_checker():
    """Background thread that processes the queue every 30 seconds.
    Always runs — process_queue() already handles the 'something is running' case
    by only overriding at exact scheduled time match."""
    last_check_minute = None
    while True:
        try:
            now = datetime.now()
            current_minute = (now.hour, now.minute)
            if current_minute != last_check_minute:
                last_check_minute = current_minute
                process_queue()
        except Exception as e:
            print(f"[AUTO-START] Error: {e}")
        time.sleep(30)


# ─── Remote program sync ─────────────────────────────────────────────

REMOTE_PROGRAMS_URL = 'https://app.rfm.org.za/api/programs/today'
remote_program_hashes = {}


def cleanup_old_remote_programs():
    """Delete remote-synced programs whose synced_date is before today."""
    today = datetime.now().strftime('%Y-%m-%d')
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT id, name, synced_date FROM programs WHERE source = 'remote' AND synced_date < ?", (today,))
            old_programs = c.fetchall()

            if not old_programs:
                return

            c.execute('SELECT current_program_id FROM current_state WHERE id = 1')
            state = c.fetchone()
            running_id = state[0] if state else None

            for prog_id, name, synced_date in old_programs:
                if prog_id == running_id:
                    print(f"[CLEANUP] Skipping {name} (currently running)")
                    continue
                c.execute('DELETE FROM program_schedules WHERE program_id = ?', (prog_id,))
                c.execute('DELETE FROM programs WHERE id = ?', (prog_id,))
                print(f"[CLEANUP] Deleted old remote program: {name} (synced {synced_date})")

            conn.commit()
    except Exception as e:
        print(f"[CLEANUP] Error cleaning up old programs: {e}")


def cleanup_old_records():
    """Purge old inactive stage_messages and countdown_timers to prevent table bloat.
    Also runs VACUUM periodically to reclaim disk space from deleted rows."""
    try:
        with get_db() as conn:
            c = conn.cursor()
            # Keep only the last 20 inactive messages
            c.execute('''DELETE FROM stage_messages WHERE is_active = FALSE
                         AND id NOT IN (SELECT id FROM stage_messages ORDER BY created_at DESC LIMIT 20)''')
            deleted_msgs = c.rowcount
            # Keep only the last 20 inactive timers
            c.execute('''DELETE FROM countdown_timers WHERE is_active = FALSE
                         AND id NOT IN (SELECT id FROM countdown_timers ORDER BY created_at DESC LIMIT 20)''')
            deleted_timers = c.rowcount
            conn.commit()

            if deleted_msgs or deleted_timers:
                print(f"[CLEANUP] Purged {deleted_msgs} old messages, {deleted_timers} old timers")
                # VACUUM reclaims disk space after bulk deletes
                # Must run outside a transaction (autocommit)
                conn.execute('VACUUM')
                print("[CLEANUP] Database vacuumed")
    except Exception as e:
        print(f"[CLEANUP] Error purging old records: {e}")


def sync_programs_once():
    """Run a single remote sync pass. Returns True if successful."""
    global remote_program_hashes
    try:
        req = urllib.request.Request(REMOTE_PROGRAMS_URL, headers={'Accept': 'application/json'})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))

        programs_data = data.get('programs', [])
        if not programs_data:
            print("[REMOTE SYNC] No programs for today")
            return True

        for prog in programs_data:
            remote_id = prog.get('id')
            prog_hash = prog.get('hash', '')
            title = prog.get('title', 'Untitled Program')
            items = prog.get('program_items', [])

            if not remote_id or not items:
                continue

            if remote_program_hashes.get(remote_id) == prog_hash:
                continue

            print(f"[REMOTE SYNC] New/updated program: {title} (hash: {prog_hash})")

            schedule_items = []
            for i, item in enumerate(items):
                item_time = item.get('time', '')
                item_name = item.get('item', '')
                if not item_time or not item_name:
                    continue

                if i < len(items) - 1:
                    next_time = items[i + 1].get('time', '')
                    try:
                        t1 = datetime.strptime(item_time, '%H:%M')
                        t2 = datetime.strptime(next_time, '%H:%M')
                        duration = int((t2 - t1).total_seconds() / 60)
                        if duration <= 0:
                            duration = 5
                    except ValueError:
                        duration = 5
                else:
                    duration = 5

                schedule_items.append((item_name, duration))

            if not schedule_items:
                continue

            start_time = items[0].get('time', '')
            today_day = datetime.now().strftime('%A')
            today_date = datetime.now().strftime('%Y-%m-%d')

            try:
                with get_db() as conn:
                    c = conn.cursor()
                    c.execute('SELECT id FROM programs WHERE name = ?', (title,))
                    existing = c.fetchone()

                    if existing:
                        program_id = existing[0]
                        c.execute('''UPDATE programs
                                     SET scheduled_start_time = ?, day_of_week = ?, auto_start = TRUE,
                                         source = 'remote', synced_date = ?
                                     WHERE id = ?''', (start_time, today_day, today_date, program_id))
                        c.execute('DELETE FROM program_schedules WHERE program_id = ?', (program_id,))
                    else:
                        c.execute('''INSERT INTO programs (name, description, scheduled_start_time, day_of_week, auto_start, source, synced_date)
                                     VALUES (?, ?, ?, ?, TRUE, 'remote', ?)''',
                                  (title, 'Synced from RFM app', start_time, today_day, today_date))
                        program_id = c.lastrowid

                    for sort_order, (activity_name, duration) in enumerate(schedule_items):
                        c.execute('SELECT id FROM activities WHERE name = ?', (activity_name,))
                        activity_row = c.fetchone()
                        if activity_row:
                            activity_id = activity_row[0]
                        else:
                            c.execute('INSERT INTO activities (name, default_duration) VALUES (?, ?)',
                                      (activity_name, duration))
                            activity_id = c.lastrowid

                        c.execute('''INSERT INTO program_schedules (program_id, activity_id, duration_minutes, sort_order)
                                     VALUES (?, ?, ?, ?)''',
                                  (program_id, activity_id, duration, sort_order))

                    conn.commit()
                    remote_program_hashes[remote_id] = prog_hash
                    print(f"[REMOTE SYNC] Synced program: {title} with {len(schedule_items)} items")

            except Exception as e:
                print(f"[REMOTE SYNC] DB error syncing {title}: {e}")

        return True

    except Exception as e:
        print(f"[REMOTE SYNC] Error fetching remote programs: {e}")
        return False


def sync_programs_from_remote():
    """Background thread that polls the remote API every 10 minutes.
    Defers sync while a program/countdown is actively running to save
    CPU, network, and DB I/O on the Pi."""
    while True:
        try:
            if _is_busy():
                # Still sleeping but longer — no point syncing mid-service
                time.sleep(120)
                continue
            cleanup_old_remote_programs()
            cleanup_old_records()
            sync_programs_once()
            populate_queue_from_db()
        except Exception as e:
            print(f"[REMOTE SYNC] Thread error: {e}")
        time.sleep(600)


# ─── Smart start helpers ──────────────────────────────────────────────

def calculate_current_activity(program_id):
    """Calculate which activity should be current based on scheduled start time"""
    with get_db() as conn:
        c = conn.cursor()

        c.execute('SELECT scheduled_start_time FROM programs WHERE id = ?', (program_id,))
        result = c.fetchone()
        if not result or not result[0]:
            return None

        scheduled_start_str = result[0]

        c.execute('''
            SELECT ps.id, ps.duration_minutes, ps.sort_order
            FROM program_schedules ps
            WHERE ps.program_id = ?
            ORDER BY ps.sort_order
        ''', (program_id,))
        schedule_items = c.fetchall()

    now = datetime.now()
    try:
        scheduled_hour, scheduled_minute = map(int, scheduled_start_str.split(':'))
        scheduled_start = now.replace(hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0)
    except ValueError:
        return None

    if now < scheduled_start:
        return schedule_items[0][0] if schedule_items else None

    elapsed_minutes = (now - scheduled_start).total_seconds() / 60
    current_time = elapsed_minutes
    current_schedule_id = None

    for schedule_id, duration, sort_order in schedule_items:
        if current_time <= duration:
            current_schedule_id = schedule_id
            break
        current_time -= duration

    if not current_schedule_id and schedule_items:
        current_schedule_id = schedule_items[-1][0]

    return current_schedule_id


def move_to_next_item():
    with get_db() as conn:
        c = conn.cursor()

        c.execute('SELECT current_program_id, current_schedule_id FROM current_state WHERE id = 1')
        result = c.fetchone()

        if result and result[0]:
            program_id, current_schedule_id = result

            schedule = get_current_schedule()

            current_index = None
            for i, item in enumerate(schedule):
                if item['id'] == current_schedule_id:
                    current_index = i
                    break

            if current_index is not None and current_index < len(schedule) - 1:
                next_item = schedule[current_index + 1]
                c.execute('''
                    UPDATE current_state
                    SET current_schedule_id = ?, start_time = ?, is_paused = FALSE
                    WHERE id = 1
                ''', (next_item['id'], datetime.now().isoformat()))
                conn.commit()
            else:
                # End of program — reset in-memory state
                c.execute('UPDATE current_state SET is_running = FALSE, manual_override = FALSE WHERE id = 1')
                conn.commit()
                current_timer['is_running'] = False
                current_timer['is_paused'] = False
                current_timer['current_activity'] = ''
                current_timer['time_remaining'] = '00:00'
                current_timer['total_duration'] = 0
                current_timer['end_time'] = None
                print(f"[TIMER] Program ended, returned to idle")

                # Auto-advance: try to start next queued program
                next_prog = queue_peek_next()
                if next_prog:
                    now = datetime.now()
                    try:
                        sh, sm = map(int, next_prog['scheduled_start_time'].split(':'))
                        scheduled = now.replace(hour=sh, minute=sm, second=0)
                    except ValueError:
                        scheduled = None

                    if scheduled and now >= scheduled:
                        queue_pop_next()
                        try:
                            start_program_smart_internal(next_prog['program_id'])
                            print(f"[QUEUE] Auto-advanced to: {next_prog['program_name']}")
                        except Exception as e:
                            print(f"[QUEUE] Error auto-advancing: {e}")
                    else:
                        update_waiting_from_queue()


def get_current_schedule():
    """Get the current schedule, using live override if available"""
    if live_schedule_override:
        return live_schedule_override

    with get_db() as conn:
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
            return [{'id': row[0], 'activity_name': row[1], 'duration_minutes': row[2],
                     'sort_order': row[3], 'activity_id': row[4]} for row in c.fetchall()]

    return []


def start_program_smart_internal(program_id):
    """Internal function to start a program smartly (used by auto-start and queue)."""
    with get_db() as conn:
        c = conn.cursor()

        c.execute('SELECT name, scheduled_start_time FROM programs WHERE id = ?', (program_id,))
        program = c.fetchone()
        if not program:
            return

        program_name, scheduled_start_str = program

        try:
            scheduled_hour, scheduled_minute = map(int, scheduled_start_str.split(':'))
            now = datetime.now()
            scheduled_start = now.replace(hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0)
        except ValueError:
            return

        if now < scheduled_start:
            queue_add(program_id, program_name, scheduled_start_str)
            print(f"[QUEUE] Added {program_name} for {scheduled_start_str}")

            c.execute('SELECT is_running FROM current_state WHERE id = 1')
            state = c.fetchone()
            if not state or not state[0]:
                update_waiting_from_queue()
                current_timer['is_running'] = False
                current_timer['is_paused'] = False
            return

        # Starting now
        queue_remove(program_id)
        current_timer['waiting_for_start'] = False
        current_timer['scheduled_start_time'] = ''
        current_timer['waiting_program_name'] = ''

        current_schedule_id = calculate_current_activity(program_id)

        if current_schedule_id:
            c.execute('SELECT duration_minutes FROM program_schedules WHERE id = ?', (current_schedule_id,))
            duration_result = c.fetchone()
            current_duration = duration_result[0] if duration_result else 5

            activity_start_time = scheduled_start

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
        print(f"Program {program_name} started successfully")


# ─── Routes ───────────────────────────────────────────────────────────

@app.route('/')
def kiosk_display():
    return render_template('kiosk.html')


@app.route('/admin')
def admin_portal():
    return render_template('admin.html')


# ─── Timer control API ────────────────────────────────────────────────

@app.route('/api/start_program', methods=['POST'])
def start_program():
    program_id = request.json.get('program_id')

    with get_db() as conn:
        c = conn.cursor()
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
                    is_running = TRUE, is_paused = FALSE, start_time = ?,
                    manual_override = TRUE
                WHERE id = 1
            ''', (program_id, first_schedule[0], datetime.now().isoformat()))
            conn.commit()

    current_timer['waiting_for_start'] = False
    current_timer['scheduled_start_time'] = ''
    current_timer['waiting_program_name'] = ''
    return jsonify({'status': 'success'})


@app.route('/api/start_program_smart', methods=['POST'])
def start_program_smart():
    """Start program and automatically jump to current activity based on scheduled time"""
    program_id = request.json.get('program_id')

    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT name FROM programs WHERE id = ?', (program_id,))
        program = c.fetchone()

    if not program:
        return jsonify({'error': 'Program not found'}), 404

    start_program_smart_internal(program_id)

    next_in_queue = queue_peek_next()
    if next_in_queue and next_in_queue['program_id'] == program_id:
        return jsonify({
            'status': 'waiting',
            'message': f'Service starts at {next_in_queue["scheduled_start_time"]}',
            'scheduled_start': next_in_queue['scheduled_start_time'],
            'program_name': next_in_queue['program_name']
        })

    return jsonify({'status': 'started', 'message': 'Program started successfully'})


@app.route('/api/pause_timer', methods=['POST'])
def pause_timer():
    with get_db() as conn:
        conn.execute('UPDATE current_state SET is_paused = TRUE, paused_at = ? WHERE id = 1',
                      (datetime.now().isoformat(),))
        conn.commit()

    current_timer['is_paused'] = True
    return jsonify({'status': 'success'})


@app.route('/api/resume_timer', methods=['POST'])
def resume_timer():
    with get_db() as conn:
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

    current_timer['is_paused'] = False
    return jsonify({'status': 'success'})


@app.route('/api/stop_timer', methods=['POST'])
def stop_timer():
    global live_schedule_override

    with get_db() as conn:
        conn.execute('UPDATE current_state SET is_running = FALSE, is_paused = FALSE, manual_override = FALSE WHERE id = 1')
        conn.commit()

    live_schedule_override = None
    current_timer.update({
        'is_running': False,
        'is_paused': False,
        'time_remaining': '00:00',
        'current_activity': '',
    })
    update_waiting_from_queue()
    return jsonify({'status': 'success'})


@app.route('/api/next_item', methods=['POST'])
def next_item():
    move_to_next_item()
    return jsonify({'status': 'success'})


@app.route('/api/clear_manual_override', methods=['POST'])
def clear_manual_override():
    with get_db() as conn:
        conn.execute('UPDATE current_state SET manual_override = FALSE WHERE id = 1')
        conn.commit()
    return jsonify({'status': 'success', 'message': 'Manual override cleared. Auto-start will resume.'})


@app.route('/api/clear_queue', methods=['POST'])
def clear_queue_legacy():
    queue_clear()
    current_timer['waiting_for_start'] = False
    current_timer['scheduled_start_time'] = ''
    current_timer['waiting_program_name'] = ''
    return jsonify({'status': 'success'})


@app.route('/api/queue', methods=['GET'])
def get_queue():
    return jsonify({'queue': queue_get_all()})


@app.route('/api/queue', methods=['DELETE'])
def clear_queue_endpoint():
    queue_clear()
    current_timer['waiting_for_start'] = False
    current_timer['scheduled_start_time'] = ''
    current_timer['waiting_program_name'] = ''
    return jsonify({'status': 'success'})


@app.route('/api/queue/<int:program_id>', methods=['DELETE'])
def remove_from_queue(program_id):
    queue_remove(program_id)
    update_waiting_from_queue()
    return jsonify({'status': 'success'})


@app.route('/api/queue/skip', methods=['POST'])
def skip_next_in_queue():
    skipped = queue_pop_next()
    if not skipped:
        return jsonify({'error': 'Queue is empty'}), 400
    update_waiting_from_queue()
    return jsonify({'status': 'success', 'skipped': skipped})


# ─── Live schedule reordering ─────────────────────────────────────────

@app.route('/api/live_schedule/reorder', methods=['POST'])
def reorder_live_schedule():
    global live_schedule_override

    data = request.json
    schedule_order = data.get('order', [])

    if not schedule_order:
        return jsonify({'error': 'No schedule items provided'}), 400

    current_schedule = get_current_schedule()
    schedule_dict = {item['id']: item for item in current_schedule}

    live_schedule_override = []
    for new_order, schedule_id in enumerate(schedule_order):
        if schedule_id in schedule_dict:
            item = schedule_dict[schedule_id].copy()
            item['sort_order'] = new_order
            live_schedule_override.append(item)

    return jsonify({'status': 'success', 'message': 'Live schedule reordered'})


@app.route('/api/live_schedule')
def get_live_schedule():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT current_program_id, current_schedule_id, is_running
            FROM current_state WHERE id = 1
        ''')
        state = c.fetchone()

    if not state or not state[0]:
        return jsonify({'schedule': [], 'current_schedule_id': None, 'is_running': False})

    program_id, current_schedule_id, is_running = state
    schedule = get_current_schedule()

    return jsonify({
        'schedule': schedule,
        'current_schedule_id': current_schedule_id,
        'is_running': is_running
    })


# ─── Program CRUD ────────────────────────────────────────────────────

@app.route('/api/programs')
def get_programs():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('''
            SELECT p.id, p.name, p.description, p.scheduled_start_time, p.day_of_week, p.auto_start,
                   COUNT(ps.id) as activity_count
            FROM programs p
            LEFT JOIN program_schedules ps ON p.id = ps.program_id
            GROUP BY p.id
            ORDER BY p.name
        ''')
        programs = [{'id': row[0], 'name': row[1], 'description': row[2],
                     'scheduled_start_time': row[3], 'day_of_week': row[4],
                     'auto_start': bool(row[5]), 'activity_count': row[6]}
                    for row in c.fetchall()]

    return jsonify(programs)


@app.route('/api/programs/<int:program_id>')
def get_program(program_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id, name, description, scheduled_start_time, day_of_week, auto_start FROM programs WHERE id = ?',
                  (program_id,))
        program = c.fetchone()

        if not program:
            return jsonify({'error': 'Program not found'}), 404

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

    return jsonify({
        'id': program[0],
        'name': program[1],
        'description': program[2],
        'scheduled_start_time': program[3],
        'day_of_week': program[4],
        'auto_start': bool(program[5]),
        'schedule': schedule
    })


@app.route('/api/programs', methods=['POST'])
def create_program():
    data = request.json
    name = data.get('name')
    description = data.get('description', '')
    scheduled_start_time = data.get('scheduled_start_time', '')
    day_of_week = data.get('day_of_week', '')
    auto_start = data.get('auto_start', False)

    if not name:
        return jsonify({'error': 'Program name is required'}), 400

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute('INSERT INTO programs (name, description, scheduled_start_time, day_of_week, auto_start) VALUES (?, ?, ?, ?, ?)',
                      (name, description, scheduled_start_time, day_of_week, auto_start))
            program_id = c.lastrowid
            conn.commit()
        # Refresh queue so new auto-start programs are picked up immediately
        populate_queue_from_db()
        process_queue()
        return jsonify({'status': 'success', 'program_id': program_id})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Program name already exists'}), 400


@app.route('/api/programs/<int:program_id>', methods=['PUT'])
def update_program(program_id):
    data = request.json
    name = data.get('name')
    description = data.get('description', '')
    scheduled_start_time = data.get('scheduled_start_time', '')
    day_of_week = data.get('day_of_week', '')
    auto_start = data.get('auto_start', False)

    with get_db() as conn:
        c = conn.cursor()
        c.execute('UPDATE programs SET name = ?, description = ?, scheduled_start_time = ?, day_of_week = ?, auto_start = ? WHERE id = ?',
                  (name, description, scheduled_start_time, day_of_week, auto_start, program_id))
        if c.rowcount == 0:
            return jsonify({'error': 'Program not found'}), 404
        conn.commit()

    # Refresh queue in case schedule/time/auto_start changed
    populate_queue_from_db()
    return jsonify({'status': 'success'})


@app.route('/api/programs/<int:program_id>', methods=['DELETE'])
def delete_program(program_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM programs WHERE id = ?', (program_id,))
        if c.rowcount == 0:
            return jsonify({'error': 'Program not found'}), 404
        conn.commit()

    # Remove from queue and refresh
    queue_remove(program_id)
    populate_queue_from_db()
    return jsonify({'status': 'success'})


# ─── Activity CRUD ───────────────────────────────────────────────────

@app.route('/api/activities')
def get_activities():
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT id, name, default_duration, description FROM activities ORDER BY name')
        activities = [{'id': row[0], 'name': row[1], 'default_duration': row[2], 'description': row[3]}
                      for row in c.fetchall()]

    return jsonify(activities)


@app.route('/api/activities', methods=['POST'])
def create_activity():
    data = request.json
    name = data.get('name')
    default_duration = data.get('default_duration', 5)
    description = data.get('description', '')

    if not name:
        return jsonify({'error': 'Activity name is required'}), 400

    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute('INSERT INTO activities (name, default_duration, description) VALUES (?, ?, ?)',
                      (name, default_duration, description))
            activity_id = c.lastrowid
            conn.commit()
        return jsonify({'status': 'success', 'activity_id': activity_id})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Activity name already exists'}), 400


@app.route('/api/activities/<int:activity_id>', methods=['PUT'])
def update_activity(activity_id):
    data = request.json
    name = data.get('name')
    default_duration = data.get('default_duration', 5)
    description = data.get('description', '')

    if not name:
        return jsonify({'error': 'Activity name is required'}), 400

    with get_db() as conn:
        c = conn.cursor()
        c.execute('UPDATE activities SET name = ?, default_duration = ?, description = ? WHERE id = ?',
                  (name, default_duration, description, activity_id))
        if c.rowcount == 0:
            return jsonify({'error': 'Activity not found'}), 404
        conn.commit()

    return jsonify({'status': 'success'})


@app.route('/api/activities/<int:activity_id>', methods=['DELETE'])
def delete_activity(activity_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM program_schedules WHERE activity_id = ?', (activity_id,))
        count = c.fetchone()[0]
        if count > 0:
            return jsonify({'error': f'Activity is used in {count} program schedule(s). Remove it from schedules first.'}), 400

        c.execute('DELETE FROM activities WHERE id = ?', (activity_id,))
        if c.rowcount == 0:
            return jsonify({'error': 'Activity not found'}), 404
        conn.commit()

    return jsonify({'status': 'success'})


# ─── Schedule management ─────────────────────────────────────────────

@app.route('/api/programs/<int:program_id>/schedule', methods=['POST'])
def add_to_schedule(program_id):
    data = request.json
    activity_id = data.get('activity_id')
    duration_minutes = data.get('duration_minutes')

    if not activity_id or not duration_minutes:
        return jsonify({'error': 'Activity ID and duration are required'}), 400

    try:
        with get_db() as conn:
            c = conn.cursor()

            c.execute('SELECT id FROM programs WHERE id = ?', (program_id,))
            if not c.fetchone():
                return jsonify({'error': 'Program not found'}), 404

            c.execute('SELECT id FROM activities WHERE id = ?', (activity_id,))
            if not c.fetchone():
                return jsonify({'error': 'Activity not found'}), 404

            c.execute('SELECT id FROM program_schedules WHERE program_id = ? AND activity_id = ?',
                      (program_id, activity_id))
            if c.fetchone():
                return jsonify({'error': 'This activity is already in the program schedule'}), 400

            c.execute('SELECT MAX(sort_order) FROM program_schedules WHERE program_id = ?', (program_id,))
            result = c.fetchone()
            next_order = 0 if result[0] is None else result[0] + 1

            c.execute('''
                INSERT INTO program_schedules (program_id, activity_id, duration_minutes, sort_order)
                VALUES (?, ?, ?, ?)
            ''', (program_id, activity_id, duration_minutes, next_order))
            conn.commit()

        return jsonify({'status': 'success'})
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Database constraint error. Please try again.'}), 400
    except Exception as e:
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500


@app.route('/api/programs/<int:program_id>/schedule/<int:schedule_id>', methods=['DELETE'])
def remove_from_schedule(program_id, schedule_id):
    with get_db() as conn:
        c = conn.cursor()
        c.execute('DELETE FROM program_schedules WHERE id = ? AND program_id = ?',
                  (schedule_id, program_id))
        if c.rowcount == 0:
            return jsonify({'error': 'Schedule item not found'}), 404
        conn.commit()

    return jsonify({'status': 'success'})


@app.route('/api/set_waiting_state', methods=['POST'])
def set_waiting_state():
    data = request.json
    current_timer['waiting_for_start'] = data.get('waiting', False)
    current_timer['scheduled_start_time'] = data.get('scheduled_start', '')
    current_timer['waiting_program_name'] = data.get('program_name', '')
    return jsonify({'status': 'success'})


@app.route('/api/programs/<int:program_id>/schedule/reorder', methods=['POST'])
def reorder_schedule(program_id):
    data = request.json
    schedule_order = data.get('order', [])

    if not schedule_order:
        return jsonify({'error': 'No schedule items provided'}), 400

    try:
        with get_db() as conn:
            c = conn.cursor()

            placeholders = ','.join('?' * len(schedule_order))
            c.execute(f'SELECT COUNT(*) FROM program_schedules WHERE id IN ({placeholders}) AND program_id = ?',
                      schedule_order + [program_id])
            count = c.fetchone()[0]
            if count != len(schedule_order):
                return jsonify({'error': 'Invalid schedule items provided'}), 400

            for new_order, schedule_id in enumerate(schedule_order):
                c.execute('UPDATE program_schedules SET sort_order = ? WHERE id = ? AND program_id = ?',
                          (new_order, schedule_id, program_id))
            conn.commit()

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': f'Error reordering schedule: {str(e)}'}), 500


@app.route('/api/next_autostart')
def next_autostart():
    try:
        now = datetime.now()
        current_day = now.strftime('%A')
        current_time = now.strftime('%H:%M')

        with get_db() as conn:
            c = conn.cursor()

            c.execute('SELECT is_running FROM current_state WHERE id = 1')
            result = c.fetchone()
            is_running = result[0] if result else False

            if is_running:
                return jsonify({'has_autostart': False, 'reason': 'Program already running'})

            c.execute('''
                SELECT id, name, scheduled_start_time, day_of_week
                FROM programs
                WHERE day_of_week = ? AND auto_start = TRUE AND scheduled_start_time > ?
                ORDER BY scheduled_start_time LIMIT 1
            ''', (current_day, current_time))
            program = c.fetchone()

            if program:
                program_id, name, scheduled_time, day = program
                try:
                    scheduled_hour, scheduled_minute = map(int, scheduled_time.split(':'))
                    scheduled_datetime = now.replace(hour=scheduled_hour, minute=scheduled_minute, second=0, microsecond=0)
                    time_until = scheduled_datetime - now
                    minutes_until = int(time_until.total_seconds() / 60)
                    hours_until = minutes_until // 60
                    mins_remaining = minutes_until % 60
                    return jsonify({
                        'has_autostart': True,
                        'program_id': program_id,
                        'program_name': name,
                        'scheduled_time': scheduled_time,
                        'day_of_week': day,
                        'minutes_until': minutes_until,
                        'time_display': f"{hours_until}h {mins_remaining}m" if hours_until > 0 else f"{mins_remaining} minutes"
                    })
                except Exception as e:
                    print(f"Error calculating time until start: {e}")

            c.execute('''
                SELECT id, name, scheduled_start_time, day_of_week
                FROM programs
                WHERE auto_start = TRUE
                ORDER BY
                    CASE day_of_week
                        WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2
                        WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4
                        WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6
                        WHEN 'Sunday' THEN 7
                    END, scheduled_start_time
                LIMIT 1
            ''')
            program = c.fetchone()

        if program:
            program_id, name, scheduled_time, day = program
            return jsonify({
                'has_autostart': True,
                'program_id': program_id,
                'program_name': name,
                'scheduled_time': scheduled_time,
                'day_of_week': day,
                'is_future_day': True
            })

        return jsonify({'has_autostart': False, 'reason': 'No auto-start programs configured'})

    except Exception as e:
        print(f"Error getting next autostart: {e}")
        return jsonify({'has_autostart': False, 'error': str(e)}), 500


# ─── Stage messages ───────────────────────────────────────────────────

@app.route('/api/stage_message', methods=['GET'])
def get_stage_message():
    try:
        now = datetime.now()
        with get_db() as conn:
            c = conn.cursor()
            c.execute('''
                SELECT id, message, duration_seconds, end_time, created_at
                FROM stage_messages
                WHERE is_active = TRUE AND end_time > ?
                ORDER BY created_at DESC LIMIT 1
            ''', (now,))
            message = c.fetchone()

        if message:
            msg_id, msg_text, duration, end_time_str, created_at = message
            end_time = datetime.fromisoformat(end_time_str)
            if end_time > now:
                time_remaining = (end_time - now).total_seconds()
                return jsonify({
                    'has_message': True,
                    'message': msg_text,
                    'duration_seconds': duration,
                    'end_time': end_time.isoformat(),
                    'time_remaining': int(time_remaining),
                    'expired': False
                })

        return jsonify({'has_message': False, 'expired': True})

    except Exception as e:
        print(f"Error getting stage message: {e}")
        return jsonify({'has_message': False, 'error': str(e)}), 500


@app.route('/api/stage_message', methods=['POST'])
def send_stage_message():
    try:
        data = request.get_json()
        message = data.get('message', '').strip()
        duration = int(data.get('duration_seconds', 60))

        if not message:
            return jsonify({'error': 'Message cannot be empty'}), 400

        message = message[:100]
        duration = min(max(duration, 10), 300)

        now = datetime.now()
        end_time = now + timedelta(seconds=duration)

        with get_db() as conn:
            c = conn.cursor()
            c.execute('UPDATE stage_messages SET is_active = FALSE WHERE is_active = TRUE')
            c.execute('''
                INSERT INTO stage_messages (message, duration_seconds, end_time, is_active)
                VALUES (?, ?, ?, TRUE)
            ''', (message, duration, end_time))
            message_id = c.lastrowid
            conn.commit()

        print(f"[STAGE MESSAGE] Sent: '{message}' for {duration}s")
        return jsonify({
            'status': 'success',
            'message_id': message_id,
            'duration': duration,
            'end_time': end_time.isoformat()
        })

    except Exception as e:
        print(f"Error sending stage message: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/stage_message', methods=['DELETE'])
def clear_stage_message():
    try:
        with get_db() as conn:
            conn.execute('UPDATE stage_messages SET is_active = FALSE WHERE is_active = TRUE')
            conn.commit()
        print("[STAGE MESSAGE] Cleared")
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f"Error clearing stage message: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Countdown timer API ─────────────────────────────────────────────

@app.route('/api/countdown_timer', methods=['GET'])
def get_countdown_timer():
    return jsonify(countdown_timer)


@app.route('/api/countdown_timer', methods=['POST'])
def start_countdown_timer():
    """Start a new countdown timer - stops any running programs"""
    try:
        data = request.get_json()
        timer_type = data.get('timer_type', 'duration')
        name = data.get('name', 'Countdown').strip()

        now = datetime.now()

        with get_db() as conn:
            c = conn.cursor()

            # Stop any running programs
            c.execute('''
                UPDATE current_state
                SET is_running = FALSE, is_paused = FALSE,
                    current_program_id = NULL, current_schedule_id = NULL,
                    manual_override = FALSE
                WHERE id = 1
            ''')
            c.execute('UPDATE countdown_timers SET is_active = FALSE WHERE is_active = TRUE')

            if timer_type == 'target_time':
                target_time_str = data.get('target_time')
                if not target_time_str:
                    return jsonify({'error': 'target_time is required for target_time type'}), 400

                if ':' in target_time_str and 'T' not in target_time_str:
                    hour, minute = map(int, target_time_str.split(':'))
                    target_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    if target_time <= now:
                        target_time = target_time + timedelta(days=1)
                else:
                    target_time = datetime.fromisoformat(target_time_str)

                c.execute('''
                    INSERT INTO countdown_timers (name, target_time, timer_type, started_at, is_active)
                    VALUES (?, ?, 'target_time', ?, TRUE)
                ''', (name, target_time.isoformat(), now.isoformat()))

            else:  # duration type
                duration_seconds = int(data.get('duration_seconds', 300))
                duration_seconds = max(10, min(duration_seconds, 86400))
                target_time = now + timedelta(seconds=duration_seconds)

                c.execute('''
                    INSERT INTO countdown_timers (name, duration_seconds, timer_type, started_at, is_active)
                    VALUES (?, ?, 'duration', ?, TRUE)
                ''', (name, duration_seconds, now.isoformat()))

            timer_id = c.lastrowid
            conn.commit()

        # Update in-memory state immediately (no DB read needed in timer loop)
        countdown_timer['is_active'] = True
        countdown_timer['name'] = name
        countdown_timer['timer_type'] = timer_type
        countdown_timer['is_expired'] = False
        _set_countdown_target(target_time)

        print(f"[COUNTDOWN] Started: '{name}' (type: {timer_type})")
        return jsonify({'status': 'success', 'timer_id': timer_id, 'timer_type': timer_type})

    except Exception as e:
        print(f"Error starting countdown timer: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/countdown_timer', methods=['DELETE'])
def stop_countdown_timer():
    try:
        with get_db() as conn:
            conn.execute('UPDATE countdown_timers SET is_active = FALSE WHERE is_active = TRUE')
            conn.commit()

        print("[COUNTDOWN] Stopped")
        countdown_timer['is_active'] = False
        countdown_timer['is_expired'] = False
        _set_countdown_target(None)

        return jsonify({'status': 'success'})

    except Exception as e:
        print(f"Error stopping countdown timer: {e}")
        return jsonify({'error': str(e)}), 500


# ─── Master reset ─────────────────────────────────────────────────────

@app.route('/api/reset_screen', methods=['POST'])
def reset_screen():
    global live_schedule_override

    with get_db() as conn:
        c = conn.cursor()
        c.execute('''UPDATE current_state
                     SET is_running = FALSE, is_paused = FALSE,
                         current_program_id = NULL, current_schedule_id = NULL,
                         manual_override = FALSE
                     WHERE id = 1''')
        c.execute('UPDATE stage_messages SET is_active = FALSE WHERE is_active = TRUE')
        c.execute('UPDATE countdown_timers SET is_active = FALSE WHERE is_active = TRUE')
        conn.commit()

    live_schedule_override = None
    queue_clear()
    _set_countdown_target(None)

    current_timer.update({
        'current_activity': '',
        'time_remaining': '00:00',
        'is_running': False,
        'is_paused': False,
        'total_duration': 0,
        'end_time': None,
        'waiting_for_start': False,
        'scheduled_start_time': '',
        'waiting_program_name': ''
    })

    countdown_timer.update({
        'is_active': False,
        'name': '',
        'target_time': None,
        'time_remaining': '',
        'is_expired': False,
        'timer_type': 'duration'
    })

    print("[RESET] Screen reset to idle")
    return jsonify({'status': 'success', 'message': 'Screen reset to idle'})


# ─── Kiosk theme API ─────────────────────────────────────────────────

@app.route('/api/kiosk_theme', methods=['GET'])
def get_kiosk_theme():
    return jsonify({'theme': kiosk_theme, 'font': kiosk_font})


@app.route('/api/kiosk_theme', methods=['POST'])
def set_kiosk_theme():
    global kiosk_theme, kiosk_font
    data = request.json
    theme = data.get('theme')
    font = data.get('font')
    if theme:
        if theme not in ('flip', 'minimal', 'neon', 'warm', 'sacred'):
            return jsonify({'error': 'Invalid theme'}), 400
        kiosk_theme = theme
        print(f"[THEME] Kiosk theme changed to: {theme}")
    if font:
        if font not in ('inter', 'oswald', 'bebas', 'orbitron', 'mono', 'jetbrains'):
            return jsonify({'error': 'Invalid font'}), 400
        kiosk_font = font
        print(f"[FONT] Kiosk font changed to: {font}")
    save_kiosk_settings()
    return jsonify({'status': 'success', 'theme': kiosk_theme, 'font': kiosk_font})


# ─── Presenter integration (Revival Fire Presenter WebSocket) ─────────

presenter_config = {
    'enabled': False,
    'host': '',
    'port': 4777,
    'filters': ['scripture', 'song'],
}

@app.route('/api/presenter', methods=['GET'])
def get_presenter():
    return jsonify(presenter_config)


@app.route('/api/presenter', methods=['POST'])
def set_presenter():
    global presenter_config
    data = request.json
    presenter_config['enabled'] = bool(data.get('enabled', False))
    presenter_config['host'] = data.get('host', '').strip()
    presenter_config['port'] = int(data.get('port', 4777))
    presenter_config['filters'] = data.get('filters', ['scripture', 'song'])
    print(f"[PRESENTER] Config updated: enabled={presenter_config['enabled']}, host={presenter_config['host']}, filters={presenter_config['filters']}")
    return jsonify({'status': 'success', **presenter_config})


presenter_connection_status = 'disconnected'

@app.route('/api/presenter_status', methods=['GET'])
def get_presenter_status():
    return jsonify({'connection': presenter_connection_status})


@app.route('/api/presenter_status', methods=['POST'])
def set_presenter_status():
    global presenter_connection_status
    data = request.json
    presenter_connection_status = data.get('status', 'disconnected')
    print(f"[PRESENTER] Connection status: {presenter_connection_status}")
    return jsonify({'status': 'ok'})


# ─── Timer status (polled by kiosk + admin) ───────────────────────────

@app.route('/api/timer_status')
def timer_status():
    response_data = current_timer.copy()
    all_queue = queue_get_all()
    if all_queue:
        response_data['queued_program'] = {
            'has_queued': True,
            'program_id': all_queue[0]['program_id'],
            'program_name': all_queue[0]['program_name'],
            'scheduled_start_time': all_queue[0]['scheduled_start_time']
        }
    else:
        response_data['queued_program'] = {
            'has_queued': False,
            'program_id': None,
            'program_name': '',
            'scheduled_start_time': ''
        }
    response_data['queue'] = all_queue
    response_data['kiosk_theme'] = kiosk_theme
    response_data['kiosk_font'] = kiosk_font
    return jsonify(response_data)


# ─── Boot sequence ────────────────────────────────────────────────────

if __name__ == '__main__':
    from database import init_db
    init_db()

    # Enable WAL mode on the database
    with get_db() as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA synchronous=NORMAL')
        _wal_initialized = True

    load_kiosk_settings()
    _load_countdown_from_db()

    # 1. Clean up old data and compact DB
    print("[BOOT] Cleaning up old data...")
    cleanup_old_remote_programs()
    cleanup_old_records()
    # One-time boot VACUUM to reclaim space from any past bloat
    try:
        with get_db() as conn:
            c = conn.cursor()
            c.execute('PRAGMA page_count')
            pages = c.fetchone()[0]
            c.execute('PRAGMA page_size')
            page_size = c.fetchone()[0]
            db_size_kb = (pages * page_size) / 1024
            c.execute('PRAGMA freelist_count')
            free_pages = c.fetchone()[0]
            print(f"[BOOT] DB size: {db_size_kb:.0f}KB, reclaimable pages: {free_pages}")
            if free_pages > 0:
                conn.execute('VACUUM')
                print(f"[BOOT] Database vacuumed, reclaimed {free_pages * page_size / 1024:.0f}KB")
    except Exception as e:
        print(f"[BOOT] VACUUM error (non-fatal): {e}")
    print("[BOOT] Running initial remote sync...")
    sync_programs_once()

    # 2. Populate queue from today's auto-start programs
    populate_queue_from_db()

    # 3. Process queue (start or set waiting state)
    process_queue()

    # 4. Start background threads
    timer_thread = threading.Thread(target=update_timer_display, daemon=True)
    timer_thread.start()

    auto_start_thread = threading.Thread(target=auto_start_checker, daemon=True)
    auto_start_thread.start()
    print("[BOOT] Auto-start checker thread started")

    remote_sync_thread = threading.Thread(target=sync_programs_from_remote, daemon=True)
    remote_sync_thread.start()
    print("[BOOT] Remote program sync thread started")

    app.run(host='0.0.0.0', port=80, debug=False, threaded=True)
