async function uploadReceipt() {
  const fileInput = document.getElementById("receiptInput");
  const resultDiv = document.getElementById("result");
  const chartCanvas = document.getElementById("expenseChart");

  if (!fileInput || !fileInput.files || !fileInput.files.length) {
    resultDiv.innerHTML = "<p>Please upload an image first.</p>";
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);

  resultDiv.innerHTML = "<p>Analyzing receipt using AI... please wait ⏳</p>";

  try {
    const response = await fetch("/upload", {
      method: "POST",
      body: formData
    });

    if (!response.ok) {
      const text = await response.text();
      resultDiv.innerHTML = `<p style='color:red;'>Server error: ${response.status} <br>${text}</p>`;
      console.error("Response text:", text);
      return;
    }

    const data = await response.json();
    console.log("📦 Response from server:", data);

    if (data.error) {
      resultDiv.innerHTML = `<p style='color:red;'>${data.error}</p>`;
      return;
    }

    // ✅ Parse grouped data (from MongoDB aggregation)
    if (Array.isArray(data.data)) {
      const summaryHTML = data.data
        .map(
          (item) =>
            `<li><b>${item._id}</b>: ₹${item.total.toFixed(2)}</li>`
        )
        .join("");

      resultDiv.innerHTML = `
        <h4>${data.message}</h4>
        <ul>${summaryHTML}</ul>
      `;
    } else {
      resultDiv.innerHTML = `
        <p><b>${data.message}</b></p>
        <p>Category: ${data.data.category}</p>
        <p>Amount: ₹${data.data.amount}</p>
      `;
    }

    // ✅ Show assessment (wanted/unwanted + tips)
    try {
      const assessBox = document.getElementById("assessment");
      const tipsList = document.getElementById("assessmentTips");
      const note = document.getElementById("assessmentNote");
      const ctxPrompts = document.getElementById("ctxPrompts");
      if (assessBox && data.assessment) {
        const a = data.assessment;
        assessBox.innerHTML = `<b>${a.label}</b> — ${a.reason} (Category: ${a.category}, Amount: ₹${Number(a.amount || 0).toFixed(2)})`;
        tipsList.innerHTML = (a.tips || [])
          .map((t) => `<li>✅ ${t}</li>`) 
          .join("");
        note.textContent = "This is a rule-based guide. Refine by chatting below.";

        // Auto-post a simple AI advice message into chat
        const bullets = (a.tips || []).slice(0, 3).map((t) => `- ${t}`).join("\n");
        const aiMsg = [
          `Based on this receipt: ${a.category} · ₹${Number(a.amount || 0).toFixed(2)} — ${a.label}.`,
          a.reason ? `Why: ${a.reason}` : "",
          bullets ? `Try:\n${bullets}` : "",
          "Ask me to set caps or suggest a weekly checklist if you want."
        ].filter(Boolean).join("\n\n");
        appendChat("AI", aiMsg);

        // Contextual quick prompts based on category
        if (ctxPrompts) {
          const cat = (a.category || '').trim();
          const btns = [
            { t: `Give me tips for ${cat}`, q: `tips for ${cat}` },
            { t: `Is this necessary?`, q: `is this necessary` },
            { t: `How much did I spend on ${cat}?`, q: `How much did I spend on ${cat}?` }
          ];
          ctxPrompts.innerHTML = btns
            .map(b => `<button onclick="sendQuick('${b.q.replace(/'/g, "\\'")}')">${b.t}</button>`) 
            .join(" ");
        }
      }
    } catch (e) {
      console.warn("Assessment render failed", e);
    }

    // ✅ Draw chart with destroy safety
    const ctx = chartCanvas.getContext("2d");
    if (window.expenseChart && typeof window.expenseChart.destroy === "function") {
      window.expenseChart.destroy();
    }

    const labels = Array.isArray(data.data) ? data.data.map((d) => d._id) : [];
    const values = Array.isArray(data.data) ? data.data.map((d) => d.total) : [];

    window.expenseChart = new Chart(ctx, {
      type: "pie",
      data: {
        labels: labels,
        datasets: [
          {
            label: "Expense Breakdown",
            data: values,
            backgroundColor: [
              "#36A2EB",
              "#FF6384",
              "#FFCE56",
              "#4BC0C0",
              "#9966FF"
            ]
          }
        ]
      },
      options: {
        responsive: true,
        plugins: { legend: { position: "bottom" } }
      }
    });
  } catch (error) {
    console.error("❌ Error:", error);
    resultDiv.innerHTML =
      "<p style='color:red;'>Something went wrong while analyzing.</p>";
  }
}

