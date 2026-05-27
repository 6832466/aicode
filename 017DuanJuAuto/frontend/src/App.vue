<template>
  <div class="admin-shell">
    <el-container class="app-container">
      <el-aside width="200px" class="app-aside">
        <div class="logo-area">
          <span class="logo-rune">&#9670;</span>
          <span class="logo-text">短剧素材采集</span>
        </div>
        <el-menu
          :default-active="activeMenu"
          router
          class="app-menu"
          background-color="transparent"
          text-color="#C0C4CC"
          active-text-color="#409EFF"
        >
          <el-menu-item index="/scrape">
            <el-icon><Search /></el-icon>
            <span>素材采集</span>
          </el-menu-item>
          <el-menu-item index="/settings">
            <el-icon><Setting /></el-icon>
            <span>设置</span>
          </el-menu-item>
        </el-menu>
      </el-aside>
      <el-container>
        <el-main>
          <router-view v-slot="{ Component }">
            <keep-alive>
              <component :is="Component" />
            </keep-alive>
          </router-view>
        </el-main>
      </el-container>
    </el-container>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<style>
/* ═══════════════════════════════════════════
   浅灰学院风 Light Admin Shell
   侧边栏深色 + 内容区浅灰白
   兼容 Element Plus 组件
   ═══════════════════════════════════════════ */

:root {
  --bg-base: #F5F7FA;
  --bg-surface: #FFFFFF;
  --bg-elevated: #FFFFFF;
  --bg-hover: #ECF5FF;
  --accent: #409EFF;
  --accent-light: #66B1FF;
  --text-primary: #303133;
  --text-secondary: #606266;
  --text-muted: #C0C4CC;
  --success: #67C23A;
  --warning: #E6A23C;
  --error: #F56C6C;
  --border: #DCDFE6;
  --border-light: #EBEEF5;
  --shadow: rgba(0,0,0,0.06);
  --shadow-md: rgba(0,0,0,0.08);
  --shadow-lg: rgba(0,0,0,0.12);

  /* Element Plus 全局覆写 */
  --el-color-primary: #409EFF;
  --el-color-primary-light-3: #66B1FF;
  --el-color-primary-light-5: #8CC7FF;
  --el-color-primary-light-7: #B3DBFF;
  --el-color-primary-light-8: #D9ECFF;
  --el-color-primary-light-9: #ECF5FF;
  --el-color-primary-dark-2: #337ECC;
  --el-color-success: #67C23A;
  --el-color-warning: #E6A23C;
  --el-color-danger: #F56C6C;
  --el-color-info: #909399;
  --el-bg-color: #FFFFFF;
  --el-bg-color-page: #F5F7FA;
  --el-bg-color-overlay: #FFFFFF;
  --el-text-color-primary: #303133;
  --el-text-color-regular: #606266;
  --el-text-color-secondary: #909399;
  --el-text-color-placeholder: #C0C4CC;
  --el-text-color-disabled: #C0C4CC;
  --el-border-color: #DCDFE6;
  --el-border-color-light: #EBEEF5;
  --el-border-color-lighter: #F2F6FC;
  --el-border-color-extra-light: #F5F7FA;
  --el-fill-color: #F5F7FA;
  --el-fill-color-light: #FAFAFA;
  --el-fill-color-lighter: #FFFFFF;
  --el-fill-color-blank: #FFFFFF;
  --el-disabled-bg-color: #F5F7FA;
  --el-disabled-text-color: #C0C4CC;
  --el-disabled-border-color: #EBEEF5;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html, body {
  background: var(--bg-base);
  color: var(--text-secondary);
  font-family: "Microsoft YaHei", "PingFang SC", sans-serif;
}

/* ═══ Shell ═══ */

.admin-shell {
  height: 100vh;
  background: var(--bg-base);
}

/* ═══ 布局 ═══ */

.app-container {
  height: 100vh;
}

.app-aside {
  background: #1D1E2C;
  overflow: hidden;
}

.logo-area {
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
}

.logo-rune {
  color: var(--accent);
  font-size: 14px;
}

.logo-text {
  color: #FFFFFF;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 1px;
}

.app-menu {
  border-right: none;
}

.app-menu .el-menu-item {
  color: #C0C4CC !important;
  border-radius: 4px;
  margin: 2px 8px;
  font-size: 14px;
  font-weight: 500;
  transition: all 0.15s ease;
}

.app-menu .el-menu-item:hover {
  background: #2A2B3C !important;
  color: #FFFFFF !important;
}

.app-menu .el-menu-item.is-active {
  color: #409EFF !important;
  background: #2A2B3C !important;
  font-weight: 600;
  border-left: 3px solid #409EFF;
}

