// ============================================================
//  Inventory Module — Stock · Batches & Expiry · Suppliers · Categories
//  Online only. The server owns every quantity: the UI never computes
//  stock itself, it only posts movements and re-reads the result.
// ============================================================

const INVENTORY_WRITE_OFF_TYPES = ["expired", "damaged", "loss", "supplier_return"];
const INVENTORY_UNITS = ["piece", "box", "pack", "carpule", "syringe", "capsule", "tube", "bottle", "vial", "ml", "g", "pair", "roll", "kit"];

let inventoryItemsRequest = 0;
let inventorySearchTimer = null;
let inventoryRestoreSearchFocus = false;

// ──────────────── FORMAT HELPERS ─────────────────────────

function invQty(value) {
    const number = Number(value);
    if (value === null || value === undefined || !Number.isFinite(number)) return "—";
    return number.toLocaleString(currentLanguage === "ar" ? "ar" : "en", { maximumFractionDigits: 3 });
}

// Standard units are stored as English keys and translated for display; custom units show as typed.
function invUnit(unit) {
    return INVENTORY_UNITS.includes(unit) ? t(`invUnit_${unit}`) : (unit || "");
}

function invSignedQty(value) {
    const number = Number(value);
    return `${number > 0 ? "+" : ""}${invQty(value)}`;
}

