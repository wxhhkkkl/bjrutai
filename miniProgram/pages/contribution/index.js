const echarts = require('../../ec-canvas/echarts');
const { summaries } = require('../../mock/foundation-fixtures');
const demo = require('../../mock/demo-control');
const {
  updateTabBar,
  openAction
} = require('../../services/navigation-service');
const { getCurrentSession } = require('../../services/session-service');

const PERIODS = [
  {
    id: 'month',
    label: '本月',
    summaryLabel: '本月累计',
    total: '12,680',
    categories: ['第1周', '第2周', '第3周', '第4周'],
    values: [2800, 7300, 10400, 13600],
    max: 15000,
    interval: 3000
  },
  {
    id: 'quarter',
    label: '近3月',
    summaryLabel: '近3月累计',
    total: '33,100',
    categories: ['5月', '6月', '7月'],
    values: [9420, 11000, 12680],
    max: 15000,
    interval: 3000
  },
  {
    id: 'year',
    label: '本年',
    summaryLabel: '本年累计',
    total: '86,420',
    categories: ['第一季度', '第二季度', '第三季度', '第四季度'],
    values: [16800, 37400, 62200, 86420],
    max: 100000,
    interval: 20000
  }
];

function formatNumber(value) {
  return Number(value).toLocaleString('en-US');
}

function buildChartOption(period) {
  return {
    animationDuration: 700,
    animationEasing: 'cubicOut',
    grid: {
      top: 12,
      right: 10,
      bottom: 3,
      left: 3,
      containLabel: true
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(16, 24, 40, 0.88)',
      borderWidth: 0,
      textStyle: {
        color: '#ffffff',
        fontSize: 11
      },
      formatter(params) {
        const point = params[0];
        return `${point.axisValue}\n${formatNumber(point.value)} 分`;
      }
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: period.categories,
      axisLine: {
        lineStyle: {
          color: '#dfe3e9',
          width: 1
        }
      },
      axisTick: {
        show: false
      },
      axisLabel: {
        color: '#696e76',
        fontSize: 11,
        margin: 10,
        interval: 0
      }
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: period.max,
      interval: period.interval,
      axisLine: {
        show: false
      },
      axisTick: {
        show: false
      },
      axisLabel: {
        color: '#777c84',
        fontSize: 11,
        margin: 10,
        formatter: formatNumber
      },
      splitLine: {
        show: true,
        lineStyle: {
          color: '#e8ebf0',
          type: 'dashed',
          width: 1
        }
      }
    },
    series: [
      {
        type: 'line',
        smooth: 0.42,
        showSymbol: true,
        symbol: 'circle',
        symbolSize(value, params) {
          return params.dataIndex === period.values.length - 1 ? 11 : 7;
        },
        data: period.values,
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
            { offset: 0, color: 'rgba(22, 119, 255, 0.28)' },
            { offset: 1, color: 'rgba(22, 119, 255, 0.02)' }
          ])
        }
      }
    ]
  };
}

Page({
  data: {
    state: 'success',
    overview: {},
    composition: {},
    details: [],
    periods: PERIODS,
    selectedPeriod: 'month',
    chartSummary: {
      label: PERIODS[0].summaryLabel,
      total: PERIODS[0].total
    },
    ec: {
      lazyLoad: true
    }
  },

  onShow() {
    this.setData({
      state: demo.getPageViewState('contribution'),
      overview: summaries.contributionOverview,
      composition: summaries.contributionComposition,
      details: summaries.contribution
    });
    updateTabBar(this, 'contribution');

    if (this.chart) {
      this.chart.resize();
    }
  },

  onReady() {
    this.chartComponent = this.selectComponent('#contribution-trend-chart');
    this.initChart();
  },

  initChart() {
    if (
      this.chart
      || !this.chartComponent
      || this.data.state !== 'success'
    ) {
      return;
    }

    this.chartComponent.init((canvas, width, height, dpr) => {
      const chart = echarts.init(canvas, null, {
        width,
        height,
        devicePixelRatio: dpr
      });
      const period = this.getSelectedPeriod();

      canvas.setChart(chart);
      chart.setOption(buildChartOption(period));
      this.chart = chart;

      return chart;
    });
  },

  getSelectedPeriod(periodId = this.data.selectedPeriod) {
    return PERIODS.find((item) => item.id === periodId) || PERIODS[0];
  },

  selectPeriod(e) {
    const selectedPeriod = e.currentTarget.dataset.id;
    const period = this.getSelectedPeriod(selectedPeriod);

    if (selectedPeriod === this.data.selectedPeriod) {
      return;
    }

    this.setData({
      selectedPeriod,
      chartSummary: {
        label: period.summaryLabel,
        total: period.total
      }
    });

    if (this.chart) {
      this.chart.setOption(buildChartOption(period), true);
    }
  },

  retry() {
    demo.setPageViewState('contribution', 'success');
    this.setData({ state: 'success' }, () => {
      this.chartComponent = this.selectComponent('#contribution-trend-chart');
      this.initChart();
    });
  },

  openAllDetails() {
    this.openActionPage('contribution-detail');
  },

  openDetail(e) {
    wx.navigateTo({
      url: '/pages/contribution-detail/index'
    });
  },

  openActionPage(actionId) {
    const result = openAction(actionId, getCurrentSession());

    if (result.ok) {
      wx.navigateTo({ url: result.url });
    } else {
      wx.showToast({ title: result.message, icon: 'none' });
    }
  }
});
