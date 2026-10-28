// Diagnostic projection of the retained prestate.ValidateConfig domain.
// The native importer remains authoritative and checks it again before replay.
const forks = [
  'homesteadBlock', 'eip150Block', 'eip155Block', 'eip158Block',
  'byzantiumBlock', 'constantinopleBlock', 'petersburgBlock', 'istanbulBlock',
  'muirGlacierBlock', 'berlinBlock', 'londonBlock',
];
const allowed = new Set([
  'chainId', ...forks, 'daoForkBlock', 'daoForkSupport', 'eip150Hash', 'clique', 'arbitrum',
]);

export function configProfile(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value))
    return ['INCORRECT_CHAIN_CONFIG_OR_ARBOS_VERSION'];
  const blockers = Object.keys(value).filter(k => !allowed.has(k))
    .map(k => 'UNSUPPORTED_CHAIN_CONFIG_FIELD: ' + k);
  const arb = value.arbitrum;
  if (value.chainId !== 4663 || value.daoForkBlock != null ||
      !arb || arb.EnableArbOS !== true)
    blockers.push('INCORRECT_CHAIN_CONFIG_OR_ARBOS_VERSION');
  if (forks.some(k => value[k] !== 0))
    blockers.push('UNSUPPORTED_FORK_SCHEDULE');
  if (!arb || arb.MaxCodeSize !== 98304 || arb.MaxInitCodeSize !== 196608 ||
      (arb.AllowDebugPrecompiles ?? false) !== false ||
      (arb.DataAvailabilityCommittee ?? false) !== false ||
      (arb.GenesisBlockNum ?? 0) !== 0 || arb.InitialArbOSVersion !== 51)
    blockers.push('UNSUPPORTED_NITRO_CHAIN_CONFIG');
  return blockers;
}
