const state = { currentShift: null, comparison: null };
const labels = {
  auto: 'Auto select', random_forest: 'Random Forest',
  gradient_boosting: 'Gradient Boosting', linear_regression: 'Linear Regression',
  rules_fallback: 'Rules fallback', manager_override: 'Manager override'
};

const element = (id) => document.getElementById(id);
const formatModel = (value) => labels[value] || value || 'Unavailable';

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const body = response.status === 204 ? null : await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(body.error || `Request failed (${response.status})`);
    error.details = body.details;
    throw error;
  }
  return body;
}

function toast(message, tone = 'default') {
  const node = element('toast');
  node.textContent = message;
  node.className = `fixed right-5 top-5 z-50 max-w-sm rounded-md px-4 py-3 text-sm text-white shadow-panel ${tone === 'error' ? 'bg-coral' : 'bg-ink'}`;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.add('hidden'), 3500);
}

function setBusy(button, busy, busyText) {
  if (!button.dataset.label) button.dataset.label = button.innerHTML;
  button.disabled = busy;
  button.innerHTML = busy ? `<span class="size-4 animate-spin rounded-full border-2 border-white/40 border-t-white"></span>${busyText}` : button.dataset.label;
}

function initializeNavigation() {
  const titles = { schedule: 'Build a safe shift plan', data: 'Prepare training history', models: 'Compare prediction methods' };
  document.querySelectorAll('.nav-button').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.nav-button').forEach((item) => item.removeAttribute('aria-current'));
      document.querySelectorAll('[data-view]').forEach((view) => view.classList.remove('is-active'));
      button.setAttribute('aria-current', 'page');
      document.querySelector(`[data-view="${button.dataset.target}"]`).classList.add('is-active');
      element('pageTitle').textContent = titles[button.dataset.target];
    });
  });
}

async function loadDashboard() {
  try {
    const [health, status, roles, departments, skills, comparison] = await Promise.all([
      api('/api/health'), api('/api/model/status'), api('/api/roles'),
      api('/api/departments'), api('/api/skills'), api('/api/model/comparison')
    ]);
    element('serviceBadge').innerHTML = `<span class="size-2 rounded-full bg-leaf"></span>${health.status === 'ok' ? 'Online' : health.status}`;
    element('trainingCount').textContent = status.training_records.toLocaleString();
    element('activeModel').textContent = formatModel(status.strategy);
    state.comparison = comparison;
    renderReferenceData(roles.roles, departments.departments, skills.skills);
    renderModels(comparison);
  } catch (error) {
    element('serviceBadge').innerHTML = '<span class="size-2 rounded-full bg-coral"></span>Offline';
    toast(error.message, 'error');
  }
}

