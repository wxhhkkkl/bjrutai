Component({
  properties: { items: { type: Array, value: [] } },
  observers: { items() { this.draw() } },
  lifetimes: { ready() { this.draw() } },
  methods: {
    draw() {
      const query = this.createSelectorQuery()
      query.select('#chart').fields({ node: true, size: true }).exec((result) => {
        const chart = result[0]
        if (!chart || !chart.node || !chart.width || !chart.height) return
        const dpr = wx.getSystemInfoSync().pixelRatio || 1
        const canvas = chart.node
        canvas.width = chart.width * dpr; canvas.height = chart.height * dpr
        const ctx = canvas.getContext('2d')
        ctx.scale(dpr, dpr); ctx.clearRect(0, 0, chart.width, chart.height)
        const values = this.data.items.map((item) => Number(item.value) || 0)
        const total = values.reduce((sum, value) => sum + value, 0)
        if (!total) return
        const colors = this.data.items.map((item) => item.color || '#1677ff')
        const radius = Math.min(chart.width, chart.height) * 0.34
        const centerX = chart.width / 2; const centerY = chart.height / 2
        let start = -Math.PI / 2
        values.forEach((value, index) => {
          const end = start + Math.PI * 2 * value / total
          ctx.beginPath(); ctx.arc(centerX, centerY, radius, start, end)
          ctx.strokeStyle = colors[index]; ctx.lineWidth = radius * .42; ctx.stroke()
          start = end
        })
      })
    }
  }
})
