import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, Check, CheckCircle2, MonitorCheck, ShieldCheck, X } from 'lucide-react'
import { cancelCapture, fetchCaptureStatus, startCapture } from './lib/liveApi'

const STEPS = [
  { key: 'starting', title: '启动进程捕获', copy: '仅针对 WeChatAppEx.exe，不修改系统代理' },
  { key: 'waiting', title: '重新打开讲座页面', copy: '在微信中重新进入目标页面，等待会话加密保存' },
  { key: 'verifying', title: '只读验证并清理', copy: '请求讲座与“我的”接口，移除临时证书和捕获进程' },
]

function stepState(key, state) {
  if (state === 'success') return 'done'
  if (state === 'verifying') return key === 'verifying' ? 'active' : 'done'
  if (state === 'waiting') return key === 'waiting' ? 'active' : key === 'starting' ? 'done' : ''
  if (state === 'starting') return key === 'starting' ? 'active' : ''
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
        if (!disposed) timer = window.setTimeout(poll, 1000)
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
  return <div className="modal-backdrop" role="presentation">
    <section className="lecture-modal setup-modal" role="dialog" aria-modal="true" aria-label="配置本机会话">
      <button className="modal-close" disabled={busy} onClick={() => stop(true)} aria-label="关闭会话配置"><X /></button>
      <span className="stat-icon green"><ShieldCheck /></span>
      <h2>配置本机会话</h2>
      <p className="setup-intro">在新电脑或会话失效时使用。无需提供账号密码，后续讲座读取和报名均通过 HTTPS 接口完成。</p>

      <div className="setup-notice"><MonitorCheck size={18} /><div><strong>开始前请准备</strong><p>在 Windows 微信中本人登录“科大微门户”，打开研究生学术讲座平台目标页面，并保持微信在线。</p></div></div>
      <ol className="setup-steps">{STEPS.map((step, index) => {
        const current = stepState(step.key, status?.state)
        return <li key={step.key} className={current}><span>{current === 'done' ? <Check size={15} /> : index + 1}</span><div><strong>{step.title}</strong><p>{step.copy}</p></div></li>
      })}</ol>

      <div className={`capture-status ${success ? 'success' : status?.state === 'error' ? 'error' : ''}`} role="status">
        {success ? <CheckCircle2 size={18} /> : <ShieldCheck size={18} />}
        <div><strong>{active ? '配置正在进行' : success ? '连接验证通过' : '安全捕获说明'}</strong><p>{error || status?.detail || '只保留目标学校接口的 Cookie／Token，并用当前 Windows 用户的 DPAPI 加密；不保存请求正文，不显示密钥。'}</p></div>
      </div>
      {status && <div className="capture-facts"><span>系统代理：未修改</span><span>捕获范围：微信小程序进程</span><span>管理员权限：{status.isAdministrator ? '已具备' : '未启用'}</span></div>}
      {!active && !success && <label className="capture-consent"><input type="checkbox" checked={authorized} disabled={busy} onChange={(event) => setAuthorized(event.target.checked)} /><span>我明确授权在本机临时捕获目标学校域名的本人登录会话，并了解临时证书将在结束后移除。</span></label>}
      {status?.state === 'error' && <p className="setup-help">若引擎提示权限不足，请关闭 EXE，右键选择“以管理员身份运行”后重试。配置成功后，日常使用无需保持捕获。</p>}
      <div className="modal-actions">
        <button className="button secondary" disabled={busy} onClick={() => stop(true)}>{active ? '取消并关闭' : '关闭'}</button>
        {active ? <button className="button danger" disabled={busy} onClick={() => stop(false)}>停止并清理</button> : success ? <button className="button primary" onClick={onClose}>完成</button> : <button className="button primary" disabled={!authorized || busy} onClick={begin}>{busy ? '正在启动…' : status?.state === 'error' ? '重新尝试' : '开始本机配置'}</button>}
      </div>
    </section>
  </div>
}
