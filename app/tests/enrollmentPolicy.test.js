import test from 'node:test'
import assert from 'node:assert/strict'
import {
  DEFAULT_LOCATION_RULES, locationCategory, normalizeLocationRules, selectOpenCandidates,
} from '../src/lib/enrollmentPolicy.js'

const base = { level: '800', status: 'open', registration: null, startAt: '2026-11-01T12:00:00+08:00' }
const lectures = [
  { ...base, id: 'second', location: '二号院201' },
  { ...base, id: 'first', location: '一号院101', startAt: '2026-11-03T12:00:00+08:00' },
  { ...base, id: 'third', location: '三号院101' },
  { ...base, id: 'nanjing', title: '  南京校区测试', location: '南京' },
  { ...base, id: 'wuhan', title: '武汉校区测试', location: '武汉' },
  { ...base, id: 'other', location: '线上' },
]

test('默认地点规则保持一号院优先并排除三号院、南京和武汉', () => {
  assert.deepEqual(selectOpenCandidates(lectures, DEFAULT_LOCATION_RULES).map((item) => item.id), ['first', 'second', 'other'])
})

test('用户可单独启用三号院和南京校区并关闭其他地点', () => {
  const rules = { firstSite: false, secondSite: false, thirdSite: true, nanjing: true, wuhan: false, other: false }
  assert.deepEqual(selectOpenCandidates(lectures, rules).map((item) => item.id), ['third', 'nanjing'])
})

test('未选择任何地点时候选为空，不自动退化为全部地点', () => {
  const rules = Object.fromEntries(Object.keys(DEFAULT_LOCATION_RULES).map((key) => [key, false]))
  assert.deepEqual(selectOpenCandidates(lectures, rules), [])
})

test('校区标题优先于地点关键词，缺省配置使用安全默认值', () => {
  assert.equal(locationCategory({ title: '南京校区测试', location: '一号院101' }), 'nanjing')
  assert.deepEqual(normalizeLocationRules({ thirdSite: true, nanjing: 'invalid' }), { ...DEFAULT_LOCATION_RULES, thirdSite: true })
})