// ================== Dashboard Summary ==================
async function loadSummary() {
  try {
    const res = await fetch('/api/summary');
    if (!res.ok) return;
    const data = await res.json();
    const fmt = (n) => `₹${Number(n||0).toFixed(0)}`;
    const net = document.getElementById('kpiNet');
    const spend = document.getElementById('kpiSpend');
    const period = document.getElementById('kpiPeriod');
    const bar = document.getElementById('budgetBar');
    const note = document.getElementById('budgetNote');
    if (period && data.period) period.textContent = `${data.period.start} → ${data.period.end}`;
    if (spend) spend.textContent = fmt(data.total_spend);
    if (net) net.textContent = data.net_balance != null ? fmt(data.net_balance) : '—';
    if (bar && data.budget) {
      const pct = Math.min(Math.max(Number(data.budget.percent_used||0), 0), 100);
      bar.style.width = `${isFinite(pct) ? pct : 0}%`;
      note && (note.textContent = data.budget.amount ? `${fmt(data.total_spend)} of ${fmt(data.budget.amount)} used` : 'No budget set');
    }

    // Mini top categories chart
    const ctx = document.getElementById('miniTopCats');
    if (ctx) {
      const labels = (data.top_categories||[]).map(x=>x.category);
      const vals = (data.top_categories||[]).map(x=>x.total);
      if (window.miniChart && typeof window.miniChart.destroy==='function') { try{window.miniChart.destroy();}catch(_){} }
      window.miniChart = new Chart(ctx.getContext('2d'), {
        type: 'doughnut',
        data: { labels, datasets: [{ data: vals, backgroundColor: ['#1f6fe5','#4BC0C0','#FFCE56'] }] },
        options: { plugins: { legend: { position: 'bottom' } } }
      });
    }

    // Recent list
    const ul = document.getElementById('recentList');
    if (ul) {
      ul.innerHTML = (data.recent||[]).map(r=>`<li><span>${r.date}</span><span>${r.category}</span><span class="amt">₹${Number(r.amount||0).toFixed(0)}</span></li>`).join('');
    }
  } catch (_) {}
}

// ================== Analysis Deep Dive ==================
function setQuickRange(kind) {
  const s = document.getElementById('rangeStart');
  const e = document.getElementById('rangeEnd');
  const now = new Date();
  let start, end;
  if (kind === 'year') {
    start = new Date(now.getFullYear(), 0, 1);
    end = new Date(now.getFullYear(), 11, 31);
  } else if (kind === 'quarter') {
    const q = Math.floor(now.getMonth()/3);
    start = new Date(now.getFullYear(), q*3, 1);
    end = new Date(now.getFullYear(), q*3+3, 0);
  } else { // month
    start = new Date(now.getFullYear(), now.getMonth(), 1);
    end = new Date(now.getFullYear(), now.getMonth()+1, 0);
  }
  const fmt = (d) => d.toISOString().slice(0,10);
  if (s) s.value = fmt(start);
  if (e) e.value = fmt(end);
}

