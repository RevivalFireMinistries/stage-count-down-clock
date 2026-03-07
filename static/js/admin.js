// admin.js - v2 Church Timer Admin
// All API logic preserved, UI updated for dark theme

let currentProgram = null;
let programs = [];
let activities = [];
let timerState = { is_running: false, is_paused: false };
let liveScheduleSortable = null;

document.addEventListener('DOMContentLoaded', function() {
    loadPrograms();
    loadActivities();
    startTimerStatusUpdates();

    // Stage message char count
    const msgInput = document.getElementById('stageMessageInput');
    const charCount = document.getElementById('messageCharCount');
    if (msgInput && charCount) {
        msgInput.addEventListener('input', () => charCount.textContent = msgInput.value.length);
    }

    // Duration slider display
    const slider = document.getElementById('messageDuration');
    const display = document.getElementById('durationDisplay');
    if (slider && display) {
        slider.addEventListener('input', () => {
            const s = parseInt(slider.value);
            display.textContent = `${Math.floor(s/60)}:${(s%60).toString().padStart(2,'0')}`;
        });
    }
});

// ── MODALS ──

function showModal(id) { document.getElementById(id).style.display = 'block'; }
function closeModal(id) { document.getElementById(id).style.display = 'none'; }

window.onclick = function(e) {
    document.querySelectorAll('.modal').forEach(m => {
        if (e.target === m) m.style.display = 'none';
    });
};

// ── ALERTS ──

function showAlert(message, type = 'success') {
    const container = document.getElementById('alertContainer');
    const el = document.createElement('div');
    el.className = `alert alert-${type}`;
    el.innerHTML = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4000);
}

// ── PROGRAMS ──

async function loadPrograms() {
    try {
        const res = await fetch('/api/programs');
        programs = await res.json();
        displayPrograms();
        displayProgramSelector();
    } catch (e) {
        console.error('Error loading programs:', e);
    }
}

function displayPrograms() {
    const list = document.getElementById('programList');
    list.innerHTML = '';
    if (programs.length === 0) {
        list.innerHTML = '<div class="empty-state"><i class="fas fa-calendar-plus"></i><p>No programs yet</p></div>';
        return;
    }
    programs.forEach(p => {
        const el = document.createElement('div');
        el.className = `program-item ${currentProgram && currentProgram.id === p.id ? 'current-program' : ''}`;
        const badge = p.auto_start ? '<span class="auto-start-badge">AUTO</span>' : '';
        el.innerHTML = `
            <div class="program-info">
                <h4>${p.name} ${badge}</h4>
                <p>${p.day_of_week || 'No day'} &middot; ${p.scheduled_start_time || 'No time'} &middot; ${p.activity_count} activities</p>
            </div>
            <div class="item-actions">
                <button class="btn btn-primary btn-sm" onclick="loadProgram(${p.id})"><i class="fas fa-folder-open"></i></button>
                <button class="btn btn-secondary btn-sm" onclick="editProgram(${p.id})"><i class="fas fa-edit"></i></button>
                <button class="btn btn-danger btn-sm" onclick="deleteProgram(${p.id})"><i class="fas fa-trash"></i></button>
            </div>`;
        list.appendChild(el);
    });
}

function displayProgramSelector() {
    const list = document.getElementById('programSelectorList');
    list.innerHTML = '';
    programs.forEach(p => {
        const el = document.createElement('div');
        el.className = 'program-item';
        const badge = p.auto_start ? '<span class="auto-start-badge">AUTO</span>' : '';
        el.innerHTML = `
            <div class="program-info">
                <h4>${p.name} ${badge}</h4>
                <p>${p.day_of_week || ''} &middot; ${p.scheduled_start_time || ''} &middot; ${p.activity_count} activities</p>
            </div>
            <button class="btn btn-primary btn-sm" onclick="loadProgram(${p.id}); closeModal('programSelectorModal')">
                <i class="fas fa-check"></i> Select
            </button>`;
        list.appendChild(el);
    });
}

async function loadProgram(id) {
    try {
        const res = await fetch(`/api/programs/${id}`);
        if (!res.ok) throw new Error(res.status);
        currentProgram = await res.json();
        displayCurrentProgram();
        displayProgramSchedule();
        showAlert(`"${currentProgram.name}" loaded`);
    } catch (e) {
        console.error('Error loading program:', e);
        showAlert('Error loading program', 'error');
        currentProgram = null;
    }
}

