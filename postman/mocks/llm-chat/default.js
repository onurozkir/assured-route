// Generated from contracts/chat-completions.yaml, extended with deterministic failures.
// Local-only synthetic values. Never point production credentials at this mock.
const http = require('http');
const invoice = {
  document_type: 'invoice', invoice_number: 'INV-2026-001',
  invoice_date: '2026-10-20', due_date: '2026-11-20', currency: 'TRY',
  invoice_total: '1200.00', vat_total: '200.00', seller_name: 'Acme Ltd',
  seller_tax_id: '1234567890', buyer_name: 'Buyer Ltd'
};

http.createServer(async (req, res) => {
  function send(status, body) {
    res.writeHead(status, {'Content-Type': 'application/json'});
    res.end(JSON.stringify(body));
  }
  if (req.method !== 'POST' || req.url.split('?')[0] !== '/v1/chat/completions') {
    return send(501, {error: {message: 'Endpoint not modeled'}});
  }
  const body = req.body;
  if (!body || typeof body.model !== 'string' || !Array.isArray(body.messages)) {
    return send(400, {error: {message: 'model and messages required'}});
  }
  const expectedKey = body.model.startsWith('cheap') ? 'simulation-cheap-key' : 'simulation-expensive-key';
  if (req.headers.authorization !== 'Bearer ' + expectedKey) {
    return send(401, {error: {message: 'Invalid synthetic credential'}});
  }
  if (!body.max_completion_tokens && !body.max_tokens) {
    return send(400, {error: {message: 'Missing output token limit'}});
  }
  const model = body.model;
  const forced = model.match(/-(401|429|500)$/);
  if (forced) return send(Number(forced[1]), {error: {message: 'Synthetic upstream error'}});
  if (model.endsWith('-timeout')) await new Promise(resolve => setTimeout(resolve, 1500));
  const isVerification = body.messages[0].content.startsWith('Check a candidate invoice');
  let payload = isVerification ? {agrees: true, disputed_fields: []} : {...invoice};
  if (model.endsWith('-schema-fail')) payload = {document_type: 'invoice'};
  if (model.endsWith('-grounding-fail')) payload.invoice_total = '999.00';
  if (model.endsWith('-fatal')) payload.invoice_total = '100.00';
  if (model.endsWith('-disagree') && isVerification) payload = {agrees: false, disputed_fields: ['seller_name']};
  const content = model.endsWith('-invalid-json') ? '{incomplete' : JSON.stringify(payload);
  send(200, {
    id: 'synthetic-completion', model: model + '-snapshot',
    choices: [{index: 0, finish_reason: model.endsWith('-truncated') ? 'length' : 'stop',
      message: {role: 'assistant', content, refusal: model.endsWith('-refusal') ? 'Synthetic refusal' : null}}]
  });
}).listen(process.env.PORT || 4500);