async function refreshAnalysis() {
  const s = document.getElementById('rangeStart')?.value;
  const e = document.getElementById('rangeEnd')?.value;
  if (!s || !e) return;
  const url = `/api/analysis?start=${encodeURIComponent(s)}&end=${encodeURIComponent(e)}`;
  try {
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();

    // Trend line
    const tEl = document.getElementById('trendChart');
    if (tEl) {
      const labels = (data.trend||[]).map(x=>x.date);
      const vals = (data.trend||[]).map(x=>x.total);
      if (window.trendChart && typeof window.trendChart.destroy==='function') { try{window.trendChart.destroy();}catch(_){} }
      window.trendChart = new Chart(tEl.getContext('2d'), {
        type: 'line',
        data: { labels, datasets: [{ label: 'Total', data: vals, borderColor: '#1f6fe5', backgroundColor: 'rgba(31,111,229,0.15)', tension: .25, fill: true }] },
        options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
      });
    }

    // Category breakdown
    const cEl = document.getElementById('categoryChart');
    if (cEl) {
      const labels = (data.by_category||[]).map(x=>x.category);
      const vals = (data.by_category||[]).map(x=>x.total);
      if (window.categoryChart && typeof window.categoryChart.destroy==='function') { try{window.categoryChart.destroy();}catch(_){} }
      window.categoryChart = new Chart(cEl.getContext('2d'), {
        type: 'bar',
        data: { labels, datasets: [{ label: 'By Category', data: vals, backgroundColor: '#4BC0C0' }] },
        options: { responsive: true, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
      });
    }

    // Table
    const tbody = document.querySelector('#analysisTable tbody');
    if (tbody) {
      tbody.innerHTML = (data.table||[]).map(r=>`<tr><td>${r.date}</td><td>${r.merchant||''}</td><td>${r.category}</td><td style="text-align:right">₹${Number(r.amount||0).toFixed(0)}</td></tr>`).join('');
    }

    // Insights
    const ul = document.getElementById('insightsList');
    if (ul) {
      const list = Array.isArray(data.insights) && data.insights.length ? data.insights : ['No notable insights for this period.'];
      ul.innerHTML = list.map(t=>`<li>✅ ${t}</li>`).join('');
    }
  } catch (_) {}
}

async function deleteLastExpense() {
  const resultDiv = document.getElementById('result');
  const chartCanvas = document.getElementById('expenseChart');
  try {
    const res = await fetch('/delete_last', { method: 'POST' });
    if (!res.ok) {
      const t = await res.text();
      appendChat('AI', `Failed to delete last (${res.status}): ${t}`);
      return;
    }
    const data = await res.json();
    const msg = data.message || 'Last expense deleted.';
    const d = data.deleted;
    const detail = d ? `Category: ${d.category || '-'} · Amount: ₹${Number(d.amount || 0).toFixed(2)}` : '';
    if (resultDiv) {
      resultDiv.innerHTML = `<p><b>${msg}</b>${detail ? `<br>${detail}` : ''}</p>`;
    }

    // Redraw chart from grouped data
    const labels = Array.isArray(data.data) ? data.data.map((x) => x._id) : [];
    const values = Array.isArray(data.data) ? data.data.map((x) => x.total) : [];
    if (chartCanvas && chartCanvas.getContext) {
      if (window.expenseChart && typeof window.expenseChart.destroy === 'function') {
        try { window.expenseChart.destroy(); } catch (_) {}
      }
      const ctx = chartCanvas.getContext('2d');
      if (labels.length) {
        window.expenseChart = new Chart(ctx, {
          type: 'pie',
          data: {
            labels,
            datasets: [{
              label: 'Expense Breakdown',
              data: values,
              backgroundColor: ['#36A2EB','#FF6384','#FFCE56','#4BC0C0','#9966FF']
            }]
          },
          options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
        });
      } else {
        ctx.clearRect(0, 0, chartCanvas.width, chartCanvas.height);
      }
    }

    appendChat('AI', msg);
  } catch (e) {
    appendChat('AI', 'Unable to delete last expense right now.');
  }
}

// ------------- Simple chat to /advice -------------
function appendChat(role, text) {
  const box = document.getElementById("chatMessages");
  if (!box) return;
  const wrap = document.createElement("div");
  const isUser = role.toLowerCase() === "you" || role.toLowerCase() === "user";
  wrap.className = `chat-msg ${isUser ? "user" : "ai"}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  wrap.appendChild(bubble);
  box.appendChild(wrap);
  box.scrollTop = box.scrollHeight;
}

async function sendAdvice() {
  const input = document.getElementById("chatInput");
  const budgetEl = document.getElementById("budgetInput");
  const msg = (input?.value || "").trim();
  if (!msg) return;
  appendChat("You", msg);
  input.value = "";

  try {
    const res = await fetch("/advice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg })
    });
    if (!res.ok) {
      const t = await res.text();
      appendChat("AI", `Server error ${res.status}: ${t}`);
      return;
    }
    const data = await res.json();
    appendChat("AI", data.reply || "(no advice)");
  } catch (e) {
    appendChat("AI", "Failed to get advice. Please try again later.");
  }
}

// Enter-to-send for chat input
function resetDashboard() {
  const resultDiv = document.getElementById("result");
  const assessBox = document.getElementById("assessment");
  const tipsList = document.getElementById("assessmentTips");
  const note = document.getElementById("assessmentNote");
  const chatBox = document.getElementById("chatMessages");
  const fileInput = document.getElementById("receiptInput");
  const chartCanvas = document.getElementById("expenseChart");

  if (resultDiv) resultDiv.innerHTML = "";
  if (assessBox) assessBox.innerHTML = "";
  if (tipsList) tipsList.innerHTML = "";
  if (note) note.textContent = "";
  if (chatBox) chatBox.innerHTML = "";
  if (fileInput) fileInput.value = "";

  if (chartCanvas && chartCanvas.getContext) {
    if (window.expenseChart && typeof window.expenseChart.destroy === "function") {
      try { window.expenseChart.destroy(); } catch (_) {}
    }
    const ctx = chartCanvas.getContext("2d");
    if (ctx && ctx.clearRect) {
      ctx.clearRect(0, 0, chartCanvas.width, chartCanvas.height);
    }
  }
}

async function clearUserData() {
  try {
    const res = await fetch('/clear_data', { method: 'POST' });
    if (!res.ok) {
      const t = await res.text();
      appendChat('AI', `Failed to clear data (${res.status}): ${t}`);
      return;
    }
    const data = await res.json();
    resetDashboard();
    appendChat('AI', data.message || 'Your data has been cleared.');
  } catch (e) {
    appendChat('AI', 'Unable to clear data right now.');
  }
}

// ================== Announcements & FAQs ==================
async function loadAnnouncements() {
  const container = document.getElementById('announcements-list');
  if (!container) return;

  try {
    container.innerHTML = '<div class="loading">Loading announcements...</div>';
    
    const response = await fetch('/api/announcements', {
      method: 'GET',
      credentials: 'include',  // Include cookies for session
      headers: {
        'Accept': 'application/json',
        'Cache-Control': 'no-cache'
      }
    });
    
    if (response.status === 401) {
      // Not authenticated, redirect to login
      window.location.href = '/login';
      return;
    }
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (!Array.isArray(data)) {
      throw new Error('Invalid response format');
    }
    
    if (data.length === 0) {
      container.innerHTML = '<div class="no-data">No announcements available.</div>';
      return;
    }

    container.innerHTML = `
      <div class="announcement-items">
        ${data.map(ann => `
          <div class="announcement-item">
            <div class="announcement-date">${ann.created_at ? new Date(ann.created_at).toLocaleDateString() : ''}</div>
            <h4 class="announcement-title">${ann.title || 'Announcement'}</h4>
            <div class="announcement-content">${ann.content || ''}</div>
          </div>
        `).join('')}
      </div>
    `;
  } catch (error) {
    console.error('Error loading announcements:', error);
    container.innerHTML = `
      <div class="error">
        <p>Failed to load announcements.</p>
        <p><small>${error.message || 'Please try again later.'}</small></p>
      </div>`;
  }
}

async function loadFAQs() {
  const container = document.getElementById('faq-list');
  if (!container) return;

  try {
    container.innerHTML = '<div class="loading">Loading FAQs...</div>';
    
    const response = await fetch('/api/faqs', {
      method: 'GET',
      credentials: 'include',  // Include cookies for session
      headers: {
        'Accept': 'application/json',
        'Cache-Control': 'no-cache'
      }
    });
    
    if (response.status === 401) {
      // Not authenticated, redirect to login
      window.location.href = '/login';
      return;
    }
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const data = await response.json();
    
    if (!Array.isArray(data)) {
      throw new Error('Invalid response format');
    }
    
    if (data.length === 0) {
      container.innerHTML = '<div class="no-data">No FAQs available yet.</div>';
      return;
    }

    container.innerHTML = `
      <div class="faq-accordion">
        ${data.map((faq, index) => `
          <div class="faq-item">
            <button class="faq-question" aria-expanded="false" aria-controls="faq-${index}">
              <span class="faq-question-text">${faq.question || 'Question'}</span>
              <span class="faq-icon">+</span>
            </button>
            <div class="faq-answer" id="faq-${index}">
              <div class="faq-answer-content">${faq.answer || 'No answer provided.'}</div>
            </div>
          </div>
        `).join('')}
      </div>
    `;

    // Add click handlers for FAQ accordion
    document.querySelectorAll('.faq-question').forEach(button => {
      button.addEventListener('click', () => {
        const expanded = button.getAttribute('aria-expanded') === 'true';
        button.setAttribute('aria-expanded', !expanded);
        button.querySelector('.faq-icon').textContent = expanded ? '+' : '−';
      });
    });
  } catch (error) {
    console.error('Error loading FAQs:', error);
    container.innerHTML = `
      <div class="error">
        <p>Failed to load FAQs.</p>
        <p><small>${error.message || 'Please try again later.'}</small></p>
      </div>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // Reset UI so a refresh starts clean
  resetDashboard();

  const input = document.getElementById("chatInput");
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendAdvice();
      }
    });
  }

  // Load chat history
  (async () => {
    try {
      const res = await fetch('/advice/history');
      if (!res.ok) return;
      const data = await res.json();
      const msgs = Array.isArray(data.messages) ? data.messages : [];
      msgs.forEach(m => appendChat(m.role === 'user' ? 'You' : 'AI', m.text || ''));
    } catch (_) {}
  })();

  // If KPI nodes exist, load dashboard summary
  if (document.getElementById('kpiSpend')) {
    loadSummary();
  }

  // If analysis filters exist, init analysis defaults and load
  if (document.getElementById('rangeStart')) {
    setQuickRange('month');
    refreshAnalysis();
  }

  // Load announcements and FAQs if on the dashboard
  if (document.getElementById('announcements-list')) {
    loadAnnouncements();
  }
  
  if (document.getElementById('faq-list')) {
    loadFAQs();
  }
});