function displayCurrentProgram() {
    const info = document.getElementById('currentProgramInfo');
    const editBtn = document.getElementById('editCurrentProgramBtn');
    if (!info) return;

    if (currentProgram) {
        const auto = currentProgram.auto_start ? ' (Auto-start)' : '';
        info.innerHTML = `
            <h4 style="font-size:1rem; font-weight:600; margin-bottom:0.25rem;">${currentProgram.name}</h4>
            <p style="font-size:0.85rem; color:var(--text-dim); margin:0.15rem 0;">${currentProgram.description || ''}</p>
            <p style="font-size:0.8rem; color:var(--text-dim);">${currentProgram.day_of_week || ''} &middot; ${currentProgram.scheduled_start_time || 'No time'}${auto} &middot; ${currentProgram.schedule.length} activities</p>`;
        if (editBtn) editBtn.style.display = 'block';
    } else {
        info.innerHTML = '<p class="empty-text">No program loaded</p>';
        if (editBtn) editBtn.style.display = 'none';
    }
    displayPrograms();
}

// ── PROGRAM CRUD ──

async function createProgram(event) {
    event.preventDefault();
    const body = {
        name: document.getElementById('programName').value,
        description: document.getElementById('programDescription').value,
        scheduled_start_time: document.getElementById('programStartTime').value,
        day_of_week: document.getElementById('programDayOfWeek').value,
        auto_start: document.getElementById('programAutoStart').checked
    };
    try {
        const res = await fetch('/api/programs', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
        });
        const result = await res.json();
        if (res.ok) {
            closeModal('createProgramModal');
            document.getElementById('programName').value = '';
            document.getElementById('programDescription').value = '';
            document.getElementById('programStartTime').value = '';
            document.getElementById('programDayOfWeek').value = '';
            document.getElementById('programAutoStart').checked = false;
            await loadPrograms();
            showAlert('Program created');
            if (result.program_id) await loadProgram(result.program_id);
        } else {
            showAlert(result.error || 'Error creating program', 'error');
        }
    } catch (e) {
        showAlert('Error creating program', 'error');
    }
}

async function updateProgram(event) {
    event.preventDefault();
    const id = document.getElementById('editProgramId').value;
    const body = {
        name: document.getElementById('editProgramName').value,
        description: document.getElementById('editProgramDescription').value,
        scheduled_start_time: document.getElementById('editProgramStartTime').value,
        day_of_week: document.getElementById('editProgramDayOfWeek').value,
        auto_start: document.getElementById('editProgramAutoStart').checked
    };
    try {
        const res = await fetch(`/api/programs/${id}`, {
            method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
        });
        if (res.ok) {
            closeModal('editProgramModal');
            await loadPrograms();
            if (currentProgram && currentProgram.id == id) await loadProgram(id);
            showAlert('Program updated');
        } else {
            const r = await res.json();
            showAlert(r.error || 'Error updating', 'error');
        }
    } catch (e) {
        showAlert('Error updating program', 'error');
    }
}

async function deleteProgram(id) {
    if (!confirm('Delete this program? This cannot be undone.')) return;
    try {
        const res = await fetch(`/api/programs/${id}`, { method: 'DELETE' });
        if (res.ok) {
            if (currentProgram && currentProgram.id == id) { currentProgram = null; displayCurrentProgram(); }
            await loadPrograms();
            showAlert('Program deleted');
        }
    } catch (e) {
        showAlert('Error deleting program', 'error');
    }
}

async function deleteCurrentProgram() {
    if (currentProgram) { await deleteProgram(currentProgram.id); closeModal('editProgramModal'); }
}

function showCreateProgramModal() { showModal('createProgramModal'); }
function showProgramSelector() { showModal('programSelectorModal'); }

function showEditProgramModal() {
    if (!currentProgram) { showAlert('Load a program first', 'error'); return; }
    document.getElementById('editProgramId').value = currentProgram.id;
    document.getElementById('editProgramName').value = currentProgram.name;
    document.getElementById('editProgramDescription').value = currentProgram.description || '';
    document.getElementById('editProgramStartTime').value = currentProgram.scheduled_start_time || '';
    document.getElementById('editProgramDayOfWeek').value = currentProgram.day_of_week || '';
    document.getElementById('editProgramAutoStart').checked = currentProgram.auto_start || false;
    displayEditProgramSchedule();
    showModal('editProgramModal');
}

