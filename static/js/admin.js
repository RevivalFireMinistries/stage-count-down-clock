// admin.js - Church Timer Admin Portal JavaScript

// Global state variables
let currentProgram = null;
let programs = [];
let activities = [];
let timerState = { is_running: false, is_paused: false };
let liveScheduleSortable = null;

// Initialize the admin interface when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    loadPrograms();
    loadActivities();
    startTimerStatusUpdates();
});

// ============================================================================
// MODAL FUNCTIONS
// ============================================================================

function showModal(modalId) {
    document.getElementById(modalId).style.display = 'block';
}

function closeModal(modalId) {
    document.getElementById(modalId).style.display = 'none';
}

// Close modals when clicking outside
window.onclick = function(event) {
    const modals = document.getElementsByClassName('modal');
    for (let modal of modals) {
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    }
}

// ============================================================================
// ALERT FUNCTIONS
// ============================================================================

function showAlert(message, type = 'success') {
    const alertContainer = document.getElementById('alertContainer');
    const alert = document.createElement('div');
    alert.className = `alert alert-${type}`;
    alert.innerHTML = message;
    alertContainer.appendChild(alert);
    
    setTimeout(() => {
        alert.remove();
    }, 5000);
}

// ============================================================================
// PROGRAM LOADING AND DISPLAY
// ============================================================================

async function loadPrograms() {
    try {
        const response = await fetch('/api/programs');
        programs = await response.json();
        displayPrograms();
        displayProgramSelector();
    } catch (error) {
        console.error('Error loading programs:', error);
        showAlert('Error loading programs', 'error');
    }
}