// Quick prompt helper
function sendQuick(text) {
  const input = document.getElementById('chatInput');
  if (input) input.value = text;
  sendAdvice();
}

// Download analysis PDF
function downloadAnalysisPdf() {
  const a = document.createElement('a');
  a.href = '/export/analysis.pdf';
  a.download = 'analysis.pdf';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

async function setBudgetFromInput() {
  const el = document.getElementById('budgetInput');
  const val = (el?.value || '').trim();
  if (!val) {
    appendChat('AI', 'Please enter a budget amount first.');
    return;
  }
  try {
    const res = await fetch('/settings/budget', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ budget: val })
    });
    const data = await res.json();
    if (!res.ok) {
      appendChat('AI', data.error || 'Failed to update budget.');
      return;
    }
    appendChat('AI', `Monthly budget set to ₹${Number(data.budget || 0).toFixed(0)}.`);
  } catch (e) {
    appendChat('AI', 'Unable to update budget right now.');
  }
}

// ================== Camera / Modal Capture Flow ==================
let __cameraStream = null;
let __torchOn = false;

function openExpenseModal(initialTab) {
  const modal = document.getElementById('cameraModal');
  if (!modal) return;
  modal.classList.add('open');
  switchExpenseTab(initialTab || 'upload');
}

function closeExpenseModal() {
  const modal = document.getElementById('cameraModal');
  if (!modal) return;
  modal.classList.remove('open');
  stopCamera();
}

