const COURIER_NAMES = Object.freeze({
  shunfeng: '顺丰速运',
  shunfengkuaiyun: '顺丰快运',
  zhongtong: '中通快递',
  zhongtongkuaiyun: '中通快运',
  yuantong: '圆通速递',
  shentong: '申通快递',
  yunda: '韵达快递',
  jtexpress: '极兔速递',
  jd: '京东快递',
  ems: '邮政 EMS',
  youzhengguonei: '邮政快递包裹',
  youzhengdsbk: '邮政电商标快',
  youzhengbk: '邮政标准快递',
  debangkuaidi: '德邦快递',
  debangwuliu: '德邦物流',
  annengwuliu: '安能物流',
  kuayue: '跨越速运',
  danniao: '菜鸟速递',
  huitongkuaidi: '百世快递'
})

function courierName(code) {
  const normalizedCode = String(code || '').trim().toLowerCase()
  return COURIER_NAMES[normalizedCode] || '其他物流公司'
}

module.exports = { courierName }
