// pages/about/about.js
Page({
  data: {
    statusBarHeight: 44,
    version: '1.0.0'
  },

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
  },

  goBack() {
    wx.navigateBack()
  },

  // 用户协议
  onUserAgreement() {
    wx.showToast({ title: '用户协议开发中', icon: 'none' })
  },

  // 隐私政策
  onPrivacyPolicy() {
    wx.showToast({ title: '隐私政策开发中', icon: 'none' })
  },

  // 复制工信部链接
  copyICP() {
    wx.setClipboardData({
      data: 'https://beian.mit.gov.cn/',
      success: () => {
        wx.showToast({ title: '工信部链接已复制', icon: 'none' })
      }
    })
  }
})
