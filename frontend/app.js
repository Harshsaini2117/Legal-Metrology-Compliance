const input = document.querySelector('#image-input');
const dropzone = document.querySelector('#dropzone');
const preview = document.querySelector('#image-preview');
const previewEmpty = document.querySelector('#preview-empty');
const previewMeta = document.querySelector('#preview-meta');
const previewState = document.querySelector('#preview-state');
const scanButton = document.querySelector('#scan-button');
const formMessage = document.querySelector('#form-message');
const processing = document.querySelector('#processing');
const results = document.querySelector('#results');
const historyList = document.querySelector('#history-list');
const refreshHistoryButton = document.querySelector('#refresh-history');
const historyFeedback = document.querySelector('#history-feedback');
const evidenceImage = document.querySelector('#evidence-image');
const evidencePreviewEmpty = document.querySelector('#evidence-preview-empty');
const evidencePreview = document.querySelector('#evidence-preview');
const evidencePreviewLabel = document.querySelector('#evidence-preview-label');
const previewPanel = document.querySelector('#preview-panel');
const reportNote = document.querySelector('#report-note');
const processingTitle = document.querySelector('#processing-title');
const processingDescription = document.querySelector('#processing-description');
const processingIndicator = document.querySelector('#processing-indicator');
const processingStages = [...document.querySelectorAll('.processing-stages li')];
const workflowSteps = [...document.querySelectorAll('.workflow li')];
const API_BASE_URL = 'http://127.0.0.1:8000';

let selectedFile = null;
let previewUrl = null;
let historyLoading = false;
let historyHasLoaded = false;

const fieldLabels = {
  product_name: 'Product Name', mrp: 'MRP', net_quantity: 'Net Quantity',
  manufacturer: 'Manufacturer', manufacturer_address: 'Manufacturer Address',
  importer: 'Importer', importer_address: 'Importer Address', packer: 'Packer',
  packer_address: 'Packer Address', month_year: 'Month/Year',
  country_of_origin: 'Country of Origin', size: 'Size',
  mrp_inclusive_of_taxes: 'MRP Inclusive of Taxes', consumer_care: 'Consumer Care'
};
const displayedFields = ['product_name', 'mrp', 'net_quantity', 'manufacturer', 'manufacturer_address', 'importer', 'importer_address', 'packer', 'packer_address', 'month_year', 'country_of_origin', 'size', 'mrp_inclusive_of_taxes', 'consumer_care'];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
}
function readable(value) { return String(value || '').replaceAll('_', ' '); }
function setMessage(message, isError = false) {
  formMessage.textContent = message;
  formMessage.classList.toggle('error', isError);
}
function setProcessing(state = 'idle') {
  const visible = state !== 'idle';
  const completed = state === 'complete';
  const failed = state === 'failed';
  processing.hidden = !visible;
  processing.setAttribute('aria-hidden', String(!visible));
  processing.style.display = visible ? '' : 'none';
  processing.classList.toggle('is-complete', completed);
  processing.classList.toggle('is-failed', failed);
  processingTitle.textContent = completed ? 'Inspection complete' : failed ? 'Inspection could not complete' : 'Inspection in progress';
  processingDescription.textContent = completed
    ? 'The inspection response was received. All listed pipeline stages completed.'
    : failed
      ? 'The service did not return a completed inspection. No individual pipeline stage result is shown.'
      : 'Analysing package label. The service returns one completed response; individual stages are shown without simulated progress.';
  processingIndicator.classList.toggle('is-complete', completed);
  processingIndicator.classList.toggle('is-failed', failed);
  processingStages.forEach((stage, index) => {
    const marker = stage.querySelector('b');
    // The service reports only a completed response, so stages stay pending
    // until that response confirms completion; no per-stage progress is implied.
    const pending = state === 'active';
    stage.classList.toggle('is-complete', completed);
    stage.classList.toggle('is-pending', pending);
    stage.classList.toggle('is-failed', failed);
    stage.removeAttribute('aria-current');
    marker.textContent = completed ? '\u2713' : failed ? '!' : String(index + 1);
  });
}
function setWorkflowReady(ready) {
  workflowSteps.forEach(step => {
    const link = step.querySelector('a');
    step.classList.toggle('is-disabled', !ready);
    link.setAttribute('aria-disabled', String(!ready));
    link.tabIndex = ready ? 0 : -1;
  });
}
function renderSelectedImage() {
  const hasSelection = Boolean(selectedFile && previewUrl);
  previewPanel.replaceChildren();
  evidencePreview.replaceChildren(evidencePreviewLabel);
  preview.hidden = !hasSelection;
  evidenceImage.hidden = !hasSelection;
  if (hasSelection) {
    preview.src = previewUrl;
    evidenceImage.src = previewUrl;
    previewPanel.append(preview, previewMeta);
    evidencePreview.append(evidenceImage);
  } else {
    preview.removeAttribute('src');
    evidenceImage.removeAttribute('src');
    previewPanel.append(previewEmpty);
    evidencePreview.append(evidencePreviewEmpty);
  }
}
function renderPreviewMeta(file) {
  previewMeta.replaceChildren();
  const name = document.createElement('span');
  name.id = 'file-name';
  name.textContent = `${file.name} - ${(file.size / 1024 / 1024).toFixed(2)} MB`;
  const remove = document.createElement('button');
  remove.className = 'text-button';
  remove.type = 'button';
  remove.textContent = 'Remove / replace';
  remove.addEventListener('click', clearSelection);
  previewMeta.append(name, remove);
  previewMeta.hidden = false;
}
function apiErrorMessage(payload, status) {
  const detail = payload?.detail;
  if (detail && typeof detail === 'object' && detail.stage) return `${detail.message || 'The scan could not be completed.'} Processing stopped during ${readable(detail.stage)}.`;
  if (typeof detail === 'string' && detail) return detail;
  if (detail && typeof detail.message === 'string') return detail.message;
  if (typeof payload?.message === 'string') return payload.message;
  return `The scan service could not complete the request (HTTP ${status}).`;
}
function scanFailureMessage(error) {
  return error instanceof TypeError
    ? 'Unable to reach the scan service at 127.0.0.1:8000. Make sure the API is running and available to this page.'
    : error.message || 'Unable to contact the scan service.';
}
function clearSelection() {
  selectedFile = null;
  input.value = '';
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  previewMeta.replaceChildren();
  renderSelectedImage();
  previewState.textContent = 'No image selected';
  scanButton.disabled = true;
  setMessage('Select a package image to begin.');
}
function selectFile(file) {
  if (!file) return;
  const supported = ['image/jpeg', 'image/png', 'image/webp'];
  if (!supported.includes(file.type)) {
    clearSelection();
    setMessage('Please choose a JPG, PNG, or WEBP image.', true);
    return;
  }
  if (file.size > 10 * 1024 * 1024) {
    clearSelection();
    setMessage('The image must be 10 MB or smaller.', true);
    return;
  }
  selectedFile = file;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = URL.createObjectURL(file);
  renderPreviewMeta(file);
  renderSelectedImage();
  scanButton.disabled = false;
  setMessage('Image ready for analysis. Select Scan product to begin.');
}

