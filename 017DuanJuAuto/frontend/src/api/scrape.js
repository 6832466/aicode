import request from './config'

export function startListScrape() {
  return request.post('/api/scrape/list')
}

export function startDetailScrape(dramaName, detailUrl) {
  return request.post('/api/scrape/detail', {
    drama_name: dramaName,
    detail_url: detailUrl || ''
  })
}

export function startBatchScrape(items) {
  return request.post('/api/scrape/detail/batch', { items })
}

export function stopScrape() {
  return request.post('/api/scrape/stop')
}

export function getScrapeStatus() {
  return request.get('/api/scrape/status')
}
