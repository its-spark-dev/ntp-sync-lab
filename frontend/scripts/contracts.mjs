// Generate directly from the local Python app, without starting HTTP or probing NTP.
import { execFileSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import openapiTS, { astToString } from 'openapi-typescript';
const python = process.env.NTP_LAB_PYTHON || '../.venv/bin/python';
const schema = JSON.parse(
  execFileSync(
    python,
    ['-c', 'import json; from ntp_sync_lab.api.app import app; print(json.dumps(app.openapi()))'],
    { encoding: 'utf8' },
  ),
);
const result =
  '// Generated from ntp_sync_lab.api.app.openapi(); do not edit.\n' +
  astToString(await openapiTS(schema));
const path = new URL('../src/generated/api.d.ts', import.meta.url);
if (process.argv.includes('--check')) {
  if (readFileSync(path, 'utf8') !== result)
    throw new Error('API types are stale. Run npm run types:generate.');
  console.log('API types match the current Python OpenAPI schema.');
} else {
  const { mkdirSync } = await import('node:fs');
  mkdirSync(new URL('../src/generated', import.meta.url), { recursive: true });
  writeFileSync(path, result);
}
