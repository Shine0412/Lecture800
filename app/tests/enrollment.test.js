import test from 'node:test'
import assert from 'node:assert/strict'
import { selectCandidate, runEnrollment, getNextRun, shouldTrigger } from '../src/lib/enrollment.js'

const base = [
  { id: 'b', level: '800', status: 'open', registration: null, startAt: '2026-10-29T08:00:00', capacity: 2, enrolledCount: 1 },
  { id: 'a', level: '800', status: 'open', registration: null, startAt: '2026-10-28T08:00:00', capacity: 3, enrolledCount: 1 },
  { id: 'c', level: '300', status: 'open', registration: null, startAt: '2026-10-27T08:00:00', capacity: 3, enrolledCount: 1 },
  { id: 'd', level: '800', status: 'full', registration: null, startAt: '2026-10-26T08:00:00', capacity: 1, enrolledCount: 1 },
]

test('只选择最早开始的可抢目标级别讲座', () => {
  assert.equal(selectCandidate(base, '800').id, 'a')
})

test('抢报成功更新报名状态和人数，不影响其他讲座', () => {
  const result = runEnrollment(base, { now: new Date('2026-10-27T04:00:00Z') })
  assert.equal(result.log.result, 'success')
  assert.equal(result.lectures.find((item) => item.id === 'a').registration, 'enrolled')
  assert.equal(result.lectures.find((item) => item.id === 'a').enrolledCount, 2)
  assert.equal(result.lectures.find((item) => item.id === 'b').registration, null)
})

test('没有候选讲座时记录跳过且不修改数据', () => {
  const lectures = base.map((item) => ({ ...item, registration: 'enrolled' }))
  const result = runEnrollment(lectures)
  assert.equal(result.log.result, 'skipped')
  assert.deepEqual(result.lectures, lectures)
})

test('最后一个名额抢报后讲座变为满员', () => {
  const result = runEnrollment(base)
  assert.equal(result.lectures.find((item) => item.id === 'b').status, 'open')
  const second = runEnrollment(result.lectures)
  assert.equal(second.lectures.find((item) => item.id === 'b').status, 'full')
})

test('计算当天或次日下一次执行时间', () => {
  assert.equal(getNextRun('12:00', new Date('2026-10-27T11:59:00')).getHours(), 12)
  assert.equal(getNextRun('12:00', new Date('2026-10-27T11:59:00')).getDate(), 27)
  assert.equal(getNextRun('12:00', new Date('2026-10-27T12:00:00')).getDate(), 28)
})

test('每个执行时段只触发一次', () => {
  const now = new Date('2026-10-27T12:00:20')
  assert.equal(shouldTrigger(now, '12:00', ''), true)
  assert.equal(shouldTrigger(now, '12:00', '2026-10-27@12:00'), false)
  assert.equal(shouldTrigger(new Date('2026-10-27T12:01:00'), '12:00', ''), false)
})
