// pages/grabHall/grabHall.js
const { orderApi, userApi, escortApi, utils } = require('../../utils/api.js')

const LEVEL_ORDER = ['黑铁', '青铜', '白银', '黄金', '铂金', '翡翠', '钻石', '大师', '宗师', '王者']
const DELAY_MS = 5000

Page({
  data: {
    statusBarHeight: 44,
    orders: [],
    loading: false,
    lastRefreshText: ''
  },

  _refreshTimer: null,
  _delayTimer: null,
  _REFRESH_INTERVAL: 15000,

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
  },

  onShow() {
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
      escortApi.getEscortProfile(user.userId).then(profile => {
        const level = (profile && profile.level) || ''
        const levelIndex = LEVEL_ORDER.indexOf(level)
        const isLowLevel = levelIndex >= 0 && levelIndex < LEVEL_ORDER.indexOf('黄金')
        if (isLowLevel) {
          this.setData({ loading: true, orders: [] })
          this._delayTimer = setTimeout(() => {
            this.loadOrders()
            this.startAutoRefresh()
          }, DELAY_MS)
        } else {
          this.loadOrders()
          this.startAutoRefresh()
        }
      }).catch(() => {
        this.loadOrders()
        this.startAutoRefresh()
      })
    })
  },

  onHide() {
    this.stopAutoRefresh()
    this.stopDelay()
  },

  onUnload() {
    this.stopAutoRefresh()
    this.stopDelay()
  },

  stopDelay() {
    if (this._delayTimer) {
      clearTimeout(this._delayTimer)
      this._delayTimer = null
    }
  },

  onPullDownRefresh() {
    this.loadOrders().then(() => {
      wx.stopPullDownRefresh()
    }).catch(() => {
      wx.stopPullDownRefresh()
    })
  },

  startAutoRefresh() {
    this.stopAutoRefresh()
    this._refreshTimer = setInterval(() => {
      this.loadOrders(true)
    }, this._REFRESH_INTERVAL)
  },

  stopAutoRefresh() {
    if (this._refreshTimer) {
      clearInterval(this._refreshTimer)
      this._refreshTimer = null
    }
  },

  loadOrders(silent = false) {
    if (!silent) {
      this.setData({ loading: true })
    }
    return orderApi.getAvailableOrders({ page: 1, pageSize: 50 }).then(res => {
      let orders = res.list || res || []
      orders = orders.map(o => ({
        ...o,
        createTimeText: utils.formatTime(o.createTime)
      }))
      const now = new Date()
      const timeStr = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}`
      this.setData({
        orders,
        loading: false,
        lastRefreshText: '上次刷新：' + timeStr
      })
    }).catch(() => {
      this.setData({ loading: false })
    })
  },

  onOrderTap(e) {
    const orderId = e.currentTarget.dataset.id
    wx.navigateTo({
      url: '/pages/grabDetail/grabDetail?orderId=' + orderId
    })
  },

  onTakeOrder(e) {
    const orderId = e.currentTarget.dataset.id

    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) {
        wx.showToast({ title: '请先登录', icon: 'none' })
        return
      }

      wx.showModal({
        title: '确认抢单',
        content: '确定要接这个订单吗？',
        success: (res) => {
          if (res.confirm) {
            escortApi.getEscortProfile(user.userId).then(escortProfile => {
              orderApi.takeOrder(orderId, user.userId, user.nickName, escortProfile).then(result => {
                if (result && result.success) {
                  wx.showToast({ title: '抢单成功', icon: 'success' })
                  this.loadOrders()
                } else {
                  wx.showToast({ title: (result && result.message) || '抢单失败', icon: 'none' })
                }
              }).catch(err => {
                if (err && !err.msg) {
                  wx.showToast({ title: '抢单失败', icon: 'none' })
                }
              })
            })
          }
        }
      })
    })
  },

  goBack() {
    wx.navigateBack()
  }
})
