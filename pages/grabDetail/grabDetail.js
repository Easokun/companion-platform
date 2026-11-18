// pages/grabDetail/grabDetail.js
const { orderApi, userApi, escortApi, utils } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    orderId: '',
    order: null,
    earnPrice: '0.00',
    myNickName: '',
    // 邀请好友
    showInvitePopup: false,
    escortList: [],
    searchKeyword: '',
    selectedCount: 0,
    teamMembers: []
  },

  _searchTimer: null,

  // 空函数，用于阻止事件冒泡
  noop() {},

  onLoad(options) {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })

    if (options.orderId) {
      this.setData({ orderId: options.orderId })
      this.loadOrderDetail()
    }
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
      this.setData({ myNickName: user.nickName || '我' })
      if (this.data.orderId) {
        this.loadOrderDetail()
      }
      this.loadTeamMembers()
    })
  },

  loadOrderDetail() {
    orderApi.getOrderDetail(this.data.orderId).then(order => {
      if (order) {
        const rate = order.commissionRate || 0.9
        const earn = parseFloat(order.totalPrice || 0) * rate
        this.setData({
          order: order,
          earnPrice: earn.toFixed(2)
        })
      } else {
        wx.showToast({ title: '订单不存在', icon: 'none' })
        setTimeout(() => {
          wx.navigateBack()
        }, 1500)
      }
    })
  },

  loadTeamMembers() {
    if (!this.data.orderId) return
    escortApi.getTeamMembers(this.data.orderId).then(res => {
      const members = res.teamMembers || []
      this.setData({ teamMembers: members })
    }).catch(() => {})
  },

  // 复制文本
  onCopy(e) {
    const text = e.currentTarget.dataset.text
    if (!text) return
    wx.setClipboardData({
      data: text,
      success: () => {
        wx.showToast({ title: '已复制', icon: 'success' })
      }
    })
  },

  // 联系客服
  onContactKefu() {
    wx.showToast({ title: '客服功能开发中', icon: 'none' })
  },

  // ====== 邀请好友 ======

  openInvitePopup() {
    this.setData({ showInvitePopup: true, searchKeyword: '' })
    this.loadEscortList('')
  },

  closeInvitePopup() {
    this.setData({ showInvitePopup: false })
  },

  loadEscortList(keyword) {
    escortApi.getEscortList(keyword).then(res => {
      const list = (res.list || []).map(e => ({
        ...e,
        selected: this.isEscortSelected(e.openid)
      }))
      this.setData({ escortList: list })
    }).catch(() => {
      this.setData({ escortList: [] })
    })
  },

  isEscortSelected(openid) {
    return this.data.teamMembers.some(m => m.openid === openid)
  },

  onSearchInput(e) {
    const keyword = e.detail.value
    this.setData({ searchKeyword: keyword })
    if (this._searchTimer) clearTimeout(this._searchTimer)
    this._searchTimer = setTimeout(() => {
      this.loadEscortList(keyword)
    }, 300)
  },

  onSearchConfirm() {
    this.loadEscortList(this.data.searchKeyword)
  },

  clearSearch() {
    this.setData({ searchKeyword: '' })
    this.loadEscortList('')
  },

  toggleSelectEscort(e) {
    const { openid, index } = e.currentTarget.dataset
    const list = this.data.escortList
    const item = list[index]
    if (!item) return

    if (item.selected) {
      item.selected = false
    } else {
      const selectedCount = list.filter(i => i.selected).length
      if (selectedCount >= 2) {
        wx.showToast({ title: '最多邀请2名护航', icon: 'none' })
        return
      }
      item.selected = true
    }
    this.setData({
      escortList: list,
      selectedCount: list.filter(i => i.selected).length
    })
  },

  confirmInvite() {
    const selected = this.data.escortList.filter(e => e.selected)
    if (selected.length === 0) {
      wx.showToast({ title: '请选择护航', icon: 'none' })
      return
    }
    if (selected.length > 2) {
      wx.showToast({ title: '最多邀请2名护航', icon: 'none' })
      return
    }

    const members = selected.map(e => ({
      openid: e.openid,
      nickName: e.nickName,
      avatar: e.avatar || '',
      level: e.level || ''
    }))

    wx.showLoading({ title: '邀请中...' })
    escortApi.inviteTeamMembers(this.data.orderId, members).then(res => {
      wx.hideLoading()
      this.setData({
        showInvitePopup: false,
        teamMembers: res.teamMembers || members
      })
      wx.showToast({ title: '邀请成功', icon: 'success' })
    }).catch(() => {
      wx.hideLoading()
      wx.showToast({ title: '邀请失败', icon: 'none' })
    })
  },

  onRemoveMember(e) {
    const index = e.currentTarget.dataset.index
    const members = this.data.teamMembers.filter((_, i) => i !== index)
    wx.showLoading({ title: '移除中...' })
    escortApi.inviteTeamMembers(this.data.orderId, members).then(res => {
      wx.hideLoading()
      this.setData({ teamMembers: res.teamMembers || members })
      wx.showToast({ title: '已移除', icon: 'success' })
    }).catch(() => {
      wx.hideLoading()
    })
  },

  // 抢单
  onTakeOrder() {
    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) {
        wx.showToast({ title: '请先登录', icon: 'none' })
        return
      }

      wx.showModal({
        title: '确认抢单',
        content: '确定要接这个订单吗？\n接单后请尽快联系用户开始服务',
        confirmText: '确认抢单',
        confirmColor: '#10B981',
        success: (res) => {
          if (res.confirm) {
            escortApi.getEscortProfile(user.userId).then(escortProfile => {
              orderApi.takeOrder(this.data.orderId, user.userId, user.nickName, escortProfile).then(result => {
                if (result && result.success) {
                  wx.showToast({ title: '抢单成功', icon: 'success' })
                  setTimeout(() => {
                    wx.redirectTo({ url: '/pages/escortOrders/escortOrders' })
                  }, 1500)
                } else {
                  wx.showToast({ title: (result && result.message) || '抢单失败', icon: 'none' })
                  setTimeout(() => {
                    wx.navigateBack()
                  }, 1500)
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