input.addEventListener('change', event => selectFile(event.target.files[0]));
refreshHistoryButton.addEventListener('click', () => loadHistory({ userInitiated: true }));
['dragenter', 'dragover'].forEach(eventName => dropzone.addEventListener(eventName, event => {
  event.preventDefault();
  dropzone.classList.add('dragging');
}));
['dragleave', 'drop'].forEach(eventName => dropzone.addEventListener(eventName, event => {
  event.preventDefault();
  dropzone.classList.remove('dragging');
}));
dropzone.addEventListener('drop', event => selectFile(event.dataTransfer.files[0]));

scanButton.addEventListener('click', async () => {
  if (!selectedFile) return;
  scanButton.disabled = true;
  scanButton.querySelector('.button-label').textContent = 'Scanning';
  setProcessing('active');
  results.hidden = true;
  results.classList.remove('is-revealed');
  setMessage('Inspection request submitted. The label is being processed.');
  try {
    const formData = new FormData();
    formData.append('file', selectedFile);
    const response = await fetch(`${API_BASE_URL}/scan`, { method: 'POST', body: formData });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(apiErrorMessage(payload, response.status));
    renderResults(payload);
    results.hidden = false;
    requestAnimationFrame(() => results.classList.add('is-revealed'));
    setProcessing('complete');
    setWorkflowReady(true);
    results.scrollIntoView({
      behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth',
      block: 'start'
    });
    setMessage('Scan complete. Review the compliance assessment below.');
    loadHistory();
  } catch (error) {
    setProcessing('failed');
    setMessage(scanFailureMessage(error), true);
  } finally {
    scanButton.disabled = false;
    scanButton.querySelector('.button-label').textContent = 'Run Inspection';
  }
});

