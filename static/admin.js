// Global variables
let updatesList, faqsList, currentUser = null, currentItemId = null, db, auth;

// Initialize admin functionality
function initAdmin() {
    console.log('Initializing admin panel...');
    
    // Get Firebase instances
    if (!firebase.apps.length) {
        // Initialize Firebase if not already initialized
        const firebaseConfig = {
            apiKey: "AIzaSyDDjpV9y82muXh1LNu6vTf6u1AVhj2q9j4",
            authDomain: "ai-expense-tracker-32a6b.firebaseapp.com",
            projectId: "ai-expense-tracker-32a6b",
            storageBucket: "ai-expense-tracker-32a6b.firebasestorage.app",
            messagingSenderId: "585250811885",
            appId: "1:585250811885:web:986a5d7cca6ba2d71381e4",
            measurementId: "G-HPS894YBQC"
        };
        firebase.initializeApp(firebaseConfig);
    }
    
    // Get Firebase services
    db = firebase.firestore();
    auth = firebase.auth();
    
    // Set up auth state observer
auth.onAuthStateChanged(user => {
    if (user) {
        currentUser = user;
        checkAdminStatus(user.uid);
        initUI();
    } else {
        window.location.href = '/login';
    }
});
    
    // Initialize UI elements and event listeners
    function initUI() {
        console.log('Initializing UI...');
        
        // Get DOM elements
        updatesList = document.getElementById('updates-list');
        faqsList = document.getElementById('faqs-list');
        
        // Set up form submissions
        const updateForm = document.getElementById('update-form');
        const faqForm = document.getElementById('faq-form');
        const editUpdateForm = document.getElementById('edit-update-form');
        const editFaqForm = document.getElementById('edit-faq-form');
        const confirmDeleteBtn = document.getElementById('confirm-delete');
        
        if (updateForm) updateForm.addEventListener('submit', handleNewUpdate);
        if (faqForm) faqForm.addEventListener('submit', handleNewFaq);
        if (editUpdateForm) editUpdateForm.addEventListener('submit', handleUpdateUpdate);
        if (editFaqForm) editFaqForm.addEventListener('submit', handleUpdateFaq);
        if (confirmDeleteBtn) confirmDeleteBtn.addEventListener('click', handleDeleteItem);
        
        // Close modals when clicking outside
        window.onclick = function(event) {
            if (event.target.classList.contains('modal')) {
                event.target.style.display = 'none';
            }
        };
        
        // Close buttons for modals
        document.querySelectorAll('.close').forEach(btn => {
            btn.onclick = function() {
                const modal = this.closest('.modal');
                if (modal) modal.style.display = 'none';
            };
        });
    }
    
    // Check authentication state
    function checkAuthState() {
        auth.onAuthStateChanged(user => {
            if (user) {
                currentUser = user;
                checkAdminStatus(user.uid);
                initUI();
            } else {
                window.location.href = '/login';
            }
        });
    }
    
    // Wait for Firebase to be ready and initialize admin
    function initializeAdmin() {
        // Check if Firebase is already initialized
        if (typeof firebase !== 'undefined' && firebase.apps.length) {
            console.log('Firebase is ready, initializing admin...');
            initAdmin();
        } else {
            console.log('Waiting for Firebase to be ready...');
            // Wait for firebase-config.js to initialize Firebase
            const checkInterval = setInterval(() => {
                if (typeof firebase !== 'undefined' && firebase.apps.length) {
                    clearInterval(checkInterval);
                    console.log('Firebase is now ready, initializing admin...');
                    initAdmin();
                }
            }, 100);
        }
    }

    // Start the initialization
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initUI);
    } else {
        initUI();
    }
}

// Start the admin panel initialization
if (typeof firebase !== 'undefined' && firebase.apps.length) {
    // Firebase is already loaded
    initAdmin();
} else {
    // Wait for Firebase to be loaded
    document.addEventListener('firebase-ready', initAdmin);
}

