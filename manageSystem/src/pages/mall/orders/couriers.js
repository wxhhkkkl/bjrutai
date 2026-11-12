export const courierOptions = [
  { code: 'shunfeng', name: '顺丰速运' },
  { code: 'shunfengkuaiyun', name: '顺丰快运' },
  { code: 'zhongtong', name: '中通快递' },
  { code: 'zhongtongkuaiyun', name: '中通快运' },
  { code: 'yuantong', name: '圆通速递' },
  { code: 'shentong', name: '申通快递' },
  { code: 'yunda', name: '韵达快递' },
  { code: 'jtexpress', name: '极兔速递' },
  { code: 'jd', name: '京东快递' },
  { code: 'ems', name: '邮政 EMS' },
  { code: 'youzhengguonei', name: '邮政快递包裹' },
  { code: 'youzhengdsbk', name: '邮政电商标快' },
  { code: 'youzhengbk', name: '邮政标准快递' },
  { code: 'debangkuaidi', name: '德邦快递' },
  { code: 'debangwuliu', name: '德邦物流' },
  { code: 'annengwuliu', name: '安能物流' },
  { code: 'kuayue', name: '跨越速运' },
  { code: 'danniao', name: '菜鸟速递' },
  { code: 'huitongkuaidi', name: '百世快递' },
]

const courierNames = new Map(courierOptions.map(({ code, name }) => [code, name]))

export function courierName(code) {
  const normalizedCode = String(code || '').trim().toLowerCase()
  return courierNames.get(normalizedCode) || '其他物流公司'
}
