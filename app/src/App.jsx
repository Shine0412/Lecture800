import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  AlertCircle, BookOpenCheck, CalendarDays, Check, CheckCircle2, ChevronRight,
  CircleHelp, Clock3, GraduationCap, History, LayoutDashboard, LibraryBig,
  ListChecks, ListFilter, MapPin, MonitorCheck, RefreshCw, Search, Settings,
  ShieldCheck, Sparkles, UserRound, UsersRound, X,
} from 'lucide-react'
import { getNextRun } from './lib/enrollment'
import {
  DEFAULT_LOCATION_RULES, LOCATION_OPTIONS, normalizeLocationRules, selectOpenCandidates,
} from './lib/enrollmentPolicy'
import {
  fetchLiveLectures, fetchMine, fetchOperationLogs, fetchSettings, fetchVerification,
  enrollAllLectures, enrollLecture, formatDateTime, formatSyncTime, setAutoEnabled, setLocationRules, withdrawLecture,
} from './lib/liveApi'
import SessionSetup from './SessionSetup'

const NAV_ITEMS = [
  { id: 'overview', label: '总览', icon: LayoutDashboard },
  { id: 'lectures', label: '全部讲座', icon: LibraryBig },
  { id: 'mine', label: '我的信息', icon: BookOpenCheck },
  { id: 'logs', label: '运行记录', icon: History },
  { id: 'settings', label: '设置', icon: Settings },
  { id: 'guide', label: '使用说明', icon: CircleHelp },
]

const PAGE_COPY = {
  overview: ['讲座实时看板', '通过学校 H5 接口读取讲座目录与报名状态。'],
  lectures: ['全部讲座', '浏览接口返回的完整 800 级讲座分页目录。'],
  mine: ['我的信息', '独立请求个人资料、讲座统计和我的报名。'],
  logs: ['运行记录', '查看接口采集、每日预检和报名动作的真实结果。'],
  settings: ['自动化设置', '管理每日任务、地点规则和连接状态。'],
  guide: ['使用说明', '了解会话准备、每日执行和 EXE 移植要求。'],
}

const MINE_TABS = [
  ['all', '全部报名'], ['pending', '待参与'], ['missedAttendance', '未完成考勤'],
  ['attended', '已考勤'], ['pendingEvaluation', '待评价'], ['evaluated', '已评价'],
]

function getStatus(lecture) {
  const enrollmentMap = {
    pending: { label: '待参与', tone: 'info' },
    missedAttendance: { label: '未完成考勤', tone: 'danger' },
    attended: { label: '已考勤', tone: 'success' },
    pendingEvaluation: { label: '待评价', tone: 'warning' },
    evaluated: { label: '已评价', tone: 'success' },
  }
  if (lecture.joinStatus && enrollmentMap[lecture.joinStatus]) return enrollmentMap[lecture.joinStatus]
  if (lecture.attendanceStatus === 'missed') return enrollmentMap.missedAttendance
  if (lecture.registration === 'enrolled') return { label: '已报名', tone: 'success' }
  const map = {
    open: { label: '可报名', tone: 'success' }, upcoming: { label: '未开放', tone: 'neutral' },
    full: { label: '已满员', tone: 'danger' }, ended: { label: '报名截止', tone: 'neutral' },
    cancelled: { label: '已取消', tone: 'danger' },
  }
  return map[lecture.status] ?? { label: '状态待确认', tone: 'neutral' }
}

function Logo() {
  return <div className="logo"><span className="logo-mark"><GraduationCap size={23} /></span><span><strong>Lecture800</strong><small>ACADEMIC LECTURES</small></span></div>
}

function StatusBadge({ lecture }) {
  const status = getStatus(lecture)
  return <span className={`status-badge ${status.tone}`}><span />{status.label}</span>
}

function capacityText(lecture) {
  if (lecture.attendanceStatus === 'missed') return '接口未记录完成签到'
  if (lecture.attendanceStatus === 'attended') return '接口已记录完成签到'
  if (lecture.registration === 'enrolled') return '已在你的报名记录中'
  if (lecture.status === 'upcoming') return '尚未开放报名'
  if (lecture.status === 'ended') return '本场报名已截止'
  if (lecture.remaining != null) return lecture.remaining > 0 ? `剩余 ${lecture.remaining} 个名额` : '剩余名额为 0'
  return '名额待确认'
}

function LectureCard({ lecture, onSelect, onEnroll, onWithdraw, enrolling = false, enrollDisabled = false, withdrawing = false, compact = false }) {
  const canEnroll = lecture.status === 'open' && !lecture.registration && onEnroll
  return <article className={`lecture-card ${compact ? 'compact' : ''}`}>
    <div className="lecture-card-top"><div className="lecture-labels"><span className={`level-tag level-${lecture.level}`}>{lecture.level} 级</span><span className="category-tag">{lecture.category}</span></div><StatusBadge lecture={lecture} /></div>
    <h3>{lecture.title}</h3><p className="speaker"><UserRound size={15} />{lecture.speaker}</p>
    <div className="lecture-meta"><span><CalendarDays size={16} />{formatDateTime(lecture.startAt, true)}</span><span><MapPin size={16} />{lecture.location}</span></div>
    <div className="lecture-card-bottom"><div className="capacity"><UsersRound size={16} /><span>{capacityText(lecture)}</span></div><div className="card-actions">{canEnroll && <button className="enroll-button" aria-label={`报名${lecture.title}`} disabled={enrolling || enrollDisabled} onClick={() => onEnroll(lecture)}>{enrolling ? '报名中…' : '报名'}</button>}{lecture.canWithdraw && lecture.applyId && onWithdraw && <button className="withdraw-button" disabled={withdrawing} onClick={() => onWithdraw(lecture)}>{withdrawing ? '退课中…' : '退课'}</button>}<button className="icon-button" aria-label={`查看${lecture.title}详情`} onClick={() => onSelect(lecture)}><ChevronRight size={19} /></button></div></div>
  </article>
}