function renderResults(result) {
  const report = result.compliance_report || {};
  const checks = Array.isArray(report.checks) ? report.checks : [];
  const violations = Array.isArray(report.violations) ? report.violations : [];
  const summary = result.summary || {};
  const status = summary.overall_status || report.overall_status || 'UNABLE_TO_VERIFY';
  const returnedStatus = check => String(check.status || check.verification_status || '').toUpperCase();
  const computed = {
    total: checks.length,
    passed: checks.filter(check => returnedStatus(check) === 'PASS').length,
    failed: checks.filter(check => returnedStatus(check) === 'FAIL').length,
    unable: checks.filter(check => returnedStatus(check) === 'UNABLE_TO_VERIFY').length,
    notApplicable: checks.filter(check => returnedStatus(check) === 'NOT_APPLICABLE').length
  };
  const statusLabels = { COMPLIANT: 'PASS', NON_COMPLIANT: 'FAIL', UNABLE_TO_VERIFY: 'UNABLE TO VERIFY' };
  const descriptions = {
    COMPLIANT: 'All detected, applicable declarations passed review.',
    NON_COMPLIANT: 'One or more declarations require attention before the product can be treated as compliant.',
    UNABLE_TO_VERIFY: 'The available label evidence was insufficient to verify one or more declarations.'
  };
  const symbols = { COMPLIANT: 'PASS', NON_COMPLIANT: 'FAIL', UNABLE_TO_VERIFY: '?' };
  const score = summary.compliance_score ?? report.compliance_score;

  document.querySelector('#result-file').textContent = selectedFile?.name || 'Product label';
  document.querySelector('#status-banner').className = `status-banner ${status.toLowerCase().replaceAll('_', '-')}`;
  document.querySelector('#status-icon').textContent = symbols[status] || '?';
  document.querySelector('#overall-status').textContent = statusLabels[status] || readable(status);
  document.querySelector('#status-description').textContent = descriptions[status] || 'Assessment completed with the evidence returned by the scan service.';
  document.querySelector('#compliance-score').textContent = score == null ? '-' : `${score} / 100`;

  const metrics = [
    [computed.passed, 'passed'],
    [computed.failed, 'failed'],
    [computed.unable, 'unable to verify'],
    [computed.notApplicable, 'not applicable'],
    [computed.total, 'checks reviewed']
  ];
  document.querySelector('#metrics').innerHTML = metrics.map(([value, label]) => `<div class="metric"><strong>${escapeHtml(value)}</strong><span>${label}</span></div>`).join('');

  const fields = result.extracted_fields || {};
  document.querySelector('#fields-list').innerHTML = displayedFields.map(name => {
    const value = fields[name];
    const displayValue = value === true ? 'Confirmed' : value === false ? 'Unable to verify' : value || 'Not detected';
    const missing = !value && value !== true ? ' data-missing' : '';
    return `<div class="field-row"><dt>${escapeHtml(fieldLabels[name])}</dt><dd${missing}>${escapeHtml(displayValue)}</dd></div>`;
  }).join('');

  document.querySelector('#checks-list').innerHTML = checks.length ? checks.map(check => {
    const checkState = returnedStatus(check);
    const unable = checkState === 'UNABLE_TO_VERIFY';
    const failed = checkState === 'FAIL';
    const notApplicable = checkState === 'NOT_APPLICABLE';
    const state = failed ? 'fail' : unable ? 'unable' : notApplicable ? 'not-applicable' : 'pass';
    const label = check.title || readable(check.field) || check.rule_id || 'Compliance check';
    const metadata = [check.rule_id && `Rule ${check.rule_id}`, check.field && `Field: ${readable(check.field)}`, check.severity && `Severity: ${check.severity}`].filter(Boolean).join(' | ');
    const evidence = Array.isArray(check.ocr_evidence) && check.ocr_evidence.length
      ? `${check.ocr_evidence.length} linked OCR item${check.ocr_evidence.length === 1 ? '' : 's'}`
      : 'No linked evidence returned';
    return `<div class="check ${state}" tabindex="0"><div class="check-name"><b>${escapeHtml(label)}</b>${metadata ? `<small>${escapeHtml(metadata)}</small>` : ''}</div><span class="check-status">${escapeHtml(check.status || check.verification_status || '-')}</span><div class="check-finding">${escapeHtml(check.message || 'No finding message returned.')}</div><div class="check-evidence">${escapeHtml(evidence)}</div></div>`;
  }).join('') : '<p class="empty">No check details were returned by the scan service.</p>';

  document.querySelector('#violation-count').textContent = `${violations.length} item${violations.length === 1 ? '' : 's'}`;
  document.querySelector('#violations-list').innerHTML = violations.length ? violations.map(item => `<div class="violation"><b>${escapeHtml(item.rule_id || 'Compliance item')} | ${escapeHtml(readable(item.field) || 'Declaration')}</b>${item.message ? `<p>${escapeHtml(item.message)}</p>` : '<p>A declaration did not pass the available check.</p>'}</div>`).join('') : '<p class="no-violations">No violations were identified in the available evidence.</p>';

  const evidence = Array.isArray(result.evidence) ? result.evidence : (Array.isArray(result.ocr_results) ? result.ocr_results.map(item => ({ detected_text: item.text, confidence: item.confidence, bounding_box: item.bounding_box })) : []);
  document.querySelector('#evidence-count').textContent = `${evidence.length} DETECTION${evidence.length === 1 ? '' : 'S'}`;
  document.querySelector('#evidence-list').innerHTML = evidence.length ? evidence.slice(0, 12).map(item => {
    const boundingBox = Array.isArray(item.bounding_box) ? '<span>Bounding box available</span>' : '';
    const confidence = typeof item.confidence === 'number' ? Math.round(item.confidence <= 1 ? item.confidence * 100 : item.confidence) : null;
    return `<div class="evidence-item"><p>${escapeHtml(item.detected_text || item.text || 'Detected label text')}</p><div>${confidence !== null ? `<span class="confidence">${confidence}% <em>confidence</em></span>` : ''}${boundingBox}${item.related_field ? `<i>${escapeHtml(fieldLabels[item.related_field] || readable(item.related_field))}</i>` : ''}${item.related_check ? `<i>${escapeHtml(item.related_check)}</i>` : ''}</div></div>`;
  }).join('') : '<p class="empty">No OCR evidence was returned for this scan.</p>';

  const reportLink = document.querySelector('#report-download');
  if (result.scan_id && (result.report_filename || result.report_path)) {
    reportLink.href = `${API_BASE_URL}/scans/${encodeURIComponent(result.scan_id)}/report`;
    reportLink.hidden = false;
    reportNote.hidden = false;
  } else {
    reportLink.hidden = true;
    reportNote.hidden = true;
  }

  renderSelectedImage();
}

