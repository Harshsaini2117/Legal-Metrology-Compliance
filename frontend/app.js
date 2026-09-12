const input = document.querySelector('#image-input');
const dropzone = document.querySelector('#dropzone');
const preview = document.querySelector('#image-preview');
const previewEmpty = document.querySelector('#preview-empty');
const previewMeta = document.querySelector('#preview-meta');
const fileName = document.querySelector('#file-name');
const clearFile = document.querySelector('#clear-file');
const scanButton = document.querySelector('#scan-button');
const formMessage = document.querySelector('#form-message');
const processing = document.querySelector('#processing');
const results = document.querySelector('#results');
const API_BASE_URL = 'http://127.0.0.1:8000';

let selectedFile = null;
let previewUrl = null;

const fieldLabels = {
  product_name: 'Product name', mrp: 'MRP', net_quantity: 'Net quantity',
  manufacturer: 'Manufacturer', manufacturer_address: 'Manufacturer address',
  importer: 'Importer', importer_address: 'Importer address', packer: 'Packer',
  packer_address: 'Packer address', country_of_origin: 'Country of origin',
  month_year: 'Month / year', size: 'Size / dimensions',
  mrp_inclusive_of_taxes: 'Tax-inclusive MRP', consumer_care: 'Consumer care'
};

const displayedFields = [
  'product_name', 'mrp', 'mrp_inclusive_of_taxes', 'net_quantity',
  'manufacturer', 'manufacturer_address', 'importer', 'importer_address',
  'month_year', 'country_of_origin', 'size', 'consumer_care'
];

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[char]);
}

function setMessage(message, isError = false) {
  formMessage.textContent = message;
  formMessage.classList.toggle('error', isError);
}

function apiErrorMessage(payload, status) {
  const detail = payload?.detail;
  if (typeof detail === 'string' && detail) return detail;
  if (detail && typeof detail.message === 'string') return detail.message;
  if (typeof payload?.message === 'string') return payload.message;
  return `The scan service could not complete the request (HTTP ${status}).`;
}

function checkDisplayStatus(check) {
  return check.status || '—';
}

function scanFailureMessage(error) {
  if (error instanceof TypeError) {
    return 'Unable to reach the scan service at 127.0.0.1:8000. Make sure the API is running and available to this page.';
  }
  return error.message || 'Unable to contact the scan service.';
}

function clearSelection() {
  selectedFile = null;
  input.value = '';
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  preview.hidden = true;
  preview.removeAttribute('src');
  previewEmpty.hidden = false;
  previewMeta.hidden = true;
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
  preview.src = previewUrl;
  preview.hidden = false;
  previewEmpty.hidden = true;
  previewMeta.hidden = false;
  fileName.textContent = `${file.name} · ${(file.size / 1024 / 1024).toFixed(2)} MB`;
  scanButton.disabled = false;
  setMessage('Image ready for analysis.');
}

input.addEventListener('change', event => selectFile(event.target.files[0]));
clearFile.addEventListener('click', clearSelection);
['dragenter', 'dragover'].forEach(eventName => dropzone.addEventListener(eventName, event => { event.preventDefault(); dropzone.classList.add('dragging'); }));
['dragleave', 'drop'].forEach(eventName => dropzone.addEventListener(eventName, event => { event.preventDefault(); dropzone.classList.remove('dragging'); }));
dropzone.addEventListener('drop', event => selectFile(event.dataTransfer.files[0]));

scanButton.addEventListener('click', async () => {
  if (!selectedFile) return;
  scanButton.disabled = true;
  scanButton.querySelector('.button-label').textContent = 'Scanning…';
  processing.hidden = false;
  results.hidden = true;
  setMessage('Your image is being processed. This can take a moment.');

  try {
    const formData = new FormData();
    formData.append('file', selectedFile);
    const response = await fetch(`${API_BASE_URL}/scan`, { method: 'POST', body: formData });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(apiErrorMessage(payload, response.status));
    renderResults(payload);
    results.hidden = false;
    results.scrollIntoView({ behavior: 'smooth', block: 'start' });
    setMessage('Scan complete. Review the assessment below.');
  } catch (error) {
    setMessage(scanFailureMessage(error), true);
  } finally {
    processing.hidden = true;
    scanButton.disabled = false;
    scanButton.querySelector('.button-label').textContent = 'Scan product';
  }
});