function displayPrograms() {
    const programList = document.getElementById('programList');
    programList.innerHTML = '';
    
    if (programs.length === 0) {
        programList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-calendar-plus"></i>
                <p>No programs yet. Create your first program!</p>
            </div>
        `;
        return;
    }
    
    programs.forEach(program => {
        const programItem = document.createElement('div');
        programItem.className = `program-item ${currentProgram && currentProgram.id === program.id ? 'current-program' : ''}`;
        
        const autoStartBadge = program.auto_start ? 
            '<span class="auto-start-badge">AUTO</span>' : '';
        
        programItem.innerHTML = `
            <div class="program-info">
                <h4>${program.name}${autoStartBadge}</h4>
                <p>${program.description || 'No description'}</p>
                <p><small>${program.day_of_week || 'No day set'} • Start: ${program.scheduled_start_time || 'Not set'} • ${program.activity_count} activities</small></p>
            </div>
            <div class="item-actions">
                <button class="btn btn-primary btn-sm" onclick="loadProgram(${program.id})">
                    <i class="fas fa-folder-open"></i> Load
                </button>
                <button class="btn btn-info btn-sm" onclick="editProgram(${program.id})">
                    <i class="fas fa-edit"></i> Edit
                </button>
                <button class="btn btn-danger btn-sm" onclick="deleteProgram(${program.id})">
                    <i class="fas fa-trash"></i> Delete
                </button>
            </div>
        `;
        programList.appendChild(programItem);
    });
}

function displayProgramSelector() {
    const programSelectorList = document.getElementById('programSelectorList');
    programSelectorList.innerHTML = '';
    
    programs.forEach(program => {
        const programItem = document.createElement('div');
        programItem.className = 'program-item';
        
        const autoStartBadge = program.auto_start ? 
            '<span class="auto-start-badge">AUTO</span>' : '';
        
        programItem.innerHTML = `
            <div class="program-info">
                <h4>${program.name} ${autoStartBadge}</h4>
                <p>${program.description || 'No description'} • ${program.activity_count} activities</p>
                <p><small>${program.day_of_week || 'No day'} • Start: ${program.scheduled_start_time || 'Not set'}</small></p>
            </div>
            <div class="item-actions">
                <button class="btn btn-primary" onclick="loadProgram(${program.id}); closeModal('programSelectorModal')">
                    <i class="fas fa-check"></i> Select
                </button>
            </div>
        `;
        programSelectorList.appendChild(programItem);
    });
}

async function loadProgram(programId) {
    try {
        const response = await fetch(`/api/programs/${programId}`);
        currentProgram = await response.json();
        displayCurrentProgram();
        displayProgramSchedule();
        showAlert(`Program "${currentProgram.name}" loaded successfully`);
    } catch (error) {
        console.error('Error loading program:', error);
        showAlert('Error loading program', 'error');
    }
}

function displayCurrentProgram() {
    const currentProgramInfo = document.getElementById('currentProgramInfo');
    const editCurrentProgramBtn = document.getElementById('editCurrentProgramBtn');
    
    if (currentProgram) {
        const autoStartText = currentProgram.auto_start ? ' (Auto-start enabled)' : '';
        
        currentProgramInfo.innerHTML = `
            <h4>${currentProgram.name}</h4>
            <p>${currentProgram.description || 'No description'}</p>
            <p><strong>Day:</strong> ${currentProgram.day_of_week || 'Not set'}</p>
            <p><strong>Scheduled Start:</strong> ${currentProgram.scheduled_start_time || 'Not set'}${autoStartText}</p>
            <p><strong>${currentProgram.schedule.length}</strong> activities in schedule</p>
        `;
        document.getElementById('programScheduleCard').style.display = 'block';
        editCurrentProgramBtn.style.display = 'block';
    } else {
        currentProgramInfo.innerHTML = '<p>No program loaded</p>';
        document.getElementById('programScheduleCard').style.display = 'none';
        editCurrentProgramBtn.style.display = 'none';
    }
    displayPrograms(); // Refresh to highlight current program
}

// ============================================================================
// PROGRAM CRUD OPERATIONS
// ============================================================================

async function createProgram(event) {
    event.preventDefault();
    const name = document.getElementById('programName').value;
    const description = document.getElementById('programDescription').value;
    const scheduled_start_time = document.getElementById('programStartTime').value;
    const day_of_week = document.getElementById('programDayOfWeek').value;
    const auto_start = document.getElementById('programAutoStart').checked;
    
    try {
        const response = await fetch('/api/programs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, scheduled_start_time, day_of_week, auto_start })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            closeModal('createProgramModal');
            document.getElementById('programName').value = '';
            document.getElementById('programDescription').value = '';
            document.getElementById('programStartTime').value = '';
            document.getElementById('programDayOfWeek').value = '';
            document.getElementById('programAutoStart').checked = false;
            await loadPrograms();
            showAlert('Program created successfully');
            
            // Auto-load the new program
            if (result.program_id) {
                await loadProgram(result.program_id);
            }
        } else {
            showAlert(result.error || 'Error creating program', 'error');
        }
    } catch (error) {
        console.error('Error creating program:', error);
        showAlert('Error creating program', 'error');
    }
}

async function updateProgram(event) {
    event.preventDefault();
    const programId = document.getElementById('editProgramId').value;
    const name = document.getElementById('editProgramName').value;
    const description = document.getElementById('editProgramDescription').value;
    const scheduled_start_time = document.getElementById('editProgramStartTime').value;
    const day_of_week = document.getElementById('editProgramDayOfWeek').value;
    const auto_start = document.getElementById('editProgramAutoStart').checked;
    
    try {
        const response = await fetch(`/api/programs/${programId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, description, scheduled_start_time, day_of_week, auto_start })
        });
        
        if (response.ok) {
            closeModal('editProgramModal');
            await loadPrograms();
            // Reload current program if it's the one being edited
            if (currentProgram && currentProgram.id == programId) {
                await loadProgram(programId);
            }
            showAlert('Program updated successfully');
        } else {
            const result = await response.json();
            showAlert(result.error || 'Error updating program', 'error');
        }
    } catch (error) {
        console.error('Error updating program:', error);
        showAlert('Error updating program', 'error');
    }
}

async function deleteProgram(programId) {
    if (!confirm('Are you sure you want to delete this program? This action cannot be undone.')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/programs/${programId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            // If we're deleting the current program, clear it
            if (currentProgram && currentProgram.id == programId) {
                currentProgram = null;
                displayCurrentProgram();
            }
            await loadPrograms();
            showAlert('Program deleted successfully');
        } else {
            const result = await response.json();
            showAlert(result.error || 'Error deleting program', 'error');
        }
    } catch (error) {
        console.error('Error deleting program:', error);
        showAlert('Error deleting program', 'error');
    }
}

async function deleteCurrentProgram() {
    if (currentProgram) {
        await deleteProgram(currentProgram.id);
        closeModal('editProgramModal');
    }
}

function showCreateProgramModal() {
    showModal('createProgramModal');
}

