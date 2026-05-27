import { ref, onUnmounted } from 'vue'

export function useWebSocket() {
  const isConnected = ref(false)
  let ws = null
  let reconnectTimer = null
  let handlers = {}
  let reconnectDelay = 1000

  function connect(url = 'ws://127.0.0.1:8200/ws') {
    if (ws && ws.readyState === WebSocket.OPEN) return

    ws = new WebSocket(url)

    ws.onopen = () => {
      isConnected.value = true
      reconnectDelay = 1000
      startHeartbeat()
    }

    ws.onclose = () => {
      isConnected.value = false
      stopHeartbeat()
      scheduleReconnect(url)
    }

    ws.onerror = () => {
      ws.close()
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'pong') return
        const cb = handlers[msg.type]
        if (cb) {
          delete msg.type
          cb(msg)
        }
      } catch (e) {
        console.error('WS message parse error:', e)
      }
    }
  }

  function disconnect() {
    stopHeartbeat()
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    if (ws) {
      ws.close()
      ws = null
    }
    isConnected.value = false
  }

  function on(type, callback) {
    handlers[type] = callback
  }

  function send(type, payload = {}) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type, ...payload }))
    }
  }

  function scheduleReconnect(url) {
    if (reconnectTimer) return
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null
      reconnectDelay = Math.min(reconnectDelay * 2, 30000)
      connect(url)
    }, reconnectDelay)
  }

  let heartbeatInterval = null

  function startHeartbeat() {
    heartbeatInterval = setInterval(() => {
      send('ping')
    }, 30000)
  }

  function stopHeartbeat() {
    if (heartbeatInterval) {
      clearInterval(heartbeatInterval)
      heartbeatInterval = null
    }
  }

  onUnmounted(() => {
    disconnect()
  })

  return { isConnected, connect, disconnect, on, send }
}