function historyStatusClass(status) {
  if (status === 'NON_COMPLIANT') return 'fail';
  if (status === 'UNABLE_TO_VERIFY') return 'unable';
  return '';
}
function historyStatusLabel(status) {
  return ({ COMPLIANT: 'PASS', NON_COMPLIANT: 'FAIL', UNABLE_TO_VERIFY: 'UNABLE TO VERIFY' })[status] || readable(status || 'Completed');
}
function formatScanTime(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleString();
}
function setHistoryRefreshState(active) {
  refreshHistoryButton.disabled = active;
  refreshHistoryButton.classList.toggle('is-loading', active);
  refreshHistoryButton.innerHTML = active
    ? '<span class="refresh-spinner" aria-hidden="true"></span>Refreshing\u2026'
    : 'Refresh history';
}
async function loadHistory({ userInitiated = false } = {}) {
  if (historyLoading) return;
  historyLoading = true;
  historyFeedback.textContent = '';
  historyFeedback.classList.remove('is-error');
  setHistoryRefreshState(true);
  historyList.setAttribute('aria-busy', 'true');
  try {
    const response = await fetch(`${API_BASE_URL}/scans`);
    if (!response.ok) throw new Error('History unavailable');
    const scans = await response.json();
    historyHasLoaded = true;
    if (userInitiated) historyFeedback.textContent = 'History updated';
    if (!Array.isArray(scans) || !scans.length) {
    historyList.innerHTML = '<div class="history-empty"><span aria-hidden="true">&#9711;</span><p>No completed inspections yet</p><small>Completed package inspections will appear here.</small></div>';
      return;
    }
    historyList.innerHTML = scans.slice(0, 8).map(scan => {
      const report = scan.report_available && scan.scan_id
        ? `<a class="history-report" href="${API_BASE_URL}/scans/${encodeURIComponent(scan.scan_id)}/report" download>PDF report</a>`
        : '<span></span>';
      const id = scan.scan_id ? `Inspection ID: ${scan.scan_id}` : 'Inspection ID unavailable';
      return `<div class="history-item"><div><span class="history-file">${escapeHtml(scan.original_filename || 'Package image')}</span><small>${escapeHtml(id)} &middot; ${escapeHtml(formatScanTime(scan.scan_timestamp || scan.timestamp))}</small></div><span class="history-status ${historyStatusClass(scan.overall_status)}">${escapeHtml(historyStatusLabel(scan.overall_status))}</span><span>${scan.compliance_score == null ? '-' : `${escapeHtml(scan.compliance_score)}%`}</span>${report}</div>`;
    }).join('');
  } catch {
    if (userInitiated) {
      historyFeedback.textContent = 'History could not be refreshed';
      historyFeedback.classList.add('is-error');
    } else if (!historyHasLoaded) {
      historyList.innerHTML = '<div class="history-empty history-unavailable"><span aria-hidden="true">!</span><p>Inspection history is unavailable</p><small>You can still run a package inspection while the history service reconnects.</small></div>';
    }
  } finally {
    historyLoading = false;
    historyList.removeAttribute('aria-busy');
    setHistoryRefreshState(false);
  }
}

setProcessing('idle');
setWorkflowReady(false);
clearSelection();
loadHistory();
