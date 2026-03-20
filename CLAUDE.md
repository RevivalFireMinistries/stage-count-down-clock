# Church Stage Countdown Clock

A Flask-based countdown timer system for church services, designed to run on a Raspberry Pi 4 in kiosk mode and be controlled from any device on the local network.

## Tech Stack

- **Backend**: Python / Flask, SQLite3 (`church_timer.db`)
- **Frontend**: Vanilla HTML/CSS/JS, Jinja2 templates
- **Libraries**: Google Fonts (Inter, Oswald, Bebas Neue, Orbitron, Roboto Mono, JetBrains Mono), Font Awesome 6, Sortable.js 1.14.0
- **Deployment**: Raspberry Pi 4, Chromium kiosk mode, X11 display server
- **Port**: 80 (HTTP, all interfaces)

## Project Structure

```
app.py                          # Main Flask application (~1700 lines)
database.py                     # Database init & migrations
templates/
  admin.html                    # Admin control panel (dark theme)
  kiosk.html                    # Stage display (full-screen, flip-clock)
static/
  css/admin.css                 # Admin styling (dark theme)
  js/admin.js                   # Admin JS
start_timer.sh                  # Simple startup script
start-kiosk.sh                  # Kiosk display startup (Chromium)
startup.sh                      # Production startup (venv + logging)
migrate_database.py             # Migration utilities
migrate_countdown_timers.py     # Countdown timer table migration
migrate_add_manual_override.py  # Manual override column migration
```

## Database Schema

| Table | Purpose |
|-------|---------|
| `programs` | Program definitions (name, description, scheduled_start_time, day_of_week, auto_start) |
| `activities` | Activity definitions (name, default_duration, description) |
| `program_schedules` | Links programs to activities (program_id, activity_id, duration_minutes, sort_order) |
| `current_state` | Single-row table tracking active program (is_running, is_paused, start_time, manual_override) |
| `stage_messages` | Messages to display on stage (message, duration_seconds, end_time, is_active) |
| `countdown_timers` | Countdown timer records (name, target_time, duration_seconds, timer_type, is_active) |
| `kiosk_settings` | Persisted kiosk theme and font (single-row, id=1) |

## Features

### Program & Activity Management
- Create/edit/delete programs with scheduled start times and day-of-week
- Create/edit/delete reusable activities with default durations (delete blocked if used in schedules)
- Build program schedules by adding activities with custom durations
- Drag-to-reorder activities in schedules (persists to DB via sort_order)

### Timer Controls
- **Start**: Begin program from first activity
- **Smart Start**: Jump to the activity that should be current based on scheduled start time and elapsed time
- **Pause/Resume**: Pause timer, resume with accurate timing
- **Next**: Skip to next activity in schedule
- **Stop**: Stop timer completely
- **Reset Screen**: Master switch that stops everything (programs, countdowns, messages, queue)

### Auto-Start & Program Queue
- Programs can be configured to auto-start on their scheduled day/time
- `program_queue` is a thread-safe ordered list of upcoming programs (sorted by scheduled_start_time)
- Queue auto-populates from today's auto-start programs on boot and after each remote sync
- Background thread (`auto_start_checker`) calls `process_queue()` every 30 seconds
- When a program's scheduled time arrives, it starts automatically (overrides running programs at exact time)
- When a program ends, the next queued program auto-advances
- Admin UI shows full queue with per-item remove, skip next, and clear all controls
- Kiosk shows "UP NEXT" banner with live countdown when a program is running and another is queued

### Waiting State
- When a queued program exists and nothing is running, shows "STARTING IN" with live countdown
- Countdown calculated client-side from scheduled start time, updates every second
- Shows program name and "Starts at HH:MM" as subtitle

### Countdown Timer (Standalone)
- **Duration mode**: Count down from X minutes/seconds
- **Target time mode**: Count down to a specific time (e.g., midnight, noon)
- Takes priority over program timers; stops any running program when started
- Displays "TIME UP" with flashing red when expired

### Stage Messages
- Send text messages to display on the kiosk screen (max 100 chars)
- Auto-sizing text based on message length (4 size classes)
- Full-screen display with pulsing background glow, progress bar, and countdown
- Configurable duration (10 seconds to 5 minutes)
- Auto-hides when expired using server-side `time_remaining` (avoids timezone parsing issues across platforms)
- Only one active message at a time

### Remote Program Sync
- Background thread polls `https://app.rfm.org.za/api/programs/today` every 10 minutes
- Also runs once synchronously at boot (before queue population)
- Uses hash-based change detection to avoid unnecessary updates
- Calculates activity durations from time gaps between consecutive items (last item defaults to 5 min)
- Creates/updates programs and activities in local DB automatically
- Sets programs to auto-start; queue refreshes after each sync
- Programs matched by title; schedules are fully replaced on updates

### Kiosk Themes & Fonts
- 4 themes: flip (ice blue), minimal (white on black), neon (purple), warm (orange)
- 6 fonts: Inter, Oswald, Bebas Neue, Orbitron, Roboto Mono, JetBrains Mono
- Theme/font persisted in `kiosk_settings` DB table across restarts
- CSS custom properties (`--t-bg`, `--t-glow`, `--t-text`, etc.) for theming
- Body class-based switching (`theme-neon`, `font-orbitron`, etc.)

