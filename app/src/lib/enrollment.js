export function getNextRun(scheduledTime = '12:00', from = new Date()) {
  const [hours, minutes] = scheduledTime.split(':').map(Number)
  const next = new Date(from)
  next.setHours(hours, minutes, 0, 0)
  if (next <= from) next.setDate(next.getDate() + 1)
  return next
}