// Admin functions
function checkAdminStatus(uid) {
    // Implement admin status check
    console.log('Checking admin status for user:', uid);
    // Add your admin status check logic here
}

// Placeholder functions - implement these as needed
function handleNewUpdate(e) { e.preventDefault(); console.log('New update'); }
function handleNewFaq(e) { e.preventDefault(); console.log('New FAQ'); }
function handleUpdateUpdate(e) { e.preventDefault(); console.log('Update update'); }
function handleUpdateFaq(e) { e.preventDefault(); console.log('Update FAQ'); }
function handleDeleteItem() { console.log('Delete item'); }

// Check if user is admin
async function checkAdminStatus(userId) {
    try {
        const userDoc = await db.collection('users').doc(userId).get();
        if (!userDoc.exists || !userDoc.data().isAdmin) {
            // Redirect to dashboard if not admin
            window.location.href = '/';
            return;
        }
        
        // User is admin, load data
        loadData();
    } catch (error) {
        console.error('Error checking admin status:', error);
        showError('Error loading admin panel');
    }
}

// Load initial data
function loadData() {
    // Load updates
    db.collection('updates_and_announcements')
        .orderBy('created_at', 'desc')
        .onSnapshot(snapshot => {
            updatesList.innerHTML = '';
            snapshot.docs.forEach(doc => {
                const data = doc.data();
                const updateElement = createUpdateElement(doc.id, data);
                updatesList.appendChild(updateElement);
            });
            
            if (snapshot.empty) {
                updatesList.innerHTML = '<div class="empty-state">No announcements yet.</div>';
            }
        }, error => {
            console.error('Error loading updates:', error);
            showError('Error loading announcements');
        });

    // Load FAQs
    db.collection('faq_content')
        .orderBy('order', 'asc')
        .onSnapshot(snapshot => {
            faqsList.innerHTML = '';
            snapshot.docs.forEach((doc, index) => {
                const data = doc.data();
                const faqElement = createFaqElement(doc.id, data, index);
                faqsList.appendChild(faqElement);
            });
            
            if (snapshot.empty) {
                faqsList.innerHTML = '<div class="empty-state">No FAQs yet.</div>';
            }
        }, error => {
            console.error('Error loading FAQs:', error);
            showError('Error loading FAQs');
        });
}

// Form Handlers
async function handleNewUpdate(e) {
    e.preventDefault();
    const title = document.getElementById('update-title').value;
    const content = document.getElementById('update-content').value;
    
    if (!title || !content) return;
    
    try {
        await db.collection('updates_and_announcements').add({
            title,
            content,
            created_at: firebase.firestore.FieldValue.serverTimestamp(),
            created_by: currentUser.uid,
            is_active: true
        });
        
        // Reset form
        e.target.reset();
        showSuccess('Announcement published successfully!');
    } catch (error) {
        console.error('Error adding update:', error);
        showError('Failed to publish announcement');
    }
}

async function handleNewFaq(e) {
    e.preventDefault();
    const question = document.getElementById('faq-question').value;
    const answer = document.getElementById('faq-answer').value;
    
    if (!question || !answer) return;
    
    try {
        // Get the highest order number
        const snapshot = await db.collection('faq_content')
            .orderBy('order', 'desc')
            .limit(1)
            .get();
            
        const lastOrder = snapshot.empty ? 0 : snapshot.docs[0].data().order;
        
        await db.collection('faq_content').add({
            question,
            answer,
            order: lastOrder + 1,
            created_at: firebase.firestore.FieldValue.serverTimestamp(),
            created_by: currentUser.uid,
            is_active: true
        });
        
        // Reset form
        e.target.reset();
        showSuccess('FAQ added successfully!');
    } catch (error) {
        console.error('Error adding FAQ:', error);
        showError('Failed to add FAQ');
    }
}

