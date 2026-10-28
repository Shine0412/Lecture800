import { createServer } from 'vite'
import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

const artifacts = fileURLToPath(new URL('../artifacts/', import.meta.url))
const snapshotPath = fileURLToPath(new URL('./fixtures/lecture-snapshot.json', import.meta.url))
const snapshot = JSON.parse(await readFile(snapshotPath, 'utf8'))
await mkdir(artifacts, { recursive: true })
const server = await createServer({ server: { host: '127.0.0.1', port: 7102, strictPort: true } })
let browser
const results = []
const errors = []

function pass(name) {
  results.push({ name, result: 'passed' })
  console.log(`PASS ${name}`)
}

try {
  await server.listen()
  browser = await chromium.launch({
    headless: true,
    executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  })
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, deviceScaleFactor: 1 })
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/api/lectures', (route) => route.fulfill({ json: snapshot }))
  await page.route('**/api/refresh', (route) => route.fulfill({ json: snapshot }))
  await page.route('**/api/logs', (route) => route.fulfill({ json: { logs: [] } }))
  await page.route('**/api/verify', (route) => route.fulfill({ json: { connected: true, checks: [
    { key: 'window', label: '小程序窗口', ok: true, detail: '科大微门户窗口可见' },
    { key: 'page', label: '目标平台页面', ok: true, detail: '已识别目标平台' },
    { key: 'lectures', label: '讲座数据', ok: true, detail: `已识别 ${snapshot.count} 张课程卡片` },
  ] } }))
  const enrollCalls = []
  await page.route('**/api/enroll', async (route) => {
    enrollCalls.push(route.request().postDataJSON())
    await route.fulfill({ json: { ok: true, verified: true, alreadyEnrolled: false, message: '模拟手动报名成功，已核验我的报名' } })
  })
  const autoNowCalls = []
  await page.route('**/api/enroll/all', async (route) => {
    autoNowCalls.push(route.request().postDataJSON())
    const lecture = snapshot.lectures.find((item) => item.status === 'open')
    await route.fulfill({ json: {
      ok: true, verified: true, submittedCount: 1, verifiedCount: 1,
      results: [{ id: lecture.id, title: lecture.title, location: lecture.location, submitted: true, verified: true, error: null }],
      message: '模拟即时抢课完成：提交 1 场，核验到 1 场。',
    } })
  })
  let withdrawn = false
  let failNextWithdraw = true
  const withdrawCalls = []
  const pendingLecture = { ...snapshot.lectures[1], id: 'pending-1', title: '待参与测试讲座', registration: 'enrolled', joinStatus: 'pending', applyId: 'apply-test-1', canWithdraw: true }
  const minePayload = () => ({
    connected: true, page: 'mine', fetchedAt: snapshot.fetchedAt,
    profile: { account: 'TEST800', role: '学生' },
    metrics: [
      { label: '我的报名数', value: 5 }, { label: '待参与数', value: withdrawn ? 0 : 1 },
      { label: '已完成考勤数', value: 3 }, { label: '已完成评价数', value: 3 },
    ],
    applications: [{ ...snapshot.lectures[0], id: 'all-1', title: '全部报名测试讲座', registration: 'enrolled' }],
    groups: {
      pending: withdrawn ? [] : [pendingLecture],
      missedAttendance: [{ ...snapshot.lectures[2], id: 'missed-1', title: '未完成考勤测试讲座', registration: 'enrolled', attendanceStatus: 'missed', canWithdraw: false }],
      attended: [{ ...snapshot.lectures[0], id: 'attended-1', title: '已考勤测试讲座', registration: 'enrolled', attendanceStatus: 'attended', joinStatus: 'attended', canWithdraw: false }],
      pendingEvaluation: [{ ...snapshot.lectures[2], id: 'evaluation-1', title: '待评价测试讲座', registration: 'enrolled', joinStatus: 'pendingEvaluation', canWithdraw: false }],
      evaluated: [{ ...snapshot.lectures[0], id: 'evaluated-1', title: '已评价测试讲座', registration: 'enrolled', joinStatus: 'evaluated', canWithdraw: false }],
    },
    items: [], rawItems: [],
  })
  await page.route('**/api/mine', (route) => route.fulfill({ json: minePayload() }))
  await page.route('**/api/withdraw', async (route) => {
    withdrawCalls.push(route.request().postDataJSON())
    if (failNextWithdraw) {
      failNextWithdraw = false
      await route.fulfill({ status: 502, json: { ok: false, verified: false, message: '模拟回执仍存在，退课未成功' } })
      return
    }
    withdrawn = true
    await route.fulfill({ json: { ok: true, verified: true, message: '模拟退课成功' } })
  })
  let autoEnabled = true
  let locationRules = { firstSite: true, secondSite: true, thirdSite: false, nanjing: false, wuhan: false, other: true }
  await page.route('**/api/settings', async (route) => {
    if (route.request().method() === 'PUT') {
      const body = route.request().postDataJSON()
      if (typeof body.autoEnabled === 'boolean') autoEnabled = body.autoEnabled
      if (body.locationRules) locationRules = body.locationRules
    }
    await route.fulfill({ json: { autoEnabled, locationRules, precheckTime: '11:58', reviewTime: '12:00', writeEnabled: true, scheduler: 'embedded', runtime: { running: false } } })
  })

  let captureState = { state: 'idle', detail: '尚未开始本机会话配置', active: false, canStart: true, isAdministrator: false, systemProxyModified: false }
  const captureStartCalls = []
  await page.route('**/api/capture', (route) => route.fulfill({ json: captureState }))
  await page.route('**/api/capture/start', async (route) => {
    captureStartCalls.push(route.request().postDataJSON())
    captureState = { ...captureState, state: 'waiting', detail: '捕获已就绪：请重新打开目标讲座页面', active: true, canStart: false }
    await route.fulfill({ status: 202, json: captureState })
  })
  await page.route('**/api/capture/cancel', async (route) => {
    captureState = { ...captureState, state: 'cancelled', detail: '已取消会话配置，未修改系统代理', active: false, canStart: true }
    await route.fulfill({ json: captureState })
  })

  await page.goto('http://127.0.0.1:7102/', { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: '讲座实时看板' }).waitFor()
  await page.getByText('接口已连接', { exact: true }).waitFor()
  assert.equal(await page.locator('.stat-card').first().locator('strong').innerText(), String(snapshot.count))
  await page.screenshot({ path: `${artifacts}desktop-overview.png`, fullPage: true })
  pass('实时总览显示真实课程数量与连接状态')

  await page.getByRole('button', { name: '立即开始自动抢课', exact: true }).click()
  const autoConfirmDialog = page.getByRole('dialog', { name: '确认立即自动抢课' })
  await autoConfirmDialog.waitFor()
  assert.match(await autoConfirmDialog.innerText(), /不是等到 12:00/)
  assert.match(await autoConfirmDialog.innerText(), /每天 11:58 预检和 12:00 自动任务仍保留/)
  assert.equal(autoNowCalls.length, 0)
  await autoConfirmDialog.getByRole('button', { name: '确认立即抢课', exact: true }).click()
  const autoResultDialog = page.getByRole('dialog', { name: '即时抢课结果' })
  await autoResultDialog.waitFor()
  assert.match(await autoResultDialog.innerText(), /提交 1 场，核验到 1 场/)
  assert.match(await autoResultDialog.innerText(), /已抢到/)
  assert.deepEqual(autoNowCalls, [{ confirm: true }])
  assert.equal(autoEnabled, true)
  await autoResultDialog.getByRole('button', { name: '完成', exact: true }).click()
  await page.getByRole('button', { name: '关闭提示', exact: true }).click()
  pass('首页可立即批量抢课并显示回执，每日自动任务保持不变')

  const sidebar = page.locator('.sidebar nav')
  await sidebar.getByRole('button', { name: '全部讲座', exact: true }).click()
  assert.equal(await page.locator('.lecture-grid .lecture-card').count(), snapshot.lectures.length)
  await page.getByRole('button', { name: '已满员', exact: true }).click()
  assert.equal(await page.locator('.lecture-grid .lecture-card').count(), snapshot.lectures.filter((item) => item.status === 'full').length)
  await page.getByRole('button', { name: '未开放', exact: true }).click()
  assert.equal(await page.locator('.lecture-grid .lecture-card').count(), snapshot.lectures.filter((item) => item.status === 'upcoming').length)
  pass('真实目录、满员与未开放筛选数量正确')

  await page.getByRole('button', { name: '全部', exact: true }).click()
  const openLecture = snapshot.lectures.find((item) => item.status === 'open')
  await page.getByRole('button', { name: `报名${openLecture.title}`, exact: true }).click()
  const enrollDialog = page.getByRole('dialog', { name: '确认手动报名' })
  await enrollDialog.waitFor()
  assert.match(await enrollDialog.innerText(), /只发送一次报名请求/)
  assert.equal(enrollCalls.length, 0)
  await enrollDialog.getByRole('button', { name: '确认报名', exact: true }).click()
  await enrollDialog.waitFor({ state: 'hidden' })
  assert.deepEqual(enrollCalls, [{ lectureId: openLecture.id, confirm: true }])
  await page.getByRole('button', { name: '关闭提示', exact: true }).click()
  pass('单课手动报名需要确认并携带讲座 ID，成功后核验回执')

  const target = snapshot.lectures[0]
  await page.getByLabel('搜索讲座').fill(target.speaker)
  assert.equal(await page.locator('.lecture-grid .lecture-card').count(), 1)
  await page.getByRole('button', { name: `查看${target.title}详情` }).click()
  const dialog = page.getByRole('dialog')
  await dialog.waitFor()
  assert.match(await dialog.innerText(), /报名开放/)
  assert.doesNotMatch(await dialog.innerText(), /Invalid Date|null/)
  await page.getByRole('button', { name: '关闭详情' }).click()
  pass('讲座搜索与未知字段详情展示正确')

  await page.getByLabel('搜索讲座').fill('不存在的讲座')
  await page.getByText('没有匹配的讲座').waitFor()
  pass('空搜索结果显示正常')

  await sidebar.getByRole('button', { name: '设置', exact: true }).click()
  const autoSwitch = page.getByRole('switch', { name: '自动抢课', exact: true })
  assert.equal(await autoSwitch.getAttribute('aria-checked'), 'true')
  await autoSwitch.click()
  assert.equal(await autoSwitch.getAttribute('aria-checked'), 'false')
  await autoSwitch.click()
  assert.equal(await autoSwitch.getAttribute('aria-checked'), 'true')
  assert.match(await page.locator('.settings-card').innerText(), /回执核验/)
  assert.match(await page.locator('.settings-card').innerText(), /12:00/)
  assert.match(await page.locator('.settings-card').innerText(), /全部候选并发提交/)
  assert.match(await page.locator('.settings-card').innerText(), /勾选的地点才会进入自动报名/)
  assert.match(await page.locator('.settings-side').innerText(), /再次打开 EXE，无需同步打开微信小程序/)
  assert.match(await page.locator('.settings-side').innerText(), /会话失效、换电脑／Windows 用户或连接验证失败/)
  const thirdSite = page.getByRole('checkbox', { name: '三号院', exact: true })
  const firstSite = page.getByRole('checkbox', { name: '一号院', exact: true })
  assert.equal(await thirdSite.getAttribute('aria-checked'), 'false')
  await thirdSite.click()
  assert.equal(await thirdSite.getAttribute('aria-checked'), 'true')
  assert.equal(locationRules.thirdSite, true)
  await firstSite.click()
  assert.equal(await firstSite.getAttribute('aria-checked'), 'false')
  assert.equal(locationRules.firstSite, false)
  await firstSite.click()
  await thirdSite.click()
  assert.equal(locationRules.firstSite, true)
  assert.equal(locationRules.thirdSite, false)
  await page.getByRole('button', { name: '关闭提示', exact: true }).click()
  pass('任务开关与六个地点选项可切换并保存，核心执行链路清晰')

  await page.getByRole('button', { name: '配置／重新配置会话', exact: true }).click()
  const setupDialog = page.getByRole('dialog', { name: '配置本机会话' })
  await setupDialog.waitFor()
  const captureStart = setupDialog.getByRole('button', { name: '开始本机配置', exact: true })
  assert.equal(await captureStart.isDisabled(), true)
  assert.match(await setupDialog.innerText(), /不修改系统代理/)
  assert.match(await setupDialog.innerText(), /管理员权限：未启用/)
  await setupDialog.getByRole('checkbox').check()
  assert.equal(await captureStart.isEnabled(), true)
  await captureStart.click()
  await setupDialog.getByText(/捕获已就绪：请重新打开目标讲座页面/).waitFor()
  assert.deepEqual(captureStartCalls, [{ authorized: true }])
  await setupDialog.getByRole('button', { name: '停止并清理', exact: true }).click()
  await setupDialog.getByText(/已取消会话配置，未修改系统代理/).waitFor()
  await setupDialog.getByRole('button', { name: '关闭', exact: true }).click()
  await setupDialog.waitFor({ state: 'hidden' })
  pass('内置会话向导需明确授权，可启动、取消并显示安全状态')

  await sidebar.getByRole('button', { name: /我的信息/ }).click()
  await page.getByText('TEST800', { exact: true }).waitFor()
  assert.equal(await page.locator('.mine-metric').count(), 4)
  assert.match(await page.locator('.mine-metrics').innerText(), /5\n我的报名数/)
  assert.match(await page.locator('.mine-metrics').innerText(), /3\n已完成评价数/)
  pass('我的信息保留账号、身份及四项统计对应关系')
  await page.getByRole('button', { name: '待参与 1', exact: true }).click()
  await page.getByText('待参与测试讲座', { exact: true }).waitFor()
  assert.equal(await page.locator('.mine-lectures .lecture-card').count(), 1)
  await page.getByRole('button', { name: '退课', exact: true }).click()
  const withdrawDialog = page.getByRole('dialog', { name: '确认退课' })
  await withdrawDialog.waitFor()
  assert.match(await withdrawDialog.innerText(), /待参与测试讲座/)
  assert.equal(withdrawCalls.length, 0)
  await withdrawDialog.getByRole('button', { name: '确认退课', exact: true }).click()
  await withdrawDialog.getByRole('alert').waitFor()
  assert.match(await withdrawDialog.getByRole('alert').innerText(), /模拟回执仍存在/)
  assert.equal(withdrawCalls.length, 1)
  await withdrawDialog.getByRole('button', { name: '确认退课', exact: true }).click()
  await page.getByRole('status').waitFor()
  assert.match(await page.getByRole('status').innerText(), /退课成功/)
  await page.getByRole('button', { name: '关闭提示', exact: true }).click()
  await withdrawDialog.waitFor({ state: 'hidden' })
  await page.getByText('暂无待参与项目', { exact: true }).waitFor()
  assert.equal(withdrawCalls.length, 2)
  assert.deepEqual(withdrawCalls.map((body) => ({ lectureId: body.lectureId, applyId: body.applyId, confirm: body.confirm })), [
    { lectureId: 'pending-1', applyId: 'apply-test-1', confirm: true },
    { lectureId: 'pending-1', applyId: 'apply-test-1', confirm: true },
  ])
  pass('退课需二次确认，失败不记成功，成功回执后刷新分类')
  await page.getByRole('button', { name: '未完成考勤 1', exact: true }).click()
  await page.getByText('未完成考勤测试讲座', { exact: true }).waitFor()
  assert.match(await page.locator('.mine-lectures .lecture-card').innerText(), /接口未记录完成签到/)
  assert.equal(await page.locator('.mine-lectures').getByRole('button', { name: '退课', exact: true }).count(), 0)
  await page.getByRole('button', { name: '已考勤 1', exact: true }).click()
  await page.getByText('已考勤测试讲座', { exact: true }).waitFor()
  assert.match(await page.locator('.mine-lectures .lecture-card').innerText(), /接口已记录完成签到/)
  await page.getByRole('button', { name: '待评价 1', exact: true }).click()
  await page.getByText('待评价测试讲座', { exact: true }).waitFor()
  await page.getByRole('button', { name: '已评价 1', exact: true }).click()
  await page.getByText('已评价测试讲座', { exact: true }).waitFor()
  await page.getByRole('button', { name: '全部报名', exact: true }).click()
  await page.getByText('全部报名测试讲座', { exact: true }).waitFor()
  pass('六个报名分类可切换，未考勤与已评价独立显示')

  await sidebar.getByRole('button', { name: '使用说明', exact: true }).click()
  await page.getByRole('heading', { name: '首次使用，按这 5 步操作' }).waitFor()
  assert.match(await page.locator('.guide-grid').innerText(), /11:58/)
  assert.match(await page.locator('.guide-grid').innerText(), /WebView2/)
  assert.match(await page.locator('.guide-grid').innerText(), /首次配置已内置/)
  assert.match(await page.locator('.guide-grid').innerText(), /再次打开 EXE，无需同步打开微信小程序/)
  assert.match(await page.locator('.guide-grid').innerText(), /首页“立即开始自动抢课”/)
  await page.getByRole('button', { name: '打开内置配置向导', exact: true }).waitFor()
  pass('使用说明包含每日时间线、内置配置入口和 EXE 移植要求')

  await sidebar.getByRole('button', { name: '总览', exact: true }).click()
  await page.getByRole('button', { name: '刷新目录', exact: true }).click()
  await page.getByRole('status').waitFor()
  assert.match(await page.getByRole('status').innerText(), new RegExp(`同步 ${snapshot.count} 场`))
  pass('手动刷新只同步数据，不伪造报名结果')

  await page.setViewportSize({ width: 1000, height: 700 })
  await page.waitForTimeout(300)
  await page.screenshot({ path: `${artifacts}desktop-compact.png`, fullPage: true })
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
  assert.equal(overflow, false)
  await sidebar.getByRole('button', { name: '全部讲座', exact: true }).click()
  await page.getByLabel('搜索讲座').waitFor()
  pass('桌面最小窗口尺寸无横向溢出且导航可用')

  assert.deepEqual(errors, [])
  pass('交互过程中无未捕获脚本错误')
  await writeFile(`${artifacts}e2e-results.json`, JSON.stringify({ results, errors }, null, 2))
} catch (error) {
  await writeFile(`${artifacts}e2e-results.json`, JSON.stringify({ results, errors, failure: error.stack }, null, 2))
  throw error
} finally {
  if (browser) await browser.close()
  await server.close()
}
