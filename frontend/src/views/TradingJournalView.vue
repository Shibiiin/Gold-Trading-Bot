<template>
  <div class="journal-page">
    <header class="hero">
      <div class="hero-copy">
        <span class="eyebrow">XAUUSD Trading</span>
        <h1>Real-Time Trade Journal</h1>
        <p>
          Live view of the journal outside MT5. This page tracks entries, exits, reasons,
          TP, SL, lot size, direction, wins, losses, and current win rate.
        </p>
      </div>
      <div class="hero-actions">
        <div class="connection-group">
          <input type="text" v-model="backendUrlInput" placeholder="Backend URL (e.g. https://...loca.lt)" class="url-input" />
          <button class="action-btn" @click="saveUrlAndRefresh">Connect</button>
        </div>
        <button class="action-btn" @click="refresh">Refresh</button>
      </div>
    </header>

    <section class="stats-grid">
      <article class="stat-card">
        <span class="label">Win Rate</span>
        <strong>{{ formatPct(stats.win_rate) }}</strong>
        <small>Closed trades only</small>
      </article>
      <article class="stat-card">
        <span class="label">Closed Trades</span>
        <strong>{{ stats.closed_trades ?? 0 }}</strong>
        <small>Finished positions</small>
      </article>
      <article class="stat-card">
        <span class="label">Wins</span>
        <strong>{{ stats.wins ?? 0 }}</strong>
        <small>Positive closes</small>
      </article>
      <article class="stat-card">
        <span class="label">Losses</span>
        <strong>{{ stats.losses ?? 0 }}</strong>
        <small>Negative closes</small>
      </article>
      <article class="stat-card">
        <span class="label">Open Trades</span>
        <strong>{{ stats.open_trades ?? 0 }}</strong>
        <small>Live positions</small>
      </article>
      <article class="stat-card">
        <span class="label">Net Profit</span>
        <strong>${{ formatNumber(stats.total_profit) }}</strong>
        <small>Closed-trade sum</small>
      </article>
    </section>

    <section class="table-panel">
      <div class="panel-header">
        <div>
          <h2>History</h2>
          <p>Auto-refreshes every 5 seconds.</p>
        </div>
        <div class="controls-row">
          <div class="filter-group">
            <button :class="['filter-btn', { active: timeFilter === 'all' }]" @click="timeFilter = 'all'">All Time</button>
            <button :class="['filter-btn', { active: timeFilter === 'month' }]" @click="timeFilter = 'month'">Last 30 Days</button>
            <button :class="['filter-btn', { active: timeFilter === 'week' }]" @click="timeFilter = 'week'">Last 7 Days</button>
          </div>
          <div class="meta">
            <span>{{ lastUpdated }}</span>
          </div>
        </div>
      </div>

      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Status</th>
              <th>Direction</th>
              <th>Entry</th>
              <th>TP / SL</th>
              <th>Lot</th>
              <th>Engine</th>
              <th>Reason</th>
              <th>Result</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="loading">
              <td colspan="9" class="empty">Loading journal...</td>
            </tr>
            <tr v-else-if="error">
              <td colspan="9" class="empty">{{ error }}</td>
            </tr>
            <tr v-else-if="filteredEntries.length === 0">
              <td colspan="9" class="empty">No trades match this filter.</td>
            </tr>
            <tr v-for="entry in filteredEntries" :key="entry.signal_id">
              <td>
                <div>{{ formatDate(entry.closed_at || entry.opened_at || entry.created_at || entry.updated_at) }}</div>
                <small>{{ entry.ticker || 'XAUUSD' }}</small>
              </td>
              <td><span :class="['pill', statusClass(entry.status)]">{{ normalizeStatus(entry.status) }}</span></td>
              <td><span :class="['pill', directionClass(entry.action)]">{{ entry.action || '-' }}</span></td>
              <td>{{ formatNumber(entry.entry_price) }}</td>
              <td>
                <div>TP {{ formatNumber(entry.tp) }}</div>
                <small>SL {{ formatNumber(entry.sl) }}</small>
              </td>
              <td>{{ formatNumber(entry.lot, 2) }}</td>
              <td>
                <div>{{ entry.strategy_name || '-' }}</div>
                <small>Score {{ formatNumber(entry.setup_score, 1) }}</small>
              </td>
              <td class="reason">{{ entry.reason || '-' }}</td>
              <td>
                <span :class="['pill', resultClass(entry)]">
                  {{ entry.result || normalizeStatus(entry.status) }}
                </span>
                <small v-if="entry.status === 'closed'">${{ formatNumber(entry.profit) }}</small>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { getTradingJournal, getBackendUrl, setBackendUrl } from '../api/trading'

