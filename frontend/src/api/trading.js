import axios from 'axios'

const getDynamicBaseUrl = () => {
  return localStorage.getItem('GOLDBOT_BACKEND_URL') || 'http://localhost:8080'
}

const tradingService = axios.create({
  timeout: 15000
})

tradingService.interceptors.request.use(config => {
  config.baseURL = getDynamicBaseUrl()
  return config
})

tradingService.interceptors.response.use(
  response => response.data,
  error => Promise.reject(error)
)

export const getTradingJournal = (limit = 200) => {
  return tradingService.get('/api/journal/entries', { params: { limit } })
}

export const getTradingStats = () => {
  return tradingService.get('/api/journal/stats')
}

export const setBackendUrl = (url) => {
  // Strip trailing slashes
  const cleanUrl = url.replace(/\/+$/, '')
  localStorage.setItem('GOLDBOT_BACKEND_URL', cleanUrl)
}

export const getBackendUrl = () => {
  return getDynamicBaseUrl()
}
