// pages/confirmOrder/confirmOrder.js
const { orderApi, userApi, utils, payApi, walletApi } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    service: null,
    quantity: 1,
    regions: ['qv区'],
    selectedRegion: 0,
    gameId: '',
    gameNickname: '',
    remark: '',
    totalPrice: '0.00',
    showPayPopup: false,
    walletBalance: '0.00',
    pendingOrderId: ''
  },

  _lastSubmitTime: 0,

  onLoad(options) {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })

    if (options.id) {
      const price = parseFloat(options.price) || 0
      const service = {
        id: options.id,
        name: decodeURIComponent(options.name),
        price: price,
        priceText: price.toFixed(2),
        icon: decodeURIComponent(options.icon || '🎮'),
        desc: decodeURIComponent(options.desc),
        tag: decodeURIComponent(options.tag),
        tagColor: options.tagColor ? decodeURIComponent(options.tagColor) : 'linear-gradient(90deg, #7B61FF, #A78BFA)',
        image: decodeURIComponent(options.image || '/images/logo.png')
      }
      this.setData({
        service: service,
        totalPrice: price.toFixed(2)
      })
    }
  },

  onMinus() {
    if (this.data.quantity <= 1) return
    const quantity = this.data.quantity - 1
    const price = this.data.service.price
    this.setData({
      quantity: quantity,
      totalPrice: (price * quantity).toFixed(2)
    })
  },

  onPlus() {
    if (this.data.quantity >= 10) {
      wx.showToast({ title: '最多购买10份', icon: 'none' })
      return
    }
    const quantity = this.data.quantity + 1
    const price = this.data.service.price
    this.setData({
      quantity: quantity,
      totalPrice: (price * quantity).toFixed(2)
    })
  },

  onSelectRegion(e) {
    const index = e.currentTarget.dataset.index
    this.setData({ selectedRegion: index })
  },

  onGameIdInput(e) {
    this.setData({ gameId: e.detail.value })
  },

  onNicknameInput(e) {
    this.setData({ gameNickname: e.detail.value })
  },

  onRemarkInput(e) {
    this.setData({ remark: e.detail.value })
  },

  // 提交订单 + 微信支付
  onPay() {
    if (!this.data.service) return
    if (!this.data.gameId) {
      wx.showToast({ title: '请输入游戏ID', icon: 'none' })
      return
    }
    if (!this.data.gameNickname) {
      wx.showToast({ title: '请输入游戏昵称', icon: 'none' })
      return
    }

    if (Date.now() - this._lastSubmitTime < 3000) {
      wx.showToast({ title: '操作太频繁，请稍后再试', icon: 'none' })
      return
    }

    wx.showLoading({ title: '正在下单...', mask: true })

    userApi.getCurrentUser().then(userInfo => {
      userInfo = userInfo || {}

      if (!userInfo.userId) {
        wx.hideLoading()
        wx.showToast({ title: '请先登录', icon: 'none' })
        return
      }

      // 1. 创建订单（未支付）
      const order = {
        orderId: utils.generateId('ORD'),
        userId: userInfo.userId || '',
        userName: userInfo.nickName || '',
        serviceId: this.data.service.id,
        serviceName: this.data.service.name,
        serviceDesc: this.data.service.desc,
        serviceImage: this.data.service.image,
        price: this.data.service.price,
        quantity: this.data.quantity,
        totalPrice: this.data.totalPrice,
        region: this.data.regions[this.data.selectedRegion],
        gameId: this.data.gameId,
        gameNickname: this.data.gameNickname,
        remark: this.data.remark
      }

      orderApi.createOrder(order).then(result => {
        if (!result) {
          wx.hideLoading()
          wx.showToast({ title: '下单失败，请重试', icon: 'none' })
          return
        }

        const realOrderId = result.orderId || result.id || order.orderId
        wx.hideLoading()
        this._lastSubmitTime = Date.now()

        // 弹出支付方式选择
        this.setData({ pendingOrderId: realOrderId })
        this.loadWalletBalance()
      }).catch(err => {
        wx.hideLoading()
        const msg = (err && err.msg) || (err && err.statusCode ? '服务器错误 ' + err.statusCode : '下单失败，请重试')
        wx.showToast({ title: msg, icon: 'none' })
      })
    })
  },

  loadWalletBalance() {
    walletApi.getWallet().then(wallet => {
      const balance = parseFloat((wallet && wallet.balance) || 0).toFixed(2)
      this.setData({ walletBalance: balance, showPayPopup: true })
    }).catch(() => {
      this.setData({ walletBalance: '0.00', showPayPopup: true })
    })
  },

  closePayPopup() {
    this.setData({ showPayPopup: false })
  },

  noop() {},

  onChooseWalletPay() {
    if (this._payProcessing) return
    const orderId = this.data.pendingOrderId
    const balance = parseFloat(this.data.walletBalance)
    const price = parseFloat(this.data.totalPrice)

    if (balance < price) {
      wx.showToast({ title: '钱包余额不足', icon: 'none' })
      return
    }

    this._payProcessing = true
    wx.showLoading({ title: '支付中...', mask: true })
    payApi.walletPay(orderId).then(res => {
      wx.hideLoading()
      this._payProcessing = false
      this.setData({ showPayPopup: false })
      wx.showToast({
        title: '支付成功',
        icon: 'success',
        duration: 1500,
        success: () => {
          setTimeout(() => {
            wx.redirectTo({
              url: '/pages/orderDetail/orderDetail?orderId=' + orderId
            })
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

  onClose() {
    wx.navigateBack()
  }
})