function switchExpenseTab(tab) {
  const upBtn = document.getElementById('tabUploadBtn');
  const capBtn = document.getElementById('tabCaptureBtn');
  const manBtn = document.getElementById('tabManualBtn');
  const up = document.getElementById('tabUpload');
  const cap = document.getElementById('tabCapture');
  const man = document.getElementById('tabManual');
  if (!up || !cap) return;

  up.classList.remove('is-active');
  cap.classList.remove('is-active');
  man && man.classList.remove('is-active');
  upBtn && upBtn.classList.remove('active');
  capBtn && capBtn.classList.remove('active');
  manBtn && manBtn.classList.remove('active');

  if (tab === 'capture') {
    cap.classList.add('is-active');
    capBtn && capBtn.classList.add('active');
    startCamera();
  } else if (tab === 'manual') {
    man && man.classList.add('is-active');
    manBtn && manBtn.classList.add('active');
    stopCamera();
  } else {
    up.classList.add('is-active');
    upBtn && upBtn.classList.add('active');
    stopCamera();
  }
}

async function startCamera() {
  try {
    const video = document.getElementById('webcam');
    if (!video) return;
    if (__cameraStream) return; // already started
    const constraints = {
      video: {
        facingMode: { ideal: 'environment' },
        width: { ideal: 1280 },
        height: { ideal: 720 }
      },
      audio: false
    };
    const stream = await navigator.mediaDevices.getUserMedia(constraints);
    __cameraStream = stream;
    video.srcObject = stream;
    __torchOn = false;
    document.getElementById('cameraNote')?.classList.remove('error');
  } catch (e) {
    const note = document.getElementById('cameraNote');
    if (note) {
      note.textContent = 'Unable to access camera. Please check permissions and device settings.';
      note.classList.add('error');
    }
  }
}

