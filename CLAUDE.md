# Church Stage Countdown Clock

A Flask-based countdown timer system for church services, designed to run on a Raspberry Pi 4 in kiosk mode and be controlled from any device on the local network.

## Tech Stack

- **Backend**: Python / Flask, SQLite3 (`church_timer.db`)
- **Frontend**: Vanilla HTML/CSS/JS, Jinja2 templates
- **Libraries**: Google Fonts (Poppins), Font Awesome 6, Sortable.js 1.14.0
- **Deployment**: Raspberry Pi 4, Chromium kiosk mode, X11 display server
- **Port**: 80 (HTTP, all interfaces)

## Project Structure

```
app.py                          # Main Flask application (~1360 lines)
database.py                     # Database init & migrations
templates/
  admin.html                    # Admin control panel
  kiosk.html                    # Stage display (full-screen)
static/
  css/admin.css                 # Admin styling
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

## Features

### Program & Activity Management
- Create/edit/delete programs with scheduled start times and day-of-week
- Create reusable activities with default durations
- Build program schedules by adding activities with custom durations
- Drag-to-reorder activities in schedules (persists to DB via sort_order)

### Timer Controls
- **Start**: Begin program from first activity
- **Smart Start**: Jump to the activity that should be current based on scheduled start time and elapsed time
- **Pause/Resume**: Pause timer, resume with accurate timing
- **Next**: Skip to next activity in schedule
- **Stop**: Stop timer completely

### Auto-Start
- Programs can be configured to auto-start on their scheduled day/time
- Background thread checks every 30 seconds
- Only triggers if no program is running and no manual override is active
- Also checks on app launch for today's programs

### Program Queue
- Programs can be queued for future start via Smart Start or remote sync
- Queue persists independently of current running state (`queued_program` global)
- Manual start clears the waiting view but keeps the queue intact
- When a manual program stops or ends, the waiting view restores for the queued program
- When the queued program's scheduled time arrives, auto-start overrides even manually running programs
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
- Send text messages to display on the kiosk screen
- Configurable duration (10 seconds to 5 minutes)
- Animated overlay with countdown and progress bar
- Auto-hides when expired; only one active message at a time

### Remote Program Sync
- Background thread polls `https://app.rfm.org.za/api/programs/today` every 10 minutes
- Uses hash-based change detection to avoid unnecessary updates
- Calculates activity durations from time gaps between consecutive items (last item defaults to 5 min)
- Creates/updates programs and activities in local DB automatically
- Sets programs to auto-start so the existing auto-start mechanism picks them up
- Programs matched by title; schedules are fully replaced on updates

### Live Schedule Reordering
- Reorder activities during a running program (in-memory only, not saved to DB)
- Cleared when timer stops

### Kiosk Display Modes
- **Clock**: Large digital clock + date when idle
- **Timer**: Activity name + HH:MM:SS countdown + progress bar + percentage
- **Waiting**: Program name + scheduled start time
- **Message overlay**: Full-screen message with minimized timer in corner
- **End screen**: "THE END" when program completes
- **Warning colors**: green (normal) -> orange (last 60s) -> red pulsing (last 10s)

### Admin Interface
- Mobile-first responsive design (works on phones/tablets)
- Tab navigation: Home, Programs, Activities, Schedule
- Dark theme with blue accents
- Program selector modal, inline editing, collapsible cards

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
- `GET /api/timer_status` - Current timer state

### Programs
- `GET /api/programs` - List all
- `POST /api/programs` - Create
- `GET /api/programs/<id>` - Get details
- `PUT /api/programs/<id>` - Update
- `DELETE /api/programs/<id>` - Delete

### Activities
- `GET /api/activities` - List all
- `POST /api/activities` - Create

### Schedules
- `POST /api/programs/<id>/schedule` - Add activity to schedule
- `DELETE /api/programs/<id>/schedule/<sid>` - Remove from schedule
- `POST /api/programs/<id>/schedule/reorder` - Reorder schedule
- `GET /api/live_schedule` - Get live schedule with current activity marked
- `POST /api/live_schedule/reorder` - Reorder live schedule (in-memory)

### Stage Messages
- `GET /api/stage_message` - Get active message
- `POST /api/stage_message` - Send message
- `DELETE /api/stage_message` - Clear message

### Countdown Timer
- `GET /api/countdown_timer` - Get active countdown
- `POST /api/countdown_timer` - Start countdown
- `DELETE /api/countdown_timer` - Stop countdown

### Auto-Start
- `GET /api/next_autostart` - Next scheduled auto-start info

## Background Threads

All start **after** `init_db()` in the `__main__` block:

1. **`update_timer_display()`** - Runs every 1 second. Updates countdown/program timer state, checks expiration, moves to next activity.
2. **`auto_start_checker()`** - Runs every 30 seconds. Checks for programs matching current day + time, triggers smart start.
3. **`sync_programs_from_remote()`** - Runs every 10 minutes. Fetches today's programs from RFM app API, syncs to local DB with hash-based change detection.

## Running Locally (Windows)

```bash
# Requires Python 3 and Flask
pip install flask
python app.py
# Admin: http://localhost/admin
# Kiosk: http://localhost/
```

## Raspberry Pi Deployment

- App directory: `/home/russel/church-timer/`
- Virtual environment: `/home/russel/church-timer/church-timer-env/`
- Logs: `app.log`, `kiosk.log`
- Chromium runs in kiosk mode with cursor hidden, screen blanking disabled
- Use `startup.sh` for the Flask server and `start-kiosk.sh` for the display

## Default Data

- **Activities**: Prayer (15m), Praise (15m), Announcements (5m), Bible reading (5m), Worship (15m), Word (60m), Admin/close (5m)
- **Programs**: Sunday Service (09:30, auto-start), Friday Service (18:00, auto-start)
