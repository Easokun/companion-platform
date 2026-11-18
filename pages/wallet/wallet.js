// pages/wallet/wallet.js
const { walletApi, utils, userApi, payApi } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    balance: '0.00',
    totalRecharge: '0.00',
    totalSpend: '0.00',
    amount: '',
    isLogin: false,
    flowList: [],
    flowPage: 1,
    flowPageSize: 20,
    flowTotal: 0,
    hasMoreFlows: false,
    loadingFlows: false
  },

  onLoad() {
    const systemInfo = wx.getSystemInfoSync()
    this.setData({ statusBarHeight: systemInfo.statusBarHeight })
  },

  onShow() {
    this.checkLoginAndLoad()
  },

  checkLoginAndLoad() {
    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) {
        this.setData({ isLogin: false, balance: '0.00', flowList: [] })
        return
      }
      this.setData({ isLogin: true })
      this.loadBalance()
      this.loadFlows(true)
    })
  },

  loadBalance() {
    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) return
      userApi.getWallet(user.userId).then(wallet => {
        this.setData({
          balance: parseFloat(wallet.balance || 0).toFixed(2),
          totalRecharge: parseFloat(wallet.totalRecharge || 0).toFixed(2),
          totalSpend: parseFloat(wallet.totalSpend || 0).toFixed(2)
        })
      })
    })
  },

  loadFlows(reset = false) {
    if (this.data.loadingFlows) return
    if (reset) {
      this.setData({ flowPage: 1, flowList: [], hasMoreFlows: true })
    }
    if (!this.data.hasMoreFlows && !reset) return

    this.setData({ loadingFlows: true })
    walletApi.getFlows({
      page: this.data.flowPage,
      pageSize: this.data.flowPageSize
    }).then(res => {
      const list = res.list || []
      const formatted = list.map(item => ({
        ...item,
        amountStr: (item.type === 1 ? '+' : '-') + parseFloat(item.amount || 0).toFixed(2),
        isIncome: item.type === 1,
        timeStr: item.createTime || ''
      }))
      const newList = reset ? formatted : this.data.flowList.concat(formatted)
      this.setData({
        flowList: newList,
        flowTotal: res.total || 0,
        hasMoreFlows: newList.length < (res.total || 0),
        flowPage: this.data.flowPage + 1,
        loadingFlows: false
      })
    }).catch(() => {
      this.setData({ loadingFlows: false })
    })
  },

  onReachBottom() {
    if (this.data.isLogin && this.data.hasMoreFlows) {
      this.loadFlows(false)
    }
  },

  onAmountInput(e) {
    this.setData({ amount: e.detail.value })
  },

  goBack() {
    wx.navigateBack()
  },

  selectAmount(e) {
    const amount = e.currentTarget.dataset.amount
    this.setData({ amount: amount })
  },

  // 虚拟支付充值
  recharge() {
    const amount = parseFloat(this.data.amount)
    if (!amount || amount <= 0) {
      wx.showToast({ title: '请输入充值金额', icon: 'none' })
      return
    }
    if (amount !== Math.floor(amount)) {
      wx.showToast({ title: '仅支持整数金额充值', icon: 'none' })
      return
    }

    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId) {
        wx.showToast({ title: '请先登录', icon: 'none' })
        return
      }

      wx.showModal({
        title: '确认充值',
        content: `确认充值 ¥${amount}？`,
        success: (res) => {
          if (!res.confirm) return

          // 1. 调用后端虚拟支付下单
          wx.showLoading({ title: '拉起支付...', mask: true })
          payApi.virtualRecharge(amount).then(payResult => {
            // 2. 调起虚拟支付
            payApi.requestVirtualPayment(payResult).then(() => {
              // 3. 支付成功，通知后端确认并加余额
              wx.showLoading({ title: '确认充值...', mask: true })
              payApi.virtualConfirm(payResult.outTradeNo).then(confirmResult => {
                wx.hideLoading()
                this.setData({ amount: '' })
                if (confirmResult && confirmResult.balance !== undefined) {
                  this.setData({ balance: confirmResult.balance })
                }
                this.loadFlows(true)
                wx.showToast({ title: '充值成功', icon: 'success' })
              }).catch(confirmErr => {
                wx.hideLoading()
                // 确认失败，延迟刷新余额（回调可能已处理）
                setTimeout(() => {
                  this.loadBalance()
                  this.loadFlows(true)
                }, 2000)
                wx.showToast({ title: '请刷新查看余额', icon: 'none' })
              })
            }).catch(payErr => {
              wx.hideLoading()
              if (payErr && payErr.errMsg && payErr.errMsg.includes('cancel')) {
                wx.showToast({ title: '支付已取消', icon: 'none' })
              } else {
                wx.showToast({ title: '支付失败', icon: 'none' })
              }
            })
          }).catch(err => {
            wx.hideLoading()
            const msg = (err && err.msg) || '充值服务不可用'
            wx.showToast({ title: msg, icon: 'none' })
          })
        }
      })
    })
  }
})
