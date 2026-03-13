/**
 * Agent Zero QMD Bridge — JSON-RPC 2.0 over stdio
 *
 * Wraps @tobilu/qmd SDK methods as line-delimited JSON-RPC requests/responses.
 * Launched by the Python client (qmd_client.py) as a subprocess.
 *
 * Protocol:
 *   stdin:  {"jsonrpc":"2.0","id":N,"method":"...","params":{...}}\n
 *   stdout: {"jsonrpc":"2.0","id":N,"result":{...}}\n  (or "error")
 *
 * Startup:
 *   1. Read QMD_DB_PATH env (or use SDK default via getDefaultDbPath())
 *   2. createStore({ dbPath })
 *   3. Write {"ready":true}\n to stdout
 *   4. Enter readline loop
 */

import readline from 'readline';
import os from 'os';
import path from 'path';
import fs from 'fs';
import { createStore } from '@tobilu/qmd';

/**
 * Compute the default QMD database path without triggering the SDK's
 * test-guard (which blocks getDefaultDbPath() unless enableProductionMode()
 * has been called or INDEX_PATH is set).
 *
 * Mirrors the SDK logic: $XDG_CACHE_HOME/qmd/index.sqlite
 *                     or ~/.cache/qmd/index.sqlite
 */
function computeDefaultDbPath() {
  const cacheDir = process.env.XDG_CACHE_HOME || path.join(os.homedir(), '.cache');
  return path.join(cacheDir, 'qmd', 'index.sqlite');
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function respond(id, result) {
  process.stdout.write(JSON.stringify({ jsonrpc: '2.0', id, result }) + '\n');
}

function respondError(id, message, code = -32000) {
  process.stdout.write(
    JSON.stringify({ jsonrpc: '2.0', id, error: { code, message } }) + '\n'
  );
}

const MANAGEMENT_METHODS = new Set([
  'collection_add',
  'collection_remove',
  'context_add',
  'context_remove',
  'update',
  'embed',
]);

// ---------------------------------------------------------------------------
// Method handlers — each receives (store, params) and returns a result value
// ---------------------------------------------------------------------------

const handlers = {
  // Ungated
  async ping(_store, _params) {
    return { ok: true };
  },

  async status(store, _params) {
    const [health, collections] = await Promise.all([
      store.getIndexHealth(),
      store.listCollections(),
    ]);
    return { health, collections };
  },

  async collection_list(store, _params) {
    return { collections: await store.listCollections() };
  },

  async context_list(store, _params) {
    const [contexts, globalContext] = await Promise.all([
      store.listContexts(),
      store.getGlobalContext(),
    ]);
    return { contexts, globalContext: globalContext ?? null };
  },

  async query(store, params) {
    // Hybrid search: BM25 + vector + optional reranking.
    // Falls back to no-rerank then BM25-only if LLM steps fail (e.g. models not
    // yet downloaded, chunk exceeds context size, or OOM).
    try {
      const results = await store.search({
        query: params.query,
        queries: params.queries,
        intent: params.intent,
        rerank: params.rerank,
        collection: params.collection,
        collections: params.collections,
        limit: params.limit,
        minScore: params.minScore,
        explain: params.explain,
      });
      return { results };
    } catch (hybridErr) {
      // Tier-2: try without reranking (still uses embeddings for vector search)
      try {
        const results = await store.search({
          query: params.query,
          rerank: false,
          collection: params.collection,
          collections: params.collections,
          limit: params.limit,
          minScore: params.minScore,
        });
        const hybridMsg = hybridErr instanceof Error ? hybridErr.message : String(hybridErr);
        return { results, warning: `Reranking skipped: ${hybridMsg}` };
      } catch (_vecErr) {
        // Tier-3: BM25-only — always works, no LLM needed
        const hybridMsg = hybridErr instanceof Error ? hybridErr.message : String(hybridErr);
        const collection = params.collection ?? params.collections?.[0];
        const ftsResults = await store.searchLex(params.query, {
          limit: params.limit,
          collection,
        });
        return { results: ftsResults, warning: `Hybrid search unavailable, showing BM25 results: ${hybridMsg}` };
      }
    }
  },

  async search(store, params) {
    // BM25 keyword search only
    const results = await store.searchLex(params.query, {
      limit: params.limit,
      collection: params.collection,
    });
    return { results };
  },

  async vsearch(store, params) {
    // Vector similarity search only
    const results = await store.searchVector(params.query, {
      limit: params.limit,
      collection: params.collection,
    });
    return { results };
  },

  async get(store, params) {
    const doc = await store.get(params.path, {
      includeBody: params.includeBody ?? true,
    });
    return { doc };
  },

  async multi_get(store, params) {
    const result = await store.multiGet(params.pattern, {
      includeBody: params.includeBody ?? true,
      maxBytes: params.maxBytes,
    });
    return result; // { docs, errors }
  },

  // Gated — management operations
  async collection_add(store, params) {
    await store.addCollection(params.name, {
      path: params.path,
      pattern: params.pattern,
      ignore: params.ignore,
    });
    return { ok: true };
  },

  async collection_remove(store, params) {
    const removed = await store.removeCollection(params.name);
    return { removed };
  },

  async context_add(store, params) {
    const ok = await store.addContext(
      params.collection,
      params.path,
      params.context
    );
    return { ok };
  },

  async context_remove(store, params) {
    const ok = await store.removeContext(params.collection, params.path);
    return { ok };
  },

  async update(store, params) {
    const result = await store.update({
      collections: params.collections,
    });
    return result; // { collections, indexed, updated, unchanged, removed, needsEmbedding }
  },

  async embed(store, params) {
    const result = await store.embed({
      force: params.force,
      model: params.model,
    });
    return result; // { docsProcessed, chunksEmbedded, errors, durationMs }
  },
};

// ---------------------------------------------------------------------------
// Main entry point
// ---------------------------------------------------------------------------

async function main() {
  const dbPath = process.env.QMD_DB_PATH || computeDefaultDbPath();
  fs.mkdirSync(path.dirname(dbPath), { recursive: true });
  const store = await createStore({ dbPath });

  const isSelfTest = process.argv.includes('--selftest');

  // Graceful shutdown handlers
  let closing = false;
  async function shutdown() {
    if (closing) return;
    closing = true;
    await store.close();
    process.exit(0);
  }

  process.on('SIGTERM', shutdown);

  if (isSelfTest) {
    // Write ready signal
    process.stdout.write(JSON.stringify({ ready: true }) + '\n');

    // Directly invoke ping handler and verify result
    try {
      const result = await handlers.ping(store, {});
      if (result.ok !== true) {
        process.stderr.write('selftest FAILED: ping returned ' + JSON.stringify(result) + '\n');
        await store.close();
        process.exit(1);
      }
      process.stderr.write('selftest PASSED\n');
      await store.close();
      process.exit(0);
    } catch (err) {
      process.stderr.write('selftest FAILED: ' + String(err) + '\n');
      await store.close();
      process.exit(1);
    }
    return;
  }

  // Normal mode: signal ready then process requests
  process.stdout.write(JSON.stringify({ ready: true }) + '\n');

  const rl = readline.createInterface({
    input: process.stdin,
    terminal: false,
  });

  rl.on('line', async (line) => {
    const trimmed = line.trim();
    if (!trimmed) return;

    let request;
    try {
      request = JSON.parse(trimmed);
    } catch (err) {
      // Parse error — no valid id, use null
      respondError(null, 'Parse error: ' + String(err), -32700);
      return;
    }

    const { id, method, params = {} } = request;

    if (!method) {
      respondError(id ?? null, 'Missing method', -32600);
      return;
    }

    const handler = handlers[method];
    if (!handler) {
      respondError(id, `Method not found: ${method}`, -32601);
      return;
    }

    // Gate management operations
    if (MANAGEMENT_METHODS.has(method) && !params._management_enabled) {
      respondError(id, 'Management operations are disabled.', -32000);
      return;
    }

    try {
      const result = await handler(store, params);
      respond(id, result);
    } catch (err) {
      respondError(id, String(err instanceof Error ? err.message : err), -32000);
    }
  });

  rl.on('close', shutdown);
}

main().catch((err) => {
  process.stderr.write('Fatal error during startup: ' + String(err) + '\n');
  process.exit(1);
});
