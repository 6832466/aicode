import request from './config'

export function fetchSettings() {
  return request.get('/api/settings')
}

export function updateSettings(data) {
  return request.put('/api/settings', data)
}