function showEditProgramModal() {
    if (!currentProgram) {
        showAlert('Please load a program first', 'error');
        return;
    }
    
    // Populate the edit form with current program data
    document.getElementById('editProgramId').value = currentProgram.id;
    document.getElementById('editProgramName').value = currentProgram.name;
    document.getElementById('editProgramDescription').value = currentProgram.description || '';
    document.getElementById('editProgramStartTime').value = currentProgram.scheduled_start_time || '';
    document.getElementById('editProgramDayOfWeek').value = currentProgram.day_of_week || '';
    document.getElementById('editProgramAutoStart').checked = currentProgram.auto_start || false;
    
    showModal('editProgramModal');
}

function editProgram(programId) {
    // Find the program in our list
    const program = programs.find(p => p.id == programId);
    if (program) {
        // Load the program first, then show edit modal
        loadProgram(programId).then(() => {
            showEditProgramModal();
        });
    }
}

function editCurrentProgram() {
    if (currentProgram) {
        showEditProgramModal();
    }
}

function showProgramSelector() {
    showModal('programSelectorModal');
}

// ============================================================================
// PROGRAM SCHEDULE MANAGEMENT
// ============================================================================

function displayProgramSchedule() {
    const programSchedule = document.getElementById('programSchedule');
    programSchedule.innerHTML = '';
    
    if (!currentProgram || !currentProgram.schedule || currentProgram.schedule.length === 0) {
        programSchedule.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-clock"></i>
                <p>No activities in schedule. Add activities to get started!</p>
            </div>
        `;
        return;
    }
    
    currentProgram.schedule.forEach(item => {
        const scheduleItem = document.createElement('div');
        scheduleItem.className = 'schedule-item';
        scheduleItem.setAttribute('data-id', item.id);
        scheduleItem.innerHTML = `
            <div>
                <span class="drag-handle"><i class="fas fa-grip-vertical"></i></span>
                <strong>${item.activity_name}</strong>
            </div>
            <div>
                <span>${item.duration_minutes} minutes</span>
                <button class="btn btn-danger btn-sm" onclick="removeFromSchedule(${item.id})" style="margin-left: 10px;">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        programSchedule.appendChild(scheduleItem);
    });
    
    // Initialize drag and drop for reordering
    new Sortable(programSchedule, {
        handle: '.drag-handle',
        animation: 150,
        onEnd: async function(evt) {
            const scheduleOrder = Array.from(programSchedule.children).map(child => child.getAttribute('data-id'));
            await reorderSchedule(scheduleOrder);
        }
    });
}

async function reorderSchedule(scheduleOrder) {
    try {
        const response = await fetch(`/api/programs/${currentProgram.id}/schedule/reorder`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order: scheduleOrder })
        });
        
        if (response.ok) {
            await loadProgram(currentProgram.id); // Reload to get updated order
            showAlert('Schedule reordered successfully');
        }
    } catch (error) {
        console.error('Error reordering schedule:', error);
        showAlert('Error reordering schedule', 'error');
    }
}

function showAddActivityModal() {
    if (!currentProgram) {
        showAlert('Please load a program first', 'error');
        return;
    }
    showModal('addActivityModal');
}

async function addActivityToSchedule() {
    const activityId = document.getElementById('activitySelect').value;
    const duration = parseInt(document.getElementById('scheduleActivityDuration').value);
    
    try {
        const response = await fetch(`/api/programs/${currentProgram.id}/schedule`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ activity_id: activityId, duration_minutes: duration })
        });
        
        if (response.ok) {
            closeModal('addActivityModal');
            await loadProgram(currentProgram.id);
            showAlert('Activity added to schedule');
        } else {
            const result = await response.json();
            showAlert(result.error || 'Error adding activity to schedule', 'error');
        }
    } catch (error) {
        console.error('Error adding activity to schedule:', error);
        showAlert('Error adding activity to schedule', 'error');
    }
}

async function removeFromSchedule(scheduleId) {
    if (!confirm('Are you sure you want to remove this activity from the schedule?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/programs/${currentProgram.id}/schedule/${scheduleId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            await loadProgram(currentProgram.id);
            showAlert('Activity removed from schedule');
        }
    } catch (error) {
        console.error('Error removing from schedule:', error);
        showAlert('Error removing activity from schedule', 'error');
    }
}

// ============================================================================
// ACTIVITY MANAGEMENT
// ============================================================================

