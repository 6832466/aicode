import axios from 'axios'

const service = axios.create({
  baseURL: 'http://127.0.0.1:8200/',
  timeout: 30000
})

service.interceptors.request.use(
  config => config,
  error => Promise.reject(error)
)

service.interceptors.response.use(
  response => response.data,
  error => {
    console.error('API Error:', error)
    return Promise.reject(error)
  }
)

export default service