function displayEditProgramSchedule() {
    const list = document.getElementById('editProgramScheduleList');
    if (!list) return;
    list.innerHTML = '';
    if (!currentProgram || !currentProgram.schedule || currentProgram.schedule.length === 0) {
        list.innerHTML = '<div class="empty-state"><p>No activities yet</p></div>';
        return;
    }
    currentProgram.schedule.forEach((item, i) => {
        const el = document.createElement('div');
        el.className = 'schedule-item';
        el.setAttribute('data-id', item.id);
        el.innerHTML = `
            <div style="display:flex; align-items:center; gap:0.5rem; flex:1;">
                <span style="color:var(--text-muted); font-size:0.8rem;">${i+1}.</span>
                <strong style="font-size:0.875rem;">${item.activity_name}</strong>
                <span style="color:var(--text-dim); font-size:0.8rem;">(${item.duration_minutes}m)</span>
            </div>
            <button class="btn btn-danger btn-sm" onclick="removeFromScheduleInModal(${item.id})" style="padding:0.2rem 0.4rem;">
                <i class="fas fa-times"></i>
            </button>`;
        list.appendChild(el);
    });
}

function editProgram(id) {
    loadProgram(id).then(() => showEditProgramModal());
}

function editCurrentProgram() {
    if (currentProgram) showEditProgramModal();
}

function showCreateActivityFromProgram() { showModal('createActivityModal'); }
function showAddActivityFromProgram() { populateActivitySelector(); showModal('addActivityModal'); }

// ── SCHEDULE ──

function displayProgramSchedule() {
    const el = document.getElementById('programSchedule');
    el.innerHTML = '';
    if (!currentProgram || !currentProgram.schedule || currentProgram.schedule.length === 0) {
        el.innerHTML = '<div class="empty-state"><p>No activities in schedule</p></div>';
        return;
    }
    currentProgram.schedule.forEach(item => {
        const div = document.createElement('div');
        div.className = 'schedule-item';
        div.setAttribute('data-id', item.id);
        div.innerHTML = `
            <div><span class="drag-handle"><i class="fas fa-grip-vertical"></i></span> <strong>${item.activity_name}</strong></div>
            <div><span style="font-size:0.85rem; color:var(--text-dim);">${item.duration_minutes}m</span>
                <button class="btn btn-danger btn-sm" onclick="removeFromSchedule(${item.id})" style="margin-left:0.5rem;"><i class="fas fa-trash"></i></button>
            </div>`;
        el.appendChild(div);
    });
    new Sortable(el, {
        handle: '.drag-handle', animation: 150,
        onEnd: async function() {
            const order = Array.from(el.children).map(c => c.getAttribute('data-id'));
            await reorderSchedule(order);
        }
    });
}

async function reorderSchedule(order) {
    try {
        const res = await fetch(`/api/programs/${currentProgram.id}/schedule/reorder`, {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ order })
        });
        if (res.ok) { await loadProgram(currentProgram.id); showAlert('Schedule reordered'); }
    } catch (e) { showAlert('Error reordering', 'error'); }
}

function showAddActivityModal() {
    if (!currentProgram) { showAlert('Load a program first', 'error'); return; }
    showModal('addActivityModal');
}

async function addActivityToSchedule() {
    const activityId = document.getElementById('activitySelect').value;
    const duration = parseInt(document.getElementById('scheduleActivityDuration').value);
    if (!activityId) { showAlert('Select an activity', 'error'); return; }
    try {
        const res = await fetch(`/api/programs/${currentProgram.id}/schedule`, {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ activity_id: activityId, duration_minutes: duration })
        });
        if (res.ok) {
            closeModal('addActivityModal');
            await loadProgram(currentProgram.id);
            const editModal = document.getElementById('editProgramModal');
            if (editModal && editModal.style.display === 'block') displayEditProgramSchedule();
            showAlert('Activity added');
        }
    } catch (e) { showAlert('Error adding activity', 'error'); }
}

async function removeFromSchedule(id) {
    if (!confirm('Remove this activity?')) return;
    try {
        const res = await fetch(`/api/programs/${currentProgram.id}/schedule/${id}`, { method: 'DELETE' });
        if (res.ok) { await loadProgram(currentProgram.id); showAlert('Removed'); }
    } catch (e) { showAlert('Error removing', 'error'); }
}

