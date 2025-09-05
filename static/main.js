// ----- Tabs Functionality -----
function showTab(tabIndex) {
    const tabs = document.querySelectorAll('.tab-content');
    const btns = document.querySelectorAll('.tab-btn');

    tabs.forEach((tab, i) => {
        if (i === tabIndex) {
            tab.classList.add('active');
            tab.style.opacity = 0;
            tab.style.transition = 'opacity 0.4s ease-in-out';
            requestAnimationFrame(() => {
                tab.style.opacity = 1;
            });
        } else {
            tab.classList.remove('active');
            tab.style.opacity = 0;
        }
    });

    btns.forEach((btn, i) => {
        btn.classList.toggle('active', i === tabIndex);
    });
}

// Activate first tab on page load
window.addEventListener('DOMContentLoaded', () => {
    showTab(0);
    // Chart removed from home page; do not initialize here
    applyStatusAlarmColors();
    // Opt-in: only add double top scrollbar for explicitly marked tables
    enableTopTableScrollbars(['.js-double-scroll']);
    enableAutoFilterForms();
    // New: animate KPI cards
    animateKpiCards();
    renderStatusDoughnut();
    renderSchedulePie();
    renderWarningLongestBar();
    renderTrend12w();
    renderWarnCorrectedStack();
    const basisSel = document.getElementById('basisToggle');
    if (basisSel) {
        basisSel.addEventListener('change', () => {
            renderWarnCorrectedStack();
        });
    }
    // removed: KPI sparklines
    renderAlarmDonut();
    initKpiScopeToggle();
    populateDateIndicator();
    initSidebar();
});

// Sidebar collapse and active-link handling for modern Testing nav
function initSidebar(){
    try{
        const sidebar = document.getElementById('cbmSidebar');
        const shell = document.querySelector('.app-shell');
        const btn = document.getElementById('sbCollapse');
        if(!sidebar || !btn || !shell) return;
        const apply = (collapsed)=>{
            sidebar.classList.toggle('is-collapsed', !!collapsed);
            shell.classList.toggle('sb-collapsed', !!collapsed);
        };
        // Restore state
        const stored = localStorage.getItem('cbm:sb-collapsed');
        apply(stored === '1');
        btn.addEventListener('click', ()=>{
            const isCollapsed = sidebar.classList.toggle('is-collapsed');
            shell.classList.toggle('sb-collapsed', isCollapsed);
            try{ localStorage.setItem('cbm:sb-collapsed', isCollapsed ? '1' : '0'); }catch(_){ }
        });
        // Active link highlight (match pathname) - choose the best (longest) matching href
        const items = Array.from(sidebar.querySelectorAll('.nav-item'));
        const rawPath = window.location.pathname || '';
        // normalize path (remove trailing slash except for root)
        const normalize = (p) => {
            if (!p) return '/';
            try { p = String(p); } catch (_) { return '/'; }
            if (p.length > 1 && p.endsWith('/')) p = p.replace(/\/+$|\/+$/g, '');
            return p || '/';
        };
        const curPath = normalize(rawPath);
        let bestMatch = null;
        let bestLen = -1;
        items.forEach(a => {
            try{
                const hrefRaw = a.getAttribute('href') || '';
                if (!hrefRaw) return;
                // Resolve relative hrefs to a pathname using the current origin
                let hrefPath = '/';
                try {
                    hrefPath = new URL(hrefRaw, window.location.origin).pathname || '/';
                } catch (e) {
                    hrefPath = hrefRaw.split('?')[0].split('#')[0] || '/';
                }
                hrefPath = normalize(hrefPath);
                // match if current path equals hrefPath or is a child (startsWith hrefPath + '/')
                if (curPath === hrefPath || curPath.startsWith(hrefPath + '/')) {
                    // prefer the longest matching href (most specific)
                    if (hrefPath.length > bestLen) {
                        bestLen = hrefPath.length;
                        bestMatch = a;
                    }
                }
            }catch(_){ }
        });
        // Clear previous and apply to the best match only
        items.forEach(a => a.classList.remove('is-active'));
        if (bestMatch) bestMatch.classList.add('is-active');
        // Tooltips on collapsed mode are provided via title attr (native)
    }catch(_){ }
}
function pad(n){ return String(n).padStart(2,'0'); }

