<template>
  <el-card>
    <div class="toolbar">
      <span class="label">漫剧列表</span>
      <el-input
        v-model="localFilter"
        placeholder="本地筛选..."
        clearable
        style="width: 200px"
      />
      <el-button type="primary" :icon="Refresh" :loading="loading" @click="$emit('refresh')">
        刷新列表
      </el-button>
      <el-button @click="$emit('select-all')">全选</el-button>
      <el-button @click="$emit('deselect-all')">取消</el-button>
      <el-button type="primary" :disabled="selectedKeys.length === 0" @click="$emit('batch-extract')">
        提取选中
      </el-button>
    </div>

    <el-table
      :data="pagedRows"
      ref="tableRef"
      style="width: 100%"
      max-height="calc(100vh - 430px)"
      @selection-change="onSelectionChange"
      @row-click="onRowClick"
    >
      <el-table-column type="selection" width="40" :selectable="() => true" />
      <el-table-column label="操作" width="70" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text type="primary" :disabled="extracting" @click="$emit('extract-single', row)">
            提取
          </el-button>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="剧名" min-width="260" show-overflow-tooltip />
      <el-table-column prop="manju_id" label="漫剧ID" width="180" show-overflow-tooltip />
      <el-table-column prop="publisher" label="制作方" width="150" show-overflow-tooltip />
      <el-table-column prop="publish_status" label="发布状态" width="80" />
      <el-table-column prop="created_time" label="创建时间" width="160" />
      <el-table-column prop="gender" label="男女频" width="75" />
      <el-table-column prop="category" label="分类" width="140" show-overflow-tooltip />
    </el-table>

    <div class="pagination-row">
      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :page-sizes="[10, 20, 30, 50, 100]"
        :total="totalFiltered"
        layout="total, sizes, prev, pager, next"
        @current-change="onPageChange"
        @size-change="onSizeChange"
      />
      <span class="count-label">
        共 {{ totalAll }} 条漫剧 | 筛选 {{ totalFiltered }} 条 | 已选 {{ selectedKeys.length }} 条
      </span>
    </div>
  </el-card>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Refresh } from '@element-plus/icons-vue'

const props = defineProps({
  rows: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  extracting: { type: Boolean, default: false },
  selectedKeys: { type: Array, default: () => [] },
})

const emit = defineEmits([
  'refresh', 'select-all', 'deselect-all', 'batch-extract',
  'extract-single', 'update:selectedKeys',
])

const localFilter = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const tableRef = ref(null)

const filteredRows = computed(() => {
  let list = props.rows
  if (localFilter.value) {
    const ft = localFilter.value.toLowerCase()
    list = list.filter(r => JSON.stringify(r).toLowerCase().includes(ft))
  }
  return list
})

const pagedRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredRows.value.slice(start, start + pageSize.value)
})

const totalAll = computed(() => props.rows.length)
const totalFiltered = computed(() => filteredRows.value.length)

watch(localFilter, () => {
  currentPage.value = 1
})

function onPageChange(page) {
  currentPage.value = page
}

function onSizeChange() {
  currentPage.value = 1
}

function onRowClick(row) {
  tableRef.value?.toggleRowSelection(row)
}

function onSelectionChange(rows) {
  emit('update:selectedKeys', rows.map(r => r.detail_url || r.name))
}
</script>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.label {
  font-weight: 600;
  margin-right: 8px;
}

.pagination-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 12px;
}

.count-label {
  font-size: 13px;
  color: #606266;
}
</style>