async function loadActivities() {
    try {
        const response = await fetch('/api/activities');
        activities = await response.json();
        displayActivities();
        populateActivitySelect();
    } catch (error) {
        console.error('Error loading activities:', error);
        showAlert('Error loading activities', 'error');
    }
}

function displayActivities() {
    const activityList = document.getElementById('activityList');
    activityList.innerHTML = '';
    
    if (activities.length === 0) {
        activityList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-tasks"></i>
                <p>No activities yet. Create your first activity!</p>
            </div>
        `;
        return;
    }
    
    activities.forEach(activity => {
        const activityItem = document.createElement('div');
        activityItem.className = 'activity-item';
        activityItem.innerHTML = `
            <div class="activity-info">
                <h4>${activity.name}</h4>
                <p>${activity.description || 'No description'} • Default: ${activity.default_duration}min</p>
            </div>
            <div class="item-actions">
                <button class="btn btn-info btn-sm" onclick="editActivity(${activity.id})">
                    <i class="fas fa-edit"></i> Edit
                </button>
            </div>
        `;
        activityList.appendChild(activityItem);
    });
}

async function createActivity(event) {
    event.preventDefault();
    const name = document.getElementById('activityName').value;
    const default_duration = parseInt(document.getElementById('activityDuration').value);
    const description = document.getElementById('activityDescription').value;
    
    try {
        const response = await fetch('/api/activities', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, default_duration, description })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            closeModal('createActivityModal');
            document.getElementById('activityName').value = '';
            document.getElementById('activityDuration').value = '5';
            document.getElementById('activityDescription').value = '';
            await loadActivities();
            showAlert('Activity created successfully');
        } else {
            showAlert(result.error || 'Error creating activity', 'error');
        }
    } catch (error) {
        console.error('Error creating activity:', error);
        showAlert('Error creating activity', 'error');
    }
}

function showCreateActivityModal() {
    showModal('createActivityModal');
}

function populateActivitySelect() {
    const activitySelect = document.getElementById('activitySelect');
    activitySelect.innerHTML = '';
    
    activities.forEach(activity => {
        const option = document.createElement('option');
        option.value = activity.id;
        option.textContent = `${activity.name} (${activity.default_duration}min default)`;
        activitySelect.appendChild(option);
    });
}

// Placeholder function for activity editing
function editActivity(activityId) {
    showAlert('Edit activity feature coming soon!', 'info');
}

// ============================================================================
// TIMER CONTROL FUNCTIONS
// ============================================================================

async function startCurrentProgram() {
    if (!currentProgram) {
        showAlert('Please load a program first', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/start_program', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ program_id: currentProgram.id })
        });
        
        if (response.ok) {
            showAlert('Program started from beginning');
            updateTimerControls(true, false);
        }
    } catch (error) {
        console.error('Error starting program:', error);
        showAlert('Error starting program', 'error');
    }
}

async function startProgramSmart() {
    if (!currentProgram) {
        showAlert('Please load a program first', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/start_program_smart', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ program_id: currentProgram.id })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            if (result.status === 'waiting') {
                showAlert(`Service will start automatically at ${result.scheduled_start}`);
                
                // Set waiting state in kiosk display
                await fetch('/api/set_waiting_state', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        waiting: true,
                        scheduled_start: result.scheduled_start,
                        program_name: result.program_name,
                        program_id: currentProgram.id
                    })
                });
            } else {
                showAlert('Program started successfully');
                updateTimerControls(true, false);
            }
        }
    } catch (error) {
        console.error('Error starting program smartly:', error);
        showAlert('Error starting program', 'error');
    }
}

async function pauseTimer() {
    try {
        const response = await fetch('/api/pause_timer', { method: 'POST' });
        if (response.ok) {
            updateTimerControls(true, true);
        }
    } catch (error) {
        console.error('Error pausing timer:', error);
        showAlert('Error pausing timer', 'error');
    }
}

async function resumeTimer() {
    try {
        const response = await fetch('/api/resume_timer', { method: 'POST' });
        if (response.ok) {
            updateTimerControls(true, false);
        }
    } catch (error) {
        console.error('Error resuming timer:', error);
        showAlert('Error resuming timer', 'error');
    }
}

async function stopTimer() {
    try {
        const response = await fetch('/api/stop_timer', { method: 'POST' });
        if (response.ok) {
            updateTimerControls(false, false);
            showAlert('Timer stopped');
        }
    } catch (error) {
        console.error('Error stopping timer:', error);
        showAlert('Error stopping timer', 'error');
    }
}

async function nextItem() {
    try {
        const response = await fetch('/api/next_item', { method: 'POST' });
        if (response.ok) {
            showAlert('Moved to next item');
        }
    } catch (error) {
        console.error('Error moving to next item:', error);
        showAlert('Error moving to next item', 'error');
    }
}

function updateTimerControls(isRunning, isPaused) {
    timerState.is_running = isRunning;
    timerState.is_paused = isPaused;
    
    document.getElementById('startBtn').disabled = isRunning;
    document.getElementById('smartStartBtn').disabled = isRunning;
    document.getElementById('pauseBtn').disabled = !isRunning || isPaused;
    document.getElementById('resumeBtn').disabled = !isRunning || !isPaused;
    document.getElementById('stopBtn').disabled = !isRunning;
    document.getElementById('nextBtn').disabled = !isRunning;
}

// ============================================================================
// LIVE SCHEDULE MANAGEMENT
// ============================================================================

async function updateLiveSchedule() {
    try {
        const response = await fetch('/api/live_schedule');
        const data = await response.json();
        
        const liveScheduleList = document.getElementById('liveScheduleList');
        liveScheduleList.innerHTML = '';
        
        if (data.schedule.length === 0) {
            liveScheduleList.innerHTML = '<p style="color: #7f8c8d;">No schedule loaded</p>';
            return;
        }
        
        data.schedule.forEach(item => {
            const scheduleItem = document.createElement('div');
            scheduleItem.className = 'live-schedule-item';
            scheduleItem.setAttribute('data-id', item.id);
            
            if (item.id === data.current_schedule_id && data.is_running) {
                scheduleItem.classList.add('current-activity');
            }
            
            scheduleItem.innerHTML = `
                <div class="live-schedule-item-info">
                    <span class="drag-handle"><i class="fas fa-grip-vertical"></i></span>
                    <strong>${item.activity_name}</strong>
                </div>
                <div class="live-schedule-item-duration">
                    ${item.duration_minutes} min
                </div>
            `;
            liveScheduleList.appendChild(scheduleItem);
        });
        
        // Initialize or update sortable
        if (liveScheduleSortable) {
            liveScheduleSortable.destroy();
        }
        
        liveScheduleSortable = new Sortable(liveScheduleList, {
            handle: '.drag-handle',
            animation: 150,
            onEnd: async function(evt) {
                const scheduleOrder = Array.from(liveScheduleList.children)
                    .map(child => parseInt(child.getAttribute('data-id')));
                await reorderLiveSchedule(scheduleOrder);
            }
        });
    } catch (error) {
        console.error('Error updating live schedule:', error);
    }
}

async function reorderLiveSchedule(scheduleOrder) {
    try {
        const response = await fetch('/api/live_schedule/reorder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ order: scheduleOrder })
        });
        
        if (response.ok) {
            showAlert('Live schedule reordered (temporary change)', 'success');
        }
    } catch (error) {
        console.error('Error reordering live schedule:', error);
        showAlert('Error reordering live schedule', 'error');
    }
}

// ============================================================================
// TIMER STATUS UPDATES
// ============================================================================

async function startTimerStatusUpdates() {
    setInterval(updateTimerStatus, 1000);
}

async function updateTimerStatus() {
    try {
        const response = await fetch('/api/timer_status');
        const status = await response.json();
        
        document.getElementById('statusText').textContent = 
            status.is_running ? (status.is_paused ? 'PAUSED' : 'RUNNING') : 'STOPPED';
        document.getElementById('currentActivity').textContent = status.current_activity || '-';
        document.getElementById('timeRemaining').textContent = status.time_remaining;
        
        // Update status indicator
        const statusIndicator = document.querySelector('.status-indicator');
        statusIndicator.className = 'status-indicator ' + 
            (status.is_running ? (status.is_paused ? 'status-paused' : 'status-running') : 'status-stopped');
        
        // Update control buttons
        updateTimerControls(status.is_running, status.is_paused);
        
        // Show/hide live schedule card based on running state
        const liveScheduleCard = document.getElementById('liveScheduleCard');
        if (status.is_running) {
            liveScheduleCard.style.display = 'block';
            updateLiveSchedule();
        } else {
            liveScheduleCard.style.display = 'none';
        }
    } catch (error) {
        console.error('Error updating timer status:', error);
    }
}