import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, Check, CheckCircle2, MonitorCheck, ShieldCheck, X } from 'lucide-react'
import { cancelCapture, fetchCaptureStatus, startCapture } from './lib/liveApi'

const STEPS = [
  { title: '启动捕获引擎', copy: '仅接管微信小程序进程，不修改系统代理' },
  { title: '证书与自检', copy: '安装本次专用临时证书，确认引擎已就绪' },
  { title: '等待微信请求', copy: '重新进入讲座平台，或切换一次“我的”' },
  { title: '识别登录会话', copy: '只保留目标接口的 Cookie／Token 并加密' },
  { title: '只读接口验证', copy: '通过 HTTPS 读取讲座与我的信息，不报名' },
  { title: '清理并完成', copy: '移除临时证书、捕获进程和本地证书文件' },
]

const STAGE_INDEX = {
  engine: 0, certificate: 1, selftest: 1, wechat: 2,
  session: 3, cleanup: 4, verify: 4, done: 6,
}

function stageIndex(status) {
  if (!status) return -1
  if (status.state === 'success') return STEPS.length
  if (status.stage in STAGE_INDEX) return STAGE_INDEX[status.stage]
  return { starting: 0, waiting: 2, verifying: 4 }[status.state] ?? -1
}

function stepState(index, status) {
  const current = stageIndex(status)
  if (status?.state === 'success') return 'done'
  if (status?.active || status?.state === 'error') {
    if (index < current) return 'done'
    if (index === current) return 'active'
  }
  return ''
}

function formatSeconds(value) {
  const seconds = Math.max(0, Number(value) || 0)
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}

function recoveryHint(status) {
  if (!status) return ''
  if (status.state === 'error') {
    const hints = {
      engine: '引擎未能启动。请关闭其他抓包软件，并以管理员身份运行 EXE 后重试。',
      certificate: '卡在临时证书安装。请确认当前 Windows 用户可写入证书存储，并以管理员身份重试。',
      selftest: '证书已处理，但引擎尚未报告就绪。请停止后重试；若仍失败，请关闭其他抓包软件。',
      wechat: '引擎已就绪但未收到微信请求。请完全关闭“科大微门户”窗口，再从微信搜索重新打开。',
      session: '已收到请求，但未识别登录信息。请重新进入讲座平台，再切换一次“我的”。',
      cleanup: '会话已保存，但临时组件清理未完成。请检查证书存储后重试。',
      verify: '会话已捕获，但 HTTPS 验证未通过。请检查网络后重试，旧会话不会被覆盖。',
    }
    return hints[status.stage] || '请按上方停下的阶段处理后重新尝试。'
  }
  if (status.state === 'waiting' && status.stage === 'session') {
    return `已收到 ${status.requestPath || '目标请求'}。现在切换一次“我的”，或重新进入讲座平台；无需反复点击。`
  }
  if (status.state === 'waiting' && Number(status.elapsedSeconds) >= 20) {
    return '仍未收到微信请求：请完全关闭“科大微门户”窗口，再从微信搜索重新打开；不需要退出微信。'
  }
  if (status.state === 'waiting') {
    return '现在请在微信中进入“科大微门户 → 应用 → 研究生学术讲座”。页面加载后，可再切换一次“我的”。'
  }
  if (status.state === 'verifying') return '无需操作微信。正在自动验证并清理，请勿关闭 Lecture800。'
  return ''
}

