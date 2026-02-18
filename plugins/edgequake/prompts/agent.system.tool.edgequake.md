## Tool: edgequake

Knowledge graph-powered RAG system. Use for deep research, document ingestion, and entity exploration.

### When to use
- User asks a knowledge-intensive question and you need richer context than conversation history provides
- User wants to store documents or knowledge for future retrieval
- User asks about relationships between concepts, people, or entities
- User wants to explore what is in the knowledge base

### Methods

**query** — Search the knowledge graph
- query: (required) the question to ask
- mode: (optional) naive|local|global|hybrid|mix|bypass (default: hybrid)

**upload** — Ingest a document into the knowledge graph
- content: (required) text content to ingest
- title: (optional) document title

**list_documents** — List ingested documents
- page: (optional) page number
- limit: (optional) results per page

**search_entities** — Find entities in the knowledge graph
- keyword: (required) search term

**graph_stats** — Get knowledge graph overview statistics

**health** — Check EdgeQuake connection status
