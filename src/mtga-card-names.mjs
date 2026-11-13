/**
 * Reference loader for the MTGA names-only artifact (Node 18+).
 *
 * The artifact is JSONL + manifest; cards.jsonl.gz is also supported.
 * No native dependencies, no runtime network access.
 */
import { readFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { join } from 'node:path';

const TAG = /<[^>]*>/g;
const ENTITIES = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' };

/** Strip Arena rich-text markup and collapse whitespace. */
export function plainText(value) {
  if (typeof value !== 'string') return '';
  return value
    .replace(TAG, '')
    .replace(/&(#x[\da-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, (match, entity) => {
      if (entity.startsWith('#')) {
        const code = entity[1].toLowerCase() === 'x'
          ? parseInt(entity.slice(2), 16)
          : parseInt(entity.slice(1), 10);
        return code >= 0 && code <= 0x10ffff ? String.fromCodePoint(code) : match;
      }
      return ENTITIES[entity.toLowerCase()] ?? match;
    })
    .replace(/\s+/g, ' ')
    .trim();
}

async function readCards(directory) {
  const plain = join(directory, 'cards.jsonl');
  if (existsSync(plain)) return readFile(plain, 'utf8');
  const gz = join(directory, 'cards.jsonl.gz');
  if (existsSync(gz)) return gunzipSync(await readFile(gz)).toString('utf8');
  throw new Error(`cards.jsonl or cards.jsonl.gz not found in ${directory}`);
}

/**
 * @param {string} directory directory containing cards.jsonl(.gz) + manifest.json
 * @returns {Promise<{manifest: object, size: number, get(id: number): object|undefined,
 *   zh(id: number): string|null, bilingual(id: number, separator?: string): string|null}>}
 */
export async function loadCardNames(directory) {
  let manifest = {};
  const manifestPath = join(directory, 'manifest.json');
  if (existsSync(manifestPath)) {
    manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
  }

  const cards = new Map();
  for (const line of (await readCards(directory)).split('\n')) {
    if (!line.trim()) continue;
    const row = JSON.parse(line);
    const id = Number(row.grp_id);
    if (!Number.isSafeInteger(id) || id <= 0) continue;
    cards.set(id, row);
  }

  return {
    manifest,
    size: cards.size,
    get: (id) => cards.get(Number(id)),
    zh: (id) => cards.get(Number(id))?.zh ?? null,
    bilingual(id, separator = ' / ') {
      const row = cards.get(Number(id));
      if (!row) return null;
      return row.zh ? `${row.zh}${separator}${row.en}` : row.en;
    },
  };
}
