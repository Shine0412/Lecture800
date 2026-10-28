const REGISTRATION_STATES = new Set(['enrolled', 'waitlisted', 'attended'])

export function parseChineseLectureTime(value) {
  if (!value) return { startAt: null, endAt: null }
  const match = String(value).match(/(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}):(\d{2})(?:\s*[-–—~至]\s*(\d{1,2}):(\d{2}))?/)
  if (!match) return { startAt: null, endAt: null }
  const [, year, month, day, hour, minute, endHour, endMinute] = match
  const start = new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute))
  const end = endHour == null
    ? null
    : new Date(Number(year), Number(month) - 1, Number(day), Number(endHour), Number(endMinute))
  return {
    startAt: Number.isNaN(start.getTime()) ? null : start.toISOString(),
    endAt: end && !Number.isNaN(end.getTime()) ? end.toISOString() : null,
  }
}

export function normalizeLecture(lecture) {
  const registration = REGISTRATION_STATES.has(lecture.status) ? lecture.status : null
  const parsedTime = parseChineseLectureTime(lecture.startAt)
  const validStartAt = lecture.startAt && !Number.isNaN(new Date(lecture.startAt).getTime()) ? lecture.startAt : null
  const validEndAt = lecture.endAt && !Number.isNaN(new Date(lecture.endAt).getTime()) ? lecture.endAt : null
  return {
    ...lecture,
    startAt: parsedTime.startAt ?? validStartAt,
    endAt: validEndAt ?? parsedTime.endAt,
    rawStartAt: lecture.startAt,
    level: String(lecture.level || '800'),
    category: lecture.category || '未分类',
    speaker: lecture.speaker || '主讲人待确认',
    location: lecture.location || '地点待确认',
    capacity: Number.isFinite(lecture.capacity) ? lecture.capacity : null,
    remaining: Number.isFinite(lecture.remaining) ? lecture.remaining : null,
    registration: lecture.registration || registration,
    enrollmentOpenAt: lecture.enrollmentOpenAt || null,
    description: lecture.description || '',
    teacherJob: lecture.teacherJob || '',
  }
}

export async function fetchLiveLectures({ refresh = false, signal } = {}) {
  const response = await fetch(refresh ? '/api/refresh' : '/api/lectures', {
    method: refresh ? 'POST' : 'GET',
    headers: { Accept: 'application/json' },
    cache: 'no-store',
    signal,
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload?.connected) {
    throw new Error(payload?.error || payload?.message || `实时采集失败（${response.status}）`)
  }
  return {
    connected: true,
    fetchedAt: payload.fetchedAt,
    lectures: Array.isArray(payload.lectures) ? payload.lectures.map(normalizeLecture) : [],
  }
}

export async function fetchOperationLogs({ signal } = {}) {
  const response = await fetch('/api/logs', { cache: 'no-store', signal })
  if (!response.ok) return []
  const payload = await response.json().catch(() => ({}))
  return Array.isArray(payload.logs) ? payload.logs : []
}

export async function fetchVerification({ signal } = {}) {
  const response = await fetch('/api/verify', { cache: 'no-store', signal })
  if (!response.ok) throw new Error('连接验证服务不可用')
  return response.json()
}

export async function fetchCaptureStatus({ signal } = {}) {
  const response = await fetch('/api/capture', { cache: 'no-store', signal })
  if (!response.ok) throw new Error('无法读取会话配置状态')
  return response.json()
}

export async function startCapture() {
  const response = await fetch('/api/capture/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ authorized: true }),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new Error(payload?.message || '会话配置未能启动')
  return payload
}

export async function cancelCapture() {
  const response = await fetch('/api/capture/cancel', {
    method: 'POST', headers: { Accept: 'application/json' },
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new Error(payload?.message || '无法停止会话配置')
  return payload
}

export async function fetchMine({ signal } = {}) {
  const response = await fetch('/api/mine', { cache: 'no-store', signal })
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload?.connected || payload.page !== 'mine') {
    throw new Error(payload?.message || '个人信息接口请求失败，请检查登录会话')
  }
  return payload
}

export async function fetchSettings({ signal } = {}) {
  const response = await fetch('/api/settings', { cache: 'no-store', signal })
  if (!response.ok) throw new Error('无法读取自动任务设置')
  return response.json()
}

export async function updateSettings(changes) {
  const response = await fetch('/api/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(changes),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) throw new Error(payload?.message || '自动任务设置失败')
  return payload
}

export function setAutoEnabled(autoEnabled) {
  return updateSettings({ autoEnabled })
}

export function setLocationRules(locationRules) {
  return updateSettings({ locationRules })
}

export async function enrollLecture(lectureId) {
  const response = await fetch('/api/enroll', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ lectureId, confirm: true }),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload?.verified) throw new Error(payload?.message || '报名未通过回执核验')
  return payload
}

export async function enrollAllLectures() {
  const response = await fetch('/api/enroll/all', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ confirm: true }),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok) {
    const error = new Error(payload?.message || '批量报名或回执核验未完成')
    error.result = payload
    throw error
  }
  return payload
}

export async function withdrawLecture({ lectureId, applyId }) {
  const response = await fetch('/api/withdraw', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({ lectureId, applyId, confirm: true }),
  })
  const payload = await response.json().catch(() => null)
  if (!response.ok || !payload?.verified) throw new Error(payload?.message || '退课未通过回执核验')
  return payload
}

export function formatDateTime(value, withYear = false) {
  if (!value) return '时间待确认'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '时间待确认'
  return new Intl.DateTimeFormat('zh-CN', {
    ...(withYear ? { year: 'numeric' } : {}),
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}

export function formatSyncTime(value) {
  if (!value) return '尚未同步'
  return formatDateTime(value, true)
}