.el-main {
  background: #F5F7FA;
  padding: 20px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* ═══ 卡片 ═══ */

.el-card {
  background: #FFFFFF !important;
  border: 1px solid #EBEEF5 !important;
  border-radius: 8px !important;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
  color: var(--text-secondary) !important;
  transition: box-shadow 0.2s ease;
}

.el-card:hover {
  box-shadow: 0 4px 12px rgba(0,0,0,0.08) !important;
}

.el-card__header {
  border-bottom: 1px solid #EBEEF5 !important;
  color: var(--text-primary) !important;
  font-weight: 600;
  font-size: 16px;
}

.el-card__body {
  color: var(--text-secondary) !important;
}

/* ═══ 主按钮 ═══ */

.el-button--primary {
  background: #409EFF !important;
  border: none !important;
  color: #FFF !important;
  font-weight: 500;
  font-size: 14px;
  border-radius: 6px !important;
}

.el-button--primary:hover {
  background: #66B1FF !important;
}

/* 次要按钮 */

.el-button--default {
  background: #FFFFFF !important;
  border: 1px solid #DCDFE6 !important;
  color: #606266 !important;
  font-weight: 500;
  font-size: 14px;
  border-radius: 6px !important;
}

.el-button--default:hover {
  color: #409EFF !important;
  border-color: #409EFF !important;
}

/* ═══ 输入框 ═══ */

.el-input__wrapper {
  background: #FFFFFF !important;
  border: 1px solid #DCDFE6 !important;
  box-shadow: none !important;
  border-radius: 6px !important;
}

.el-input__wrapper:focus,
.el-input__wrapper.is-focus {
  border-color: #409EFF !important;
  box-shadow: 0 0 0 2px rgba(64,158,255,0.15) !important;
}

.el-input__inner {
  color: #303133 !important;
}

.el-input__inner::placeholder {
  color: #C0C4CC !important;
}

/* ═══ 表格 ═══ */

.el-table {
  --el-table-bg-color: transparent;
  --el-table-tr-bg-color: transparent;
  --el-table-header-bg-color: #FAFAFA;
  --el-table-row-hover-bg-color: #ECF5FF;
  --el-table-border-color: #EBEEF5;
  --el-table-text-color: #303133;
  --el-table-header-text-color: #303133;
  border-radius: 8px;
  overflow: hidden;
}

.el-table th {
  font-weight: 600;
  font-size: 13px;
}

.el-table .el-table__row {
  border-bottom: 1px solid #EBEEF5;
}

/* ═══ 分页 ═══ */

.el-pagination button,
.el-pager li {
  background: transparent !important;
  color: #606266 !important;
  border: 1px solid #DCDFE6 !important;
  border-radius: 4px !important;
  font-weight: 500;
}

.el-pager li.is-active {
  background: #409EFF !important;
  color: #FFF !important;
  border-color: transparent !important;
  font-weight: 600;
}

/* ═══ 开关 ═══ */

.el-switch.is-checked .el-switch__core {
  background: #409EFF !important;
  border-color: #409EFF !important;
}

/* ═══ 进度条 ═══ */

.el-progress-bar__outer {
  background: #EBEEF5 !important;
  border: none;
  border-radius: 4px !important;
}

.el-progress-bar__inner {
  background: #409EFF !important;
  border-radius: 4px !important;
}

/* ═══ 表单 ═══ */

.el-form-item__label {
  color: #303133 !important;
  font-weight: 600;
  font-size: 14px;
}

/* ═══ 弹窗 ═══ */

.el-dialog {
  background: #FFFFFF !important;
  border: none !important;
  border-radius: 12px !important;
  box-shadow: 0 12px 48px rgba(0,0,0,0.15);
}

.el-dialog__title {
  color: #303133 !important;
  font-weight: 700;
  font-size: 18px;
}

/* ═══ 消息框 ═══ */

.el-message {
  background: #FFFFFF !important;
  border: none !important;
  border-radius: 8px !important;
  box-shadow: 0 4px 12px rgba(0,0,0,0.10);
}

.el-message__content {
  color: #303133 !important;
}

/* ═══ 通知 ═══ */

.el-notification {
  background: #FFFFFF !important;
  border: none !important;
  border-radius: 8px !important;
  box-shadow: 0 4px 12px rgba(0,0,0,0.10);
}

.el-notification__title {
  color: #303133 !important;
  font-weight: 600;
}

.el-notification__content {
  color: #606266 !important;
}

/* ═══ 选中/多选 ═══ */

.el-checkbox__input.is-checked .el-checkbox__inner {
  background: #409EFF !important;
  border-color: #409EFF !important;
}

.el-checkbox__inner {
  background: #FFFFFF !important;
  border: 1px solid #DCDFE6 !important;
}

/* ═══ 下拉菜单 ═══ */

.el-select-dropdown {
  background: #FFFFFF !important;
  border: 1px solid #EBEEF5 !important;
  box-shadow: 0 6px 16px rgba(0,0,0,0.12) !important;
}

.el-select-dropdown__item {
  color: #606266 !important;
}

.el-select-dropdown__item.hover,
.el-select-dropdown__item:hover {
  background: #ECF5FF !important;
  color: #303133 !important;
}

.el-select-dropdown__item.selected {
  color: #409EFF !important;
}

/* ═══ 标签/徽章 ═══ */

.el-tag {
  background: #ECF5FF !important;
  border-color: #D9ECFF !important;
  color: #409EFF !important;
  border-radius: 4px;
}

/* ═══ 危险按钮 ═══ */

.el-button--danger {
  background: #F56C6C !important;
  border: none !important;
  color: #FFF !important;
  font-weight: 500;
  border-radius: 6px !important;
}

.el-button--danger:hover {
  background: #F78989 !important;
}

/* ═══ 文字按钮 ═══ */

.el-button.is-text {
  color: #409EFF !important;
}
</style>
