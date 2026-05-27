console.log('process.type:', process.type)
console.log('process.versions.electron:', process.versions.electron)

// Try require('electron/main') instead of require('electron')
try {
  const electronMain = require('electron/main')
  console.log('electron/main keys:', Object.keys(electronMain).slice(0, 10))
} catch(e) {
  console.log('electron/main error:', e.message)
}

// Check the throw behavior
try {
  require('electron/common')
} catch(e) {
  console.log('electron/common error:', e.message)
}
