/**
 * a0_swarm — inline @-mention routing for the main chat input.
 *
 * Recognises leading @-token prefixes and routes the remainder of the
 * message to the matched subagent(s) via /plugins/a0_swarm/swarm_send_message
 * instead of (or in addition to) sending to the orchestrator.
 *
 * Supported targets:
 *   @SA{parent}_{slot}   exact agent_name (e.g. @SA1_3)
 *   @{slot}              numeric slot index across all currently-active
 *                        subagents (e.g. @1, @2)
 *   @all                 broadcast to every active subagent
 *   @orchestrator        explicit route to Agent Zero (also implicit if no
 *                        @-prefix is used)
 *
 * Multiple tokens may be chained: "@1 @3 please double-check this".
 * The @-prefix is consumed and stripped from the message before any
 * downstream send.
 */
import { callJsonApi } from "/js/api.js";

const SUBAGENT_API = "/plugins/a0_swarm/swarm_send_message";
const TERMINAL = new Set(["done", "failed", "cancelled"]);

function getActiveAgents() {
    try {
        const store = globalThis.Alpine?.store?.("swarmStore");
        const agents = (store && Array.isArray(store.agents)) ? store.agents : [];
        return agents.filter(a => !TERMINAL.has(a.status));
    } catch (_) {
        return [];
    }
}

function resolveToken(tok, activeAgents) {
    const lower = tok.toLowerCase();
    if (lower === "all") {
        return { kind: "subagents", names: activeAgents.map(a => a.agent_name) };
    }
    if (lower === "orchestrator") {
        return { kind: "orchestrator" };
    }
    if (/^\d+$/.test(tok)) {
        const slot = parseInt(tok, 10);
        const matches = activeAgents
            .map(a => {
                const m = /^SA\d+_(\d+)$/.exec(a.agent_name);
                return m && parseInt(m[1], 10) === slot ? a.agent_name : null;
            })
            .filter(Boolean);
        if (matches.length) return { kind: "subagents", names: matches };
        return { kind: "unresolved", token: tok };
    }
    const exact = activeAgents.find(a => a.agent_name === tok);
    if (exact) return { kind: "subagents", names: [exact.agent_name] };
    return { kind: "unresolved", token: tok };
}

async function sendToSubagent(agentName, content) {
    try {
        await callJsonApi(SUBAGENT_API, {
            agent_name: agentName,
            content,
            unblock: false,
        });
    } catch (e) {
        console.warn("[a0_swarm] swarm_send_message failed for", agentName, e);
    }
}

function clearChatInput() {
    try { globalThis.Alpine?.store?.("inputStore")?.reset?.(); } catch (_) {}
    try {
        const el = document.getElementById("chat-input");
        if (el) {
            el.value = "";
            el.style.height = "auto";
        }
    } catch (_) {}
}

export default async function swarmMentions(sendCtx) {
    if (!sendCtx || typeof sendCtx.message !== "string") return;
    const original = sendCtx.message;

    // Find consecutive @<word> tokens at the very start of the message.
    // A token ends at whitespace; subsequent tokens may be space-separated.
    // Allows letters, digits, underscore, dash.
    const headMatch = original.match(/^((?:\s*@[A-Za-z0-9_-]+)+)\s*/);
    if (!headMatch) return;

    const head = headMatch[1];
    const remainder = original.slice(headMatch[0].length);
    const tokens = head.trim().split(/\s+/).map(t => t.slice(1));   // drop leading @

    const activeAgents = getActiveAgents();

    const subagentSet = new Set();
    let routeToOrchestrator = false;
    const unresolved = [];

    for (const tok of tokens) {
        const r = resolveToken(tok, activeAgents);
        if (r.kind === "subagents") r.names.forEach(n => subagentSet.add(n));
        else if (r.kind === "orchestrator") routeToOrchestrator = true;
        else unresolved.push(r.token);
    }

    // No recognised targets at all? Leave the message untouched so the
    // user's literal "@something" goes through to the orchestrator as plain
    // text. This avoids hijacking unrelated text that happens to start
    // with an @.
    if (subagentSet.size === 0 && !routeToOrchestrator) return;

    // Fan out to all matched subagents in parallel. Use the cleaned content
    // (no @-prefix). If the remainder is empty, send a single space so the
    // recipient still gets an intervention message.
    const content = remainder.trim() || "(ping)";
    await Promise.all(
        Array.from(subagentSet).map(name => sendToSubagent(name, content))
    );

    if (routeToOrchestrator) {
        // Let the rest of sendMessage() continue with the cleaned message.
        sendCtx.message = remainder;
    } else {
        // Mentions were exclusively for subagents — suppress the A0 send.
        sendCtx.cancel = true;
        clearChatInput();
    }

    if (unresolved.length && globalThis.toastFrontendWarning) {
        try {
            globalThis.toastFrontendWarning(
                `@${unresolved.join(", @")} not matched to any active subagent`,
                "Swarm mention",
            );
        } catch (_) {}
    }
}