function renderReferenceData(roles, departments, skills) {
  const activeRoles = roles.filter((item) => item.active);
  const activeDepartments = departments.filter((item) => item.active);
  element('roleSelect').innerHTML = activeRoles.length
    ? `<option value="" disabled selected>Select a role</option>${activeRoles.map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)}</option>`).join('')}`
    : '<option value="" disabled selected>No active roles configured</option>';
  element('departmentSelect').innerHTML = `<option value="">Any department</option>${activeDepartments.map((item) => `<option value="${escapeHtml(item.name)}">${escapeHtml(item.name)}</option>`).join('')}`;
  element('skillSelect').innerHTML = skills.length ? skills.map((skill) => `<option value="${escapeHtml(skill.name)}">${escapeHtml(skill.name)}</option>`).join('') : '<option disabled>No skills configured</option>';
}

function renderModels(comparison) {
  const grid = element('modelGrid');
  const fallback = element('modelFallback');
  if (!comparison.models.length) {
    grid.innerHTML = '';
    fallback.classList.remove('hidden');
    fallback.innerHTML = `<h3 class="font-bold">More history needed</h3><p class="mt-1 text-sm text-black/55">${comparison.training_records} of ${comparison.minimum_training_records} required records are available. Predictions currently use the rules fallback.</p>`;
    return;
  }
  fallback.classList.add('hidden');
  const maxMae = Math.max(...comparison.models.map((model) => model.mae), 0.01);
  grid.innerHTML = comparison.models.map((model, index) => `
    <article class="rounded-lg border ${model.strategy === comparison.best_model ? 'border-leaf' : 'border-black/10'} bg-white p-5 shadow-panel">
      <div class="flex items-start justify-between gap-3"><div><p class="text-xs font-bold uppercase text-black/45">Rank ${index + 1}</p><h3 class="mt-1 text-lg font-bold">${formatModel(model.strategy)}</h3></div>${model.strategy === comparison.best_model ? '<span class="rounded-full bg-leaf/10 px-2.5 py-1 text-xs font-bold text-leaf">Best fit</span>' : ''}</div>
      <div class="mt-6"><div class="flex justify-between text-xs font-semibold"><span>Mean absolute error</span><span>${model.mae.toFixed(3)}</span></div><div class="mt-2 h-2 overflow-hidden rounded-full bg-black/5"><div class="metric-bar h-full bg-leaf" style="width:${Math.max(8, (model.mae / maxMae) * 100)}%"></div></div></div>
      <dl class="mt-5 grid grid-cols-2 gap-3 border-t border-black/10 pt-4"><div><dt class="text-xs text-black/45">RMSE</dt><dd class="font-bold">${model.rmse.toFixed(3)}</dd></div><div><dt class="text-xs text-black/45">R²</dt><dd class="font-bold">${model.r2.toFixed(3)}</dd></div></dl>
      <button class="mt-5 w-full rounded-md border border-black/15 px-3 py-2 text-sm font-bold hover:border-leaf" data-use-model="${model.strategy}">Use for next shift</button>
    </article>`).join('');
  document.querySelectorAll('[data-use-model]').forEach((button) => button.addEventListener('click', () => {
    document.querySelector('[name="model_strategy"]').value = button.dataset.useModel;
    document.querySelector('[data-target="schedule"]').click();
    toast(`${formatModel(button.dataset.useModel)} selected`);
  }));
}

function schedulePayload(form) {
  const data = new FormData(form);
  const payload = {
    shift_date: data.get('shift_date'), start_time: data.get('start_time'), end_time: data.get('end_time'),
    required_role: data.get('required_role').trim(), workload_score: Number(data.get('workload_score')),
    model_strategy: data.get('model_strategy'), allow_overtime: data.get('allow_overtime') === 'on',
    required_skills: [...element('skillSelect').selectedOptions].map((option) => option.value)
  };
  const department = data.get('required_department').trim();
  if (department) payload.required_department = department;
  if (element('overrideToggle').checked) payload.required_staff = Number(data.get('required_staff'));
  return payload;
}

async function submitSchedule(event) {
  event.preventDefault();
  const button = element('predictButton');
  setBusy(button, true, 'Predicting...');
  try {
    const result = await api('/api/shifts/recommendations', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(schedulePayload(event.currentTarget))
    });
    state.currentShift = result;
    renderShift(result);
    toast('Draft recommendation created');
  } catch (error) { toast(error.message, 'error'); }
  finally { setBusy(button, false); lucide.createIcons(); }
}

function renderShift(shift) {
  element('emptyResults').classList.add('hidden');
  element('resultsContent').classList.remove('hidden');
  element('resultStatus').textContent = shift.status;
  element('resultId').textContent = `Shift #${shift.id}`;
  element('resultTitle').textContent = `${shift.required_role} coverage`;
  element('resultSubtitle').textContent = `${shift.shift_date} · ${shift.start_time}–${shift.end_time}${shift.required_department ? ` · ${shift.required_department}` : ''}`;
  element('requiredStaff').textContent = shift.required_staff;
  element('assignedCount').textContent = shift.assignments.length;
  const gap = Math.max(0, shift.required_staff - shift.assignments.length);
  element('coverageGap').textContent = gap;
  element('coverageGap').className = `mt-1 text-xl font-bold ${gap ? 'text-coral' : 'text-leaf'}`;
  element('coverageStat').textContent = gap ? `${gap} open` : 'Covered';
  element('staffingRange').textContent = `${shift.staffing_range.minimum}–${shift.staffing_range.maximum}`;
  element('resultModel').textContent = formatModel(shift.model_source);
  const summary = shift.constraint_summary || {};
  element('candidateSummary').textContent = `${summary.eligible_candidates || 0} eligible of ${summary.considered_candidates || 0}`;
  element('warningList').innerHTML = (shift.constraint_warnings || []).map((warning) => `<p class="flex items-start gap-2 rounded-md bg-sun/15 px-3 py-2 text-sm text-[#6b4a0e]"><i data-lucide="triangle-alert" class="mt-0.5 size-4 shrink-0"></i>${escapeHtml(warning)}</p>`).join('');
  element('assignmentList').innerHTML = shift.assignments.length ? shift.assignments.map((assignment, index) => `
    <article class="grid gap-3 rounded-md border border-black/10 p-4 sm:grid-cols-[auto_1fr_auto] sm:items-center">
      <span class="grid size-9 place-items-center rounded-full bg-[#e9ede7] text-sm font-bold text-forest">${index + 1}</span>
      <div><div class="flex flex-wrap items-center gap-2"><h4 class="font-bold">${escapeHtml(assignment.employee_name)}</h4><span class="text-xs text-black/45">${escapeHtml(assignment.department)}</span></div><p class="mt-1 text-xs leading-5 text-black/55">${escapeHtml(assignment.reason)}</p></div>
      <div class="sm:text-right"><p class="text-lg font-bold text-forest">${assignment.recommendation_score.toFixed(1)}</p><p class="text-xs text-black/45">${assignment.projected_weekly_hours}h projected</p></div>
    </article>`).join('') : '<div class="rounded-md border border-coral/30 bg-coral/5 p-4 text-sm text-coral">No eligible employees matched every constraint.</div>';
  element('decisionPanel').classList.toggle('hidden', shift.status !== 'draft');
  lucide.createIcons();
}

