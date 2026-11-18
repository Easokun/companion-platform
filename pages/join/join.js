// pages/join/join.js
const { applyApi, userApi } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    applyStatus: null,    // null=未申请 0=审核中 1=已通过 2=已拒绝 3=已取消 'banned'=封禁
    applyStatusText: '',
    applyId: '',
    // 封禁信息
    banInfo: {
      banned: false,
      count: 0,
      banEndTime: '',
      reason: ''
    }
  },

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
  },

  onShow() {
    if (typeof this.getTabBar === 'function' && this.getTabBar()) {
      this.getTabBar().setData({ selected: 3 })
    }
    this.checkApplyStatus()
  },

  // 检查申请状态
  checkApplyStatus() {
    // 强制刷新用户信息（确保 userType 是最新的，比如刚通过审核）
    userApi.getCurrentUser(true).then(user => {
      if (!user || !user.userId) {
        this.setData({
          applyStatus: null,
          applyStatusText: '',
          applyId: '',
          banInfo: { banned: false, count: 0, banEndTime: '', reason: '' }
        })
        return
      }

      // 先检查封禁状态
      applyApi.checkBanStatus(user.userId).then(banInfo => {
        this.setData({ banInfo })

        if (banInfo.banned) {
          this.setData({
            applyStatus: 'banned',
            applyStatusText: '暂无法申请'
          })
          return
        }

        // 以实际 userType 为准
        const userType = user.userType || 0
        if (userType === 1) {
          // 实际是护航，显示已通过
          this.setData({
            applyStatus: 1,
            applyStatusText: '已通过',
            applyId: ''
          })
          return
        }

        // 不是护航，看申请记录
        applyApi.getUserApply(user.userId).then(apply => {
          if (apply) {
            // 如果申请记录是已通过，但用户不是护航，说明被撤销了
            if (apply.status === 1) {
              this.setData({
                applyStatus: 4,
                applyStatusText: '已撤销',
                applyId: apply.id
              })
            } else {
              this.setData({
                applyStatus: apply.status,
                applyStatusText: apply.statusText,
                applyId: apply.id
              })
            }
          } else {
            this.setData({
              applyStatus: null,
              applyStatusText: '',
              applyId: ''
            })
          }
        })
      })
    })
  },

  // 点击申请
  onApplyTap() {
    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) {
        wx.showToast({ title: '请先登录', icon: 'none' })
        return
      }

      if (this.data.banInfo.banned) {
        wx.showModal({
          title: '无法申请',
          content: this.data.banInfo.reason + '，解封时间：' + this.data.banInfo.banEndTime,
          showCancel: false
        })
        return
      }

      if (this.data.applyStatus === 0) {
        wx.showToast({ title: '申请审核中，请耐心等待', icon: 'none' })
        return
      }

      if (this.data.applyStatus === 1) {
        // 已是护航，跳转到抢单大厅
        wx.navigateTo({ url: '/pages/grabHall/grabHall' })
        return
      }

      wx.navigateTo({
        url: '/pages/joinApply/joinApply'
      })
    })
  },

  // 取消申请
  onCancelApply() {
    if (!this.data.applyId) return
    wx.showModal({
      title: '确认取消',
      content: '确定要取消本次护航申请吗？\n（30天内取消3次将被封禁30天）',
      confirmText: '取消申请',
      confirmColor: '#FF6B6B',
      success: (res) => {
        if (res.confirm) {
          applyApi.cancelApply(this.data.applyId).then(() => {
            wx.showToast({ title: '已取消申请', icon: 'none' })
            this.checkApplyStatus()
          })
        }
      }
    })
  }
})