function isoWeekAndYear(d){
    // returns [year, week]
    const target = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    // Thursday in current week decides the year
    target.setUTCDate(target.getUTCDate() + 3 - (target.getUTCDay() + 6) % 7);
    const year = target.getUTCFullYear();
    const firstThursday = new Date(Date.UTC(year,0,4));
    const week = 1 + Math.round(((target - firstThursday) / 86400000 - 3 + (firstThursday.getUTCDay() + 6) % 7) / 7);
    return [year, week];
}

function populateDateIndicator(){
    const elDate = document.getElementById('date-indicator-date');
    const elDay = document.getElementById('date-indicator-day');
    const elWeek = document.getElementById('date-indicator-week');
    const wkPicker = document.getElementById('kpi-week-picker');
    // If server provided a selected PM date, prefer it for the KPI indicator
    const pmFromServer = (document.getElementById('kpi-date-indicator') || {}).dataset ? (document.getElementById('kpi-date-indicator').dataset.pmDate || '') : '';
    let now = new Date();
    if (pmFromServer) {
        try {
            // pmFromServer is ISO-like; use only date part
            now = new Date(pmFromServer);
            if (isNaN(now.getTime())) now = new Date();
        } catch (_) { now = new Date(); }
    }
    const [y,w] = isoWeekAndYear(now);
    // compact single-line: Weekday, Mon D • Wnn YYYY
    const weekday = now.toLocaleDateString(undefined, { weekday: 'short' });
    const monthDay = now.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
    if (elDate) elDate.textContent = `${weekday}, ${monthDay} • W${pad(w)} ${y}`;
    // hide the separate day label (CSS will take care of visuals); still keep nodes for ARIA
    if (elDay) elDay.textContent = weekday;
    if (elWeek) elWeek.textContent = `W${pad(w)} ${y}`;
    // Keep week picker in sync if present
    if (wkPicker && !wkPicker.value) {
        wkPicker.value = `${y}-W${pad(w)}`;
    }
    // Also update kpi-cards data-week/year if not set
    const kcards = document.getElementById('kpi-cards');
    if (kcards) {
        if (!kcards.getAttribute('data-week')) kcards.setAttribute('data-week', String(w));
        if (!kcards.getAttribute('data-year')) kcards.setAttribute('data-year', String(y));
    }
    // When week picker changes, only update the compact week label
    // Keep the displayed date/day fixed to today's values so filters won't overwrite it
    if (wkPicker) {
        wkPicker.addEventListener('change', (e) => {
            const v = (e.target.value || '').trim();
            if (!v) return;
            const parts = v.split('-W');
            if (parts.length === 2) {
                const yy = parts[0];
                const ww = parseInt(parts[1],10);
                // Update only the week indicator; do NOT touch elDate/elDay which should remain as today
                if (elWeek) elWeek.textContent = `W${pad(ww)} ${yy}`;
            }
        });
    }
}

function wkName(weekNum){ return 'Week'; }

function applyStatusAlarmColors() {
    // Color selects in technician lists and detail
    document.querySelectorAll('select[name="status"]').forEach(sel => {
        colorizeStatusSelect(sel);
        sel.addEventListener('change', () => colorizeStatusSelect(sel));
    });
    document.querySelectorAll('select[name="alarm_level"]').forEach(sel => {
        colorizeAlarmSelect(sel);
        sel.addEventListener('change', () => colorizeAlarmSelect(sel));
    });
    // Color plain text cells where status/alarm are rendered as text
    document.querySelectorAll('[data-status-text]').forEach(el => {
        setStatusClass(el, (el.getAttribute('data-status-text') || '').trim());
    });
    document.querySelectorAll('[data-alarm-text]').forEach(el => {
        setAlarmClass(el, (el.getAttribute('data-alarm-text') || '').trim());
    });
}

function colorizeStatusSelect(sel) {
    const v = (sel.value || '').toLowerCase();
    sel.classList.remove('status-ongoing','status-completed','status-analysis','status-revisit','status-waived','status-sending','status-todo');
    if (v === 'completed' || v === 'done') sel.classList.add('status-completed');
    else if (v === 'ongoing' || v === 'todo') sel.classList.add('status-ongoing');
    else if (v === 'ongoing analysis') sel.classList.add('status-analysis');
    else if (v === 'for revisit') sel.classList.add('status-revisit');
    else if (v === 'waived') sel.classList.add('status-waived');
    else if (v === 'sending report') sel.classList.add('status-sending');
    else sel.classList.add('status-todo');
}