function EmptyState({ title, copy }) {
  return <div className="empty-state"><span><LibraryBig size={28} /></span><h3>{title}</h3><p>{copy}</p></div>
}

function VerificationList({ verification }) {
  const checks = verification?.checks ?? [
    { key: 'session', label: '本机会话', ok: false, detail: '正在验证' },
    { key: 'network', label: 'HTTPS 接口', ok: false, detail: '正在验证' },
    { key: 'lectures', label: '讲座与我的', ok: false, detail: '正在验证' },
  ]
  return <div className="verification-list">{checks.map((check) => <div className="verification-item" key={check.key}><span className={`verification-icon ${check.ok ? 'ok' : 'bad'}`}>{check.ok ? <Check size={15} /> : <X size={15} />}</span><div><strong>{check.label}</strong><p>{check.detail}</p></div><small>{check.ok ? '通过' : '待处理'}</small></div>)}</div>
}

function logView(log, index) {
  const detail = typeof log.detail === 'string' ? log.detail : log.detail?.message
  const titles = {
    scrape: '课程目录采集', enroll: '报名动作', enroll_all: '批量并发报名',
    withdraw: '退课动作', auto_enroll: '每日自动任务', scheduler: '自动任务设置',
    capture: '本机会话配置',
  }
  return {
    id: `${log.time}-${index}`, time: log.time,
    title: titles[log.action] ?? '运行记录',
    message: detail || (log.result === 'failed' ? '执行失败，请检查会话与网络。' : '执行完成。'),
    result: log.result === 'submitted' ? 'success' : log.result === 'failed' || log.result === 'rejected' ? 'skipped' : log.result,
    source: 'HTTPS 接口',
  }
}

