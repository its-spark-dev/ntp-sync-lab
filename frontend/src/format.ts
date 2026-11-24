// Display conversion only. All NTP metrics and validation come from Python.
export function milliseconds(ns: string, signed = false): string {
  const negative = ns.startsWith('-');
  const [whole, fraction = ''] = ns.replace(/^-/, '').split('.');
  const padded = whole.padStart(7, '0');
  const integer = padded.slice(0, -6).replace(/^0+(?=\d)/, '');
  const decimal = (padded.slice(-6) + fraction).replace(/0+$/, '');
  const zero = !/[1-9]/.test(whole + fraction);
  return (
    (negative && !zero ? '−' : signed && !zero ? '+' : '') +
    integer +
    (decimal ? '.' + decimal : '')
  );
}
export function utc(ns: string): string {
  const value = BigInt(ns);
  let seconds = value / 1_000_000_000n;
  let fraction = value % 1_000_000_000n;
  if (fraction < 0) {
    seconds -= 1n;
    fraction += 1_000_000_000n;
  }
  const date = new Date(Number(seconds * 1000n));
  if (Number.isNaN(date.getTime())) return 'Outside calendar display range';
  return (
    date
      .toISOString()
      .replace('T', ' ')
      .replace(/\.\d{3}Z$/, '') +
    '.' +
    fraction.toString().padStart(9, '0') +
    ' UTC'
  );
}
export function remainingSeconds(due: number, now: number) {
  return Math.max(0, Math.ceil((due - now) / 1000));
}
export function cooldownDuration(ns: string | null): number {
  if (!ns || !/^\d+$/.test(ns)) return 0;
  return Number((BigInt(ns) + 999_999_999n) / 1_000_000_000n);
}
