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
        
        if (!response.ok) {
            throw new Error(`Failed to load program: ${response.status}`);
        }
        
        currentProgram = await response.json();
        displayCurrentProgram();
        displayProgramSchedule();
        showAlert(`Program "${currentProgram.name}" loaded successfully`);
    } catch (error) {
        console.error('Error loading program:', error);
        showAlert('Error loading program: ' + error.message, 'error');
        currentProgram = null;
    }
}

function displayCurrentProgram() {
    const currentProgramInfo = document.getElementById('currentProgramInfo');
    const editCurrentProgramBtn = document.getElementById('editCurrentProgramBtn');
    
    if (!currentProgramInfo) {
        console.error('currentProgramInfo element not found');
        return;
    }
    
    if (currentProgram) {
        const autoStartText = currentProgram.auto_start ? ' (Auto-start enabled)' : '';
        
        currentProgramInfo.innerHTML = `
            <h4>${currentProgram.name}</h4>
            <p>${currentProgram.description || 'No description'}</p>
            <p><strong>Day:</strong> ${currentProgram.day_of_week || 'Not set'}</p>
            <p><strong>Scheduled Start:</strong> ${currentProgram.scheduled_start_time || 'Not set'}${autoStartText}</p>
            <p><strong>${currentProgram.schedule.length}</strong> activities in schedule</p>
        `;
        
        // Check if elements exist before accessing
        const programScheduleCard = document.getElementById('programScheduleCard');
        if (programScheduleCard) {
            programScheduleCard.style.display = 'block';
        }
        
        if (editCurrentProgramBtn) {
            editCurrentProgramBtn.style.display = 'block';
        }
    } else {
        currentProgramInfo.innerHTML = '<p class="empty-text">No program loaded</p>';
        
        const programScheduleCard = document.getElementById('programScheduleCard');
        if (programScheduleCard) {
            programScheduleCard.style.display = 'none';
        }
        
        if (editCurrentProgramBtn) {
            editCurrentProgramBtn.style.display = 'none';
        }
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
    
    // Populate the schedule list in the modal
    displayEditProgramSchedule();
    
    showModal('editProgramModal');
}

function displayEditProgramSchedule() {
    const scheduleList = document.getElementById('editProgramScheduleList');
    
    if (!scheduleList) {
        console.error('editProgramScheduleList element not found');
        return;
    }
    
    scheduleList.innerHTML = '';
    
    if (!currentProgram || !currentProgram.schedule || currentProgram.schedule.length === 0) {
        scheduleList.innerHTML = `
            <div class="empty-state" style="padding: 1rem; text-align: center;">
                <i class="fas fa-clock" style="font-size: 2rem; color: #bdc3c7; margin-bottom: 0.5rem;"></i>
                <p style="color: #7f8c8d; margin: 0;">No activities yet. Add some to get started!</p>
            </div>
        `;
        return;
    }
    
    currentProgram.schedule.forEach((item, index) => {
        const scheduleItem = document.createElement('div');
        scheduleItem.className = 'schedule-item';
        scheduleItem.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 0.75rem; background: #f8f9fa; border-radius: 8px; margin-bottom: 0.5rem;';
        scheduleItem.setAttribute('data-id', item.id);
        
        scheduleItem.innerHTML = `
            <div style="display: flex; align-items: center; gap: 0.5rem; flex: 1;">
                <span style="color: #7f8c8d; font-size: 0.9rem;">${index + 1}.</span>
                <strong>${item.activity_name}</strong>
                <span style="color: #7f8c8d; font-size: 0.9rem;">(${item.duration_minutes} min)</span>
            </div>
            <button class="btn btn-danger btn-sm" onclick="removeFromScheduleInModal(${item.id})" style="padding: 0.25rem 0.5rem;">
                <i class="fas fa-times"></i>
            </button>
        `;
        scheduleList.appendChild(scheduleItem);
    });
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

// Open Create Activity modal from Edit Program modal
function showCreateActivityFromProgram() {
    // Don't close the edit program modal - we'll return to it
    showModal('createActivityModal');
}

// Open Add Activity to Schedule modal from Edit Program modal
function showAddActivityFromProgram() {
    // Populate the activity selector
    populateActivitySelector();
    showModal('addActivityModal');
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
    
    if (!activityId) {
        showAlert('Please select an activity', 'error');
        return;
    }
    
    try {
        const response = await fetch(`/api/programs/${currentProgram.id}/schedule`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ activity_id: activityId, duration_minutes: duration })
        });
        
        if (response.ok) {
            closeModal('addActivityModal');
            await loadProgram(currentProgram.id);
            
            // If edit program modal is open, refresh its schedule list
            const editProgramModal = document.getElementById('editProgramModal');
            if (editProgramModal && editProgramModal.style.display === 'block') {
                displayEditProgramSchedule();
                showAlert('Activity added to schedule!');
            } else {
                showAlert('Activity added to schedule');
            }
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

async function removeFromScheduleInModal(scheduleId) {
    if (!confirm('Remove this activity from the schedule?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/programs/${currentProgram.id}/schedule/${scheduleId}`, {
            method: 'DELETE'
        });
        
        if (response.ok) {
            await loadProgram(currentProgram.id);
            // Refresh the schedule list in the modal
            displayEditProgramSchedule();
            showAlert('Activity removed from schedule');
        } else {
            const result = await response.json();
            showAlert(result.error || 'Error removing activity', 'error');
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
            showAlert('Activity created successfully! You can now add it to the schedule.');
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
    populateActivitySelector();
}

function populateActivitySelector() {
    const activitySelect = document.getElementById('activitySelect');
    activitySelect.innerHTML = '';
    
    if (activities.length === 0) {
        activitySelect.innerHTML = '<option value="">No activities available - create one first</option>';
        return;
    }
    
    activities.forEach(activity => {
        const option = document.createElement('option');
        option.value = activity.id;
        option.textContent = `${activity.name} (${activity.default_duration}min default)`;
        activitySelect.appendChild(option);
    });
    
    // Auto-populate duration with first activity's default
    if (activities.length > 0) {
        document.getElementById('scheduleActivityDuration').value = activities[0].default_duration;
        
        // Update duration when selection changes
        activitySelect.addEventListener('change', function() {
            const selectedActivity = activities.find(a => a.id == this.value);
            if (selectedActivity) {
                document.getElementById('scheduleActivityDuration').value = selectedActivity.default_duration;
            }
        });
    }
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
    // Show confirmation dialog
    if (!confirm('Are you sure you want to STOP the timer? This will clear all running programs and waiting states.')) {
        return; // User cancelled
    }
    
    try {
        const response = await fetch('/api/stop_timer', { method: 'POST' });
        if (response.ok) {
            updateTimerControls(false, false);
            showAlert('Timer stopped and reset');
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
    setInterval(updateAutoStartStatus, 10000); // Update every 10 seconds
    updateAutoStartStatus(); // Initial call
}

async function updateAutoStartStatus() {
    try {
        const response = await fetch('/api/next_autostart');
        const data = await response.json();
        
        const autoStartCard = document.getElementById('autoStartCard');
        const autoStartMessage = document.getElementById('autoStartMessage');
        const autoStartCountdown = document.getElementById('autoStartCountdown');
        
        if (data.has_autostart && !data.is_future_day) {
            // Show the auto-start card
            autoStartCard.style.display = 'block';
            
            // Update message
            autoStartMessage.textContent = `"${data.program_name}" will start automatically at ${data.scheduled_time} (${data.day_of_week})`;
            
            // Update countdown
            if (data.minutes_until !== undefined) {
                if (data.minutes_until <= 0) {
                    autoStartCountdown.textContent = 'Starting now...';
                    autoStartCountdown.style.color = '#27ae60';
                } else if (data.minutes_until <= 5) {
                    autoStartCountdown.textContent = `⏱️ Starting in ${data.minutes_until} minute${data.minutes_until !== 1 ? 's' : ''}!`;
                    autoStartCountdown.style.color = '#e74c3c';
                } else if (data.minutes_until <= 15) {
                    autoStartCountdown.textContent = `Starting in ${data.time_display}`;
                    autoStartCountdown.style.color = '#f39c12';
                } else {
                    autoStartCountdown.textContent = `Starting in ${data.time_display}`;
                    autoStartCountdown.style.color = '#3498db';
                }
            } else {
                autoStartCountdown.textContent = '';
            }
        } else if (data.has_autostart && data.is_future_day) {
            // Show info about future program
            autoStartCard.style.display = 'block';
            autoStartMessage.textContent = `Next auto-start: "${data.program_name}" on ${data.day_of_week} at ${data.scheduled_time}`;
            autoStartCountdown.textContent = '';
        } else {
            // Hide the auto-start card
            autoStartCard.style.display = 'none';
        }
    } catch (error) {
        console.error('Error updating auto-start status:', error);
        // Hide card on error
        const autoStartCard = document.getElementById('autoStartCard');
        if (autoStartCard) {
            autoStartCard.style.display = 'none';
        }
    }
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
// ============================================================================
// STAGE MESSAGE FUNCTIONS
// ============================================================================

// Update character count

// ============================================================================
// STAGE MESSAGE FUNCTIONS
// ============================================================================

async function sendStageMessage() {
    const messageInput = document.getElementById('stageMessageInput');
    const durationSlider = document.getElementById('messageDuration');
    const statusDiv = document.getElementById('messageStatus');
    
    const message = messageInput.value.trim();
    const duration = parseInt(durationSlider.value);
    
    if (!message) {
        showMessageStatus('Please enter a message', 'error');
        return;
    }
    
    try {
        const response = await fetch('/api/stage_message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                duration_seconds: duration
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const minutes = Math.floor(duration / 60);
            const secs = duration % 60;
            const timeStr = `${minutes}:${secs.toString().padStart(2, '0')}`;
            
            showMessageStatus(`✓ Message sent to stage! Will display for ${timeStr}`, 'success');
            
            // Clear input after successful send
            messageInput.value = '';
            document.getElementById('messageCharCount').textContent = '0';
        } else {
            showMessageStatus('Error: ' + (data.error || 'Failed to send message'), 'error');
        }
    } catch (error) {
        console.error('Error sending stage message:', error);
        showMessageStatus('Error: Failed to send message', 'error');
    }
}

async function clearStageMessage() {
    const statusDiv = document.getElementById('messageStatus');
    
    try {
        const response = await fetch('/api/stage_message', {
            method: 'DELETE'
        });
        
        if (response.ok) {
            showMessageStatus('✓ Stage message cleared', 'success');
        } else {
            showMessageStatus('Error: Failed to clear message', 'error');
        }
    } catch (error) {
        console.error('Error clearing stage message:', error);
        showMessageStatus('Error: Failed to clear message', 'error');
    }
}

function showMessageStatus(message, type) {
    const statusDiv = document.getElementById('messageStatus');
    
    statusDiv.textContent = message;
    statusDiv.style.display = 'block';
    
    if (type === 'success') {
        statusDiv.style.background = '#d4edda';
        statusDiv.style.color = '#155724';
        statusDiv.style.border = '1px solid #c3e6cb';
    } else if (type === 'error') {
        statusDiv.style.background = '#f8d7da';
        statusDiv.style.color = '#721c24';
        statusDiv.style.border = '1px solid #f5c6cb';
    }
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        statusDiv.style.display = 'none';
    }, 5000);
}

// Initialize stage message event listeners when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    const messageInput = document.getElementById('stageMessageInput');
    const charCount = document.getElementById('messageCharCount');
    const durationSlider = document.getElementById('messageDuration');
    const durationDisplay = document.getElementById('durationDisplay');
    
    if (messageInput && charCount) {
        messageInput.addEventListener('input', function() {
            charCount.textContent = this.value.length;
        });
    }
    
    if (durationSlider && durationDisplay) {
        durationSlider.addEventListener('input', function() {
            const seconds = parseInt(this.value);
            const minutes = Math.floor(seconds / 60);
            const secs = seconds % 60;
            durationDisplay.textContent = `${minutes}:${secs.toString().padStart(2, '0')}`;
        });
    }
});