async function removeFromScheduleInModal(id) {
    if (!confirm('Remove this activity?')) return;
    try {
        const res = await fetch(`/api/programs/${currentProgram.id}/schedule/${id}`, { method: 'DELETE' });
        if (res.ok) { await loadProgram(currentProgram.id); displayEditProgramSchedule(); showAlert('Removed'); }
    } catch (e) { showAlert('Error removing', 'error'); }
}

// ── ACTIVITIES ──

async function loadActivities() {
    try {
        const res = await fetch('/api/activities');
        activities = await res.json();
        displayActivities();
        populateActivitySelect();
    } catch (e) { console.error('Error loading activities:', e); }
}

function displayActivities() {
    const list = document.getElementById('activityList');
    list.innerHTML = '';
    if (activities.length === 0) {
        list.innerHTML = '<div class="empty-state"><i class="fas fa-tasks"></i><p>No activities yet</p></div>';
        return;
    }
    activities.forEach(a => {
        const el = document.createElement('div');
        el.className = 'activity-item';
        el.innerHTML = `
            <div class="activity-info">
                <h4>${a.name}</h4>
                <p>${a.description || ''} &middot; ${a.default_duration}min default</p>
            </div>
            <div class="item-actions">
                <button class="btn btn-secondary btn-sm" onclick="editActivity(${a.id})"><i class="fas fa-edit"></i></button>
            </div>`;
        list.appendChild(el);
    });
}

async function createActivity(event) {
    event.preventDefault();
    const body = {
        name: document.getElementById('activityName').value,
        default_duration: parseInt(document.getElementById('activityDuration').value),
        description: document.getElementById('activityDescription').value
    };
    try {
        const res = await fetch('/api/activities', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
        });
        if (res.ok) {
            closeModal('createActivityModal');
            document.getElementById('activityName').value = '';
            document.getElementById('activityDuration').value = '5';
            document.getElementById('activityDescription').value = '';
            await loadActivities();
            showAlert('Activity created');
        }
    } catch (e) { showAlert('Error creating activity', 'error'); }
}

function showCreateActivityModal() { showModal('createActivityModal'); }
function populateActivitySelect() { populateActivitySelector(); }

function populateActivitySelector() {
    const sel = document.getElementById('activitySelect');
    sel.innerHTML = '';
    if (activities.length === 0) {
        sel.innerHTML = '<option value="">No activities - create one first</option>';
        return;
    }
    activities.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.id;
        opt.textContent = `${a.name} (${a.default_duration}min)`;
        sel.appendChild(opt);
    });
    if (activities.length > 0) {
        document.getElementById('scheduleActivityDuration').value = activities[0].default_duration;
        sel.addEventListener('change', function() {
            const act = activities.find(a => a.id == this.value);
            if (act) document.getElementById('scheduleActivityDuration').value = act.default_duration;
        });
    }
}

function editActivity(id) {
    const activity = activities.find(a => a.id == id);
    if (!activity) { showAlert('Activity not found', 'error'); return; }
    document.getElementById('editActivityId').value = activity.id;
    document.getElementById('editActivityName').value = activity.name;
    document.getElementById('editActivityDuration').value = activity.default_duration;
    document.getElementById('editActivityDescription').value = activity.description || '';
    showModal('editActivityModal');
}

async function updateActivity(event) {
    event.preventDefault();
    const id = document.getElementById('editActivityId').value;
    const body = {
        name: document.getElementById('editActivityName').value,
        default_duration: parseInt(document.getElementById('editActivityDuration').value),
        description: document.getElementById('editActivityDescription').value
    };
    try {
        const res = await fetch(`/api/activities/${id}`, {
            method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body)
        });
        if (res.ok) {
            closeModal('editActivityModal');
            await loadActivities();
            showAlert('Activity updated');
        } else {
            const r = await res.json();
            showAlert(r.error || 'Error updating', 'error');
        }
    } catch (e) { showAlert('Error updating activity', 'error'); }
}

async function deleteActivity() {
    const id = document.getElementById('editActivityId').value;
    if (!confirm('Delete this activity? It must not be in any program schedule.')) return;
    try {
        const res = await fetch(`/api/activities/${id}`, { method: 'DELETE' });
        if (res.ok) {
            closeModal('editActivityModal');
            await loadActivities();
            showAlert('Activity deleted');
        } else {
            const r = await res.json();
            showAlert(r.error || 'Error deleting', 'error');
        }
    } catch (e) { showAlert('Error deleting activity', 'error'); }
}

