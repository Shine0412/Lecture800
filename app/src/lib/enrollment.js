export function selectCandidate(lectures, targetLevel = '800') {
  return lectures
    .filter((lecture) =>
      lecture.level === targetLevel &&
      lecture.status === 'open' &&
      !lecture.registration
    )
    .sort((a, b) => new Date(a.startAt) - new Date(b.startAt))[0] ?? null
}

export function runEnrollment(lectures, options = {}) {
  const { targetLevel = '800', now = new Date(), source = 'manual' } = options
  const candidate = selectCandidate(lectures, targetLevel)
  const time = now.toISOString()

  if (!candidate) {
    return {
      lectures,
      log: {
        id: `log-${now.getTime()}`,
        lectureId: null,
        title: '没有符合条件的讲座',
        result: 'skipped',
        source,
        time,
        message: `未找到可抢的 ${targetLevel} 级讲座，或目标讲座已报名。`,
      },
    }
  }

  const updated = lectures.map((lecture) =>
    lecture.id === candidate.id
      ? {
          ...lecture,
          registration: 'enrolled',
          enrolledCount: Math.min(lecture.capacity, lecture.enrolledCount + 1),
          status: lecture.enrolledCount + 1 >= lecture.capacity ? 'full' : lecture.status,
        }
      : lecture
  )

  return {
    lectures: updated,
    log: {
      id: `log-${now.getTime()}`,
      lectureId: candidate.id,
      title: candidate.title,
      result: 'success',
      source,
      time,
      message: `模拟抢报成功，已锁定 1 个名额。${source === 'auto' ? '由定时任务触发。' : '由立即演练触发。'}`,
    },
  }
}

export function getNextRun(scheduledTime = '12:00', from = new Date()) {
  const [hours, minutes] = scheduledTime.split(':').map(Number)
  const next = new Date(from)
  next.setHours(hours, minutes, 0, 0)
  if (next <= from) next.setDate(next.getDate() + 1)
  return next
}

export function getRunKey(now, scheduledTime) {
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}@${scheduledTime}`
}

export function shouldTrigger(now, scheduledTime, lastRunKey) {
  const currentTime = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  return currentTime === scheduledTime && getRunKey(now, scheduledTime) !== lastRunKey
}

export function formatDateTime(value, withYear = false) {
  const date = new Date(value)
  return new Intl.DateTimeFormat('zh-CN', {
    ...(withYear ? { year: 'numeric' } : {}),
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date)
}
