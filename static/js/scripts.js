// TrySpeak Complete JavaScript

const API_URL = window.location.origin;

// === AUTH HELPERS ===
function getAuthToken() {
    return localStorage.getItem('access_token');
}

function getOwnerId() {
    return localStorage.getItem('owner_id');
}

function isAuthenticated() {
    return !!getAuthToken() && !!getOwnerId();
}

function requireAuth() {
    if (!isAuthenticated()) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('owner_id');
    window.location.href = '/login';
}

// === API WRAPPER ===
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

// === DASHBOARD FUNCTIONS ===
async function loadDashboard() {
    try {
        const response = await fetchAPI('/api/customer/dashboard');
        const data = await response.json();
        
        if (document.getElementById('businessName')) {
            document.getElementById('businessName').textContent = data.business_name || 'User';
        }
        if (document.getElementById('callsToday')) {
            document.getElementById('callsToday').textContent = data.calls_today || 0;
        }
        if (document.getElementById('emergenciesToday')) {
            document.getElementById('emergenciesToday').textContent = data.emergencies_today || 0;
        }
        if (document.getElementById('bookingsToday')) {
            document.getElementById('bookingsToday').textContent = data.bookings_today || 0;
        }
    } catch (error) {
        console.error('Error loading dashboard:', error);
    }
}

async function loadRecentCalls() {
    try {
        const response = await fetchAPI('/api/customer/calls?limit=5');
        const calls = await response.json();
        const container = document.getElementById('recentCallsList');
        
        if (!container) return;
        
        if (calls.length === 0) {
            container.innerHTML = '<p class="empty-state">No calls yet</p>';
            return;
        }

        container.innerHTML = '';
        
        calls.forEach(call => {
            const badge = call.is_emergency ? 'badge-emergency' : 
                         call.type === 'booking' ? 'badge-booking' : 'badge-general';
            const label = call.is_emergency ? '🚨 Emergency' : 
                         call.type === 'booking' ? '📅 Booking' : '💬 General';
            
            const time = new Date(call.created_at).toLocaleTimeString('en-GB', {
                hour: '2-digit',
                minute: '2-digit'
            });
            
            const duration = Math.floor(call.call_duration / 60);
            
            const item = document.createElement('div');
            item.className = 'caller-info';
            item.innerHTML = `
                <div style="display: flex; justify-content: space-between;">
                    <div>
                        <div class="caller-name">${call.caller_phone || 'Unknown'}</div>
                        <div class="call-time">${time} · ${duration} mins</div>
                    </div>
                    <span class="call-badge ${badge}">${label}</span>
                </div>
            `;
            container.appendChild(item);
        });
    } catch (error) {
        console.error('Error loading calls:', error);
    }
}

// === CALLS PAGE FUNCTIONS ===
let allCalls = [];

async function loadAllCalls() {
    const container = document.getElementById('callsList');
    if (!container) return;
    
    container.innerHTML = '<p class="loading">Loading calls...</p>';
    
    try {
        const response = await fetchAPI('/api/customer/calls?limit=50');
        allCalls = await response.json();
        renderCalls(allCalls);
    } catch (error) {
        console.error('Error loading calls:', error);
        container.innerHTML = '<p class="empty-state">Error loading calls</p>';
    }
}

