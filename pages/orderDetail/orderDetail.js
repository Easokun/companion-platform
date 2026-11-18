// pages/orderDetail/orderDetail.js
const { orderApi, utils, payApi, userApi, walletApi, ORDER_STATUS } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    order: null,
    showPayPopup: false,
    walletBalance: '0.00'
  },

  onLoad(options) {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })

    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) {
        wx.showToast({ title: '请先登录', icon: 'none' })
        setTimeout(() => wx.navigateBack(), 1500)
        return
      }
      if (options.orderId) {
        this.loadOrder(options.orderId)
      }
    }).catch(() => {
      wx.showToast({ title: '请先登录', icon: 'none' })
      setTimeout(() => wx.navigateBack(), 1500)
    })
  },

  onShow() {
    if (this.data.order && this.data.order.orderId) {
      this.loadOrder(this.data.order.orderId)
    }
  },

  loadOrder(orderId) {
    orderApi.getOrderDetail(orderId).then(order => {
      if (order) {
        // 格式化时间
        order = {
          ...order,
          createTimeText: utils.formatTime(order.createTime),
          takeTimeText: order.takeTime ? utils.formatTime(order.takeTime) : '',
          startTimeText: order.startTime ? utils.formatTime(order.startTime) : '',
          completeTimeText: order.completeTime ? utils.formatTime(order.completeTime) : ''
        }
        this.setData({ order })
      } else {
        wx.showToast({ title: '订单不存在', icon: 'none' })
        setTimeout(() => wx.navigateBack(), 1500)
      }
    })
  },

  goBack() {
    wx.navigateBack()
  },

  // 联系客服
  onContactKefu() {
    wx.showToast({ title: '联系客服', icon: 'none' })
  },

  // 取消订单
  onCancelOrder() {
    const order = this.data.order
    const isPendingPayment = order && order.status === ORDER_STATUS.PENDING_PAYMENT
    const content = isPendingPayment
      ? '确定要取消该订单吗？\n订单尚未支付，取消后不会产生费用'
      : '确定要取消该订单吗？\n取消后款项将原路退回钱包'
    wx.showModal({
      title: '提示',
      content: content,
      success: (res) => {
        if (res.confirm) {
          orderApi.cancelOrder(this.data.order.orderId).then(result => {
            if (result && result.success) {
              wx.showToast({ title: '订单已取消', icon: 'success' })
              setTimeout(() => {
                this.loadOrder(this.data.order.orderId)
              }, 500)
            } else {
              wx.showToast({ title: (result && result.message) || '取消失败', icon: 'none' })
            }
          })
        }
      }
    })
  },

  // 去支付 - 弹出支付方式选择
  onPayNow() {
    const order = this.data.order
    if (!order) return
    walletApi.getWallet().then(wallet => {
      const balance = parseFloat((wallet && wallet.balance) || 0).toFixed(2)
      this.setData({ walletBalance: balance, showPayPopup: true })
    }).catch(() => {
      this.setData({ walletBalance: '0.00', showPayPopup: true })
    })
  },

  noop() {},

  closePayPopup() {
    this.setData({ showPayPopup: false })
  },

  onChooseWalletPay() {
    if (this._payProcessing) return
    const order = this.data.order
    const balance = parseFloat(this.data.walletBalance)
    const price = parseFloat(order.totalPrice || order.price)

    if (balance < price) {
      wx.showToast({ title: '钱包余额不足', icon: 'none' })
      return
    }

    this._payProcessing = true
    wx.showLoading({ title: '支付中...', mask: true })
    payApi.walletPay(order.orderId).then(() => {
      wx.hideLoading()
      this._payProcessing = false
      this.setData({ showPayPopup: false })
      wx.showToast({
        title: '支付成功',
        icon: 'success',
        duration: 1500,
        success: () => {
          setTimeout(() => {
            this.loadOrder(order.orderId)
          }, 1500)
        }
      })
    }).catch(err => {
      wx.hideLoading()
      this._payProcessing = false
      const msg = (err && err.msg) || '支付失败，请重试'
      wx.showToast({ title: msg, icon: 'none' })
    })
  },

  onChooseWechatPay() {
    // 余额不足时跳转充值
    wx.navigateTo({ url: '/pages/wallet/wallet' })
  },

  // 确认完成
  onConfirmComplete() {
    wx.showModal({
      title: '确认完成',
      content: '确认服务已完成？确认后订单将完成结算，佣金将发放给护航。',
      confirmText: '确认完成',
      confirmColor: '#10B981',
      success: (res) => {
        if (res.confirm) {
          wx.showLoading({ title: '确认中...', mask: true })
          orderApi.confirmComplete(this.data.order.orderId).then(result => {
            wx.hideLoading()
            if (result && result.success) {
              wx.showToast({ title: '已确认完成', icon: 'success' })
              setTimeout(() => {
                this.loadOrder(this.data.order.orderId)
              }, 500)
            } else {
              wx.showToast({ title: (result && result.message) || '操作失败', icon: 'none' })
            }
          })
        }
      }
    })
  }
})