function colorizeAlarmSelect(sel) {
    const v = (sel.value || '').toLowerCase();
    sel.classList.remove('alarm-text-normal','alarm-text-warning','alarm-text-critical');
    if (v === 'critical') sel.classList.add('alarm-text-critical');
    else if (v === 'warning') sel.classList.add('alarm-text-warning');
    else sel.classList.add('alarm-text-normal');
}

function setStatusClass(el, text) {
    const v = (text || '').toLowerCase();
    el.classList.remove('status-ongoing','status-completed','status-analysis','status-revisit','status-waived','status-sending','status-todo');
    if (v === 'completed' || v === 'done') el.classList.add('status-completed');
    else if (v === 'ongoing' || v === 'todo') el.classList.add('status-ongoing');
    else if (v === 'ongoing analysis') el.classList.add('status-analysis');
    else if (v === 'for revisit') el.classList.add('status-revisit');
    else if (v === 'waived') el.classList.add('status-waived');
    else if (v === 'sending report') el.classList.add('status-sending');
    else el.classList.add('status-todo');
}

function setAlarmClass(el, text) {
    const v = (text || '').toLowerCase();
    el.classList.remove('alarm-text-normal','alarm-text-warning','alarm-text-critical');
    if (v === 'critical') el.classList.add('alarm-text-critical');
    else if (v === 'warning') el.classList.add('alarm-text-warning');
    else el.classList.add('alarm-text-normal');
}

// Add a synchronized top horizontal scrollbar for wide tables
function enableTopTableScrollbars(selectors) {
    if (!selectors) {
        selectors = ['.js-double-scroll'];
    } else if (typeof selectors === 'string') {
        selectors = [selectors];
    }
    selectors.forEach(sel => {
        document.querySelectorAll(sel).forEach(tbl => {
            // Skip if already wrapped
            if (tbl.closest('.double-scroll-wrapper')) return;
            // Measure before DOM changes
            const parent = tbl.parentNode;
            const parentWidth = parent ? parent.clientWidth : 0;
            const tableWidth = tbl.scrollWidth || tbl.offsetWidth;
            if (parentWidth && tableWidth <= parentWidth) {
                return; // No horizontal overflow; no need to add a top bar
            }

            const contentWrapper = document.createElement('div');
            contentWrapper.className = 'double-scroll-content';
            parent.insertBefore(contentWrapper, tbl);
            contentWrapper.appendChild(tbl);

            const topWrapper = document.createElement('div');
            topWrapper.className = 'double-scroll-top';
            const dummy = document.createElement('div');
            topWrapper.appendChild(dummy);

            const outer = document.createElement('div');
            outer.className = 'double-scroll-wrapper';
            contentWrapper.parentNode.insertBefore(outer, contentWrapper);
            outer.appendChild(topWrapper);
            outer.appendChild(contentWrapper);

            function syncWidths() {
                const width = Math.max(contentWrapper.scrollWidth, tbl.scrollWidth, tbl.offsetWidth);
                dummy.style.width = width + 'px';
            }
            // Sync scroll positions
            topWrapper.addEventListener('scroll', () => {
                contentWrapper.scrollLeft = topWrapper.scrollLeft;
            });
            contentWrapper.addEventListener('scroll', () => {
                topWrapper.scrollLeft = contentWrapper.scrollLeft;
            });
            // Initial and responsive sync
            syncWidths();
            new ResizeObserver(syncWidths).observe(contentWrapper);
            window.addEventListener('resize', syncWidths);
        });
    });
}

// Chart.js rendering removed

// Auto-submit filter forms when any control changes
function enableAutoFilterForms() {
    document.querySelectorAll('form.auto-filter-form').forEach(form => {
        const submit = () => form.requestSubmit ? form.requestSubmit() : form.submit();
        form.querySelectorAll('input, select').forEach(ctrl => {
            // For text inputs, submit on Enter key to avoid submitting on every keystroke
            if (ctrl.tagName === 'INPUT' && (!ctrl.type || ctrl.type === 'text' || ctrl.type === 'number')) {
                ctrl.addEventListener('change', submit);
                ctrl.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });
            } else {
                ctrl.addEventListener('change', submit);
            }
        });
    });
}

