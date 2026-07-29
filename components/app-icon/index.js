const GLYPHS = { user: '♙', link: '⌁', chart: '▥', team: '♧', task: '✓', shield: '◇', code: '▦', bell: '♧', record: '▤', heart: '♡', document: '▣', profile: '◎' }
Component({ properties: { name: { type: String, value: 'user' }, tone: { type: String, value: 'blue' } }, data: { glyph: '♙' }, observers: { name(value) { this.setData({ glyph: GLYPHS[value] || '•' }) } } })