async function handleUpdateUpdate(e) {
    e.preventDefault();
    const id = document.getElementById('edit-update-id').value;
    const title = document.getElementById('edit-update-title').value;
    const content = document.getElementById('edit-update-content').value;
    
    if (!id || !title || !content) return;
    
    try {
        await db.collection('updates_and_announcements').doc(id).update({
            title,
            content,
            updated_at: firebase.firestore.FieldValue.serverTimestamp()
        });
        
        closeModal('update-modal');
        showSuccess('Announcement updated successfully!');
    } catch (error) {
        console.error('Error updating announcement:', error);
        showError('Failed to update announcement');
    }
}

async function handleUpdateFaq(e) {
    e.preventDefault();
    const id = document.getElementById('edit-faq-id').value;
    const question = document.getElementById('edit-faq-question').value;
    const answer = document.getElementById('edit-faq-answer').value;
    
    if (!id || !question || !answer) return;
    
    try {
        await db.collection('faq_content').doc(id).update({
            question,
            answer,
            updated_at: firebase.firestore.FieldValue.serverTimestamp()
        });
        
        closeModal('faq-modal');
        showSuccess('FAQ updated successfully!');
    } catch (error) {
        console.error('Error updating FAQ:', error);
        showError('Failed to update FAQ');
    }
}

async function handleDeleteItem() {
    if (!currentItemId) return;
    
    const modal = document.getElementById('confirm-modal');
    const collection = modal.getAttribute('data-collection');
    
    try {
        await db.collection(collection).doc(currentItemId).delete();
        closeModal('confirm-modal');
        showSuccess('Item deleted successfully!');
    } catch (error) {
        console.error('Error deleting item:', error);
        showError('Failed to delete item');
    }
    
    currentItemId = null;
}

// UI Helpers
function createUpdateElement(id, data) {
    const element = document.createElement('div');
    element.className = 'update-item';
    element.innerHTML = `
        <div class="update-header">
            <h3>${escapeHtml(data.title)}</h3>
            <div class="actions">
                <button class="btn-icon" onclick="editUpdate('${id}', '${escapeHtml(data.title)}', '${escapeHtml(data.content)}')">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn-icon danger" onclick="confirmDelete('${id}', 'updates_and_announcements')">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
        <div class="update-meta">
            <span>${formatDate(data.created_at?.toDate())}</span>
        </div>
        <div class="update-content">${escapeHtml(data.content).replace(/\n/g, '<br>')}</div>
    `;
    return element;
}

function createFaqElement(id, data, index) {
    const element = document.createElement('div');
    element.className = 'faq-item';
    element.setAttribute('data-id', id);
    element.setAttribute('draggable', 'true');
    element.innerHTML = `
        <div class="faq-header">
            <div class="faq-question">
                <span class="drag-handle">☰</span>
                <span>${escapeHtml(data.question)}</span>
            </div>
            <div class="actions">
                <button class="btn-icon" onclick="editFaq('${id}', '${escapeHtml(data.question)}', '${escapeHtml(data.answer)}')">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="btn-icon danger" onclick="confirmDelete('${id}', 'faq_content')">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
        <div class="faq-answer">${escapeHtml(data.answer).replace(/\n/g, '<br>')}</div>
    `;
    
    // Add drag and drop functionality
    element.addEventListener('dragstart', handleDragStart);
    element.addEventListener('dragover', handleDragOver);
    element.addEventListener('drop', handleDrop);
    element.addEventListener('dragend', handleDragEnd);
    
    return element;
}

// Drag and Drop for FAQ reordering
let draggedItem = null;

function handleDragStart(e) {
    draggedItem = this;
    this.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/html', this.innerHTML);
}

function handleDragOver(e) {
    if (e.preventDefault) {
        e.preventDefault();
    }
    e.dataTransfer.dropEffect = 'move';
    return false;
}

