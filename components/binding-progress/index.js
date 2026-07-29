Component({
  properties: {
    step: {
      type: Number,
      value: 1
    }
  },

  data: {
    steps: [1, 2, 3],
    labels: ['身份识别', '客户确认', '绑定结果']
  }
});