// ── TIMER CONTROLS ──

async function startCurrentProgram() {
    if (!currentProgram) { showAlert('Load a program first', 'error'); return; }
    try {
        const res = await fetch('/api/start_program', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ program_id: currentProgram.id })
        });
        if (res.ok) { showAlert('Program started'); updateTimerControls(true, false); }
    } catch (e) { showAlert('Error starting program', 'error'); }
}

async function startProgramSmart() {
    if (!currentProgram) { showAlert('Load a program first', 'error'); return; }
    try {
        const res = await fetch('/api/start_program_smart', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ program_id: currentProgram.id })
        });
        const result = await res.json();
        if (res.ok) {
            if (result.status === 'waiting') {
                showAlert(`Will start at ${result.scheduled_start}`);
                await fetch('/api/set_waiting_state', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({
                        waiting: true,
                        scheduled_start: result.scheduled_start,
                        program_name: result.program_name,
                        program_id: currentProgram.id
                    })
                });
            } else {
                showAlert('Program started');
                updateTimerControls(true, false);
            }
        }
    } catch (e) { showAlert('Error starting program', 'error'); }
}

async function pauseTimer() {
    try {
        const res = await fetch('/api/pause_timer', { method: 'POST' });
        if (res.ok) updateTimerControls(true, true);
    } catch (e) { showAlert('Error pausing', 'error'); }
}

async function resumeTimer() {
    try {
        const res = await fetch('/api/resume_timer', { method: 'POST' });
        if (res.ok) updateTimerControls(true, false);
    } catch (e) { showAlert('Error resuming', 'error'); }
}

async function stopTimer() {
    if (!confirm('Stop the timer? This clears all running programs and waiting states.')) return;
    try {
        const res = await fetch('/api/stop_timer', { method: 'POST' });
        if (res.ok) { updateTimerControls(false, false); showAlert('Timer stopped'); }
    } catch (e) { showAlert('Error stopping', 'error'); }
}

async function nextItem() {
    try {
        const res = await fetch('/api/next_item', { method: 'POST' });
        if (res.ok) showAlert('Next item');
    } catch (e) { showAlert('Error', 'error'); }
}

function updateTimerControls(running, paused) {
    timerState.is_running = running;
    timerState.is_paused = paused;
    document.getElementById('startBtn').disabled = running;
    document.getElementById('smartStartBtn').disabled = running;
    document.getElementById('pauseBtn').disabled = !running || paused;
    document.getElementById('resumeBtn').disabled = !running || !paused;
    document.getElementById('stopBtn').disabled = !running;
    document.getElementById('nextBtn').disabled = !running;
}

// ── LIVE SCHEDULE ──

async function updateLiveSchedule() {
    try {
        const res = await fetch('/api/live_schedule');
        const data = await res.json();
        const list = document.getElementById('liveScheduleList');
        list.innerHTML = '';
        if (data.schedule.length === 0) return;

        data.schedule.forEach(item => {
            const el = document.createElement('div');
            el.className = 'live-schedule-item';
            el.setAttribute('data-id', item.id);
            if (item.id === data.current_schedule_id && data.is_running) el.classList.add('current-activity');
            el.innerHTML = `
                <div class="live-schedule-item-info">
                    <span class="drag-handle"><i class="fas fa-grip-vertical"></i></span>
                    <strong>${item.activity_name}</strong>
                </div>
                <div class="live-schedule-item-duration">${item.duration_minutes}m</div>`;
            list.appendChild(el);
        });

        if (liveScheduleSortable) liveScheduleSortable.destroy();
        liveScheduleSortable = new Sortable(list, {
            handle: '.drag-handle', animation: 150,
            onEnd: async function() {
                const order = Array.from(list.children).map(c => parseInt(c.getAttribute('data-id')));
                await reorderLiveSchedule(order);
            }
        });
    } catch (e) { console.error('Error updating live schedule:', e); }
}

async function reorderLiveSchedule(order) {
    try {
        const res = await fetch('/api/live_schedule/reorder', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ order })
        });
        if (res.ok) showAlert('Reordered (temporary)');
    } catch (e) { showAlert('Error reordering', 'error'); }
}

// ── STATUS UPDATES ──