export default function App() {
  const [activePage, setActivePage] = useState('overview')
  const [lectures, setLectures] = useState([])
  const [logs, setLogs] = useState([])
  const [mine, setMine] = useState(null)
  const [mineError, setMineError] = useState('')
  const [mineLoading, setMineLoading] = useState(false)
  const [mineTab, setMineTab] = useState('all')
  const [verification, setVerification] = useState(null)
  const [connected, setConnected] = useState(false)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [lastSync, setLastSync] = useState(null)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(null)
  const [toast, setToast] = useState(null)
  const [search, setSearch] = useState('')
  const [filter, setFilter] = useState('all')
  const [settings, setSettings] = useState(null)
  const [settingsSaving, setSettingsSaving] = useState(false)
  const [withdrawTarget, setWithdrawTarget] = useState(null)
  const [withdrawing, setWithdrawing] = useState(false)
  const [withdrawError, setWithdrawError] = useState('')
  const [enrollTarget, setEnrollTarget] = useState(null)
  const [enrolling, setEnrolling] = useState(false)
  const [enrollError, setEnrollError] = useState('')
  const [showAutoConfirm, setShowAutoConfirm] = useState(false)
  const [autoRunning, setAutoRunning] = useState(false)
  const [autoError, setAutoError] = useState('')
  const [autoReceipt, setAutoReceipt] = useState(null)
  const [showSessionSetup, setShowSessionSetup] = useState(false)
  const nextPrecheck = getNextRun('11:58')
  const showToast = useCallback((message, tone = 'success') => setToast({ message, tone }), [])

  const loadMine = useCallback(async (notify = false) => {
    setMineLoading(true)
    try {
      const result = await fetchMine()
      setMine(result)
      setMineError('')
      if (notify) showToast(`已读取个人资料、四项统计和 ${result.applications?.length ?? 0} 条报名记录。`)
      return result
    } catch (reason) {
      setMineError(reason.message || '个人信息接口读取失败')
      return null
    } finally {
      setMineLoading(false)
    }
  }, [showToast])

  const loadData = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true)
    try {
      const [snapshot, operationLogs, checks, currentSettings] = await Promise.all([
        fetchLiveLectures({ refresh: manual }), fetchOperationLogs(), fetchVerification(), fetchSettings(),
      ])
      setLectures(snapshot.lectures)
      setLogs(operationLogs.map(logView))
      setVerification(checks)
      setSettings(currentSettings)
      setConnected(Boolean(snapshot.connected && checks.connected))
      setLastSync(snapshot.fetchedAt)
      setError('')
      loadMine(false)
      if (manual) showToast(`已通过接口同步 ${snapshot.lectures.length} 场 800 级讲座。`)
    } catch (reason) {
      setConnected(false)
      setError(reason.message || '无法连接学校接口')
      try {
        const [checks, currentSettings] = await Promise.all([fetchVerification(), fetchSettings()])
        setVerification(checks)
        setSettings(currentSettings)
      } catch {}
      if (manual) showToast(reason.message || '同步失败，请检查登录会话。', 'warning')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [loadMine, showToast])

  const handleCaptureVerified = useCallback(async () => {
    await loadData(false)
    showToast('本机会话配置完成，讲座与我的信息已通过 HTTPS 接口验证。')
  }, [loadData, showToast])

  const confirmEnroll = useCallback(async () => {
    if (!enrollTarget || enrolling || autoRunning) return
    setEnrolling(true)
    setEnrollError('')
    try {
      const result = await enrollLecture(enrollTarget.id)
      setEnrollTarget(null)
      await loadData(false)
      showToast(result.message || '报名成功，已在我的报名中核验到该讲座。')
    } catch (reason) {
      setEnrollError(reason.message || '报名未完成，请先查询我的报名')
    } finally {
      setEnrolling(false)
    }
  }, [enrollTarget, enrolling, autoRunning, loadData, showToast])

  const confirmAutoNow = useCallback(async () => {
    if (autoRunning || enrolling) return
    setAutoRunning(true)
    setAutoError('')
    try {
      const result = await enrollAllLectures()
      setAutoReceipt(result)
      setShowAutoConfirm(false)
      await loadData(false)
      showToast(result.message || `即时抢课完成，核验到 ${result.verifiedCount ?? 0} 场。`, result.verified ? 'success' : 'warning')
    } catch (reason) {
      if (reason.result) {
        setAutoReceipt(reason.result)
        setShowAutoConfirm(false)
        await loadData(false)
        showToast(reason.message || '部分课程未通过回执核验，请查看结果明细。', 'warning')
      } else {
        setAutoError(reason.message || '即时抢课未能完成')
      }
    } finally {
      setAutoRunning(false)
    }
  }, [autoRunning, enrolling, loadData, showToast])

  const confirmWithdraw = useCallback(async () => {
    if (!withdrawTarget || withdrawing) return
    setWithdrawing(true)
    setWithdrawError('')
    try {
      await withdrawLecture({ lectureId: withdrawTarget.id, applyId: withdrawTarget.applyId })
      setWithdrawTarget(null)
      await loadData(false)
      showToast('退课成功，已确认该讲座从我的报名中移除。')
    } catch (reason) {
      setWithdrawError(reason.message || '退课失败，请稍后查询我的报名')
    } finally {
      setWithdrawing(false)
    }
  }, [withdrawTarget, withdrawing, loadData, showToast])

  const toggleAuto = useCallback(async () => {
    if (!settings || settingsSaving) return
    setSettingsSaving(true)
    try {
      const result = await setAutoEnabled(!settings.autoEnabled)
      setSettings(result)
      showToast(`自动报名已${result.autoEnabled ? '开启' : '关闭'}；开启时每天 12:00 并发报名全部符合条件的课程。`)
    } catch (reason) {
      showToast(reason.message || '设置失败', 'warning')
    } finally {
      setSettingsSaving(false)
    }
  }, [settings, settingsSaving, showToast])

  const toggleLocationRule = useCallback(async (key) => {
    if (!settings || settingsSaving) return
    const nextRules = { ...normalizeLocationRules(settings.locationRules), [key]: !normalizeLocationRules(settings.locationRules)[key] }
    setSettingsSaving(true)
    try {
      const result = await setLocationRules(nextRules)
      setSettings(result)
      showToast(`已保存地点选择：${LOCATION_OPTIONS.filter((item) => result.locationRules[item.key]).map((item) => item.label).join('、') || '未选择任何地点'}。`)
    } catch (reason) {
      showToast(reason.message || '地点规则保存失败', 'warning')
    } finally {
      setSettingsSaving(false)
    }
  }, [settings, settingsSaving, showToast])

  useEffect(() => {
    loadData()
    const timer = window.setInterval(() => loadData(), 15000)
    return () => window.clearInterval(timer)
  }, [loadData])

  useEffect(() => {
    if (!toast) return
    const timer = window.setTimeout(() => setToast(null), 4000)
    return () => window.clearTimeout(timer)
  }, [toast])

  const myLectures = mine?.applications?.length ? mine.applications : lectures.filter((lecture) => lecture.registration)
  const visibleMineLectures = mineTab === 'all' ? myLectures : (mine?.groups?.[mineTab] ?? [])
  const locationRules = normalizeLocationRules(settings?.locationRules ?? DEFAULT_LOCATION_RULES)
  const selectedLocations = LOCATION_OPTIONS.filter((item) => locationRules[item.key]).map((item) => item.label)
  const openTarget = selectOpenCandidates(lectures, locationRules)
  const fullCount = lectures.filter((lecture) => lecture.status === 'full').length
  const upcomingCount = lectures.filter((lecture) => lecture.status === 'upcoming').length
  const filteredLectures = useMemo(() => lectures.filter((lecture) => {
    const matchesSearch = `${lecture.title}${lecture.speaker}${lecture.location}${lecture.category}`.toLowerCase().includes(search.toLowerCase())
    const matchesFilter = filter === 'all' || (filter === '800' && lecture.level === '800') ||
      (filter === 'open' && lecture.status === 'open' && !lecture.registration) || (filter === 'mine' && lecture.registration) ||
      (filter === 'upcoming' && lecture.status === 'upcoming') || (filter === 'full' && lecture.status === 'full')
    return matchesSearch && matchesFilter
  }), [lectures, search, filter])

  function navigate(page) {
    setActivePage(page)
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const [title, subtitle] = PAGE_COPY[activePage]
  return <div className="app-shell dark-theme">
    <aside className="sidebar">
      <div className="sidebar-head"><Logo /></div>
      <nav>{NAV_ITEMS.map((item) => <button key={item.id} className={activePage === item.id ? 'active' : ''} onClick={() => navigate(item.id)}><item.icon size={19} /><span>{item.label}</span>{item.id === 'mine' && myLectures.length > 0 && <b>{myLectures.length}</b>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="demo-mode"><span className={`pulse-dot ${connected ? '' : 'paused'}`} /><div><strong>HTTPS 接口直连</strong><small>{connected ? '会话与接口验证通过' : '等待已登录会话'}</small></div></div><div className="account-row"><span className="avatar"><MonitorCheck size={17} /></span><div><strong>Lecture800 本机版</strong><small>会话由 Windows 加密保存</small></div></div></div>
    </aside>

    <main className="main-content">
      <header className="topbar"><div><h1>{title}</h1><p>{subtitle}</p></div><div className="topbar-right"><span className={`environment-pill ${connected ? 'online' : 'offline'}`}><ShieldCheck size={15} />{connected ? '接口已连接' : '等待会话验证'}</span><button className="notification-button" aria-label="立即刷新" disabled={refreshing} onClick={() => loadData(true)}><RefreshCw size={19} className={refreshing ? 'spinning' : ''} /></button></div></header>
      <div className="page-content">
        {!connected && <div className="connection-banner" role="alert"><AlertCircle size={18} /><div><strong>{loading ? '正在验证登录会话…' : '实时接口暂不可用'}</strong><p>{error || '请先完成本人已登录会话的本机捕获与验证。'}</p></div><div className="connection-actions"><button className="button primary small" onClick={() => setShowSessionSetup(true)}>配置本机会话</button><button className="button secondary small" onClick={() => navigate('guide')}>查看说明</button></div></div>}

        {activePage === 'overview' && <>
          <section className="automation-hero"><div className="hero-copy"><span className="eyebrow light"><Sparkles size={14} /> 即时执行 · 每日 12:00 自动执行</span><h2>现在抢课，不必等到 12:00</h2><p>当前候选 {openTarget.length} 场，地点：{selectedLocations.join('、') || '未选择'}。立即执行与每日任务使用相同规则；提交后逐场核验“我的报名”。</p><div className="hero-actions"><button className="button lime" disabled={!connected || autoRunning || enrolling} onClick={() => { setAutoError(''); setShowAutoConfirm(true) }}><Sparkles size={17} />{autoRunning ? '正在即时抢课…' : '立即开始自动抢课'}</button><button className="button ghost-light" disabled={refreshing || autoRunning} onClick={() => loadData(true)}><RefreshCw size={16} className={refreshing ? 'spinning' : ''} />刷新目录</button><button className="button ghost-light" onClick={() => navigate('settings')}>每日设置<ChevronRight size={17} /></button></div></div><div className="next-run-card"><span>每日任务仍保留</span><strong>11:58</strong><small>{formatDateTime(nextPrecheck, true)} 预检 · 12:00 自动抢课</small><div><span className={`pulse-dot ${settings?.autoEnabled ? '' : 'paused'}`} />{settings?.autoEnabled ? '每日自动报名已启用' : '每日自动报名已暂停'}</div></div></section>
          <div className="demo-disclaimer"><AlertCircle size={17} /><span>目录由学校接口分页返回，每 15 秒同步；不是窗口截图或当前可见卡片。最后同步：{formatSyncTime(lastSync)}</span></div>
          <section className="stats-grid"><div className="stat-card"><span className="stat-icon green"><LibraryBig /></span><div><small>接口目录</small><strong>{lectures.length}</strong><p>800 级讲座</p></div></div><div className="stat-card"><span className="stat-icon blue"><BookOpenCheck /></span><div><small>可报名</small><strong>{openTarget.length}</strong><p>800 级目标讲座</p></div></div><div className="stat-card"><span className="stat-icon amber"><UsersRound /></span><div><small>已满员</small><strong>{fullCount}</strong><p>剩余名额为 0</p></div></div><div className="stat-card"><span className="stat-icon violet"><Clock3 /></span><div><small>未开放</small><strong>{upcomingCount}</strong><p>等待报名开放</p></div></div></section>
          <div className="overview-grid"><section className="section-block"><div className="section-heading"><div><h2>优先关注</h2><p>可报名与即将开放的讲座</p></div><button className="text-button" onClick={() => navigate('lectures')}>查看全部<ChevronRight size={16} /></button></div><div className="lecture-list">{[...openTarget, ...lectures.filter((l) => l.status === 'upcoming')].slice(0, 3).map((lecture) => <LectureCard key={lecture.id} lecture={lecture} onSelect={setSelected} onEnroll={(target) => { setEnrollError(''); setEnrollTarget(target) }} enrolling={enrolling && enrollTarget?.id === lecture.id} enrollDisabled={autoRunning} compact />)}{!openTarget.length && !upcomingCount && <EmptyState title="暂无待关注讲座" copy="当前接口目录没有可报名或未开放的讲座。" />}</div></section><section className="section-block activity-block"><div className="section-heading"><div><h2>连接验证</h2><p>确认加密会话、HTTPS 请求与数据可用</p></div><button className="text-button" onClick={() => navigate('settings')}>完整状态<ChevronRight size={16} /></button></div><VerificationList verification={verification} /></section></div>
        </>}

        {activePage === 'lectures' && <section className="section-block catalog-section"><div className="catalog-tools"><div className="search-box"><Search size={18} /><input aria-label="搜索讲座" placeholder="搜索讲座、主讲人或地点" value={search} onChange={(e) => setSearch(e.target.value)} />{search && <button onClick={() => setSearch('')} aria-label="清空搜索"><X size={16} /></button>}</div><span className="result-count">{filteredLectures.length} 场讲座</span></div><div className="filter-row"><ListFilter size={17} />{[['all', '全部'], ['800', '800 级'], ['open', '可报名'], ['upcoming', '未开放'], ['mine', '我的'], ['full', '已满员']].map(([id, label]) => <button key={id} className={filter === id ? 'active' : ''} onClick={() => setFilter(id)}>{label}</button>)}</div><div className="lecture-grid">{filteredLectures.map((lecture) => <LectureCard key={lecture.id} lecture={lecture} onSelect={setSelected} onEnroll={(target) => { setEnrollError(''); setEnrollTarget(target) }} enrolling={enrolling && enrollTarget?.id === lecture.id} enrollDisabled={autoRunning} />)}{!filteredLectures.length && <EmptyState title="没有匹配的讲座" copy="试试更换搜索关键词或状态筛选。" />}</div></section>}

        {activePage === 'mine' && <>
          <section className="section-block mine-panel"><div className="section-heading"><div><h2>我的接口数据</h2><p>个人资料、统计与报名独立请求，无需切换小程序页面</p></div><button className="button secondary small" disabled={mineLoading} onClick={() => loadMine(true)}><RefreshCw size={15} className={mineLoading ? 'spinning' : ''} />{mineLoading ? '正在读取…' : '同步我的信息'}</button></div>
            {mineError && <div className="inline-notice warning"><AlertCircle size={17} /><span>{mineError}</span></div>}
            {mine && <><div className="verified-line"><CheckCircle2 size={17} />接口验证通过 · {formatSyncTime(mine.fetchedAt)}</div>
              <div className="mine-profile"><span className="avatar"><UserRound size={20} /></span><div><small>账号／学号</small><strong>{mine.profile?.account || '接口未返回'}</strong></div>{mine.profile?.role && <span className="category-tag">{mine.profile.role}</span>}</div>
              <div className="mine-metrics">{(mine.metrics ?? []).map((metric) => <div className="mine-metric" key={metric.label}><strong>{metric.value}</strong><span>{metric.label}</span></div>)}</div>
            </>}
            {!mine && !mineError && <EmptyState title="等待读取我的信息" copy="验证登录会话后，软件会直接请求个人信息接口。" />}
          </section>
          <section className="section-block catalog-section mine-lectures"><div className="mine-summary"><div><span className="stat-icon green"><BookOpenCheck /></span><div><strong>{visibleMineLectures.length}</strong><small>{MINE_TABS.find(([id]) => id === mineTab)?.[1]}记录</small></div></div><p>与讲座目录并发读取，不会互相覆盖</p></div><div className="filter-row" aria-label="我的报名分类">{MINE_TABS.map(([id, label]) => <button key={id} className={mineTab === id ? 'active' : ''} aria-pressed={mineTab === id} onClick={() => setMineTab(id)}>{label}{id !== 'all' && ` ${mine?.groups?.[id]?.length ?? 0}`}</button>)}</div><div className="lecture-grid">{visibleMineLectures.map((lecture) => <LectureCard key={lecture.id} lecture={lecture} onSelect={setSelected} onWithdraw={(target) => { setWithdrawError(''); setWithdrawTarget(target) }} withdrawing={withdrawing && withdrawTarget?.id === lecture.id} />)}{!visibleMineLectures.length && <EmptyState title={`暂无${MINE_TABS.find(([id]) => id === mineTab)?.[1]}项目`} copy="学校接口当前未返回此分类的讲座记录。" />}</div></section>
        </>}

        {activePage === 'logs' && <section className="section-block logs-section"><div className="section-heading"><div><h2>执行时间线</h2><p>最新记录排在前面</p></div><button className="button secondary small" disabled={refreshing} onClick={() => loadData(true)}><RefreshCw size={15} />立即刷新</button></div><div className="timeline">{logs.map((log) => <article className="log-item" key={log.id}><span className={`log-icon ${log.result}`}>{log.result === 'success' ? <Check size={19} /> : <AlertCircle size={19} />}</span><div className="log-body"><div><StatusLog result={log.result} /><span className="source-tag">{log.source}</span><time>{formatDateTime(log.time, true)}</time></div><h3>{log.title}</h3><p>{log.message}</p></div></article>)}{!logs.length && <EmptyState title="暂无运行记录" copy="异常、预检与报名动作会在这里留下记录。" />}</div></section>}

        {activePage === 'settings' && <div className="settings-grid">
          <section className="section-block settings-card">
            <div className="section-heading"><div><h2>自动报名策略</h2><p>只保留影响每日执行的核心选项，修改后立即保存</p></div><span className="stat-icon green"><Settings /></span></div>
            <div className="automation-master"><div><div className="setting-title">每日自动报名 <span className="setting-lock">全部并发 · 回执核验</span></div><p>仅报名 800 级、可报名且未报名的课程；需保持 EXE 运行</p></div><button role="switch" aria-checked={settings?.autoEnabled ?? false} aria-label="自动抢课" className={`switch ${settings?.autoEnabled ? 'on' : ''}`} disabled={!settings || settingsSaving} onClick={toggleAuto}><span /></button></div>
            <div className="schedule-strip" aria-label="每日执行链路"><div><span>01</span><strong>11:58</strong><small>会话与候选预检</small></div><ChevronRight size={17} /><div><span>02</span><strong>12:00</strong><small>全部候选并发提交</small></div><ChevronRight size={17} /><div><span>03</span><strong>随后</strong><small>逐场回执核验</small></div></div>
            <section className="location-settings" aria-labelledby="location-title"><div className="location-heading"><div><h3 id="location-title">开课地点</h3><p>勾选的地点才会进入自动报名，取消勾选即排除</p></div><span>{selectedLocations.length} / {LOCATION_OPTIONS.length} 已选</span></div><div className="location-option-grid">{LOCATION_OPTIONS.map((item) => <button key={item.key} role="checkbox" aria-checked={locationRules[item.key]} aria-label={item.label} className={`location-option ${locationRules[item.key] ? 'selected' : ''}`} disabled={!settings || settingsSaving} onClick={() => toggleLocationRule(item.key)}><span className="location-check">{locationRules[item.key] && <Check size={14} />}</span><span><strong>{item.label}</strong><small>{item.detail}</small></span></button>)}</div>{!selectedLocations.length && <div className="inline-notice warning"><AlertCircle size={17} /><span>当前未选择任何地点，每日任务不会提交报名。</span></div>}<p className="setting-footnote">候选列表中一号院优先，其余按开课时间排序；所有候选同时并发提交。学校服务器、网络和名额仍可能影响结果。</p></section>
          </section>
          <div className="settings-side"><section className="section-block task-status-card"><div className="section-heading"><div><h2>下一次执行</h2><p>核心状态一目了然</p></div><span className={`pulse-dot ${settings?.autoEnabled ? '' : 'paused'}`} /></div><strong className="task-time">11:58</strong><p>{formatDateTime(nextPrecheck, true)} 预检，12:00 报名</p><dl><div><dt>当前候选</dt><dd>{openTarget.length} 场</dd></div><div><dt>任务状态</dt><dd>{settings?.runtime?.running ? '正在执行' : settings?.autoEnabled ? '已启用' : '已暂停'}</dd></div><div><dt>已选地点</dt><dd>{selectedLocations.length} 类</dd></div></dl></section><section className="section-block security-card"><span className="stat-icon blue"><ListChecks /></span><h2>连接验证</h2><div className="setup-notice session-reuse-note"><ShieldCheck size={18} /><div><strong>再次打开 EXE，无需同步打开微信小程序</strong><p>配置成功后，程序会复用本机加密会话直接访问接口。仅在会话失效、换电脑／Windows 用户或连接验证失败时，才需重新打开小程序配置。</p></div></div><VerificationList verification={verification} /><p className="setting-footnote">不要复制旧电脑的加密会话；需要重新配置时，在 EXE 内打开向导。</p><button className="button secondary full" onClick={() => setShowSessionSetup(true)}><ShieldCheck size={16} />配置／重新配置会话</button></section><section className="section-block reset-card"><p>最后同步：{formatSyncTime(lastSync)}</p><button className="button secondary" disabled={refreshing} onClick={() => loadData(true)}><RefreshCw size={16} />立即同步</button></section></div>
        </div>}

        {activePage === 'guide' && <div className="guide-grid"><section className="section-block guide-main"><div className="section-heading"><div><h2>首次使用，按这 5 步操作</h2><p>适用于 Lecture800 Windows 桌面端</p></div><CircleHelp /></div><ol className="guide-steps"><li><span>1</span><div><h3>本人登录小程序</h3><p>在 Windows 微信中登录“科大微门户”，进入“研究生学术讲座信息化平台”。软件不索取账号密码。</p></div></li><li><span>2</span><div><h3>授权并验证本机会话</h3><p>仅在明确授权后捕获目标学校域名的登录会话。会话用当前 Windows 用户的 DPAPI 加密保存，界面只显示验证结果，不显示 Token 或 Cookie。</p><p>点击“打开内置配置向导”，按提示重新打开讲座页面；成功、取消或超时都会停止捕获并清理临时证书，不修改系统代理。</p><button className="button secondary small" onClick={() => setShowSessionSetup(true)}>打开内置配置向导</button></div></li><li><span>3</span><div><h3>确认三项连接验证通过</h3><p>首页和设置页会实际请求学校接口。讲座与“我的”可独立并发读取，无需保持小程序在前台，也不依赖屏幕截图或控件。</p></div></li><li><span>4</span><div><h3>选择地点并开启每日任务</h3><p>在设置页勾选允许自动报名的校区和开课地点，再打开“自动抢课”。开关与地点规则都会立即保存，不需要另建 Windows 定时任务。</p></div></li><li><span>5</span><div><h3>手动、即时或每日自动报名</h3><p>可报名讲座的卡片和详情页提供“手动报名”；首页“立即开始自动抢课”会按当前地点规则立即并发提交全部候选。每天 11:58 预检、12:00 自动任务仍然保留。所有操作逐场以“我的报名”为回执，未核验到不记为成功，也不会自动重发。</p></div></li></ol><div className="setup-notice session-reuse-note"><ShieldCheck size={18} /><div><strong>再次打开 EXE，无需同步打开微信小程序</strong><p>配置成功后，程序会复用本机加密会话直接访问接口。仅在会话失效、换电脑／Windows 用户或连接验证失败时，才需重新打开小程序配置。</p></div></div></section><div className="guide-side"><section className="section-block security-card"><span className="stat-icon green"><ShieldCheck /></span><h2>实现原理与限制</h2><p className="guide-copy">首次从本人已登录流量捕获 Cookie／Token，之后由 Python requests 直接请求学校 H5 接口并保存服务端下发的新会话。12:00 秒级触发并并发提交可缩短耗时，但受学校服务器、名额和网络影响，不能保证全部抢到或长期无人值守。</p></section><section className="section-block security-card"><span className="stat-icon amber"><BookOpenCheck /></span><h2>考勤分类与退课</h2><p className="guide-copy">接口签到字段为 1 时归为“已考勤”；讲座已结束且未记录签到时归为“未完成考勤”，与“待评价／已评价”分开显示。可退课程会显示“退课”，必须二次确认，并重新查询报名记录确认移除后才记为成功。</p></section><section className="section-block security-card"><span className="stat-icon blue"><MonitorCheck /></span><h2>EXE 移植要求</h2><ul><li>单 EXE 可启动不等于免配置抢课，也不保证报名成功</li><li>Windows 10／11，需要 Microsoft Edge WebView2，无需另装 Python 或 Node.js</li><li>复制到可写目录；任务与数据保存在 EXE 旁的 Lecture800-data</li><li>首次配置已内置：在设置页或使用说明中打开配置向导</li><li>新电脑必须重新捕获；如提示权限不足，需手动以管理员身份运行</li><li>DPAPI 会话绑定原电脑和 Windows 用户，复制数据目录不能迁移登录</li><li>每天保持 EXE 运行、电脑不睡眠、网络可用且会话有效</li></ul></section><section className="section-block security-card"><span className="stat-icon amber"><Clock3 /></span><h2>每日时间线</h2><ul><li>11:58：会话、接口与全部候选课程预检</li><li>12:00：重新读取并并发提交全部候选</li><li>提交后：统一查询“我的报名”，逐场核验结果</li></ul></section></div></div>}
      </div>
    </main>

    {selected && <div className="modal-backdrop" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setSelected(null) }}><section className="lecture-modal" role="dialog" aria-modal="true" aria-label="讲座详情"><button className="modal-close" onClick={() => setSelected(null)} aria-label="关闭详情"><X /></button><div className="lecture-labels"><span className={`level-tag level-${selected.level}`}>{selected.level} 级</span><StatusBadge lecture={selected} /></div><h2>{selected.title}</h2><p className="speaker"><UserRound size={17} />{selected.speaker}{selected.teacherJob ? ` · ${selected.teacherJob}` : ''}</p><p className="modal-description">{selected.description || '该讲座暂无详细介绍。'}</p><dl><div><dt><CalendarDays size={17} />讲座时间</dt><dd>{formatDateTime(selected.startAt, true)}{selected.endAt ? ` — ${formatDateTime(selected.endAt)}` : ''}</dd></div><div><dt><MapPin size={17} />讲座地点</dt><dd>{selected.location}</dd></div><div><dt><Clock3 size={17} />报名开放</dt><dd>{formatDateTime(selected.enrollmentOpenAt, true)}</dd></div><div><dt><UsersRound size={17} />名额情况</dt><dd>{capacityText(selected)}{selected.capacity != null ? ` / 共 ${selected.capacity} 人` : ''}</dd></div></dl><div className="modal-actions">{selected.status === 'open' && !selected.registration && <button className="button primary" disabled={autoRunning} onClick={() => { setEnrollError(''); setEnrollTarget(selected); setSelected(null) }}>手动报名</button>}<button className="button secondary" onClick={() => setSelected(null)}>关闭</button></div></section></div>}
    {enrollTarget && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (!enrolling && event.target === event.currentTarget) setEnrollTarget(null) }}><section className="lecture-modal" role="dialog" aria-modal="true" aria-label="确认手动报名"><button className="modal-close" disabled={enrolling} onClick={() => setEnrollTarget(null)} aria-label="关闭报名确认"><X /></button><span className="stat-icon green"><BookOpenCheck /></span><h2>确认手动报名</h2><p className="withdraw-confirm-copy">即将报名：<strong>{enrollTarget.title}</strong><br />{enrollTarget.location} · {formatDateTime(enrollTarget.startAt, true)}<br />只发送一次报名请求，并重新查询“我的报名”核验结果；未核验到不会记为成功。</p>{enrollError && <div className="inline-notice warning" role="alert"><AlertCircle size={17} /><span>{enrollError}</span></div>}<div className="modal-actions"><button className="button secondary" disabled={enrolling} onClick={() => setEnrollTarget(null)}>暂不</button><button className="button primary" disabled={enrolling} onClick={confirmEnroll}>{enrolling ? '正在报名并核验…' : '确认报名'}</button></div></section></div>}
    {showAutoConfirm && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (!autoRunning && event.target === event.currentTarget) setShowAutoConfirm(false) }}><section className="lecture-modal" role="dialog" aria-modal="true" aria-label="确认立即自动抢课"><button className="modal-close" disabled={autoRunning} onClick={() => setShowAutoConfirm(false)} aria-label="关闭即时抢课确认"><X /></button><span className="stat-icon green"><Sparkles /></span><h2>立即开始自动抢课？</h2><p className="withdraw-confirm-copy">现在按当前地点规则并发提交全部候选课程，<strong>不是等到 12:00</strong>。本次预计处理 {openTarget.length} 场；每天 11:58 预检和 12:00 自动任务仍保留，每日开关状态不受影响。</p><div className="capture-facts"><span>地点：{selectedLocations.join('、') || '未选择'}</span><span>执行方式：全部候选并发</span><span>结果：逐场回执核验</span></div>{autoError && <div className="inline-notice warning" role="alert"><AlertCircle size={17} /><span>{autoError}</span></div>}<div className="modal-actions"><button className="button secondary" disabled={autoRunning} onClick={() => setShowAutoConfirm(false)}>取消</button><button className="button primary" disabled={autoRunning} onClick={confirmAutoNow}>{autoRunning ? '正在并发抢课…' : '确认立即抢课'}</button></div></section></div>}
    {autoReceipt && <div className="modal-backdrop" role="presentation"><section className="lecture-modal" role="dialog" aria-modal="true" aria-label="即时抢课结果"><button className="modal-close" onClick={() => setAutoReceipt(null)} aria-label="关闭即时抢课结果"><X /></button><span className={`stat-icon ${autoReceipt.verified ? 'green' : 'amber'}`}>{autoReceipt.verified ? <CheckCircle2 /> : <AlertCircle />}</span><h2>即时抢课结果</h2><div className="auto-result-summary"><div><strong>{autoReceipt.submittedCount ?? 0}</strong><span>已提交</span></div><div><strong>{autoReceipt.verifiedCount ?? 0}</strong><span>已核验</span></div><div><strong>{autoReceipt.results?.length ?? 0}</strong><span>处理课程</span></div></div><p className="guide-copy">{autoReceipt.message}</p><div className="auto-result-list">{(autoReceipt.results ?? []).map((item) => <article key={item.id}><div><strong>{item.title}</strong><small>{item.location || '地点待确认'}</small></div><span className={item.verified ? 'verified' : 'unverified'}>{item.verified ? '已抢到' : item.error || '未核验到'}</span></article>)}</div><p className="setting-footnote">未核验到的课程不会自动重发；请先查看“我的信息”。每天 12:00 的自动任务设置保持不变。</p><div className="modal-actions"><button className="button primary" onClick={() => setAutoReceipt(null)}>完成</button></div></section></div>}
    {withdrawTarget && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (!withdrawing && event.target === event.currentTarget) setWithdrawTarget(null) }}><section className="lecture-modal" role="dialog" aria-modal="true" aria-label="确认退课"><button className="modal-close" disabled={withdrawing} onClick={() => setWithdrawTarget(null)} aria-label="关闭退课确认"><X /></button><h2>确认退课</h2><p className="withdraw-confirm-copy">即将退掉：<strong>{withdrawTarget.title}</strong><br />此操作会向学校接口发送一次真实退课请求，可能无法恢复名额。只有重新查询“我的报名”并确认记录消失后，才会显示退课成功。</p>{withdrawError && <div className="inline-notice warning" role="alert"><AlertCircle size={17} /><span>{withdrawError}</span></div>}<div className="modal-actions"><button className="button secondary" disabled={withdrawing} onClick={() => setWithdrawTarget(null)}>暂不</button><button className="button danger" disabled={withdrawing} onClick={confirmWithdraw}>{withdrawing ? '正在退课并核验…' : '确认退课'}</button></div></section></div>}
    {showSessionSetup && <SessionSetup onClose={() => setShowSessionSetup(false)} onVerified={handleCaptureVerified} />}
    {toast && <div className={`toast ${toast.tone}`} role="status">{toast.tone === 'success' ? <CheckCircle2 size={20} /> : <AlertCircle size={20} />}<span>{toast.message}</span><button onClick={() => setToast(null)} aria-label="关闭提示"><X size={16} /></button></div>}
  </div>
}

function StatusLog({ result }) {
  const copy = { success: '执行成功', skipped: '未执行', failed: '执行失败', blocked_unverified: '路径待验证' }
  return <span className={`log-status ${result}`}>{copy[result] ?? '执行记录'}</span>
}