// ----- Status Doughnut (Chart.js) -----
function renderStatusDoughnut() {
    const el = document.getElementById('statusDoughnut');
    if (!el || typeof Chart === 'undefined') return;
    const data = {
        labels: ['Completed', 'Ongoing', 'Ongoing Analysis', 'For Revisit'],
        datasets: [{
            data: [
                parseInt(el.getAttribute('data-completed') || '0', 10),
                parseInt(el.getAttribute('data-ongoing') || '0', 10),
                parseInt(el.getAttribute('data-analysis') || '0', 10),
                parseInt(el.getAttribute('data-revisit') || '0', 10),
            ],
            backgroundColor: ['#16a34a', '#0b5ed7', '#7c3aed', '#ea580c'],
            borderWidth: 0,
        }]
    };
    new Chart(el.getContext('2d'), {
        type: 'doughnut',
        data,
        options: {
            responsive: false,
            plugins: { legend: { display: false } },
            cutout: '60%'
        }
    });
}

// ----- Schedule Split Pie (Chart.js) -----
function renderSchedulePie() {
    const el = document.getElementById('schedulePie');
    if (!el || typeof Chart === 'undefined') return;
    // Count from board table cells
    const counts = { planned: 0, unplanned: 0, validation: 0 };
    document.querySelectorAll('table.planner-table tbody tr td:nth-child(5) .schedule-planned').forEach(() => counts.planned++);
    document.querySelectorAll('table.planner-table tbody tr td:nth-child(5) .schedule-unplanned').forEach(() => counts.unplanned++);
    document.querySelectorAll('table.planner-table tbody tr td:nth-child(5) .schedule-validation').forEach(() => counts.validation++);

    new Chart(el.getContext('2d'), {
        type: 'pie',
        data: {
            labels: ['Planned', 'Unplanned', 'Validation'],
            datasets: [{
                data: [counts.planned, counts.unplanned, counts.validation],
                backgroundColor: ['#16a34a', '#dc2626', '#2563eb'],
                borderWidth: 0,
            }]
        },
        options: {
            responsive: false,
            plugins: { legend: { display: false } },
        }
    });
}

// ----- Warning Longest Horizontal Bar -----
function renderWarningLongestBar() {
    const el = document.getElementById('warningLongestBar');
    const dataEl = document.getElementById('warningLongestData');
    const wrap = document.getElementById('warningLongestWrap');
    if (!dataEl) return; // nothing to render
    let rows = [];
    try { rows = JSON.parse(dataEl.textContent || '[]') || []; } catch (_) { rows = []; }
    if (!Array.isArray(rows) || rows.length === 0) return;
    // If Chart.js is missing or canvas not available, render a simple table
    if (typeof Chart === 'undefined' || !el || !el.getContext) {
        if (!wrap) return;
        const tbl = document.createElement('table');
        tbl.className = 'planner-table';
        tbl.style.width = '100%';
        tbl.innerHTML = `
            <thead><tr><th>Equipment</th><th>Dept.</th><th>Since</th><th>Days</th><th>Open</th></tr></thead>
            <tbody>
                ${rows.map(r => `<tr><td>${r.equipment||''}</td><td>${r.department||''}</td><td>${r.first_warning_date||''}</td><td>${r.days_open||0}</td><td>${r.open_count||0}</td></tr>`).join('')}
            </tbody>
        `;
        wrap.innerHTML = '';
        wrap.appendChild(tbl);
        return;
    }
    const labels = rows.map(r => `${r.equipment || ''} (${r.department || ''})`);
    const days = rows.map(r => parseInt(r.days_open || 0, 10));
    const openCounts = rows.map(r => parseInt(r.open_count || 0, 10));
    const ctx = el.getContext('2d');
    new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Days Open',
                    data: days,
                    backgroundColor: '#f59e0b',
                    borderWidth: 0,
                },
                {
                    label: 'Open Count',
                    data: openCounts,
                    backgroundColor: '#0ea5e9',
                    borderWidth: 0,
                },
            ]
        },
        options: {
            indexAxis: 'y',
            responsive: false,
            scales: {
                x: { beginAtZero: true, grid: { display: true } },
                y: { grid: { display: false } },
            },
            plugins: {
                legend: { display: true, position: 'bottom' },
                tooltip: { enabled: true },
            },
        }
    });
}