function startTimerStatusUpdates() {
    setInterval(updateTimerStatus, 1000);
}

async function updateTimerStatus() {
    try {
        const res = await fetch('/api/timer_status');
        const s = await res.json();

        // Status text + dot
        const dot = document.querySelector('.status-dot');
        const text = document.getElementById('statusText');
        if (s.is_running) {
            text.textContent = s.is_paused ? 'PAUSED' : 'RUNNING';
            dot.className = 'status-dot ' + (s.is_paused ? 'paused' : 'running');
        } else {
            text.textContent = 'STOPPED';
            dot.className = 'status-dot stopped';
        }

        document.getElementById('currentActivity').textContent = s.current_activity || '-';
        document.getElementById('timeRemaining').textContent = s.time_remaining;

        updateTimerControls(s.is_running, s.is_paused);

        // Live schedule
        const liveCard = document.getElementById('liveScheduleCard');
        if (s.is_running) { liveCard.style.display = 'block'; updateLiveSchedule(); }
        else { liveCard.style.display = 'none'; }

        // Queue
        const qCard = document.getElementById('queuedProgramCard');
        const qp = s.queued_program;
        if (qp && qp.has_queued) {
            qCard.style.display = 'block';
            document.getElementById('queuedProgramName').textContent = qp.program_name;
            const parts = qp.scheduled_start_time.split(':');
            if (parts.length === 2) {
                const now = new Date();
                const target = new Date();
                target.setHours(parseInt(parts[0]), parseInt(parts[1]), 0, 0);
                const diff = Math.max(0, Math.floor((target - now) / 1000));
                const h = Math.floor(diff / 3600);
                const m = Math.floor((diff % 3600) / 60);
                const sec = diff % 60;
                const pad = n => String(n).padStart(2, '0');
                document.getElementById('queuedProgramCountdown').textContent =
                    `${pad(h)}:${pad(m)}:${pad(sec)} \u2022 starts at ${qp.scheduled_start_time}`;
            }
        } else {
            qCard.style.display = 'none';
        }
    } catch (e) { console.error('Error updating status:', e); }
}

async function clearQueue() {
    try { await fetch('/api/clear_queue', { method: 'POST' }); }
    catch (e) { console.error('Error clearing queue:', e); }
}

async function resetScreen() {
    if (!confirm('Reset screen? This stops ALL running programs, countdowns, messages, and queued items.')) return;
    try {
        const res = await fetch('/api/reset_screen', { method: 'POST' });
        if (res.ok) {
            updateTimerControls(false, false);
            showAlert('Screen reset to idle');
        }
    } catch (e) { showAlert('Error resetting screen', 'error'); }
}

// ── STAGE MESSAGE ──

async function sendStageMessage() {
    const msg = document.getElementById('stageMessageInput').value.trim();
    const dur = parseInt(document.getElementById('messageDuration').value);
    if (!msg) { showMessageStatus('Enter a message', 'error'); return; }
    try {
        const res = await fetch('/api/stage_message', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ message: msg, duration_seconds: dur })
        });
        if (res.ok) {
            const m = Math.floor(dur/60), s = dur%60;
            showMessageStatus(`Sent for ${m}:${s.toString().padStart(2,'0')}`, 'success');
            document.getElementById('stageMessageInput').value = '';
            document.getElementById('messageCharCount').textContent = '0';
        } else { showMessageStatus('Failed to send', 'error'); }
    } catch (e) { showMessageStatus('Failed to send', 'error'); }
}

async function clearStageMessage() {
    try {
        const res = await fetch('/api/stage_message', { method: 'DELETE' });
        if (res.ok) showMessageStatus('Cleared', 'success');
    } catch (e) { showMessageStatus('Failed to clear', 'error'); }
}

function showMessageStatus(msg, type) {
    const el = document.getElementById('messageStatus');
    el.textContent = msg;
    el.style.display = 'block';
    el.style.background = type === 'success' ? 'var(--green-dim)' : 'var(--red-dim)';
    el.style.color = type === 'success' ? 'var(--green)' : 'var(--red)';
    el.style.border = '1px solid ' + (type === 'success' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)');
    setTimeout(() => el.style.display = 'none', 4000);
}

// ── COUNTDOWN TIMER ──