function stopCamera() {
  try {
    if (__cameraStream) {
      __cameraStream.getTracks().forEach(t => t.stop());
    }
  } catch (_) {}
  __cameraStream = null;
}

async function toggleTorch() {
  try {
    if (!__cameraStream) return;
    const track = __cameraStream.getVideoTracks()[0];
    const cap = track.getCapabilities ? track.getCapabilities() : {};
    if (!cap.torch) {
      appendChat('AI', 'Torch/flash is not supported on this device.');
      return;
    }
    __torchOn = !__torchOn;
    await track.applyConstraints({ advanced: [{ torch: __torchOn }] });
    const btn = document.getElementById('torchBtn');
    if (btn) btn.textContent = __torchOn ? 'Flash On' : 'Flash';
  } catch (_) {
    appendChat('AI', 'Unable to toggle torch on this device.');
  }
}

async function snapReceipt() {
  try {
    const video = document.getElementById('webcam');
    const canvas = document.getElementById('captureCanvas');
    const resultDiv = document.getElementById('result');
    if (!video || !canvas) return;
    const w = video.videoWidth || 1280;
    const h = video.videoHeight || 720;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(video, 0, 0, w, h);
    const blob = await new Promise(r => canvas.toBlob(r, 'image/jpeg', 0.95));
    if (!blob) {
      appendChat('AI', 'Failed to capture image. Please try again.');
      return;
    }

    // Show processing message
    if (resultDiv) resultDiv.innerHTML = '<p>Processing Receipt with AI... ⏳</p>';

    const formData = new FormData();
    formData.append('file', blob, 'capture.jpg');
    await processFormDataWithOcr(formData);
    closeExpenseModal();
  } catch (e) {
    appendChat('AI', 'Could not snap receipt.');
  }
}

