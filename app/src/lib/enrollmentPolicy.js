export const DEFAULT_LOCATION_RULES = {
  firstSite: true,
  secondSite: true,
  thirdSite: false,
  nanjing: false,
  wuhan: false,
  other: true,
}

export const LOCATION_OPTIONS = [
  { key: 'firstSite', label: '一号院', detail: '地点包含“一号院”' },
  { key: 'secondSite', label: '二号院', detail: '地点包含“二号院”' },
  { key: 'thirdSite', label: '三号院', detail: '地点包含“三号院”' },
  { key: 'nanjing', label: '南京校区', detail: '标题以“南京校区”开头' },
  { key: 'wuhan', label: '武汉校区', detail: '标题以“武汉校区”开头' },
  { key: 'other', label: '其他地点', detail: '以上规则以外的课程' },
]

export function normalizeLocationRules(rules) {
  return Object.fromEntries(Object.entries(DEFAULT_LOCATION_RULES).map(([key, fallback]) => [
    key, typeof rules?.[key] === 'boolean' ? rules[key] : fallback,
  ]))
}

export function locationCategory(lecture) {
  const title = lecture.title?.trimStart() ?? ''
  const location = lecture.location ?? ''
  if (title.startsWith('南京校区')) return 'nanjing'
  if (title.startsWith('武汉校区')) return 'wuhan'
  if (location.includes('三号院')) return 'thirdSite'
  if (location.includes('一号院')) return 'firstSite'
  if (location.includes('二号院')) return 'secondSite'
  return 'other'
}

function startTime(lecture) {
  const value = new Date(lecture.startAt).getTime()
  return Number.isNaN(value) ? Number.MAX_SAFE_INTEGER : value
}

export function selectOpenCandidates(lectures, locationRules) {
  const rules = normalizeLocationRules(locationRules)
  return lectures
    .filter((lecture) => lecture.level === '800' && lecture.status === 'open' && !lecture.registration && rules[locationCategory(lecture)])
    .sort((a, b) => Number(!a.location?.includes('一号院')) - Number(!b.location?.includes('一号院')) || startTime(a) - startTime(b))
}
