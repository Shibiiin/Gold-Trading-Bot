import axios from 'axios'

const tradingService = axios.create({
  baseURL: import.meta.env.VITE_TRADING_API_BASE_URL || '/trading-api',
  timeout: 15000
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
