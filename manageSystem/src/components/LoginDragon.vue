<template>
  <canvas ref="canvasRef" class="login-dragon" aria-hidden="true"></canvas>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const canvasRef = ref(null)
let ctx = null
let raf = 0
let W = 0
let H = 0
let dpr = 1

// ── 龙头状态（沿随机目标缓动游动） ──
const head = { x: 0, y: 0, angle: 0, speed: 0.6 }
let target = { x: 0, y: 0 }
let wobble = 0

// 身体历史点（头部经过的轨迹）
let trail = []

const rand = (a, b) => a + Math.random() * (b - a)

function pickTarget() {
  target.x = rand(W * 0.15, W * 0.85)
  target.y = rand(H * 0.18, H * 0.82)
}

function resize() {
  const canvas = canvasRef.value
  if (!canvas) return
  dpr = Math.min(window.devicePixelRatio || 1, 2)
  W = window.innerWidth
  H = window.innerHeight
  canvas.width = W * dpr
  canvas.height = H * dpr
  canvas.style.width = `${W}px`
  canvas.style.height = `${H}px`
  ctx = canvas.getContext('2d')
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  // 仅首次初始化龙头位置；resize 时不瞬移
  if (!trail.length) {
    head.x = W * 0.5
    head.y = H * 0.5
    pickTarget()
  }
}

// ── 头部前进 ──
function stepHead() {
  const dx = target.x - head.x
  const dy = target.y - head.y
  const dist = Math.hypot(dx, dy)
  const desired = Math.atan2(dy, dx)
  // 平滑转向目标
  let diff = desired - head.angle
  while (diff > Math.PI) diff -= Math.PI * 2
  while (diff < -Math.PI) diff += Math.PI * 2
  head.angle += diff * 0.02

  // 到达目标附近则随机选新目标
  if (dist < 40) pickTarget()

  // 撞边折返
  const margin = 90
  if (head.x < margin && head.angle < -Math.PI / 2) pickTarget()
  if (head.x > W - margin && head.angle > Math.PI / 2) pickTarget()
  if (head.y < margin) pickTarget()
  if (head.y > H - margin) pickTarget()

  wobble += 0.03
  // 前进 + 轻微身体摆动带来的横向偏移（舞动感）
  head.x += Math.cos(head.angle) * head.speed + Math.sin(wobble) * 0.35
  head.y += Math.sin(head.angle) * head.speed + Math.cos(wobble * 0.8) * 0.35

  trail.unshift({ x: head.x, y: head.y })
  if (trail.length > 90) trail.pop()
}

