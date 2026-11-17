// Adapted from the existing Studio generic metadata renderer. No execution endpoints.
import {parameterValue} from './studio-model.mjs';
import {comparison, burnTotals} from './provider.mjs';
export function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}
function field(label, control, note) {
  const box = node('div', undefined, 'studio-field'), lab = node('label', label);
  control.id = 'field-' + (++field.counter); lab.htmlFor = control.id;
  box.append(lab, control);
  if (note) { const help = node('p', note, 'field-note'); help.id = control.id + '-help'; control.setAttribute('aria-describedby', help.id); box.append(help); }
  return box;
}
field.counter = 0;
export function renderCatalog(host, catalog, model, onEdit) {
  host.replaceChildren();
  for (const block of catalog.blocks) {
    const current = model.draft.blocks.find(b => b.id === block.id);
    const details = node('details', undefined, 'studio-block');
    details.dataset.search = [block.name, block.id, block.summary, ...block.parameters.map(p => p.label + ' ' + p.key)].join(' ').toLowerCase();
    details.open = current.enabled;
    const summary = node('summary'), toggle = node('input'); toggle.type = 'checkbox'; toggle.checked = current.enabled;
    toggle.setAttribute('aria-label', 'Enable ' + block.name);
    toggle.addEventListener('click', event => event.stopPropagation());
    toggle.addEventListener('change', () => { model.edit(d => d.blocks.find(b => b.id === block.id).enabled = toggle.checked); details.open = toggle.checked; onEdit(); });
    summary.append(toggle, node('span', block.name, 'studio-block-title'), node('span', block.recordedCoverage === 'CATALOG_ONLY' ? 'CATALOGUE ONLY' : 'SAVED CASE COVERAGE', 'studio-badge'));
    details.append(summary, node('p', block.summary, 'field-note'));
    const grid = node('div', undefined, 'studio-parameters');
    for (const parameter of block.parameters) {
      let control;
      const choices = parameter.type === 'boolean' ? [{value: false, label: 'False'}, {value: true, label: 'True'}] : parameter.choices ?? [];
      if (choices.length) {
        control = node('select');
        for (const c of [{value: '', label: 'Not set'}, ...choices]) { const o = node('option', c.label ?? String(c.value)); o.value = String(c.value); control.append(o); }
      } else { control = node('input'); control.type = 'text'; control.autocomplete = 'off'; control.spellcheck = false; if (['integer','uint-string'].includes(parameter.type)) control.inputMode = 'numeric'; }
      control.value = current.parameters[parameter.key] === null ? '' : String(current.parameters[parameter.key] ?? '');
      control.dataset.blockId = block.id; control.dataset.parameter = parameter.key;
      control.addEventListener(choices.length ? 'change' : 'input', () => { model.edit(d => d.blocks.find(b => b.id === block.id).parameters[parameter.key] = parameterValue(parameter, control.value)); onEdit(); });
      grid.append(field(parameter.label + ' (' + parameter.key + ')', control, [parameter.solidityType ?? parameter.type, parameter.unit, 'range ' + (parameter.min ?? 'context') + '–' + (parameter.max ?? 'context'), parameter.requiresContext ? 'needs contract context' : 'catalogue bounds only'].filter(Boolean).join(' · ')));
    }
    if (!block.parameters.length) grid.append(node('p', 'No catalogue parameters. Configuration does not establish native support.', 'field-note'));
    details.append(grid); host.append(details);
  }
}
export function renderActions(host, model, onEdit) {
  host.replaceChildren();
  model.draft.actions.forEach((action, index) => {
    const article = node('article', undefined, 'studio-action'); article.append(node('strong', '0' + (index + 1) + ' · ' + action.kind + ' · ' + action.walletId));
    const control = node('input'); control.type = 'text'; control.inputMode = 'numeric'; control.value = action.amount;
    control.addEventListener('input', () => { model.edit(d => d.actions[index].amount = control.value); onEdit(); });
    article.append(field('Exact input (wei)', control)); host.append(article);
  });
}
function table(caption, headings, rows) {
  const scroll = node('div', undefined, 'table-scroll'); scroll.tabIndex = 0; scroll.setAttribute('role', 'region'); scroll.setAttribute('aria-label', caption);
  const t = node('table'); t.append(node('caption', caption)); const thead = node('thead'), tr = node('tr');
  headings.forEach(h => {const th = node('th', h); th.scope = 'col'; tr.append(th);}); thead.append(tr); t.append(thead);
  const body = node('tbody'); for (const row of rows) { const r = node('tr'); row.forEach(v => r.append(node('td', String(v)))); body.append(r); } t.append(body); scroll.append(t); return scroll;
}
const sum = actions => String(actions.slice(2).reduce((n, a) => n + BigInt(a.tokenTransferNetBaseUnits), 0n));
export function renderRecord(host, record) {
  host.replaceChildren(); const p = record.projection, burn = record.id === 'burn';
  const notice = node('div', undefined, 'acceptance'); notice.append(node('strong', burn ? 'Native execution + separate saved-result acceptance PASS' : 'Full original controller workflow PASS'));
  notice.append(node('p', burn ? 'Original Compare: STOP. Corrected adapter + separate verifier: PASS. Original Lab result was not installed; historical quarantine retained. This public view reads the accepted sidecar; it does not rewrite the controller.' : 'Verify → Compare → Read Final completed. A and B used the same compiled worker, identical bootstrap and identical BASELINE.'));
  host.append(notice, node('p', burn ? 'Control: Anti-Snipe + Dynamic Fee ON, Auto Burn OFF. Variant: same AS/DF settings, Auto Burn 100 bps. Protocol quote slice and subject-token transfers both change.' : 'BASELINE: Anti-Snipe and Dynamic Fee OFF. VARIANT: selected AS/DF settings ON. Two ordered 0.001 ETH buys by the same test actor.', 'field-note'));
  const worlds = node('div', undefined, 'worlds');
  p.worlds.forEach((w, i) => {const card = node('article', undefined, 'world' + (i ? ' alternative' : '')); card.append(node('p', i ? 'VARIANT' : 'BASELINE', 'world-title'), node('p', 'Buyer net received · both buys', 'field-note'), node('strong', sum(w.actions)), node('small', 'test-token base units · Transfer-event net'), node('small', 'BUY fees: ' + w.actions.slice(2).map(a => a.outerSwapFeePips.join(', ')).join(' / ') + ' pips')); worlds.append(card);});
  host.append(worlds, table('Exact buyer comparison · VARIANT minus BASELINE', ['Buy', 'BASELINE output', 'VARIANT output', 'Output Δ (base units)', 'Gas Δ'], comparison(record).map(r => [r.buy, r.baseline, r.variant, r.delta, r.gasDelta])));
  if (burn) {
    const flow = p.tokenFlow;
    host.append(node('p', 'Transfer to DEAD is not totalSupply destruction. The two output reductions are not identical to DEAD transfers: the protocol quote slice changes too.', 'field-note'));
    host.append(table('Token accounting · both buys', ['World', 'Sent to DEAD (base units)', 'totalSupply Δ', 'Accrued quote claim (wei)'], burnTotals(record).map(w => [w.world.replace('SCENARIO_', ''), w.sentToDeadBaseUnits, w.supplyDeltaBaseUnits, w.accruedProtocolClaimWei])));
    host.append(table('Per-buy token flows · worker-reported ABI observations', ['World / buy', 'Trader Δ', 'DEAD Δ', 'PoolManager Δ', 'Supply Δ', 'Quote claim Δ (wei)'], flow.worlds.flatMap(w => w.buys.map((b,i) => [w.world.replace('SCENARIO_', '') + ' / ' + (i+1), b.traderDeltaBaseUnits, b.sentToDeadBaseUnits, b.poolManagerDeltaBaseUnits, b.supplyDeltaBaseUnits, b.protocolClaimableDeltaWei]))));
    const snapshots = node('details'); snapshots.append(node('summary', 'Exact launch/buy balance snapshots · 60 ABI view calls'), node('pre', JSON.stringify(flow, null, 2))); host.append(snapshots);
  }
  const tx = node('details'); tx.append(node('summary', 'All recorded transactions, gas and state observations'));
  p.worlds.forEach(w => {
    tx.append(table(w.world, ['Action', 'Receipt', 'Gas', 'Transfer net', 'Fee pips'], w.actions.map(a => [a.kind, a.receiptStatus ? 'SUCCESS' : 'REVERT', a.gasUsed, a.tokenTransferNetBaseUnits, a.outerSwapFeePips.join(', ') || '—'])));
    tx.append(node('pre', JSON.stringify(w, null, 2)));
  }); host.append(tx);
  const provenance = node('details'); provenance.append(node('summary', 'Provenance, original result identity and integrity boundaries'));
  provenance.append(node('p', 'Sanitized publication, not the full evidence bundle. Original resultIdentity is retained as a provenance commitment; it is not recomputed from this reduced JSON. Dataset SHA-256 verifies bytes only. Original producer flags describe the saved run; opening this page performs no native or verifier execution.', 'field-note'));
  const dl = node('dl');
  for (const [label,value] of Object.entries({Profile:p.executionProfile,Operation:p.operationCommitment,'Original result identity':p.resultIdentity,'Scenario commitment':p.scenarioCommitment,'Request commitment':p.requestCommitment,'Common bootstrap root':p.commonBootstrapRoot,'Worker SHA-256':record.provenance.workerSha256,'Source commitment':record.provenance.sourceCommitment,'Original record SHA-256':record.provenance.originalRecordSha256})) dl.append(node('dt',label),node('dd',value));
  provenance.append(dl, node('pre', JSON.stringify({acceptance:record.acceptance,provenance:record.provenance},null,2)));
  const link = node('a', 'Download sanitized record JSON', 'download'); link.href = './data/' + record.id + '.json'; link.download = record.id + '.json'; provenance.append(link); host.append(provenance);
}
