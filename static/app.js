/* Chaos Collection */

// =========================================================================
// Submit idea
// =========================================================================

async function submitIdea() {
    const input = document.getElementById('idea-input');
    const text = input.value.trim();
    if (!text) return;

    const hint = document.getElementById('input-hint');
    input.value = '';
    input.style.height = 'auto';
    hint.textContent = '...';

    try {
        const res = await fetch('/api/ideas', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ raw_text: text }),
        });
        if (!res.ok) { hint.textContent = '保存失败'; return; }
        const idea = await res.json();
        hint.textContent = '已记下';
        loadDailySummaries();
        waitAndRefresh(idea.id);
    } catch { hint.textContent = '网络错误'; }
    setTimeout(() => { if (hint.textContent === '已记下') hint.textContent = ''; }, 3000);
}

async function waitAndRefresh(ideaId) {
    for (let i = 0; i < 20; i++) {
        await new Promise(r => setTimeout(r, 1500));
        try {
            const r = await fetch(`/api/ideas/${ideaId}`);
            const idea = await r.json();
            if ((idea.ai_tags && idea.ai_tags !== '[]') || idea.ai_summary) {
                loadDailySummaries();
                loadTagCloud();
                return;
            }
        } catch {}
    }
}

// =========================================================================
// Tag cloud
// =========================================================================

let tagRange = 'week';

