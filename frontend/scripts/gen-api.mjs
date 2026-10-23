import { writeFileSync } from 'node:fs';
import openapiTS, { astToString } from 'openapi-typescript';
const url = process.env.OPENAPI_URL || `${(process.env.BACKEND_URL || 'http://127.0.0.1:8060').replace(/\/$/, '')}/openapi.json`;
const ast = await openapiTS(new URL(url));
writeFileSync(new URL('../src/lib/api/schema.d.ts', import.meta.url), astToString(ast));