// ── 绘制龙 ──
function drawDragon() {
  const n = Math.min(trail.length, 60)
  if (n < 3) return

  // 计算身体轴线（轨迹平滑化 + 正弦波动）
  const pts = []
  for (let i = 0; i < n; i++) {
    const t = trail[i]
    const k = i / n // 0=头, 1=尾
    const sway = Math.sin(wobble * 1.2 - k * 2.4) * (4 + 8 * k)
    pts.push({
      x: t.x + Math.cos(head.angle + Math.PI / 2) * sway,
      y: t.y + Math.sin(head.angle + Math.PI / 2) * sway,
    })
  }

  // 身体宽度：头粗尾细
  const width = (k) => 13 * (1 - k * 0.85)

  // 身体多边形（左右两条边）
  const left = []
  const right = []
  for (let i = 0; i < n; i++) {
    const p = pts[i]
    const p2 = pts[Math.min(i + 1, n - 1)]
    const nx = -(p2.y - p.y)
    const ny = p2.x - p.x
    const len = Math.hypot(nx, ny) || 1
    const ux = nx / len
    const uy = ny / len
    const w = width(i / n) / 2
    left.push({ x: p.x + ux * w, y: p.y + uy * w })
    right.push({ x: p.x - ux * w, y: p.y - uy * w })
  }

  // 身体金色渐变
  const g = ctx.createLinearGradient(
    pts[0].x, pts[0].y,
    pts[n - 1].x, pts[n - 1].y,
  )
  g.addColorStop(0, 'rgba(250, 204, 21, 0.85)')
  g.addColorStop(0.5, 'rgba(217, 119, 6, 0.7)')
  g.addColorStop(1, 'rgba(180, 83, 9, 0.5)')

  ctx.beginPath()
  ctx.moveTo(left[0].x, left[0].y)
  for (let i = 1; i < left.length; i++) ctx.lineTo(left[i].x, left[i].y)
  for (let i = right.length - 1; i >= 0; i--) ctx.lineTo(right[i].x, right[i].y)
  ctx.closePath()
  ctx.fillStyle = g
  ctx.fill()

  // 龙鳞（沿中线的小弧）
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)'
  ctx.lineWidth = 1
  for (let i = 4; i < n - 2; i += 4) {
    const p = pts[i]
    const k = i / n
    if (Math.random() < 0.7) continue // 稀疏鳞片
    const w = width(k)
    ctx.beginPath()
    ctx.arc(p.x, p.y, Math.max(1.5, w * 0.18), 0, Math.PI * 2)
    ctx.stroke()
  }

  // 背鳍（身体背部锯齿）
  ctx.fillStyle = 'rgba(251, 146, 60, 0.55)'
  for (let i = 3; i < n - 1; i += 3) {
    const p = pts[i]
    const p2 = pts[i + 1]
    const nx = -(p2.y - p.y)
    const ny = p2.x - p.x
    const len = Math.hypot(nx, ny) || 1
    const ux = nx / len
    const uy = ny / len
    const h = 5 + Math.sin(wobble + i * 0.5) * 2
    ctx.beginPath()
    ctx.moveTo(p.x, p.y)
    ctx.lineTo(p.x + ux * h, p.y + uy * h)
    ctx.lineTo(p2.x, p2.y)
    ctx.closePath()
    ctx.fill()
  }

  // 龙须（从头部伸出的两条飘动细线）
  ctx.strokeStyle = 'rgba(255, 241, 181, 0.7)'
  ctx.lineWidth = 1.2
  for (let side = -1; side <= 1; side += 2) {
    ctx.beginPath()
    const baseA = head.angle + side * 1.0
    for (let s = 0; s <= 5; s++) {
      const lx = head.x + Math.cos(baseA) * (s * 7) + Math.sin(wobble * 2 + side) * s * 1.6
      const ly = head.y + Math.sin(baseA) * (s * 7) + Math.cos(wobble * 1.7 + side) * s * 1.4
      if (s === 0) ctx.moveTo(lx, ly)
      else ctx.lineTo(lx, ly)
    }
    ctx.stroke()
  }

  // 龙头（简化侧影：吻部 + 角 + 眼）
  drawHead()
}

function drawHead() {
  const cx = head.x
  const cy = head.y
  const a = head.angle

  ctx.save()
  ctx.translate(cx, cy)
  ctx.rotate(a)

  // 头部主体（扁圆）
  ctx.fillStyle = 'rgba(250, 204, 21, 0.9)'
  ctx.beginPath()
  ctx.ellipse(6, 0, 14, 11, 0, 0, Math.PI * 2)
  ctx.fill()

  // 吻部（前伸）
  ctx.beginPath()
  ctx.moveTo(12, -4)
  ctx.lineTo(30, 0)
  ctx.lineTo(12, 5)
  ctx.closePath()
  ctx.fill()

  // 龙角（两根分叉）
  ctx.strokeStyle = 'rgba(217, 119, 6, 0.9)'
  ctx.lineWidth = 3
  ctx.lineCap = 'round'
  ctx.beginPath()
  ctx.moveTo(2, -9)
  ctx.lineTo(-2, -22)
  ctx.moveTo(2, -9)
  ctx.lineTo(9, -20)
  ctx.stroke()

  // 眼睛
  ctx.fillStyle = 'rgba(15, 23, 42, 0.9)'
  ctx.beginPath()
  ctx.arc(4, -3, 2.2, 0, Math.PI * 2)
  ctx.fill()

  ctx.restore()
}

function frame() {
  stepHead()
  ctx.clearRect(0, 0, W, H)
  drawDragon()
  raf = requestAnimationFrame(frame)
}

onMounted(() => {
  resize()
  window.addEventListener('resize', resize)
  frame()
})

onUnmounted(() => {
  cancelAnimationFrame(raf)
  window.removeEventListener('resize', resize)
})
</script>

<style scoped>
.login-dragon {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  opacity: 0.85;
}
</style>
