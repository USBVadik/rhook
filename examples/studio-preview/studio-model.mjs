// Adapted from the existing RHOOK Studio draft/revision boundary.
// A draft never becomes an execution result.
export function canonical(value) {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(key => JSON.stringify(key) + ':' + canonical(value[key])).join(',') + '}';
  return JSON.stringify(value);
}
export function parameterValue(field, raw) {
  if (raw === '') return null;
  if (field.type === 'boolean' && ['true', 'false'].includes(raw)) return raw === 'true';
  if (field.type === 'integer' && /^-?\d+$/.test(raw) && Number.isSafeInteger(Number(raw))) return Number(raw);
  return raw;
}
export function createStudioModel() {
  return {
    draft: null, record: null, revision: 0, sequence: 0, pending: null,
    select(id) { this.revision++; this.record = null; this.draft = null; return this.pending = {id, revision: this.revision, sequence: ++this.sequence}; },
    accept(ticket, record) {
      if (ticket !== this.pending || ticket.revision !== this.revision) return false;
      if (record.id !== ticket.id) throw Error('Saved result identity mismatch.');
      this.record = record; this.draft = structuredClone(record.draft); this.pending = null; return true;
    },
    edit(change) { if (!this.draft) throw Error('Load a recorded configuration first.'); change(this.draft); this.revision++; this.pending = null; },
    reset() { if (this.record) { this.draft = structuredClone(this.record.draft); this.revision++; this.pending = null; } },
    get matchesRecord() { return Boolean(this.record && canonical(this.draft) === canonical(this.record.draft)); },
    get resultForDraft() { return this.matchesRecord ? this.record : null; }
  };
}