// ----- 12-Week Trend (Chart.js) -----
function renderTrend12w() {
    const el = document.getElementById('trend12w');
    if (!el || typeof Chart === 'undefined') return;
    fetch('/api/dashboard/weekly_metrics?weeks=12')
        .then(r => r.json())
        .then(d => {
            const ctx = el.getContext('2d');
            // Destroy previous instance if re-rendering
            if (el._chart) {
                try { el._chart.destroy(); } catch (_) {}
            }
            el._chart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: d.labels,
                    datasets: [
                        { label: 'Planned', data: d.planned || [], borderColor: '#2563eb', backgroundColor: 'rgba(37,99,235,0.12)', borderWidth: 2, pointRadius: 2, tension: 0.3, fill: false },
                        { label: 'Completed', data: d.completed || [], borderColor: '#16a34a', backgroundColor: 'rgba(22,163,74,0.15)', borderWidth: 3, pointRadius: 2, tension: 0.3, fill: true },
                        { label: 'Waived', data: d.waived || [], borderColor: '#64748b', backgroundColor: 'rgba(100,116,139,0.15)', borderWidth: 2, pointRadius: 2, tension: 0.3, fill: false }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: {
                        legend: {
                            display: true,
                            position: 'bottom',
                            labels: {
                                usePointStyle: true,
                                generateLabels: function(chart) {
                                    const original = Chart.defaults.plugins.legend.labels.generateLabels(chart);
                                    return original.map(label => {
                                        try {
                                            const ds = chart.data.datasets[label.datasetIndex];
                                            if (ds && ds.type === 'line') {
                                                label.pointStyle = 'line';
                                                label.fillStyle = 'transparent';
                                                label.strokeStyle = ds.borderColor || ds.backgroundColor || label.strokeStyle;
                                                label.lineWidth = ds.borderWidth || 2;
                                            }
                                        } catch (e) { }
                                        return label;
                                    });
                                }
                            }
                        }
                    },
                    scales: { x: { grid: { display: false } }, y: { beginAtZero: true } }
                }
            });
        })
        .catch(() => {});
}

// ----- Alarm Split Donut (Chart.js) -----
function renderAlarmDonut() {
    const el = document.getElementById('alarmDonut');
    if (!el || typeof Chart === 'undefined') return;
    const critEl = document.getElementById('alarmCritCnt');
    const warnEl = document.getElementById('alarmWarnCnt');
    // Try to get selected week/year from URL or data available in sidebar
    const url = new URL(window.location.href);
    const w = url.searchParams.get('week');
    const y = url.searchParams.get('year');
    const qp = (w && y) ? `?week=${encodeURIComponent(w)}&year=${encodeURIComponent(y)}` : '';
    fetch('/api/dashboard/alarm_split' + qp)
        .then(r => r.json())
        .then(d => {
            if (critEl) critEl.textContent = d.critical || 0;
            if (warnEl) warnEl.textContent = d.warning || 0;
            const ctx = el.getContext('2d');
            // Normalize critical series: API may return as d.critical or inside d.alarms.critical
            const criticalSeries = (d.critical && Array.isArray(d.critical) && d.critical) || ((d.alarms && Array.isArray(d.alarms.critical) && d.alarms.critical) || []);
            new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Critical', 'Warning'],
                    datasets: [{ data: [d.critical || 0, d.warning || 0], backgroundColor: ['#dc2626', '#f59e0b'], borderWidth: 0 }]
                },
                options: { responsive: false, plugins: { legend: { display: false } }, cutout: '60%' }
            });
        })
        .catch(() => {});
}