async function decideShift(decision) {
  if (!state.currentShift) return;
  const managerName = element('managerName').value.trim();
  if (!managerName) { toast('Enter a manager name before deciding', 'error'); return; }
  try {
    const shift = await api(`/api/shifts/${state.currentShift.id}/decision`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, manager_name: managerName, manager_note: element('managerNote').value.trim() })
    });
    state.currentShift = shift;
    renderShift(shift);
    toast(`Shift ${decision}`);
  } catch (error) { toast(error.message, 'error'); }
}

async function uploadCsv(event) {
  event.preventDefault();
  const file = element('csvFile').files[0];
  if (!file) { toast('Choose a CSV file first', 'error'); return; }
  const button = element('uploadButton');
  setBusy(button, true, 'Importing...');
  try {
    const form = new FormData(); form.append('file', file);
    const result = await api('/api/historical-staffing/import', { method: 'POST', body: form });
    const panel = element('uploadResult');
    panel.className = 'mt-4 rounded-md border border-leaf/30 bg-leaf/5 p-4 text-sm text-forest';
    panel.innerHTML = `<strong class="block">Import complete</strong><span>${result.imported_records} added · ${result.skipped_duplicates} duplicates skipped · ${result.total_rows} rows checked</span>`;
    toast(`${result.imported_records} training records imported`);
    await loadDashboard();
  } catch (error) {
    const invalid = error.details?.invalid_rows?.map((row) => `Row ${row.row}: ${escapeHtml(row.error)}`).join('<br>');
    const panel = element('uploadResult');
    panel.className = 'mt-4 rounded-md border border-coral/30 bg-coral/5 p-4 text-sm text-coral';
    panel.innerHTML = `<strong class="block">Import failed</strong>${escapeHtml(error.message)}${invalid ? `<span class="mt-2 block">${invalid}</span>` : ''}`;
    toast(error.message, 'error');
  } finally { setBusy(button, false); lucide.createIcons(); }
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);
}

document.addEventListener('DOMContentLoaded', () => {
  initializeNavigation();
  const tomorrow = new Date(); tomorrow.setDate(tomorrow.getDate() + 1);
  document.querySelector('[name="shift_date"]').value = tomorrow.toISOString().slice(0, 10);
  element('workloadInput').addEventListener('input', (event) => { element('workloadOutput').textContent = event.target.value; });
  element('overrideToggle').addEventListener('change', (event) => { element('staffingOverride').disabled = !event.target.checked; });
  element('scheduleForm').addEventListener('submit', submitSchedule);
  element('uploadForm').addEventListener('submit', uploadCsv);
  element('csvFile').addEventListener('change', (event) => { const file = event.target.files[0]; if (file) { element('fileName').textContent = file.name; element('fileMeta').textContent = `${(file.size / 1024).toFixed(1)} KB`; } });
  const dropZone = element('dropZone');
  ['dragenter', 'dragover'].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add('border-leaf', 'bg-leaf/5');
  }));
  ['dragleave', 'drop'].forEach((eventName) => dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove('border-leaf', 'bg-leaf/5');
  }));
  dropZone.addEventListener('drop', (event) => {
    const file = event.dataTransfer.files[0];
    if (!file) return;
    const transfer = new DataTransfer(); transfer.items.add(file);
    element('csvFile').files = transfer.files;
    element('csvFile').dispatchEvent(new Event('change'));
  });
  document.querySelectorAll('[data-decision]').forEach((button) => button.addEventListener('click', () => decideShift(button.dataset.decision)));
  element('refreshButton').addEventListener('click', loadDashboard);
  lucide.createIcons();
  loadDashboard();
});