import {createStudioModel} from './studio-model.mjs';
import {createProvider} from './provider.mjs';
import {renderCatalog, renderActions, renderRecord} from './studio-view.mjs';
const $ = id => document.getElementById(id), model = createStudioModel(), provider = createProvider();
let catalog;
function filter() {
  if (!catalog) return;
  const q = $('studio-search').value.trim().toLowerCase(); let visible = 0;
  for (const block of $('studio-blocks').children) { block.hidden = !block.dataset.search.includes(q); if (!block.hidden) visible++; }
  $('search-count').textContent = visible + ' of ' + catalog.blocks.length + ' blocks';
}
function draftStatus() {
  $('draft-status').textContent = model.matchesRecord ? 'MATCHES SELECTED RECORD · saved outcome available above. New Run unavailable.' : 'EDITED DRAFT · NOT EXECUTED · No result exists for these settings. Comparison above belongs only to the selected saved record.';
}
function editor() { renderCatalog($('studio-blocks'),catalog,model,draftStatus); renderActions($('studio-actions'),model,draftStatus); filter(); draftStatus(); }
async function select(id) {
  const ticket = model.select(id); $('record-result').replaceChildren(); $('studio-blocks').replaceChildren(); $('studio-actions').replaceChildren();
  $('record-status').textContent = 'Loading saved record…'; $('record-status').classList.remove('error'); $('result-title').textContent = 'Loading recorded outcome';
  $('draft-status').textContent = 'No draft or result loaded.'; $('reset-draft').disabled = true; $('export-draft').disabled = true;
  try {
    const record = await provider.record(id); if (!model.accept(ticket, record)) return;
    $('result-title').textContent = record.label + ' · recorded result';
    $('record-status').textContent = record.id === 'burn' ? '0.3 · native + saved-result acceptance · original controller STOP' : '0.2 · full controller PASS · same worker for A/B';
    renderRecord($('record-result'),record); editor(); $('reset-draft').disabled = false; $('export-draft').disabled = false;
  } catch (error) {
    if (model.pending !== ticket) return;
    $('record-status').textContent = 'Record refused: ' + error.message; $('record-status').classList.add('error'); $('result-title').textContent = 'Result unavailable';
  }
}
$('record-select').addEventListener('change', () => select($('record-select').value));
$('studio-search').addEventListener('input', filter);
$('reset-draft').addEventListener('click', () => {model.reset();editor();});
$('export-draft').addEventListener('click', () => {
  const blob = new Blob([JSON.stringify({schema:'rhook/public-studio-draft/0.1',status:'UNEXECUTED_UNVALIDATED_DRAFT',referenceRecord:model.record.id,nativeExecutionPerformedNow:false,configuration:model.draft},null,2)+'\n'],{type:'application/json'});
  const url = URL.createObjectURL(blob), a = document.createElement('a'); a.href = url; a.download = 'rhook-studio-draft-' + model.record.id + '.json'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
try { await provider.init(); catalog = await provider.catalog(); if (catalog.schema !== 'rhook/public-studio-catalog/0.1') throw Error('Unknown catalogue version.'); await select($('record-select').value); }
catch(error) { $('record-status').textContent='Preview unavailable: '+error.message; $('record-status').classList.add('error'); $('record-select').disabled=true; }