export default function SessionSetup({ onClose, onVerified }) {
  const [status, setStatus] = useState(null)
  const [authorized, setAuthorized] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    const result = await fetchCaptureStatus()
    setStatus(result)
    return result
  }, [])

  useEffect(() => {
    let disposed = false
    let notified = false
    let timer
    async function poll() {
      try {
        const result = await refresh()
        if (result.state === 'success' && !notified) {
          notified = true
          await onVerified()
        }
      } catch (reason) {
        if (!disposed) setError(reason.message || '无法读取配置状态')
      } finally {
        if (!disposed) timer = window.setTimeout(poll, 750)
      }
    }
    poll()
    return () => { disposed = true; window.clearTimeout(timer) }
  }, [refresh, onVerified])

  async function begin() {
    if (!authorized || busy) return
    setBusy(true)
    setError('')
    try {
      const result = await startCapture()
      setStatus(result)
      setAuthorized(false)
    } catch (reason) {
      setError(reason.message || '会话配置未能启动')
    } finally {
      setBusy(false)
    }
  }

  async function stop(closeAfter = false) {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      if (status?.active) {
        const result = await cancelCapture()
        setStatus(result)
      }
      if (closeAfter) onClose()
    } catch (reason) {
      setError(reason.message || '无法停止会话配置')
    } finally {
      setBusy(false)
    }
  }

  const active = Boolean(status?.active)
  const success = status?.state === 'success'
  const current = stageIndex(status)
  const hint = recoveryHint(status)
  const title = success ? '连接验证通过' : status?.state === 'error' ? '配置停在这里' : active ? `当前：${STEPS[current]?.title || '配置中'}` : '安全捕获说明'

  return <div className="modal-backdrop" role="presentation">
    <section className="lecture-modal setup-modal" role="dialog" aria-modal="true" aria-label="配置本机会话">
      <button className="modal-close" disabled={busy} onClick={() => stop(true)} aria-label="关闭会话配置"><X /></button>
      <span className="stat-icon green"><ShieldCheck /></span>
      <h2>配置本机会话</h2>
      <p className="setup-intro">在新电脑或会话失效时使用。无需提供账号密码，后续讲座读取和报名均通过 HTTPS 接口完成。</p>

      <div className="setup-notice"><MonitorCheck size={18} /><div><strong>你只需操作微信一次</strong><p>先点击“开始本机配置”，等到第 3 步高亮后，再进入“科大微门户 → 应用 → 研究生学术讲座”。</p></div></div>
      <ol className="setup-steps">{STEPS.map((step, index) => {
        const currentStep = stepState(index, status)
        return <li key={step.title} className={currentStep}><span>{currentStep === 'done' ? <Check size={15} /> : index + 1}</span><div><strong>{step.title}</strong><p>{step.copy}</p></div></li>
      })}</ol>

      <div className={`capture-status ${success ? 'success' : status?.state === 'error' ? 'error' : ''}`} role="status" aria-live="polite">
        {success ? <CheckCircle2 size={18} /> : status?.state === 'error' ? <AlertCircle size={18} /> : <ShieldCheck size={18} />}
        <div><strong>{title}</strong><p>{error || status?.detail || '只保留目标学校接口的 Cookie／Token，并用当前 Windows 用户的 DPAPI 加密；不保存请求正文，不显示密钥。'}</p></div>
      </div>
      {hint && <p className="setup-help">{status?.state === 'waiting' ? '有效操作窗口为 10 分钟。' : ''}{hint}</p>}
      {success && status.verification && <div className="capture-receipt"><CheckCircle2 size={16} /><span>HTTPS 已验证：读取 {status.verification.lectureCount} 场 800 级讲座、{status.verification.applicationCount} 条报名记录；临时证书已移除，未提交报名。</span></div>}
      {status && <div className="capture-facts"><span>系统代理：未修改</span><span>捕获范围：微信小程序进程</span><span>管理员权限：{status.isAdministrator ? '已具备' : '未启用'}</span>{active && <span>已进行 {formatSeconds(status.elapsedSeconds)} · 剩余 {formatSeconds(status.remainingSeconds)}</span>}{success && <span>本次用时 {formatSeconds(status.elapsedSeconds)}</span>}</div>}
      {!active && !success && <label className="capture-consent"><input type="checkbox" checked={authorized} disabled={busy} onChange={(event) => setAuthorized(event.target.checked)} /><span>我明确授权在本机临时捕获目标学校域名的本人登录会话，并了解临时证书将在结束后移除。</span></label>}
      <div className="modal-actions">
        <button className="button secondary" disabled={busy} onClick={() => stop(true)}>{active ? '取消并关闭' : '关闭'}</button>
        {active ? <button className="button danger" disabled={busy} onClick={() => stop(false)}>停止并清理</button> : success ? <button className="button primary" onClick={onClose}>完成</button> : <button className="button primary" disabled={!authorized || busy} onClick={begin}>{busy ? '正在启动…' : status?.state === 'error' ? '重新尝试' : '开始本机配置'}</button>}
      </div>
    </section>
  </div>
}
