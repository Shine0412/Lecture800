import { spawn, spawnSync } from 'node:child_process'
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright'

const artifacts = fileURLToPath(new URL('../artifacts/', import.meta.url))
await mkdir(artifacts, { recursive: true })
const server = spawn(process.execPath, ['dev-server.mjs', '--host', '127.0.0.1', '--port', '7100', '--strictPort'], {
  cwd: fileURLToPath(new URL('../', import.meta.url)),
  stdio: ['ignore', 'pipe', 'pipe'],
})
let output = ''
server.stdout.on('data', (chunk) => { output += chunk })
server.stderr.on('data', (chunk) => { output += chunk })
let browser

async function waitForServer() {
  const deadline = Date.now() + 30000
  while (Date.now() < deadline) {
    try {
      const response = await fetch('http://127.0.0.1:7100/api/health')
      if (response.ok) return response.json()
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 400))
  }
  throw new Error(`开发服务启动超时\n${output}`)
}

try {
  const health = await waitForServer()
  assert.equal(health.connected, true, '已保存会话应通过学校 HTTPS 接口验证')
  const response = await fetch('http://127.0.0.1:7100/api/lectures')
  const snapshot = await response.json()
  assert.equal(response.status, 200)
  assert.equal(snapshot.connected, true)
  assert.ok(snapshot.count > 0)

  browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
  const errors = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('http://127.0.0.1:7100/', { waitUntil: 'domcontentloaded' })
  await page.getByText('接口已连接', { exact: true }).waitFor({ timeout: 30000 })
  await page.locator('.sidebar nav').getByRole('button', { name: '全部讲座', exact: true }).click()
  await page.waitForFunction((count) => document.querySelectorAll('.lecture-grid .lecture-card').length === count, snapshot.count)
  await page.screenshot({ path: `${artifacts}live-catalog.png`, fullPage: true })
  assert.deepEqual(errors, [])
  const result = { connected: true, count: snapshot.count, fetchedAt: snapshot.fetchedAt, pageErrors: errors }
  await writeFile(`${artifacts}live-integration-results.json`, JSON.stringify(result, null, 2))
  console.log(JSON.stringify(result, null, 2))
} finally {
  if (browser) await browser.close()
  if (server.pid) spawnSync('taskkill', ['/pid', String(server.pid), '/T', '/F'], { stdio: 'ignore' })
}