const entries = ref([])
const rawStats = ref({})
const loading = ref(true)
const error = ref('')
const lastUpdated = ref('Waiting for data')
const timeFilter = ref('all') // 'all', 'week', 'month'
const backendUrlInput = ref(getBackendUrl())
let timer = null

const saveUrlAndRefresh = () => {
  if (backendUrlInput.value) {
    setBackendUrl(backendUrlInput.value)
    refresh()
  }
}

const formatNumber = (value, digits = 2) => {
  const num = Number(value ?? 0)
  return Number.isFinite(num) ? num.toFixed(digits) : '-'
}

const formatPct = (value) => `${formatNumber(value, 2)}%`

const formatDate = (value) => {
  if (!value) return '-'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString()
}

const normalizeStatus = (value) => String(value || 'pending').replaceAll('_', ' ')

const statusClass = (status) => {
  if (status === 'open') return 'status-open'
  if (status === 'closed') return 'status-closed'
  return 'status-pending'
}

const directionClass = (direction) => {
  if (direction === 'BUY') return 'dir-buy'
  if (direction === 'SELL') return 'dir-sell'
  return 'status-pending'
}

const resultClass = (entry) => {
  if (entry.result === 'win') return 'status-win'
  if (entry.result === 'loss') return 'status-loss'
  if (entry.result === 'breakeven') return 'status-pending'
  return statusClass(entry.status)
}

const filteredEntries = computed(() => {
  if (timeFilter.value === 'all') return entries.value

  const now = new Date()
  return entries.value.filter(entry => {
    const entryDate = new Date(entry.closed_at || entry.opened_at || entry.created_at || entry.updated_at)
    if (Number.isNaN(entryDate.getTime())) return true

    if (timeFilter.value === 'week') {
      const oneWeekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000)
      return entryDate >= oneWeekAgo
    }
    if (timeFilter.value === 'month') {
      const oneMonthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000)
      return entryDate >= oneMonthAgo
    }
    return true
  })
})

const stats = computed(() => {
  // Recalculate stats based on filtered entries
  const closed = filteredEntries.value.filter(e => e.status === 'closed')
  const wins = closed.filter(e => e.result === 'win').length
  const losses = closed.filter(e => e.result === 'loss').length
  const breakeven = closed.filter(e => e.result === 'breakeven').length
  const closed_count = closed.length
  const win_rate = closed_count > 0 ? (wins / closed_count) * 100 : 0
  const total_profit = closed.reduce((sum, e) => sum + (Number(e.profit) || 0), 0)
  
  const open_trades = filteredEntries.value.filter(e => e.status === 'open').length

  return {
    closed_trades: closed_count,
    wins,
    losses,
    breakeven,
    win_rate,
    total_profit,
    open_trades
  }
})

const refresh = async () => {
  try {
    if (!entries.value.length) {
      loading.value = true
    }
    error.value = ''
    const payload = await getTradingJournal(1000) // fetch more to allow client-side filtering
    entries.value = payload.entries || []
    rawStats.value = payload.stats || {}
    lastUpdated.value = `Updated ${new Date().toLocaleTimeString()}`
  } catch (err) {
    error.value = err?.message || 'Failed to load journal'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refresh()
  timer = window.setInterval(refresh, 5000)
})

onUnmounted(() => {
  if (timer) {
    window.clearInterval(timer)
  }
})
</script>

