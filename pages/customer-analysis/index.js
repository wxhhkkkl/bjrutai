const echarts = require('../../ec-canvas/echarts');
const {
  CUSTOMER_ANALYSIS_PERIODS,
  getCustomerAnalysisPeriod,
  getBindingDistribution
} = require('../../models/customer-analysis');

function buildTrendOption(period) {
  return {
    animationDuration: 650,
    animationEasing: 'cubicOut',
    grid: {
      top: 38,
      right: 14,
      bottom: 4,
      left: 5,
      containLabel: true
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(16, 24, 40, 0.9)',
      borderWidth: 0,
      textStyle: {
        color: '#ffffff',
        fontSize: 11
      }
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: period.trend.categories,
      axisLine: {
        lineStyle: {
          color: '#dfe3e9',
          width: 1
        }
      },
      axisTick: { show: false },
      axisLabel: {
        color: '#555b64',
        fontSize: 11,
        margin: 10,
        interval: 0
      }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: period.trend.max,
      interval: period.trend.interval,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: {
        color: '#666c75',
        fontSize: 10,
        margin: 10
      },
      splitLine: {
        lineStyle: {
          color: '#e8ebf0',
          type: 'dashed'
        }
      }
    },
    series: [
      {
        type: 'line',
        smooth: 0,
        showSymbol: true,
        symbol: 'circle',
        symbolSize: 9,
        data: period.trend.values,
        label: {
          show: true,
          position: 'top',
          distance: 8,
          color: '#1677ff',
          fontSize: 12
        },
        lineStyle: {
          color: '#1677ff',
          width: 3
        },
        itemStyle: {
          color: '#ffffff',
          borderColor: '#1677ff',
          borderWidth: 2
        },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(22, 119, 255, 0.25)' },
            { offset: 1, color: 'rgba(22, 119, 255, 0.01)' }
          ])
        }
      }
    ]
  };
}

function buildStatusOption(period) {
  const distribution = getBindingDistribution(period);

  return {
    animationDuration: 600,
    series: [
      {
        type: 'pie',
        radius: ['58%', '78%'],
        center: ['50%', '50%'],
        silent: true,
        avoidLabelOverlap: false,
        label: { show: false },
        labelLine: { show: false },
        itemStyle: {
          borderColor: '#ffffff',
          borderWidth: 2
        },
        data: distribution.map((item) => ({
          value: item.value,
          name: item.name,
          itemStyle: { color: item.color }
        }))
      }
    ]
  };
}

Page({
  data: {
    periods: CUSTOMER_ANALYSIS_PERIODS,
    selectedPeriod: 'month',
    period: CUSTOMER_ANALYSIS_PERIODS[0],
    distribution: getBindingDistribution(CUSTOMER_ANALYSIS_PERIODS[0]),
    selectedDate: '2026-07-28',
    ec: {
      lazyLoad: true
    }
  },

  onReady() {
    this.trendComponent = this.selectComponent('#customer-trend-chart');
    this.statusComponent = this.selectComponent('#binding-status-chart');
    this.initTrendChart();
    this.initStatusChart();
  },

  onShow() {
    if (this.trendChart) this.trendChart.resize();
    if (this.statusChart) this.statusChart.resize();
  },

  onUnload() {
    if (this.trendChart) this.trendChart.dispose();
    if (this.statusChart) this.statusChart.dispose();
  },

  initTrendChart() {
    if (this.trendChart || !this.trendComponent) return;

    this.trendComponent.init((canvas, width, height, dpr) => {
      const chart = echarts.init(canvas, null, {
        width,
        height,
        devicePixelRatio: dpr
      });

      canvas.setChart(chart);
      chart.setOption(buildTrendOption(this.data.period));
      this.trendChart = chart;

      return chart;
    });
  },

  initStatusChart() {
    if (this.statusChart || !this.statusComponent) return;

    this.statusComponent.init((canvas, width, height, dpr) => {
      const chart = echarts.init(canvas, null, {
        width,
        height,
        devicePixelRatio: dpr
      });

      canvas.setChart(chart);
      chart.setOption(buildStatusOption(this.data.period));
      this.statusChart = chart;

      return chart;
    });
  },

  selectPeriod(e) {
    const selectedPeriod = e.currentTarget.dataset.id;

    if (selectedPeriod === this.data.selectedPeriod) return;

    const period = getCustomerAnalysisPeriod(selectedPeriod);

    this.setData({
      selectedPeriod,
      period,
      distribution: getBindingDistribution(period)
    });

    if (this.trendChart) {
      this.trendChart.setOption(buildTrendOption(period), true);
    }
    if (this.statusChart) {
      this.statusChart.setOption(buildStatusOption(period), true);
    }
  },

  onDateChange(e) {
    this.setData({ selectedDate: e.detail.value });
    wx.showToast({
      title: '统计日期已更新',
      icon: 'none'
    });
  },

  openAttention(e) {
    const type = e.currentTarget.dataset.type;

    if (type === 'matching') {
      wx.navigateTo({
        url: '/pages/binding-records/index?filter=matching'
      });
      return;
    }

    wx.switchTab({ url: '/pages/customers/index' });
  },

  handleBack() {
    wx.navigateBack();
  }
});