function renderResults(result) {
  const report = result.compliance_report || {};
  const checks = Array.isArray(report.checks) ? report.checks : [];
  const summary = result.summary || {
    overall_status: report.overall_status,
    compliance_score: report.compliance_score,
    total_checks: checks.length,
    passed_checks: checks.filter(check => check.status === 'PASS').length,
    failed_checks: checks.filter(check => check.status === 'FAIL').length,
    unable_to_verify_checks: checks.filter(check => check.verification_status === 'UNABLE_TO_VERIFY').length,
    violation_count: (report.violations || []).length
  };
  const status = summary.overall_status || 'UNABLE_TO_VERIFY';
  const statusClass = status.toLowerCase().replaceAll('_', '-');
  const descriptions = { COMPLIANT: 'All detected, applicable declarations passed review.', NON_COMPLIANT: 'One or more detected declarations require attention.', UNABLE_TO_VERIFY: 'Some declarations could not be verified from this label.' };
  const symbols = { COMPLIANT: '✓', NON_COMPLIANT: '!', UNABLE_TO_VERIFY: '?' };

  document.querySelector('#result-file').textContent = selectedFile?.name || 'Product label';
  document.querySelector('#status-banner').className = `status-banner ${statusClass}`;
  document.querySelector('#status-icon').textContent = symbols[status] || '?';
  document.querySelector('#overall-status').textContent = status.replaceAll('_', ' ');
  document.querySelector('#status-description').textContent = descriptions[status] || 'Assessment completed.';
  document.querySelector('#compliance-score').textContent = summary.compliance_score == null ? '—' : `${summary.compliance_score}%`;

  const metricData = [
    [summary.total_checks ?? checks.length, 'checks reviewed'],
    [summary.passed_checks ?? 0, 'passed checks'],
    [summary.failed_checks ?? checks.filter(check => check.status === 'FAIL').length, 'failed checks'],
    [summary.unable_to_verify_checks ?? 0, 'unable to verify'],
    [summary.violation_count ?? (report.violations || []).length, 'violations']
  ];
  document.querySelector('#metrics').innerHTML = metricData.map(([value, label]) => `<div class="metric"><strong>${escapeHtml(value)}</strong><span>${label}</span></div>`).join('');

  const fields = result.extracted_fields || {};
  document.querySelector('#fields-list').innerHTML = displayedFields
    .map(name => {
      const value = fields[name];
      const displayValue = value === true ? 'Confirmed' : value === false ? 'Not confirmed' : value || 'Not detected';
      return `<div class="field-row"><dt>${escapeHtml(fieldLabels[name])}</dt><dd>${escapeHtml(displayValue)}</dd></div>`;
    }).join('');

  document.querySelector('#checks-list').innerHTML = checks.length
    ? checks.map(check => {
      const unable = check.verification_status === 'UNABLE_TO_VERIFY';
      const failed = check.status === 'FAIL';
      const className = failed ? 'fail' : unable ? 'unable' : '';
      const icon = failed ? '!' : unable ? '?' : '✓';
      const label = check.title || check.field?.replaceAll('_', ' ') || check.rule_id || 'Compliance check';
      const metadata = [
        check.rule_id && `Rule ${check.rule_id}`,
        check.field && `Field: ${check.field.replaceAll('_', ' ')}`,
        check.severity && `Severity: ${check.severity}`,
        unable && 'UNABLE_TO_VERIFY'
      ].filter(Boolean).join(' · ');
      return `<div class="check ${className}"><span class="check-symbol">${icon}</span><div><b>${escapeHtml(label)}</b><small>${escapeHtml(metadata)}</small><small>${escapeHtml(check.message || '')}</small></div><span class="check-status">${escapeHtml(checkDisplayStatus(check))}</span></div>`;
    }).join('')
    : '<p class="empty">No check details were returned.</p>';

  const violations = Array.isArray(report.violations) ? report.violations : [];
  document.querySelector('#violation-count').textContent = `${violations.length} item${violations.length === 1 ? '' : 's'}`;
  document.querySelector('#violations-list').innerHTML = violations.length
    ? violations.map(item => `<div class="violation"><b>${escapeHtml(item.rule_id || 'Compliance item')} · ${escapeHtml(item.field?.replaceAll('_', ' ') || 'Declaration')}</b><p>${escapeHtml(item.message || 'A declaration did not pass the available check.')}</p></div>`).join('')
    : '<p class="no-violations">No violations were identified in the available evidence.</p>';

  const evidence = Array.isArray(result.evidence) ? result.evidence : (Array.isArray(result.ocr_results) ? result.ocr_results.map(item => ({ detected_text: item.text, confidence: item.confidence })) : []);
  document.querySelector('#evidence-list').innerHTML = evidence.length
    ? evidence.slice(0, 12).map(item => `<div class="evidence-item"><p>${escapeHtml(item.detected_text || item.text || 'Detected label text')}</p><div>${typeof item.confidence === 'number' ? `<span>${Math.round(item.confidence * 100)}% confidence</span>` : ''}${item.related_field ? `<i>${escapeHtml(fieldLabels[item.related_field] || item.related_field)}</i>` : ''}${item.related_check ? `<i>${escapeHtml(item.related_check)}</i>` : ''}</div></div>`).join('')
    : '<p class="empty">No OCR evidence was returned for this scan.</p>';

  const reportLink = document.querySelector('#report-download');
  if (result.scan_id && (result.report_filename || result.report_path)) {
    reportLink.href = `${API_BASE_URL}/scans/${encodeURIComponent(result.scan_id)}/report`;
    reportLink.hidden = false;
  } else {
    reportLink.hidden = true;
  }
}