// ----- Alarms (Critical+Warning) stacked vs Corrected — 12 Weeks (Chart.js) -----
function renderWarnCorrectedStack() {
    const el = document.getElementById('warnCorrectedStack');
    if (!el || typeof Chart === 'undefined') return;
    const basisSel = document.getElementById('basisToggle');
    const basis = (basisSel && basisSel.value) || 'planner';
    fetch('/api/dashboard/weekly_metrics?weeks=12&basis=' + encodeURIComponent(basis))
        .then(r => r.json())
        .then(d => {
            const ctx = el.getContext('2d');
            if (el._chart) { try { el._chart.destroy(); } catch (_) {} }
            const labels = Array.isArray(d.labels) ? d.labels : [];
            const len = labels.length;
            // Alarms stacked: total alarms per week by type (use alarms.* series)
            const alarmsCritical = (d.alarms && Array.isArray(d.alarms.critical)) ? d.alarms.critical : new Array(len).fill(0);
            const alarmsWarning = (d.alarms && Array.isArray(d.alarms.warning)) ? d.alarms.warning : new Array(len).fill(0);
            // Corrected from alarms: sum of warnings_closed and criticals_closed (fallback to corrected warnings only)
            const warningsClosed = Array.isArray(d.warnings_closed) ? d.warnings_closed : (Array.isArray(d.corrected) ? d.corrected : new Array(len).fill(0));
            const criticalsClosed = Array.isArray(d.criticals_closed) ? d.criticals_closed : new Array(len).fill(0);
            const correctedFromAlarms = labels.map((_, i) => (Number(warningsClosed[i] || 0) + Number(criticalsClosed[i] || 0)));
            // Series for actual correction date (done-week) — provided by API as corrected_by_done
            const correctedByDone = Array.isArray(d.corrected_by_done) ? d.corrected_by_done : new Array(len).fill(0);

            el._chart = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels,
                    datasets: [
                        // Alarms (stacked): Critical + Warning
                        { label: 'Critical', data: alarmsCritical, backgroundColor: '#ad0404ff', borderWidth: 0, stack: 'alarms', categoryPercentage: 0.7, barPercentage: 0.8 },
                        { label: 'Warning', data: alarmsWarning, backgroundColor: '#f73f3fff', borderWidth: 0, stack: 'alarms', categoryPercentage: 0.7, barPercentage: 0.8 },
                        // Corrected from Alarms (side-by-side cluster)
                        { label: 'Corrected from Alarms', data: correctedFromAlarms, backgroundColor: '#16a34a', borderWidth: 0, stack: 'corrected', categoryPercentage: 0.7, barPercentage: 0.8 },
                        // Actual corrections by Done week (line) — draw on top with shadow
                        { label: 'Corrected (Actual Week)', data: correctedByDone, type: 'line', borderColor: '#059669', backgroundColor: 'rgba(5,150,105,0.1)', fill: false, tension: 0.25, pointRadius: 3, borderWidth: 2, order: 999 }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: true,
                            position: 'bottom',
                            labels: {
                                // use pointStyle so we can render a line-style marker for the line dataset
                                usePointStyle: true,
                                generateLabels: function(chart) {
                                    // start from default labels
                                    const original = Chart.defaults.plugins.legend.labels.generateLabels(chart);
                                    return original.map(label => {
                                        try {
                                            const ds = chart.data.datasets[label.datasetIndex];
                                            // For the actual corrections line, render a line-only marker
                                            if (ds && (ds.type === 'line' || ds.label === 'Corrected (by Done week)')) {
                                                // render a horizontal line marker in the legend
                                                label.pointStyle = 'line';
                                                // no filled box
                                                label.fillStyle = 'transparent';
                                                // use the line stroke color for visibility
                                                label.strokeStyle = ds.borderColor || ds.backgroundColor || label.strokeStyle;
                                                // line width used by legend drawing
                                                label.lineWidth = ds.borderWidth || 2;
                                                // make the legend marker wider so the line is visible
                                                label.boxWidth = 28;
                                                // ensure horizontal orientation
                                                label.rotation = 0;
                                            }
                                        } catch (e) { /* ignore and fall back to original */ }
                                        return label;
                                    });
                                }
                            }
                        },
                        tooltip: { mode: 'index', intersect: false }
                    },
                    scales: {
                        x: { stacked: true, grid: { display: false } },
                        y: { stacked: true, beginAtZero: true }
                    }
                },
                plugins: [
                    {
                        id: 'lineShadow',
                        // After all datasets drawn, redraw any line datasets on top with a shadow
                        afterDatasetsDraw(chart, args, options) {
                            const ctx = chart.ctx;
                            // find line datasets (type 'line' or matching label)
                            chart.data.datasets.forEach((ds, i) => {
                                if (ds && (ds.type === 'line' || ds.label === 'Corrected (by Done week)')) {
                                    try {
                                        ctx.save();
                                        ctx.shadowColor = 'rgba(5,150,105,0.35)';
                                        ctx.shadowBlur = 12;
                                        ctx.shadowOffsetX = 0;
                                        ctx.shadowOffsetY = 6;
                                        const meta = chart.getDatasetMeta(i);
                                        if (meta && meta.controller && typeof meta.controller.draw === 'function') {
                                            meta.controller.draw();
                                        }
                                    } catch (e) {
                                        // swallow
                                    } finally {
                                        ctx.restore();
                                    }
                                }
                            });
                        }
                    }
                ]
            });
        })
        .catch(() => {});
}

// ----- KPI Sparklines (tiny line charts) -----
// removed: KPI sparkline renderer