async function uploadFromModalFile() {
  const fileEl = document.getElementById('modalFileInput');
  const resultDiv = document.getElementById('result');
  if (!fileEl || !fileEl.files.length) {
    appendChat('AI', 'Please choose a file to upload.');
    return;
  }
  if (resultDiv) resultDiv.innerHTML = '<p>Processing Receipt with AI... ⏳</p>';
  const fd = new FormData();
  fd.append('file', fileEl.files[0]);
  await processFormDataWithOcr(fd);
  closeExpenseModal();
}

// Reuse OCR pipeline rendering using a helper
async function processFormDataWithOcr(formData) {
  const resultDiv = document.getElementById('result');
  const chartCanvas = document.getElementById('expenseChart');
  try {
    const response = await fetch('/upload', { method: 'POST', body: formData });
    if (!response.ok) {
      const text = await response.text();
      resultDiv && (resultDiv.innerHTML = `<p style='color:red;'>Server error: ${response.status}<br>${text}</p>`);
      return;
    }
    const data = await response.json();
    if (data.error) {
      resultDiv && (resultDiv.innerHTML = `<p style='color:red;'>${data.error}</p>`);
      return;
    }
    // Render summary
    if (Array.isArray(data.data)) {
      const summaryHTML = data.data.map(item => `<li><b>${item._id}</b>: ₹${item.total.toFixed(2)}</li>`).join('');
      resultDiv && (resultDiv.innerHTML = `<h4>${data.message}</h4><ul>${summaryHTML}</ul>`);
    }
    // Render assessment
    try {
      const assessBox = document.getElementById('assessment');
      const tipsList = document.getElementById('assessmentTips');
      const note = document.getElementById('assessmentNote');
      const ctxPrompts = document.getElementById('ctxPrompts');
      if (assessBox && data.assessment) {
        const a = data.assessment;
        assessBox.innerHTML = `<b>${a.label}</b> — ${a.reason} (Category: ${a.category}, Amount: ₹${Number(a.amount || 0).toFixed(2)})`;
        tipsList && (tipsList.innerHTML = (a.tips || []).map(t => `<li>✅ ${t}</li>`).join(''));
        note && (note.textContent = 'This is a rule-based guide. Refine by chatting below.');
        if (ctxPrompts) {
          const cat = (a.category || '').trim();
          const btns = [
            { t: `Give me tips for ${cat}`, q: `tips for ${cat}` },
            { t: `Is this necessary?`, q: `is this necessary` },
            { t: `How much did I spend on ${cat}?`, q: `How much did I spend on ${cat}?` }
          ];
          ctxPrompts.innerHTML = btns.map(b => `<button onclick="sendQuick('${b.q.replace(/'/g, "\\'")}')">${b.t}</button>`).join(' ');
        }
      }
    } catch (_) {}

    // Draw chart
    if (chartCanvas && chartCanvas.getContext) {
      const ctx = chartCanvas.getContext('2d');
      if (window.expenseChart && typeof window.expenseChart.destroy === 'function') {
        try { window.expenseChart.destroy(); } catch (_) {}
      }
      const labels = Array.isArray(data.data) ? data.data.map(d => d._id) : [];
      const values = Array.isArray(data.data) ? data.data.map(d => d.total) : [];
      if (labels.length) {
        window.expenseChart = new Chart(ctx, {
          type: 'pie',
          data: { labels, datasets: [{ label: 'Expense Breakdown', data: values, backgroundColor: ['#36A2EB','#FF6384','#FFCE56','#4BC0C0','#9966FF'] }] },
          options: { responsive: true, plugins: { legend: { position: 'bottom' } } }
        });
      }
    }
  } catch (e) {
    resultDiv && (resultDiv.innerHTML = "<p style='color:red;'>Something went wrong while analyzing.</p>");
  }
}

