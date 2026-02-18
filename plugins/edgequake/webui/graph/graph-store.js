import { createStore } from "/js/AlpineStore.js";
import * as API from "/js/api.js";

const ENDPOINT = "/api/plugins/edgequake/edgequake_graph";
const NODE_RADIUS = 22;

const TYPE_COLORS = {
  TECHNOLOGY: "#7c8cff",
  ORGANIZATION: "#ff7cad",
  CONCEPT: "#7cffc5",
  PERSON: "#ffc77c",
  LOCATION: "#c77cff",
  EVENT: "#ff7c7c",
  PRODUCT: "#7cd4ff",
  DEFAULT: "#aabbcc",
};

function getTypeColor(type) {
  if (!type) return TYPE_COLORS.DEFAULT;
  return TYPE_COLORS[type.toUpperCase()] || TYPE_COLORS.DEFAULT;
}

/**
 * Transform entity API data into deduplicated nodes + edges for D3.
 */
function buildGraphData(entities) {
  const nodeMap = new Map();
  const edgeSet = new Set();
  const edges = [];

  for (const ent of entities) {
    if (!nodeMap.has(ent.name)) {
      nodeMap.set(ent.name, {
        id: ent.name,
        type: ent.entity_type || "",
        description: ent.description || "",
        color: getTypeColor(ent.entity_type),
      });
    }
    for (const rel of ent.relationships || []) {
      const key = `${rel.source}|${rel.relationship}|${rel.target}`;
      if (edgeSet.has(key)) continue;
      edgeSet.add(key);
      for (const name of [rel.source, rel.target]) {
        if (!nodeMap.has(name)) {
          nodeMap.set(name, {
            id: name, type: "", description: "", color: TYPE_COLORS.DEFAULT,
          });
        }
      }
      edges.push({
        source: rel.source,
        target: rel.target,
        label: rel.relationship || "",
      });
    }
  }
  return { nodes: Array.from(nodeMap.values()), edges };
}

// ── D3 lazy-load + non-reactive graph state ──────────────────────────
// Keeping D3 objects out of Alpine's reactive proxy avoids thousands of
// unnecessary getter/setter triggers during force simulation ticks.

let d3 = null;

const _g = {
  nodes: [],
  edges: [],
  simEdges: [],
  simulation: null,
  svg: null,
  nodesSel: null,
  linksSel: null,
  linkLabelsSel: null,
};

// D3 mutates forceLink edges: source/target become node objects after tick
function edgeNodeId(nodeOrId) {
  return typeof nodeOrId === "object" ? nodeOrId.id : nodeOrId;
}

function stopSim() {
  if (_g.simulation) {
    _g.simulation.stop();
    _g.simulation = null;
  }
}

function clearGraph() {
  stopSim();
  Object.assign(_g, {
    svg: null, nodesSel: null, linksSel: null, linkLabelsSel: null,
    nodes: [], edges: [], simEdges: [],
  });
}

// ── D3 graph renderer ────────────────────────────────────────────────