async function handleDrop(e) {
    e.stopPropagation();
    
    if (draggedItem !== this) {
        const faqId = this.getAttribute('data-id');
        const targetId = draggedItem.getAttribute('data-id');
        
        if (faqId && targetId) {
            try {
                // Get the current order of the target FAQ
                const targetDoc = await db.collection('faq_content').doc(faqId).get();
                const targetOrder = targetDoc.data().order;
                
                // Update the dragged item's order
                await db.collection('faq_content').doc(targetId).update({
                    order: targetOrder,
                    updated_at: firebase.firestore.FieldValue.serverTimestamp()
                });
                
                // The real-time listener will update the UI
            } catch (error) {
                console.error('Error reordering FAQs:', error);
                showError('Failed to reorder FAQs');
            }
        }
    }
    
    return false;
}

function handleDragEnd() {
    this.classList.remove('dragging');
    draggedItem = null;
}

// Modal Helpers
function openUpdateModal(id = '', title = '', content = '') {
    const modal = document.getElementById('update-modal');
    document.getElementById('edit-update-id').value = id;
    document.getElementById('edit-update-title').value = title;
    document.getElementById('edit-update-content').value = content;
    modal.style.display = 'block';
}

function openFaqModal(id = '', question = '', answer = '') {
    const modal = document.getElementById('faq-modal');
    document.getElementById('edit-faq-id').value = id;
    document.getElementById('edit-faq-question').value = question;
    document.getElementById('edit-faq-answer').value = answer;
    modal.style.display = 'block';
}

function confirmDelete(id, collection) {
    currentItemId = id;
    const modal = document.getElementById('confirm-modal');
    modal.setAttribute('data-collection', collection);
    modal.style.display = 'block';
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
    }
}

// Utility Functions
function formatDate(date) {
    if (!date) return 'Unknown date';
    return new Date(date).toLocaleDateString('en-US', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function escapeHtml(unsafe) {
    if (!unsafe) return '';
    return unsafe
        .toString()
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function showError(message) {
    // Implement your error notification UI here
    console.error(message);
    alert(`Error: ${message}`);
}

function showSuccess(message) {
    // Implement your success notification UI here
    console.log(message);
    alert(`Success: ${message}`);
}

// Global functions for inline event handlers
function switchTab(tabName, event) {
    if (event) event.preventDefault();
    
    console.log('Switching to tab:', tabName);
    
    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(tab => {
        tab.classList.remove('active');
    });
    
    // Deactivate all tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    
    // Show selected tab content
    const tabContent = document.getElementById(`${tabName}-tab`);
    if (tabContent) {
        tabContent.classList.add('active');
    } else {
        console.error('Tab content not found:', `${tabName}-tab`);
    }
    
    // Activate clicked button if event is from a button
    if (event && event.currentTarget) {
        event.currentTarget.classList.add('active');
    } else {
        // Or find the button and activate it
        const tabButtons = document.querySelectorAll('.tab-btn');
        for (let btn of tabButtons) {
            if (btn.getAttribute('onclick') && btn.getAttribute('onclick').includes(tabName)) {
                btn.classList.add('active');
                break;
            }
        }
    }
    
    // Load data for the selected tab
    if (tabName === 'updates') {
        console.log('Loading updates...');
        if (updatesList && (updatesList.children.length === 0 || updatesList.querySelector('.loading'))) {
            loadData();
        }
    } else if (tabName === 'faqs') {
        console.log('Loading FAQs...');
        if (faqsList && (faqsList.children.length === 0 || faqsList.querySelector('.loading'))) {
            loadData();
        }
    }
}

window.editUpdate = function(id, title, content) {
    openUpdateModal(id, title, content);
};

window.editFaq = function(id, question, answer) {
    openFaqModal(id, question, answer);
};

window.confirmDelete = function(id, collection) {
    confirmDelete(id, collection);
};

window.closeModal = function(modalId) {
    closeModal(modalId);
};
