## QMD Knowledge Search

You have access to a local hybrid search engine (QMD) for searching markdown notes, documentation, and knowledge bases.

**Available collections:** {{collections}}

### Tools

**qmd_search** — Search for information
- `mode`: `"query"` (best, uses AI reranking), `"search"` (fast keyword), `"vsearch"` (semantic)
- `q`: your query — plain text or structured syntax
- `collections`: optional list to restrict search
- `limit`: number of results (default 5)
- `intent`: optional context to disambiguate ambiguous queries

**qmd_get** — Retrieve document content
- `path`: file path or `#docid` (from search results)
- `pattern`: glob pattern or comma-separated list (for batch retrieval)
- `full`: true for complete content

**qmd_status** — Check index health and available collections

**qmd_manage** — Manage collections and index (requires management access)
- `action`: `collection_add`, `collection_remove`, `context_add`, `embed`, `update`

### Query Syntax (for qmd_search `q` param)

Single-line queries are auto-expanded. For best results use structured syntax:
```
lex: exact keywords "quoted phrase" -exclude
vec: natural language question about the topic
hyde: write what the answer would look like, 50-100 words
intent: disambiguation context (optional, on its own line)
```

### Search Strategy

1. **Start with `query` mode** — it auto-expands, does BM25+vector+reranking
2. **Use `lex:` when you know exact terms** — function names, error messages, version numbers
3. **Use `vec:` for concepts** — "how does X work", "why does Y happen"
4. **Combine `lex:` + `vec:`** for best recall on complex topics
5. **After search, use `qmd_get` with `#docid`** to retrieve full content of relevant documents