// ----- KPI Card Entrance + Count-up Animation -----
function animateKpiCards() {
    const cards = Array.from(document.querySelectorAll('.kpi-card'));
    if (!cards.length) return;
    const prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    // Prepare count-up targets
    const targets = cards.map(card => {
        const countEl = card.querySelector('.card-count');
        const target = countEl ? parseInt(String(countEl.textContent || '0').replace(/[^0-9-]/g,''), 10) : 0;
        // Store initial for animation
        if (countEl) {
            countEl.setAttribute('data-target', String(isFinite(target) ? target : 0));
            if (!prefersReduced) countEl.textContent = '0';
        }
        return { card, countEl };
    });

    // If reduced motion, just reveal instantly
    if (prefersReduced) {
        cards.forEach(c => c.classList.add('is-in'));
        return;
    }

    const io = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (!entry.isIntersecting) return;
            const card = entry.target;
            // Stagger via index for nicer cascade
            const idx = Math.max(0, cards.indexOf(card));
            const delay = Math.min(400, idx * 80);
            setTimeout(() => {
                card.classList.add('is-in');
                const countEl = card.querySelector('.card-count');
                if (countEl && !countEl._counted) {
                    countEl._counted = true;
                    doCountUp(countEl, parseInt(countEl.getAttribute('data-target') || '0', 10));
                }
            }, delay);
            io.unobserve(card);
        });
    }, { root: null, threshold: 0.2 });

    cards.forEach(c => io.observe(c));
}

