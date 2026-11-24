import { describe, expect, it } from 'vitest';
import { cooldownDuration, milliseconds, utc } from './format';
describe('exact display conversion', () => {
  it.each([
    ['81043432.5', '81.0434325'],
    ['-0.5', '−0.0000005'],
    ['0', '0'],
    ['1', '0.000001'],
    ['78664213', '78.664213'],
  ])('%s ns -> %s ms', (input, expected) => expect(milliseconds(input)).toBe(expected));
  it('does not coerce a large epoch into floating point', () =>
    expect(utc('1794735025245506539')).toBe('2026-11-15 09:30:25.245506539 UTC'));
  it('preserves a negative ns date', () =>
    expect(utc('-1')).toBe('1969-12-31 23:59:59.999999999 UTC'));
  it('handles unsupported calendar dates without losing the original value', () =>
    expect(utc((2n ** 100n).toString())).toBe('Outside calendar display range'));
  it('rounds cooldown display upward', () => expect(cooldownDuration('1000000001')).toBe(2));
});