function invDateTime(iso) {
    if (!iso) return "—";
    return new Date(iso).toLocaleString(currentLanguage === "ar" ? "ar" : "en", {
        year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
}

function invStockBadge(status) {
    if (status === "out") return `<span class="badge badge-danger">${t("invStatusOut")}</span>`;
    if (status === "low") return `<span class="badge badge-amber">${t("invStatusLow")}</span>`;
    return `<span class="badge badge-green">${t("invStatusOk")}</span>`;
}

function invExpiryBadge(status) {
    if (status === "expired") return `<span class="badge badge-danger">${t("expired")}</span>`;
    if (status === "expiring_soon") return `<span class="badge badge-amber">${t("expiringSoon")}</span>`;
    return "";
}

function invMovementLabel(type) {
    return t(`invMv_${type}`);
}

function invMovementBadge(type) {
    const tone = {
        opening: "badge-gray",
        stock_in: "badge-green",
        return: "badge-blue",
        usage: "badge-purple",
        adjustment: "badge-amber",
    }[type] || "badge-danger";
    return `<span class="badge ${tone}">${esc(invMovementLabel(type))}</span>`;
}

function invOption(value, label, selected) {
    return `<option value="${esc(value)}" ${String(selected) === String(value) ? "selected" : ""}>${esc(label)}</option>`;
}

function invActiveCategories(currentId = null) {
    return state.inventoryCategories.filter((c) => c.is_active || c.id === currentId);
}

function invActiveSuppliers(currentId = null) {
    const options = state.inventorySupplierOptions.slice();
    if (currentId && !options.some((s) => s.id === currentId)) {
        const current = state.inventorySuppliers.find((s) => s.id === currentId);
        if (current) options.push(current);
    }
    return options;
}

function invCloseModal() {
    $("#modal").classList.remove("show");
}

function invErrorText(error) {
    return error?.message || t("errorOccurred");
}

// ──────────────── DATA LOADING ────────────────────────────

function resetInventoryState() {
    state.inventoryDashboard = null;
    state.inventoryItems = [];
    state.inventoryMovements = [];
    state.inventoryBatches = [];
    state.inventoryCategories = [];
    state.inventorySuppliers = [];
    state.inventorySupplierOptions = [];
    state.inventoryLookupsLoaded = false;
    state.inventoryError = "";
}

async function loadInventoryLookups() {
    const [categories, suppliers] = await Promise.all([
        window.AERODENT_API.get("/api/inventory/categories"),
        window.AERODENT_API.get("/api/inventory/suppliers?active=true"),
    ]);
    state.inventoryCategories = categories?.data || [];
    state.inventorySupplierOptions = suppliers?.data || [];
    state.inventoryLookupsLoaded = true;
}

async function loadInventoryDashboard() {
    const response = await window.AERODENT_API.get("/api/inventory/dashboard");
    state.inventoryDashboard = response?.data || null;
}

async function loadInventoryItems() {
    const requestId = ++inventoryItemsRequest;
    const params = new URLSearchParams({
        page: String(state.inventoryPage),
        per_page: String(state.inventoryPerPage),
    });
    const search = state.inventorySearch.trim();
    if (search) params.set("q", search);
    for (const [key, value] of Object.entries(state.inventoryFilters)) {
        if (value !== "all" || key === "active") params.set(key, value);
    }
    const response = await window.AERODENT_API.get(`/api/inventory/items?${params}`);
    if (requestId !== inventoryItemsRequest) return false;
    state.inventoryItems = response?.data || [];
    state.inventoryTotal = response?.meta?.total || 0;
    state.inventoryPages = response?.meta?.pages || 0;
    return true;
}

async function loadInventoryMovements() {
    const params = new URLSearchParams({
        page: String(state.inventoryMovementPage),
        per_page: "25",
        type: state.inventoryMovementType,
    });
    const response = await window.AERODENT_API.get(`/api/inventory/movements?${params}`);
    state.inventoryMovements = response?.data || [];
    state.inventoryMovementTotal = response?.meta?.total || 0;
    state.inventoryMovementPages = response?.meta?.pages || 0;
}

async function loadInventoryBatches() {
    const params = new URLSearchParams({ expiry_status: state.inventoryBatchStatus, per_page: "100" });
    const response = await window.AERODENT_API.get(`/api/inventory/batches?${params}`);
    state.inventoryBatches = response?.data || [];
}

async function loadInventorySuppliers() {
    const params = new URLSearchParams();
    const search = state.inventorySupplierSearch.trim();
    if (search) params.set("q", search);
    const response = await window.AERODENT_API.get(`/api/inventory/suppliers?${params}`);
    state.inventorySuppliers = response?.data || [];
}

async function loadInventoryView() {
    if (!window.AERODENT_ONLINE || !hasPermission("inventory.read")) return;
    state.inventoryLoading = true;
    state.inventoryError = "";
    try {
        const tasks = [];
        if (!state.inventoryLookupsLoaded || ["categories", "suppliers"].includes(state.inventoryTab)) {
            tasks.push(loadInventoryLookups());
        }
        const tab = state.inventoryTab;
        if (tab === "overview") tasks.push(loadInventoryDashboard());
        else if (tab === "items") tasks.push(loadInventoryItems());
        else if (tab === "movements") tasks.push(loadInventoryMovements());
        else if (tab === "expiry") tasks.push(loadInventoryBatches());
        else if (tab === "suppliers") tasks.push(loadInventorySuppliers());
        await Promise.all(tasks);
    } catch (error) {
        state.inventoryError = invErrorText(error);
    } finally {
        state.inventoryLoading = false;
    }
}

async function reloadInventoryView() {
    await loadInventoryView();
    if (state.view === "inventory") render();
}

async function fetchInventoryItem(itemId) {
    const response = await window.AERODENT_API.get(`/api/inventory/items/${itemId}`);
    return response?.data;
}

// ──────────────── MAIN DASHBOARD ALERT ───────────────────

async function loadInventoryAlertSummary() {
    if (!window.AERODENT_ONLINE || !hasPermission("inventory.read")) return;
    try {
        await loadInventoryDashboard();
    } catch (_) {
        // The clinical dashboard must not fail because of an inventory hiccup.
    }
}

function renderInventoryDashboardAlert() {
    const d = state.inventoryDashboard;
    if (!window.AERODENT_ONLINE || !d || !hasPermission("inventory.read")) return "";
    const stockIssues = (d.low_stock || 0) + (d.out_of_stock || 0);
    const expiryIssues = (d.expiring_soon || 0) + (d.expired || 0);
    if (!stockIssues && !expiryIssues) return "";
    const parts = [];
    if (d.out_of_stock) parts.push(`${d.out_of_stock} ${t("invStatusOut")}`);
    if (d.low_stock) parts.push(`${d.low_stock} ${t("invStatusLow")}`);
    if (d.expired) parts.push(`${d.expired} ${t("expired")}`);
    if (d.expiring_soon) parts.push(`${d.expiring_soon} ${t("expiringSoon")}`);
    return `<div class="inv-alert-banner">
      📦 <strong>${t("invNeedsAttention")}</strong> — ${esc(parts.join(" · "))}
      <button class="hr-alert-link" data-inv-open-view="overview">${t("reviewNow")}</button>
    </div>`;
}

// ──────────────── TABS: OVERVIEW ─────────────────────────

function invKpi(value, label, tone, filter) {
    const attrs = filter ? `data-inv-kpi="${esc(filter)}" role="button" tabindex="0"` : "";
    return `<div class="inv-kpi inv-kpi--${tone} ${filter ? "inv-kpi--link" : ""}" ${attrs}>
      <div class="inv-kpi-number">${value}</div>
      <div class="inv-kpi-label">${label}</div>
    </div>`;
}

function renderInventoryOverview() {
    const d = state.inventoryDashboard;
    if (!d) return `<p class="muted">${t("loading")}</p>`;

    const kpis = `
    <div class="inv-kpi-grid">
      ${invKpi(d.total_items, t("invTotalItems"), "total", "all")}
      ${invKpi(d.in_stock, t("invStatusOk"), "ok", "stock:ok")}
      ${invKpi(d.low_stock, t("invStatusLow"), "low", "stock:low")}
      ${invKpi(d.out_of_stock, t("invStatusOut"), "out", "stock:out")}
      ${invKpi(d.expiring_soon, t("expiringSoon"), "low", "expiry:expiring_soon")}
      ${invKpi(d.expired, t("expired"), "out", "expiry:expired")}
    </div>`;

    const valueNote = d.items_without_cost
        ? `${t("invValueNote")} ${d.items_without_cost} ${t("invItemsWithoutCost")}`
        : t("invValueNote");
    const moneyCards = `
    <div class="inv-money-row">
      <div class="card inv-money-card">
        <span class="stat-label">${t("invEstimatedValue")}</span>
        <div class="stat-value">${money(d.estimated_value)}</div>
        <small class="muted">${esc(valueNote)}</small>
      </div>
      <div class="card inv-money-card">
        <span class="stat-label">${t("invReceipts30")}</span>
        <div class="stat-value">${money(d.receipts_last_30_days?.cost)}</div>
        <small class="muted">${d.receipts_last_30_days?.count || 0} ${t("invReceiptsCount")}</small>
      </div>
    </div>`;

    const canReceive = hasPermission("inventory.stock_in");
    const attention = (d.attention_items || []).map((item) => `
      <div class="inv-list-row">
        <button class="inv-link" data-inv-item="${item.id}">${esc(item.name)}</button>
        <span class="muted">${invQty(item.usable_quantity)} / ${t("invMin")} ${invQty(item.minimum_quantity)} ${esc(invUnit(item.unit))}</span>
        ${invStockBadge(item.stock_status)}
        ${canReceive ? `<button class="button button-ghost btn-xs" data-inv-action="receive" data-inv-id="${item.id}">＋ ${t("invReceive")}</button>` : ""}
      </div>`).join("") || `<p class="muted inv-empty">✓ ${t("invNoAttention")}</p>`;

    const expiring = (d.expiring_batches || []).map((batch) => `
      <div class="inv-list-row">
        <button class="inv-link" data-inv-item="${batch.item_id}">${esc(batch.item_name)}</button>
        <span class="muted">${esc(batch.batch_number || t("invNoBatchNumber"))} · ${invQty(batch.quantity)} ${esc(invUnit(batch.item_unit))}</span>
        <span><bdi dir="ltr">${esc(batch.expiry_date)}</bdi> ${invExpiryBadge(batch.expiry_status)}</span>
      </div>`).join("") || `<p class="muted inv-empty">✓ ${t("invNoExpiring")} (${d.expiry_warning_days} ${t("invDays")})</p>`;

    return `
      ${kpis}
      ${moneyCards}
      <div class="inv-two-col">
        <section class="card">
          <div class="card-heading"><h3>⚠️ ${t("invNeedsAttention")}</h3>
            <button class="button button-ghost btn-xs" data-inv-kpi="stock:attention">${t("invViewAll")}</button></div>
          ${attention}
        </section>
        <section class="card">
          <div class="card-heading"><h3>⏳ ${t("invExpiringBatches")}</h3>
            <button class="button button-ghost btn-xs" data-inv-tab="expiry">${t("invViewAll")}</button></div>
          ${expiring}
        </section>
      </div>
      <section class="card">
        <div class="card-heading"><h3>🔄 ${t("invRecentMovements")}</h3>
          <button class="button button-ghost btn-xs" data-inv-tab="movements">${t("invViewAll")}</button></div>
        ${renderInventoryMovementTable(d.recent_movements || [], { showItem: true })}
      </section>`;
}

// ──────────────── TABS: ITEMS ────────────────────────────

function renderInventoryItemsToolbar() {
    const f = state.inventoryFilters;
    const categories = state.inventoryCategories
        .map((c) => invOption(c.id, c.is_active ? c.name : `${c.name} (${t("inactive")})`, f.category_id)).join("");
    const suppliers = state.inventorySupplierOptions
        .map((s) => invOption(s.id, s.name, f.supplier_id)).join("");
    return `
    <div class="inv-toolbar">
      <input type="search" id="invSearch" class="inv-search" value="${esc(state.inventorySearch)}"
        placeholder="${t("invSearchPlaceholder")}" autocomplete="off">
      <select data-inv-filter="category_id">${invOption("all", t("invAllCategories"), f.category_id)}${categories}</select>
      <select data-inv-filter="supplier_id">${invOption("all", t("invAllSuppliers"), f.supplier_id)}${suppliers}</select>
      <select data-inv-filter="stock_status">
        ${invOption("all", t("invAnyStock"), f.stock_status)}
        ${invOption("attention", t("invNeedsAttention"), f.stock_status)}
        ${invOption("ok", t("invStatusOk"), f.stock_status)}
        ${invOption("low", t("invStatusLow"), f.stock_status)}
        ${invOption("out", t("invStatusOut"), f.stock_status)}
      </select>
      <select data-inv-filter="expiry_status">
        ${invOption("all", t("invAnyExpiry"), f.expiry_status)}
        ${invOption("attention", t("invExpiryAttention"), f.expiry_status)}
        ${invOption("expiring_soon", t("expiringSoon"), f.expiry_status)}
        ${invOption("expired", t("expired"), f.expiry_status)}
      </select>
      <select data-inv-filter="active">
        ${invOption("true", t("active"), f.active)}
        ${invOption("false", t("inactive"), f.active)}
        ${invOption("all", t("invAll"), f.active)}
      </select>
      <select data-inv-filter="sort">
        ${invOption("name", t("invSortName"), f.sort)}
        ${invOption("quantity", t("invSortQuantity"), f.sort)}
        ${invOption("expiry", t("invSortExpiry"), f.sort)}
        ${invOption("updated", t("invSortUpdated"), f.sort)}
      </select>
      ${hasPermission("inventory.create") ? `<button class="button button-primary" data-inv-action="new-item">＋ ${t("invNewItem")}</button>` : ""}
    </div>`;
}

function renderInventoryItemRow(item) {
    const canIn = hasPermission("inventory.stock_in") && item.is_active;
    const canOut = hasPermission("inventory.stock_out") && item.is_active;
    const codes = [item.sku, item.barcode].filter(Boolean).map((code) => `<bdi dir="ltr">${esc(code)}</bdi>`).join(" · ");
    const expiredNote = Number(item.expired_quantity) > 0
        ? `<small class="inv-danger-text">${invQty(item.expired_quantity)} ${t("expired")}</small>`
        : "";
    return `<tr class="${item.is_active ? "" : "inv-row-inactive"}">
      <td>
        <button class="inv-link" data-inv-item="${item.id}">${esc(item.name)}</button>
        ${codes ? `<small class="muted inv-codes">${codes}</small>` : ""}
      </td>
      <td>${esc(item.category_name || "—")}</td>
      <td>${esc(item.location || "—")}</td>
      <td class="inv-num"><b>${invQty(item.usable_quantity)}</b> <span class="muted">${esc(invUnit(item.unit))}</span>${expiredNote}</td>
      <td class="inv-num">${invQty(item.minimum_quantity)}</td>
      <td>${item.is_active ? invStockBadge(item.stock_status) : `<span class="badge badge-gray">${t("inactive")}</span>`}</td>
      <td>${item.nearest_expiry ? `<bdi dir="ltr">${esc(item.nearest_expiry)}</bdi> ${invExpiryBadge(item.expiry_status)}` : "—"}</td>
      <td class="action-cell inv-actions">
        ${canOut ? `<button class="button button-ghost btn-xs" data-inv-action="use" data-inv-id="${item.id}">− ${t("invUse")}</button>` : ""}
        ${canIn ? `<button class="button button-ghost btn-xs" data-inv-action="receive" data-inv-id="${item.id}">＋ ${t("invReceive")}</button>` : ""}
      </td>
    </tr>`;
}

function renderInventoryItems() {
    const rows = state.inventoryItems.map(renderInventoryItemRow).join("")
        || `<tr><td colspan="8" class="tc-empty">${state.inventoryLoading ? t("loading") : state.inventorySearch || Object.values(state.inventoryFilters).some((v) => v !== "all" && v !== "true" && v !== "name")
            ? t("invNoMatches") : t("invNoItems")}</td></tr>`;
    const pagination = state.inventoryPages > 1
        ? `<div class="patient-pagination">
            <button class="button button-ghost" data-inv-page="previous" ${state.inventoryPage <= 1 ? "disabled" : ""}>${t("previous")}</button>
            <span>${state.inventoryPage} / ${state.inventoryPages}</span>
            <button class="button button-ghost" data-inv-page="next" ${state.inventoryPage >= state.inventoryPages ? "disabled" : ""}>${t("next")}</button>
          </div>`
        : "";
    return `
      ${renderInventoryItemsToolbar()}
      <div class="card">
        <div class="table-wrap">
          <table class="hr-table inv-table">
            <thead><tr>
              <th>${t("invItem")}</th><th>${t("invCategory")}</th><th>${t("location")}</th>
              <th>${t("invOnHand")}</th><th>${t("invMin")}</th><th>${t("status")}</th>
              <th>${t("invNearestExpiry")}</th><th></th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>
        <div class="inv-table-foot">
          <small class="muted">${state.inventoryTotal} ${t("invItems")}</small>
          ${pagination}
        </div>
      </div>`;
}

// ──────────────── TABS: MOVEMENTS ────────────────────────

function renderInventoryMovementTable(movements, { showItem = false } = {}) {
    if (!movements.length) return `<p class="muted inv-empty">${t("invNoMovements")}</p>`;
    const rows = movements.map((m) => {
        const details = [
            m.reason ? esc(m.reason) : "",
            m.reference ? `<span class="muted">${t("invRef")}: ${esc(m.reference)}</span>` : "",
            m.reference_type ? `<span class="muted">${esc(t(m.reference_type))} #${esc(m.reference_id)}</span>` : "",
            m.supplier_name ? `<span class="muted">🚚 ${esc(m.supplier_name)}</span>` : "",
            m.notes ? `<span class="muted">${esc(m.notes)}</span>` : "",
        ].filter(Boolean).join("<br>");
        const tone = Number(m.quantity) > 0 ? "inv-in" : "inv-out";
        return `<tr>
          <td class="inv-nowrap">${invDateTime(m.created_at)}</td>
          ${showItem ? `<td><button class="inv-link" data-inv-item="${m.item_id}">${esc(m.item_name)}</button></td>` : ""}
          <td>${invMovementBadge(m.type)}</td>
          <td class="inv-num ${tone}"><b>${invSignedQty(m.quantity)}</b></td>
          <td class="inv-num">${invQty(m.quantity_after)}</td>
          <td>${m.batch_number ? `<bdi dir="ltr">${esc(m.batch_number)}</bdi>` : "—"}</td>
          <td>${m.unit_cost ? money(m.unit_cost) : "—"}</td>
          <td class="inv-details">${details || "—"}</td>
          <td>${esc(m.created_by_name || "—")}</td>
        </tr>`;
    }).join("");
    return `<div class="table-wrap"><table class="hr-table inv-table">
      <thead><tr>
        <th>${t("date")}</th>${showItem ? `<th>${t("invItem")}</th>` : ""}<th>${t("type")}</th>
        <th>${t("invChange")}</th><th>${t("invBalance")}</th><th>${t("invBatch")}</th>
        <th>${t("invUnitCost")}</th><th>${t("invDetails")}</th><th>${t("invBy")}</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`;
}

function renderInventoryMovements() {
    const types = ["stock_in", "usage", "return", "adjustment", "expired", "damaged", "loss", "supplier_return", "opening"];
    const typeOptions = types.map((type) => invOption(type, invMovementLabel(type), state.inventoryMovementType)).join("");
    const pagination = state.inventoryMovementPages > 1
        ? `<div class="patient-pagination">
            <button class="button button-ghost" data-inv-mv-page="previous" ${state.inventoryMovementPage <= 1 ? "disabled" : ""}>${t("previous")}</button>
            <span>${state.inventoryMovementPage} / ${state.inventoryMovementPages}</span>
            <button class="button button-ghost" data-inv-mv-page="next" ${state.inventoryMovementPage >= state.inventoryMovementPages ? "disabled" : ""}>${t("next")}</button>
          </div>`
        : "";
    return `
      <div class="inv-toolbar">
        <select id="invMovementType">
          ${invOption("all", t("invAllMovements"), state.inventoryMovementType)}
          ${invOption("write_off", t("invWriteOffs"), state.inventoryMovementType)}
          ${typeOptions}
        </select>
        <small class="muted">${t("invLedgerNote")}</small>
      </div>
      <div class="card">
        ${renderInventoryMovementTable(state.inventoryMovements, { showItem: true })}
        <div class="inv-table-foot">
          <small class="muted">${state.inventoryMovementTotal} ${t("invMovements")}</small>
          ${pagination}
        </div>
      </div>`;
}

// ──────────────── TABS: EXPIRY ───────────────────────────

function renderInventoryExpiry() {
    const canWriteOff = hasPermission("inventory.adjust");
    const rows = state.inventoryBatches.map((b) => {
        const days = b.days_to_expiry;
        const daysLabel = days === null ? "—" : days < 0 ? `${Math.abs(days)} ${t("invDaysAgo")}` : `${days} ${t("invDays")}`;
        return `<tr>
          <td><button class="inv-link" data-inv-item="${b.item_id}">${esc(b.item_name)}</button></td>
          <td>${b.batch_number ? `<bdi dir="ltr">${esc(b.batch_number)}</bdi>` : "—"}</td>
          <td class="inv-num">${invQty(b.quantity)} <span class="muted">${esc(invUnit(b.item_unit))}</span></td>
          <td><bdi dir="ltr">${esc(b.expiry_date || "—")}</bdi></td>
          <td>${daysLabel}</td>
          <td>${invExpiryBadge(b.expiry_status) || `<span class="badge badge-green">${t("valid")}</span>`}</td>
          <td class="action-cell">${canWriteOff && b.expiry_status === "expired"
            ? `<button class="button btn-danger-ghost btn-xs" data-inv-action="writeoff" data-inv-id="${b.item_id}" data-inv-batch="${b.id}">${t("invWriteOff")}</button>`
            : ""}</td>
        </tr>`;
    }).join("") || `<tr><td colspan="7" class="tc-empty">✓ ${t("invNoExpiring")}</td></tr>`;

    const days = state.inventoryDashboard?.expiry_warning_days;
    return `
      <div class="inv-toolbar">
        <select id="invBatchStatus">
          ${invOption("attention", t("invExpiryAttention"), state.inventoryBatchStatus)}
          ${invOption("expired", t("expired"), state.inventoryBatchStatus)}
          ${invOption("expiring_soon", t("expiringSoon"), state.inventoryBatchStatus)}
          ${invOption("all", t("invAllBatches"), state.inventoryBatchStatus)}
        </select>
        <small class="muted">${t("invExpiryNote")}${days ? ` (${days} ${t("invDays")})` : ""}</small>
      </div>
      <div class="card">
        <div class="table-wrap"><table class="hr-table inv-table">
          <thead><tr>
            <th>${t("invItem")}</th><th>${t("invBatch")}</th><th>${t("invQuantity")}</th>
            <th>${t("expiryDate")}</th><th>${t("daysRemaining")}</th><th>${t("status")}</th><th></th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table></div>
      </div>`;
}

// ──────────────── TABS: SUPPLIERS ────────────────────────

function renderInventorySuppliers() {
    const canManage = hasPermission("inventory.manage_suppliers");
    const rows = state.inventorySuppliers.map((s) => `<tr class="${s.is_active ? "" : "inv-row-inactive"}">
        <td><b>${esc(s.name)}</b>${s.notes ? `<small class="muted inv-codes">${esc(s.notes)}</small>` : ""}</td>
        <td>${esc(s.contact_person || "—")}</td>
        <td><bdi dir="ltr">${esc(s.phone || "—")}</bdi></td>
        <td><bdi dir="ltr">${esc(s.email || "—")}</bdi></td>
        <td class="inv-num">${s.item_count ?? 0}</td>
        <td>${s.is_active ? `<span class="badge badge-green">${t("active")}</span>` : `<span class="badge badge-gray">${t("inactive")}</span>`}</td>
        <td class="action-cell inv-actions">${canManage ? `
          <button class="button button-ghost btn-xs" data-inv-supplier-edit="${s.id}">✏️</button>
          <button class="button button-ghost btn-xs" data-inv-supplier-toggle="${s.id}">${s.is_active ? t("invDeactivate") : t("invActivate")}</button>
          <button class="button btn-danger-ghost btn-xs" data-inv-supplier-delete="${s.id}" title="${t("delete")}">🗑</button>` : ""}
        </td>
      </tr>`).join("") || `<tr><td colspan="7" class="tc-empty">${t("invNoSuppliers")}</td></tr>`;
    return `
      <div class="inv-toolbar">
        <input type="search" id="invSupplierSearch" class="inv-search" value="${esc(state.inventorySupplierSearch)}"
          placeholder="${t("invSupplierSearch")}" autocomplete="off">
        ${canManage ? `<button class="button button-primary" data-inv-action="new-supplier">＋ ${t("invNewSupplier")}</button>` : ""}
      </div>
      <div class="card"><div class="table-wrap"><table class="hr-table inv-table">
        <thead><tr>
          <th>${t("invSupplier")}</th><th>${t("invContactPerson")}</th><th>${t("phone")}</th>
          <th>${t("email")}</th><th>${t("invItems")}</th><th>${t("status")}</th><th></th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table></div></div>`;
}

// ──────────────── TABS: CATEGORIES ───────────────────────

function renderInventoryCategories() {
    const canManage = hasPermission("inventory.manage_categories");
    const rows = state.inventoryCategories.map((c) => `<tr class="${c.is_active ? "" : "inv-row-inactive"}">
        <td><b>${esc(c.name)}</b></td>
        <td class="inv-num">${c.item_count ?? 0}</td>
        <td>${c.is_active ? `<span class="badge badge-green">${t("active")}</span>` : `<span class="badge badge-gray">${t("inactive")}</span>`}</td>
        <td class="action-cell inv-actions">${canManage ? `
          <button class="button button-ghost btn-xs" data-inv-category-edit="${c.id}">✏️</button>
          <button class="button button-ghost btn-xs" data-inv-category-toggle="${c.id}">${c.is_active ? t("invDeactivate") : t("invActivate")}</button>
          ${c.item_count ? "" : `<button class="button btn-danger-ghost btn-xs" data-inv-category-delete="${c.id}" title="${t("delete")}">🗑</button>`}` : ""}
        </td>
      </tr>`).join("");
    const empty = !state.inventoryCategories.length
        ? `<div class="dashboard-empty-state">
            <span class="empty-state-icon">🗂️</span>
            <p class="muted">${t("invNoCategories")}</p>
            ${canManage ? `<button class="button button-primary" data-inv-action="default-categories">✨ ${t("invAddDefaultCategories")}</button>` : ""}
          </div>`
        : "";
    return `
      <div class="inv-toolbar">
        <small class="muted">${t("invCategoryNote")}</small>
        ${canManage ? `<button class="button button-primary" data-inv-action="new-category">＋ ${t("invNewCategory")}</button>` : ""}
      </div>
      <div class="card">
        ${empty || `<div class="table-wrap"><table class="hr-table inv-table">
          <thead><tr><th>${t("invCategory")}</th><th>${t("invItems")}</th><th>${t("status")}</th><th></th></tr></thead>
          <tbody>${rows}</tbody>
        </table></div>`}
      </div>`;
}

// ──────────────── MAIN RENDER ────────────────────────────

function renderInventory() {
    if (!window.AERODENT_ONLINE) {
        return `<div class="card"><p class="muted">${t("invOnlineOnly")}</p></div>`;
    }
    if (!hasPermission("inventory.read")) {
        return `<div class="card"><p class="muted">${t("invNoAccess")}</p></div>`;
    }

    const tab = state.inventoryTab;
    const tabs = [
        ["overview", "📊 " + t("invOverview")],
        ["items", "📦 " + t("invItems")],
        ["movements", "🔄 " + t("invMovements")],
        ["expiry", "⏳ " + t("invExpiry")],
        ["suppliers", "🚚 " + t("invSuppliers")],
        ["categories", "🗂️ " + t("invCategories")],
    ];
    const tabHtml = tabs.map(([key, label]) =>
        `<button class="inv-tab${tab === key ? " inv-tab--active" : ""}" data-inv-tab="${key}">${label}</button>`,
    ).join("");

    let content;
    if (state.inventoryError) {
        content = `<div class="login-error">${esc(state.inventoryError)}
          <button class="button button-ghost btn-xs" data-inv-action="retry">${t("invRetry")}</button></div>`;
    } else if (state.inventoryLoading && tab !== "items") {
        content = `<p class="muted">${t("loading")}</p>`;
    } else if (tab === "items") content = renderInventoryItems();
    else if (tab === "movements") content = renderInventoryMovements();
    else if (tab === "expiry") content = renderInventoryExpiry();
    else if (tab === "suppliers") content = renderInventorySuppliers();
    else if (tab === "categories") content = renderInventoryCategories();
    else content = renderInventoryOverview();

    const quick = [];
    if (hasPermission("inventory.stock_in")) quick.push(`<button class="button button-ghost" data-inv-action="pick-receive">＋ ${t("invReceiveStock")}</button>`);
    if (hasPermission("inventory.stock_out")) quick.push(`<button class="button button-ghost" data-inv-action="pick-use">− ${t("invRecordUsage")}</button>`);

    return `
    <div class="inv-container">
      <div class="inv-tabs-row">
        <div class="inv-tabs">${tabHtml}</div>
        <div class="inv-quick">${quick.join("")}</div>
      </div>
      <div class="inv-content">${content}</div>
    </div>`;
}

// ──────────────── ITEM DETAIL ────────────────────────────

function renderInventoryItemDetail(item) {
    const info = [
        [t("invCategory"), esc(item.category_name || "—")],
        [t("invSupplier"), esc(item.supplier_name || "—")],
        [t("location"), esc(item.location || "—")],
        [t("invUnit"), esc(invUnit(item.unit))],
        ["SKU", item.sku ? `<bdi dir="ltr">${esc(item.sku)}</bdi>` : "—"],
        [t("invBarcode"), item.barcode ? `<bdi dir="ltr">${esc(item.barcode)}</bdi>` : "—"],
        [t("invCostPerUnit"), item.cost_per_unit ? money(item.cost_per_unit) : "—"],
        [t("invEstimatedValue"), item.estimated_value ? money(item.estimated_value) : "—"],
    ].map(([label, value]) => `<div><span class="stat-label">${label}</span><div>${value}</div></div>`).join("");

    const canIn = hasPermission("inventory.stock_in") && item.is_active;
    const canOut = hasPermission("inventory.stock_out") && item.is_active;
    const canAdjust = hasPermission("inventory.adjust") && item.is_active;
    const actions = [
        canIn ? `<button class="button button-primary" data-inv-detail-action="receive">＋ ${t("invReceive")}</button>` : "",
        canOut ? `<button class="button button-ghost" data-inv-detail-action="use">− ${t("invUse")}</button>` : "",
        canOut ? `<button class="button button-ghost" data-inv-detail-action="return">↩ ${t("invReturn")}</button>` : "",
        canAdjust ? `<button class="button button-ghost" data-inv-detail-action="adjust">⚖️ ${t("invAdjust")}</button>` : "",
        canAdjust ? `<button class="button btn-danger-ghost" data-inv-detail-action="writeoff">🗑 ${t("invWriteOff")}</button>` : "",
        hasPermission("inventory.update") ? `<button class="button button-ghost" data-inv-detail-action="edit">✏️ ${t("edit")}</button>` : "",
        item.is_active && hasPermission("inventory.delete") ? `<button class="button button-ghost" data-inv-detail-action="deactivate">${t("invDeactivate")}</button>` : "",
        !item.is_active && hasPermission("inventory.update") ? `<button class="button button-ghost" data-inv-detail-action="reactivate">${t("invActivate")}</button>` : "",
    ].join("");

    const batches = item.track_batches
        ? `<h3 class="inv-section-title">🏷️ ${t("invBatches")}</h3>
           ${item.batches.length ? `<div class="table-wrap"><table class="hr-table inv-table">
             <thead><tr><th>${t("invBatch")}</th><th>${t("invQuantity")}</th><th>${t("expiryDate")}</th><th>${t("status")}</th><th>${t("invUnitCost")}</th><th>${t("invSupplier")}</th></tr></thead>
             <tbody>${item.batches.map((b) => `<tr>
               <td>${b.batch_number ? `<bdi dir="ltr">${esc(b.batch_number)}</bdi>` : `<span class="muted">${t("invNoBatchNumber")}</span>`}</td>
               <td class="inv-num">${invQty(b.quantity)}</td>
               <td><bdi dir="ltr">${esc(b.expiry_date || "—")}</bdi></td>
               <td>${invExpiryBadge(b.expiry_status) || (b.expiry_date ? `<span class="badge badge-green">${t("valid")}</span>` : "—")}</td>
               <td>${b.unit_cost ? money(b.unit_cost) : "—"}</td>
               <td>${esc(b.supplier_name || "—")}</td>
             </tr>`).join("")}</tbody></table></div>`
            : `<p class="muted">${t("invNoBatches")}</p>`}`
        : "";

    const expiredLine = Number(item.expired_quantity) > 0
        ? `<div class="alert-banner">⚠ ${invQty(item.expired_quantity)} ${esc(invUnit(item.unit))} ${t("invExpiredNotUsable")}</div>`
        : "";

    return `
    <div class="inv-detail" data-inv-detail-id="${item.id}">
      <div class="inv-detail-head">
        <div>
          ${item.is_active ? invStockBadge(item.stock_status) : `<span class="badge badge-gray">${t("inactive")}</span>`}
          ${invExpiryBadge(item.expiry_status)}
          ${item.track_batches ? `<span class="badge badge-blue">${t("invBatchTracked")}</span>` : ""}
        </div>
        <div class="inv-detail-stock">
          <div><span class="stat-label">${t("invUsable")}</span><div class="stat-value">${invQty(item.usable_quantity)} <small>${esc(invUnit(item.unit))}</small></div></div>
          <div><span class="stat-label">${t("invOnHand")}</span><div class="stat-value">${invQty(item.quantity)}</div></div>
          <div><span class="stat-label">${t("invMinimum")}</span><div class="stat-value">${invQty(item.minimum_quantity)}</div></div>
        </div>
      </div>
      ${expiredLine}
      <div class="inv-detail-actions">${actions}</div>
      <div class="inv-info-grid">${info}</div>
      ${item.description ? `<p class="inv-description">${esc(item.description)}</p>` : ""}
      ${batches}
      <h3 class="inv-section-title">🔄 ${t("invRecentMovements")}</h3>
      ${renderInventoryMovementTable(item.recent_movements || [])}
    </div>`;
}

async function openInventoryItemDetail(itemId) {
    try {
        const item = await fetchInventoryItem(itemId);
        modal(esc(item.name), renderInventoryItemDetail(item));
        bindInventoryDetail(item);
    } catch (error) {
        toast(invErrorText(error));
    }
}

function bindInventoryDetail(item) {
    $$("[data-inv-detail-action]").forEach((button) => {
        button.onclick = async () => {
            const action = button.dataset.invDetailAction;
            if (action === "edit") openInventoryItemForm(item);
            else if (action === "deactivate") await deactivateInventoryItem(item);
            else if (action === "reactivate") await reactivateInventoryItem(item);
            else openInventoryMovementForm(item, action, { returnToDetail: true });
        };
    });
    $$(".inv-detail [data-inv-item]").forEach((button) => {
        button.onclick = () => openInventoryItemDetail(Number(button.dataset.invItem));
    });
}

async function deactivateInventoryItem(item) {
    if (!confirm(t("invConfirmDeactivate"))) return;
    try {
        await window.AERODENT_API.delete(`/api/inventory/items/${item.id}`);
        toast(t("invItemDeactivated"));
        await openInventoryItemDetail(item.id);
        await reloadInventoryView();
    } catch (error) {
        toast(invErrorText(error));
    }
}

async function reactivateInventoryItem(item) {
    try {
        await window.AERODENT_API.patch(`/api/inventory/items/${item.id}`, { is_active: true });
        toast(t("invItemReactivated"));
        await openInventoryItemDetail(item.id);
        await reloadInventoryView();
    } catch (error) {
        toast(invErrorText(error));
    }
}

// ──────────────── ITEM FORM ──────────────────────────────

function openInventoryItemForm(item = null) {
    const isEdit = Boolean(item);
    const categories = invActiveCategories(item?.category_id)
        .map((c) => invOption(c.id, c.name, item?.category_id ?? "")).join("");
    const suppliers = invActiveSuppliers(item?.supplier_id)
        .map((s) => invOption(s.id, s.name, item?.supplier_id ?? "")).join("");
    const unitOptions = INVENTORY_UNITS.map((u) => `<option value="${u}">`).join("");
    const trackLocked = isEdit && Number(item.quantity) !== 0;

    modal(isEdit ? t("invEditItem") : t("invNewItem"), `
    <form id="invItemForm" class="form-grid">
      <div class="field full-span"><label>${t("invName")} *</label>
        <input name="name" required maxlength="200" value="${esc(item?.name || "")}"></div>
      <div class="field"><label>${t("invCategory")}</label>
        <select name="category_id"><option value="">—</option>${categories}</select></div>
      <div class="field"><label>${t("invPreferredSupplier")}</label>
        <select name="supplier_id"><option value="">—</option>${suppliers}</select></div>
      <div class="field"><label>SKU</label>
        <input name="sku" maxlength="64" dir="ltr" value="${esc(item?.sku || "")}"></div>
      <div class="field"><label>${t("invBarcode")}</label>
        <input name="barcode" maxlength="64" dir="ltr" value="${esc(item?.barcode || "")}"></div>
      <div class="field"><label>${t("invUnit")}</label>
        <input name="unit" list="invUnitList" maxlength="30" value="${esc(item?.unit || "piece")}">
        <datalist id="invUnitList">${unitOptions}</datalist></div>
      <div class="field"><label>${t("location")}</label>
        <input name="location" maxlength="120" value="${esc(item?.location || "")}" placeholder="${t("invLocationHint")}"></div>
      <div class="field"><label>${t("invMinimum")}</label>
        <input name="minimum_quantity" type="number" min="0" step="any" value="${esc(item?.minimum_quantity ?? "0")}">
        <small class="muted">${t("invMinimumHint")}</small></div>
      <div class="field"><label>${t("invCostPerUnit")}</label>
        <input name="cost_per_unit" type="number" min="0" step="0.01" value="${esc(item?.cost_per_unit ?? "")}"></div>
      <div class="field full-span"><label class="inv-checkbox">
        <input type="checkbox" name="track_batches" ${item?.track_batches ? "checked" : ""} ${trackLocked ? "disabled" : ""}>
        ${t("invTrackBatches")}</label>
        <small class="muted">${trackLocked ? t("invTrackLocked") : t("invTrackHint")}</small></div>
      ${isEdit ? "" : `
      <div class="field"><label>${t("invInitialQuantity")}</label>
        <input name="initial_quantity" type="number" min="0" step="any" value="0"></div>
      <div class="field inv-batch-only"><label>${t("invBatchNumber")}</label>
        <input name="initial_batch_number" maxlength="64" dir="ltr"></div>
      <div class="field inv-batch-only"><label>${t("expiryDate")}</label>
        <input name="initial_expiry_date" type="date"></div>`}
      <div class="field full-span"><label>${t("invDescription")}</label>
        <textarea name="description" rows="2" maxlength="2000">${esc(item?.description || "")}</textarea></div>
      <div class="form-actions inv-form-actions">
        <button type="submit" class="button button-primary">${isEdit ? t("save") : t("add")}</button>
        <button type="button" class="button button-ghost" data-inv-cancel>${t("cancel")}</button>
      </div>
    </form>`);

    const form = $("#invItemForm");
    const trackBox = form.elements.track_batches;
    const syncBatchFields = () => $$("#invItemForm .inv-batch-only").forEach((node) => {
        node.classList.toggle("hidden", !trackBox.checked);
    });
    trackBox.onchange = syncBatchFields;
    syncBatchFields();
    $("[data-inv-cancel]").onclick = () => (isEdit ? openInventoryItemDetail(item.id) : invCloseModal());

    form.onsubmit = async (event) => {
        event.preventDefault();
        if (state.inventorySaving) return;
        const fd = new FormData(form);
        const text = (name) => (fd.get(name) || "").toString().trim();
        const payload = {
            name: text("name"),
            category_id: text("category_id") ? Number(text("category_id")) : null,
            supplier_id: text("supplier_id") ? Number(text("supplier_id")) : null,
            sku: text("sku") || null,
            barcode: text("barcode") || null,
            unit: text("unit") || "piece",
            location: text("location") || null,
            minimum_quantity: text("minimum_quantity") || "0",
            cost_per_unit: text("cost_per_unit") || null,
            description: text("description") || null,
        };
        if (!trackLocked) payload.track_batches = trackBox.checked;
        if (!isEdit) {
            payload.initial_quantity = text("initial_quantity") || "0";
            if (trackBox.checked) {
                payload.initial_batch_number = text("initial_batch_number") || null;
                payload.initial_expiry_date = text("initial_expiry_date") || null;
            }
        }
        state.inventorySaving = true;
        try {
            const response = isEdit
                ? await window.AERODENT_API.patch(`/api/inventory/items/${item.id}`, payload)
                : await window.AERODENT_API.post("/api/inventory/items", payload);
            toast(isEdit ? t("invItemSaved") : t("invItemCreated"));
            await openInventoryItemDetail(response.data.id);
            await reloadInventoryView();
        } catch (error) {
            toast(invErrorText(error));
        } finally {
            state.inventorySaving = false;
        }
    };
}

// ──────────────── STOCK MOVEMENT FORMS ───────────────────

function invBatchSelect(item, { required, allowAuto, selected, includeExpired = true }) {
    const batches = item.batches.filter((b) => includeExpired || b.expiry_status !== "expired");
    const options = batches.map((b) => {
        const label = `${b.batch_number || t("invNoBatchNumber")} · ${invQty(b.quantity)} ${invUnit(item.unit)}`
            + (b.expiry_date ? ` · ${b.expiry_date}` : "")
            + (b.expiry_status === "expired" ? ` (${t("expired")})` : "");
        return invOption(b.id, label, selected ?? "");
    }).join("");
    const first = allowAuto
        ? `<option value="">${t("invAutoFefo")}</option>`
        : `<option value="" disabled ${selected ? "" : "selected"}>${t("invSelectBatch")}</option>`;
    return `<div class="field full-span"><label>${t("invBatch")}${required ? " *" : ""}</label>
      <select name="batch_id" ${required ? "required" : ""}>${first}${options}</select></div>`;
}

function openInventoryMovementForm(item, kind, { returnToDetail = false, batchId = null } = {}) {
    const tracked = item.track_batches;
    const usableText = `${invQty(item.usable_quantity)} ${esc(invUnit(item.unit))}`;
    const common = `
      <div class="field full-span"><label>${t("notes")}</label>
        <textarea name="notes" rows="2" maxlength="2000"></textarea></div>`;
    let title;
    let fields;

    if (kind === "receive") {
        title = `${t("invReceiveStock")} — ${esc(item.name)}`;
        const suppliers = invActiveSuppliers().map((s) => invOption(s.id, s.name, item.supplier_id ?? "")).join("");
        fields = `
          <div class="field"><label>${t("invQuantity")} (${esc(invUnit(item.unit))}) *</label>
            <input name="quantity" type="number" min="0.001" step="any" required autofocus></div>
          <div class="field"><label>${t("invUnitCost")}</label>
            <input name="unit_cost" type="number" min="0" step="0.01" value="${esc(item.cost_per_unit || "")}"></div>
          <div class="field"><label>${t("invSupplier")}</label>
            <select name="supplier_id"><option value="">—</option>${suppliers}</select></div>
          <div class="field"><label>${t("invInvoiceRef")}</label>
            <input name="reference" maxlength="120" dir="auto"></div>
          ${tracked ? `
          <div class="field"><label>${t("invBatchNumber")}</label>
            <input name="batch_number" maxlength="64" dir="ltr"></div>
          <div class="field"><label>${t("expiryDate")}</label>
            <input name="expiry_date" type="date"></div>
          <p class="muted full-span inv-hint">${t("invReceiveBatchHint")}</p>` : ""}
          ${common}`;
    } else if (kind === "use") {
        title = `${t("invRecordUsage")} — ${esc(item.name)}`;
        const patient = state.selectedPatient;
        fields = `
          <p class="muted full-span inv-hint">${t("invAvailable")}: <b>${usableText}</b>${Number(item.expired_quantity) > 0 ? ` · ${t("invExpiredExcluded")}` : ""}</p>
          <div class="field"><label>${t("invQuantity")} (${esc(invUnit(item.unit))}) *</label>
            <input name="quantity" type="number" min="0.001" step="any" required autofocus></div>
          <div class="field"><label>${t("invReason")}</label>
            <input name="reason" maxlength="255" placeholder="${t("invUsageReasonHint")}"></div>
          ${tracked ? invBatchSelect(item, { required: false, allowAuto: true, includeExpired: false }) : ""}
          ${patient ? `<div class="field full-span"><label class="inv-checkbox">
            <input type="checkbox" name="link_patient" value="${patient.id}"> ${t("invLinkPatient")}: <b>${esc(patient.name)}</b></label></div>` : ""}
          ${common}`;
    } else if (kind === "return") {
        title = `${t("invReturnToStock")} — ${esc(item.name)}`;
        fields = `
          <p class="muted full-span inv-hint">${t("invReturnHint")}</p>
          <div class="field"><label>${t("invQuantity")} (${esc(invUnit(item.unit))}) *</label>
            <input name="quantity" type="number" min="0.001" step="any" required autofocus></div>
          <div class="field"><label>${t("invReason")}</label>
            <input name="reason" maxlength="255"></div>
          ${tracked ? invBatchSelect(item, { required: true, allowAuto: false }) : ""}
          ${common}`;
    } else if (kind === "adjust") {
        title = `${t("invAdjustStock")} — ${esc(item.name)}`;
        fields = `
          <p class="muted full-span inv-hint">${t("invAdjustHint")}</p>
          ${tracked ? invBatchSelect(item, { required: true, allowAuto: false, selected: batchId }) : `
          <p class="full-span">${t("invCurrentlyRecorded")}: <b>${invQty(item.quantity)} ${esc(invUnit(item.unit))}</b></p>`}
          <div class="field"><label>${t("invCountedQuantity")} *</label>
            <input name="new_quantity" type="number" min="0" step="any" required value="${tracked ? "" : esc(item.quantity)}"></div>
          <div class="field"><label>${t("invReason")} *</label>
            <input name="reason" maxlength="255" required placeholder="${t("invAdjustReasonHint")}"></div>
          ${common}`;
    } else {
        title = `${t("invWriteOff")} — ${esc(item.name)}`;
        const selectedBatch = item.batches.find((b) => b.id === batchId);
        const defaultType = selectedBatch?.expiry_status === "expired" || (!selectedBatch && Number(item.expired_quantity) > 0)
            ? "expired"
            : "damaged";
        const typeOptions = INVENTORY_WRITE_OFF_TYPES
            .map((type) => invOption(type, invMovementLabel(type), defaultType))
            .join("");
        fields = `
          <p class="muted full-span inv-hint">${t("invWriteOffHint")}</p>
          <div class="field"><label>${t("type")} *</label><select name="type">${typeOptions}</select></div>
          <div class="field"><label>${t("invQuantity")} (${esc(invUnit(item.unit))}) *</label>
            <input name="quantity" type="number" min="0.001" step="any" required value="${esc(selectedBatch?.quantity || "")}"></div>
          ${tracked ? invBatchSelect(item, { required: false, allowAuto: true, selected: batchId }) : ""}
          <div class="field full-span"><label>${t("invReason")}</label>
            <input name="reason" maxlength="255"></div>
          ${common}`;
    }

    modal(title, `
      <form id="invMovementForm" class="form-grid">
        ${fields}
        <div class="form-actions inv-form-actions">
          <button type="submit" class="button button-primary">${t("save")}</button>
          <button type="button" class="button button-ghost" data-inv-cancel>${t("cancel")}</button>
        </div>
      </form>`);

    const form = $("#invMovementForm");
    $("[data-inv-cancel]").onclick = () => (returnToDetail ? openInventoryItemDetail(item.id) : invCloseModal());
    form.querySelector("input[autofocus]")?.focus();

    form.onsubmit = async (event) => {
        event.preventDefault();
        if (state.inventorySaving) return;
        const fd = new FormData(form);
        const text = (name) => (fd.get(name) || "").toString().trim();
        const payload = {
            reason: text("reason") || undefined,
            reference: text("reference") || undefined,
            notes: text("notes") || undefined,
        };
        if (text("batch_id")) payload.batch_id = Number(text("batch_id"));
        if (kind === "receive") {
            Object.assign(payload, {
                type: "stock_in",
                quantity: text("quantity"),
                unit_cost: text("unit_cost") || undefined,
                supplier_id: text("supplier_id") ? Number(text("supplier_id")) : undefined,
                batch_number: text("batch_number") || undefined,
                expiry_date: text("expiry_date") || undefined,
            });
        } else if (kind === "use") {
            payload.type = "usage";
            payload.quantity = text("quantity");
            if (text("link_patient")) {
                payload.reference_type = "patient";
                payload.reference_id = Number(text("link_patient"));
            }
        } else if (kind === "return") {
            payload.type = "return";
            payload.quantity = text("quantity");
        } else if (kind === "adjust") {
            payload.type = "adjustment";
            payload.new_quantity = text("new_quantity");
        } else {
            payload.type = text("type");
            payload.quantity = text("quantity");
        }

        state.inventorySaving = true;
        try {
            const response = await window.AERODENT_API.post(`/api/inventory/items/${item.id}/movements`, payload);
            const updated = response.data.item;
            toast(`${t("invStockUpdated")}: ${invQty(updated.quantity)} ${invUnit(updated.unit)}`);
            if (returnToDetail) await openInventoryItemDetail(item.id);
            else invCloseModal();
            await reloadInventoryView();
        } catch (error) {
            toast(invErrorText(error));
        } finally {
            state.inventorySaving = false;
        }
    };
}

async function openInventoryMovementFormFor(itemId, kind, options = {}) {
    try {
        const item = await fetchInventoryItem(itemId);
        openInventoryMovementForm(item, kind, options);
    } catch (error) {
        toast(invErrorText(error));
    }
}

// Quick "Receive stock" / "Record usage" from the header: search an item first.
function openInventoryItemPicker(kind) {
    modal(kind === "receive" ? t("invReceiveStock") : t("invRecordUsage"), `
      <div class="field">
        <label>${t("invFindItem")}</label>
        <input id="invPickerSearch" type="search" autocomplete="off" placeholder="${t("invSearchPlaceholder")}">
      </div>
      <div id="invPickerResults" class="inv-picker-results"><p class="muted">${t("invTypeToSearch")}</p></div>`);
    const input = $("#invPickerSearch");
    let timer = null;
    let requestId = 0;
    const search = async () => {
        const current = ++requestId;
        const params = new URLSearchParams({ q: input.value.trim(), per_page: "10", active: "true" });
        try {
            const response = await window.AERODENT_API.get(`/api/inventory/items?${params}`);
            if (current !== requestId) return;
            const items = response?.data || [];
            $("#invPickerResults").innerHTML = items.map((item) => `
              <button type="button" class="inv-picker-row" data-inv-pick="${item.id}">
                <span><b>${esc(item.name)}</b> ${item.sku ? `<small class="muted" dir="ltr">${esc(item.sku)}</small>` : ""}</span>
                <span class="muted">${invQty(item.usable_quantity)} ${esc(invUnit(item.unit))} ${invStockBadge(item.stock_status)}</span>
              </button>`).join("") || `<p class="muted">${t("invNoMatches")}</p>`;
            $$("[data-inv-pick]").forEach((button) => {
                button.onclick = () => openInventoryMovementFormFor(Number(button.dataset.invPick), kind);
            });
        } catch (error) {
            if (current === requestId) $("#invPickerResults").innerHTML = `<p class="login-error">${esc(invErrorText(error))}</p>`;
        }
    };
    input.oninput = () => {
        clearTimeout(timer);
        timer = setTimeout(search, 250);
    };
    input.focus();
    search();
}

// ──────────────── SUPPLIER & CATEGORY FORMS ──────────────

function openInventorySupplierForm(supplier = null) {
    const isEdit = Boolean(supplier);
    modal(isEdit ? t("invEditSupplier") : t("invNewSupplier"), `
    <form id="invSupplierForm" class="form-grid">
      <div class="field full-span"><label>${t("invName")} *</label>
        <input name="name" required maxlength="150" value="${esc(supplier?.name || "")}"></div>
      <div class="field"><label>${t("invContactPerson")}</label>
        <input name="contact_person" maxlength="150" value="${esc(supplier?.contact_person || "")}"></div>
      <div class="field"><label>${t("phone")}</label>
        <input name="phone" maxlength="50" dir="ltr" value="${esc(supplier?.phone || "")}"></div>
      <div class="field full-span"><label>${t("email")}</label>
        <input name="email" type="email" maxlength="255" dir="ltr" value="${esc(supplier?.email || "")}"></div>
      <div class="field full-span"><label>${t("address")}</label>
        <input name="address" maxlength="1000" value="${esc(supplier?.address || "")}"></div>
      <div class="field full-span"><label>${t("notes")}</label>
        <textarea name="notes" rows="2" maxlength="2000">${esc(supplier?.notes || "")}</textarea></div>
      <div class="form-actions inv-form-actions">
        <button type="submit" class="button button-primary">${isEdit ? t("save") : t("add")}</button>
        <button type="button" class="button button-ghost" data-inv-cancel>${t("cancel")}</button>
      </div>
    </form>`);
    $("[data-inv-cancel]").onclick = invCloseModal;
    const form = $("#invSupplierForm");
    form.onsubmit = async (event) => {
        event.preventDefault();
        const fd = new FormData(form);
        const payload = {};
        for (const field of ["name", "contact_person", "phone", "email", "address", "notes"]) {
            payload[field] = (fd.get(field) || "").toString().trim() || null;
        }
        try {
            if (isEdit) await window.AERODENT_API.patch(`/api/inventory/suppliers/${supplier.id}`, payload);
            else await window.AERODENT_API.post("/api/inventory/suppliers", payload);
            invCloseModal();
            toast(t("invSupplierSaved"));
            await reloadInventoryView();
        } catch (error) {
            toast(invErrorText(error));
        }
    };
}

function openInventoryCategoryForm(category = null) {
    modal(category ? t("invRenameCategory") : t("invNewCategory"), `
    <form id="invCategoryForm" class="form-grid">
      <div class="field full-span"><label>${t("invName")} *</label>
        <input name="name" required maxlength="100" value="${esc(category?.name || "")}" autofocus></div>
      <div class="form-actions inv-form-actions">
        <button type="submit" class="button button-primary">${category ? t("save") : t("add")}</button>
        <button type="button" class="button button-ghost" data-inv-cancel>${t("cancel")}</button>
      </div>
    </form>`);
    $("[data-inv-cancel]").onclick = invCloseModal;
    const form = $("#invCategoryForm");
    form.onsubmit = async (event) => {
        event.preventDefault();
        const name = (new FormData(form).get("name") || "").toString().trim();
        try {
            if (category) await window.AERODENT_API.patch(`/api/inventory/categories/${category.id}`, { name });
            else await window.AERODENT_API.post("/api/inventory/categories", { name });
            invCloseModal();
            toast(t("invCategorySaved"));
            await reloadInventoryView();
        } catch (error) {
            toast(invErrorText(error));
        }
    };
}

// ──────────────── EVENTS ─────────────────────────────────

async function switchInventoryTab(tab) {
    state.inventoryTab = tab;
    state.inventoryLoading = true;
    render();
    await reloadInventoryView();
}

async function applyInventoryItemFilters() {
    state.inventoryPage = 1;
    state.inventoryLoading = true;
    try {
        const current = await loadInventoryItems();
        if (!current) return;
        state.inventoryError = "";
    } catch (error) {
        state.inventoryError = invErrorText(error);
    } finally {
        state.inventoryLoading = false;
    }
    if (state.view === "inventory") render();
}

function bindInventoryEvents() {
    // Main-dashboard alert banner shortcut (rendered outside the inventory view)
    $$("[data-inv-open-view]").forEach((button) => {
        button.onclick = async () => {
            state.view = "inventory";
            state.inventoryTab = button.dataset.invOpenView;
            render();
            await reloadInventoryView();
        };
    });

    if (state.view !== "inventory") return;

    $$("#view [data-inv-tab]").forEach((button) => {
        button.onclick = () => switchInventoryTab(button.dataset.invTab);
    });

    $$("#view [data-inv-item]").forEach((button) => {
        button.onclick = () => openInventoryItemDetail(Number(button.dataset.invItem));
    });

    $$("#view [data-inv-kpi]").forEach((node) => {
        const activate = async () => {
            const [kind, value] = node.dataset.invKpi.split(":");
            state.inventoryFilters = {
                ...state.inventoryFilters,
                stock_status: kind === "stock" ? value : "all",
                expiry_status: kind === "expiry" ? value : "all",
                active: "true",
            };
            state.inventorySearch = "";
            state.inventoryPage = 1;
            await switchInventoryTab("items");
        };
        node.onclick = activate;
        node.onkeydown = (event) => {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                activate();
            }
        };
    });

    $$("#view [data-inv-action]").forEach((button) => {
        button.onclick = async () => {
            const action = button.dataset.invAction;
            const itemId = Number(button.dataset.invId);
            if (action === "new-item") openInventoryItemForm();
            else if (action === "receive" || action === "use") openInventoryMovementFormFor(itemId, action);
            else if (action === "writeoff") {
                openInventoryMovementFormFor(itemId, "writeoff", { batchId: Number(button.dataset.invBatch) || null });
            } else if (action === "pick-receive") openInventoryItemPicker("receive");
            else if (action === "pick-use") openInventoryItemPicker("use");
            else if (action === "new-supplier") openInventorySupplierForm();
            else if (action === "new-category") openInventoryCategoryForm();
            else if (action === "retry") await reloadInventoryView();
            else if (action === "default-categories") {
                try {
                    await window.AERODENT_API.post("/api/inventory/categories/defaults", { language: currentLanguage });
                    await reloadInventoryView();
                } catch (error) {
                    toast(invErrorText(error));
                }
            }
        };
    });

    // Items: search + filters + pagination (all server-side)
    const search = $("#invSearch");
    if (search) {
        if (inventoryRestoreSearchFocus) {
            search.focus();
            search.setSelectionRange(search.value.length, search.value.length);
            inventoryRestoreSearchFocus = false;
        }
        search.oninput = () => {
            state.inventorySearch = search.value;
            clearTimeout(inventorySearchTimer);
            inventorySearchTimer = setTimeout(async () => {
                inventoryRestoreSearchFocus = document.activeElement === search;
                await applyInventoryItemFilters();
            }, 300);
        };
    }
    $$("#view [data-inv-filter]").forEach((select) => {
        select.onchange = () => {
            state.inventoryFilters = { ...state.inventoryFilters, [select.dataset.invFilter]: select.value };
            applyInventoryItemFilters();
        };
    });
    $$("#view [data-inv-page]").forEach((button) => {
        button.onclick = async () => {
            if (button.dataset.invPage === "previous" && state.inventoryPage > 1) state.inventoryPage -= 1;
            if (button.dataset.invPage === "next" && state.inventoryPage < state.inventoryPages) state.inventoryPage += 1;
            await loadInventoryItems().catch((error) => { state.inventoryError = invErrorText(error); });
            render();
        };
    });

    // Movements
    const movementType = $("#invMovementType");
    if (movementType) {
        movementType.onchange = async () => {
            state.inventoryMovementType = movementType.value;
            state.inventoryMovementPage = 1;
            await reloadInventoryView();
        };
    }
    $$("#view [data-inv-mv-page]").forEach((button) => {
        button.onclick = async () => {
            if (button.dataset.invMvPage === "previous" && state.inventoryMovementPage > 1) state.inventoryMovementPage -= 1;
            if (button.dataset.invMvPage === "next" && state.inventoryMovementPage < state.inventoryMovementPages) state.inventoryMovementPage += 1;
            await reloadInventoryView();
        };
    });

    // Expiry
    const batchStatus = $("#invBatchStatus");
    if (batchStatus) {
        batchStatus.onchange = async () => {
            state.inventoryBatchStatus = batchStatus.value;
            await reloadInventoryView();
        };
    }

    // Suppliers
    const supplierSearch = $("#invSupplierSearch");
    if (supplierSearch) {
        if (inventoryRestoreSearchFocus) {
            supplierSearch.focus();
            supplierSearch.setSelectionRange(supplierSearch.value.length, supplierSearch.value.length);
            inventoryRestoreSearchFocus = false;
        }
        supplierSearch.oninput = () => {
            state.inventorySupplierSearch = supplierSearch.value;
            clearTimeout(inventorySearchTimer);
            inventorySearchTimer = setTimeout(async () => {
                inventoryRestoreSearchFocus = document.activeElement === supplierSearch;
                await loadInventorySuppliers().catch((error) => { state.inventoryError = invErrorText(error); });
                render();
            }, 300);
        };
    }
    $$("#view [data-inv-supplier-edit]").forEach((button) => {
        button.onclick = () => {
            const supplier = state.inventorySuppliers.find((s) => s.id === Number(button.dataset.invSupplierEdit));
            if (supplier) openInventorySupplierForm(supplier);
        };
    });
    $$("#view [data-inv-supplier-toggle]").forEach((button) => {
        button.onclick = async () => {
            const supplier = state.inventorySuppliers.find((s) => s.id === Number(button.dataset.invSupplierToggle));
            if (!supplier) return;
            try {
                await window.AERODENT_API.patch(`/api/inventory/suppliers/${supplier.id}`, { is_active: !supplier.is_active });
                await reloadInventoryView();
            } catch (error) {
                toast(invErrorText(error));
            }
        };
    });
    $$("#view [data-inv-supplier-delete]").forEach((button) => {
        button.onclick = async () => {
            if (!confirm(t("confirmDelete"))) return;
            try {
                await window.AERODENT_API.delete(`/api/inventory/suppliers/${button.dataset.invSupplierDelete}`);
                await reloadInventoryView();
            } catch (error) {
                toast(invErrorText(error));
            }
        };
    });

    // Categories
    $$("#view [data-inv-category-edit]").forEach((button) => {
        button.onclick = () => {
            const category = state.inventoryCategories.find((c) => c.id === Number(button.dataset.invCategoryEdit));
            if (category) openInventoryCategoryForm(category);
        };
    });
    $$("#view [data-inv-category-toggle]").forEach((button) => {
        button.onclick = async () => {
            const category = state.inventoryCategories.find((c) => c.id === Number(button.dataset.invCategoryToggle));
            if (!category) return;
            try {
                await window.AERODENT_API.patch(`/api/inventory/categories/${category.id}`, { is_active: !category.is_active });
                await reloadInventoryView();
            } catch (error) {
                toast(invErrorText(error));
            }
        };
    });
    $$("#view [data-inv-category-delete]").forEach((button) => {
        button.onclick = async () => {
            if (!confirm(t("confirmDelete"))) return;
            try {
                await window.AERODENT_API.delete(`/api/inventory/categories/${button.dataset.invCategoryDelete}`);
                await reloadInventoryView();
            } catch (error) {
                toast(invErrorText(error));
            }
        };
    });
}
