// pages/escortOrders/escortOrders.js
const { orderApi, userApi, utils, PLATFORM_COMMISSION } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    activeTab: 1, // 1=进行中 5=服务中 6=待确认 2=已完成 4=已取消
    tabs: [
      { id: 1, text: '进行中' },
      { id: 5, text: '服务中' },
      { id: 6, text: '待确认' },
      { id: 2, text: '已完成' },
      { id: 4, text: '已取消' }
    ],
    orders: [],
    loading: false
  },

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
  },

  onShow() {
    // 权限校验：只有护航才能查看服务订单
    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId || (user.userType || 0) !== 1) {
        wx.showModal({
          title: '提示',
          content: '您还不是护航，请先申请成为护航',
          showCancel: false,
          success: () => {
            wx.navigateBack()
          }
        })
        return
      }
      this.loadOrders()
    })
  },

  loadOrders() {
    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) return

      this.setData({ loading: true })
      orderApi.getEscortOrders(user.userId, {
        status: this.data.activeTab,
        page: 1,
        pageSize: 100
      }).then(res => {
        let orders = res.list || res || []
        orders = orders.map(o => {
          const rate = o.commissionRate || 0.9
          const teamCount = (o.teamMembers && o.teamMembers.length > 0) ? (1 + o.teamMembers.length) : 1
          const earn = (parseFloat(o.totalPrice || 0) * rate / teamCount).toFixed(2)
          return {
            ...o,
            createTimeText: utils.formatTime(o.createTime),
            takeTimeText: o.takeTime ? utils.formatTime(o.takeTime) : '',
            completeTimeText: o.completeTime ? utils.formatTime(o.completeTime) : '',
            earnAmount: earn,
            teamCount: teamCount
          }
        })
        this.setData({ orders, loading: false })
      }).catch(() => {
        this.setData({ loading: false })
      })
    })
  },

  switchTab(e) {
    const id = e.currentTarget.dataset.id
    this.setData({ activeTab: id }, () => {
      this.loadOrders()
    })
  },

  // 点击订单进入详情
  onOrderTap(e) {
    const orderId = e.currentTarget.dataset.id
    wx.navigateTo({
      url: '/pages/escortOrderDetail/escortOrderDetail?orderId=' + orderId
    })
  },

  goBack() {
    wx.navigateBack()
  }
})
