import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    redirect: '/scrape'
  },
  {
    path: '/scrape',
    name: 'Scrape',
    component: () => import('../views/ScrapePage.vue')
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('../views/SettingsPage.vue')
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export default router
