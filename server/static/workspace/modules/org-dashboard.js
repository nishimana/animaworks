/**
 * Organization dashboard view for the Workspace.
 * Alternative 2D view to the 3D office with 3-column layout:
 * - Left (250px): Organization tree
 * - Center (flex): Anima status cards
 * - Right (300px): Real-time activity feed
 */
import { createLogger } from "../../shared/logger.js";
import { escapeHtml, smartTimestamp } from "./utils.js";
import { animaHashColor } from "../../shared/avatar-utils.js";

const logger = createLogger("org-dashboard");

let _container = null;
let _statusCards = new Map();
let _activityFeed = null;
const MAX_ACTIVITY_ITEMS = 50;

// ── Org Tree Builder ──────────────────────

function buildOrgTree(animas) {
  const nodeMap = new Map();
  for (const p of animas) {
    nodeMap.set(p.name, {
      name: p.name,
      role: p.role || null,
      supervisor: p.supervisor || null,
      status: p.status,
      children: [],
    });
  }
  const roots = [];
  for (const node of nodeMap.values()) {
    if (node.role === "commander" || !node.supervisor || !nodeMap.has(node.supervisor)) {
      roots.push(node);
    } else {
      const parent = nodeMap.get(node.supervisor);
      if (parent) parent.children.push(node);
    }
  }
  return roots.length ? roots : [...nodeMap.values()];
}

function renderTreeNode(node, depth = 0) {
  const statusDot = getStatusDotClass(node.status);
  let html = `<div class="org-tree-node" data-name="${escapeHtml(node.name)}" style="padding-left:${depth * 16}px">
    <span class="org-tree-dot ${statusDot}"></span>
    <span class="org-tree-name">${escapeHtml(node.name)}</span>
    ${node.role ? `<span class="org-tree-role">${escapeHtml(node.role)}</span>` : ""}
  </div>`;
  for (const child of node.children) {
    html += renderTreeNode(child, depth + 1);
  }
  return html;
}

function getStatusDotClass(status) {
  if (!status) return "dot-unknown";
  const s = typeof status === "object" ? (status.state || status.status || "") : String(status);
  const lower = s.toLowerCase();
  if (lower === "idle") return "dot-idle";
  if (lower === "thinking" || lower === "working") return "dot-active";
  if (lower === "sleeping" || lower === "stopped" || lower === "not_found") return "dot-sleeping";
  if (lower.includes("error")) return "dot-error";
  if (lower.includes("bootstrap")) return "dot-bootstrap";
  return "dot-unknown";
}

// ── Status Cards ──────────────────────

function renderStatusCard(anima) {
  const s = typeof anima.status === "object" ? anima.status : { state: anima.status || "unknown" };
  const state = (s.state || s.status || "unknown").toLowerCase();
  const dotClass = getStatusDotClass(anima.status);
  const initial = (anima.name || "?")[0].toUpperCase();
  const color = animaHashColor(anima.name);

  return `<div class="org-status-card" data-name="${escapeHtml(anima.name)}" id="orgCard_${escapeHtml(anima.name)}">
    <div class="org-card-header">
      <div class="org-card-avatar" style="background:${color}">${initial}</div>
      <div class="org-card-info">
        <div class="org-card-name">${escapeHtml(anima.name)}</div>
        <div class="org-card-role">${escapeHtml(anima.role || "")}</div>
      </div>
      <span class="org-card-dot ${dotClass}"></span>
    </div>
    <div class="org-card-status">${escapeHtml(state)}</div>
    <div class="org-card-task" id="orgTask_${escapeHtml(anima.name)}"></div>
    <div class="org-card-time" id="orgTime_${escapeHtml(anima.name)}"></div>
  </div>`;
}

// animaHashColor imported from shared/avatar-utils.js

// ── Activity Feed ──────────────────────

function renderActivityItem(item) {
  const time = smartTimestamp(item.ts || item.timestamp || "");
  const icon = item.type === "error" ? "⚠️" : "📌";
  const from = item.from ? `<span class="org-activity-from">${escapeHtml(item.from)}</span>` : "";
  const summary = escapeHtml(item.summary || item.content || item.type || "");
  return `<div class="org-activity-item">
    <span class="org-activity-icon">${icon}</span>
    <div class="org-activity-body">
      ${from}
      <span class="org-activity-text">${summary}</span>
    </div>
    <span class="org-activity-time">${time}</span>
  </div>`;
}

function addActivityItem(item) {
  if (!_activityFeed) return;
  const div = document.createElement("div");
  div.innerHTML = renderActivityItem(item);
  const el = div.firstElementChild;
  _activityFeed.prepend(el);
  // Trim old items
  while (_activityFeed.children.length > MAX_ACTIVITY_ITEMS) {
    _activityFeed.removeChild(_activityFeed.lastElementChild);
  }
}

// ── Main API ──────────────────────

export async function initOrgDashboard(container, animas) {
  _container = container;
  _statusCards.clear();

  const roots = buildOrgTree(animas);

  // Build tree HTML
  let treeHtml = "";
  for (const root of roots) {
    treeHtml += renderTreeNode(root);
  }

  // Build cards HTML
  let cardsHtml = "";
  for (const p of animas) {
    cardsHtml += renderStatusCard(p);
  }

  container.innerHTML = `
    <div class="org-dashboard">
      <div class="org-col-left">
        <div class="org-section-title">組織ツリー</div>
        <div class="org-tree">${treeHtml}</div>
      </div>
      <div class="org-col-center">
        <div class="org-section-title">ステータス</div>
        <div class="org-cards">${cardsHtml}</div>
      </div>
      <div class="org-col-right">
        <div class="org-section-title">アクティビティ</div>
        <div class="org-activity-feed" id="orgActivityFeed"></div>
      </div>
    </div>
  `;

  _activityFeed = document.getElementById("orgActivityFeed");

  // Cache card elements
  for (const p of animas) {
    _statusCards.set(p.name, document.getElementById(`orgCard_${p.name}`));
  }

  // Load recent activity
  try {
    const resp = await fetch("/api/activity/recent?hours=12&limit=20");
    if (resp.ok) {
      const data = await resp.json();
      const items = Array.isArray(data) ? data : (data.events || []);
      for (const item of items.reverse()) {
        addActivityItem(item);
      }
    }
  } catch (err) {
    logger.warn("Failed to load activity", { error: err.message });
  }

  // Tree node click → highlight card
  container.addEventListener("click", (e) => {
    const node = e.target.closest(".org-tree-node");
    if (!node) return;
    const name = node.dataset.name;
    const card = _statusCards.get(name);
    if (card) {
      card.scrollIntoView({ behavior: "smooth", block: "center" });
      card.classList.add("org-card-highlight");
      setTimeout(() => card.classList.remove("org-card-highlight"), 1500);
    }
  });

  logger.info("Org dashboard initialized", { animaCount: animas.length });
}

export function disposeOrgDashboard() {
  if (_container) {
    _container.innerHTML = "";
  }
  _statusCards.clear();
  _activityFeed = null;
  _container = null;
}

export function updateAnimaStatus(name, status) {
  const card = _statusCards.get(name);
  if (!card) return;

  const state = typeof status === "object" ? (status.state || status.status || "unknown") : String(status);
  const dotClass = getStatusDotClass(status);

  const dot = card.querySelector(".org-card-dot");
  if (dot) {
    dot.className = `org-card-dot ${dotClass}`;
  }

  const statusEl = card.querySelector(".org-card-status");
  if (statusEl) {
    statusEl.textContent = state.toLowerCase();
  }
}

export { addActivityItem };
