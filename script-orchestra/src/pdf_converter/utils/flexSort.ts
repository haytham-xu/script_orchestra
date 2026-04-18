/**
 * ⚠️ INDEPENDENT COPY FOR PDF_CONVERTER MODULE ⚠️
 *
 * This is an independent copy of src/basic/flexSort.ts specifically for the pdf_converter module.
 * DO NOT modify this file when working on other modules.
 * This ensures pdf_converter remains stable without E2E test coverage.
 *
 * If you need to modify sorting behavior in other modules, edit src/basic/flexSort.ts instead.
 *
 * Flexible natural sorting that supports Chinese numbers
 * TypeScript port of backend/basic/flex_sort.py
 */

// Mapping of Chinese number variants to simplified forms
const SIMPLIFY_MAP: Record<string, string> = {
  "零": "零", "〇": "零",
  "一": "一", "二": "二", "三": "三", "四": "四", "五": "五",
  "六": "六", "七": "七", "八": "八", "九": "九",
  "十": "十", "拾": "十",
  "壹": "一", "贰": "二", "叁": "三", "肆": "四", "伍": "五",
  "陆": "六", "柒": "七", "捌": "八", "玖": "九"
}

// Chinese digit values
const CN_DIGITS: Record<string, number> = {
  "零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
  "五": 5, "六": 6, "七": 7, "八": 8, "九": 9
}

// Regex to match Chinese number patterns at the end of string
const CN_TAIL_REGEX = /([零〇一二三四五六七八九十拾壹贰叁肆伍陆柒捌玖]{1,4})$/

/**
 * Normalize Chinese numbers to simplified form
 */
function normalizeChinese(s: string): string {
  return Array.from(s).map(ch => SIMPLIFY_MAP[ch] || ch).join('')
}

/**
 * Parse Chinese numbers from 1 to 20
 * Returns the numeric value or null if not parseable
 */
function parseChinese1To20(token: string): number | null {
  if (!token) return null

  const t = normalizeChinese(token)

  // Single digit 1-9
  if (t.length === 1 && t in CN_DIGITS && CN_DIGITS[t] !== 0) {
    return CN_DIGITS[t]
  }

  // 十 = 10
  if (t === "十") {
    return 10
  }

  // 十一..十九 = 11..19
  if (t.startsWith("十") && t.length === 2 && t[1] in CN_DIGITS && CN_DIGITS[t[1]] !== 0) {
    return 10 + CN_DIGITS[t[1]]
  }

  // 二十 = 20
  if (t === "二十") {
    return 20
  }

  return null
}

/**
 * Check if any item contains parseable Chinese numbers
 */
function hasChineseNumber(items: string[]): boolean {
  return items.some(item => {
    const match = item.match(CN_TAIL_REGEX)
    return match && parseChinese1To20(match[1]) !== null
  })
}

/**
 * Natural sort comparison function that handles numbers in strings
 * Similar to natsort algorithm
 */
function naturalCompare(a: string, b: string): number {
  // Split strings into segments of text and numbers
  const regex = /(\d+)|([^\d]+)/g
  const aParts: Array<string | number> = []
  const bParts: Array<string | number> = []

  let match: RegExpExecArray | null

  while ((match = regex.exec(a)) !== null) {
    aParts.push(match[1] ? parseInt(match[1], 10) : match[2].toLowerCase())
  }

  regex.lastIndex = 0
  while ((match = regex.exec(b)) !== null) {
    bParts.push(match[1] ? parseInt(match[1], 10) : match[2].toLowerCase())
  }

  // Compare segments
  const maxLen = Math.max(aParts.length, bParts.length)
  for (let i = 0; i < maxLen; i++) {
    const aPart = aParts[i]
    const bPart = bParts[i]

    // Handle undefined (shorter string)
    if (aPart === undefined) return -1
    if (bPart === undefined) return 1

    // Compare numbers numerically
    if (typeof aPart === 'number' && typeof bPart === 'number') {
      if (aPart !== bPart) return aPart - bPart
    }
    // Compare strings lexicographically
    else if (typeof aPart === 'string' && typeof bPart === 'string') {
      if (aPart !== bPart) return aPart.localeCompare(bPart, undefined, { numeric: true, sensitivity: 'base' })
    }
    // Number comes before string
    else if (typeof aPart === 'number') {
      return -1
    } else {
      return 1
    }
  }

  return 0
}

/**
 * Generate hybrid sort key for items with Chinese numbers
 * Returns: [priority, chineseNumber, originalString]
 * priority = 0 for items with Chinese numbers, 1 for others
 */
function hybridKey(name: string): [number, number, string] {
  const match = name.match(CN_TAIL_REGEX)
  if (match) {
    const num = parseChinese1To20(match[1])
    if (num !== null) {
      return [0, num, name]
    }
  }
  return [1, Infinity, name]
}

/**
 * Flexible natural sort
 * If items contain Chinese numbers => sort by Chinese numbers + natural sort
 * Otherwise => natural sort only
 */
export function flexNatsort(items: string[]): string[] {
  if (!items || items.length === 0) {
    return []
  }

  // Check if any item has Chinese numbers
  if (hasChineseNumber(items)) {
    // Sort with hybrid key
    return items.slice().sort((a, b) => {
      const [aPriority, aNum, aStr] = hybridKey(a)
      const [bPriority, bNum, bStr] = hybridKey(b)

      // First compare priority
      if (aPriority !== bPriority) {
        return aPriority - bPriority
      }

      // Then compare Chinese number
      if (aNum !== bNum) {
        return aNum - bNum
      }

      // Finally natural sort
      return naturalCompare(aStr, bStr)
    })
  }

  // No Chinese numbers, use natural sort
  return items.slice().sort(naturalCompare)
}