async function renderGraph(store) {
  if (!d3) {
    try {
      d3 = await import("https://cdn.jsdelivr.net/npm/d3@7/+esm");
    } catch (e) {
      store.errorMessage = "Failed to load D3 library: " + e.message;
      return;
    }
  }

  const svgEl = document.getElementById("eq-graph-svg");
  if (!svgEl) return;

  stopSim();
  const svg = d3.select(svgEl);
  svg.selectAll("*").remove();

  // Size to container
  const container = svgEl.parentElement;
  const rect = container.getBoundingClientRect();
  const width = rect.width > 100 ? rect.width : store.graphWidth;
  const height = store.graphHeight;
  store.graphWidth = width;

  svg.attr("width", width).attr("height", height)
    .attr("viewBox", `0 0 ${width} ${height}`);

  const nodes = _g.nodes;
  if (nodes.length === 0) return;

  // ── Defs: arrowhead marker ──
  svg.append("defs").append("marker")
    .attr("id", "eq-arrow")
    .attr("viewBox", "0 0 10 7")
    .attr("refX", 10).attr("refY", 3.5)
    .attr("markerWidth", 8).attr("markerHeight", 6)
    .attr("orient", "auto")
    .append("polygon")
    .attr("points", "0 0, 10 3.5, 0 7")
    .attr("fill", "rgba(170,187,204,0.5)");

  // ── Zoom + pan ──
  const g = svg.append("g");
  svg.call(
    d3.zoom().scaleExtent([0.2, 5])
      .on("zoom", (event) => g.attr("transform", event.transform)),
  );

  // Click background → deselect
  svg.on("click", (event) => {
    if (event.target === svgEl) store.selectNode(null);
  });

  // ── Force simulation ──
  _g.simEdges = _g.edges.map((e) => ({ ...e }));

  const simulation = d3.forceSimulation(nodes)
    .force(
      "link",
      d3.forceLink(_g.simEdges).id((d) => d.id).distance(120).strength(0.7),
    )
    .force("charge", d3.forceManyBody().strength(-500))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide().radius(NODE_RADIUS + 10));

  // ── Edges ──
  const link = g.append("g").selectAll("line")
    .data(_g.simEdges).join("line")
    .attr("stroke", "rgba(170,187,204,0.4)")
    .attr("stroke-width", 1).attr("opacity", 0.5)
    .attr("marker-end", "url(#eq-arrow)");

  // ── Edge labels ──
  const linkLabel = g.append("g").selectAll("text")
    .data(_g.simEdges.filter((e) => e.label)).join("text")
    .attr("text-anchor", "middle")
    .attr("fill", "rgba(170,187,204,0.6)")
    .attr("font-size", 9).attr("font-style", "italic")
    .attr("opacity", 0.5)
    .text((d) => d.label.replace(/_/g, " ").toLowerCase());

  // ── Node groups ──
  const nodeG = g.append("g").selectAll("g")
    .data(nodes).join("g")
    .style("cursor", "pointer")
    .on("click", (event, d) => {
      event.stopPropagation();
      store.selectNode(d.id);
    })
    .call(
      d3.drag()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x;
          d.fy = d.y;
        })
        .on("drag", (event, d) => {
          d.fx = event.x;
          d.fy = event.y;
        })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null;
          d.fy = null;
        }),
    );

  // Glow ring (selection indicator, initially invisible)
  nodeG.append("circle").attr("class", "eq-glow")
    .attr("r", NODE_RADIUS + 6)
    .attr("fill", "none")
    .attr("stroke", (d) => d.color)
    .attr("stroke-width", 2).attr("opacity", 0);

  // Main circle
  nodeG.append("circle").attr("class", "eq-circle")
    .attr("r", NODE_RADIUS)
    .attr("fill", (d) => d.color + "33")
    .attr("stroke", (d) => d.color)
    .attr("stroke-width", 1.5);

  // Type badge above node
  nodeG.filter((d) => d.type)
    .append("text").attr("class", "eq-badge")
    .attr("text-anchor", "middle")
    .attr("dy", -(NODE_RADIUS + 6))
    .attr("fill", (d) => d.color)
    .attr("font-size", 8).attr("opacity", 0.7)
    .text((d) => d.type);

  // Node label
  nodeG.append("text").attr("class", "eq-label")
    .attr("text-anchor", "middle").attr("dy", 4)
    .attr("fill", "#eee").attr("font-size", 11).attr("font-weight", 500)
    .text((d) => (d.id.length > 18 ? d.id.substring(0, 16) + "\u2026" : d.id));

  // ── Tick: update positions, shorten edges to stop at circle border ──
  simulation.on("tick", () => {
    link.each(function (d) {
      const dx = d.target.x - d.source.x;
      const dy = d.target.y - d.source.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const ox = (dx / dist) * NODE_RADIUS;
      const oy = (dy / dist) * NODE_RADIUS;
      d3.select(this)
        .attr("x1", d.source.x).attr("y1", d.source.y)
        .attr("x2", d.target.x - ox).attr("y2", d.target.y - oy);
    });
    linkLabel
      .attr("x", (d) => (d.source.x + d.target.x) / 2)
      .attr("y", (d) => (d.source.y + d.target.y) / 2 - 6);
    nodeG.attr("transform", (d) => `translate(${d.x},${d.y})`);
  });

  // Store refs for selection updates
  _g.simulation = simulation;
  _g.svg = svg;
  _g.nodesSel = nodeG;
  _g.linksSel = link;
  _g.linkLabelsSel = linkLabel;
}

// ── Selection highlight ──────────────────────────────────────────────

