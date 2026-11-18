// pages/escortOrderDetail/escortOrderDetail.js
const { orderApi, userApi, escortApi, utils } = require('../../utils/api.js')

Page({
  data: {
    statusBarHeight: 44,
    activeTab: 0,
    orderId: '',
    order: null,
    earnPrice: '0.00',
    teamCount: 1,
    teamMembers: [],
    createTimeText: '',
    escortName: '',
    // 退单弹窗
    showRefund: false,
    refundReason: '',
    bombCount: 0,
    // 完成服务倒计时
    canComplete: false,
    countdownText: '',
    // 上传完成照片弹窗
    showCompleteModal: false,
    completePhotos: [],
    completePhotoMax: 5,
    completeRemark: '',
    // 邀请好友弹窗
    showInvitePopup: false,
    escortList: [],
    searchKeyword: '',
    selectedCount: 0
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
    // 权限校验
    userApi.getCurrentUser().then(user => {
      if (!user || !user.userId || (user.userType || 0) !== 1) {
        wx.showModal({
          title: '提示',
          content: '您还不是护航',
          showCancel: false,
          success: () => {
            wx.navigateBack()
          }
        })
        return
      }
      if (this.data.orderId) {
        this.loadOrderDetail()
      }
    })
  },

  onUnload() {
    // 清理倒计时
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer)
      this._countdownTimer = null
    }
  },

  onHide() {
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer)
      this._countdownTimer = null
    }
  },

  loadOrderDetail() {
    userApi.getCurrentUser().then(user => {
      orderApi.getEscortOrderDetail(this.data.orderId).then(order => {
        if (order) {
          const rate = order.commissionRate || 0.9
          const teamMembers = order.teamMembers || []
          const teamCount = teamMembers.length > 0 ? (1 + teamMembers.length) : 1
          const earn = parseFloat(order.totalPrice || 0) * rate / teamCount
          this.setData({
            order: order,
            earnPrice: earn.toFixed(2),
            teamCount: teamCount,
            teamMembers: teamMembers,
            createTimeText: utils.formatTime(order.createTime),
            escortName: user ? user.nickName : '护航'
          })

          // 如果是服务中状态，检查倒计时
          if (order.status === 5 && order.startTime) {
            this.startCountdown()
          }
        } else {
          wx.showToast({ title: '订单不存在', icon: 'none' })
          setTimeout(() => {
            wx.navigateBack()
          }, 1500)
        }
      })
    })
  },

  // 启动完成服务倒计时（5分钟）
  startCountdown() {
    // 如果已有定时器，先清理
    if (this._countdownTimer) {
      clearInterval(this._countdownTimer)
    }

    // 计算剩余秒数
    const now = Date.now()
    const fiveMin = 5 * 60 * 1000
    // startTime 可能是时间戳（数字）也可能是格式化字符串（"2026-08-03 10:30"）
    let startTimeMs = Number(this.data.order.startTime)
    if (isNaN(startTimeMs)) {
      // 字符串格式，转成 Date 再取时间戳（兼容 YYYY-MM-DD HH:mm 和 YYYY-MM-DD HH:mm:ss）
      const timeStr = String(this.data.order.startTime).replace(/-/g, '/')
      startTimeMs = new Date(timeStr).getTime()
    }
    const elapsed = now - startTimeMs
    let remainingSeconds = Math.max(0, Math.ceil((fiveMin - elapsed) / 1000))

    if (remainingSeconds <= 0) {
      this.setData({
        canComplete: true,
        countdownText: ''
      })
      return
    }

    // 记录剩余秒数
    this._remainingSeconds = remainingSeconds
    this._updateCountdownText()

    this._countdownTimer = setInterval(() => {
      this._remainingSeconds--
      if (this._remainingSeconds <= 0) {
        clearInterval(this._countdownTimer)
        this._countdownTimer = null
        this.setData({
          canComplete: true,
          countdownText: ''
        })
      } else {
        this._updateCountdownText()
      }
    }, 1000)
  },

  _updateCountdownText() {
    const remaining = this._remainingSeconds || 0
    const min = Math.floor(remaining / 60)
    const sec = remaining % 60
    const text = `${min}:${String(sec).padStart(2, '0')}后可完成`
    this.setData({
      canComplete: false,
      countdownText: text
    })
  },

  switchTab(e) {
    const id = e.currentTarget.dataset.id
    this.setData({ activeTab: parseInt(id) })
  },

  // 复制
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

  // 邀请好友
  onInvite() {
    this.setData({ showInvitePopup: true, searchKeyword: '', selectedCount: 0 })
    this.loadEscortList('')
  },

  closeInvitePopup() {
    this.setData({ showInvitePopup: false })
  },

  loadEscortList(keyword) {
    escortApi.getEscortList(keyword).then(res => {
      const list = (res.list || []).map(e => ({
        ...e,
        selected: this.data.teamMembers.some(m => m.openid === e.openid)
      }))
      this.setData({ escortList: list, selectedCount: list.filter(i => i.selected).length })
    }).catch(() => {
      this.setData({ escortList: [] })
    })
  },

  onSearchInput(e) {
    const keyword = e.detail.value
    this.setData({ searchKeyword: keyword })
    if (this._searchTimer) clearTimeout(this._searchTimer)
    this._searchTimer = setTimeout(() => {
      this.loadEscortList(keyword)
    }, 300)
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
      const teamMembers = res.teamMembers || members
      const teamCount = 1 + teamMembers.length
      const rate = (this.data.order && this.data.order.commissionRate) || 0.9
      const earn = parseFloat(this.data.order.totalPrice || 0) * rate / teamCount
      this.setData({
        showInvitePopup: false,
        teamMembers: teamMembers,
        teamCount: teamCount,
        earnPrice: earn.toFixed(2)
      })
      wx.showToast({ title: '邀请成功', icon: 'success' })
    }).catch(() => {
      wx.hideLoading()
      wx.showToast({ title: '邀请失败', icon: 'none' })
    })
  },

  // 阻止事件冒泡
  stopPropagation() {},

  // 显示退单弹窗
  showRefundModal() {
    this.setData({
      showRefund: true,
      refundReason: '',
      bombCount: 0
    })
  },

  // 隐藏退单弹窗
  hideRefundModal() {
    this.setData({ showRefund: false })
  },

  // 退单说明输入
  onRefundReasonInput(e) {
    this.setData({ refundReason: e.detail.value })
  },

  // 炸单次数减少
  onBombMinus() {
    if (this.data.bombCount <= 0) return
    this.setData({ bombCount: this.data.bombCount - 1 })
  },

  // 炸单次数增加
  onBombPlus() {
    this.setData({ bombCount: this.data.bombCount + 1 })
  },

  // 确认退单
  confirmRefund() {
    if (!this.data.refundReason.trim()) {
      wx.showToast({ title: '请输入退单说明', icon: 'none' })
      return
    }

    wx.showModal({
      title: '确认退单',
      content: '确定要退掉这个订单吗？',
      confirmColor: '#FF4D4F',
      success: (res) => {
        if (res.confirm) {
          orderApi.escortCancelOrder(this.data.orderId, this.data.refundReason).then(result => {
            if (result && result.success) {
              this.setData({ showRefund: false })
              wx.showToast({ title: '已退单', icon: 'none' })
              setTimeout(() => {
                wx.navigateBack()
              }, 1500)
            } else {
              wx.showToast({ title: (result && result.message) || '退单失败', icon: 'none' })
            }
          })
        }
      }
    })
  },

  // 开始服务
  onStartService() {
    wx.showModal({
      title: '确认开始',
      content: '确定要开始服务吗？',
      confirmColor: '#FF4D4F',
      success: (res) => {
        if (res.confirm) {
          orderApi.startService(this.data.orderId).then(result => {
            if (result && result.success) {
              wx.showToast({ title: '服务已开始', icon: 'success' })
              // 记录剩余秒数为300
              this._remainingSeconds = 300
              this.loadOrderDetail()
            } else {
              wx.showToast({ title: (result && result.message) || '开始服务失败', icon: 'none' })
            }
          })
        }
      }
    })
  },

  // 完成服务
  onComplete() {
    if (!this.data.canComplete) {
      wx.showToast({ title: '服务时间不足5分钟', icon: 'none' })
      return
    }

    // 显示上传照片弹窗
    this.setData({
      showCompleteModal: true,
      completePhotos: [],
      completeRemark: ''
    })
  },

  // 关闭完成服务弹窗
  hideCompleteModal() {
    this.setData({ showCompleteModal: false })
  },

  // 选择完成照片
  chooseCompletePhoto() {
    const remain = this.data.completePhotoMax - this.data.completePhotos.length
    if (remain <= 0) {
      wx.showToast({ title: `最多${this.data.completePhotoMax}张照片`, icon: 'none' })
      return
    }
    wx.chooseImage({
      count: remain,
      sizeType: ['compressed'],
      sourceType: ['album', 'camera'],
      success: (res) => {
        const tempPaths = res.tempFilePaths.slice(0, remain)
        // 直接使用临时路径（wx.uploadFile 对临时路径支持最好）
        const completePhotos = [...this.data.completePhotos, ...tempPaths]
        this.setData({ completePhotos })
      }
    })
  },

  // 删除完成照片
  deleteCompletePhoto(e) {
    const index = e.currentTarget.dataset.index
    const completePhotos = this.data.completePhotos.filter((_, i) => i !== index)
    this.setData({ completePhotos })
  },

  // 预览完成照片
  previewCompletePhoto(e) {
    const current = e.currentTarget.dataset.url
    wx.previewImage({ current, urls: this.data.completePhotos })
  },

  // 完成备注输入
  onCompleteRemarkInput(e) {
    this.setData({ completeRemark: e.detail.value })
  },

  // 提交完成申请
  submitComplete() {
    if (this.data.completePhotos.length === 0) {
      wx.showToast({ title: '请上传服务完成照片', icon: 'none' })
      return
    }

    wx.showModal({
      title: '确认提交',
      content: '提交后等待管理员审核确认，确认完成后佣金将自动到账',
      confirmColor: '#52C41A',
      success: (res) => {
        if (res.confirm) {
          wx.showLoading({ title: '上传照片中...' })
          // 先上传照片到服务器，再提交完成
          utils.uploadFiles(this.data.completePhotos, 'complete').then(uploadedUrls => {
            wx.hideLoading()
            wx.showLoading({ title: '提交中...' })
            orderApi.submitComplete(
              this.data.orderId,
              uploadedUrls,
              this.data.completeRemark
            ).then(result => {
              wx.hideLoading()
              if (result && result.success) {
                this.setData({ showCompleteModal: false })
                wx.showToast({ title: '已提交，等待确认', icon: 'success' })
                setTimeout(() => {
                  this.loadOrderDetail()
                }, 1000)
              } else {
                wx.showToast({ title: (result && result.message) || '提交失败', icon: 'none' })
              }
            }).catch(err => {
              wx.hideLoading()
              wx.showToast({ title: err.msg || '提交失败', icon: 'none' })
            })
          }).catch(err => {
            wx.hideLoading()
            wx.showToast({ title: '照片上传失败，请重试', icon: 'none' })
          })
        }
      }
    })
  },

  goBack() {
    wx.navigateBack()
  }
})