async function refreshChart() {
    try {
        const response = await fetch('/expenses/summary');
        if (!response.ok) throw new Error('Failed to load expense data');
        
        const data = await response.json();
        
        // Update chart if it exists
        if (window.expenseChart && data && data.categories && data.totals) {
            window.expenseChart.data.labels = data.categories;
            window.expenseChart.data.datasets[0].data = data.totals;
            window.expenseChart.update();
        }
    } catch (error) {
        console.error('Error refreshing chart:', error);
    }
}

async function submitManualExpense() {
    const merchant = document.getElementById('manMerchant')?.value || '';
    const category = document.getElementById('manCategory')?.value || 'Misc';
    const amountStr = document.getElementById('manAmount')?.value || '';
    const note = document.getElementById('manNote')?.value || '';
    const dateRaw = document.getElementById('manDate')?.value || '';
    const resultDiv = document.getElementById('result');
    const btn = document.getElementById('manualSaveBtn');
    const status = document.getElementById('manualSaveStatus');
    const amount = parseFloat(amountStr);

    // Validate input
    if (!isFinite(amount) || amount <= 0) {
        status && (status.textContent = 'Please enter a valid amount');
        return;
    }

    // Update UI
    const originalBtnText = btn?.textContent;
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Saving...';
    }
    if (status) {
        status.textContent = 'Saving expense...';
        status.style.color = '';
    }

    try {
        // Format date for backend
        let dateToSend = dateRaw;
        if (dateRaw) {
            const date = new Date(dateRaw);
            if (!isNaN(date.getTime())) {
                dateToSend = date.toISOString().slice(0, 16).replace('T', ' ');
            }
        }

        // Send request to server
        const response = await fetch('/expenses/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            },
            body: JSON.stringify({
                merchant,
                category,
                amount,
                note,
                date: dateToSend
            })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to save expense');
        }

        // Show success message
        if (resultDiv) {
            resultDiv.innerHTML = `
                <div class="alert alert-success" style="padding: 10px; margin: 10px 0; border-radius: 4px; background-color: #d4edda; color: #155724; border: 1px solid #c3e6cb;">
                    <strong>Success!</strong> Expense of ₹${amount.toFixed(2)} for ${category} has been added.
                </div>
            `;
        }

        // Reset form
        const form = document.querySelector('#expenseModal form');
        if (form) form.reset();

        // Refresh data
        await Promise.all([
            loadSummary(),
            refreshAnalysis(),
            refreshChart()
        ]);

        // Close modal after a short delay
        setTimeout(() => {
            const modal = bootstrap.Modal.getInstance(document.getElementById('expenseModal'));
            if (modal) modal.hide();
        }, 1500);

    } catch (error) {
        console.error('Error adding expense:', error);
        if (resultDiv) {
            resultDiv.innerHTML = `
                <div class="alert alert-danger" style="padding: 10px; margin: 10px 0; border-radius: 4px; background-color: #f8d7da; color: #721c24; border: 1px solid #f5c6cb;">
                    <strong>Error:</strong> ${error.message || 'Failed to add expense. Please try again.'}
                </div>
            `;
        }
        status && (status.textContent = 'Failed to save');
        status && (status.style.color = 'red');
    } finally {
        // Reset button state
        if (btn) {
            btn.disabled = false;
            btn.textContent = originalBtnText || 'Save Expense';
        }
    }
}