function updateSelection(store) {
  if (!_g.nodesSel || !_g.linksSel || !d3) return;
  const sel = store.selectedNode;
  const dur = 200;

  if (!sel) {
    _g.nodesSel.select(".eq-glow").transition().duration(dur).attr("opacity", 0);
    _g.nodesSel.select(".eq-circle").transition().duration(dur)
      .attr("opacity", 1).attr("stroke-width", 1.5);
    _g.nodesSel.select(".eq-label").transition().duration(dur)
      .attr("opacity", 1).attr("font-weight", 500);
    _g.nodesSel.select(".eq-badge").transition().duration(dur)
      .attr("opacity", 0.7);
    _g.linksSel.transition().duration(dur)
      .attr("stroke", "rgba(170,187,204,0.4)")
      .attr("stroke-width", 1).attr("opacity", 0.5);
    if (_g.linkLabelsSel) {
      _g.linkLabelsSel.transition().duration(dur)
        .attr("fill", "rgba(170,187,204,0.6)").attr("opacity", 0.5);
    }
    return;
  }

  const connected = new Set([sel]);
  for (const e of _g.simEdges) {
    const src = edgeNodeId(e.source);
    const tgt = edgeNodeId(e.target);
    if (src === sel) connected.add(tgt);
    if (tgt === sel) connected.add(src);
  }

  _g.nodesSel.select(".eq-glow").transition().duration(dur)
    .attr("opacity", (d) => (d.id === sel ? 0.4 : 0));
  _g.nodesSel.select(".eq-circle").transition().duration(dur)
    .attr("opacity", (d) => (connected.has(d.id) ? 1 : 0.15))
    .attr("stroke-width", (d) => (d.id === sel ? 3 : 1.5));
  _g.nodesSel.select(".eq-label").transition().duration(dur)
    .attr("opacity", (d) => (connected.has(d.id) ? 1 : 0.15))
    .attr("font-weight", (d) => (d.id === sel ? 700 : 500));
  _g.nodesSel.select(".eq-badge").transition().duration(dur)
    .attr("opacity", (d) => (connected.has(d.id) ? 0.7 : 0.1));

  function isHighlighted(d) {
    return edgeNodeId(d.source) === sel || edgeNodeId(d.target) === sel;
  }

  _g.linksSel.each(function (d) {
    const hl = isHighlighted(d);
    d3.select(this).transition().duration(dur)
      .attr("stroke", hl ? "#7c8cff" : "rgba(170,187,204,0.4)")
      .attr("stroke-width", hl ? 2 : 1)
      .attr("opacity", hl ? 0.9 : 0.1);
  });

  if (_g.linkLabelsSel) {
    _g.linkLabelsSel.each(function (d) {
      const hl = isHighlighted(d);
      d3.select(this).transition().duration(dur)
        .attr("fill", hl ? "#7c8cff" : "rgba(170,187,204,0.6)")
        .attr("opacity", hl ? 0.9 : 0.1);
    });
  }
}

// ── Store model ──────────────────────────────────────────────────────

const model = {
  entities: [],
  stats: null,

  searchKeyword: "",
  searching: false,
  hasSearched: false,
  selectedNode: null,
  loading: false,
  errorMessage: "",

  graphWidth: 800,
  graphHeight: 450,

  async open() {
    this.loading = true;
    this.errorMessage = "";
    try {
      const [statsRes, allRes] = await Promise.all([
        API.callJsonApi(ENDPOINT, { action: "stats" }),
        API.callJsonApi(ENDPOINT, { action: "load_all" }),
      ]);
      if (statsRes?.error) this.errorMessage = statsRes.error;
      else this.stats = statsRes;

      if (allRes?.error) this.errorMessage = allRes.error;
      else {
        this.entities = allRes.entities || [];
        this.hasSearched = this.entities.length > 0;
      }
    } catch (e) {
      this.errorMessage = "Failed to load graph: " + e.message;
    } finally {
      this.loading = false;
      await this._buildAndRender();
    }
  },

  async search() {
    const keyword = this.searchKeyword.trim();
    if (!keyword) return;
    this.searching = true;
    this.errorMessage = "";
    this.selectedNode = null;
    try {
      const res = await API.callJsonApi(ENDPOINT, {
        action: "search",
        keyword,
      });
      if (res?.error) {
        this.errorMessage = res.error;
        this.entities = [];
      } else {
        this.entities = res.entities || [];
      }
    } catch (e) {
      this.errorMessage = "Search failed: " + e.message;
      this.entities = [];
    } finally {
      this.searching = false;
      this.hasSearched = true;
      await this._buildAndRender();
    }
  },

  async searchByLabel(label) {
    this.searchKeyword = label;
    await this.search();
  },

  async showAll() {
    this.searchKeyword = "";
    this.selectedNode = null;
    this.loading = true;
    this.errorMessage = "";
    try {
      const res = await API.callJsonApi(ENDPOINT, { action: "load_all" });
      if (res?.error) this.errorMessage = res.error;
      else {
        this.entities = res.entities || [];
        this.hasSearched = this.entities.length > 0;
      }
    } catch (e) {
      this.errorMessage = "Failed to load: " + e.message;
    } finally {
      this.loading = false;
      await this._buildAndRender();
    }
  },

  selectNode(nodeId) {
    this.selectedNode = this.selectedNode === nodeId ? null : nodeId;
    updateSelection(this);
  },

  async _buildAndRender() {
    const { nodes, edges } = buildGraphData(this.entities);
    _g.nodes = nodes;
    _g.edges = edges;
    // Let Alpine flush DOM updates (so SVG element is visible)
    await new Promise((r) => requestAnimationFrame(r));
    await renderGraph(this);
  },

  destroy() {
    clearGraph();
    this.entities = [];
    this.stats = null;
    this.searchKeyword = "";
    this.searching = false;
    this.hasSearched = false;
    this.selectedNode = null;
    this.loading = false;
    this.errorMessage = "";
  },
};

export const store = createStore("edgequakeGraph", model);