### Kiosk Display Modes
- **Clock**: Large digital clock + date when idle
- **Timer**: Activity name + flip-clock digits (HH:MM:SS or MM:SS) + progress bar
- **Waiting**: Program name + "STARTING IN" countdown
- **Message overlay**: Full-screen message with minimized timer in corner
- **End screen**: "THE END" when program completes
- **Warning colors**: normal -> orange (last 60s) -> red pulsing (last 10s)

### Admin Interface
- Dark theme with indigo accents, mobile-first responsive design
- Tab navigation: Home, Programs, Activities, Schedule
- Program queue card with numbered list, per-item remove, skip, clear all
- Reset Screen master button
- Kiosk theme selector with visual previews
- Clock font selector with live font samples
- Collapsible accordion cards, bottom-sheet modals on mobile

### Live Schedule Reordering
- Reorder activities during a running program (in-memory only, not saved to DB)
- Cleared when timer stops

## API Endpoints

### Pages
- `GET /` - Kiosk display
- `GET /admin` - Admin panel

### Timer Control
- `POST /api/start_program` - Start program from beginning
- `POST /api/start_program_smart` - Smart start (jump to current activity)
- `POST /api/pause_timer` - Pause
- `POST /api/resume_timer` - Resume
- `POST /api/stop_timer` - Stop
- `POST /api/next_item` - Next activity
- `POST /api/clear_manual_override` - Clear manual override
- `POST /api/reset_screen` - Master reset (stops everything, clears queue)
- `GET /api/timer_status` - Current timer state (includes full queue array)

### Queue
- `GET /api/queue` - Get full program queue
- `DELETE /api/queue` - Clear entire queue
- `DELETE /api/queue/<program_id>` - Remove specific program from queue
- `POST /api/queue/skip` - Skip (remove) next program in queue

### Programs
- `GET /api/programs` - List all
- `POST /api/programs` - Create
- `GET /api/programs/<id>` - Get details
- `PUT /api/programs/<id>` - Update
- `DELETE /api/programs/<id>` - Delete

### Activities
- `GET /api/activities` - List all
- `POST /api/activities` - Create
- `PUT /api/activities/<id>` - Update
- `DELETE /api/activities/<id>` - Delete (blocked if used in schedules)

### Schedules
- `POST /api/programs/<id>/schedule` - Add activity to schedule
- `DELETE /api/programs/<id>/schedule/<sid>` - Remove from schedule
- `POST /api/programs/<id>/schedule/reorder` - Reorder schedule
- `GET /api/live_schedule` - Get live schedule with current activity marked
- `POST /api/live_schedule/reorder` - Reorder live schedule (in-memory)

### Stage Messages
- `GET /api/stage_message` - Get active message
- `POST /api/stage_message` - Send message (truncated to 100 chars)
- `DELETE /api/stage_message` - Clear message

### Countdown Timer
- `GET /api/countdown_timer` - Get active countdown
- `POST /api/countdown_timer` - Start countdown
- `DELETE /api/countdown_timer` - Stop countdown

### Kiosk Settings
- `GET /api/kiosk_theme` - Get current theme and font
- `POST /api/kiosk_theme` - Set theme and/or font (persists to DB)

### Auto-Start
- `GET /api/next_autostart` - Next scheduled auto-start info

## Boot Sequence

When the app starts (Pi power-on or manual restart):

1. **`init_db()`** - Create tables if missing, run migrations
2. **`load_kiosk_settings()`** - Load persisted theme/font from DB
3. **`sync_programs_once()`** - Single synchronous remote API fetch (gets today's programs before queueing)
4. **`populate_queue_from_db()`** - Queue ALL today's auto-start programs (sorted by time)
5. **`process_queue()`** - Start the first program or set waiting state
6. **Background threads start**: `update_timer_display` (1s), `auto_start_checker` (30s), `sync_programs_from_remote` (10min)

## Background Threads

1. **`update_timer_display()`** - Runs every 1 second. Updates countdown/program timer state, checks expiration, moves to next activity, auto-advances from queue.
2. **`auto_start_checker()`** - Runs every 30 seconds. Calls `process_queue()` to start programs when their scheduled time arrives.
3. **`sync_programs_from_remote()`** - Runs every 10 minutes. Calls `sync_programs_once()` then `populate_queue_from_db()` to refresh the queue.

## Running Locally (Windows)

```bash
# Requires Python 3 and Flask
pip install flask
python app.py
# Admin: http://localhost/admin
# Kiosk: http://localhost/
```

Note: On the dev Windows machine, the Python executable is `python3.13.exe`.

## Raspberry Pi Deployment

- App directory: `/home/russel/church-timer/`
- Virtual environment: `/home/russel/church-timer/church-timer-env/`
- Logs: `app.log`, `kiosk.log`
- Chromium runs in kiosk mode with cursor hidden, screen blanking disabled
- Use `startup.sh` for the Flask server and `start-kiosk.sh` for the display

## Default Data

- **Activities**: Prayer (15m), Praise (15m), Announcements (5m), Bible reading (5m), Worship (15m), Word (60m), Admin/close (5m)
- **Programs**: Sunday Service (09:30, auto-start), Friday Service (18:00, auto-start)

## Cache Busting

Static files use query string versioning (`?v=8`). Bump the version in `admin.html` when changing `admin.css` or `admin.js` to bypass browser cache.
