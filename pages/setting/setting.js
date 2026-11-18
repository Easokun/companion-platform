// pages/setting/setting.js
Page({
  data: {
    statusBarHeight: 44,
    // 通知设置
    notifyOrder: true,
    notifyMessage: true,
    // 缓存大小
    cacheSize: '0.00M'
  },

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
    this.calcCacheSize()
  },

  goBack() {
    wx.navigateBack()
  },

  // 计算缓存大小
  calcCacheSize() {
    try {
      const res = wx.getStorageInfoSync()
      const size = (res.currentSize / 1024).toFixed(2)
      this.setData({ cacheSize: size + 'M' })
    } catch (e) {
      this.setData({ cacheSize: '0.00M' })
    }
  },

  // 切换订单通知
  switchOrderNotify(e) {
    this.setData({ notifyOrder: e.detail.value })
  },

  // 切换消息通知
  switchMessageNotify(e) {
    this.setData({ notifyMessage: e.detail.value })
  },

  // 清除缓存（保留登录态）
  clearCache() {
    wx.showModal({
      title: '提示',
      content: '确定要清除缓存吗？\n将清除图片缓存、临时数据等，不会影响登录状态。',
      success: (res) => {
        if (res.confirm) {
          // 保留登录态关键数据
          const userInfo = wx.getStorageSync('userInfo')
          const token = wx.getStorageSync('token')

          // 清除所有缓存
          wx.clearStorageSync()

          // 恢复登录态
          if (userInfo) wx.setStorageSync('userInfo', userInfo)
          if (token) wx.setStorageSync('token', token)

          this.setData({ cacheSize: '0.00M' })
          wx.showToast({ title: '缓存已清除', icon: 'success' })
        }
      }
    })
  },

  // 意见反馈
  goFeedback() {
    wx.navigateTo({ url: '/pages/feedback/feedback' })
  },

  // 关于我们
  goAbout() {
    wx.navigateTo({ url: '/pages/about/about' })
  },

  // 检查更新
  checkUpdate() {
    if (wx.canIUse('getUpdateManager')) {
      const updateManager = wx.getUpdateManager()
      updateManager.onCheckForUpdate(function (res) {
        if (!res.hasUpdate) {
          wx.showToast({ title: '当前已是最新版本', icon: 'none' })
        }
      })
      updateManager.onUpdateReady(function () {
        wx.showModal({
          title: '更新提示',
          content: '新版本已经准备好，是否重启应用？',
          success: function (res) {
            if (res.confirm) {
              updateManager.applyUpdate()
            }
          }
        })
      })
      updateManager.onUpdateFailed(function () {
        wx.showToast({ title: '更新失败，请检查网络后重试', icon: 'none' })
      })
    } else {
      wx.showToast({ title: '当前已是最新版本', icon: 'none' })
    }
  }
})
