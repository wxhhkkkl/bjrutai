Component({
  properties: {
    categories: { type: Array, value: [] },
    values: { type: Array, value: [] },
    max: { type: Number, value: 0 },
    interval: { type: Number, value: 0 },
    showYAxis: { type: Boolean, value: false }
  },
  observers: {
    'categories, values, max, interval, showYAxis'() { this.draw() }
  },
  lifetimes: {
    ready() { this.draw() }
  },
  methods: {
    draw() {
      const query = this.createSelectorQuery()
      query.select('#chart').fields({ node: true, size: true }).exec((result) => {
        const chart = result[0]
        if (!chart || !chart.node || !chart.width || !chart.height) return
        const dpr = wx.getSystemInfoSync().pixelRatio || 1
        const canvas = chart.node
        canvas.width = chart.width * dpr
        canvas.height = chart.height * dpr
        const context = canvas.getContext('2d')
        context.scale(dpr, dpr)
        context.clearRect(0, 0, chart.width, chart.height)
        this.paint(context, chart.width, chart.height)
      })
    },
    paint(ctx, width, height) {
      const values = this.data.values.map(Number).filter((value) => Number.isFinite(value))
      if (!values.length) return
      const categories = this.data.categories
      const max = Math.max(Number(this.data.max) || 0, ...values, 1)
      const left = this.data.showYAxis ? 44 : 8
      const right = 10
      const top = 14
      const bottom = this.data.showYAxis ? 26 : 20
      const plotWidth = width - left - right
      const plotHeight = height - top - bottom
      const step = values.length > 1 ? plotWidth / (values.length - 1) : 0
      const pointAt = (value, index) => ({
        x: left + step * index,
        y: top + plotHeight * (1 - value / max)
      })

      ctx.lineWidth = 1
      ctx.strokeStyle = '#edf0f4'
      for (let index = 0; index < 4; index += 1) {
        const y = top + (plotHeight / 3) * index
        ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(width - right, y); ctx.stroke()
        if (this.data.showYAxis) {
          ctx.fillStyle = '#8a8f98'; ctx.font = '10px sans-serif'; ctx.textAlign = 'right'
          ctx.fillText(String(Math.round(max * (1 - index / 3))), left - 7, y + 3)
        }
      }

      const gradient = ctx.createLinearGradient(0, top, 0, top + plotHeight)
      gradient.addColorStop(0, 'rgba(22, 119, 255, .22)')
      gradient.addColorStop(1, 'rgba(22, 119, 255, .01)')
      ctx.beginPath()
      values.forEach((value, index) => {
        const point = pointAt(value, index)
        index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)
      })
      const last = pointAt(values[values.length - 1], values.length - 1)
      ctx.lineTo(last.x, top + plotHeight); ctx.lineTo(left, top + plotHeight); ctx.closePath()
      ctx.fillStyle = gradient; ctx.fill()

      ctx.beginPath()
      values.forEach((value, index) => {
        const point = pointAt(value, index)
        index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y)
      })
      ctx.strokeStyle = '#1677ff'; ctx.lineWidth = 3; ctx.stroke()
      if (!this.data.showYAxis) {
        ctx.fillStyle = '#7b818a'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center'
        categories.forEach((label, index) => ctx.fillText(label, left + step * index, height - 4))
      }
    }
  }
})
