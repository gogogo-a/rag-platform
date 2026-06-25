const escapeHtml = (value = '') => String(value)
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;')

const renderInline = (value = '') => escapeHtml(value)
  .replace(/`([^`]+)`/g, '<code>$1</code>')
  .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  .replace(/\*([^*]+)\*/g, '<em>$1</em>')

const isTableDivider = (line = '') => /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$/.test(line)
const isTableRow = (line = '') => line.trim().startsWith('|') && line.trim().endsWith('|')

const splitTableCells = (line = '') => line
  .trim()
  .replace(/^\|/, '')
  .replace(/\|$/, '')
  .split('|')
  .map((cell) => cell.trim())

export const formatChatMessage = (content = '') => {
  const lines = String(content || '').replace(/\r\n/g, '\n').split('\n')
  const html = []
  let paragraph = []
  let listType = null
  let tableOpen = false

  const closeParagraph = () => {
    if (!paragraph.length) return
    html.push(`<p>${paragraph.map(renderInline).join('<br>')}</p>`)
    paragraph = []
  }

  const closeList = () => {
    if (!listType) return
    html.push(`</${listType}>`)
    listType = null
  }

  const closeTable = () => {
    if (!tableOpen) return
    html.push('</tbody></table>')
    tableOpen = false
  }

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index]
    const trimmed = line.trim()
    const nextLine = lines[index + 1] || ''

    if (!trimmed) {
      closeParagraph()
      closeList()
      closeTable()
      continue
    }

    if (isTableRow(line) && isTableDivider(nextLine)) {
      closeParagraph()
      closeList()
      closeTable()
      const headers = splitTableCells(line)
      html.push('<table><thead><tr>')
      headers.forEach((cell) => html.push(`<th>${renderInline(cell)}</th>`))
      html.push('</tr></thead><tbody>')
      tableOpen = true
      index += 1
      continue
    }

    if (tableOpen && isTableRow(line)) {
      const cells = splitTableCells(line)
      html.push('<tr>')
      cells.forEach((cell) => html.push(`<td>${renderInline(cell)}</td>`))
      html.push('</tr>')
      continue
    }

    closeTable()

    const heading = trimmed.match(/^(#{1,4})\s+(.+)$/)
    if (heading) {
      closeParagraph()
      closeList()
      const level = heading[1].length
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`)
      continue
    }

    const ordered = trimmed.match(/^\d+\.\s+(.+)$/)
    const unordered = trimmed.match(/^[-*]\s+(.+)$/)
    if (ordered || unordered) {
      closeParagraph()
      const nextType = ordered ? 'ol' : 'ul'
      if (listType !== nextType) {
        closeList()
        html.push(`<${nextType}>`)
        listType = nextType
      }
      html.push(`<li>${renderInline((ordered || unordered)[1])}</li>`)
      continue
    }

    closeList()
    paragraph.push(line)
  }

  closeParagraph()
  closeList()
  closeTable()

  return html.join('')
}
