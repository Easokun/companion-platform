// pages/orders/orders.js
const { orderApi, utils, userApi, ORDER_STATUS } = require('../../utils/api.js')

// 每页加载数量
const PAGE_SIZE = 10

// Tab 对应状态码（数字状态码，与 ORDER_STATUS 常量一致）
// 索引0=全部, 1=待支付(PENDING_PAYMENT=7), 2=待接单(PENDING=0), 3=进行中(IN_PROGRESS=1),
// 4=服务中(IN_SERVICE=5), 5=待确认(TO_CONFIRM=6), 6=已完成(COMPLETED=2), 7=已取消(CANCELLED=4)
const TAB_STATUS_MAP = {
  0: '',            // 全部
  1: ORDER_STATUS.PENDING_PAYMENT,
  2: ORDER_STATUS.PENDING,
  3: ORDER_STATUS.IN_PROGRESS,
  4: ORDER_STATUS.IN_SERVICE,
  5: ORDER_STATUS.TO_CONFIRM,
  6: ORDER_STATUS.COMPLETED,
  7: ORDER_STATUS.CANCELLED
}

Page({
  data: {
    statusBarHeight: 44,
    activeTab: 0,
    tabs: ['全部', '待支付', '待接单', '进行中', '服务中', '待确认', '已完成', '已取消'],
    // 分页相关
    page: 1,
    hasMore: true,
    loading: false,
    // 当前显示的订单数据
    displayOrders: []
  },

  onLoad(options) {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
    // 如果带了tab参数，切换到对应tab
    if (options.tab) {
      const tabIndex = parseInt(options.tab)
      this.setData({ activeTab: tabIndex })
    }
  },

  onShow() {
    // 每次显示时重置并重新加载
    this.loadOrders(true)
  },

  // 加载订单数据
  // reset: 是否重置（从头加载），false=加载下一页
  loadOrders(reset = false) {
    if (this.data.loading) return
    if (!reset && !this.data.hasMore) return

    this.setData({ loading: true })

    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) {
        this.setData({ displayOrders: [], loading: false, hasMore: false })
        return
      }

      const page = reset ? 1 : this.data.page + 1
      const status = TAB_STATUS_MAP[this.data.activeTab]

      orderApi.getUserOrders(user.userId, { status, page, pageSize: PAGE_SIZE }).then(res => {
        const list = (res.list || []).map(o => ({
          ...o,
          createTimeText: utils.formatTime(o.createTime)
        }))

        if (reset) {
          this.setData({
            displayOrders: list,
            page: 1,
            hasMore: list.length >= PAGE_SIZE,
            loading: false
          })
          wx.stopPullDownRefresh()
        } else {
          this.setData({
            displayOrders: this.data.displayOrders.concat(list),
            page: page,
            hasMore: list.length >= PAGE_SIZE,
            loading: false
          })
        }
      }).catch(() => {
        this.setData({ loading: false })
        wx.stopPullDownRefresh()
      })
    })
  },

  // 切换 tab
  switchTab(e) {
    const index = e.currentTarget.dataset.index
    this.setData({ activeTab: index }, () => {
      this.loadOrders(true)
    })
  },

  // 下拉刷新
  onPullDownRefresh() {
    this.loadOrders(true)
  },

  // 上拉加载更多
  onReachBottom() {
    if (this.data.hasMore && !this.data.loading) {
      this.loadOrders(false)
    }
  },

  // 点击订单进入详情
  onOrderTap(e) {
    const orderId = e.currentTarget.dataset.orderId
    wx.navigateTo({
      url: '/pages/orderDetail/orderDetail?orderId=' + orderId
    })
  },

  // 返回上一页
  goBack() {
    const pages = getCurrentPages()
    if (pages.length > 1) {
      wx.navigateBack()
    } else {
      wx.switchTab({
        url: '/pages/index/index'
      })
    }
  },

  // 去首页逛逛
  goHome() {
    wx.switchTab({
      url: '/pages/index/index'
    })
  }
})
