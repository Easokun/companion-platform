// pages/invite/invite.js
const { userApi } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    inviteCode: '',
    inviteCount: 0,
    inviteReward: 0,
    isLogin: false
  },

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
    this.checkLoginAndGenerate()
  },

  // 检查登录并生成邀请码
  checkLoginAndGenerate() {
    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) {
        this.setData({ isLogin: false, inviteCode: '' })
        return
      }
      this.setData({ isLogin: true })
      this.generateInviteCode(user)
    })
  },

  // 生成邀请码
  generateInviteCode(user) {
    let code = ''
    if (user && user.userId) {
      code = user.userId.replace('UID', '')
    } else {
      code = Math.random().toString(36).substring(2, 8).toUpperCase()
    }
    this.setData({ inviteCode: code })
  },

  goBack() {
    wx.navigateBack()
  },

  // 复制邀请码
  copyCode() {
    if (!this.data.inviteCode) {
      wx.showToast({ title: '请先登录', icon: 'none' })
      return
    }
    wx.setClipboardData({
      data: this.data.inviteCode,
      success: () => {
        wx.showToast({ title: '邀请码已复制', icon: 'success' })
      }
    })
  },

  // 微信分享给好友
  onShareAppMessage() {
    return {
      title: '快来加入电竞护航平台，专业护航带你飞！',
      path: '/pages/index/index?inviteCode=' + this.data.inviteCode,
      imageUrl: '/images/logo.png'
    }
  },

  // 分享到朋友圈
  onShareTimeline() {
    return {
      title: '电竞护航平台 - 专业游戏陪玩服务',
      query: 'inviteCode=' + this.data.inviteCode,
      imageUrl: '/images/logo.png'
    }
  },

  // 调用微信分享
  shareToWechat() {
    if (!this.data.isLogin) {
      wx.showToast({ title: '请先登录', icon: 'none' })
      return
    }
    wx.showShareMenu({
      withShareTicket: true,
      menus: ['shareAppMessage', 'shareTimeline']
    })
    wx.showToast({ title: '请点击右上角分享', icon: 'none' })
  }
})
