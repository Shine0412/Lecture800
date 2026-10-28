import test from 'node:test'
import assert from 'node:assert/strict'
import { normalizeLecture, parseChineseLectureTime, formatDateTime } from '../src/lib/liveApi.js'

test('转换中文讲座开始与结束时间', () => {
  const result = parseChineseLectureTime('2026年11月8日 14:30-16:30')
  assert.equal(new Date(result.startAt).getHours(), 14)
  assert.equal(new Date(result.startAt).getMinutes(), 30)
  assert.equal(new Date(result.endAt).getHours(), 16)
})

test('保留接口返回的 ISO 开始与结束时间', () => {
  const result = normalizeLecture({
    id: 'iso', startAt: '2026-11-08T14:30:00+08:00', endAt: '2026-11-08T16:30:00+08:00',
  })
  assert.equal(result.startAt, '2026-11-08T14:30:00+08:00')
  assert.equal(result.endAt, '2026-11-08T16:30:00+08:00')
  assert.match(formatDateTime(result.startAt, true), /2026/)
})

test('无法识别的时间不会被伪造成有效日期', () => {
  assert.deepEqual(parseChineseLectureTime('待定'), { startAt: null, endAt: null })
  assert.equal(formatDateTime(null), '时间待确认')
  assert.equal(formatDateTime('not-a-date'), '时间待确认')
})

test('保留未知容量与剩余名额，不执行空值算术', () => {
  const result = normalizeLecture({ id: 'a', title: '讲座', startAt: '2026年11月8日 14:30-16:30', capacity: null, remaining: null, status: 'upcoming' })
  assert.equal(result.capacity, null)
  assert.equal(result.remaining, null)
  assert.equal(result.registration, null)
  assert.ok(result.startAt)
})

test('将采集状态映射为我的讲座报名状态', () => {
  for (const status of ['enrolled', 'waitlisted', 'attended']) {
    assert.equal(normalizeLecture({ status }).registration, status)
  }
})