function selectCountdownType(type) {
    document.querySelectorAll('.countdown-type-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.type === type);
    });
    document.getElementById('durationInputSection').style.display = type === 'duration' ? 'block' : 'none';
    document.getElementById('targetTimeInputSection').style.display = type === 'target_time' ? 'block' : 'none';
    document.getElementById('quickPresetsSection').style.display = type === 'target_time' ? 'grid' : 'none';
}

function setQuickPreset(preset) {
    const now = new Date();
    const t = document.getElementById('targetTime');
    const n = document.getElementById('countdownName');
    switch(preset) {
        case 'midnight': t.value = '00:00'; n.value = 'Countdown to Midnight'; break;
        case 'noon': t.value = '12:00'; n.value = 'Countdown to Noon'; break;
        case 'hour':
            const nh = new Date(now); nh.setHours(nh.getHours()+1,0,0,0);
            t.value = `${nh.getHours().toString().padStart(2,'0')}:00`;
            n.value = 'Countdown to Top of Hour'; break;
        case 'half':
            const hh = new Date(now);
            if (now.getMinutes() < 30) hh.setMinutes(30,0,0);
            else hh.setHours(hh.getHours()+1,0,0,0);
            t.value = `${hh.getHours().toString().padStart(2,'0')}:${hh.getMinutes().toString().padStart(2,'0')}`;
            n.value = 'Countdown to Half Hour'; break;
    }
}

async function startCountdownTimer() {
    const type = document.querySelector('.countdown-type-btn.active').dataset.type;
    const name = document.getElementById('countdownName').value.trim() || 'Countdown';
    let payload = { timer_type: type, name };

    if (type === 'duration') {
        const mins = parseInt(document.getElementById('countdownMinutes').value) || 0;
        const secs = parseInt(document.getElementById('countdownSeconds').value) || 0;
        const total = mins * 60 + secs;
        if (total <= 0) { showCountdownStatus('Enter a valid duration', 'error'); return; }
        payload.duration_seconds = total;
    } else {
        const target = document.getElementById('targetTime').value;
        if (!target) { showCountdownStatus('Select a target time', 'error'); return; }
        payload.target_time = target;
    }

    try {
        const res = await fetch('/api/countdown_timer', {
            method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload)
        });
        if (res.ok) { showCountdownStatus(`Started: ${name}`, 'success'); showAlert(`Countdown "${name}" started`); }
        else { const e = await res.json(); showCountdownStatus(e.error || 'Failed', 'error'); }
    } catch (e) { showCountdownStatus('Failed to start', 'error'); }
}

async function stopCountdownTimer() {
    try {
        const res = await fetch('/api/countdown_timer', { method: 'DELETE' });
        if (res.ok) { showCountdownStatus('Stopped', 'success'); showAlert('Countdown stopped', 'info'); }
    } catch (e) { showCountdownStatus('Failed to stop', 'error'); }
}

// ── THEME ──

async function setTheme(theme) {
    try {
        const res = await fetch('/api/kiosk_theme', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ theme })
        });
        if (res.ok) {
            document.querySelectorAll('.theme-option').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.theme === theme);
            });
            showAlert(`Theme: ${theme}`);
        }
    } catch (e) { showAlert('Error setting theme', 'error'); }
}

async function setFont(font) {
    try {
        const res = await fetch('/api/kiosk_theme', {
            method: 'POST', headers: {'Content-Type':'application/json'},
            body: JSON.stringify({ font })
        });
        if (res.ok) {
            document.querySelectorAll('.font-option').forEach(btn => {
                btn.classList.toggle('active', btn.dataset.font === font);
            });
            showAlert(`Font: ${font}`);
        }
    } catch (e) { showAlert('Error setting font', 'error'); }
}

// Load current theme + font on startup
fetch('/api/kiosk_theme').then(r=>r.json()).then(d => {
    document.querySelectorAll('.theme-option').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.theme === d.theme);
    });
    document.querySelectorAll('.font-option').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.font === d.font);
    });
}).catch(()=>{});

function showCountdownStatus(msg, type) {
    const el = document.getElementById('countdownStatus');
    el.textContent = msg;
    el.style.display = 'block';
    el.style.background = type === 'success' ? 'var(--green-dim)' : 'var(--red-dim)';
    el.style.color = type === 'success' ? 'var(--green)' : 'var(--red)';
    el.style.border = '1px solid ' + (type === 'success' ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)');
    setTimeout(() => el.style.display = 'none', 4000);
}