async function switchTagRange(range, btn) {
    tagRange = range;
    document.querySelectorAll('.tag-toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    loadTagCloud();
}

async function loadTagCloud() {
    const canvas = document.getElementById('tag-cloud');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    const W = canvas.width = canvas.offsetWidth * (window.devicePixelRatio || 1);
    const H = canvas.height = canvas.offsetHeight * (window.devicePixelRatio || 1);
    ctx.scale(window.devicePixelRatio || 1, window.devicePixelRatio || 1);
    const cw = canvas.offsetWidth, ch = canvas.offsetHeight;
    const cx = cw / 2, cy = ch / 2;
    ctx.clearRect(0, 0, cw, ch);

    try {
        let days;
        if (tagRange === 'week') {
            const now = new Date();
            days = now.getDay() || 7; // Monday=1, Sunday=7. Days since Monday.
        } else {
            days = 9999;
        }
        const r = await fetch(`/api/tags?days=${days}`);
        const tags = await r.json();
        // Only show tag cloud when there are enough tags (3+ distinct, 5+ total)
        const totalOccurrences = tags.reduce((s, t) => s + t.count, 0);
        if (tags.length < 3 || totalOccurrences < 5) {
            document.querySelector('.tag-toggle').classList.add('hidden');
            canvas.classList.add('hidden');
            return;
        }
        document.querySelector('.tag-toggle').classList.remove('hidden');
        canvas.classList.remove('hidden');

        const maxCount = tags[0].count;
        const minCount = tags[tags.length - 1].count;
        const placed = [];

        // Font size range
        const sizeMin = 14, sizeMax = 40;
        function fontSize(count) {
            if (maxCount === minCount) return (sizeMin + sizeMax) / 2;
            return sizeMin + (sizeMax - sizeMin) * (count - minCount) / (maxCount - minCount);
        }

        // Spiral placement
        function tryPlace(w, h) {
            for (let step = 0; step < 600; step++) {
                const angle = step * 0.15;
                const r = step * 1.2;
                const x = cx + r * Math.cos(angle) - w / 2;
                const y = cy + r * Math.sin(angle) - h / 2;
                if (x < 4 || y < 4 || x + w > cw - 4 || y + h > ch - 4) continue;
                let overlap = false;
                for (const p of placed) {
                    if (x < p.x + p.w && x + w > p.x && y < p.y + p.h && y + h > p.y) {
                        overlap = true; break;
                    }
                }
                if (!overlap) return { x, y };
            }
            return null;
        }

        // Draw each tag
        for (const tag of tags) {
            const size = fontSize(tag.count);
            ctx.font = `${size}px -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif`;
            const metrics = ctx.measureText(tag.name);
            const tw = metrics.width + 12;
            const th = size + 8;
            const pos = tryPlace(tw, th);
            if (!pos) continue;
            placed.push({ x: pos.x, y: pos.y, w: tw, h: th });

            // Color based on frequency
            const t = (tag.count - minCount) / (maxCount - minCount || 1);
            const r_col = Math.round(180 + 75 * t);
            const g_col = Math.round(180 + 75 * t);
            const b_col = Math.round(180 + 75 * t);
            ctx.fillStyle = `rgb(${r_col},${g_col},${b_col})`;
            ctx.fillText(tag.name, pos.x + 6, pos.y + size);
        }
    } catch {}
}

// =========================================================================
// Homepage — today's ideas
// =========================================================================

async function loadDailySummaries() {
    try {
        const res = await fetch('/api/daily?days=7');
        const data = await res.json();
        const container = document.getElementById('daily-summaries');
        let html = '';

        const today = data.today || [];
        if (today.length > 0) {
            html += '<div class="day-group"><div class="day-header">Today</div><div class="day-items">' +
                today.map(idea =>
                    `<div class="idea-accordion" id="ia-${idea.id}">
                        <div class="day-item" onclick="toggleIdea('${idea.id}')">
                            <span class="item-time">${fmtTime(idea.created_at)}</span>
                            <span class="item-summary">${esc(idea.ai_summary || idea.raw_text.slice(0, 60))}</span>
                        </div>
                        <div class="idea-expand hidden" id="ie-${idea.id}"></div>
                    </div>`
                ).join('') +
                '</div></div>';
        }

        // This week's past daily summaries
        const weekDailies = data.week_dailies || [];
        if (weekDailies.length > 0) {
            html += '<div class="day-group"><div class="day-header">This week</div>' +
                weekDailies.map(s => `
                    <div class="day-accordion" id="acc-${s.date}">
                        <div class="day-row" onclick="toggleDay('${s.date}')">
                            <span class="day-row-date">${fmtDayHeader(s.date)}</span>
                            <span class="day-row-text" id="text-${s.date}">${esc(s.summary)}</span>
                        </div>
                        <div class="day-ideas hidden" id="ideas-${s.date}"></div>
                    </div>
                `).join('') +
                '</div>';
        }

        if (!html) html = '<div class="day-empty">还没有记录。</div>';
        container.innerHTML = html;
    } catch {}
}

// =========================================================================
// Idea accordion
// =========================================================================

async function toggleIdea(id) {
    const expand = document.getElementById('ie-' + id);
    const row = document.getElementById('ia-' + id);
    if (!expand) return;

    if (!expand.classList.contains('hidden')) {
        expand.classList.add('hidden');
        if (row) row.querySelector('.item-summary, .det-text')?.classList.remove('expanded');
        return;
    }

    // Un-truncate the summary line
    const summary = row?.querySelector('.item-summary, .det-text');
    if (summary) summary.classList.add('expanded');

    if (!expand.dataset.loaded) {
        expand.innerHTML = '<div style="color:var(--text-muted);padding:8px 0">...</div>';
        try {
            const r = await fetch(`/api/ideas/${id}`);
            const idea = await r.json();
            const now = new Date();
            const todayStr = `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`;
            const isToday = idea.created_at.startsWith(todayStr);
            expand.innerHTML =
                `<div class="ie-wrap">
                    <div class="ie-body">${esc(idea.raw_text)}</div>
                    ${isToday ? `<span class="ie-delete" onclick="event.stopPropagation(); deleteIdea('${id}')">&times;</span>` : ''}
                </div>`;
            expand.dataset.loaded = '1';
        } catch { expand.innerHTML = '<div style="color:var(--text-muted)">加载失败</div>'; }
    }
    expand.classList.remove('hidden');
}

async function deleteIdea(id) {
    if (!confirm('删除这条想法？')) return;
    await fetch(`/api/ideas/${id}`, { method: 'DELETE' });
    document.getElementById('ia-' + id)?.remove();
    loadDailySummaries();
    loadTagCloud();
}

// =========================================================================
// Archive page — weekly summaries
// =========================================================================

const WEEKDAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

async function loadWeeklySection() {
    try {
        const r = await fetch('/api/weekly?days=90');
        const weeks = await r.json();
        const container = document.getElementById('weekly-section');
        if (!weeks.length) { container.innerHTML = '<div class="day-empty">暂无归档</div>'; return; }

        container.innerHTML = weeks.map((w, wi) => {
            const label = `Week ${isoWeek(w.week_start)}, ${fmtWeekRange(w.week_start, w.week_end)}`;
            const isLatest = wi === 0;
            const dailies = w.dailies || [];

            return `
                <div class="week-group">
                    <div class="week-header" onclick="toggleWeek(this)">
                        <span>${label}</span>
                        <span class="week-count">${w.idea_count} ideas</span>
                    </div>
                    <div class="week-body ${isLatest ? '' : 'hidden'}">
                        <div class="week-summary" onclick="toggleWeek(this.parentElement.previousElementSibling)">${esc(w.summary)}</div>
                        ${dailies.map(s => `
                            <div class="day-accordion" id="acc-${s.date}">
                                <div class="day-row" onclick="toggleDay('${s.date}')">
                                    <span class="day-row-date">${fmtDayHeader(s.date)}</span>
                                    <span class="day-row-text" id="text-${s.date}">${esc(s.summary)}</span>
                                </div>
                                <div class="day-ideas hidden" id="ideas-${s.date}"></div>
                            </div>
                        `).join('')}
                    </div>
                </div>`;
        }).join('');
    } catch {}
}

function fmtWeekRange(start, end) {
    const toMD = (s) => {
        const d = new Date(s); const m = MONTHS[d.getMonth()];
        return `${m} ${d.getDate()}`;
    };
    return `${toMD(start)} - ${toMD(end)}`;
}

function isoWeek(dateStr) {
    const d = new Date(dateStr);
    const jan4 = new Date(d.getFullYear(), 0, 4);
    const mon = new Date(jan4);
    mon.setDate(jan4.getDate() - (jan4.getDay() || 7) + 1);
    const diff = (d - mon) / 86400000;
    return Math.floor(diff / 7) + 1;
}

function toggleWeek(el) { el.nextElementSibling.classList.toggle('hidden'); }

async function toggleDay(date) {
    const ideasDiv = document.getElementById('ideas-' + date);
    const textEl = document.getElementById('text-' + date);
    const isOpen = !ideasDiv.classList.contains('hidden');
    if (isOpen) { textEl.classList.remove('expanded'); ideasDiv.classList.add('hidden'); return; }
    textEl.classList.add('expanded');
    ideasDiv.classList.remove('hidden');
    if (!ideasDiv.dataset.loaded) {
        ideasDiv.innerHTML = '<div style="color:var(--text-muted);padding:4px 0 4px 122px">...</div>';
        try {
            const r = await fetch('/api/ideas?page_size=200');
            const data = await r.json();
            const ideas = data.ideas.filter(i => i.created_at.startsWith(date));
            ideasDiv.innerHTML = ideas.map(idea =>
                `<div class="idea-accordion" id="ia-${idea.id}">
                    <div class="det-row" onclick="toggleIdea('${idea.id}')">
                        <span class="det-time">${fmtTime(idea.created_at)}</span>
                        <span class="det-text">${esc(idea.ai_summary || idea.raw_text.slice(0, 80))}</span>
                    </div>
                    <div class="idea-expand hidden" id="ie-${idea.id}"></div>
                </div>`
            ).join('') || '<div class="day-empty">无条目</div>';
            ideasDiv.dataset.loaded = '1';
        } catch { ideasDiv.innerHTML = '<div class="day-empty">加载失败</div>'; }
    }
}

// =========================================================================
// Settings
// =========================================================================

async function saveAIConfig(e) {
    e.preventDefault();
    const body = { base_url: document.getElementById('ai-base-url').value.trim(), api_key: document.getElementById('ai-api-key').value.trim(), model: document.getElementById('ai-model').value.trim() };
    try {
        const res = await fetch('/api/settings/ai', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        showStatus('ai-config-status', res.ok ? 'success' : 'error', res.ok ? '已保存' : '保存失败');
    } catch { showStatus('ai-config-status', 'error', '网络错误'); }
}

function showStatus(id, type, msg) {
    const el = document.getElementById(id); if (!el) return;
    el.className = `status-msg ${type}`; el.textContent = msg; el.classList.remove('hidden');
    setTimeout(() => el.classList.add('hidden'), 3000);
}

// =========================================================================
// Helpers
// =========================================================================

function esc(s) { if (!s) return ''; const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function fmtTime(d) { return d ? d.slice(11, 16) : ''; }

function fmtDate(d) {
    if (!d) return '';
    const date = new Date(d);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const thatDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    const diff = Math.round((today - thatDay) / 86400000);
    if (diff === 0) return 'Today';
    if (diff === 1) return 'Yesterday';
    const wd = WEEKDAYS[date.getDay()];
    const md = `${String(date.getMonth()+1).padStart(2,'0')}/${String(date.getDate()).padStart(2,'0')}`;
    if (date.getFullYear() === now.getFullYear()) return `${wd} ${md}`;
    return `${wd} ${md}/${date.getFullYear()}`;
}

function fmtDayHeader(dateStr) { return fmtDate(dateStr + 'T00:00:00'); }

// =========================================================================
// Init
// =========================================================================

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('idea-input')) {
        loadTagCloud();
        loadDailySummaries();
        const input = document.getElementById('idea-input');
        input.addEventListener('input', autoResize);
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                submitIdea();
            }
        });
    }
    if (document.getElementById('weekly-section')) { loadWeeklySection(); }
});

function autoResize(e) { e.target.style.height = 'auto'; e.target.style.height = e.target.scrollHeight + 'px'; }
