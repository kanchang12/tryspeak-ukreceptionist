// TrySpeak JavaScript

const API_URL = window.location.origin;

// Get stored auth data
function getAuthToken() {
    return localStorage.getItem('access_token');
}

function getOwnerId() {
    return localStorage.getItem('owner_id');
}

// Check if user is authenticated
function isAuthenticated() {
    return !!getAuthToken() && !!getOwnerId();
}

// Redirect to login if not authenticated
function requireAuth() {
    if (!isAuthenticated()) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

// API fetch wrapper with auth
async function fetchAPI(endpoint, options = {}) {
    const token = getAuthToken();
    const ownerId = getOwnerId();
    
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };
    
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }
    
    if (ownerId) {
        headers['X-Owner-ID'] = ownerId;
    }
    
    const response = await fetch(`${API_URL}${endpoint}`, {
        ...options,
        headers
    });
    
    if (response.status === 401) {
        localStorage.removeItem('access_token');
        localStorage.removeItem('owner_id');
        window.location.href = '/login';
        throw new Error('Unauthorized');
    }
    
    return response;
}

// Format phone number
function formatPhone(phone) {
    if (!phone) return 'Unknown';
    return phone;
}

// Format date/time
function formatDateTime(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleString('en-GB', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatTime(dateString) {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Format duration (seconds to minutes)
function formatDuration(seconds) {
    if (!seconds) return '0 mins';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
}

// Show loading state
function showLoading(elementId) {
    const el = document.getElementById(elementId);
    if (el) {
        el.innerHTML = '<p style="text-align: center; color: #6B7280; padding: 2rem;">Loading...</p>';
    }
}

// Show error
function showError(elementId, message) {
    const el = document.getElementById(elementId);
    if (el) {
        el.innerHTML = `<p style="text-align: center; color: #DC2626; padding: 2rem;">${message}</p>`;
    }
}

// Show empty state
function showEmpty(elementId, message) {
    const el = document.getElementById(elementId);
    if (el) {
        el.innerHTML = `<p style="text-align: center; color: #6B7280; padding: 2rem;">${message}</p>`;
    }
}

// Copy to clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        alert('Copied to clipboard!');
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

// Logout
function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('owner_id');
    window.location.href = '/login';
}
