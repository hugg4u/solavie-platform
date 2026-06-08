import { readFileSync, existsSync } from 'fs';
import { join } from 'path';

const envPath = join(__dirname, '../.env');
if (existsSync(envPath)) {
  const envConfig = readFileSync(envPath, 'utf-8');
  for (const line of envConfig.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const parts = trimmed.split('=');
    if (parts.length >= 2) {
      const key = parts[0].trim();
      const val = parts.slice(1).join('=').trim().replace(/^['"]|['"]$/g, '');
      process.env[key] = val;
    }
  }
}