function renderCalls(calls) {
    const container = document.getElementById('callsList');
    if (!container) return;
    
    if (calls.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-state-icon">📞</div>
                <p>No calls yet</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = '';
    
    calls.forEach(call => {
        const badge = call.is_emergency ? 'badge-emergency' : 
                     call.type === 'booking' ? 'badge-booking' : 'badge-routine';
        const label = call.is_emergency ? '🚨 Emergency' : 
                     call.type === 'booking' ? '📅 Booking' : '💬 General';
        
        const date = new Date(call.created_at).toLocaleString('en-GB');
        const duration = Math.floor(call.call_duration / 60);
        
        const item = document.createElement('div');
        item.className = 'caller-info';
        item.onclick = () => viewCall(call);
        item.innerHTML = `
            <div style="display: flex; justify-content: space-between;">
                <div>
                    <div class="caller-name">${call.caller_phone || 'Unknown'}</div>
                    <div class="call-meta">${date} · ${duration} mins</div>
                </div>
                <span class="call-badge ${badge}">${label}</span>
            </div>
        `;
        container.appendChild(item);
    });
}

function filterCalls() {
    const type = document.getElementById('filterType')?.value || 'all';
    const date = document.getElementById('filterDate')?.value || '';
    
    let filtered = allCalls;
    
    if (type !== 'all') {
        if (type === 'emergency') {
            filtered = filtered.filter(c => c.is_emergency);
        } else {
            filtered = filtered.filter(c => c.type === type);
        }
    }
    
    if (date) {
        filtered = filtered.filter(c => {
            const callDate = new Date(c.created_at).toISOString().split('T')[0];
            return callDate === date;
        });
    }
    
    renderCalls(filtered);
}

function viewCall(call) {
    const modal = document.getElementById('callModal');
    if (!modal) {
        alert(`Call from: ${call.caller_phone}\n\nSummary: ${call.summary || 'No summary'}`);
        return;
    }
    
    document.getElementById('modalPhone').textContent = call.caller_phone || 'Unknown';
    document.getElementById('modalTime').textContent = new Date(call.created_at).toLocaleString('en-GB');
    document.getElementById('modalDuration').textContent = `${Math.floor(call.call_duration / 60)} minutes`;
    document.getElementById('modalTranscript').textContent = call.transcript || 'No transcript available';
    
    modal.classList.add('active');
}

function closeCallModal() {
    const modal = document.getElementById('callModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

// === REFERRALS PAGE FUNCTIONS ===
async function loadReferralStats() {
    try {
        const response = await fetchAPI('/api/referrals/stats');
        const data = await response.json();
        
        if (document.getElementById('totalReferrals')) {
            document.getElementById('totalReferrals').textContent = data.total_referrals || 0;
        }
        if (document.getElementById('completedReferrals')) {
            document.getElementById('completedReferrals').textContent = data.completed || 0;
        }
        if (document.getElementById('activeReferrals')) {
            document.getElementById('activeReferrals').textContent = data.active || 0;
        }
        if (document.getElementById('totalEarned')) {
            document.getElementById('totalEarned').textContent = `£${data.total_earned || 0}`;
        }
    } catch (error) {
        console.error('Error loading referral stats:', error);
    }
}

async function loadShareData() {
    try {
        const response = await fetchAPI('/api/referrals/share-data');
        const data = await response.json();
        
        if (document.getElementById('referralCode')) {
            document.getElementById('referralCode').textContent = data.code || 'Loading...';
        }
        
        window.shareData = data;
    } catch (error) {
        console.error('Error loading share data:', error);
    }
}

async function loadReferralsList() {
    try {
        const response = await fetchAPI('/api/referrals/list');
        const referrals = await response.json();
        const container = document.getElementById('referralsList');
        
        if (!container) return;
        
        if (referrals.length === 0) {
            container.innerHTML = '<p class="empty-state">No referrals yet. Start sharing!</p>';
            return;
        }

        container.innerHTML = '';
        
        referrals.forEach(ref => {
            const statusClass = `status-${ref.status}`;
            const date = new Date(ref.created_at).toLocaleDateString('en-GB');
            
            const item = document.createElement('div');
            item.className = 'referral-item';
            item.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <strong>${ref.referee_business_name || ref.referee_email}</strong>
                        <div style="color: #6B7280; font-size: 14px; margin-top: 5px;">
                            Signed up ${date}
                            ${ref.referrer_credit_applied ? ' • £25 credited ✅' : ''}
                        </div>
                    </div>
                    <span class="referral-status ${statusClass}">
                        ${ref.status.toUpperCase()}
                    </span>
                </div>
            `;
            container.appendChild(item);
        });
    } catch (error) {
        console.error('Error loading referrals:', error);
    }
}

function copyCode() {
    const code = document.getElementById('referralCode')?.textContent;
    if (code) {
        navigator.clipboard.writeText(code);
        alert('Code copied!');
    }
}

function copyLink() {
    if (window.shareData?.link) {
        navigator.clipboard.writeText(window.shareData.link);
        alert('Link copied!');
    }
}

function shareVia(method) {
    if (!window.shareData) return;
    
    const data = window.shareData;
    
    if (method === 'whatsapp') {
        window.open(`https://wa.me/?text=${encodeURIComponent(data.whatsapp)}`);
    } else if (method === 'sms') {
        window.open(`sms:?body=${encodeURIComponent(data.sms)}`);
    } else if (method === 'email') {
        window.location.href = `mailto:?subject=${encodeURIComponent(data.email_subject)}&body=${encodeURIComponent(data.email_body)}`;
    }
}

// === ADMIN PAGE FUNCTIONS ===
async function loadPendingOnboardings() {
    const container = document.getElementById('pendingList');
    if (!container) return;
    
    container.innerHTML = '<p class="loading">Loading...</p>';
    
    try {
        const response = await fetch(`${API_URL}/api/admin/pending-onboardings`);
        const pending = await response.json();
        
        if (pending.length === 0) {
            container.innerHTML = '<p class="empty-state">No pending onboardings</p>';
            return;
        }
        
        container.innerHTML = '';
        
        pending.forEach(item => {
            const isUrgent = item.hours_waiting > 2;
            const card = document.createElement('div');
            card.className = `pending-card ${isUrgent ? 'urgent' : ''}`;
            card.innerHTML = `
                <div class="card-header">
                    <div>
                        <div class="business-name">${item.signup_name}</div>
                        <div class="business-type">${item.business_type}</div>
                    </div>
                    <span>${item.hours_waiting}h waiting</span>
                </div>
                <div class="card-info">
                    <div>📧 ${item.signup_email}</div>
                    <div>📞 ${item.signup_phone}</div>
                    <div>⏱️ ${Math.floor(item.call_duration / 60)} min call</div>
                </div>
                <div class="buttons">
                    <button class="btn-primary" onclick="viewTranscript('${item.id}')">View Transcript</button>
                    <button class="btn-success" onclick="createAssistant('${item.id}')">Create Assistant</button>
                </div>
            `;
            container.appendChild(card);
        });
    } catch (error) {
        console.error('Error loading onboardings:', error);
        container.innerHTML = '<p class="empty-state">Error loading onboardings</p>';
    }
}

async function viewTranscript(id) {
    try {
        const response = await fetch(`${API_URL}/api/admin/onboarding/${id}`);
        const data = await response.json();
        
        const modal = document.getElementById('transcriptModal');
        if (!modal) {
            alert(data.full_transcript);
            return;
        }
        
        document.getElementById('modalBusinessName').textContent = data.signup_name;
        document.getElementById('modalTranscriptText').textContent = data.full_transcript || 'No transcript';
        
        modal.classList.add('active');
    } catch (error) {
        console.error('Error viewing transcript:', error);
        alert('Error loading transcript');
    }
}

function closeModal() {
    const modals = document.querySelectorAll('.modal');
    modals.forEach(modal => modal.classList.remove('active'));
}

async function createAssistant(id) {
    if (!confirm('Create AI assistant for this business?')) return;
    
    try {
        const response = await fetch(`${API_URL}/api/admin/onboarding/${id}/create-assistant`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            alert(`✅ Assistant created!\n\nPhone: ${data.phone_number}\n\nCustomer has been notified via SMS.`);
            loadPendingOnboardings();
        } else {
            alert('Error creating assistant');
        }
    } catch (error) {
        console.error('Error creating assistant:', error);
        alert('Error creating assistant');
    }
}

// === UTILITY FUNCTIONS ===
function formatPhone(phone) {
    return phone || 'Unknown';
}

function formatDateTime(dateString) {
    if (!dateString) return '';
    return new Date(dateString).toLocaleString('en-GB');
}

function formatTime(dateString) {
    if (!dateString) return '';
    return new Date(dateString).toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatDuration(seconds) {
    if (!seconds) return '0 mins';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
}

function showLoading(elementId) {
    const el = document.getElementById(elementId);
    if (el) el.innerHTML = '<p class="loading">Loading...</p>';
}

function showError(elementId, message) {
    const el = document.getElementById(elementId);
    if (el) el.innerHTML = `<p class="empty-state">${message}</p>`;
}

function showEmpty(elementId, message) {
    const el = document.getElementById(elementId);
    if (el) el.innerHTML = `<p class="empty-state">${message}</p>`;
}