<style scoped>
.journal-page {
  min-height: 100vh;
  padding: 32px 20px 48px;
  background:
    radial-gradient(circle at top left, rgba(227, 188, 98, 0.15), transparent 26%),
    linear-gradient(180deg, #0a1218 0%, #071016 100%);
  color: #eef4f0;
}

.hero {
  max-width: 1320px;
  margin: 0 auto 24px;
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-end;
}

.eyebrow {
  display: inline-flex;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid rgba(227, 188, 98, 0.35);
  color: #e3bc62;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-size: 12px;
}

.hero-copy h1 {
  margin: 12px 0 10px;
  font-size: clamp(34px, 5vw, 56px);
  line-height: 0.95;
}

.hero-copy p {
  max-width: 760px;
  color: #9bb0ad;
  line-height: 1.55;
}

.hero-actions {
  display: flex;
  gap: 12px;
  align-items: center;
  flex-wrap: wrap;
}

.connection-group {
  display: flex;
  gap: 8px;
  align-items: center;
}

.url-input {
  background: rgba(14, 24, 30, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: #eef4f0;
  padding: 10px 14px;
  border-radius: 999px;
  min-width: 250px;
  font-size: 14px;
}

.url-input:focus {
  outline: none;
  border-color: rgba(227, 188, 98, 0.5);
}

.action-btn,
.secondary-link {
  text-decoration: none;
  border-radius: 999px;
  padding: 12px 16px;
  border: 1px solid rgba(227, 188, 98, 0.3);
  background: transparent;
  color: #e3bc62;
  cursor: pointer;
}

.stats-grid {
  max-width: 1320px;
  margin: 0 auto 24px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}

.stat-card,
.table-panel {
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(14, 24, 30, 0.9);
  border-radius: 22px;
  box-shadow: 0 24px 70px rgba(0, 0, 0, 0.28);
}

.stat-card {
  padding: 18px;
}

.label {
  color: #8ea4a1;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 12px;
}

.stat-card strong {
  display: block;
  margin-top: 10px;
  font-size: 34px;
}

.stat-card small,
.panel-header p,
small {
  color: #8ea4a1;
}

.table-panel {
  max-width: 1320px;
  margin: 0 auto;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
  padding: 18px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.panel-header h2 {
  margin: 0 0 6px;
}

.meta {
  color: #8ea4a1;
}

.controls-row {
  display: flex;
  align-items: center;
  gap: 20px;
}

.filter-group {
  display: flex;
  gap: 8px;
  background: rgba(0, 0, 0, 0.2);
  padding: 4px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.filter-btn {
  background: transparent;
  border: none;
  color: #8ea4a1;
  padding: 6px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s ease;
}

.filter-btn:hover {
  color: #fff;
}

.filter-btn.active {
  background: rgba(227, 188, 98, 0.15);
  color: #e3bc62;
  font-weight: 600;
}

.table-wrap {
  overflow-x: auto;
}

table {
  width: 100%;
  min-width: 1240px;
  border-collapse: collapse;
}

th,
td {
  padding: 14px 16px;
  text-align: left;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  vertical-align: top;
}

th {
  color: #8ea4a1;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  font-size: 12px;
}

.pill {
  display: inline-flex;
  padding: 6px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.status-open {
  background: rgba(255, 190, 92, 0.12);
  color: #ffbe5c;
}

.status-closed {
  background: rgba(120, 184, 255, 0.12);
  color: #78b8ff;
}

.status-pending {
  background: rgba(255, 255, 255, 0.08);
  color: #bdc9c7;
}

.dir-buy,
.status-win {
  background: rgba(63, 208, 161, 0.14);
  color: #3fd0a1;
}

.dir-sell,
.status-loss {
  background: rgba(255, 122, 122, 0.14);
  color: #ff7a7a;
}

.reason {
  max-width: 420px;
  line-height: 1.5;
}

.empty {
  text-align: center;
  color: #8ea4a1;
  padding: 28px;
}

@media (max-width: 768px) {
  .journal-page {
    padding: 20px 14px 28px;
  }

  .hero {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
