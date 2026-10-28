import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const appRoot = dirname(fileURLToPath(import.meta.url))
const workspaceRoot = resolve(appRoot, '..')
const python = resolve(workspaceRoot, 'windows-agent', '.venv', 'Scripts', 'python.exe')
const agent = resolve(workspaceRoot, 'windows-agent', 'lecture_agent.py')
const vite = resolve(appRoot, 'node_modules', 'vite', 'bin', 'vite.js')

if (!existsSync(python)) {
  console.error(`未找到采集服务 Python：${python}`)
  process.exit(1)
}

const api = spawn(python, [agent, '--host', '127.0.0.1', '--port', '8765'], {
  cwd: workspaceRoot,
  stdio: ['ignore', 'pipe', 'pipe'],
})
const web = spawn(process.execPath, [vite, ...process.argv.slice(2)], {
  cwd: appRoot,
  stdio: 'inherit',
})

api.stdout.on('data', (chunk) => process.stdout.write(`[实时采集] ${chunk}`))
api.stderr.on('data', (chunk) => process.stderr.write(`[实时采集] ${chunk}`))

let stopping = false
function stop(code = 0) {
  if (stopping) return
  stopping = true
  if (!api.killed) api.kill()
  if (!web.killed) web.kill()
  setTimeout(() => process.exit(code), 150).unref()
}

api.on('error', (error) => {
  console.error(`实时采集启动失败：${error.message}`)
  stop(1)
})
web.on('error', (error) => {
  console.error(`Web 服务启动失败：${error.message}`)
  stop(1)
})
api.on('exit', (code) => {
  if (!stopping && code) stop(code)
})
web.on('exit', (code) => stop(code || 0))
process.on('SIGINT', () => stop(0))
process.on('SIGTERM', () => stop(0))
