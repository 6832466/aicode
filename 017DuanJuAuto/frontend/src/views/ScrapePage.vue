<template>
  <div class="scrape-page">
    <div class="header-row">
      <h2 class="page-title">漫剧素材采集</h2>
      <div class="header-right">
        <span class="silent-label">后台静默运行</span>
        <el-switch v-model="silentMode" @change="onSilentChanged" />
      </div>
    </div>

    <DramaTable
      :rows="listData"
      :loading="listLoading"
      :extracting="extracting"
      v-model:selectedKeys="selectedKeys"
      @refresh="onRefreshList"
      @select-all="onSelectAll"
      @deselect-all="onDeselectAll"
      @batch-extract="onBatchExtract"
      @extract-single="onExtractSingle"
    />

    <ProgressPanel
      :percent="progressPercent"
      :statusText="progressText"
      :running="listLoading || extracting"
      @stop="onStop"
    />

    <LogPanel :messages="logMessages" />
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
import DramaTable from '../components/DramaTable.vue'
import ProgressPanel from '../components/ProgressPanel.vue'
import LogPanel from '../components/LogPanel.vue'
import { useWebSocket } from '../composables/useWebSocket'
import { startListScrape, startDetailScrape, startBatchScrape, stopScrape, getScrapeStatus } from '../api/scrape'
import { fetchSettings, updateSettings } from '../api/settings'

const { isConnected, connect, disconnect, on } = useWebSocket()

const listData = ref([])
const listLoading = ref(false)
const extracting = ref(false)
const selectedKeys = ref([])
const silentMode = ref(false)
const progressPercent = ref(0)
const progressText = ref('就绪 — 请先刷新列表')
const logMessages = reactive([])
const inBatch = ref(false)

function addLog(level, message) {
  logMessages.push({ level, message, timestamp: new Date().toLocaleTimeString() })
  if (logMessages.length > 500) logMessages.shift()
}

// ── WebSocket handlers ──

on('progress', (payload) => {
  progressPercent.value = payload.percent || 0
  progressText.value = payload.description || ''
})

on('log', (payload) => {
  logMessages.push({
    level: payload.level || 'info',
    message: payload.message || '',
    timestamp: payload.timestamp || new Date().toLocaleTimeString(),
  })
  if (logMessages.length > 500) logMessages.shift()
})

on('page_loaded', (payload) => {
  if (payload.rows) {
    for (const row of payload.rows) {
      if (!listData.value.find(r => r.detail_url === row.detail_url)) {
        listData.value.push(row)
      }
    }
  }
  addLog('info', `第 ${payload.page_num} 页: ${payload.rows?.length || 0} 条`)
})

on('list_complete', (payload) => {
  if (payload.all_rows) {
    listData.value = payload.all_rows
  }
  listLoading.value = false
  progressPercent.value = 100
  progressText.value = `列表加载完成 — 共 ${payload.total_rows} 条`
  addLog('success', `列表采集完成，共 ${payload.total_rows} 条`)
})

on('finished', (payload) => {
  if (!inBatch.value) {
    extracting.value = false
  }
  if (payload.success) {
    progressPercent.value = 100
    progressText.value = '提取完成'
    ElNotification.success({ title: '提取完成', message: `数据已保存到: ${payload.message}` })
  } else if (payload.message?.includes('已取消')) {
    progressText.value = '已取消'
  } else if (payload.message?.includes('登录已过期')) {
    silentMode.value = false
    progressText.value = '需要重新登录'
    ElNotification.warning({ title: '需要登录', message: payload.message })
  } else {
    ElNotification.error({ title: '提取失败', message: payload.message || '未知错误' })
  }

  if (inBatch.value && payload.drama_name) {
    addLog(payload.success ? 'success' : 'error', `[批量] ${payload.drama_name}: ${payload.success ? '完成' : payload.message}`)
  }
})

on('login_expired', () => {
  silentMode.value = false
  addLog('error', '检测到未登录，已关闭静默模式')
  ElNotification.warning({ title: '需要登录', message: '检测到登录过期，请关闭静默模式后重试' })
})

on('batch_progress', (payload) => {
  progressText.value = `批量提取: ${payload.current}/${payload.total}`
})

on('batch_complete', (payload) => {
  inBatch.value = false
  extracting.value = false
  progressPercent.value = 100
  progressText.value = '批量提取完成'
  ElNotification.success({ title: '批量提取完成', message: `已处理全部漫剧` })
})

// ── Actions ──

async function onRefreshList() {
  listLoading.value = true
  listData.value = []
  selectedKeys.value = []
  progressPercent.value = 0
  progressText.value = '正在加载漫剧列表...'
  try {
    await startListScrape()
  } catch (e) {
    listLoading.value = false
    ElMessage.error('启动列表采集失败: ' + (e.response?.data?.message || e.message))
  }
}

function onExtractSingle(row) {
  extracting.value = true
  progressPercent.value = 0
  progressText.value = `正在提取: ${row.name}`
  addLog('info', `开始提取: ${row.name}`)
  startDetailScrape(row.name, row.detail_url).catch(e => {
    extracting.value = false
    ElMessage.error('启动提取失败')
  })
}

function onBatchExtract() {
  const selected = listData.value.filter(r => selectedKeys.value.includes(r.detail_url || r.name))
  if (!selected.length) return
  inBatch.value = true
  extracting.value = true
  progressPercent.value = 0
  progressText.value = `批量提取 0/${selected.length}`
  const items = selected.map(r => ({ drama_name: r.name, detail_url: r.detail_url }))
  addLog('info', `批量提取 ${items.length} 部漫剧`)
  startBatchScrape(items).catch(e => {
    inBatch.value = false
    extracting.value = false
    ElMessage.error('启动批量提取失败')
  })
}

function onStop() {
  addLog('warning', '用户请求停止...')
  stopScrape().catch(() => {})
  listLoading.value = false
  extracting.value = false
  inBatch.value = false
}

function onSelectAll() {
  selectedKeys.value = listData.value.map(r => r.detail_url || r.name)
}

function onDeselectAll() {
  selectedKeys.value = []
}

async function onSilentChanged(val) {
  try {
    await updateSettings({ silent_mode: val })
  } catch (e) {
    ElMessage.error('保存设置失败')
  }
}

async function loadSilentMode() {
  try {
    const res = await fetchSettings()
    if (res.code === 200) {
      silentMode.value = res.data.silent_mode
    }
  } catch (e) {
    // ignore
  }
}

onMounted(() => {
  loadSilentMode()
  connect()
  addLog('info', 'WebSocket 已连接')
})

onUnmounted(() => {
  disconnect()
})
</script>

<style scoped>
.scrape-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
}

.scrape-page > :nth-child(2) {
  flex: 1;
  min-height: 0;
}

.scrape-page > :last-child {
  flex: 0 0 30%;
  min-height: 0;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.silent-label {
  font-size: 14px;
  color: var(--text-muted);
}

.page-title {
  font-size: 20px;
  color: var(--text-primary);
  font-weight: 600;
  font-family: Georgia, 'Times New Roman', serif;
  letter-spacing: 0.5px;
}
</style>