function doCountUp(el, target) {
    const duration = 900; // ms
    const start = 0;
    const startTs = performance.now();
    const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
    function step(now) {
        const t = clamp((now - startTs) / duration, 0, 1);
        // easeOutCubic
        const eased = 1 - Math.pow(1 - t, 3);
        const val = Math.round(start + (target - start) * eased);
        el.textContent = String(val);
        if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
}

// ----- KPI Weekly / All-time Toggle -----
function initKpiScopeToggle() {
    const container = document.getElementById('kpi-cards');
    if (!container) return;
    const scopeHint = document.querySelector('.kpi-scope-hint');
    const seg = document.querySelector('.segmented');
    if (!seg) return;
    const buttons = Array.from(seg.querySelectorAll('.seg-item'));
    const setActive = (btn) => {
        buttons.forEach(b => b.classList.toggle('is-active', b === btn));
        buttons.forEach(b => b.setAttribute('aria-selected', b === btn ? 'true' : 'false'));
    };
    const updateHint = (scope) => {
        if (!scopeHint) return;
        scopeHint.textContent = (scope === 'all') ? 'Showing all-time totals | Current Date:' : 'Current Date:';
    };
    const updateCounts = (counts) => {
        // Map KPI selectors to fields
        const mapping = [
            { sel: '.kpi-total .card-count', key: 'total' },
            { sel: '.kpi-completed .card-count', key: 'completed' },
            { sel: '.kpi-inprogress .card-count', key: 'active_in_progress' },
            { sel: '.kpi-revisit .card-count', key: 'for_revisit' },
            { sel: '.kpi-waived .card-count', key: 'waived' },
            { sel: '.kpi-alarms .card-count', key: 'alarm_crit_warn' },
        ];
        // Subchips in Total
        const sub = [
            { sel: '.kpi-total .chip-planned', key: 'planned_tests' },
            { sel: '.kpi-total .chip-unplanned', key: 'unplanned_tests' },
            { sel: '.kpi-total .chip-validation', key: 'validation_tests' },
            { sel: '.kpi-total .chip-other', key: 'other_schedule_tests' },
        ];
        // Visual: mark as updating
        container.classList.add('updating');
        setTimeout(() => container.classList.remove('updating'), 250);
        // Animate number swaps
        mapping.forEach(m => {
            const el = document.querySelector(m.sel);
            if (!el) return;
            const target = parseInt(counts[m.key] || 0, 10);
            // Count-up from current displayed value
            const startVal = parseInt(String(el.textContent || '0').replace(/[^0-9-]/g,''), 10) || 0;
            animateNumber(el, startVal, target, 600);
        });
        // Update subchips labels
        sub.forEach(s => {
            const chip = document.querySelector(s.sel);
            if (!chip) return;
            const val = parseInt(counts[s.key] || 0, 10);
            const label = chip.getAttribute('data-label') || chip.textContent.split(/\s+/)[0] || '';
            chip.innerHTML = '<i class="kpi-dot"></i> ' + label + ' ' + val;
            // Planned and Unplanned should always remain visible (even if zero)
            if (s.sel.includes('chip-planned') || s.sel.includes('chip-unplanned')) {
                chip.style.display = 'inline-flex';
            } else {
                // Validation/Other: toggle visibility based on value
                chip.style.display = val > 0 ? 'inline-flex' : 'none';
            }
        });
    // summary removed; rely on chips for breakdown
    // (compact breakdown removed) 
    };

    const fetchCounts = (scope) => {
        const w = container.getAttribute('data-week');
        const y = container.getAttribute('data-year');
        const qp = (scope === 'all') ? 'scope=all' : `scope=weekly&week=${encodeURIComponent(w)}&year=${encodeURIComponent(y)}`;
        return fetch('/api/dashboard/kpi_counts?' + qp).then(r => r.json());
    };

    const onClick = (e) => {
        const btn = e.currentTarget;
        const scope = btn.getAttribute('data-scope') || 'weekly';
        setActive(btn);
        container.setAttribute('data-scope', scope);
        updateHint(scope);
        // Show/hide week picker
        const weekPickerWrap = document.getElementById('kpi-week-picker');
        if (weekPickerWrap) {
            weekPickerWrap.closest('label').style.display = (scope === 'all') ? 'none' : 'inline-flex';
        }
        fetchCounts(scope).then(updateCounts).catch(() => {});
        // Navigate so server-side board rendering aligns with selected scope
        try {
            const cur = new URL(window.location.href);
            const params = new URLSearchParams(cur.search);
            if (scope === 'all') {
                params.set('scope', 'all');
                params.delete('week');
                params.delete('year');
            } else {
                params.set('scope', 'weekly');
                const weekInput = document.getElementById('kpi-week-picker');
                if (weekInput && weekInput.value) {
                    const parts = (weekInput.value || '').split('-W');
                    if (parts.length === 2) {
                        params.set('year', parts[0]);
                        params.set('week', String(parseInt(parts[1], 10)));
                    }
                }
            }
            cur.search = params.toString();
            if (cur.toString() !== window.location.href) window.location.href = cur.toString();
        } catch (err) {
            // ignore navigation errors
        }
    };
    buttons.forEach(b => b.addEventListener('click', onClick));

    // Wire week picker change to update data-week/data-year and refresh when in weekly scope
    const weekInput = document.getElementById('kpi-week-picker');
    if (weekInput) {
        weekInput.addEventListener('change', (ev) => {
            const v = (ev.target.value || '').trim(); // format YYYY-Www
            if (!v) return;
            const parts = v.split('-W');
            if (parts.length === 2) {
                const y = parts[0];
                const w = String(parseInt(parts[1], 10));
                container.setAttribute('data-week', w);
                container.setAttribute('data-year', y);
                // If weekly scope selected, refresh
                const active = buttons.find(b => b.classList.contains('is-active'));
                const scope = active && active.getAttribute('data-scope') || 'weekly';
                if (scope === 'weekly') {
                    // Update KPI counts via API
                    fetchCounts('weekly').then(updateCounts).catch(() => {});
                    // Also update the page URL so server-side board (board_rows/equipment_board)
                    // will be rendered for the selected week/year. This preserves existing
                    // query params and only sets week/year.
                    try {
                        const cur = new URL(window.location.href);
                        const params = new URLSearchParams(cur.search);
                        params.set('week', String(w));
                        params.set('year', String(y));
                        // Only navigate if something would change
                        if (cur.search !== '?' + params.toString()) {
                            cur.search = params.toString();
                            window.location.href = cur.toString();
                        }
                    } catch (e) {
                        // fallback: simple reload
                        window.location.search = `week=${encodeURIComponent(w)}&year=${encodeURIComponent(y)}`;
                    }
                }
            }
        });
        // Initialize visibility based on current scope
        const curScope = container.getAttribute('data-scope') || 'weekly';
        weekInput.closest('label').style.display = (curScope === 'all') ? 'none' : 'inline-flex';
    }
}

function animateNumber(el, from, to, duration) {
    const start = performance.now();
    const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
    function step(now) {
        const t = clamp((now - start) / duration, 0, 1);
        const eased = 1 - Math.pow(1 - t, 3);
        const val = Math.round(from + (to - from) * eased);
        el.textContent = String(val);
        if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
}
