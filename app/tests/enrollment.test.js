import test from 'node:test'
import assert from 'node:assert/strict'
import { getNextRun } from '../src/lib/enrollment.js'

test('计算当天或次日下一次执行时间', () => {
  assert.equal(getNextRun('12:00', new Date('2026-10-27T11:59:00')).getHours(), 12)
  assert.equal(getNextRun('12:00', new Date('2026-10-27T11:59:00')).getDate(), 27)
  assert.equal(getNextRun('12:00', new Date('2026-10-27T12:00:00')).getDate(), 28)
})
